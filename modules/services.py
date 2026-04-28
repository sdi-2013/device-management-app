from modules.database import get_connection, read_df
from modules.utils import get_current_date_str, get_kst_now
import pandas as pd
import streamlit as st

class AssetService:
    @staticmethod
    def get_all_assets(filters=None):
        conn = get_connection()
        # Modified Query: Join with processes to get REAL-TIME location
        # If a process exists for this asset, construct location string.
        # Otherwise, use empty string or fallback to assets.location (if needed, but better to trust process linkage)
        
        query = """
            SELECT a.*, 
                   CASE 
                       WHEN p.id IS NOT NULL THEN p.factory || ' ' || p.name || ' ' || p.hogi || ' (' || p.ip || ')'
                       ELSE a.location 
                   END as real_location
            FROM assets a
            LEFT JOIN processes p ON a.id = p.asset_id
        """
        params = []
        if filters:
            conditions = []
            for k, v in filters.items():
                if v:
                    # Handle ambiguity or specific columns
                    if k == 'id':
                        conditions.append("a.id LIKE %s")
                    elif k == 'type':
                        conditions.append("a.type LIKE %s")
                    elif k == 'maker':
                        conditions.append("a.maker LIKE %s")
                    else:
                        conditions.append(f"a.{k} LIKE %s")
                    params.append(f"%{v}%")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        df = read_df(query, conn, params=params)
        
        # Override the static 'location' column with dynamic 'real_location'
        if not df.empty and 'real_location' in df.columns:
            df['location'] = df['real_location']
            
        conn.close()
        return df

    @staticmethod
    def create_asset(data):
        conn = get_connection()
        try:
            c = conn.cursor()
            # Check ID
            c.execute("SELECT id FROM assets WHERE id = %s", (data['id'],))
            if c.fetchone():
                return False, "이미 존재하는 관리번호입니다."

            c.execute("""
                INSERT INTO assets (id, type, maker, model, os, status, location, deploy_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
            
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            values = list(updates.values())
            values.append(asset_id)
            
            conn.cursor().execute(f"UPDATE assets SET {set_clause} WHERE id = %s", values)
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
            placeholders = ','.join(['%s'] * len(asset_ids))
            conn.cursor().execute(f"DELETE FROM assets WHERE id IN ({placeholders})", asset_ids)
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
        # Join with assets table to get asset type
        query = """
            SELECT p.*, a.type as asset_type_joined 
            FROM processes p 
            LEFT JOIN assets a ON p.asset_id = a.id
        """
        params = []
        if filters:
            conditions = []
            for k, v in filters.items():
                if v:
                    # Ambiguous columns need prefix
                    if k in ['id', 'type', 'ip', 'name', 'dept', 'factory', 'hogi', 'asset_id']:
                         conditions.append(f"p.{k} LIKE %s")
                    else:
                         conditions.append(f"{k} LIKE %s")
                    params.append(f"%{v}%")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        df = read_df(query, conn, params=params)
        conn.close()
        return df

    @staticmethod
    def create_process(data):
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("INSERT INTO processes (id, ip, type, name, dept, factory, hogi) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                      (data['id'], data['ip'], data['type'], data['name'], data['dept'], data.get('factory'), data.get('hogi')))
            conn.commit()
            return True, "등록되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def update_batch_processes(updates):
        """
        Batch update processes.
        updates: List of tuples (type, name, dept, factory, hogi, id)
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            # Based on views/processes.py: updates is list of (type, name, dept, factory, hogi, id)
            from psycopg2.extras import execute_batch
            execute_batch(c, "UPDATE processes SET type=%s, name=%s, dept=%s, factory=%s, hogi=%s WHERE id=%s", updates)
            conn.commit()
            return True, f"{len(updates)}건 수정 완료"
        except Exception as e:
            conn.rollback() # Important for batch ops
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def assign_asset_to_process(proc_id, asset_id, record_log=True):
        """
        Transactional assignment of asset to process.
        - Release current asset from process (if any).
        - Lock new asset (check status).
        - Assign new asset to process.
        - record_log: If True, records individual movement logs. Set False for bulk ops.
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            
            # Get Process Info
            c.execute("SELECT * FROM processes WHERE id = %s", (proc_id,))
            proc = c.fetchone()
            if not proc: return False, "공정 정보를 찾을 수 없습니다."
            
            current_asset_id = proc['asset_id']
            today = get_current_date_str()
            location_str = f"{proc['factory']} {proc['name']} {proc['hogi']} ({proc['ip']})"
            
            # --- Ghost Cleanup Logic ---
            query = """
                SELECT * FROM assets 
                WHERE status = '투입중' 
                AND type = %s 
                AND location LIKE %s
            """
            c.execute(query, (proc['type'], f"%{proc['ip']}%"))
            ghosts = c.fetchall()
            
            for ghost in ghosts:
                if ghost['id'] != current_asset_id:
                     c.execute("UPDATE assets SET status = '대기중', location = '', deploy_date = '' WHERE id = %s", (ghost['id'],))
                     if record_log:
                         LogService.record_movement(conn, ghost['id'], "반납(중복제거)", ghost['location'], "자재창고(대기)")
            
            # 1. If removing existing
            if current_asset_id:
                c.execute("UPDATE assets SET status = '대기중', location = '', deploy_date = '' WHERE id = %s", (current_asset_id,))
                c.execute("UPDATE processes SET asset_id = '', deploy_date = '' WHERE id = %s", (proc_id,))
                if record_log:
                    LogService.record_movement(conn, current_asset_id, "반납", location_str, "자재창고(대기)")

            # 2. If assigning new
            if asset_id:
                # Check status
                c.execute("SELECT * FROM assets WHERE id = %s", (asset_id,))
                asset_row = c.fetchone()
                if not asset_row: return False, "장비 정보를 찾을 수 없습니다."
                
                if asset_row['status'] == '투입중':
                    c.execute("SELECT * FROM processes WHERE asset_id = %s", (asset_id,))
                    old_proc = c.fetchone()
                    if old_proc:
                        c.execute("UPDATE processes SET asset_id = '', deploy_date = '' WHERE id = %s", (old_proc['id'],))
                        prev_loc_for_new_asset = asset_row['location']
                        if record_log:
                            LogService.record_movement(conn, asset_id, "이동(재배치)", prev_loc_for_new_asset, location_str)
                    else:
                        if record_log:
                            LogService.record_movement(conn, asset_id, "이동(강제배치)", asset_row['location'], location_str)

                else:
                    if record_log:
                        LogService.record_movement(conn, asset_id, "투입", "자재창고(대기)", location_str)
                
                c.execute("UPDATE assets SET status = '투입중', location = %s, deploy_date = %s WHERE id = %s", (location_str, today, asset_id))
                c.execute("UPDATE processes SET asset_id = %s, deploy_date = %s WHERE id = %s", (asset_id, today, proc_id))

            conn.commit()
            return True, "배치 완료"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()


    @staticmethod
    def replace_asset(old_asset_id, new_asset_id, reason, technician, location_snapshot):
        """
        Transactional replacement of an asset in a process.
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            today = get_current_date_str()
            
            # 1. Update Old Asset (Return/Repair)
            # Log format: Existing ID -> New ID / Reason
            log_content = f"{old_asset_id} -> {new_asset_id} / {reason}"
            
            c.execute("UPDATE assets SET status = '수리중', location = '', deploy_date = '' WHERE id = %s", (old_asset_id,))
            
            # 2. Update New Asset (Deploy)
            c.execute("UPDATE assets SET status = '투입중', location = %s, deploy_date = %s WHERE id = %s", (location_snapshot, today, new_asset_id))
            
            # 3. Update Process
            # Find process by old asset to be safe or just update where asset_id matches%s
            # Better to find process first to ensure integrity.
            c.execute("SELECT id FROM processes WHERE asset_id = %s", (old_asset_id,))
            proc_row = c.fetchone()
            if proc_row:
               c.execute("UPDATE processes SET asset_id = %s, deploy_date = %s WHERE id = %s", (new_asset_id, today, proc_row['id']))
            else:
               # Fallback: Try to find process by IP in location_snapshot
               # Format: "Factory Process Hogi (IP)"
               import re
               ip_match = re.search(r'\((.*%s)\)', location_snapshot)
               if ip_match:
                   extracted_ip = ip_match.group(1)
                   c.execute("UPDATE processes SET asset_id = %s, deploy_date = %s WHERE ip = %s", (new_asset_id, today, extracted_ip))
            
            # 4. Logs
            # Movement Log (Old: Deployed -> Repair)
            LogService.record_movement(conn, old_asset_id, "반출(교체)", location_snapshot, "수리실")
            # Movement Log (New: Wait -> Deployed)
            LogService.record_movement(conn, new_asset_id, "투입(교체)", "자재창고(대기)", location_snapshot)
            
            # Maintenance Log (Attached to OLD asset history usually, or both%s Request says: "Existing ID -> New ID / Reason")
            from datetime import datetime
            import uuid
            c.execute("""
                INSERT INTO maintenance_logs (id, asset_id, action_type, content, technician, timestamp, location_snapshot)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (str(uuid.uuid4()), old_asset_id, "교체", log_content, technician, get_kst_now().strftime("%Y-%m-%d %H:%M"), location_snapshot))
            
            conn.commit()
            return True, f"교체 완료 ({old_asset_id} -> {new_asset_id})"
        except Exception as e:
            conn.rollback()
            return False, str(e)

        finally:
            conn.close()

    @staticmethod
    def retrieve_asset(asset_id, reason, technician, location_snapshot):
        """
        Transactional retrieval of asset for repair (Un-deploy).
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            today = get_current_date_str()
            
            # 1. Update Asset (Status -> Repairing)
            c.execute("UPDATE assets SET status = '수리중', location = '', deploy_date = '' WHERE id = %s", (asset_id,))
            
            # 2. Update Process (Remove Link)
            c.execute("UPDATE processes SET asset_id = '', deploy_date = '' WHERE asset_id = %s", (asset_id,))
            
            # 3. Logs
            # Movement Log (Deployed -> Repair)
            LogService.record_movement(conn, asset_id, "반출(수리)", location_snapshot, "수리실")
            
            # Maintenance Log (Reason for retrieval)
            # Log as "수리회수"
            from datetime import datetime
            import uuid
            c.execute("""
                INSERT INTO maintenance_logs (id, asset_id, action_type, content, technician, timestamp, location_snapshot)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (str(uuid.uuid4()), asset_id, "수리회수", reason, technician, get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), location_snapshot))
            
            conn.commit()
            return True, "회수(수리) 처리 완료"
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
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (str(uuid.uuid4()), asset_id, action_type, content, technician, get_kst_now().strftime("%Y-%m-%d %H:%M"), location_snapshot))
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
        df = read_df(query, conn, params=params)
        conn.close()
        return df

    @staticmethod
    def get_movement_logs():
        conn = get_connection()
        df = read_df("SELECT * FROM movement_logs", conn)
        conn.close()
        return df

    @staticmethod
    def record_movement(conn, asset_id, action, prev_loc, new_loc):
        # Helper to be called within a transaction
        import uuid
        from datetime import datetime
        c = conn.cursor()
        c.execute("INSERT INTO movement_logs (id, asset_id, action_type, prev_loc, curr_loc, date) VALUES (%s, %s, %s, %s, %s, %s)",
                  (str(uuid.uuid4()), asset_id, action, prev_loc, new_loc, get_kst_now().strftime("%Y-%m-%d %H:%M:%S")))

    @staticmethod
    def update_maintenance_logs(updates):
        conn = get_connection()
        try:
            c = conn.cursor()
            from psycopg2.extras import execute_batch
            execute_batch(c, "UPDATE maintenance_logs SET action_type=%s, content=%s, technician=%s, timestamp=%s WHERE id=%s", updates)
            conn.commit()
            return True, "수정되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def update_movement_logs(updates):
        # updates: (action_type, prev_loc, curr_loc, date, id)
        conn = get_connection()
        try:
            c = conn.cursor()
            from psycopg2.extras import execute_batch
            execute_batch(c, "UPDATE movement_logs SET action_type=%s, prev_loc=%s, curr_loc=%s, date=%s WHERE id=%s", updates)
            conn.commit()
            return True, "수정되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def delete_maintenance_logs(ids):
        conn = get_connection()
        try:
             placeholders = ','.join(['%s'] * len(ids))
             conn.cursor().execute(f"DELETE FROM maintenance_logs WHERE id IN ({placeholders})", ids)
             conn.commit()
             return True, f"{len(ids)}건 삭제됨"
        except Exception as e: return False, str(e)
        finally: conn.close()

    @staticmethod
    def delete_movement_logs(ids):
        conn = get_connection()
        try:
             placeholders = ','.join(['%s'] * len(ids))
             conn.cursor().execute(f"DELETE FROM movement_logs WHERE id IN ({placeholders})", ids)
             conn.commit()
             return True, f"{len(ids)}건 삭제됨"
        except Exception as e: return False, str(e)
        finally: conn.close()

    @staticmethod
    def delete_mixed_logs(df_to_del):
         # df_to_del columns: ['id', 'src_table']
         mv_ids = df_to_del[df_to_del['src_table'] == 'movement']['id'].tolist()
         mt_ids = df_to_del[df_to_del['src_table'] == 'maintenance']['id'].tolist()
         
         total = 0
         if mv_ids:
             ok, _ = LogService.delete_movement_logs(mv_ids)
             if ok: total += len(mv_ids)
         if mt_ids:
             ok, _ = LogService.delete_maintenance_logs(mt_ids)
             if ok: total += len(mt_ids)
             
         return True, f"총 {total}건 삭제 완료"

class CodeService:
    @staticmethod
    @st.cache_data(ttl=300)
    def get_common_codes(group_code=None, active_only=True, ref_id=None):
        conn = get_connection()
        query = "SELECT * FROM common_codes"
        params = []
        conds = []
        if group_code:
            conds.append("group_code = %s")
            params.append(group_code)
        if active_only:
            conds.append("is_active = TRUE")
        if ref_id is not None:
             # If ref_id is explicit, filter by it. If it's a special flag or we want NULL%s
             # For now, precise match.
             conds.append("ref_id = %s")
             params.append(ref_id)
            
        if conds:
            query += " WHERE " + " AND ".join(conds)
            
        query += " ORDER BY group_code, sort_order ASC"
        df = read_df(query, conn, params=params)
        conn.close()
        return df

    @staticmethod
    def add_common_code(data):
        # data: group_code, code_id, code_name, ref_id (optional)
        conn = get_connection()
        try:
            c = conn.cursor()
            # Sort Order: Max + 1
            # We sort within the group. Ref_id doesn't strictly affect sort order logic but we could scope it.
            # Let's keep global group sort for now.
            c.execute("SELECT MAX(sort_order) FROM common_codes WHERE group_code = %s", (data['group_code'],))
            res = c.fetchone()
            max_sort = res[0] if res[0] is not None else -1
            
            ref = data.get('ref_id', None)
            
            c.execute("INSERT INTO common_codes (group_code, code_id, code_name, sort_order, ref_id) VALUES (%s, %s, %s, %s, %s)",
                      (data['group_code'], data['code_id'], data['code_name'], max_sort + 1, ref))
            conn.commit()
            st.cache_data.clear()
            return True, "등록되었습니다."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def update_common_code(group_code, code_id, updates):
        # updates: dict of field -> value
        # we generally update code_name, sort_order. code_id is usually PK key argument, so not updated.
        conn = get_connection()
        try:
            allowed = ['code_name', 'sort_order', 'ref_id']
            fields = []
            values = []
            for k, v in updates.items():
                if k in allowed:
                    fields.append(f"{k} = %s")
                    values.append(v)
            
            if not fields: return True, "변경 없음"
            
            values.append(group_code)
            values.append(code_id)
            
            sql = f"UPDATE common_codes SET {', '.join(fields)} WHERE group_code = %s AND code_id = %s"
            conn.cursor().execute(sql, values)
            conn.commit()
            st.cache_data.clear()
            return True, "수정되었습니다."
        except Exception as e: return False, str(e)
        finally: conn.close()
        
    @staticmethod
    def delete_common_codes(group_code, code_ids):
        conn = get_connection()
        try:
             placeholders = ','.join(['%s'] * len(code_ids))
             conn.cursor().execute(f"DELETE FROM common_codes WHERE group_code = %s AND code_id IN ({placeholders})", (group_code, *code_ids))
             conn.commit()
             st.cache_data.clear()
             return True, f"{len(code_ids)}건 삭제됨"
        except Exception as e: return False, str(e)
        finally: conn.close()

    @staticmethod
    @st.cache_data(ttl=300)
    def get_failure_codes(device_type=None):
        conn = get_connection()
        query = "SELECT * FROM failure_codes"
        params = []
        if device_type:
            # Logic: Show codes specific to this type AND 'COMMON' codes
            query += " WHERE device_type = %s OR device_type = 'COMMON' OR device_type IS NULL"
            params.append(device_type)
            
        query += " ORDER BY sort_order ASC, category, detail"
        df = read_df(query, conn, params=params)
        conn.close()
        return df

    @staticmethod
    def add_failure_code(device_type, category, detail):
        conn = get_connection()
        try:
            import uuid
            conn.cursor().execute("INSERT INTO failure_codes (id, device_type, category, detail, sort_order) VALUES (%s, %s, %s, %s, 0)",
                         (str(uuid.uuid4()), device_type, category, detail))
            conn.commit()
            st.cache_data.clear()
            return True, "등록완료"
        except Exception as e: return False, str(e)
        finally: conn.close()
        
    @staticmethod
    def update_failure_code(code_id, updates):
        conn = get_connection()
        try:
            allowed = ['device_type', 'category', 'detail', 'sort_order']
            fields = []
            values = []
            for k, v in updates.items():
                if k in allowed:
                    fields.append(f"{k} = %s")
                    values.append(v)
            if not fields: return True, "변경 없음"
            values.append(code_id)
            
            sql = f"UPDATE failure_codes SET {', '.join(fields)} WHERE id = %s"
            conn.cursor().execute(sql, values)
            conn.commit()
            st.cache_data.clear()
            return True, "수정완료"
        except Exception as e: return False, str(e)
        finally: conn.close()

    @staticmethod
    def delete_failure_codes(ids):
        conn = get_connection()
        try:
             placeholders = ','.join(['%s'] * len(ids))
             conn.cursor().execute(f"DELETE FROM failure_codes WHERE id IN ({placeholders})", ids)
             conn.commit()
             st.cache_data.clear()
             return True, f"{len(ids)}건 삭제됨"
        except Exception as e: return False, str(e)
        finally: conn.close()
