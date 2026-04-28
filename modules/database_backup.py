import sqlite3
import os
import logging
from datetime import datetime

DB_FILE = "device_management.db"

def get_connection():
    """Returns a database connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with the required schema."""
    if not os.path.exists(DB_FILE):
        logging.info("Initializing new database...")
    
    conn = get_connection()
    c = conn.cursor()
    
    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        name TEXT,
        role TEXT,
        must_change_pw BOOLEAN DEFAULT 0,
        created_at TEXT
    )''')

    # Sessions Table (New for secure session management)
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT,
        created_at TEXT,
        expires_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Assets Table
    c.execute('''CREATE TABLE IF NOT EXISTS assets (
        id TEXT PRIMARY KEY, -- 자체관리번호
        type TEXT, -- 단말기종류
        maker TEXT, -- 제조사
        model TEXT, -- 모델명
        os TEXT,
        status TEXT, -- 장비상태
        location TEXT, -- 현재위치
        deploy_date TEXT -- 투입일자
    )''')

    # Processes Table
    c.execute('''CREATE TABLE IF NOT EXISTS processes (
        id TEXT PRIMARY KEY,
        ip TEXT UNIQUE,
        type TEXT, -- 단말기종류
        name TEXT, -- 공정
        dept TEXT, -- 부서
        factory TEXT, -- 공장
        hogi TEXT, -- 호기
        asset_id TEXT, -- 투입장비 (FK)
        deploy_date TEXT, -- 투입일자
        FOREIGN KEY(asset_id) REFERENCES assets(id)
    )''')

    # Maintenance Logs
    c.execute('''CREATE TABLE IF NOT EXISTS maintenance_logs (
        id TEXT PRIMARY KEY,
        asset_id TEXT,
        action_type TEXT, -- 유형
        content TEXT, -- 내용
        technician TEXT, -- 담당자
        timestamp TEXT,
        location_snapshot TEXT,
        FOREIGN KEY(asset_id) REFERENCES assets(id)
    )''')

    # Movement Logs
    c.execute('''CREATE TABLE IF NOT EXISTS movement_logs (
        id TEXT PRIMARY KEY,
        asset_id TEXT,
        prev_loc TEXT,
        curr_loc TEXT,
        worker TEXT,
        date TEXT,
        FOREIGN KEY(asset_id) REFERENCES assets(id)
    )''')

    # Failure Codes
    c.execute('''CREATE TABLE IF NOT EXISTS failure_codes (
        id TEXT PRIMARY KEY,
        category TEXT, -- 대분류
        detail TEXT -- 상세내용
    )''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
