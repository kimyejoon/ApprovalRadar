import sqlite3
import json
import os

DB_FILE = "food_safety.db"

def migrate():
    print("Starting database migration...")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Create a backup just in case
    import shutil
    shutil.copy2(DB_FILE, DB_FILE + ".bak")
    print("Backup created as food_safety.db.bak")
    
    # 2. Create the new table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS businesses_new (
            license_no TEXT PRIMARY KEY,
            business_name TEXT,
            address TEXT,
            representative_name TEXT,
            business_status TEXT,
            license_date TEXT,
            phone_number TEXT,
            last_event_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_new INTEGER DEFAULT 1,
            update_type TEXT,
            prev_business_status TEXT,
            prev_representative_name TEXT,
            prev_business_name TEXT
        )
    ''')
    
    # 3. Read existing data and insert into new table
    cursor.execute("SELECT * FROM businesses")
    rows = cursor.fetchall()
    
    for row in rows:
        record = dict(row)
        
        # Parse JSON
        try:
            lic_history = json.loads(record.get('licensing_history', '[]'))
        except:
            lic_history = []
            
        try:
            rep_history = json.loads(record.get('representative_history', '[]'))
        except:
            rep_history = []
            
        update_type = None
        prev_business_status = None
        prev_representative_name = None
        prev_business_name = None
        
        # Extract latest representative change
        if rep_history and isinstance(rep_history, list) and len(rep_history) > 0:
            latest_rep = rep_history[-1]
            if isinstance(latest_rep, dict):
                prev_representative_name = latest_rep.get('prev')
                update_type = "대표자변경"
                
        # Extract latest licensing change (overrides update_type if exists since it's more recent usually or we just combine)
        if lic_history and isinstance(lic_history, list) and len(lic_history) > 0:
            latest_lic = lic_history[-1]
            if isinstance(latest_lic, dict):
                update_type = latest_lic.get('type') or update_type
                if update_type == "상태변경":
                    prev_business_status = latest_lic.get('prev')
                elif "명칭변경" in str(update_type) or "상호변경" in str(update_type) or latest_lic.get('type') == '변경민원':
                    prev_business_name = latest_lic.get('prev')
                
        # Insert into new table
        cursor.execute('''
            INSERT INTO businesses_new (
                license_no, business_name, address, representative_name, business_status,
                license_date, phone_number, last_event_date, created_at, updated_at, is_new,
                update_type, prev_business_status, prev_representative_name, prev_business_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record['license_no'], record['business_name'], record['address'], 
            record['representative_name'], record['business_status'],
            record['license_date'], record['phone_number'], record['last_event_date'],
            record['created_at'], record['updated_at'], record['is_new'],
            update_type, prev_business_status, prev_representative_name, prev_business_name
        ))
        
    # 4. Drop old table and rename new table
    cursor.execute("DROP TABLE businesses")
    cursor.execute("ALTER TABLE businesses_new RENAME TO businesses")
    
    # 5. Recreate indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_businesses_last_event_date ON businesses (last_event_date);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_businesses_created_at ON businesses (created_at);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_businesses_business_name ON businesses (business_name);')
    
    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
