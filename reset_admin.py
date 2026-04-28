import sqlite3
from modules.auth import AuthManager

def reset_password():
    # 'hdweld@123' 문자열을 해싱합니다.
    pw_hash = AuthManager.hash_password('hdweld@123')
    
    # DB에 연결하여 admin 계정의 비밀번호를 업데이트합니다.
    conn = sqlite3.connect('device_management.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = 'admin'", (pw_hash,))
    conn.commit()
    conn.close()
    
    print("========================================")
    print("성공: admin 계정의 비밀번호가 초기화되었습니다.")
    print("초기 비밀번호: hdweld@123")
    print("========================================")

if __name__ == "__main__":
    reset_password()
