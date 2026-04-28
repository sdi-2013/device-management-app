import streamlit as st
from modules.services import LogService


def render_movement_tab():
    st.subheader("장비 이동 이력 (Asset Movement)")
    logs = LogService.get_movement_logs()
    if not logs.empty:
            from views.common_ui import render_grid_with_edit
            
            # Columns: id, asset_id, action_type, prev_loc, curr_loc, date, worker...
            # Config Labels
            col_cfg = {
                "date": st.column_config.TextColumn("처리일시"),
                "asset_id": st.column_config.TextColumn("자체관리번호"),
                "action_type": st.column_config.TextColumn("구분"),
                "prev_loc": st.column_config.TextColumn("이전 위치"),
                "curr_loc": st.column_config.TextColumn("현재위치"),
                "worker": st.column_config.TextColumn("작업자"),
                "id": st.column_config.TextColumn("ID", disabled=True)
            }
            
            def update_move_cb(rid, rdict):
                updates = [(rdict.get('action_type'), rdict.get('prev_loc'), rdict.get('curr_loc'), rdict.get('date'), rid)]
                LogService.update_movement_logs(updates)
            
            def delete_move_cb(ids):
                return LogService.delete_movement_logs(ids)

            render_grid_with_edit(
                logs,
                key_col="id",
                update_callback=update_move_cb,
                column_config=col_cfg,
                column_order=["select", "date", "asset_id", "action_type", "prev_loc", "curr_loc"],
                label="이동이력",
                can_delete=True,
                delete_callback=delete_move_cb
            )

    else:
            st.info("이동 이력이 없습니다.")

def render_maintenance_tab():
    st.subheader("점검/수리 이력 (Maintenance Logs)")
    mt_df = LogService.get_maintenance_logs()
    if mt_df.empty:
        st.info("이력이 없습니다.")
    else:
        from views.common_ui import render_grid_with_edit
        
        # Columns: id, asset_id, action_type, content, technician, timestamp, location_snapshot...
        col_cfg = {
                "timestamp": st.column_config.TextColumn("처리일시"),
                "asset_id": st.column_config.TextColumn("자체관리번호"),
                "action_type": st.column_config.TextColumn("구분"),
                "content": st.column_config.TextColumn("내용"),
                "location_snapshot": st.column_config.TextColumn("위치(당시)"),
                "technician": st.column_config.TextColumn("작업자"),
                "id": st.column_config.TextColumn("ID", disabled=True)
        }
        
        def update_mt_cb(rid, rdict):
            updates = [(rdict.get('action_type'), rdict.get('content'), rdict.get('technician'), rdict.get('timestamp'), rid)]
            LogService.update_maintenance_logs(updates)
        
        def delete_mt_cb(ids):
            return LogService.delete_maintenance_logs(ids)
        
        render_grid_with_edit(
            mt_df,
            key_col="id",
            update_callback=update_mt_cb,
            column_config=col_cfg,
            column_order=["select", "timestamp", "asset_id", "action_type", "content", "location_snapshot", "technician"],
            label="점검이력",
            can_delete=True,
            delete_callback=delete_mt_cb
        )

def render_history():
    st.title("📜 이력 조회")
    tab1, tab2 = st.tabs(["🚛 장비 이동 이력", "🛠️ 점검/수리 이력"])
    with tab1: render_movement_tab()
    with tab2: render_maintenance_tab()

def render_fail_history():
    st.title("🛠️ 점검 이력 조회")
    render_maintenance_tab()

def render_asset_movement():
    st.title("🚛 장비 이동 이력 조회")
    render_movement_tab()
