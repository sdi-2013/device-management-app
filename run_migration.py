import os
import subprocess
import sys

def refactor_code():
    print("PostgreSQL 호환성을 위해 코드 리팩토링 중...")
    files_to_update = ['modules/auth.py', 'modules/services.py']
    
    for filepath in files_to_update:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # SQLite의 파라미터 바인딩(?)을 PostgreSQL(%s)로 변경
        content = content.replace('?', '%s')
        
        # psycopg2에서는 conn.execute가 없으므로 conn.cursor().execute로 변경
        content = content.replace('conn.execute(', 'conn.cursor().execute(')
        
        # executemany 처리 (Batch Update)
        content = content.replace('c.executemany(', 'from psycopg2.extras import execute_batch\n            execute_batch(c, ')
        # execute_batch(c, query, params)
        # c.executemany("UPDATE...", updates) -> execute_batch(c, "UPDATE...", updates)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            
    print("코드 리팩토링 완료.")

def run_migration():
    print("데이터베이스 마이그레이션 스크립트 실행 중...")
    try:
        import migrate_to_postgres
        migrate_to_postgres.main()
    except Exception as e:
        print(f"마이그레이션 실패: {e}")

if __name__ == "__main__":
    refactor_code()
    run_migration()
    print("========================================")
    print("✅ 모든 마이그레이션 작업이 완료되었습니다!")
    print("앱을 다시 실행해서 확인해 보세요.")
