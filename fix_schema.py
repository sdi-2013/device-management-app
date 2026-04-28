import sqlite3

def fix_schema():
    conn = sqlite3.connect('device_management.db')
    c = conn.cursor()
    
    # Check if action_type exists
    c.execute("PRAGMA table_info(movement_logs)")
    columns = [row[1] for row in c.fetchall()]
    
    if 'action_type' not in columns:
        print("Adding action_type column...")
        c.execute("ALTER TABLE movement_logs ADD COLUMN action_type TEXT")
    else:
        print("action_type column already exists.")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    fix_schema()
