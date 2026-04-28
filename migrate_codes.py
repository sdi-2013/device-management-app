import json
import sqlite3
import pandas as pd
import os

DB_FILE = 'device_management.db'
JSON_FILE = 'failure_codes.json'

def migrate_codes():
    if not os.path.exists(JSON_FILE):
        print("No JSON file found.")
        return

    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except: return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Create table if not exists (it should exist from init_db, but safe check)
    c.execute('''CREATE TABLE IF NOT EXISTS failure_codes
                 (id TEXT PRIMARY KEY, category TEXT, detail TEXT)''')
    
    # Clear old
    c.execute("DELETE FROM failure_codes")

    count = 0
    for item in data:
        c.execute("INSERT INTO failure_codes (id, category, detail) VALUES (?, ?, ?)",
                  (item.get('id', str(count)), item.get('대분류'), item.get('상세내용')))
        count += 1
        
    conn.commit()
    conn.close()
    print(f"Migrated {count} codes.")

if __name__ == "__main__":
    migrate_codes()
