from modules.database import get_connection
from modules.utils import get_current_date_str
import pandas as pd

class AssetService:
    @staticmethod
    def get_all_assets(filters=None):
        conn = get_connection()
        query = "SELECT * FROM assets"
        params = []
        if filters:
            conditions = []
            for k, v in filters.items():
                if v:
                    conditions.append(f"{k} LIKE ?")
                    params.append(f"%{v}%")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return df

    @staticmethod
    def create_asset(data):
        conn = get_connection()
        try:
            c = conn.cursor()
            # Check ID
            c.execute("SELECT id FROM assets WHERE id = ?", (data['id'],))
            if c.fetchone():
                return False, "이미 존재하는 관리번호입니다."

            c.execute("""
                INSERT INTO assets (id, type, maker, model, os, status, location, deploy_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['id'], data['type'], data['maker'], data['model'], data['os'], data.get('status', '대기중'), "", data.get('deploy_date', get_current_date_str())))
            conn.commit()
            return True, "등록되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def update_asset(asset_id, updates):
        conn = get_connection()
        try:
            # Handle special logic like 'status' change affecting 'location'
            # This follows the original sync_data_integrity logic
            if 'status' in updates:
                status = updates['status']
                if status in ['대기중', '수리중', '폐기예정']:
                    updates['location'] = ""
                    # Also need to update processes if this asset was deployed (complex logic)
                    # For now, we update the asset. Process sync should be handled via ProcessService or trigger.
            
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values())
            values.append(asset_id)
            
            conn.execute(f"UPDATE assets SET {set_clause} WHERE id = ?", values)
            conn.commit()
            return True, "수정되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def delete_assets(asset_ids):
        conn = get_connection()
        try:
            placeholders = ','.join(['?'] * len(asset_ids))
            conn.execute(f"DELETE FROM assets WHERE id IN ({placeholders})", asset_ids)
            conn.commit()
            return True, f"{len(asset_ids)}건 삭제됨"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

class ProcessService:
    @staticmethod
    def get_all_processes(filters=None):
        conn = get_connection()
        query = "SELECT * FROM processes"
        params = []
        if filters:
            conditions = []
            for k, v in filters.items():
                if v:
                    conditions.append(f"{k} LIKE ?")
                    params.append(f"%{v}%")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return df

    @staticmethod
    def create_process(data):
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("INSERT INTO processes (id, ip, type, name, dept, factory, hogi) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (data['id'], data['ip'], data['type'], data['name'], data['dept'], data.get('factory'), data.get('hogi')))
            conn.commit()
            return True, "등록되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def assign_asset_to_process(proc_id, asset_id):
        """
        Transactional assignment of asset to process.
        - Release current asset from process (if any).
        - Lock new asset (check status).
        - Assign new asset to process.
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            
            # Get Process Info
            c.execute("SELECT * FROM processes WHERE id = ?", (proc_id,))
            proc = c.fetchone()
            if not proc: return False, "공정 정보를 찾을 수 없습니다."
            
            current_asset_id = proc['asset_id']
            today = get_current_date_str()
            location_str = f"{proc['factory']} {proc['name']} {proc['hogi']} ({proc['ip']})"
            
            # 1. If removing existing
            if current_asset_id:
                c.execute("UPDATE assets SET status = '대기중', location = '', deploy_date = '' WHERE id = ?", (current_asset_id,))
                c.execute("UPDATE processes SET asset_id = '', deploy_date = '' WHERE id = ?", (proc_id,))
                # Log Movement (Return)
                LogService.record_movement(conn, current_asset_id, "반납", location_str, "자재창고(대기)")

            
            # 2. If assigning new
            if asset_id:
                # Check status
                c.execute("SELECT status FROM assets WHERE id = ?", (asset_id,))
                asset_row = c.fetchone()
                if not asset_row: return False, "장비 정보를 찾을 수 없습니다."
                if asset_row['status'] != '대기중': return False, f"장비({asset_id})가 '대기중' 상태가 아닙니다."
                
                c.execute("UPDATE assets SET status = '투입중', location = ?, deploy_date = ? WHERE id = ?", (location_str, today, asset_id))
                c.execute("UPDATE processes SET asset_id = ?, deploy_date = ? WHERE id = ?", (asset_id, today, proc_id))
                # Log Movement (Deploy)
                LogService.record_movement(conn, asset_id, "투입", "자재창고(대기)", location_str)

            
            conn.commit()
            return True, "배치 완료"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def replace_asset(old_asset_id, new_asset_id, reason, technician):
        """
        Transactional replacement of an asset in a process.
        - Verifies old asset is currently deployed.
        - Verifies new asset is 'Standby'.
        - Swaps them in the process.
        - Updates both assets' status/location.
        - Records movement logs for both.
        - Records maintenance log for the old asset.
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            today = get_current_date_str()
            
            # 1. Verify Old Asset & Find Process
            c.execute("SELECT * FROM processes WHERE asset_id = ?", (old_asset_id,))
            proc = c.fetchone()
            if not proc: return False, "해당 장비는 현재 공정에 투입된 상태가 아닙니다."
            
            proc_id = proc['id']
            location_str = f"{proc['factory']} {proc['name']} {proc['hogi']} ({proc['ip']})"
            
            # 2. Verify New Asset
            c.execute("SELECT status FROM assets WHERE id = ?", (new_asset_id,))
            new_asset = c.fetchone()
            if not new_asset: return False, "교체할 장비를 찾을 수 없습니다."
            if new_asset['status'] != '대기중': return False, f"교체할 장비({new_asset_id})가 '대기중' 상태가 아닙니다."
            
            # 3. Transaction Operations
            # Process: Update asset_id
            c.execute("UPDATE processes SET asset_id = ?, deploy_date = ? WHERE id = ?", (new_asset_id, today, proc_id))
            
            # Old Asset: Status -> Repair/Return (User logic usually implies it's broken or just returned)
            # We set it to '수리중' as default for replacement context, or '대기중' if just swap. 
            # Given 'Inspection' context, usually it's '수리중'.
            c.execute("UPDATE assets SET status = '수리중', location = '', deploy_date = '' WHERE id = ?", (old_asset_id,))
            
            # New Asset: Status -> Deployed
            c.execute("UPDATE assets SET status = '투입중', location = ?, deploy_date = ? WHERE id = ?", (location_str, today, new_asset_id))
            
            # Logs
            # Movement
            LogService.record_movement(conn, old_asset_id, "반출(교체)", location_str, "수리실/자재창고")
            LogService.record_movement(conn, new_asset_id, "투입(교체)", "자재창고(대기)", location_str)
            
            # Maintenance Log (linked to old asset)
            from datetime import datetime
            import uuid
            c.execute("""
                INSERT INTO maintenance_logs (id, asset_id, action_type, content, technician, timestamp, location_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), old_asset_id, "교체", reason, technician, datetime.now().strftime("%Y-%m-%d %H:%M"), location_str))
            
            conn.commit()
            return True, f"교체 완료 ({old_asset_id} -> {new_asset_id})"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()


class LogService:
    @staticmethod
    def log_inspection(asset_id, action_type, content, technician, location_snapshot):
        conn = get_connection()
        try:
            import uuid
            from datetime import datetime
            c = conn.cursor()
            c.execute("""
                INSERT INTO maintenance_logs (id, asset_id, action_type, content, technician, timestamp, location_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), asset_id, action_type, content, technician, datetime.now().strftime("%Y-%m-%d %H:%M"), location_snapshot))
            conn.commit()
            return True, "저장되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
            
    @staticmethod
    def get_maintenance_logs(filters=None):

        conn = get_connection()
        query = "SELECT * FROM maintenance_logs"
        params = []
        # Add basic filtering if needed
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return df

    @staticmethod
    def get_movement_logs():
        conn = get_connection()
        df = pd.read_sql("SELECT * FROM movement_logs", conn)
        conn.close()
        return df

    @staticmethod
    def record_movement(conn, asset_id, action, prev_loc, new_loc):
        # Helper to be called within a transaction
        import uuid
        from datetime import datetime
        c = conn.cursor()
        c.execute("INSERT INTO movement_logs (id, asset_id, action_type, prev_location, curr_location, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), asset_id, action, prev_loc, new_loc, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

