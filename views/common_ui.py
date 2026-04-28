import streamlit as st
import pandas as pd

def render_grid_with_edit(
    df: pd.DataFrame, 
    key_col: str, 
    update_callback, 
    column_config: dict = {}, 
    column_order: list = None,
    can_delete: bool = False,
    delete_callback = None,
    label: str = "데이터",
    hide_id: bool = True,
    show_index: bool = False  # Default changed to False to prevent sorting confusion
):
    """
    Reusable component for "Select -> Edit -> Distinction -> Save" pattern.
    """
    
    if df.empty:
        st.info("데이터가 없습니다.")
        return
        
    total_count = len(df)
    if total_count > 100:
        st.caption(f"⚡ 성능 최적화(빠른 전체 선택)를 위해 최근 100건만 표시됩니다. (전체 {total_count}건)")
        df = df.head(100)

    # Session State keys for this grid
    grid_key = f"grid_{label}"
    edit_mode_key = f"edit_mode_{label}"
    selected_ids_key = f"selected_{label}"
    select_all_key = f"select_all_flag_{label}"
    
    if edit_mode_key not in st.session_state: st.session_state[edit_mode_key] = False
    
    # --- Edit Mode UI ---
    if st.session_state[edit_mode_key]:
        st.markdown(f"### 📝 {label} 수정 모드")
        st.info("선택한 항목만 수정합니다. 수정을 완료하면 '변경된 내용 저장'을 누르세요.")
        
        # Filter DF to selected IDs
        target_ids = st.session_state.get(selected_ids_key, [])
        if not target_ids:
            st.error("선택된 항목이 없습니다.")
            st.session_state[edit_mode_key] = False
            st.rerun()
            return
            
        edit_df = df[df[key_col].isin(target_ids)].copy()
        
        # Use data editor for editing
        # Ensure 'select' col is removed for edit view
        if 'select' in edit_df.columns: edit_df = edit_df.drop(columns=['select'])
        
        # Config for edit: Disable key_col
        edit_config = column_config.copy()
        edit_config[key_col] = st.column_config.TextColumn(disabled=True)
        
        edited_data = st.data_editor(
            edit_df,
            column_config=edit_config,
            column_order=[c for c in column_order if c != 'select'] if column_order else None,
            use_container_width=True,
            key=f"editor_{label}",
            hide_index=True # Always hide index in edit mode for cleaner look
        )
        
        c1, c2 = st.columns([1, 1])
        if c1.button("💾 변경된 내용 저장", type="primary", key=f"save_{label}"):
            count = 0
            for index, row in edited_data.iterrows():
                row_id = row[key_col]
                row_dict = row.to_dict()
                update_callback(row_id, row_dict)
                count += 1
            
            st.success(f"{count}행 저장 완료!")
            st.session_state[edit_mode_key] = False
            st.rerun()
            
        if c2.button("❌ 취소 (목록으로)", key=f"cancel_{label}"):
            st.session_state[edit_mode_key] = False
            st.rerun()
            
        st.markdown("---")

    # --- Read/Select Mode UI ---
    else:
        # Add checkbox for selection if not exists
        view_df = df.copy()
        
        # Manual Index Handling removed to avoid sorting issues. 
        # We will hide index by default.
            
        # Select All Logic
        if select_all_key in st.session_state:
            val = st.session_state[select_all_key]
            view_df['select'] = val
        elif 'select' not in view_df.columns:
             view_df.insert(0, "select", False)
        
        # Main Grid
        final_col_order = column_order.copy() if column_order else list(view_df.columns)
        if hide_id and key_col in final_col_order:
            final_col_order.remove(key_col)
            
        if 'select' in final_col_order:
            final_col_order.remove('select')
            final_col_order.insert(0, 'select')
            
        editor_state = st.session_state.get(f"grid_read_{label}")
        has_sel_pre = False
        
        if view_df['select'].any(): has_sel_pre = True
        
        if editor_state and "edited_rows" in editor_state:
            for v in editor_state["edited_rows"].values():
                if v.get('select'): has_sel_pre = True
        
        st.markdown("<div style='margin-bottom: 5px;'></div>", unsafe_allow_html=True)
        st.markdown("<div class='grid-action-buttons'></div>", unsafe_allow_html=True)
        ac1, ac2, ac3, ac4, spacer = st.columns([1.2, 1.2, 1.2, 1.2, 5], gap="small")
        
        with ac1:
            if st.button("✅ 전체", key=f"sel_all_{label}", use_container_width=True):
                st.session_state[select_all_key] = True
                if f"grid_read_{label}" in st.session_state: del st.session_state[f"grid_read_{label}"]
                st.rerun()
        with ac2:
            if st.button("⬜ 해제", key=f"desel_all_{label}", use_container_width=True):
                st.session_state[select_all_key] = False
                if f"grid_read_{label}" in st.session_state: del st.session_state[f"grid_read_{label}"]
                st.rerun()
        
        with ac3:
            if st.button("🛠️ 수정", key=f"btn_edit_{label}", disabled=not has_sel_pre, use_container_width=True):
                st.session_state[f"trigger_edit_{label}"] = True
                
        with ac4:
             if can_delete:
                 if st.button("🗑️ 삭제", key=f"btn_del_{label}", disabled=not has_sel_pre, use_container_width=True):
                     st.session_state[f"trigger_del_{label}"] = True
        
        final_column_config = column_config.copy()
        for col_name in view_df.columns:
            if col_name == "select": continue
            if col_name not in final_column_config:
                 final_column_config[col_name] = st.column_config.TextColumn(width="medium")

        # Show Row Count
        col_cnt, col_tog = st.columns([1, 1])
        col_cnt.caption(f"총 {len(view_df)}건")
        use_mobile_view = col_tog.toggle("📱 모바일 뷰 (카드형)", value=st.session_state.get(f"mview_{label}", False), key=f"mview_{label}")

        if use_mobile_view:
            st.markdown("<div style='font-size:0.85em; color:gray; margin-bottom:10px;'>💡 카드를 체크하여 상단의 [변경/삭제] 버튼을 사용할 수 있습니다.</div>", unsafe_allow_html=True)
            selected_in_mobile = []
            
            for idx, row in view_df.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([1, 9])
                    is_sel = bool(row.get('select', False))
                    if c1.checkbox("", value=is_sel, key=f"mchk_{label}_{idx}"):
                        selected_in_mobile.append(idx)
                    
                    key_val = row.get(key_col, '')
                    main_cols = [c for c in final_col_order if c not in ['select', key_col]]
                    
                    info_html = f"<div style='font-size:1.05em; font-weight:bold; margin-bottom:4px; color:#1f77b4;'>{key_val}</div>"
                    info_html += "<div style='font-size:0.9em; line-height:1.5;'>"
                    for col in main_cols:
                        val = row.get(col, '')
                        if pd.isna(val) or val == '': val = '-'
                        info_html += f"<b>{col}</b>: {val}<br>"
                    info_html += "</div>"
                    c2.markdown(info_html, unsafe_allow_html=True)

            view_df['select'] = False
            if selected_in_mobile:
                view_df.loc[selected_in_mobile, 'select'] = True
            grid_result = view_df.copy()
        else:
            grid_result = st.data_editor(
                view_df,
                column_config=final_column_config,
                column_order=final_col_order,
                use_container_width=True, 
                hide_index=not show_index,
                key=f"grid_read_{label}"
            )
        
        # Determine selection
        if 'select' in grid_result.columns:
            selected_rows = grid_result[grid_result['select']]
        else:
            selected_rows = pd.DataFrame()
            
        # Handle Deferred Actions from Top Toolbar
        if st.session_state.get(f"trigger_edit_{label}"):
            del st.session_state[f"trigger_edit_{label}"]
            if not selected_rows.empty:
                st.session_state[selected_ids_key] = selected_rows[key_col].tolist()
                st.session_state[edit_mode_key] = True
                st.rerun()
            else:
                st.warning("선택된 항목이 없습니다.")
                
        if st.session_state.get(f"trigger_del_{label}"):
            del st.session_state[f"trigger_del_{label}"]
            if not selected_rows.empty:
                ids = selected_rows[key_col].tolist()
                ok, msg = delete_callback(ids)
                if ok: st.success(msg); st.rerun()
                else: st.error(msg)
            else:
                st.warning("선택된 항목이 없습니다.")
            
