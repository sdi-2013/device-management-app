import streamlit as st
import pandas as pd
from modules.services import AssetService
from modules.utils import normalize_id

def render_asset_master():
    st.title("🖥️ 장비 마스터 조회")
    
    # --- Search ---
    with st.expander("🔍 상세 검색 필터", expanded=True):
        if st.button("🔄 검색 조건 초기화", key="reset_search_asset"):
            keys_to_clear = ["f_asset_id", "f_asset_types", "f_asset_makers", "f_asset_statuses"]
            for k in keys_to_clear:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
            
        # Prepare Options from Loaded Data (Cascade)
        all_assets = AssetService.get_all_assets()
        
        # Layout: 4 Columns
        # Order: ID, Type, Maker, Status
        c1, c2, c3, c4 = st.columns(4)
        
        # 1. ID (Independent)
        f_id = c1.text_input("자체관리번호 검색", key="f_asset_id")
        
        # 2. Type (Priority 1)
        type_opts = sorted([x for x in all_assets['type'].unique() if pd.notna(x) and x])
        f_types = c2.multiselect("단말기종류", type_opts, placeholder="전체", key="f_asset_types")
        
        # Filter Step 1
        step1_df = all_assets.copy()
        if f_types:
            step1_df = step1_df[step1_df['type'].isin(f_types)]
            
        # 3. Maker (Priority 2)
        maker_opts = sorted([x for x in step1_df['maker'].unique() if pd.notna(x) and x])
        
        if "f_asset_makers" in st.session_state:
            st.session_state["f_asset_makers"] = [x for x in st.session_state["f_asset_makers"] if x in maker_opts]
            
        f_makers = c3.multiselect("제조사", maker_opts, placeholder="전체", key="f_asset_makers")
        
        # Filter Step 2
        step2_df = step1_df.copy()
        if f_makers:
            step2_df = step2_df[step2_df['maker'].isin(f_makers)]
        
        # 4. Status (Priority 3)
        status_opts = sorted([x for x in step2_df['status'].unique() if pd.notna(x) and x])
        
        if "f_asset_statuses" in st.session_state:
            st.session_state["f_asset_statuses"] = [x for x in st.session_state["f_asset_statuses"] if x in status_opts]
            
        f_status = c4.multiselect("장비상태", status_opts, placeholder="전체", key="f_asset_statuses")
        
        # Final Filter
        display_df = step2_df.copy()
        if f_status:
            display_df = display_df[display_df['status'].isin(f_status)]
            
        # Apply ID Filter
        if f_id:
            display_df = display_df[display_df['id'].str.contains(f_id, na=False)]

    # --- Excel Export ---
    import io
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        display_df.to_excel(writer, index=False, sheet_name='Assets')
    
    st.download_button(
        label="📥 엑셀 다운로드",
        data=excel_buffer.getvalue(),
        file_name="asset_master.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --- Grid (Common UI) ---
    from views.common_ui import render_grid_with_edit
    
    # Callback Handlers
    def update_asset_cb(row_id, row_dict):
        # row_dict contains new values
        # Filter only valid fields
        valid_fields = ["type", "maker", "model", "os", "status"]
        update_data = {k: v for k, v in row_dict.items() if k in valid_fields}
        AssetService.update_asset(row_id, update_data)
        
    def delete_asset_cb(ids):
        return AssetService.delete_assets(ids)
    
    column_config = {
        "id": st.column_config.TextColumn("자체관리번호", disabled=True),
        "type": st.column_config.TextColumn("단말기종류", disabled=True), # Type usually fixed, or allow edit? User might want to edit.
        "maker": st.column_config.TextColumn("제조사"),
        "model": st.column_config.TextColumn("모델명"),
        "os": st.column_config.TextColumn("OS"),
        "status": st.column_config.SelectboxColumn("장비상태", options=["투입중", "대기중", "수리중", "폐기예정"]),
        "location": st.column_config.TextColumn("현재위치", disabled=True),
        "deploy_date": st.column_config.TextColumn("투입일자", disabled=True)
    }
    
    # Enable Type edit in "Edit Mode" -> common_ui respects passed config.
    # If we want read-only in main list but editable in Edit Mode, we should separate configs or handle it in common_ui.
    # current common_ui uses the passed config for both, but disables key_col in edit mode.
    # To strictly follow "Read Only List, Editable Edit Mode", common_ui should perhaps force disabled=True in Read Mode.
    # But for now, let's allow Type edit.
    
    render_grid_with_edit(
        display_df,
        key_col="id",
        update_callback=update_asset_cb,
        column_config=column_config,
        column_order=["select", "id", "type", "maker", "model", "status", "os", "location", "deploy_date"],
        can_delete=True,
        delete_callback=delete_asset_cb,
        label="장비목록",
        hide_id=False
    )

    # --- Registration ---
    with st.expander("➕ 장비 신규 등록"):
        with st.form("new_asset_form"):
            c_a, c_b = st.columns(2)
            n_id = c_a.text_input("자체관리번호 (ID)")
            
            # Dynamic Dropdowns
            from modules.services import CodeService
            
            # 1. Asset Type
            types_df = CodeService.get_common_codes('ASSET_TYPE')
            
            if types_df.empty:
                st.error("등록된 단말기 종류가 없습니다. 기초코드 관리에서 먼저 등록하세요.")
                st.stop()
                
            # Create a Dict for mapping Name -> ID
            # Assuming code_name is unique enough for display.
            type_map = {row['code_name']: row['code_id'] for row in types_df.to_dict('records')}
            
            # Selectbox returns Name
            n_type_name = c_b.selectbox("단말기종류", list(type_map.keys()), key="new_asset_type_sel")
            n_type_id = type_map[n_type_name]
            
            # 2. Dependencies (Ref ID = n_type_id)
            # Maker
            makers_df = CodeService.get_common_codes('MAKER', ref_id=n_type_id)
            maker_opts = makers_df['code_name'].tolist()
            
            maker_id = None
            if maker_opts:
                 n_maker = c_a.selectbox("제조사", maker_opts)
                 # Find ID for Model Dependency
                 # Explicit lookup
                 m_row = makers_df[makers_df['code_name'] == n_maker].iloc[0]
                 maker_id = m_row['code_id']
            else:
                 n_maker = c_a.text_input("제조사 (등록된 제조사가 없음, 직접 입력)", placeholder="직접 입력")
            
            # Model - Depends on Maker
            n_model = ""
            if maker_id:
                models_df = CodeService.get_common_codes('MODEL', ref_id=maker_id)
                model_opts = models_df['code_name'].tolist()
                
                if model_opts:
                    n_model = c_b.selectbox("모델명", ["직접 입력"] + model_opts)
                    if n_model == "직접 입력":
                        n_model = c_b.text_input("모델명 입력", key="direct_model_input")
                else:
                     n_model = c_b.text_input("모델명")
            else: 
                 n_model = c_b.text_input("모델명")
            
            # OS
            os_df = CodeService.get_common_codes('OS', ref_id=n_type_id)
            os_opts = os_df['code_name'].tolist()
            
            if os_opts:
                n_os = c_a.selectbox("OS", os_opts)
            else:
                n_os = c_a.text_input("OS (등록된 OS가 없음, 직접 입력)", value="Windows 10")
            
            # Status (Global or Specific?)
            # User said "Maker, OS, Status... depends on Asset Type".
            # Let's try fetching status by ref_id. If empty, fallback to default.
            status_df = CodeService.get_common_codes('ASSET_STATUS', ref_id=n_type_id)
            if not status_df.empty:
                 status_opts = status_df['code_name'].tolist()
            else:
                 status_opts = ["대기중", "투입중", "수리중", "폐기예정"]
            
            # We don't have a status field in creation form usually (defaults to '대기중' or similar), 
            # but if we wanted to set initial status.
            # Creation usually expects 'status' to be controlled by logic (e.g. "대기중" initially).
            # The current creation code doesn't ask for status, it defaults probably?
            # Looking at `services.py` `create_asset`, it likely insert defaults.
            # But the form didn't provide status input. I won't add it unless necessary.
            
            if st.form_submit_button("등록", type="primary"):
                if n_id and n_type_name:
                     final_maker = n_maker
                     
                     ok, msg = AssetService.create_asset({
                        "id": n_id, "type": n_type_name, "maker": final_maker, 
                        "model": n_model, "os": n_os
                     })
                     if ok: st.success(msg); st.rerun()
                     else: st.error(msg)
                else:
                    st.error("자체관리번호와 종류는 필수입니다.")
