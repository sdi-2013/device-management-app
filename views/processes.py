import streamlit as st
import pandas as pd
from modules.services import ProcessService, AssetService
import uuid

def render_process_master():
    st.title("🏭 공정 마스터 조회")
    
    # --- Filter ---
    with st.expander("🔍 상세 검색 필터", expanded=True):
        if st.button("🔄 검색 조건 초기화", key="reset_search_proc"):
            # Clear specific keys
            keys_to_clear = ["proc_f_dept", "proc_f_factory", "proc_f_name", "proc_f_type"]
            for k in keys_to_clear:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
        
        # Load Data
        df_all = ProcessService.get_all_processes()
        
        if df_all.empty:
            st.info("데이터가 없습니다.")
            st.stop()
            
        # Layout: 5 Columns
        # Order: IP, Dept, Factory, Name, Type
        c1, c2, c3, c4, c5 = st.columns(5)
        
        # 1. IP (Independent Text)
        f_ip = c1.text_input("IP 검색", key="proc_f_ip")
        
        # 2. Dept (Priority 1, Single Select)
        # Options from full data
        depts_opts = ["전체"] + sorted([x for x in df_all['dept'].unique() if pd.notna(x) and x])
        sel_dept = c2.selectbox("부서", depts_opts, key="proc_f_dept")
        
        # Filter Step 1
        step1_df = df_all.copy()
        if sel_dept != "전체":
            step1_df = step1_df[step1_df['dept'] == sel_dept]
            
        # 3. Factory (Priority 2, Multi Select)
        # Options from Step 1
        factories_opts = sorted([x for x in step1_df['factory'].unique() if pd.notna(x) and x])
        
        # Sanitize
        if "proc_f_factory" in st.session_state:
            st.session_state["proc_f_factory"] = [x for x in st.session_state["proc_f_factory"] if x in factories_opts]
            
        sel_factories = c3.multiselect("공장", factories_opts, placeholder="전체", key="proc_f_factory")
        
        # Filter Step 2
        step2_df = step1_df.copy()
        if sel_factories:
            step2_df = step2_df[step2_df['factory'].isin(sel_factories)]
            
        # 4. Name (Process Name) (Priority 3, Multi Select)
        # Options from Step 2
        names_opts = sorted([x for x in step2_df['name'].unique() if pd.notna(x) and x])
        
        if "proc_f_name" in st.session_state:
             st.session_state["proc_f_name"] = [x for x in st.session_state["proc_f_name"] if x in names_opts]
             
        sel_names = c4.multiselect("공정명", names_opts, placeholder="전체", key="proc_f_name")
        
        # Filter Step 3
        step3_df = step2_df.copy()
        if sel_names:
            step3_df = step3_df[step3_df['name'].isin(sel_names)]
            
        # 5. Type (Priority 4, Multi Select)
        # Options from Step 3
        types_opts = sorted([x for x in step3_df['type'].unique() if pd.notna(x) and x])
        
        if "proc_f_type" in st.session_state:
             st.session_state["proc_f_type"] = [x for x in st.session_state["proc_f_type"] if x in types_opts]
             
        sel_types = c5.multiselect("공정설정종류", types_opts, placeholder="전체", key="proc_f_type")
        
        # Final Filter
        df = step3_df.copy()
        if sel_types:
            df = df[df['type'].isin(sel_types)]
            
        # Apply IP Filter (Text)
        if f_ip:
            df = df[df['ip'].str.contains(f_ip, na=False)]
        
        # --- Excel Export ---
        import io
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Processes')
        
        st.download_button(
            label="📥 엑셀 다운로드",
            data=excel_buffer.getvalue(),
            file_name="process_master.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # --- List ---
    if df.empty:
        st.info("조건에 맞는 데이터가 없습니다.")
    else:
        from views.common_ui import render_grid_with_edit
        
        # Don't rename DF columns, use config labels
        # Columns: id, ip, type, name, dept, factory, hogi, asset_id, deploy_date, asset_type_joined
        
        def update_proc_cb(row_id, row_dict):
            # row_dict: type, name, dept, factory, hogi
            # Check mappings
            # If we renamed columns, row_dict has Korean keys.
            # If we use config labels, row_dict has English keys!
            # Using config labels is cleaner.
            
            updates = [(
                row_dict['type'], row_dict['name'], row_dict['dept'], row_dict['factory'], row_dict['hogi'],
                row_id
            )]
            ProcessService.update_batch_processes(updates)

        # Dynamic Types for Selectbox
        from modules.services import CodeService
        types_df_dyn = CodeService.get_common_codes('ASSET_TYPE')
        dynamic_types = types_df_dyn['code_name'].tolist() if not types_df_dyn.empty else ["PC", "PDA", "MES단말기", "프린터"]

        col_cfg = {
            "ip": st.column_config.TextColumn("IP", disabled=True),
            "type": st.column_config.SelectboxColumn("공정설정종류", options=dynamic_types),
            "name": st.column_config.TextColumn("공정명"),
            "dept": st.column_config.TextColumn("부서"),
            "factory": st.column_config.TextColumn("공장"),
            "hogi": st.column_config.TextColumn("호기"),
            "asset_id": st.column_config.TextColumn("투입장비", disabled=True),
            "deploy_date": st.column_config.TextColumn("투입일자", disabled=True),
            "asset_type_joined": st.column_config.TextColumn("실투입종류", disabled=True),
            "id": st.column_config.TextColumn("ID", disabled=True) # Hidden usually
        }
        
        render_grid_with_edit(
            df,
            key_col="id",
            update_callback=update_proc_cb,
            column_config=col_cfg,
            column_order=["select", "ip", "type", "name", "dept", "factory", "hogi", "asset_id", "deploy_date", "asset_type_joined"],
            can_delete=False, # No delete requested for processes explicitly, safe to skip or add later
            label="공정목록"
        )

    # --- Assignment Action ---
    st.markdown("### 🛠️ 장비 배치 / 해제")
    
    # Select Process
    # Select Process
    # Use ID map to handle duplicate IPs
    df['proc_label'] = df.apply(lambda x: f"{x['factory']} {x['name']} ({x['ip']}) - [{x['type']}]", axis=1)
    proc_map = dict(zip(df['proc_label'], df['id']))
    
    selected_proc_str = st.selectbox("공정 선택", ["선택하세요"] + list(proc_map.keys()))
    
    if selected_proc_str != "선택하세요":
        # Find ID
        proc_id = proc_map[selected_proc_str]
        proc_row = df[df['id'] == proc_id].iloc[0]
        
        current_asset = proc_row['asset_id']
        st.info(f"현재 투입 장비: {current_asset if current_asset else '없음'}")
        
        # Load available assets
        # Get ALL assets of the same type (not just waiting)
        # Filter by type
        all_assets = AssetService.get_all_assets({'type': proc_row['type']})
        
        display_options = []
        if not all_assets.empty:
            # Sort: Waiting first
            all_assets['sort_key'] = all_assets['status'].apply(lambda x: 0 if x == '대기중' else 1)
            all_assets = all_assets.sort_values('sort_key')
            
            # Format label: [ID] Model (Status) - Location
            def fmt(r):
                loc = r['location'] if r['location'] else "위치없음"
                return f"[{r['id']}] {r['model']} ({r['status']}) - {loc}"
            
            all_assets['label'] = all_assets.apply(fmt, axis=1)
            display_options = all_assets['label'].tolist()
            
        
        c_a, c_b = st.columns(2)
        target_asset_str = c_a.selectbox("투입할 장비 선택 (미투입 우선)", ["선택안함 (해제)"] + display_options)
        
        if c_b.button("적용", type="primary"):
            asset_to_assign = None
            if target_asset_str != "선택안함 (해제)":
                # Extract ID: [ID] ...
                asset_to_assign = target_asset_str.split(']')[0].replace('[', '')
            
            ok, msg = ProcessService.assign_asset_to_process(proc_id, asset_to_assign)
            if ok: st.success(msg); st.rerun()
            else: st.error(msg)
            
    # --- New Process ---
    with st.expander("➕ 공정 신규 등록"):
        with st.form("new_proc_form"):
            c1, c2 = st.columns(2)
            n_ip = c1.text_input("IP (Unique)")
            
            # Dynamic Asset Types (using CodeService)
            from modules.services import CodeService
            types_df = CodeService.get_common_codes('ASSET_TYPE')
            type_options = types_df['code_name'].tolist() if not types_df.empty else ["PC", "PDA", "MES단말기", "프린터"]
            
            n_type = c2.selectbox("단말기종류 (공정설정)", type_options)
            n_name = c1.text_input("공정명")
            n_dept = c2.text_input("부서")
            n_fac = c1.text_input("공장")
            n_hogi = c2.text_input("호기")
            
            if st.form_submit_button("등록"):
                if n_ip:
                    ok, msg = ProcessService.create_process({
                        "id": str(uuid.uuid4()), "ip": n_ip, "type": n_type,
                        "name": n_name, "dept": n_dept, "factory": n_fac, "hogi": n_hogi
                    })
                    if ok: st.success(msg); st.rerun()
                    else: st.error(msg)
                else: st.error("IP는 필수입니다.")
