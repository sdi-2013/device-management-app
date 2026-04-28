import streamlit as st

MENU_MAP = {
    "dashboard": "🏠 홈", "status": "📊 투입현황", "inspection": "🔧 현장점검",
    "fail_history": "📉 점검이력", "asset_movement": "📱 장비 이동이력 조회", "asset_master": "🖥️ 장비마스터",
    "process_master": "🏭 공정마스터", "upload": "📥 업로드(Admin)", "qr_gen": "🖼️ QR생성",
    "code_master": "🛠️ 기초코드", "activity_logs": "📜 사용이력 관리(Admin)",
    "user_mgmt": "👥 사용자(Admin)"
}

def render_dashboard():
    st.markdown("<h2 style='text-align: center;'>🏠 메인 대시보드</h2>", unsafe_allow_html=True)
    st.write("") # Spacer
    
    user_role = st.session_state.user_info.get('role', 'user')
    
    # Define Categories (Synced with app.py NAV_STRUCTURE)
    # Using a local mapping here since importing from main script might cause circular imports
    
    # Structure: Category -> [(key, label)]
    dashboard_cats = {
        "현장 업무": [("inspection", "🔧 현장점검"), ("qr_gen", "🖼️ QR생성")],
        "이력 조회": [("status", "📊 투입현황"), ("fail_history", "📉 점검이력"), ("asset_movement", "📱 이동이력")],
        "데이터 관리": [("asset_master", "🖥️ 장비마스터"), ("process_master", "🏭 공정마스터"), ("code_master", "🛠️ 기초코드")],
        "시스템 관리": [("upload", "📥 데이터업로드"), ("user_mgmt", "👥 사용자관리"), ("activity_logs", "📜 사용이력")]
    }
    
    # Render Layout
    for cat_name, items in dashboard_cats.items():
        # Check visibility
        if cat_name == "시스템 관리" and user_role != 'admin': continue
            
        st.subheader(cat_name)
        
        # Grid Layout for Buttons
        cols = st.columns(4)
        for i, (key, label) in enumerate(items):
            with cols[i % 4]:
                st.markdown('<div class="dashboard-btn">', unsafe_allow_html=True)
                if st.button(label, key=f"dash_main_{key}", use_container_width=True):
                    st.session_state.active_page = key
                    st.session_state.nav_category = cat_name # Sync Category
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        
        st.divider()
