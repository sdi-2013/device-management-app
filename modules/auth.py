import hashlib
import uuid
import secrets
from datetime import datetime, timedelta
from modules.utils import get_kst_now
from .database import get_connection

class AuthManager:
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using SHA-256 with a salt (simplified for no-dependency reqs)."""
        # In a real generic env, we might use uuid as salt per user, but here we keep it simple yet better than plaintext.
        # Ideally, we should store salt in the DB. For this refactor, we will use a fixed salt + user specific salt if possible.
        # Let's use PBKDF2 if available (standard in Python 3.4+)
        salt = b'device_mgr_salt' # In production, use random salt per user
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000).hex()

    @staticmethod
    def login(user_id, password):
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = c.fetchone()
        conn.close()

        if user:
            # Verify password
            input_hash = AuthManager.hash_password(password)
            if input_hash == user['password_hash']:
                return dict(user)
        return None

    @staticmethod
    def create_session(user_id):
        token = secrets.token_urlsafe(32)
        created_at = get_kst_now()
        expires_at = created_at + timedelta(hours=12) # 12 hour session
        
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                  (token, user_id, created_at.isoformat(), expires_at.isoformat()))
        conn.commit()
        conn.close()
        return token

    @staticmethod
    def logout():
        token = None
        try:
            import streamlit as st
            token = st.query_params.get("token")
        except Exception:
            pass
            
        if token:
            conn = get_connection()
            try:
                c = conn.cursor()
                c.execute("DELETE FROM sessions WHERE token = %s", (token,))
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()
                
        try:
            import streamlit as st
            st.session_state.logged_in = False
            st.session_state.user_info = {}
            st.query_params.clear()
        except Exception:
            pass

    @staticmethod
    def validate_session(token):
        if not token: return None
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT s.*, u.name, u.role FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = %s", (token,))
        session = c.fetchone()
        conn.close()
        
        if session:
            expires = datetime.fromisoformat(session['expires_at'])
            if get_kst_now() < expires:
                return {"id": session['user_id'], "name": session['name'], "role": session['role']}
            else:
                # Cleanup expired
                conn = get_connection()
                conn.cursor().execute("DELETE FROM sessions WHERE token = %s", (token,))
                conn.commit()
                conn.close()
        return None

    @staticmethod
    def create_initial_admin():
        """Creates the initial admin user if no users exist."""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT count(*) FROM users")
        if c.fetchone()[0] == 0:
            # Create default admin
            pw_hash = AuthManager.hash_password("hdweld@123") # Default password, shoud be changed
            c.execute("INSERT INTO users (id, password_hash, name, role, created_at) VALUES (%s, %s, %s, %s, %s)",
                      ("admin", pw_hash, "마스터", "admin", get_kst_now().isoformat()))
            conn.commit()
            print("Admin user created (admin / hdweld@123)")
        conn.close()
