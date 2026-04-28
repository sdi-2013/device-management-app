import streamlit as st
import os
import logging
from modules.database import init_db
from modules.auth import AuthManager
from views.login import render_login_page

# --- Configuration ---
def configure_streamlit():
    st.set_page_config(page_title="장비관리 시스템", layout="wide", page_icon="⚙️")
    
    # CSS
    st.markdown("""<style>
        /* .stApp { font-family: 'Pretendard', sans-serif; } */
        
        /* Hide Streamlit Native Header (우측 상단 ... 메뉴 폰트 깨짐 방지) */
        header[data-testid="stHeader"] { display: none !important; }
        
        /* Hide Expander Icons to prevent text overlap in intranet (offline font load failure) */
        details[data-testid="stExpander"] summary svg,
        details[data-testid="stExpander"] summary .st-icon,
        details[data-testid="stExpander"] summary [data-testid="stIconMaterial"] { display: none !important; }
        
        /* Disable ALL animations and transitions for instant screen switching */
        *, *::before, *::after {
            animation: none !important;
            transition: none !important;
        }
        
        /* Top Navigation Button Styling */
        .top-nav-btn {
            width: 100%;
            margin-bottom: 5px !important;
        }
        
        /* Mobile responsive typography for main content */
        @media (max-width: 768px) {
            /* Titles (st.title) */
            h1 {
                font-size: 1.8rem !important;
                line-height: 1.2 !important;
            }
            
            /* Headers (st.header) */
            h2 {
                font-size: 1.5rem !important;
                line-height: 1.3 !important;
            }
            
            /* Subheaders (st.subheader) */
            h3 {
                font-size: 1.2rem !important;
                line-height: 1.3 !important;
            }
            
            /* Smaller headers */
            h4 {
                font-size: 1rem !important;
            }
            
            h5 {
                font-size: 0.9rem !important;
            }
        }
        
        .dashboard-btn button { height: 120px; font-size: 20px !important; font-weight: bold; width: 100%; border-radius: 12px; }
        .edit-mode-box { border: 2px solid #238636; border-radius: 10px; padding: 20px; margin-top: 20px; margin-bottom: 20px; }
        
        /* DataGrid Font Size Adjustment - Aggressive */
        [data-testid="stDataFrame"] *, [data-testid="stDataEditor"] * {
            font-size: 18px !important;
            line-height: 1.5 !important;
        }
    </style>""", unsafe_allow_html=True)

# --- Init ---
if __name__ == "__main__":
    init_db()
    configure_streamlit()

    # Session State Init
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if 'user_info' not in st.session_state: st.session_state.user_info = {}
    if 'active_page' not in st.session_state: st.session_state.active_page = "login"

    # Token Check
    if not st.session_state.logged_in:
        try: token = st.query_params.get("token", None)
        except: token = None
        
        user = AuthManager.validate_session(token)
        if user:
            st.session_state.logged_in = True
            st.session_state.user_info = user
            st.session_state.active_page = "fail_history"
            st.session_state.active_category = "history"

    # Routing
    if not st.session_state.logged_in:
        render_login_page()
    else:
        # Header / Logout (상단 구석에 작게 배치)
        hc1, hc2 = st.columns([8, 2])
        hc1.markdown(f"<div style='font-size:0.9em; color:gray; padding-top:10px; text-align:right;'>🧑‍💼 <b>{st.session_state.user_info.get('name', '사용자')}</b>님 접속중</div>", unsafe_allow_html=True)
        if hc2.button("로그아웃", key="btn_logout_top", use_container_width=True):
            AuthManager.logout()
            st.rerun()
            
        from views.sidebar import render_navigation
        render_navigation()
        
        page = st.session_state.active_page
        
        if page == "asset_master":
            from views.assets import render_asset_master
            render_asset_master()
        elif page == "process_master":
            from views.processes import render_process_master
            render_process_master()
        elif page == "inspection":
            from views.inspection import render_inspection
            render_inspection()
        elif page == "status":
            from views.status import render_status
            render_status()
        elif page == "fail_history":
            from views.history import render_fail_history
            render_fail_history()
        elif page == "asset_movement":
            from views.history import render_asset_movement
            render_asset_movement()
        elif page == "user_mgmt":
            from views.admin import render_user_mgmt
            render_user_mgmt()
        elif page == "code_master":
            from views.admin import render_code_master
            render_code_master()
        elif page == "qr_gen":
            from views.qr_gen import render_qr_gen
            render_qr_gen()
        elif page == "upload":
            from views.upload import render_upload
            render_upload()
        elif page == "activity_logs":
            from views.logs import render_activity_logs
            render_activity_logs()
        else:
            st.info(f"Page '{page}' is under construction.")
