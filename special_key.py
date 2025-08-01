import sqlite3

DB_PATH = 'ttsapp.db'

with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()

    # Check if 'special_key' column exists
    cursor.execute("PRAGMA table_info(tb_users);")
    columns = [col[1] for col in cursor.fetchall()]

    if 'special_key' not in columns:
        cursor.execute("ALTER TABLE tb_users ADD COLUMN special_key TEXT DEFAULT '';")
        cursor.execute("ALTER TABLE tb_users ADD COLUMN last_credit_date TEXT DEFAULT '';")
        conn.commit()
        print("✅ 'special_key' and 'last_credit_date' columns added successfully.")
    else:
        print("ℹ️ Columns already exist. No changes made.")
