import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "missions.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_all_missions():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, title, description FROM missions").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
