import streamlit as st
import pandas as pd
import json
import os
import qrcode
import cv2
import numpy as np
import uuid
import base64
import secrets
import logging
from datetime import datetime, timedelta, date
from io import BytesIO
import streamlit.components.v1 as components

# --- 0. 설정 및 로깅 초기화 ---
def configure_streamlit_server():
    config_dir = ".streamlit"
    config_file = os.path.join(config_dir, "config.toml")
    if not os.path.exists(config_dir): os.makedirs(config_dir)
    config_content = """
[server]
enableCORS = false
enableXsrfProtection = false
headless = true
[browser]
gatherUsageStats = false
[server]
websocketCompression = false
"""
    try:
        with open(config_file, "w") as f: f.write(config_content)
    except: pass

configure_streamlit_server()
st.set_page_config(page_title="장비관리 시스템", layout="wide", page_icon="⚙️")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- 2. 데이터 파일 경로 ---
ASSETS_FILE = 'assets.json'
PROCESS_FILE = 'processes.json'
LOGS_FILE = 'maintenance_logs.json'
MOVEMENT_FILE = 'movement_logs.json'
FAILURE_CODE_FILE = 'failure_codes.json'
USERS_FILE = 'users.json'
SESSION_FILE = 'user_sessions.json'
ACTIVITY_LOG_FILE = 'user_activity_logs.json'

# --- 3. 데이터 헬퍼 함수 ---
def load_data(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return []
    return []

def save_data(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def init_users():
    if not os.path.exists(USERS_FILE):
        # Use environment variable for initial admin password or a secure default placeholder
        # WARN: This file seems properly migrated to database.py in the main app. This might be legacy code.
        default_pw = os.environ.get("ADMIN_INIT_PW", "admin1234") 
        initial_users = [{"id": "admin", "password": default_pw, "name": "마스터", "role": "admin", "must_change_pw": True}]
        save_data(initial_users, USERS_FILE)
init_users()

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output) as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def normalize_id(val):
    if val is None: return ""
    s = str(val).strip()
    if s.lower() == 'nan': return ""
    if s.endswith('.0'): return str(int(float(s)))
    return s.upper()

def log_activity(menu_name, action_detail):
    if 'user_info' in st.session_state:
        user_name = st.session_state.user_info.get('name', 'Unknown')
        logs = load_data(ACTIVITY_LOG_FILE)
        logs.append({
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_name": user_name,
            "menu": menu_name,
            "action": action_detail
        })
        save_data(logs, ACTIVITY_LOG_FILE)

# --- 도메인 키 정의 ---
DOMAIN_KEYS = {
    ASSETS_FILE: "자체관리번호",
    PROCESS_FILE: "id", 
    LOGS_FILE: "id",
    MOVEMENT_FILE: "id",
    FAILURE_CODE_FILE: "id",
    USERS_FILE: "id",
    ACTIVITY_LOG_FILE: "id"
}

# [Helper] IP로 전체 위치명 생성
def get_full_location_name(ip, procs_data):
    if not ip: return ""
    if "(" in ip and ")" in ip: return ip 
    for p in procs_data:
        if p.get('IP') == ip:
            return f"{p.get('공장','')} {p.get('공정','')} {p.get('호기','')} ({ip})"
    return f"({ip})"

# [검증] 데이터 검증 함수
def validate_asset_data(df: pd.DataFrame) -> tuple[bool, str]:
    required_cols = ['자체관리번호', '단말기종류']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return False, f"필수 컬럼 누락: {', '.join(missing)}"
    if df['자체관리번호'].duplicated().any():
        return False, "중복된 자체관리번호가 엑셀 파일 내에 존재합니다."
    if df['자체관리번호'].isna().any() or df['단말기종류'].isna().any():
        return False, "자체관리번호와 단말기종류는 빈 값일 수 없습니다."
    return True, "검증 통과"

# [검증] 점검 입력 검증 함수
def validate_inspection_input(is_new_deploy, new_loc_str, m, s, memo):
    errors = []
    if is_new_deploy and (not new_loc_str or new_loc_str.startswith("위치 정보 없음")):
        errors.append("🚫 신규 투입(대기중) 장비는 반드시 '위치/공정'을 선택해야 합니다.")
    if m == "선택하세요" or s == "선택하세요":
        errors.append("⚠️ 고장 대분류와 상세 유형을 모두 선택해야 합니다.")
    if len(memo.strip()) < 2:
        errors.append("⚠️ 점검 및 조치 내용은 최소 2글자 이상 입력해주세요.")
    return errors

# [핵심] 데이터 정합성 동기화
def sync_data_integrity():
    assets = load_data(ASSETS_FILE)
    procs = load_data(PROCESS_FILE)
    if not assets and not procs: return

    asset_map = {normalize_id(a.get('자체관리번호')): a for a in assets}
    deployed_ids = set()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    p_change = False
    a_change = False

    for p in procs:
        if 'id' not in p: p['id'] = str(uuid.uuid4()); p_change = True
        if '단말기종류' not in p: p['단말기종류'] = ""; p_change = True
        
        aid = normalize_id(p.get('투입장비'))
        ip = p.get('IP', '')
        
        if aid and aid in asset_map:
            deployed_ids.add(aid)
            if not p.get('투입일자') or str(p.get('투입일자')).lower() == 'nan':
                p['투입일자'] = today_str; p_change = True
            
            asset = asset_map[aid]
            full_loc_name = f"{p.get('공장','')} {p.get('공정','')} {p.get('호기','')} ({ip})"
            
            if asset.get('장비상태') != '투입중' or asset.get('현재위치') != full_loc_name:
                asset['장비상태'] = '투입중'
                asset['현재위치'] = full_loc_name
                asset['투입일자'] = p['투입일자']
                a_change = True
            
            if not p.get('단말기종류') and asset.get('단말기종류'):
                p['단말기종류'] = asset['단말기종류']; p_change = True

    for a in assets:
        aid = normalize_id(a.get('자체관리번호'))
        if aid not in deployed_ids:
            if a.get('장비상태') == '투입중': 
                a['장비상태'] = '대기중'; a['현재위치'] = ""; a['투입일자'] = ""; a_change = True
            elif a.get('장비상태') in ['대기중', '수리중', '폐기예정'] and a.get('현재위치'):
                a['현재위치'] = ""; a_change = True
        
        if a.get('장비상태') not in ['투입중', '대기중', '수리중', '폐기예정']:
            a['장비상태'] = '대기중'; a_change = True

    if p_change: save_data(procs, PROCESS_FILE)
    if a_change: save_data(assets, ASSETS_FILE)

try: sync_data_integrity()
except json.JSONDecodeError as e: logging.error(f"JSON Parsing Error: {e}")
except Exception as e: logging.error(f"Data Sync Error: {e}", exc_info=True)

# --- 로그인 세션 ---
def create_session(user_id, user_name, user_role):
    token = secrets.token_urlsafe(32)
    sessions = load_data(SESSION_FILE)
    sessions = [s for s in sessions if s.get('user_id') != user_id]
    sessions.append({"token": token, "user_id": user_id, "user_name": user_name, "user_role": user_role, "created_at": datetime.now().isoformat()})
    save_data(sessions, SESSION_FILE)
    return token

def validate_session():
    try: token = st.query_params.get("token", None)
    except: token = None
    if token:
        sessions = load_data(SESSION_FILE)
        session = next((s for s in sessions if s.get('token') == token), None)
        if session:
            st.session_state.logged_in = True
            st.session_state.user_info = {"id": session['user_id'], "name": session['user_name'], "role": session['user_role'], "must_change_pw": False}
            return True
    return False

def logout():
    try: st.query_params.clear()
    except: pass
    st.session_state.logged_in = False
    st.session_state.user_info = {}
    st.rerun()

# --- CSS 스타일 ---
st.markdown("""<style>
    .stApp { background: linear-gradient(135deg, #0e1117 0%, #161b22 100%); color: #c9d1d9; font-family: 'Pretendard', sans-serif; font-size: 18px !important; }
    
    /* Hide Default Sidebar */
    [data-testid="stSidebar"] { display: none; }
    
    /* Sticky Top Nav Container */
    .sticky-nav {
        position: sticky;
        top: 0;
        z-index: 999;
        background: rgba(13, 17, 23, 0.95);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid rgba(255,255,255,0.1);
        padding: 10px 20px;
        margin-top: -60px; /* Streamlit default padding offset */
        margin-left: -20px;
        margin-right: -20px;
    }
    
    .nav-btn-cat button {
        background-color: transparent;
        border: none;
        color: #8b949e;
        font-weight: bold;
        font-size: 18px;
        padding: 5px 15px;
    }
    .nav-btn-cat button:hover { color: #58a6ff; }
    .nav-btn-cat-active button { color: #58a6ff !important; border-bottom: 2px solid #58a6ff; }
    
    .nav-btn-sub button {
        background-color: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        color: #c9d1d9;
        font-size: 16px;
        border-radius: 20px;
        padding: 5px 15px;
    }
    .nav-btn-sub button:hover { background-color: #238636; border-color: #238636; color: white; }
    .nav-btn-sub-active button { background-color: #238636 !important; border-color: #238636 !important; color: white !important; }

    .dashboard-btn button { height: 120px; font-size: 22px !important; font-weight: bold; width: 100%; border-radius: 12px; }
    div[data-testid="stDataEditor"] { font-size: 16px !important; }
    .edit-mode-box { border: 2px solid #238636; border-radius: 10px; padding: 20px; background-color: rgba(35, 134, 54, 0.1); margin-top: 20px; margin-bottom: 20px; }
</style>""", unsafe_allow_html=True)

# --- 상태 초기화 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_info' not in st.session_state: st.session_state.user_info = {}
if 'active_page' not in st.session_state: st.session_state.active_page = "login"
if 'nav_category' not in st.session_state: st.session_state.nav_category = "대시보드" # Default Category

if 'edit_target_file' not in st.session_state: st.session_state.edit_target_file = None
if 'edit_selected_ids' not in st.session_state: st.session_state.edit_selected_ids = []
if 'select_all_logs' not in st.session_state: st.session_state.select_all_logs = False
if 'select_all_moves' not in st.session_state: st.session_state.select_all_moves = False

if not st.session_state.logged_in:
    if validate_session(): st.session_state.active_page = "dashboard"

# --- 네비게이션 구조 정의 ---
# Format: Category -> List of (Key, Label, PageID)
NAV_STRUCTURE = {
    "대시보드": [("home", "🏠 홈", "dashboard")],
    "현장 업무": [("insp", "🔧 현장점검", "inspection"), ("qr", "🖼️ QR생성", "qr_gen")],
    "이력 조회": [("status", "📊 투입현황", "status"), ("hist", "📉 점검이력", "fail_history"), ("move", "📱 이동이력", "asset_movement")],
    "데이터 관리": [("asset", "🖥️ 장비마스터", "asset_master"), ("proc", "🏭 공정마스터", "process_master"), ("code", "🛠️ 기초코드", "code_master")],
    "시스템 관리": [("upload", "📥 데이터업로드", "upload"), ("user", "👥 사용자관리", "user_mgmt"), ("logs", "📜 사용이력", "activity_logs")]
}

def render_top_nav():
    st.markdown('<div class="sticky-nav">', unsafe_allow_html=True)
    
    # Row 1: Logo/Title | Categories | User Info
    c1, c2, c3 = st.columns([1.5, 6, 2.5])
    
    with c1:
        st.markdown(f"### 🏭 포항공장")
    
    with c2:
        # Categories
        cols = st.columns(len(NAV_STRUCTURE))
        for i, (cat, items) in enumerate(NAV_STRUCTURE.items()):
            # Check Admin
            if cat == "시스템 관리" and st.session_state.user_info.get('role') != 'admin': continue
            
            with cols[i]:
                # Style Active Category
                if st.session_state.nav_category == cat:
                    st.markdown('<div class="nav-btn-cat-active">', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="nav-btn-cat">', unsafe_allow_html=True)
                
                if st.button(cat, key=f"cat_{i}"):
                    st.session_state.nav_category = cat
                    # Default to first item in category? Or stay on current if in list?
                    # For now just switch category view.
                    # Optional: Auto-navigate to first item?
                    # let's just update category.
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        # User Info & Logout
        uc1, uc2 = st.columns([2, 1])
        with uc1:
            st.markdown(f"<div style='text-align:right; padding-top:10px;'>👋 {st.session_state.user_info.get('name','')}</div>", unsafe_allow_html=True)
        with uc2:
            if st.button("LOGOUT", key="top_logout", type="primary"): logout()
            
    st.markdown("---")
    
    # Row 2: Sub-menus for Active Category
    current_cat = st.session_state.nav_category
    if current_cat in NAV_STRUCTURE:
        sub_items = NAV_STRUCTURE[current_cat]
        # Calculate columns based on items
        scols = st.columns(len(sub_items) + 1) # +1 buffer
        for j, (key, label, page_id) in enumerate(sub_items):
            with scols[j]:
                # Style Active Page
                if st.session_state.active_page == page_id:
                    st.markdown('<div class="nav-btn-sub-active">', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="nav-btn-sub">', unsafe_allow_html=True)
                    
                if st.button(label, key=f"nav_{key}"):
                    st.session_state.active_page = page_id
                    st.session_state.edit_target_file = None
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True) # Spacer

def login_page():
    st.title("⚙️ 장비관리 시스템")
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            uid = st.text_input("아이디")
            upw = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인", type="primary"):
                users = load_data(USERS_FILE)
                u = next((x for x in users if x.get('id')==uid and x.get('password')==upw), None)
                if u:
                    st.session_state.logged_in = True
                    st.session_state.user_info = u
                    st.session_state.active_page = "dashboard"
                    st.session_state.nav_category = "대시보드" # Reset
                    token = create_session(u['id'], u['name'], u['role'])
                    try: st.query_params["token"] = token
                    except: pass
                    st.rerun()
                else: st.error("로그인 실패")

def add_code_callback():
    cat = st.session_state.get("new_code_cat_input", "")
    sub = st.session_state.get("new_code_sub_input", "")
    cat_select = st.session_state.get("new_code_cat_select", "직접입력")
    final_cat = cat if cat_select == "직접입력" else cat_select
    if final_cat and sub:
        codes = load_data(FAILURE_CODE_FILE)
        codes.append({"id": str(uuid.uuid4()), "대분류": final_cat, "상세내용": sub})
        save_data(codes, FAILURE_CODE_FILE)
        log_activity("기초코드", f"코드 추가: {final_cat} > {sub}")
        st.session_state["new_code_cat_input"] = ""; st.session_state["new_code_sub_input"] = ""
        st.success("추가되었습니다.")
    else: st.warning("내용을 입력해주세요.")

def register_asset_callback():
    a1 = st.session_state.get("new_asset_id", "").strip()
    a3 = st.session_state.get("new_asset_maker", "").strip()
    a4 = st.session_state.get("new_asset_model", "").strip()
    type_sel = st.session_state.get("new_asset_type_sel", "선택하세요")
    type_direct = st.session_state.get("new_asset_type_direct", "").strip()
    final_type = type_direct if type_sel == "직접입력" else (type_sel if type_sel != "선택하세요" else "")
    final_os = ""
    if final_type == "PDA": final_os = "Android"
    elif final_type in ["PC", "MES단말기"]: final_os = st.session_state.get("new_asset_os_win", "WINDOWS 10")
    else: final_os = st.session_state.get("new_asset_os_other", "지정없음")

    if not a1 or not final_type: st.error("자체관리번호와 단말기종류는 필수입니다."); return
    assets = load_data(ASSETS_FILE)
    if any(a['자체관리번호'] == a1 for a in assets): st.error(f"이미 존재하는 관리번호입니다: {a1}"); return

    today_str = datetime.now().strftime("%Y-%m-%d")
    assets.append({"자체관리번호": a1, "단말기종류": final_type, "제조사": a3, "모델명": a4, "장비상태": "대기중", "현재위치": "", "OS": final_os, "투입일자": today_str})
    save_data(assets, ASSETS_FILE)
    log_activity("장비마스터", f"신규 장비 등록: {a1} / {final_type}")
    st.session_state["new_asset_id"] = ""; st.session_state["new_asset_maker"] = ""; st.session_state["new_asset_model"] = ""
    st.session_state["new_asset_type_sel"] = "선택하세요"
    if "new_asset_type_direct" in st.session_state: st.session_state["new_asset_type_direct"] = ""
    if "new_asset_os_other" in st.session_state: st.session_state["new_asset_os_other"] = "지정없음"
    st.success("등록되었습니다.")

def clear_asset_fields_on_change():
    if "new_asset_id" in st.session_state: st.session_state["new_asset_id"] = ""
    if "new_asset_maker" in st.session_state: st.session_state["new_asset_maker"] = ""
    if "new_asset_model" in st.session_state: st.session_state["new_asset_model"] = ""
    if "new_asset_os_other" in st.session_state: st.session_state["new_asset_os_other"] = "지정없음"

# --- 공통 에디터 ---
def render_managed_editor(data, file_path, visible_cols=None, read_only_cols=None, show_filter_ui=True, custom_filter_df=None, menu_name="", select_all_key=None):
    if not data: st.info("데이터가 없습니다."); return pd.DataFrame()
    df = pd.DataFrame(data)
    df = df.astype(str).replace('nan', '')
    
    dom_key = DOMAIN_KEYS.get(file_path, "id")
    if dom_key not in df.columns: df[dom_key] = [str(uuid.uuid4()) for _ in range(len(df))]

    d_btn_col, _ = st.columns([2, 8])
    with d_btn_col:
        excel_df = df.copy()
        for c in ['선택', '_origin_idx']:
            if c in excel_df.columns: excel_df = excel_df.drop(columns=[c])
        st.download_button("📥 엑셀 다운로드", to_excel(excel_df), f"{file_path.split('.')[0]}.xlsx")

    if custom_filter_df is not None:
        display_df = custom_filter_df.copy().astype(str).replace('nan', '')
    else:
        display_df = df.copy()
        if show_filter_ui:
            with st.expander("🔍 상세 검색 필터"):
                if st.button("🔄 검색 조건 초기화", key=f"reset_search_{file_path}"):
                    keys_to_clear = [k for k in st.session_state.keys() if k.startswith(f"f_{file_path}_")]
                    for k in keys_to_clear: del st.session_state[k]
                    st.rerun()
                f_col = st.columns(3)
                filters = {}
                search_cols = [c for c in display_df.columns if c != 'password']
                for i, col in enumerate(search_cols):
                    uv = ["전체"] + sorted([x for x in display_df[col].unique() if x])
                    sel = f_col[i%3].selectbox(col, uv, key=f"f_{file_path}_{col}")
                    if sel != "전체": filters[col] = sel
            for k, v in filters.items(): display_df = display_df[display_df[k] == v]

    display_df.reset_index(drop=True, inplace=True)
    display_df.insert(0, "No.", range(1, len(display_df) + 1))
    
    is_selected_all = False
    if select_all_key and select_all_key in st.session_state:
        is_selected_all = st.session_state[select_all_key]
    display_df.insert(0, "선택", is_selected_all)

    if select_all_key:
        c_sel, c_desel, _ = st.columns([1.5, 1.5, 7])
        if c_sel.button("✅ 전체 선택", key=f"btn_all_{file_path}"):
            st.session_state[select_all_key] = True; st.rerun()
        if c_desel.button("❌ 전체 해제", key=f"btn_none_{file_path}"):
            st.session_state[select_all_key] = False; st.rerun()

    col_cfg = { "선택": st.column_config.CheckboxColumn(width="small"), "No.": st.column_config.NumberColumn(width="small", disabled=True) }
    grid_cols = [c for c in display_df.columns if c != "선택"]
    for c in grid_cols: col_cfg[c] = st.column_config.TextColumn(disabled=True)

    if visible_cols: final_cols = ['선택', 'No.'] + [c for c in visible_cols if c in display_df.columns]
    else: final_cols = ['선택', 'No.'] + [c for c in display_df.columns if c not in ['password', '선택', 'No.']]

    main_editor = st.data_editor(display_df, use_container_width=True, hide_index=True, column_order=final_cols, column_config=col_cfg, key=f"main_editor_{file_path}")
    
    c1, c2, _ = st.columns([1.2, 1.2, 7.6])
    with c1:
        if st.button("🛠️ 변경", key=f"btn_edit_{file_path}", type="primary", use_container_width=True):
            selected = main_editor[main_editor['선택']]
            if selected.empty: st.warning("변경할 항목을 선택해주세요."); st.session_state.edit_target_file = None
            else: st.session_state.edit_target_file = file_path; st.session_state.edit_selected_ids = selected[dom_key].tolist(); st.rerun()
    with c2:
        if st.button("🗑️ 선택 삭제", key=f"del_{file_path}", use_container_width=True):
            selected = main_editor[main_editor['선택']]
            if selected.empty: st.warning("삭제할 항목을 선택해주세요.")
            else:
                del_keys = selected[dom_key].astype(str).tolist()
                full_data = load_data(file_path)
                new_data = [d for d in full_data if str(d.get(dom_key)) not in del_keys]
                save_data(new_data, file_path)
                log_msg = f"데이터 삭제 ({len(del_keys)}건)"
                if file_path == ASSETS_FILE: log_msg = f"장비 삭제: {', '.join(selected['자체관리번호'].tolist())}"
                if menu_name: log_activity(menu_name, log_msg)
                st.session_state.edit_target_file = None
                if select_all_key: st.session_state[select_all_key] = False
                st.warning(f"{len(del_keys)}건 삭제됨"); st.rerun()

    if st.session_state.edit_target_file == file_path and st.session_state.edit_selected_ids:
        st.markdown(f"""<div class="edit-mode-box"><h3>📝 선택 항목 수정 모드</h3><p>아래 목록에서 내용을 수정한 뒤 [수정사항 저장] 버튼을 누르세요.</p></div>""", unsafe_allow_html=True)
        full_data_for_edit = load_data(file_path)
        edit_df = pd.DataFrame([d for d in full_data_for_edit if d.get(dom_key) in st.session_state.edit_selected_ids])
        edit_df = edit_df.astype(str).replace('nan', '')
        if edit_df.empty: st.error("데이터를 찾을 수 없습니다."); st.session_state.edit_target_file = None; st.rerun()

        edit_col_cfg = {}
        if read_only_cols:
            for c in read_only_cols: edit_col_cfg[c] = st.column_config.TextColumn(disabled=True)
        edit_col_cfg[dom_key] = st.column_config.TextColumn(disabled=True)
        if file_path == ASSETS_FILE: edit_col_cfg['장비상태'] = st.column_config.SelectboxColumn("장비상태", options=["투입중", "대기중", "수리중", "폐기예정"], required=True)
        
        if visible_cols: edit_final_cols = [c for c in visible_cols if c in edit_df.columns]
        else: edit_final_cols = [c for c in edit_df.columns if c not in ['password']]
        if dom_key not in edit_final_cols and dom_key != 'id': edit_final_cols.insert(0, dom_key)

        edited_data = st.data_editor(edit_df, use_container_width=True, hide_index=True, column_order=edit_final_cols, column_config=edit_col_cfg, key=f"sub_editor_{file_path}")

        ec1, ec2 = st.columns([2, 2])
        with ec1:
            if st.button("💾 수정사항 저장", key=f"save_edit_{file_path}", type="primary"):
                current_full_data = load_data(file_path)
                data_map = {str(r[dom_key]): r for r in current_full_data}
                changes = edited_data.to_dict(orient='records')
                if file_path == ASSETS_FILE:
                    for row in changes:
                        if row.get('장비상태') == '투입중' and not row.get('현재위치'): st.error(f"⚠️ 오류: 장비({row.get('자체관리번호')})의 상태가 '투입중'이면 현재위치를 반드시 입력해야 합니다."); return
                        if row.get('장비상태') in ['대기중', '수리중', '폐기예정']: row['현재위치'] = ""
                    all_procs = load_data(PROCESS_FILE)
                    proc_updated = False
                    for row in changes:
                        aid = row.get('자체관리번호'); status = row.get('장비상태')
                        if status in ['대기중', '수리중', '폐기예정']:
                            for p in all_procs:
                                if p.get('투입장비') == aid: p['투입장비'] = ""; p['투입일자'] = ""; proc_updated = True
                    if proc_updated: save_data(all_procs, PROCESS_FILE)

                change_ids = []
                for row in changes:
                    k = str(row[dom_key]); change_ids.append(row.get(dom_key, k))
                    if k in data_map: data_map[k].update(row)
                save_data(list(data_map.values()), file_path)
                if menu_name: log_activity(menu_name, f"데이터 수정: {', '.join(change_ids)}")
                st.session_state.edit_target_file = None; st.success("수정사항이 저장되었습니다."); st.rerun()
        with ec2:
            if st.button("❌ 닫기 (취소)", key=f"cancel_edit_{file_path}"): st.session_state.edit_target_file = None; st.rerun()

    return main_editor

# --- 메인 로직 ---
if not st.session_state.logged_in:
    login_page()
else:
    # --- Top Navigation ---
    render_top_nav()

    page = st.session_state.active_page

    if page in ["upload", "activity_logs", "user_mgmt"] and st.session_state.user_info.get('role') != 'admin':
        st.error("⛔ 접근 권한이 없습니다."); st.stop()

    if page == "dashboard":
        st.title("🏠 메인 대시보드")
        
        # Dashboard Tiles based on NAV_STRUCTURE
        # Flatten structure except dashboard
        cols = st.columns(4)
        col_idx = 0
        
        for cat, items in NAV_STRUCTURE.items():
            if cat == "대시보드": continue # Skip Home
            if cat == "시스템 관리" and st.session_state.user_info.get('role') != 'admin': continue
            
            for key, label, page_id in items:
                with cols[col_idx % 4]:
                    st.markdown('<div class="dashboard-btn">', unsafe_allow_html=True)
                    if st.button(label, key=f"dash_{key}", use_container_width=True): 
                        st.session_state.active_page = page_id
                        st.session_state.nav_category = cat # Sync Category
                        st.session_state.edit_target_file = None
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                col_idx += 1

    elif page == "activity_logs":
        st.title("📜 시스템 사용 이력")
        logs = load_data(ACTIVITY_LOG_FILE)
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        render_managed_editor(logs, ACTIVITY_LOG_FILE, visible_cols=["timestamp", "user_name", "menu", "action"], read_only_cols=["timestamp", "user_name", "menu", "action"], show_filter_ui=True)

    elif page == "status":
        st.title("📊 전산장비 투입 현황")
        procs = load_data(PROCESS_FILE); assets = load_data(ASSETS_FILE)
        if not procs: st.info("공정 데이터가 없습니다."); 
        else:
            asset_map = {normalize_id(a.get('자체관리번호')): a for a in assets}
            table_data = []
            for p in procs:
                aid = normalize_id(p.get('투입장비', ''))
                a_info = asset_map.get(aid, {})
                row = p.copy()
                row.update({"자체관리번호": aid, "단말기종류": a_info.get('단말기종류', ''), "모델명": a_info.get('모델명', ''), "OS": a_info.get('OS', ''), "장비상태": a_info.get('장비상태', '미투입')})
                for k, v in row.items():
                    if str(v).lower() == 'nan': row[k] = ""
                table_data.append(row)
            
            with st.expander("🔍 상세 검색 필터", expanded=True):
                if st.button("🔄 검색 조건 초기화", key="reset_search_status"):
                    keys = ["f_status_ip", "f_status_dept", "f_status_fac", "f_status_id", "f_status_type", "f_status_os"]
                    for k in keys:
                        if k in st.session_state: del st.session_state[k]
                    st.rerun()
                df_s = pd.DataFrame(table_data).astype(str).replace('nan', '')
                c1, c2, c3 = st.columns(3)
                f_ip = c1.text_input("IP 검색", key="f_status_ip")
                if f_ip and not df_s.empty: df_s = df_s[df_s['IP'].str.contains(f_ip, na=False)]
                f_dept = c2.selectbox("부서", ["전체"] + sorted([x for x in df_s['부서'].unique() if x]), key="f_status_dept")
                if f_dept != "전체" and not df_s.empty: df_s = df_s[df_s['부서'] == f_dept]
                f_fac = c3.selectbox("공장", ["전체"] + sorted([x for x in df_s['공장'].unique() if x]), key="f_status_fac")
                if f_fac != "전체" and not df_s.empty: df_s = df_s[df_s['공장'] == f_fac]
                c4, c5, c6 = st.columns(3)
                f_id = c4.text_input("자체관리번호 검색", key="f_status_id")
                if f_id and not df_s.empty: df_s = df_s[df_s['자체관리번호'].str.contains(f_id, na=False)]
                f_type = c5.selectbox("단말기종류", ["전체"] + sorted([x for x in df_s['단말기종류'].unique() if x]), key="f_status_type")
                if f_type != "전체" and not df_s.empty: df_s = df_s[df_s['단말기종류'] == f_type]
                f_os = c6.selectbox("OS", ["전체"] + sorted([x for x in df_s['OS'].unique() if x]), key="f_status_os")
                if f_os != "전체" and not df_s.empty: df_s = df_s[df_s['OS'] == f_os]

            if not df_s.empty:
                df_final = df_s.reset_index(drop=True)
                df_final.insert(0, "No.", range(1, len(df_final) + 1))
                
                excel_data = to_excel(df_s)
                st.download_button("📥 엑셀 다운로드", excel_data, file_name="투입현황.xlsx")
                
                cols = ["No.", "부서", "공장", "공정", "호기", "IP", "단말기종류", "자체관리번호", "모델명", "OS", "장비상태", "투입일자"]
                valid_cols = [c for c in cols if c in df_final.columns]
                st.dataframe(df_final[valid_cols], use_container_width=True, hide_index=True)
            else: st.info("검색된 데이터가 없습니다.")

    # [복구] 점검이력
    elif page == "fail_history":
        st.title("📉 점검이력관리")
        logs = load_data(LOGS_FILE)
        df_l = pd.DataFrame(logs).astype(str).replace('nan', '')
        if '장비ID' in df_l.columns: df_l.rename(columns={'장비ID': '자체관리번호'}, inplace=True)
        
        with st.expander("🔍 검색 필터", expanded=True):
            if st.button("🔄 검색 조건 초기화", key="reset_search_fail"):
                keys = ["f_fail_range", "f_fail_id", "f_fail_fac", "f_fail_proc", "f_fail_type", "f_fail_man"]
                for k in keys: 
                    if k in st.session_state: del st.session_state[k]
                st.rerun()

            c1, c2, c3 = st.columns(3)
            today = datetime.now().date()
            d_range = c1.date_input("날짜 범위 (From - To)", [today - timedelta(days=7), today], key="f_fail_range")
            s_id = c2.text_input("자체관리번호", key="f_fail_id")
            fac_opts = ["전체"] + sorted([x for x in df_l['공장'].unique() if x]) if '공장' in df_l.columns else ["전체"]
            s_fac = c3.selectbox("공장", fac_opts, key="f_fail_fac")
            c4, c5, c6 = st.columns(3)
            proc_opts = ["전체"] + sorted([x for x in df_l['공정'].unique() if x]) if '공정' in df_l.columns else ["전체"]
            s_proc = c4.selectbox("공정", proc_opts, key="f_fail_proc")
            type_opts = ["전체"] + sorted([x for x in df_l['유형'].unique() if x]) if '유형' in df_l.columns else ["전체"]
            s_type = c5.selectbox("유형", type_opts, key="f_fail_type")
            man_opts = ["전체"] + sorted([x for x in df_l['담당자'].unique() if x]) if '담당자' in df_l.columns else ["전체"]
            s_man = c6.selectbox("담당자", man_opts, key="f_fail_man")

            if len(d_range) == 2:
                start_d, end_d = d_range
                try:
                    df_l['temp_date'] = pd.to_datetime(df_l['일시'], format='%Y-%m-%d %H:%M', errors='coerce').dt.date
                    df_l = df_l[(df_l['temp_date'] >= start_d) & (df_l['temp_date'] <= end_d)]
                    df_l.drop(columns=['temp_date'], inplace=True)
                except: pass
            if s_id and '자체관리번호' in df_l.columns: df_l = df_l[df_l['자체관리번호'].str.contains(s_id, na=False)]
            if s_fac != "전체" and '공장' in df_l.columns: df_l = df_l[df_l['공장'] == s_fac]
            if s_proc != "전체" and '공정' in df_l.columns: df_l = df_l[df_l['공정'] == s_proc]
            if s_type != "전체" and '유형' in df_l.columns: df_l = df_l[df_l['유형'] == s_type]
            if s_man != "전체" and '담당자' in df_l.columns: df_l = df_l[df_l['담당자'] == s_man]

            filtered_logs = df_l.to_dict('records')

        render_managed_editor(filtered_logs, LOGS_FILE, 
                             visible_cols=["일시", "자체관리번호", "IP", "공장", "공정", "호기", "유형", "내용", "담당자"], 
                             read_only_cols=["일시", "자체관리번호", "담당자"], 
                             show_filter_ui=False, custom_filter_df=df_l, menu_name="점검이력", select_all_key="select_all_logs")

    # [복구] 이동이력
    elif page == "asset_movement":
        st.title("📱 장비 이동이력 조회")
        moves = load_data(MOVEMENT_FILE)
        procs = load_data(PROCESS_FILE)
        display_moves = []
        for m in moves:
            row = m.copy()
            prev = row.get('이전위치', '')
            curr = row.get('현재위치', '')
            if prev.replace('.', '').isdigit() or "172." in prev or "192." in prev:
                row['이전위치'] = get_full_location_name(prev, procs)
            if curr.replace('.', '').isdigit() or "172." in curr or "192." in curr:
                row['현재위치'] = get_full_location_name(curr, procs)
            display_moves.append(row)
        
        df_m = pd.DataFrame(display_moves).astype(str).replace('nan', '')

        with st.expander("🔍 검색 필터", expanded=True):
            if st.button("🔄 검색 조건 초기화", key="reset_search_move"):
                keys = ["f_move_range", "f_move_id", "f_move_worker", "f_move_prev", "f_move_curr"]
                for k in keys:
                    if k in st.session_state: del st.session_state[k]
                st.rerun()

            c1, c2, c3 = st.columns(3)
            today = datetime.now().date()
            d_range = c1.date_input("날짜 범위 (From - To)", [today - timedelta(days=7), today], key="f_move_range")
            s_id = c2.text_input("자체관리번호", key="f_move_id")
            worker_opts = ["전체"] + sorted([x for x in df_m['작업자'].unique() if x]) if '작업자' in df_m.columns else ["전체"]
            s_worker = c3.selectbox("작업자", worker_opts, key="f_move_worker")
            c4, c5 = st.columns(2)
            s_prev = c4.text_input("이전위치 검색", key="f_move_prev")
            s_curr = c5.text_input("현재위치 검색", key="f_move_curr")
            
            if len(d_range) == 2:
                start_d, end_d = d_range
                try:
                    df_m['temp_date'] = pd.to_datetime(df_m['날짜'], format='%Y-%m-%d', errors='coerce').dt.date
                    df_m = df_m[(df_m['temp_date'] >= start_d) & (df_m['temp_date'] <= end_d)]
                    df_m.drop(columns=['temp_date'], inplace=True)
                except: pass
            if s_id and '자체관리번호' in df_m.columns: df_m = df_m[df_m['자체관리번호'].str.contains(s_id, na=False)]
            if s_worker != "전체" and '작업자' in df_m.columns: df_m = df_m[df_m['작업자'] == s_worker]
            if s_prev and '이전위치' in df_m.columns: df_m = df_m[df_m['이전위치'].str.contains(s_prev, na=False)]
            if s_curr and '현재위치' in df_m.columns: df_m = df_m[df_m['현재위치'].str.contains(s_curr, na=False)]
            
            filtered_moves = df_m.to_dict('records')

        render_managed_editor(filtered_moves, MOVEMENT_FILE, 
                             visible_cols=["날짜", "자체관리번호", "이전위치", "현재위치", "작업자"], 
                             read_only_cols=["날짜", "자체관리번호", "이전위치", "현재위치", "작업자"], 
                             show_filter_ui=False, custom_filter_df=df_m, menu_name="이동이력", select_all_key="select_all_moves")

    elif page == "inspection":
        st.title("🔧 현장 장비 점검")
        assets = load_data(ASSETS_FILE)
        procs = load_data(PROCESS_FILE)
        fails = load_data(FAILURE_CODE_FILE)
        
        search_list = []
        asset_map = {}
        if assets:
            for a in assets:
                aid = a.get('자체관리번호')
                if not aid: continue
                loc = a.get('현재위치', '미지정')
                status_txt = f"({a.get('장비상태', '')})"
                p_info = next((p for p in procs if p.get('IP') == loc), None)
                loc_str = f"{p_info['공장']} {p_info['공정']} ({loc})" if p_info else loc
                hogi = p_info.get('호기', '') if p_info else ""
                if hogi: loc_str = f"{p_info['공장']} {p_info['공정']} {hogi} ({loc})"
                label = f"[{aid}] {a.get('모델명','')} {status_txt} - {loc_str}"
                search_list.append(label)
                asset_map[label] = a
            
        target_asset = None
        t1, t2 = st.tabs(["🔍 통합 검색", "📸 QR 스캔"])
        with t1:
            sel = st.selectbox("장비 검색", [""] + sorted(search_list))
            if sel: target_asset = asset_map[sel]
        with t2:
            img = st.camera_input("QR 스캔")
            if img:
                try:
                    v = img.getvalue(); cv_img = cv2.imdecode(np.frombuffer(v, np.uint8), cv2.IMREAD_COLOR)
                    d, _, _ = cv2.QRCodeDetector().detectAndDecode(cv_img)
                    if d:
                        found = next((a for a in assets if normalize_id(a.get('자체관리번호'))==normalize_id(d)), None)
                        if found: target_asset = found
                        else: st.warning(f"QR 코드 '{d}'에 해당하는 장비를 찾을 수 없습니다.")
                except cv2.error as e: st.error(f"QR 이미지 처리 오류: {str(e)}")
                except Exception as e: st.error(f"QR 스캔 오류: {str(e)}")

        if target_asset:
            current_loc = target_asset.get('현재위치', '')
            target_type = target_asset.get('단말기종류', '')
            p_info = next((p for p in procs if p.get('IP') == current_loc), None)
            loc_disp = f"{p_info['공장']} {p_info['공정']} ({current_loc})" if p_info else current_loc
            st.info(f"📍 현재 위치: {loc_disp}")
            st.success(f"✅ 선택 장비: {target_asset.get('자체관리번호')} | {target_asset.get('모델명')} | {target_asset.get('단말기종류')}")
            
            is_new_deploy = (target_asset.get('장비상태') == '대기중')
            c1, c2 = st.columns(2)
            m_cats = ["선택하세요"] + sorted(list(set([f.get('대분류','') for f in fails if f.get('대분류')])))
            
            def_m_idx = 0
            if is_new_deploy and "신규투입" in m_cats: def_m_idx = m_cats.index("신규투입")
            m = c1.selectbox("고장 대분류", m_cats, index=def_m_idx)
            
            s_cats = []
            if m and m != "선택하세요": s_cats = sorted([f.get('상세내용','') for f in fails if f.get('대분류')==m])
            s_cats = ["선택하세요"] + s_cats
            
            def_s_idx = 0
            if is_new_deploy and "장비투입" in s_cats: def_s_idx = s_cats.index("장비투입")
            s = c1.selectbox("상세 유형", s_cats, index=def_s_idx)
            
            filtered_procs = [p for p in procs if p.get('단말기종류') == target_type]
            
            if not filtered_procs:
                locs = ["위치 정보 없음 (해당 타입 공정 없음)"]
                if is_new_deploy: st.warning(f"⚠️ '{target_type}' 타입의 등록된 공정이 없습니다.")
            else:
                locs = [""]
                for p in filtered_procs:
                    curr_equip = p.get('투입장비', '')
                    status_info = f"[현재: {curr_equip}]" if curr_equip else "[비어있음]"
                    label = f"{p.get('공장','')} {p.get('공정','')} {p.get('호기','')} ({p.get('IP','')}) [{p.get('단말기종류','')}] {status_info}"
                    locs.append(label)
            
            def_index = 0
            if current_loc and len(locs) > 1:
                try:
                    for idx, txt in enumerate(locs):
                        if current_loc in txt or f"({current_loc})" in txt:
                            def_index = idx; break
                except: def_index = 0
            
            if not isinstance(def_index, int) or def_index < 0 or def_index >= len(locs): def_index = 0
            new_loc_str = c2.selectbox("위치/공정 선택", locs, index=int(def_index))
            
            def get_asset_display(a_item):
                a_id = a_item['자체관리번호']; a_model = a_item.get('모델명', ''); a_status = a_item.get('장비상태', ''); a_ip = a_item.get('현재위치', '')
                loc_txt = "비어있음"
                if a_ip:
                    p_match = next((p for p in procs if p.get('IP') == a_ip), None)
                    if p_match: loc_txt = f"{p_match.get('공장','')} {p_match.get('공정','')} {p_match.get('호기','')} ({a_ip})"
                    else: loc_txt = f"({a_ip})"
                return f"[{a_id}] {a_model} ({a_status}) - {loc_txt}"

            standby = [get_asset_display(a) for a in assets if a['장비상태'] == '대기중' and a['자체관리번호'] != target_asset['자체관리번호'] and a.get('단말기종류') == target_type]
            others = [get_asset_display(a) for a in assets if a['장비상태'] not in ['대기중', '폐기예정'] and a['자체관리번호'] != target_asset['자체관리번호'] and a.get('단말기종류') == target_type]
            avail_list = ["선택안함"] + sorted(standby) + sorted(others)
            alt_sel = c2.selectbox("대체 투입 단말기", avail_list)
            
            memo = st.text_area("점검 및 조치 내용")
            
            if st.button("점검 이력 저장 & 위치 적용", type="primary"):
                errors = validate_inspection_input(is_new_deploy, new_loc_str, m, s, memo)
                if errors:
                    for e in errors: st.error(e)
                else:
                    target_ip = ""; target_fac = ""; target_proc = ""; target_hogi = ""; full_target_loc = ""
                    if new_loc_str and not new_loc_str.startswith("위치 정보 없음"):
                        try: target_ip = new_loc_str.split('(')[-1].split(')')[0].strip()
                        except: pass
                    if not target_ip and current_loc:
                        try:
                            if "(" in current_loc and ")" in current_loc: target_ip = current_loc.split('(')[-1].split(')')[0].strip()
                            else: target_ip = current_loc
                        except: pass

                    if target_ip:
                        proc_match = next((p for p in procs if p['IP'] == target_ip), None)
                        if proc_match:
                            target_fac = proc_match.get('공장', ''); target_proc = proc_match.get('공정', ''); target_hogi = proc_match.get('호기', '')
                            full_target_loc = f"{target_fac} {target_proc} {target_hogi} ({target_ip})"
                        else: full_target_loc = f"({target_ip})"

                    logs = load_data(LOGS_FILE)
                    logs.append({"id": str(uuid.uuid4()), "일시": datetime.now().strftime("%Y-%m-%d %H:%M"), "장비ID": target_asset.get('자체관리번호'), "유형": f"{m}>{s}", "내용": f"{m}>{s} / {memo}", "담당자": st.session_state.user_info['name'], "IP": target_ip, "공장": target_fac, "공정": target_proc, "호기": target_hogi})
                    save_data(logs, LOGS_FILE)
                    
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    all_assets = load_data(ASSETS_FILE); all_procs = load_data(PROCESS_FILE); moves = load_data(MOVEMENT_FILE)

                    if alt_sel != "선택안함" and target_ip:
                        new_id = alt_sel.split(']')[0].replace('[', '').strip(); old_id = target_asset.get('자체관리번호')
                        for a in all_assets:
                            if a['자체관리번호'] == old_id: a['장비상태'] = '수리중'; a['현재위치'] = ""; break
                        for a in all_assets:
                            if a['자체관리번호'] == new_id: a['장비상태'] = '투입중'; a['현재위치'] = full_target_loc; a['투입일자'] = today_str; break
                        target_proc_row = next((p for p in all_procs if p['IP'] == target_ip and p.get('투입장비') == old_id), None)
                        if not target_proc_row: target_proc_row = next((p for p in all_procs if p['IP'] == target_ip and p.get('단말기종류') == target_asset.get('단말기종류')), None)
                        if not target_proc_row: target_proc_row = next((p for p in all_procs if p['IP'] == target_ip), None)
                        if target_proc_row: target_proc_row['투입장비'] = new_id; target_proc_row['투입일자'] = today_str
                        old_prev_loc = get_full_location_name(target_ip, procs)
                        moves.append({"id": str(uuid.uuid4()), "날짜": today_str, "자체관리번호": old_id, "이전위치": old_prev_loc, "현재위치": "수리실(반출)", "작업자": st.session_state.user_info['name']})
                        moves.append({"id": str(uuid.uuid4()), "날짜": today_str, "자체관리번호": new_id, "이전위치": "대기/보관", "현재위치": full_target_loc, "작업자": st.session_state.user_info['name']})
                        logs.append({"id": str(uuid.uuid4()), "일시": datetime.now().strftime("%Y-%m-%d %H:%M"), "장비ID": new_id, "유형": "대체투입", "내용": f"기존장비({old_id}) 고장 교체 / 원인: {m}>{s} / {memo}", "담당자": st.session_state.user_info['name'], "IP": target_ip, "공장": target_fac, "공정": target_proc, "호기": target_hogi})
                        save_data(all_assets, ASSETS_FILE); save_data(all_procs, PROCESS_FILE); save_data(moves, MOVEMENT_FILE); save_data(logs, LOGS_FILE)
                        log_activity("현장점검", f"장비 교체 완료: {old_id} -> {new_id}")
                        st.success(f"✅ 교체 완료! (기존:{old_id} -> 신규:{new_id})")

                    elif target_ip:
                        target_id = target_asset.get('자체관리번호')
                        for a in all_assets:
                            if a['자체관리번호'] == target_id: a['장비상태'] = "투입중"; a['현재위치'] = full_target_loc; a['투입일자'] = today_str; break
                        target_proc_row = next((p for p in all_procs if p['IP'] == target_ip and p.get('단말기종류') == target_asset.get('단말기종류')), None)
                        if not target_proc_row: target_proc_row = next((p for p in all_procs if p['IP'] == target_ip), None)
                        if target_proc_row: target_proc_row['투입장비'] = target_id; target_proc_row['투입일자'] = today_str
                        save_data(all_assets, ASSETS_FILE); save_data(all_procs, PROCESS_FILE)
                        log_activity("현장점검", f"점검 이력/위치 갱신: {target_id}")
                        st.success(f"✅ 점검 이력 및 위치({full_target_loc}) 갱신 완료")
                    else:
                        save_data(logs, LOGS_FILE)
                        st.warning("⚠️ 위치 정보가 선택되지 않아 점검 이력만 저장되었습니다 (위치정보 없음).")

    # [복구] QR 생성
    elif page == "qr_gen":
        st.title("🖼️ 전산장비 QR코드")
        assets = load_data(ASSETS_FILE)
        c1, c2 = st.columns([1, 2])
        with c1:
            tid = st.selectbox("장비 선택", [a.get('자체관리번호') for a in assets])
            if tid:
                qr = qrcode.make(tid); buf = BytesIO(); qr.save(buf, format="PNG")
                img_bytes = buf.getvalue(); st.image(img_bytes, width=200)
                st.download_button("💾 QR 다운로드", img_bytes, file_name=f"{tid}.png", mime="image/png")
        with c2:
            if tid:
                a = next((x for x in assets if x['자체관리번호']==tid), {})
                procs = load_data(PROCESS_FILE)
                p_info = next((p for p in procs if p.get('투입장비') == tid), None)
                if p_info: loc_info = f"{p_info.get('공장', '')} {p_info.get('공정', '')} ({p_info.get('IP', '')})"
                else: loc_info = "미배치"
                st.markdown(f"""<div class="qr-info-card">
                    <div class="qr-info-label">자체관리번호</div><div class="qr-info-value">{a.get('자체관리번호')}</div>
                    <div class="qr-info-label">모델명</div><div class="qr-info-value">{a.get('모델명')}</div>
                    <div class="qr-info-label">종류/제조사</div><div class="qr-info-value">{a.get('단말기종류')} / {a.get('제조사')}</div>
                    <div class="qr-info-label">투입공정</div><div class="qr-info-value" style="color: #28a745;">{loc_info}</div>
                    <div class="qr-info-label">상태</div><div class="qr-info-value">{a.get('장비상태')}</div>
                </div>""", unsafe_allow_html=True)

    # [복구] 업로드
    elif page == "upload":
        st.title("📥 마스터 데이터 업로드")
        t1, t2, t3, t4 = st.tabs(["📄 장비 엑셀", "🏭 공정 엑셀", "🔧 투입현황 엑셀", "⚠️ 초기화"])
        with t1:
            f1 = st.file_uploader("장비 마스터", key="u1")
            if f1 and st.button("장비 업로드"):
                try:
                    df = pd.read_excel(f1)
                    is_valid, msg = validate_asset_data(df)
                    if not is_valid: st.error(f"❌ {msg}")
                    else:
                        df = df.astype(str).fillna("")
                        if '투입일자' not in df.columns: df['투입일자'] = datetime.now().strftime("%Y-%m-%d")
                        else: df['투입일자'] = df['투입일자'].apply(lambda x: datetime.now().strftime("%Y-%m-%d") if not x or x.lower()=='nan' else x)
                        save_data(df.to_dict('records'), ASSETS_FILE); sync_data_integrity()
                        log_activity("업로드", "장비 마스터 엑셀 업로드"); st.success("완료")
                except Exception as e: st.error(f"업로드 실패: {e}")
        with t2:
            f2 = st.file_uploader("공정 마스터", key="u2")
            if f2 and st.button("공정 업로드"):
                try:
                    df = pd.read_excel(f2).astype(str).fillna("")
                    if 'id' not in df.columns: df['id'] = [str(uuid.uuid4()) for _ in range(len(df))]
                    else: df['id'] = df['id'].apply(lambda x: str(uuid.uuid4()) if x == 'nan' or not x else x)
                    save_data(df.to_dict('records'), PROCESS_FILE); sync_data_integrity()
                    log_activity("업로드", "공정 마스터 엑셀 업로드"); st.success("완료")
                except Exception as e: st.error(f"업로드 실패: {e}")
        with t3:
            f3 = st.file_uploader("투입현황(보정) 엑셀", key="u3")
            if f3 and st.button("투입현황 업로드"):
                try:
                    df = pd.read_excel(f3).astype(str).fillna("")
                    procs = load_data(PROCESS_FILE); assets = load_data(ASSETS_FILE)
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    for _, row in df.iterrows():
                        ip = row.get('IP'); p_type = row.get('단말기종류'); aid = row.get('자체관리번호')
                        if ip and aid:
                            for p in procs:
                                if p['IP'] == ip and p.get('단말기종류') == p_type: p['투입장비'] = aid; p['투입일자'] = today_str; break
                            for a in assets:
                                if a['자체관리번호'] == aid: a['현재위치'] = ip; a['장비상태'] = "투입중"; a['투입일자'] = today_str; break
                    save_data(procs, PROCESS_FILE); save_data(assets, ASSETS_FILE); sync_data_integrity()
                    log_activity("업로드", "투입현황(보정) 업로드"); st.success("투입현황 동기화 완료")
                except Exception as e: st.error(f"업로드 실패: {e}")
        with t4:
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("장비 초기화"): save_data([], ASSETS_FILE); log_activity("초기화", "장비 데이터 초기화"); st.warning("장비 삭제됨")
            if c2.button("공정 초기화"): save_data([], PROCESS_FILE); log_activity("초기화", "공정 데이터 초기화"); st.warning("공정 삭제됨")
            if c3.button("투입 초기화"):
                assets = load_data(ASSETS_FILE); procs = load_data(PROCESS_FILE)
                for a in assets: a['현재위치'] = ""; a['장비상태'] = "대기중"; a['투입일자'] = ""
                for p in procs: p['투입장비'] = ""; p['투입일자'] = ""
                save_data(assets, ASSETS_FILE); save_data(procs, PROCESS_FILE)
                log_activity("초기화", "투입 정보(매핑) 초기화"); st.warning("투입 정보 초기화됨")
            if c4.button("전체 초기화"): save_data([], ASSETS_FILE); save_data([], PROCESS_FILE); save_data([], LOGS_FILE); log_activity("초기화", "전체 시스템 데이터 초기화"); st.warning("전체 삭제됨")

    elif page == "code_master":
        st.title("🛠️ 기초코드(고장유형) 관리")
        codes = load_data(FAILURE_CODE_FILE)
        for c in codes:
            if 'id' not in c: c['id'] = str(uuid.uuid4())
        render_managed_editor(codes, FAILURE_CODE_FILE, visible_cols=["대분류", "상세내용"], read_only_cols=["id"], menu_name="기초코드")
        with st.expander("➕ 새로운 분류 추가"):
            c1, c2 = st.columns(2)
            existing_cats = sorted(list(set([c['대분류'] for c in codes])))
            cat_choice = c1.selectbox("대분류 선택", ["직접입력"] + existing_cats, key="new_code_cat_select")
            if cat_choice == "직접입력": c1.text_input("대분류 직접 입력", key="new_code_cat_input")
            c2.text_input("상세내용 입력", key="new_code_sub_input")
            st.button("추가 등록", type="primary", on_click=add_code_callback)

    elif page == "asset_master":
        st.title("🖥️ 장비 마스터 조회")
        assets = load_data(ASSETS_FILE)
        df_a = pd.DataFrame(assets).astype(str).replace('nan', '')
        if df_a.empty: df_a = pd.DataFrame(columns=["자체관리번호", "단말기종류", "제조사", "모델명", "OS", "장비상태", "현재위치", "투입일자"])
        with st.expander("🔍 상세 검색 필터", expanded=True):
            if st.button("🔄 검색 조건 초기화", key="reset_search_asset"):
                keys_to_clear = ["f_asset_id", "f_asset_type", "f_asset_maker", "f_asset_os"]
                for k in keys_to_clear: 
                    if k in st.session_state: del st.session_state[k]
                st.rerun()
            c1, c2 = st.columns(2)
            f_id = c1.text_input("자체관리번호 검색", key="f_asset_id")
            if f_id: df_a = df_a[df_a['자체관리번호'].str.contains(f_id, na=False)]
            all_types = ["전체"] + sorted([x for x in df_a['단말기종류'].unique() if x])
            f_type = c2.selectbox("단말기종류", all_types, key="f_asset_type")
            if f_type != "전체": df_a = df_a[df_a['단말기종류'] == f_type]
            c3, c4 = st.columns(2)
            f_maker = c3.selectbox("제조사", ["전체"] + sorted([x for x in df_a['제조사'].unique() if x]), key="f_asset_maker")
            if f_maker != "전체": df_a = df_a[df_a['제조사'] == f_maker]
            f_os = c4.selectbox("OS", ["전체"] + sorted([x for x in df_a['OS'].unique() if x]), key="f_asset_os")
            if f_os != "전체": df_a = df_a[df_a['OS'] == f_os]
            filtered_assets = df_a.to_dict('records')
        edited_df = render_managed_editor(filtered_assets, ASSETS_FILE, visible_cols=["자체관리번호", "단말기종류", "제조사", "모델명", "OS", "장비상태", "현재위치", "투입일자"], read_only_cols=["자체관리번호", "현재위치", "투입일자"], show_filter_ui=False, custom_filter_df=df_a, menu_name="장비마스터")
        if st.button("📋 선택 행 복사 (신규등록 폼으로)", use_container_width=True):
            sel_rows = edited_df[edited_df['선택']]
            if not sel_rows.empty:
                row = sel_rows.iloc[0]
                st.session_state["new_asset_id"] = row.get("자체관리번호", "")
                st.session_state["new_asset_maker"] = row.get("제조사", "")
                st.session_state["new_asset_model"] = row.get("모델명", "")
                curr_type = row.get("단말기종류", "")
                if curr_type in ["MES단말기", "프린터", "PC", "PDA"]: st.session_state["new_asset_type_sel"] = curr_type
                else: st.session_state["new_asset_type_sel"] = "직접입력"; st.session_state["new_asset_type_direct"] = curr_type
                curr_os = row.get("OS", "")
                if curr_type in ["PC", "MES단말기"] and curr_os in ["WINDOWS XP", "WINDOWS 7", "WINDOWS 10", "WINDOWS 11"]: st.session_state["new_asset_os_win"] = curr_os
                elif curr_type != "PDA": st.session_state["new_asset_os_other"] = curr_os
                st.success("복사되었습니다."); st.rerun()
            else: st.warning("선택해주세요.")
        with st.expander("➕ 장비 신규 등록", expanded=True):
            c1, c2 = st.columns(2)
            base_types = ["MES단말기", "프린터", "PC", "PDA"]
            type_opts = ["선택하세요"] + base_types + ["직접입력"]
            a2_select = c2.selectbox("단말기종류", type_opts, key="new_asset_type_sel", on_change=clear_asset_fields_on_change)
            final_type = ""
            if a2_select == "직접입력": final_type = c2.text_input("단말기종류 직접 입력", key="new_asset_type_direct")
            elif a2_select != "선택하세요": final_type = a2_select
            c1.text_input("자체관리번호(KEY)", key="new_asset_id")
            c1.text_input("제조사", key="new_asset_maker")
            c2.text_input("모델명", key="new_asset_model")
            if final_type == "PDA": c1.text_input("OS", value="Android", disabled=True, key="new_asset_os_pda")
            elif final_type in ["PC", "MES단말기"] or (a2_select in ["PC", "MES단말기"]): c1.selectbox("OS", ["WINDOWS XP", "WINDOWS 7", "WINDOWS 10", "WINDOWS 11"], key="new_asset_os_win")
            else: c1.text_input("OS", value="지정없음", key="new_asset_os_other")
            st.button("등록", type="primary", on_click=register_asset_callback)

    elif page == "process_master":
        st.title("🏭 공정 마스터 조회")
        procs = load_data(PROCESS_FILE)
        df_p = pd.DataFrame(procs).astype(str).replace('nan', '')
        if not df_p.empty:
            with st.expander("🔍 상세 검색 필터", expanded=True):
                if st.button("🔄 검색 조건 초기화", key="reset_search_proc"):
                    keys_to_clear = ["f_proc_ip", "f_proc_dept", "f_proc_fac", "f_proc_proc", "f_proc_hogi"]
                    for k in keys_to_clear: 
                        if k in st.session_state: del st.session_state[k]
                    st.rerun()
                f_ip = st.text_input("IP 검색", key="f_proc_ip")
                if f_ip: df_p = df_p[df_p['IP'].str.contains(f_ip, na=False)]
                c1, c2, c3, c4 = st.columns(4)
                dept_opts = ["전체"] + sorted([x for x in df_p['부서'].unique() if x])
                f_dept = c1.selectbox("부서", dept_opts, key="f_proc_dept")
                if f_dept != "전체": df_p = df_p[df_p['부서'] == f_dept]
                fac_opts = ["전체"] + sorted([x for x in df_p['공장'].unique() if x])
                f_fac = c2.selectbox("공장", fac_opts, key="f_proc_fac")
                if f_fac != "전체": df_p = df_p[df_p['공장'] == f_fac]
                proc_opts = ["전체"] + sorted([x for x in df_p['공정'].unique() if x])
                f_proc = c3.selectbox("공정", proc_opts, key="f_proc_proc")
                if f_proc != "전체": df_p = df_p[df_p['공정'] == f_proc]
                hogi_opts = ["전체"] + sorted([x for x in df_p['호기'].unique() if x])
                f_hogi = c4.selectbox("호기", hogi_opts, key="f_proc_hogi")
                if f_hogi != "전체": df_p = df_p[df_p['호기'] == f_hogi]
                filtered_procs = df_p.to_dict('records')
        else: filtered_procs = []
        edited_df = render_managed_editor(filtered_procs, PROCESS_FILE, visible_cols=["IP", "단말기종류", "부서", "공장", "공정", "호기", "투입장비", "투입일자"], read_only_cols=["IP", "투입장비", "투입일자"], show_filter_ui=False, custom_filter_df=df_p if not df_p.empty else None, menu_name="공정마스터")
        if st.button("📋 선택 행 복사 (신규등록 폼으로)", use_container_width=True):
            sel_rows = edited_df[edited_df['선택']]
            if not sel_rows.empty:
                row = sel_rows.iloc[0]
                st.session_state["new_proc_ip"] = row.get("IP", "")
                st.session_state["new_proc_type"] = row.get("단말기종류", "")
                st.session_state["new_proc_name"] = row.get("공정", "")
                st.session_state["new_proc_dept"] = row.get("부서", "")
                st.session_state["new_proc_factory"] = row.get("공장", "")
                st.session_state["new_proc_hogi"] = row.get("호기", "")
                st.success("복사되었습니다."); st.rerun()
            else: st.warning("선택해주세요.")
        with st.expander("➕ 공정 신규 등록", expanded=True):
            with st.form("new_proc"):
                c1, c2 = st.columns(2)
                p1 = c1.text_input("IP (KEY)", key="new_proc_ip")
                p_type = c2.selectbox("단말기종류(Slot)", ["MES단말기", "프린터", "PC", "PDA", "기타"], key="new_proc_type")
                p2 = c2.text_input("공정명", key="new_proc_name")
                p3 = c1.text_input("부서", key="new_proc_dept")
                p4 = c2.text_input("공장", key="new_proc_factory")
                p5 = c1.text_input("호기", key="new_proc_hogi")
                if st.form_submit_button("등록", type="primary"):
                    procs.append({"id": str(uuid.uuid4()), "IP":p1, "단말기종류":p_type, "공정":p2, "부서":p3, "공장":p4, "호기":p5, "투입장비":"", "투입일자":""})
                    save_data(procs, PROCESS_FILE)
                    log_activity("공정마스터", f"신규 공정 등록: {p1} ({p_type})")
                    st.session_state["new_proc_ip"] = ""; st.session_state["new_proc_name"] = ""; st.session_state["new_proc_dept"] = ""; st.session_state["new_proc_factory"] = ""; st.session_state["new_proc_hogi"] = ""
                    st.success("등록되었습니다."); st.rerun()