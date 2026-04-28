import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
import os
import logging
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DATABASE_URL")
if DB_URL and "?" in DB_URL:
    DB_URL = DB_URL.split("?")[0]

@st.cache_resource
def get_pool():
    if not DB_URL:
        logging.error("DATABASE_URL is not set.")
        raise ValueError("DATABASE_URL is not set in environment variables.")
    # Initialize a pool with 1 min and 50 max connections
    return ThreadedConnectionPool(1, 50, DB_URL)

class PooledConnectionWrapper:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._closed = False
        
    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', RealDictCursor)
        return self._conn.cursor(*args, **kwargs)
        
    def commit(self):
        self._conn.commit()
        
    def rollback(self):
        self._conn.rollback()
        
    def close(self):
        if not self._closed:
            # Return connection to the pool instead of closing it
            try:
                self._conn.rollback()
            except Exception:
                pass
            self._pool.putconn(self._conn)
            self._closed = True

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

def get_connection():
    """Returns a pooled PostgreSQL database connection."""
    pool = get_pool()
    conn = pool.getconn()
    return PooledConnectionWrapper(conn, pool)

import pandas as pd

def read_df(query, conn, params=None):
    """
    pandas.read_sql 대신 사용합니다.
    RealDictCursor의 결과를 DataFrame으로 안전하게 변환합니다.
    """
    with conn.cursor() as c:
        c.execute(query, params)
        data = c.fetchall()
        if not data:
            cols = [desc[0] for desc in c.description] if c.description else []
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(data)

def init_db():
    """Create indexes for performance optimization."""
    conn = get_connection()
    try:
        with conn.cursor() as c:
            c.execute("CREATE INDEX IF NOT EXISTS idx_processes_asset_id ON processes(asset_id);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_processes_ip ON processes(ip);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_common_codes_group_code ON common_codes(group_code);")
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to create indexes: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
