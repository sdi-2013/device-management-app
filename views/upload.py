import streamlit as st
import pandas as pd
import io
import uuid
from modules.services import AssetService, ProcessService, CodeService
from modules.database import get_connection
from modules.utils import get_current_date_str

def render_upload():
    st.title("📥 데이터 일괄 업로드 (Admin)")
    
    tab1, tab2 = st.tabs(["📄 장비 마스터 업로드", "🏭 공정 마스터 업로드"])
    
    # --- Helper: Dynamic Asset Types for Validation/Guide ---
    types_df = CodeService.get_common_codes('ASSET_TYPE')
    valid_types = types_df['code_name'].tolist() if not types_df.empty else ["PC", "PDA", "MES단말기", "프린터"]
    type_guide_str = ", ".join(valid_types)
    
    with tab1:
        st.subheader("1. 엑셀 템플릿 다운로드")
        st.markdown(f"**Tip**: 단말기종류는 기초코드에 등록된 값({type_guide_str})을 사용하세요.")
        st.markdown("**Tip**: '현재위치(IP)'를 입력하면 해당 IP를 가진 공정에 자동으로 장비가 투입됩니다.")
        
        # Asset Template
        asset_template = pd.DataFrame(columns=['자체관리번호', '단말기종류', '제조사', '모델명', 'OS', '현재위치(IP)'])
        # Add a sample row
        asset_template.loc[0] = ['M24300001', 'MES단말기', '삼성', 'Galaxy Tab', 'Android 13', '192.168.0.100']
        
        buffer1 = io.BytesIO()
        with pd.ExcelWriter(buffer1, engine='openpyxl') as writer:
            asset_template.to_excel(writer, index=False)
            
        st.download_button("📥 장비 업로드 템플릿 다운로드", data=buffer1.getvalue(), file_name="template_assets.xlsx")
        
        st.divider()
        st.subheader("2. 엑셀 파일 업로드")
        
        # Initialize Button
        if st.expander("🚨 데이터 초기화 옵션"):
            if st.button("🚨 장비 데이터 전체 삭제", type="primary"):
                conn = get_connection()
                try:
                    with conn.cursor() as c:
                        c.execute("DELETE FROM assets")
                    conn.commit()
                    st.toast("장비 데이터가 초기화되었습니다.", icon="🗑️")
                except Exception as e: st.error(f"초기화 실패: {e}")
                finally: conn.close()
            
        f1 = st.file_uploader("장비 엑셀 파일 (.xlsx)", type=['xlsx'], key="u_asset")
        if f1 and st.button("장비 업로드 실행"):
            try:
                df = pd.read_excel(f1)
                
                # Check required
                required_map = {'자체관리번호': 'id', '단말기종류': 'type', '모델명': 'model'}
                missing = [col for col in required_map.keys() if col not in df.columns]
                
                if missing:
                    st.error(f"필수 컬럼 누락: {', '.join(missing)}")
                else:
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        
                        # 1. Prepare Data for Bulk Insert
                        insert_data = []
                        assign_tasks = []
                        
                        total_rows = len(df)
                        progress_bar = st.progress(0, text="데이터 준비 중...")
                        
                        existing_ids_query = "SELECT id FROM assets"
                        c.execute(existing_ids_query)
                        existing = set(r['id'] for r in c.fetchall())
                        
                        skip_count = 0
                        
                        for idx, row in df.iterrows():
                            asset_id = str(row['자체관리번호']).strip()
                            
                            # Skip Duplicate IDs
                            if asset_id in existing:
                                skip_count += 1
                                continue
                            
                            target_ip = str(row.get('현재위치(IP)', '')).strip()
                            if pd.isna(row.get('현재위치(IP)')): target_ip = ""
                            
                            maker = str(row.get('제조사', ''))
                            if pd.isna(maker): maker = ""
                            
                            os_val = str(row.get('OS', ''))
                            if pd.isna(os_val): os_val = ""

                            # Data tuple for INSERT
                            # id, type, maker, model, os, status, location, deploy_date
                            insert_data.append((
                                asset_id, 
                                str(row['단말기종류']).strip(),
                                maker,
                                str(row['모델명']).strip(),
                                os_val,
                                '대기중', '', get_current_date_str()
                            ))
                            
                            if target_ip:
                                # Include Type for Composite Key Matching
                                assign_tasks.append((asset_id, target_ip, str(row['단말기종류']).strip()))
                                
                        # 2. Batch Insert
                        if insert_data:
                            progress_bar.progress(30, text=f"장비 {len(insert_data)}건 DB 저장 중...")
                            c.executemany("""
                                INSERT INTO assets (id, type, maker, model, os, status, location, deploy_date)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, insert_data)
                            conn.commit()
                        
                        # 3. Process Assignment (Composite Key: IP + Type)
                        auto_assign_count = 0
                        failed_assigns = []
                        
                        if assign_tasks:
                            total_assigns = len(assign_tasks)
                            # Get map: (IP, Type) -> List of Process Info
                            # Why list? Because multiple processes might share same IP & Type (e.g. Printer 1, Printer 2)
                            c.execute("SELECT id, ip, type, asset_id FROM processes")
                            proc_rows = c.fetchall()
                            ip_type_to_proc_list = {}
                            
                            def normalize_ip(ip_str):
                                try:
                                    parts = ip_str.split('.')
                                    if len(parts) == 4:
                                        return ".".join([str(int(p.strip())) for p in parts])
                                    return ip_str.strip()
                                except:
                                    return ip_str.strip()

                            for r in proc_rows:
                                if r['ip']:
                                    clean_ip = normalize_ip(str(r['ip']))
                                    p_type = str(r['type']).strip()
                                    key = (clean_ip, p_type)
                                    
                                    if key not in ip_type_to_proc_list:
                                        ip_type_to_proc_list[key] = []
                                    
                                    # Store basic info and mutable 'occupied' flag
                                    # We use 'asset_id' to check if initially occupied from DB
                                    # We use 'temp_assigned' to track assignments during this batch
                                    ip_type_to_proc_list[key].append({
                                        'id': r['id'],
                                        'initial_asset': r['asset_id'],
                                        'temp_assigned': False
                                    })
                            
                            conn.close() 

                            # Warn about potential overflows (More assets than slots)
                            task_counts = {}
                            for _, t_ip, t_type in assign_tasks:
                                key = (normalize_ip(str(t_ip)), t_type)
                                task_counts[key] = task_counts.get(key, 0) + 1
                            
                            # Check if we have enough slots
                            overflows = []
                            for key, count in task_counts.items():
                                slots = ip_type_to_proc_list.get(key, [])
                                if count > len(slots):
                                    overflows.append(f"{key}: 장비 {count}대 vs 공정슬롯 {len(slots)}개")
                                    
                            if overflows:
                                st.warning(f"⚠️ 슬롯 부족 경고: 일부 위치에 준비된 공정보다 더 많은 장비가 할당요청 되었습니다. 초과분은 대기 처리되거나 덮어써질 수 있습니다. ({overflows[0]} 등)")

                            import time
                            
                            for i, (a_id, t_ip, a_type) in enumerate(assign_tasks):
                                pct = 50 + int((i / total_assigns) * 50)
                                progress_bar.progress(pct, text=f"자동 투입 처리 중... ({i+1}/{total_assigns})")
                                
                                clean_target_ip = normalize_ip(str(t_ip))
                                candidates = ip_type_to_proc_list.get((clean_target_ip, a_type), [])
                                
                                target_proc_id = None
                                
                                # Strategy: Find First Empty Slot (not assigned in DB AND not assigned in this batch)
                                for cand in candidates:
                                    if not cand['initial_asset'] and not cand['temp_assigned']:
                                        target_proc_id = cand['id']
                                        cand['temp_assigned'] = True # Mark as taken
                                        break
                                
                                # If no empty slot, try overwriting a slot that hasn't been touched in THIS batch yet
                                # (To replace old equipment with new one)
                                if not target_proc_id:
                                    for cand in candidates:
                                        if not cand['temp_assigned']:
                                            target_proc_id = cand['id']
                                            cand['temp_assigned'] = True
                                            break
                                            
                                # If still None (All slots taken by this batch!), we overwrite the last one? 
                                # Or just fail. Let's fail accurately.
                                
                                if target_proc_id:
                                    # Call Service with log suppression
                                    ok, msg = ProcessService.assign_asset_to_process(target_proc_id, a_id, record_log=False)
                                    if ok: auto_assign_count += 1
                                    else: failed_assigns.append(f"{a_id}({clean_target_ip}/{a_type}): {msg}")
                                else:
                                    if not candidates:
                                         failed_assigns.append(f"{a_id}: 공정 마스터 매칭 실패 (IP:{clean_target_ip}, Type:{a_type})")
                                    else:
                                         failed_assigns.append(f"{a_id}: 가용 공정 슬롯 부족 (IP:{clean_target_ip}, Type:{a_type})")
                            

                            
                            # --- Final Data Sync (The Magic Fix) ---
                            # Ensure all assets linked in Processes table are correctly marked as 'Deployed' in Assets table.
                            # This fixes any inconsistencies where Process is updated but Asset is not.
                            progress_bar.progress(95, text="데이터 무결성 동기화 중...")
                            
                            # Open new connection for sync (Previous one was closed)
                            conn_sync = get_connection()
                            c_sync = conn_sync.cursor()
                            
                            try:
                                c_sync.execute("""
                                    SELECT p.asset_id, p.factory, p.name, p.hogi, p.ip
                                    FROM processes p
                                    WHERE p.asset_id IS NOT NULL AND p.asset_id != ''
                                """)
                                linked_rows = c_sync.fetchall()
                                
                                sync_count = 0
                                today_str = get_current_date_str()
                                
                                for row in linked_rows:
                                    a_id = row['asset_id']
                                    loc_str = f"{row['factory']} {row['name']} {row['hogi']} ({row['ip']})"
                                    
                                    # Force update Asset to match Process
                                    c_sync.execute("""
                                        UPDATE assets 
                                        SET status = '투입중', location = %s, deploy_date = %s 
                                        WHERE id = %s AND (status != '투입중' OR location != %s)
                                    """, (loc_str, today_str, a_id, loc_str))
                                    
                                    if c_sync.rowcount > 0:
                                        sync_count += 1
                                
                                conn_sync.commit()
                                if sync_count > 0:
                                    st.toast(f"데이터 동기화 완료: {sync_count}건의 자산 상태 자동 보정됨", icon="🔧")
                                    
                            except Exception as e:
                                st.error(f"동기화 중 오류 발생: {e}")
                            finally:
                                conn_sync.close()
                            
                            progress_bar.progress(100, text="완료!")
                        else:
                            conn.close()
                            progress_bar.progress(100, text="완료!")
                            
                        st.success(f"처리 완료: 신규저장 {len(insert_data)}건, 중복제외 {skip_count}건, 자동투입 {auto_assign_count}건")
                        
                        if failed_assigns:
                            with st.expander(f"⚠️ 자동 투입 실패 {len(failed_assigns)}건 (확인 필요)"):
                                st.write(failed_assigns)
                        
                    except Exception as e:
                        if conn: conn.close()
                        st.error(f"DB 처리 오류: {e}")
                    
            except Exception as e:
                st.error(f"엑셀 읽기 오류: {e}")

    with tab2:
        st.subheader("1. 엑셀 템플릿 다운로드")
        st.info("시스템 관리 컬럼(ID, 투입장비 등)은 자동 처리되므로 템플릿에 포함되지 않습니다.")
        
        # Process Template - Hiding System Columns
        proc_template = pd.DataFrame(columns=['IP', '공정설정종류', '공정명', '부서', '공장', '호기'])
        proc_template.loc[0] = ['192.168.0.100', 'MES단말기', '도포2호기', '생산1팀', '1공장', '2호기']
        
        buffer2 = io.BytesIO()
        with pd.ExcelWriter(buffer2, engine='openpyxl') as writer:
            proc_template.to_excel(writer, index=False)
            
        st.download_button("📥 공정 업로드 템플릿 다운로드", data=buffer2.getvalue(), file_name="template_processes.xlsx")
        
        st.divider()
        st.subheader("2. 엑셀 파일 업로드")
        
        if st.expander("🚨 데이터 초기화 옵션"):
            if st.button("🚨 공정 데이터 전체 삭제", type="primary"):
                conn = get_connection()
                try:
                    with conn.cursor() as c:
                        c.execute("DELETE FROM processes")
                    conn.commit()
                    st.toast("공정 데이터가 초기화되었습니다.", icon="🗑️")
                except Exception as e: st.error(f"초기화 실패: {e}")
                finally: conn.close()
            
        f2 = st.file_uploader("공정 엑셀 파일 (.xlsx)", type=['xlsx'], key="u_proc")
        if f2 and st.button("공정 업로드 실행"):
            try:
                df = pd.read_excel(f2)
                
                # Check required
                required_map = {'IP': 'ip', '공정명': 'name', '공정설정종류': 'type'}
                missing = [col for col in required_map.keys() if col not in df.columns]
                
                if missing:
                    st.error(f"필수 컬럼 누락: {', '.join(missing)}")
                else:
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        
                        # Data Prep
                        insert_data = []
                        progress_bar = st.progress(0, text="데이터 준비 중...")
                        
                        # Check existing IPs or IDs? Usually check IP for duplicates
                        existing_ips_query = "SELECT ip FROM processes"
                        c.execute(existing_ips_query)
                        existing = set(r['ip'] for r in c.fetchall())
                        
                        skip_count = 0
                        total_rows = len(df)
                        
                        for idx, row in df.iterrows():
                            ip = str(row['IP']).strip()
                            
                            if ip in existing:
                                skip_count += 1
                                continue
                            
                            new_id = str(uuid.uuid4())
                            
                            # id, ip, type, name, dept, factory, hogi, asset_id, deploy_date
                            insert_data.append((
                                new_id,
                                ip,
                                str(row['공정설정종류']).strip(),
                                str(row['공정명']).strip(),
                                str(row.get('부서', '')),
                                str(row.get('공장', '')),
                                str(row.get('호기', '')),
                                '', '' # asset_id, deploy_date
                            ))
                            
                        # Batch Insert
                        if insert_data:
                            progress_bar.progress(50, text=f"공정 {len(insert_data)}건 DB 저장 중...")
                            c.executemany("""
                                INSERT INTO processes (id, ip, type, name, dept, factory, hogi, asset_id, deploy_date)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, insert_data)
                            conn.commit()
                            
                        conn.close()
                        progress_bar.progress(100, text="완료!")
                        
                        st.success(f"처리 완료: 신규생성 {len(insert_data)}건, 중복제외 {skip_count}건")
                        
                    except Exception as e:
                        if conn: conn.close()
                        st.error(f"DB 처리 오류: {e}")
                    
            except Exception as e:
                st.error(f"오류: {e}")
