import streamlit as st

MENU_MAP = {
    "status": "📊 투입현황", "inspection": "🔧 현장점검",
    "fail_history": "📉 점검이력", "asset_movement": "📱 장비 이동이력", "asset_master": "🖥️ 장비마스터",
    "process_master": "🏭 공정마스터", "upload": "📥 데이터 업로드", "qr_gen": "🖼️ QR생성",
    "code_master": "🛠️ 기초코드 관리", "activity_logs": "📜 시스템 사용이력", "user_mgmt": "👥 사용자 관리"
}

def render_top_nav():
    user_role = st.session_state.user_info.get('role', 'user')
    
    # 기본 상태 설정
    if "active_category" not in st.session_state:
        st.session_state.active_category = "history"
        
    st.markdown("""
    <style>
    /* 메인 카테고리 메뉴 스타일 */
    div[data-testid="stColumn"]:has(.nav-item) button,
    div[data-testid="stColumn"]:has(.nav-item) button p {
        background: transparent !important;
        border: none !important;
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        padding: 4px 0px !important;
        box-shadow: none !important;
        border-radius: 0px !important;
        transition: opacity 0.2s ease;
    }
    div[data-testid="stColumn"]:has(.nav-item) button:hover p { opacity: 0.8; }
    div[data-testid="stColumn"]:has(.nav-active) button {
        border-bottom: 3px solid #1f77b4 !important; 
    }
    div[data-testid="stColumn"]:has(.nav-active) button p { opacity: 1.0 !important; }
    div[data-testid="stColumn"]:has(.nav-item):not(:has(.nav-active)) button p { opacity: 0.4; }
    
    /* 서브 메뉴 스타일 */
    div[data-testid="stColumn"]:has(.sub-nav-item) button,
    div[data-testid="stColumn"]:has(.sub-nav-item) button p {
        background: transparent !important;
        border-radius: 20px !important;
        font-size: 0.9rem !important;
        padding: 5px 15px !important;
        transition: all 0.2s ease;
    }
    div[data-testid="stColumn"]:has(.sub-nav-active) button {
        background: #1f77b4 !important;
        border: 1px solid #1f77b4 !important;
    }
    div[data-testid="stColumn"]:has(.sub-nav-active) button p {
        color: #ffffff !important;
        font-weight: bold !important;
        opacity: 1.0 !important;
    }

    /* 라이트/다크 모드 명시적 색상 지정 */
    @media (prefers-color-scheme: light) {
        div[data-testid="stColumn"]:has(.nav-item) button p { color: #111111 !important; }
        div[data-testid="stColumn"]:has(.sub-nav-item):not(:has(.sub-nav-active)) button { border: 1px solid #555555 !important; }
        div[data-testid="stColumn"]:has(.sub-nav-item):not(:has(.sub-nav-active)) button p { color: #333333 !important; }
    }
    @media (prefers-color-scheme: dark) {
        div[data-testid="stColumn"]:has(.nav-item) button p { color: #eeeeee !important; }
        div[data-testid="stColumn"]:has(.sub-nav-item):not(:has(.sub-nav-active)) button { border: 1px solid #aaaaaa !important; }
        div[data-testid="stColumn"]:has(.sub-nav-item):not(:has(.sub-nav-active)) button p { color: #dddddd !important; }
    }
    
    /* 화면 해상도에 따른 반응형 처리 (핵심) */
    
    /* 모바일에서 Streamlit 컬럼이 세로로 붕괴되는 것을 막고 토스 앱처럼 가로 스크롤 유지 */
    div[data-testid="stHorizontalBlock"]:has(.nav-item) {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        /* 스크롤바 숨김 */
        -ms-overflow-style: none;
        scrollbar-width: none;
    }
    div[data-testid="stHorizontalBlock"]:has(.nav-item)::-webkit-scrollbar {
        display: none;
    }
    div[data-testid="stHorizontalBlock"]:has(.nav-item) > div[data-testid="stColumn"] {
        width: auto !important;
        flex: 1 1 0% !important; /* 균등 분할 */
        min-width: max-content !important;
    }
    
    /* 서브 메뉴 가로 배치 */
    div[data-testid="stHorizontalBlock"]:has(.sub-nav-item) {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 5px !important;
        -ms-overflow-style: none;
        scrollbar-width: none;
    }
    div[data-testid="stHorizontalBlock"]:has(.sub-nav-item)::-webkit-scrollbar {
        display: none;
    }
    div[data-testid="stHorizontalBlock"]:has(.sub-nav-item) > div[data-testid="stColumn"] {
        width: auto !important;
        flex: 0 0 auto !important; /* 글자 크기만큼만 차지 */
        min-width: max-content !important;
    }

    @media (max-width: 768px) {
        /* 모바일에서는 PC전용(nav-pc-only) 메뉴 숨김 */
        div[data-testid="stColumn"]:has(.nav-pc-only) { display: none !important; }
        
        /* 모바일 메뉴 폰트 크기 조절 */
        div[data-testid="stColumn"]:has(.nav-item) button { font-size: 1.05rem !important; }
        div[data-testid="stColumn"]:has(.sub-nav-item) button { font-size: 0.85rem !important; padding: 4px 10px !important;}
    }
    
    @media (min-width: 769px) {
        /* PC에서는 모바일전용(nav-mobile-only) 메뉴 숨김 */
        div[data-testid="stColumn"]:has(.nav-mobile-only) { display: none !important; }
    }
    </style>
    """, unsafe_allow_html=True)

    # --- 1. 메인 카테고리 ---
    cats = [
        {"id": "qr", "label": "QR생성", "class": "nav-pc-only"},           # PC만
        {"id": "field", "label": "현장업무", "class": "nav-mobile-only"},  # 모바일만
        {"id": "history", "label": "이력조회", "class": ""},               # 공통
        {"id": "data", "label": "데이터 관리", "class": "nav-pc-only"},    # PC만
        {"id": "system", "label": "시스템 관리", "class": "nav-pc-only"}   # PC만
    ]
    
    cols = st.columns(len(cats))
    
    for idx, c in enumerate(cats):
        with cols[idx]:
            active_cls = "nav-active" if st.session_state.active_category == c["id"] else ""
            st.markdown(f"<div class='nav-item {c['class']} {active_cls}'></div>", unsafe_allow_html=True)
            if st.button(c["label"], key=f"top_{c['id']}", use_container_width=True):
                st.session_state.active_category = c["id"]
                # 카테고리 변경 시 기본 진입 페이지 설정
                if c["id"] == "qr": st.session_state.active_page = "qr_gen"
                elif c["id"] == "field": st.session_state.active_page = "inspection"
                elif c["id"] == "history": st.session_state.active_page = "fail_history"
                elif c["id"] == "data": st.session_state.active_page = "asset_master"
                elif c["id"] == "system": st.session_state.active_page = "upload"
                st.rerun()

    # 상단 메뉴와 서브 메뉴 사이 구분선
    st.markdown("<hr style='margin:0; padding:0; border:none; border-bottom:1px solid #444;'/>", unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:15px;'></div>", unsafe_allow_html=True)

    # --- 2. 서브 메뉴 ---
    sub_menus = []
    if st.session_state.active_category == "qr":
        # PC용 단일 메뉴: 서브 메뉴 없음
        pass
    elif st.session_state.active_category == "field":
        sub_menus = [("inspection", "🔧 현장점검"), ("qr_gen", "🖼️ QR생성")]
    elif st.session_state.active_category == "history":
        sub_menus = [("fail_history", "📉 점검이력"), ("asset_movement", "📱 이동이력"), ("activity_logs", "📜 사용이력")]
        if user_role != 'admin':
            sub_menus = [("fail_history", "📉 점검이력"), ("asset_movement", "📱 이동이력")]
    elif st.session_state.active_category == "data":
        sub_menus = [("asset_master", "🖥️ 장비마스터"), ("process_master", "🏭 공정마스터"), ("code_master", "🛠️ 기초코드")]
    elif st.session_state.active_category == "system":
        if user_role == 'admin':
            sub_menus = [("upload", "📥 업로드"), ("user_mgmt", "👥 사용자")]

    if sub_menus:
        # 왼쪽으로 정렬하기 위해 남은 공간은 빈 컬럼으로 채움
        sub_cols = st.columns(len(sub_menus) + max(0, 6 - len(sub_menus)))
        for idx, (page_id, label) in enumerate(sub_menus):
            with sub_cols[idx]:
                active_cls = "sub-nav-active" if st.session_state.active_page == page_id else ""
                st.markdown(f"<div class='sub-nav-item {active_cls}'></div>", unsafe_allow_html=True)
                if st.button(label, key=f"sub_{page_id}", use_container_width=True):
                    st.session_state.active_page = page_id
                    st.rerun()
                    
    st.markdown("<div style='margin-bottom:20px;'></div>", unsafe_allow_html=True)
