import psycopg2
from psycopg2.extras import RealDictCursor
import os
import logging
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DATABASE_URL")
if DB_URL and "?" in DB_URL:
    DB_URL = DB_URL.split("?")[0]

def get_connection():
    """Returns a PostgreSQL database connection."""
    if not DB_URL:
        logging.error("DATABASE_URL is not set.")
        raise ValueError("DATABASE_URL is not set in environment variables.")
    
    # Connect using RealDictCursor so rows can be accessed like dictionaries
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    return conn

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
    """Database initialization is now handled by PostgreSQL migration scripts."""
    pass

if __name__ == "__main__":
    init_db()
