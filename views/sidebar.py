import streamlit as st

# Flat menu structure for PC
PC_MENUS = [
    {"id": "inspection", "icon": "🔧", "label": "현장점검"},
    {"id": "fail_history", "icon": "📉", "label": "점검이력"},
    {"id": "asset_movement", "icon": "📱", "label": "단말기 이동이력"},
    {"id": "activity_logs", "icon": "📜", "label": "시스템 사용이력"},
    {"id": "asset_master", "icon": "🖥️", "label": "장비 마스터"},
    {"id": "process_master", "icon": "🏭", "label": "공정 마스터"},
    {"id": "code_master", "icon": "🛠️", "label": "기초코드 관리"},
    {"id": "upload", "icon": "📥", "label": "데이터 업로드"},
    {"id": "user_mgmt", "icon": "👥", "label": "사용자 관리"},
    {"id": "qr_gen", "icon": "🖼️", "label": "QR 코드 생성"}
]

# Bottom Navigation for Mobile
MOBILE_MENUS = [
    {"id": "inspection", "icon": "🔧", "label": "현장점검"},
    {"id": "fail_history", "icon": "📋", "label": "점검이력"},
    {"id": "asset_movement", "icon": "📱", "label": "단말기이동"},
    {"id": "activity_logs", "icon": "📜", "label": "사용이력"}
]

def render_navigation():
    user_role = st.session_state.user_info.get('role', 'user')
    
    # 기본 상태 설정
    if "active_page" not in st.session_state:
        st.session_state.active_page = "fail_history"

    st.markdown("""
    <style>
    /* 공통: 상단 여백 및 기본 헤더 제거 */
    .block-container {
        padding-top: 1.5rem !important;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }

    /* 1. PC 환경 (769px 이상) */
    @media (min-width: 769px) {
        /* 하단 네비게이션 컨테이너 숨김 */
        div[data-testid="stHorizontalBlock"]:has(.bottom-nav-marker) {
            display: none !important;
        }
    }
    
    /* 2. 모바일 환경 (768px 이하) */
    @media (max-width: 768px) {
        /* 좌측 햄버거 메뉴 및 사이드바 완전 숨김 */
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stSidebar"] { display: none !important; }
        
        /* 모바일 컨텐츠 하단 여백 확보 (네비바에 가리지 않게) */
        .block-container { padding-bottom: 90px !important; }

        /* 하단 네비게이션 컨테이너 고정 (Bottom Nav Bar) */
        div[data-testid="stHorizontalBlock"]:has(.bottom-nav-marker) {
            position: fixed;
            bottom: 0; left: 0; width: 100%;
            background-color: #ffffff;
            border-top: 1px solid #e0e0e0;
            margin: 0 !important;
            padding: 5px 0px;
            padding-bottom: env(safe-area-inset-bottom, 5px); /* 아이폰 하단 홈바 대응 */
            z-index: 999999;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
            gap: 0 !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
        }
        
        @media (prefers-color-scheme: dark) {
            div[data-testid="stHorizontalBlock"]:has(.bottom-nav-marker) {
                background-color: #161b22;
                border-top: 1px solid #333333;
            }
        }

        /* 하단 네비게이션 컬럼 레이아웃 */
        div[data-testid="stHorizontalBlock"]:has(.bottom-nav-marker) > div[data-testid="stColumn"] {
            position: relative;
            margin: 0 !important;
            padding: 5px 0 !important;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex: 1 1 0% !important;
            width: 25% !important;
            min-width: 0 !important;
        }
        
        /* 투명 버튼 오버레이 트릭 (실제 클릭을 받는 투명 버튼) */
        div[data-testid="stHorizontalBlock"]:has(.bottom-nav-marker) div.stButton {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            opacity: 0.0001; /* 완전 투명 */
            z-index: 99;
            cursor: pointer;
        }
        div[data-testid="stHorizontalBlock"]:has(.bottom-nav-marker) div.stButton button {
            height: 100% !important;
            width: 100% !important;
        }
        
        /* 커스텀 버튼 아이콘 및 텍스트 스타일 */
        .bottom-nav-label { font-size: 0.7rem; color: #777777; margin-top: 4px; font-weight: 500; }
        .bottom-nav-icon { font-size: 1.5rem; line-height: 1; }
        .nav-active .bottom-nav-label { color: #1f77b4 !important; font-weight: 700; }
        .nav-active .bottom-nav-icon { filter: sepia(1) saturate(100) hue-rotate(180deg); /* 아이콘 색상 변경 트릭 */ }
    }
    
    /* PC 사이드바 버튼 커스텀 (버튼을 왼쪽 정렬하고 플랫하게) */
    [data-testid="stSidebar"] button[kind="secondary"] {
        border: none !important;
        background-color: transparent !important;
        text-align: left !important;
        justify-content: flex-start !important;
        padding-left: 15px !important;
    }
    [data-testid="stSidebar"] button[kind="primary"] {
        text-align: left !important;
        justify-content: flex-start !important;
        padding-left: 15px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # --- 1. PC 환경 사이드바 렌더링 ---
    with st.sidebar:
        st.markdown("<h2 style='text-align:center; padding-bottom: 20px; font-size:1.6rem;'>⚙️ 장비관리 시스템</h2>", unsafe_allow_html=True)
        
        # 관리자가 아니면 일부 메뉴 제외
        pc_menu_list = PC_MENUS
        if user_role != 'admin':
            pc_menu_list = [m for m in PC_MENUS if m['id'] in ['inspection', 'fail_history', 'asset_movement', 'qr_gen']]
            
        for menu in pc_menu_list:
            btn_type = "primary" if st.session_state.active_page == menu["id"] else "secondary"
            if st.button(f"{menu['icon']}  {menu['label']}", key=f"pc_nav_{menu['id']}", use_container_width=True, type=btn_type):
                st.session_state.active_page = menu["id"]
                st.rerun()
                
        # 로그아웃 버튼 (사이드바 여백 추가)
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:10px 0;'/>", unsafe_allow_html=True)
        st.write(f"🧑‍💼 **{st.session_state.user_info.get('name', '사용자')}**님")
        if st.button("🚪 로그아웃", key="pc_logout", use_container_width=True):
            from modules.auth import AuthManager
            AuthManager.logout()
            st.rerun()

    # --- 2. 모바일 환경 하단 바 렌더링 ---
    # 모바일은 이 부분만 보이게 됩니다.
    cols = st.columns(len(MOBILE_MENUS))
    with cols[0]:
        st.markdown("<div class='bottom-nav-marker'></div>", unsafe_allow_html=True)
        
    for idx, menu in enumerate(MOBILE_MENUS):
        with cols[idx]:
            is_active = st.session_state.active_page == menu["id"]
            active_class = "nav-active" if is_active else ""
            
            # 실제 보이는 커스텀 아이콘+텍스트 마크업
            st.markdown(f"""
            <div style="display:flex; flex-direction:column; align-items:center; text-align:center;" class="{active_class}">
                <span class="bottom-nav-icon">{menu['icon']}</span>
                <span class="bottom-nav-label">{menu['label']}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # 보이지 않는 클릭용 투명 버튼 (위에 오버레이 됨)
            if st.button("hidden_btn", key=f"mobile_nav_{menu['id']}", use_container_width=True):
                st.session_state.active_page = menu["id"]
                st.rerun()

# 하위 호환성을 위한 껍데기 함수 (app.py 수정 최소화를 위함)
def render_top_nav():
    render_navigation()
