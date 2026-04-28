import sqlite3
import pandas as pd

def migrate_processes_schema():
    conn = sqlite3.connect('device_management.db')
    c = conn.cursor()
    
    print("Beginning migration: Removing UNIQUE constraint on 'ip' in 'processes' table...")
    
    # 1. Rename existing table
    c.execute("ALTER TABLE processes RENAME TO processes_old")
    
    # 2. Create new table WITHOUT UNIQUE on ip
    # Note: We keep the structure but remove "UNIQUE" from "ip TEXT UNIQUE"
    c.execute('''CREATE TABLE IF NOT EXISTS processes (
        id TEXT PRIMARY KEY,
        ip TEXT, -- UNIQUE constraint removed
        type TEXT,
        name TEXT,
        dept TEXT,
        factory TEXT,
        hogi TEXT,
        asset_id TEXT,
        deploy_date TEXT,
        FOREIGN KEY(asset_id) REFERENCES assets(id)
    )''')
    
    # 3. Copy data
    # explicitly listing columns to be safe
    c.execute("""
        INSERT INTO processes (id, ip, type, name, dept, factory, hogi, asset_id, deploy_date)
        SELECT id, ip, type, name, dept, factory, hogi, asset_id, deploy_date
        FROM processes_old
    """)
    
    # 4. Verify count
    old_count = c.execute("SELECT count(*) FROM processes_old").fetchone()[0]
    new_count = c.execute("SELECT count(*) FROM processes").fetchone()[0]
    
    if old_count == new_count:
        print(f"Data migration successful. Row count: {new_count}")
        # 5. Drop old table
        c.execute("DROP TABLE processes_old")
        conn.commit()
    else:
        print(f"CRITICAL ERROR: Row count mismatch (Old: {old_count}, New: {new_count}). Rolling back.")
        conn.rollback()
        
    conn.close()

if __name__ == "__main__":
    migrate_processes_schema()
