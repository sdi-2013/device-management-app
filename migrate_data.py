import json
import os
import secrets
from modules.database import get_connection, init_db
from modules.auth import AuthManager
from datetime import datetime

# File paths
ASSETS_FILE = 'assets.json'
PROCESS_FILE = 'processes.json'
LOGS_FILE = 'maintenance_logs.json'
MOVEMENT_FILE = 'movement_logs.json'
FAILURE_CODE_FILE = 'failure_codes.json'
USERS_FILE = 'users.json'

def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def migrate():
    print("Starting migration...")
    init_db()
    conn = get_connection()
    c = conn.cursor()

    # 1. Users
    users = load_json(USERS_FILE)
    print(f"Migrating {len(users)} users...")
    for u in users:
        uid = u.get('id')
        plain_pw = u.get('password')
        name = u.get('name')
        role = u.get('role')
        
        # Hash password
        pw_hash = AuthManager.hash_password(plain_pw) if plain_pw else AuthManager.hash_password("hdweld@123")
        
        try:
            c.execute("INSERT OR REPLACE INTO users (id, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                      (uid, pw_hash, name, role, datetime.now().isoformat()))
        except Exception as e:
            print(f"Error migrating user {uid}: {e}")

    # 2. Assets
    assets = load_json(ASSETS_FILE)
    print(f"Migrating {len(assets)} assets...")
    for a in assets:
        try:
            c.execute("INSERT OR REPLACE INTO assets (id, type, maker, model, os, status, location, deploy_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (
                          a.get('자체관리번호'), 
                          a.get('단말기종류'),
                          a.get('제조사'),
                          a.get('모델명'),
                          a.get('OS'),
                          a.get('장비상태'),
                          a.get('현재위치'),
                          a.get('투입일자')
                      ))
        except Exception as e:
            print(f"Error migrating asset {a.get('자체관리번호')}: {e}")

    # 3. Processes
    procs = load_json(PROCESS_FILE)
    print(f"Migrating {len(procs)} processes...")
    for p in procs:
        try:
            c.execute("INSERT OR REPLACE INTO processes (id, ip, type, name, dept, factory, hogi, asset_id, deploy_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (
                          p.get('id'),
                          p.get('IP'),
                          p.get('단말기종류'),
                          p.get('공정'),
                          p.get('부서'),
                          p.get('공장'),
                          p.get('호기'),
                          p.get('투입장비'),
                          p.get('투입일자')
                      ))
        except Exception as e:
            print(f"Error migrating process {p.get('IP')}: {e}")

    # 4. Logs
    logs = load_json(LOGS_FILE)
    print(f"Migrating {len(logs)} maintenance logs...")
    for l in logs:
        try:
            # Construct a location snapshot string if possible
            loc_snapshot = f"{l.get('공장','')} {l.get('공정','')} {l.get('호기','')} ({l.get('IP','')})"
            c.execute("INSERT OR REPLACE INTO maintenance_logs (id, asset_id, action_type, content, technician, timestamp, location_snapshot) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (
                          l.get('id'),
                          l.get('장비ID'),
                          l.get('유형'),
                          l.get('내용'),
                          l.get('담당자'),
                          l.get('일시'),
                          loc_snapshot
                      ))
        except Exception as e:
            print(f"Error migrating log {l.get('id')}: {e}")

    # 5. Movement
    moves = load_json(MOVEMENT_FILE)
    print(f"Migrating {len(moves)} movement logs...")
    for m in moves:
        try:
            c.execute("INSERT OR REPLACE INTO movement_logs (id, asset_id, prev_loc, curr_loc, worker, date) VALUES (?, ?, ?, ?, ?, ?)",
                      (
                          m.get('id'),
                          m.get('자체관리번호'),
                          m.get('이전위치'),
                          m.get('현재위치'),
                          m.get('작업자'),
                          m.get('날짜')
                      ))
        except Exception as e:
            print(f"Error migrating movement {m.get('id')}: {e}")

    # 6. Failure Codes
    codes = load_json(FAILURE_CODE_FILE)
    print(f"Migrating {len(codes)} failure codes...")
    for cd in codes:
        try:
            c.execute("INSERT OR REPLACE INTO failure_codes (id, category, detail) VALUES (?, ?, ?)",
                      (
                          cd.get('id'),
                          cd.get('대분류'),
                          cd.get('상세내용')
                      ))
        except Exception as e:
            print(f"Error migrating code {cd.get('id')}: {e}")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
