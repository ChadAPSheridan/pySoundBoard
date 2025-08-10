import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'soundboard.db')

class SoundboardDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.create_tables()

    def create_tables(self):
        cur = self.conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS configurations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            last_used INTEGER DEFAULT 0
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id INTEGER,
            label TEXT,
            audio_path TEXT,
            row INTEGER,
            col INTEGER,
            FOREIGN KEY(config_id) REFERENCES configurations(id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        self.conn.commit()

    def get_setting(self, key):
        cur = self.conn.cursor()
        cur.execute('SELECT value FROM settings WHERE key=?', (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def set_setting(self, key, value):
        cur = self.conn.cursor()
        cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        self.conn.commit()

    def get_last_used_config(self):
        cur = self.conn.cursor()
        cur.execute('SELECT id, name FROM configurations WHERE last_used=1 LIMIT 1')
        return cur.fetchone()

    def set_last_used_config(self, config_id):
        cur = self.conn.cursor()
        cur.execute('UPDATE configurations SET last_used=0')
        cur.execute('UPDATE configurations SET last_used=1 WHERE id=?', (config_id,))
        self.conn.commit()

    def get_config_buttons(self, config_id):
        cur = self.conn.cursor()
        cur.execute('SELECT label, audio_path, row, col FROM buttons WHERE config_id=?', (config_id,))
        return cur.fetchall()

    def save_config(self, name, buttons, rows, cols):
        cur = self.conn.cursor()
        cur.execute('INSERT OR IGNORE INTO configurations (name) VALUES (?)', (name,))
        cur.execute('SELECT id FROM configurations WHERE name=?', (name,))
        config_id = cur.fetchone()[0]
        cur.execute('DELETE FROM buttons WHERE config_id=?', (config_id,))
        for btn in buttons:
            cur.execute('INSERT INTO buttons (config_id, label, audio_path, row, col) VALUES (?, ?, ?, ?, ?)',
                        (config_id, btn['label'], btn['audio_path'], btn['row'], btn['col']))
        self.conn.commit()
        return config_id

    def get_all_configs(self):
        cur = self.conn.cursor()
        cur.execute('SELECT id, name FROM configurations')
        return cur.fetchall()
