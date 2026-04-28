import streamlit as st
import pandas as pd
import cv2
import numpy as np
import re
from modules.services import AssetService, ProcessService, LogService
from modules.database import get_connection

def render_inspection():
    st.title("🔧 현장 장비 점검")
    
    # --- 1. Load Master Data ---
    # Moved to dynamic loading inside asset selection for filtering
    
    # --- 2. Search / Scan Section ---
    target_asset = None
    
    tab1, tab2 = st.tabs(["🔍 통합 검색", "📸 QR 스캔"])
    
    with tab1:
        assets = AssetService.get_all_assets()
        if not assets.empty:
            # Create Label
            assets['search_label'] = assets.apply(lambda x: f"[{x['id']}] {x['model']} ({x['status']}) - {x['location']}", axis=1)
            
            # Text Input for Search
            sc1, sc2 = st.columns([8, 2], gap="small")
            search_query_raw = sc1.text_input("장비 검색", placeholder="ID, 모델, 위치 등 (예: 0048)", label_visibility="collapsed")
            do_search = sc2.button("검색", type="primary", use_container_width=True)
            
            st.caption("💡 검색어 입력 후 'Enter' 또는 '검색' 버튼을 누르세요.")
            
            # Use raw query
            search_query = search_query_raw
            
            filtered_assets = pd.DataFrame()
            
            target_asset = None
            
            if search_query:
                # Filter Logic
                # 1. Exact ID
                exact_match = assets[assets['id'] == search_query]
                # 2. Contains ID
                id_match = assets[assets['id'].str.contains(search_query, case=False) & (assets['id'] != search_query)]
                # 3. Contains Others (Model, Location)
                other_match = assets[assets['search_label'].str.contains(search_query, case=False) & ~assets['id'].str.contains(search_query, case=False)]
                
                # Concatenate with priority
                filtered_assets = pd.concat([exact_match, id_match, other_match])
                
                # Remove duplicates just in case
                filtered_assets = filtered_assets.drop_duplicates(subset=['id'])
                
            else:
                # Show all? Too many. Show nothing or recent?
                # User said "Enter 안쳐도 아래쪽에 바로 보여주면".
                # If empty, showing nothing is cleaner OR show all.
                # Let's show all but top 100?
                filtered_assets = assets.head(100)

            # Display List
            if not filtered_assets.empty:
                # Determine Auto-Collapse State
                # Check directly in session state if selection exists for this key
                # Key format: f"asset_sel_df_{search_query}"
                # We default to Expanded (True). If selection exists, Collapse (False).
                df_key = f"asset_sel_df_{search_query}"
                is_expanded = True
                
                # Check session state for selection
                ss_data = st.session_state.get(df_key)
                if ss_data and ss_data.get("selection") and ss_data["selection"].get("rows"):
                     is_expanded = False
                
                with st.expander(f"검색 결과 ({len(filtered_assets)}건)", expanded=is_expanded):
                    # Show Dataframe with Selection
                    # Columns to show: id, model, location, status
                    display_df = filtered_assets[['id', 'model', 'location', 'status']].copy()
                    display_df.rename(columns={'id': 'ID', 'model': '모델', 'location': '위치', 'status': '상태'}, inplace=True)
                    
                    # Use st.dataframe selection (Streamlit 1.35+)
                    event = st.dataframe(
                        display_df,
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        key=df_key
                    )
                    
                    if event.selection.rows:
                        idx = event.selection.rows[0]
                        selected_id = display_df.iloc[idx]['ID']
                        target_asset = assets[assets['id'] == selected_id].iloc[0]
                    elif len(filtered_assets) == 1 and search_query:
                         pass
            else:
                if search_query: st.warning("검색 결과가 없습니다.")
                
    with tab2:
        img_file = st.camera_input("QR 코드를 비춰주세요")
        if img_file:
            try:
                file_bytes = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
                img = cv2.imdecode(file_bytes, 1)
                detector = cv2.QRCodeDetector()
                data, bbox, _ = detector.detectAndDecode(img)
                if data:
                    assets = AssetService.get_all_assets({'id': data})
                    if not assets.empty:
                        target_asset = assets.iloc[0]
                        st.success(f"QR 인식 성공: {data}")
                    else: st.error(f"등록되지 않은 장비입니다: {data}")
            except Exception as e: st.error(f"QR 스캔 오류: {e}")

    # --- 3. Inspection Action Section ---
    if target_asset is not None:
        st.divider()
        st.subheader("📋 점검 및 조치")
        
        # Display Info & Resolve Location
        from modules.database import read_df
        conn = get_connection()
        proc = read_df("SELECT * FROM processes WHERE asset_id = %s", conn, params=(target_asset['id'],))
        
        # IP Fallback Logic
        if proc.empty and target_asset['status'] == '투입중' and target_asset['location']:
            ip_match = re.search(r'\((.*?)\)', target_asset['location'])
            if ip_match:
                extracted_ip = ip_match.group(1)
                proc = read_df("SELECT * FROM processes WHERE ip = %s", conn, params=(extracted_ip,))
        conn.close()
        
        is_deployed = not proc.empty
        current_loc_str = target_asset['location']
        
        p_row = None
        if is_deployed:
            p_row = proc.iloc[0]
            current_loc_str = f"{p_row['factory']} {p_row['name']} {p_row['hogi']} ({p_row['ip']})"
            st.success(f"**현재 위치**: {current_loc_str}")
        else:
            if target_asset['status'] == '투입중':
                 st.warning(f"**현재 위치**: 공정 데이터 미연결 ({current_loc_str})")
                 if not proc.empty: is_deployed = True; p_row = proc.iloc[0]
            else:
                 st.info(f"**현재 위치**: 미배치 ({target_asset['status']})")

        st.markdown("---")
        
        # Fetch Dynamic Failure Codes based on Asset Type
        from modules.services import CodeService
        fail_codes_df = CodeService.get_failure_codes(target_asset['type'])
        
        if fail_codes_df.empty:
             m_cats = ["선택하세요", "기타"]
        else:
             m_cats = ["선택하세요"] + sorted(fail_codes_df['category'].unique().tolist())
        
        # --- Default Value Logic for Undeployed Assets ---
        is_new_deploy = False
        if not is_deployed and target_asset['status'] == '대기중':
            is_new_deploy = True
            # Ensure "신규투입" option exists
            if "신규투입" not in m_cats: m_cats.append("신규투입")
            
        # Determine Main Code Index
        main_idx = 0
        if is_new_deploy and "신규투입" in m_cats:
            main_idx = m_cats.index("신규투입")
        
        # Interactive UI
        c1, c2 = st.columns(2)
        
        # Failure Codes
        main_code = c1.selectbox("고장 대분류", m_cats, index=main_idx, key="insp_main_cat")
        sub_codes = []
        if main_code != "선택하세요":
            if main_code == "신규투입":
                sub_codes = ["장비투입"]
            elif not fail_codes_df.empty:
                sub_codes = fail_codes_df[fail_codes_df['category'] == main_code]['detail'].tolist()
            else:
                sub_codes = ["기타"]
        
        # Ensure '장비투입' exists if new deploy
        if is_new_deploy and "장비투입" not in sub_codes: 
             pass # Logic handles via "신규투입" selection causing sub_codes=["장비투입"]
             
        # Determine Sub Code Index
        sub_idx = 0
        sub_opts = ["선택하세요"] + sorted(list(set(sub_codes)))
        
        if is_new_deploy and main_code == "신규투입" and "장비투입" in sub_opts:
            sub_idx = sub_opts.index("장비투입")
            
        sub_code = c2.selectbox("상세 유형", sub_opts, index=sub_idx, key="insp_sub_cat")
        

        # Memo Default
        memo_default = ""
        if is_new_deploy: memo_default = "장비 신규투입"
        
        memo = st.text_area("점검 내용 및 조치사항", value=memo_default, placeholder="구체적인 내용을 입력하세요...")
        
        st.markdown("#### 🛠️ 조치 방법 선택")
        

        
        # Requests: 단순 점검, 부품 교체, 수리회수, 장비교체
        # Logic Mapping:
        # 1. 단순 점검 -> Log Only
        # 2. 부품 교체 -> Log Only
        # 3. 수리회수 -> Retrieve Asset (Undeploy)
        # 4. 장비교체 -> Replace Asset
        
        # Dynamic Action Types
        asset_type_name = target_asset['type']
        types_df = CodeService.get_common_codes('ASSET_TYPE')
        matching_type = types_df[types_df['code_name'] == asset_type_name]
        
        action_options = []
        if not matching_type.empty:
            type_id = matching_type.iloc[0]['code_id']
            actions_df = CodeService.get_common_codes('ACTION_TYPE', ref_id=type_id)
            if not actions_df.empty:
                action_options = actions_df['code_name'].tolist()
        
        if not action_options:
             action_options = ["단순 점검", "부품 교체", "수리회수", "장비교체"]
        
        # Force "장비투입" if undeployed
        if "장비투입" not in action_options:
            action_options.append("장비투입")
            
        # Determine Action Index
        act_idx = 0
        if is_new_deploy and "장비투입" in action_options:
             act_idx = action_options.index("장비투입")
        
        action_type_sel = st.selectbox("조치 구분", action_options, index=act_idx)
        
        new_asset_id = None
        target_process_id = None
        
        if action_type_sel == "장비투입":
             st.info("🏭 투입할 공정 선택")
             
             # Fetch all processes
             all_procs = ProcessService.get_all_processes()
             if all_procs.empty:
                 st.error("등록된 공정이 없습니다.")
             else:
                 # Sort: Empty asset first
                 all_procs['sort_key'] = all_procs['asset_id'].apply(lambda x: 0 if not x else 1)
                 all_procs = all_procs.sort_values('sort_key')
                 
                 # Label
                 def p_fmt(r):
                     base = f"{r['factory']} {r['name']} {r['hogi']} ({r['ip']})"
                     if r['asset_id']:
                         return base + f" - [사용중: {r['asset_id']}]"
                     else:
                         return base + " - [미사용]"
                 
                 all_procs['label'] = all_procs.apply(p_fmt, axis=1)
                 
                 # Map label to ID
                 p_map = dict(zip(all_procs['label'], all_procs['id']))
                 
                 sel_proc = st.selectbox("공정 선택", ["선택하세요"] + list(p_map.keys()))
                 if sel_proc != "선택하세요":
                     target_process_id = p_map[sel_proc]
                     
                     if "사용중" in sel_proc:
                         st.warning("⚠️ 해당 공정에는 이미 장비가 투입되어 있습니다. (기존 장비는 반납 처리됨)")
        if action_type_sel == "장비교체":
            if not is_deployed:
                 st.warning("⚠️ 현재 장비가 공정에 배치되어 있지 않습니다. (장비교체는 배치된 장비에 대해 수행)")
                 
            st.info("🔄 대체 단말기 선택")
            
            # Fetch ALL assets of same type
            same_type_assets = AssetService.get_all_assets({'type': target_asset['type']})
            
            if same_type_assets.empty:
                st.error("교체 가능한 동일 기종 장비가 없습니다.")
            else:
                # Remove current asset from list
                same_type_assets = same_type_assets[same_type_assets['id'] != target_asset['id']].copy()
                
                # Sort: Undeployed (Waiting) first
                same_type_assets['sort_key'] = same_type_assets['status'].apply(lambda x: 0 if x == '대기중' else 1)
                same_type_assets = same_type_assets.sort_values('sort_key')
                
                def format_asset_label(row):
                    base = f"[{row['id']}/{row['type']}"
                    if row['status'] == '대기중':
                        return base + "/- / - / - / -] (대기중)"
                    else:
                        return base + f"/{row['location']}] ({row['status']})"

                same_type_assets['display_label'] = same_type_assets.apply(format_asset_label, axis=1)
                
                sel_sa = st.selectbox("교체 투입할 장비 (미투입 장비 우선)", same_type_assets['display_label'].tolist())
                if sel_sa:
                    new_asset_id = sel_sa.split('/')[0].replace('[', '')

        st.markdown("<br>", unsafe_allow_html=True)
        
        technician = st.text_input("담당자", value=st.session_state.user_info.get('name', ''), disabled=True)
        
        if st.button("💾 저장 및 적용", type="primary"):
            # Validation
            if main_code == "선택하세요" or sub_code == "선택하세요":
                st.error("고장 유형을 선택해주세요.")
                return
            if not memo:
                st.error("내용을 입력해주세요.")
                return

            full_reason = f"[{main_code}-{sub_code}] {memo}"
            
            if action_type_sel == "장비교체":
                if not new_asset_id:
                     st.error("교체할 장비를 선택해야 합니다.")
                     return
                
                success, msg = ProcessService.replace_asset(
                    target_asset['id'], 
                    new_asset_id, 
                    full_reason, 
                    technician, 
                    current_loc_str
                )
                if success:
                    st.balloons(); st.success(f"교체 완료! {msg}"); st.rerun()
                else:
                    st.error(f"교체 실패: {msg}")

            elif action_type_sel == "장비투입":
                if not target_process_id:
                    st.error("투입할 공정을 선택해야 합니다.")
                    return
                
                success, msg = ProcessService.assign_asset_to_process(target_process_id, target_asset['id'])
                if success:
                    # Log additional inspection log?
                    LogService.log_inspection(target_asset['id'], action_type_sel, full_reason, technician, "자재창고(대기) -> 현장")
                    st.balloons(); st.success(f"투입 완료! {msg}"); st.rerun()
                else:
                    st.error(f"투입 실패: {msg}")
                    
            elif action_type_sel == "수리회수":
                # Retrieve (Un-deploy) logic
                success, msg = ProcessService.retrieve_asset(
                    target_asset['id'],
                    full_reason,
                    technician,
                    current_loc_str
                )
                if success:
                    st.success(f"회수 완료! {msg}"); st.rerun()
                else:
                    st.error(f"회수 실패: {msg}")
                    
            else:
                # 단순 점검, 부품 교체
                success, msg = LogService.log_inspection(target_asset['id'], action_type_sel, full_reason, technician, current_loc_str)
                if success:
                    st.success(msg); st.rerun()
                else:
                    st.error(msg)
