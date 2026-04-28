import sqlite3
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
import pandas as pd

# .env 파일에서 DATABASE_URL 로드
load_dotenv()
PG_URL = os.environ.get('DIRECT_URL') or os.environ.get('DATABASE_URL')
SQLITE_DB = 'device_management.db'

def get_sqlite_conn():
    return sqlite3.connect(SQLITE_DB)

def get_pg_conn():
    if not PG_URL:
        print("Error: DATABASE_URL 환경 변수가 설정되지 않았습니다.")
        print(".env 파일을 생성하고 DATABASE_URL=postgres://... 를 입력해주세요.")
        return None
    return psycopg2.connect(PG_URL)

def init_pg_db(pg_conn):
    """PostgreSQL에 테이블 스키마 생성"""
    print("PostgreSQL 테이블 생성 중...")
    with pg_conn.cursor() as c:
        # Users Table
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            name TEXT,
            role TEXT,
            must_change_pw BOOLEAN DEFAULT FALSE,
            created_at TEXT
        )''')

        # Sessions Table
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT,
            expires_at TEXT
        )''')

        # Assets Table
        c.execute('''CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            type TEXT,
            maker TEXT,
            model TEXT,
            os TEXT,
            status TEXT,
            location TEXT,
            deploy_date TEXT
        )''')

        # Processes Table
        c.execute('''CREATE TABLE IF NOT EXISTS processes (
            id TEXT PRIMARY KEY,
            ip TEXT,
            type TEXT,
            name TEXT,
            dept TEXT,
            factory TEXT,
            hogi TEXT,
            asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            deploy_date TEXT
        )''')

        # Maintenance Logs
        c.execute('''CREATE TABLE IF NOT EXISTS maintenance_logs (
            id TEXT PRIMARY KEY,
            asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
            action_type TEXT,
            content TEXT,
            technician TEXT,
            timestamp TEXT,
            location_snapshot TEXT
        )''')

        # Movement Logs
        c.execute('''CREATE TABLE IF NOT EXISTS movement_logs (
            id TEXT PRIMARY KEY,
            asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
            action_type TEXT,
            prev_loc TEXT,
            curr_loc TEXT,
            worker TEXT,
            date TEXT
        )''')

        # Failure Codes
        c.execute('''CREATE TABLE IF NOT EXISTS failure_codes (
            id TEXT PRIMARY KEY,
            device_type TEXT,
            category TEXT,
            detail TEXT,
            sort_order INTEGER DEFAULT 0
        )''')

        # Common Codes
        c.execute('''CREATE TABLE IF NOT EXISTS common_codes (
            group_code TEXT,
            code_id TEXT,
            code_name TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            ref_id TEXT,
            PRIMARY KEY (group_code, code_id)
        )''')
    pg_conn.commit()
    print("테이블 생성 완료.")

def migrate_table(sqlite_conn, pg_conn, table_name):
    """단일 테이블 데이터 마이그레이션"""
    print(f"[{table_name}] 데이터 복사 중...")
    
    # SQLite에서 데이터 읽기
    df = pd.read_sql(f"SELECT * FROM {table_name}", sqlite_conn)
    if df.empty:
        print(f"  - {table_name}: 데이터 없음")
        return
        
    # Pandas DataFrame의 boolean 값을 PostgreSQL이 인식할 수 있도록 변환 (필요시)
    # 현재 스키마에서는 주로 TEXT나 INTEGER를 사용함.
    
    # PostgreSQL에 삽입
    columns = list(df.columns)
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
        sql.Identifier(table_name),
        sql.SQL(', ').join(map(sql.Identifier, columns)),
        sql.SQL(', ').join(sql.Placeholder() * len(columns))
    )
    
    with pg_conn.cursor() as c:
        for row in df.itertuples(index=False, name=None):
            clean_row = []
            for col_name, x in zip(columns, row):
                if pd.isna(x) or x == "":
                    clean_row.append(None)
                elif col_name in ['must_change_pw', 'is_active']:
                    clean_row.append(bool(x))
                else:
                    clean_row.append(x)
            c.execute(query, tuple(clean_row))
            
    pg_conn.commit()
    print(f"  - {table_name}: {len(df)}행 복사 완료")

def main():
    pg_conn = get_pg_conn()
    if not pg_conn:
        return
        
    sqlite_conn = get_sqlite_conn()
    
    try:
        init_pg_db(pg_conn)
        
        # 외래키 참조 무결성을 위해 순서대로 마이그레이션
        tables = [
            'users', 
            'sessions', 
            'assets', 
            'processes', 
            'maintenance_logs', 
            'movement_logs', 
            'failure_codes', 
            'common_codes'
        ]
        
        for table in tables:
            migrate_table(sqlite_conn, pg_conn, table)
            
        print("\n🎉 모든 데이터 마이그레이션이 완료되었습니다!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        pg_conn.rollback()
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    main()
