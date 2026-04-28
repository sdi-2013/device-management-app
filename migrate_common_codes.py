import sqlite3
import pandas as pd
from modules.database import get_connection, init_db
import uuid

def migrate():
    print("Running Common Codes Migration...")
    
    # Ensure schema is updated
    init_db()
    
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Seed Initial Common Codes
    # Scan existing assets to find Types, Makers, OS
    print("Scanning existing assets for initial codes...")
    assets = pd.read_sql("SELECT * FROM assets", conn)
    
    common_data = []

    # Helper to add code
    def add_code(group, code_name, code_id=None):
        if not code_name or pd.isna(code_name): return
        normalized_name = str(code_name).strip()
        if not normalized_name: return
        
        cid = code_id if code_id else normalized_name
        common_data.append({
            'group_code': group,
            'code_id': cid,
            'code_name': normalized_name,
            'sort_order': 0,
            'is_active': 1
        })

    # Asset Types
    if not assets.empty:
        for val in assets['type'].unique():
            add_code('ASSET_TYPE', val)
            
        for val in assets['maker'].unique():
            add_code('MAKER', val)

        for val in assets['os'].unique():
            add_code('OS', val)
            
    # Default Asset Status (Fixed list)
    statuses = ['비치된', '투입중', '수리중', '대기중', '폐기']
    for idx, s in enumerate(statuses):
        common_data.append({
            'group_code': 'ASSET_STATUS',
            'code_id': s,
            'code_name': s,
            'sort_order': idx,
            'is_active': 1
        })
        
    # Action Types (For Inspection)
    actions = ['단순 점검 (이력 저장)', '부품 교체', '수리', '데이터 수정', '장비 교체 (반출 및 대기장비 투입)', '수리 완료 (입고)', '폐기']
    for idx, a in enumerate(actions):
         common_data.append({
            'group_code': 'ACTION_TYPE',
            'code_id': a,
            'code_name': a,
            'sort_order': idx,
            'is_active': 1
        })

    # Device Type -> Failure Code Mapping
    # Logic: Existing failure codes need a device type. 
    # For now, assign them to 'ALL' (or create an 'ALL' type code)
    # Or if users want separate lists, we duplicate them?
    # Strategy: Assign existing to 'COMMON' ( 공통 )
    
    add_code('ASSET_TYPE', '공통', 'COMMON')
    
    # Insert Common Codes (Ignore duplicates)
    count = 0
    for row in common_data:
        try:
            c.execute("INSERT OR IGNORE INTO common_codes (group_code, code_id, code_name, sort_order, is_active) VALUES (?, ?, ?, ?, ?)",
                      (row['group_code'], row['code_id'], row['code_name'], row['sort_order'], row['is_active']))
            count += 1
        except Exception as e:
            print(f"Error inserting {row}: {e}")
            
    print(f"Seeded {count} common codes.")
    
    # 2. Update existing Failure Codes to have 'COMMON' device_type if NULL
    c.execute("UPDATE failure_codes SET device_type = 'COMMON' WHERE device_type IS NULL OR device_type = ''")
    
    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
