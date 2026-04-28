import streamlit as st
from modules.auth import AuthManager

def render_login_page():
    st.markdown("<h2 style='text-align: center; white-space: nowrap;'>⚙️ 장비관리 시스템</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            uid = st.text_input("아이디")
            upw = st.text_input("비밀번호", type="password")
            
            if st.form_submit_button("로그인", type="primary"):
                user = AuthManager.login(uid, upw)
                if user:
                    token = AuthManager.create_session(user['id'])
                    st.session_state.logged_in = True
                    st.session_state.user_info = user
                    st.session_state.active_page = "fail_history"
                    st.session_state.active_category = "history"
                    try: st.query_params["token"] = token
                    except: pass
                    st.rerun()
                else:
                    st.error("로그인 실패: 아이디 또는 비밀번호를 확인하세요.")
