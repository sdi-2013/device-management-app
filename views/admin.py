import streamlit as st
import pandas as pd
import hashlib
from modules.database import get_connection

def hash_password(password):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), b'salt_123', 100000).hex()

def render_user_mgmt():
    st.title("👥 사용자 관리 (Admin)")
    
    # 1. List Users
    conn = get_connection()
    from modules.database import read_df
    users = read_df("SELECT id, name, role, must_change_pw FROM users", conn)
    conn.close()
    
    st.caption(f"총 {len(users)}명")
    st.dataframe(users, use_container_width=True, hide_index=True)
    
    # 2. Add User
    with st.expander("➕ 사용자 추가"):
        with st.form("add_user"):
            uid = st.text_input("아이디")
            uname = st.text_input("이름")
            upw = st.text_input("비밀번호", type="password")
            urole = st.selectbox("권한", ["user", "admin"])
            
            if st.form_submit_button("추가"):
                if uid and uname and upw:
                    conn = get_connection()
                    try:
                        with conn.cursor() as c:
                            c.execute("INSERT INTO users (id, password_hash, name, role, must_change_pw) VALUES (%s, %s, %s, %s, %s)",
                                      (uid, hash_password(upw), uname, urole, True))
                        conn.commit()
                        st.success("추가되었습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")
                    finally:
                        conn.close()
                else:
                    st.warning("모든 필드를 입력하세요.")

from modules.services import CodeService
from views.common_ui import render_grid_with_edit

def render_code_master():
    st.title("🏷️ 기초 코드 관리")
    
    tab1, tab2 = st.tabs(["📦 공통 코드 관리", "🛠️ 고장 코드 관리"])
    
    # --- Tab 1: Common Codes ---
    with tab1:
        st.info("단말기 종류를 기준으로 제조사, 운영체제 등을 관리합니다.")
        
        # 1. Group Selector (Selectbox for Mobile Safety)
        groups = {
            'ASSET_TYPE': '단말기 종류 (최상위)',
            'MAKER': '제조사',
            'OS': '운영체제',
            'ASSET_STATUS': '장비 상태'
        }
        
        # Reverse map for display
        group_opts = list(groups.keys())
        def format_group(x): return groups.get(x, x)
        
        sel_group_key = st.selectbox("관리할 항목 선택", group_opts, format_func=format_group)
        
        # Logic Divider
        parent_group = None
        if sel_group_key == 'ASSET_TYPE':
             parent_group = None
        elif sel_group_key == 'MODEL':
             parent_group = 'MAKER'
        else:
             parent_group = 'ASSET_TYPE'
             
        is_root = (parent_group is None)
        
        selected_ref_id = None
        selected_ref_name = "공통"
        parent_opts = {}
        
        if not is_root:
            # Fetch Parent Codes for Dependency
            parents_df = CodeService.get_common_codes(parent_group)
            
            if parents_df.empty:
                st.warning(f"⚠️ 먼저 상위 항목('{groups.get(parent_group, parent_group)}')을 등록해야 합니다.")
                st.stop()
                
            # Create options: Name (ID)
            # For Maker, we might want to distinguish if names are same? (Usually rare in this limited scope)
            parent_opts = {f"{t['code_name']}": t['code_id'] for t in parents_df.to_dict('records')}
            
            # Parent Selector (For VIEWING)
            st.markdown(f"##### 🔗 조회할 '{groups[sel_group_key]}'의 상위 항목({groups.get(parent_group)}) 선택")
            
            # Options: All + Specific Parents
            display_opts = ["전체 보기"] + list(parent_opts.keys())
            
            sel_parent_name = st.selectbox(f"{groups.get(parent_group)} 선택 (조회용)", display_opts, key=f"ref_sel_{sel_group_key}")
            
            if sel_parent_name == "전체 보기":
                selected_ref_id = None
                selected_ref_name = "전체"
            else:
                selected_ref_id = parent_opts[sel_parent_name]
                selected_ref_name = sel_parent_name
            
            st.divider()

        # 2. Add Code (Multi-select supported)
        action_label = groups[sel_group_key]
        
        with st.expander(f"➕ {action_label} 추가", expanded=True):
            with st.form(f"add_code_{sel_group_key}"):
                # Layout depends on if we have extra inputs (Default Model)
                if sel_group_key == 'MAKER':
                    c1, c2 = st.columns(2)
                    new_code_name = c1.text_input(f"{action_label} 명칭")
                    new_model_name = c2.text_input("초기 모델 등록 (옵션)", placeholder="제조사 등록 시 모델 자동 생성")
                else:
                    new_code_name = st.text_input(f"{action_label} 명칭")
                    new_model_name = ""
                
                # Multi-select for Target Types (Only if not root)
                target_ref_ids = []
                if not is_root:
                    # Logic for default selection: 
                    # If "All" is selected in view, default to None? Or Empty?
                    # If specific parent selected, default to it.
                    default_sel = []
                    if selected_ref_id is not None and sel_parent_name in parent_opts:
                        default_sel = [sel_parent_name]
                        
                    sel_targets = st.multiselect(f"적용 대상 ({groups.get(parent_group)}) - 다중 선택 가능", list(parent_opts.keys()), default=default_sel)
                    target_ref_ids = [parent_opts[n] for n in sel_targets]
                
                if st.form_submit_button("추가"):
                    if new_code_name:
                        # Logic: Iterate targets
                        targets = target_ref_ids if not is_root else [None]
                        if not is_root and not targets:
                            st.error("적용 대상을 하나 이상 선택하세요.")
                        else:
                            import uuid
                            success_count = 0
                            for ref in targets:
                                # Always Auto-Generate ID
                                # Format: GROUP_HASH or similar
                                # To avoid duplicates if Name is same but different Ref?
                                # We stick to random suffix.
                                final_cid = f"{sel_group_key}_{str(uuid.uuid4())[:8]}"
                                
                                res, msg = CodeService.add_common_code({
                                    'group_code': sel_group_key,
                                    'code_id': final_cid,
                                    'code_name': new_code_name,
                                    'ref_id': ref
                                })
                                if res: 
                                    success_count += 1
                                    
                                    # If Maker & Model requested
                                    if new_model_name:
                                        m_cid = f"MODEL_{str(uuid.uuid4())[:8]}"
                                        CodeService.add_common_code({
                                            'group_code': 'MODEL',
                                            'code_id': m_cid,
                                            'code_name': new_model_name,
                                            'ref_id': final_cid # Link to Maker
                                        })
                                
                            if success_count > 0: 
                                st.success(f"{success_count}건 등록 완료"); st.rerun()
                            else: 
                                st.error("등록 실패")
                    else:
                        st.warning("명칭을 입력하세요.")

        # 3. List
        # Filter by Ref ID if not root. If selected_ref_id is None (ALL), pass None (Service handles it?)
        # Let's check Service. get_common_codes(ref_id=None) might mean "No Filter" OR "ref_id IS NULL"?
        # Service logic: if ref_id is not None: conds.append("ref_id = ?")
        # So passing None means "Don't filter by ref_id", which returns ALL. Correct.
        
        df_common = CodeService.get_common_codes(sel_group_key, ref_id=selected_ref_id if not is_root else None)
        
        def del_common_cb(ids):
            return CodeService.delete_common_codes(sel_group_key, ids)

        if not df_common.empty:
            df_display = df_common[['code_id', 'code_name', 'sort_order', 'ref_id']].copy()
            
            # Dynamic Ref Info
            if not is_root:
                if selected_ref_id is None: # ALL View
                    # Map ref_id to Name using parent_opts (reverse lookup needed)
                    # parent_opts is "Name" -> ID. Reverse it.
                    id_to_name = {v: k for k, v in parent_opts.items()}
                    df_display['ref_info'] = df_display['ref_id'].map(id_to_name).fillna("알 수 없음")
                else:
                    df_display['ref_info'] = selected_ref_name
            else:
                df_display['ref_info'] = "-"
            
            # Logic for Showing Linked Models (If Group is MAKER)
            extra_cols = []
            if sel_group_key == 'MAKER':
                # Fetch all models to map them
                models_all = CodeService.get_common_codes('MODEL')
                if not models_all.empty:
                    # Group by ref_id (Maker ID)
                    model_map = models_all.groupby('ref_id')['code_name'].apply(lambda x: ", ".join(x)).to_dict()
                    df_display['models'] = df_display['code_id'].map(model_map).fillna("")
                else:
                    df_display['models'] = ""
                extra_cols.append("models")

            # Column Config
            col_cfg = {
                "code_id": st.column_config.TextColumn("코드ID"), # Hidden via column_order
                "code_name": st.column_config.TextColumn("명칭"),
                "sort_order": st.column_config.NumberColumn("정렬순서", disabled=True) # Fix type error
            }
            
            # Dynamic Ref Info Config
            if not is_root:
                 col_cfg["ref_info"] = st.column_config.TextColumn(f"상위항목 ({groups.get(parent_group, '-')})", disabled=True)
            
            if 'models' in extra_cols:
                col_cfg['models'] = st.column_config.TextColumn("등록된 모델", disabled=True, width="large")
            
            def update_common_cb(row_id, row_dict):
                return CodeService.update_common_code(sel_group_key, row_id, row_dict)
            
            # Construction of final column order
            # User Feedback: Hide Sort Order. Hide Parent if Root. Code ID already hidden.
            final_col_order = ["select"]
            if not is_root:
                final_col_order.append("ref_info")
            
            final_col_order.append("code_name")
            final_col_order.extend(extra_cols)
            
            # sort_order excluded.
            
            render_grid_with_edit(
                df_display,
                key_col='code_id',
                update_callback=update_common_cb,
                column_config=col_cfg,
                column_order=final_col_order, 
                can_delete=True,
                delete_callback=del_common_cb,
                label=f"common_{sel_group_key}_{selected_ref_id}",
                hide_id=False # Index column hide/show. We use checkbox as selector.
            )
        else:
            st.info(f"등록된 '{groups[sel_group_key]}' 코드가 없습니다.")

    # --- Tab 2: Failure Codes ---
    with tab2:
        st.info("단말기 종류별 고장 유형을 관리합니다.")
        
        types_df = CodeService.get_common_codes('ASSET_TYPE')
        if types_df.empty:
            st.warning("등록된 단말기 종류가 없습니다.")
        else:
            # 1. Target Type Select (For VIEWING)
            type_map = {t['code_name']: t['code_id'] for t in types_df.to_dict('records')}
            
            sel_fail_type_name = st.selectbox("조회할 단말기 종류 선택", list(type_map.keys()), key="fail_code_type_sel")
            target_dev_key = sel_fail_type_name # Using Name
            
            # 2. Add Code (Multi-select)
            with st.expander(f"➕ 고장 유형 추가"):
                with st.form("add_fail_code"):
                    # Type Multi-select
                    default_sel_fail = [sel_fail_type_name] if sel_fail_type_name in type_map else []
                    sel_fail_targets = st.multiselect("적용 대상 (단말기 종류) - 다중 선택 가능", list(type_map.keys()), default=default_sel_fail)
                    
                    c1, c2 = st.columns(2)
                    cat_input = c1.text_input("대분류 (예: 화면 불량)")
                    detail_input = c2.text_input("상세 내용 (예: 깨짐)")
                    
                    if st.form_submit_button("추가"):
                        if cat_input and detail_input and sel_fail_targets:
                            count = 0
                            for t_name in sel_fail_targets:
                                # t_name is the Key (Name)
                                res, msg = CodeService.add_failure_code(t_name, cat_input, detail_input)
                                if res: count += 1
                            
                            st.success(f"{count}개 유형에 등록 완료"); st.rerun()
                        else:
                            st.warning("내용과 대상을 모두 입력하세요.")

            # 3. List
            df_fail = CodeService.get_failure_codes(target_dev_key)
            
            def del_fail_cb(ids):
                return CodeService.delete_failure_codes(ids)
            
            def update_fail_cb(row_id, row_dict):
                return CodeService.update_failure_code(row_id, row_dict)
                
            if not df_fail.empty:
                    # Prepare options for device_type editing
                    type_options = list(type_map.keys())
                    
                    render_grid_with_edit(
                        df_fail,
                        key_col='id',
                        update_callback=update_fail_cb,
                        column_config={
                            "device_type": st.column_config.SelectboxColumn("적용 대상", options=type_options, required=True),
                            "category": st.column_config.TextColumn("대분류"),
                            "detail": st.column_config.TextColumn("상세 내용"),
                            "sort_order": st.column_config.NumberColumn("정렬순서", disabled=True) # Fix type error
                        },
                    column_order=["select", "device_type", "category", "detail"],
                    can_delete=True,
                    delete_callback=del_fail_cb,
                    label=f"fail_codes_{target_dev_key}",
                    hide_id=True
                )
            else:
                st.info("등록된 고장 코드가 없습니다.")
