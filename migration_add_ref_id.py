import sqlite3

db_path = "c:\\Users\\justi\\DeviceManagementApp\\device_management.db"

def migrate():
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Check if column exists
        c.execute("PRAGMA table_info(common_codes)")
        columns = [row[1] for row in c.fetchall()]
        
        if 'ref_id' not in columns:
            print("Adding ref_id column to common_codes...")
            c.execute("ALTER TABLE common_codes ADD COLUMN ref_id TEXT")
            conn.commit()
            print("Column added successfully.")
        else:
            print("Column ref_id already exists.")
            
        conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
