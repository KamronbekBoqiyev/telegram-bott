import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("files.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    code TEXT PRIMARY KEY,
    user_id INTEGER,
    file_id TEXT,
    file_type TEXT,
    format TEXT,
    caption TEXT,
    views INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

def save_file(code, user_id, file_id, file_type, format, caption):
    cur.execute("INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (code, user_id, file_id, file_type, format, caption, datetime.now()))
    conn.commit()

def get_file(code):
    cur.execute("SELECT * FROM files WHERE code = ?", (code,))
    return cur.fetchone()

def increment_views(code):
    cur.execute("UPDATE files SET views = views + 1 WHERE code = ?", (code,))
    conn.commit()

def delete_old_files():
    cur.execute("DELETE FROM files WHERE created_at < ?", (datetime.now() - timedelta(hours=24),))
    conn.commit()
