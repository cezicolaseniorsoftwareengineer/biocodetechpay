import sqlite3
import os

DB_PATH = "fintech.db"

def inspect():
    if not os.path.exists(DB_PATH):
        print("DB doesn't exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n--- TRANSACOES_PIX COLUMNS ---")
    try:
        cursor.execute("PRAGMA table_info(transacoes_pix)")
        cols = cursor.fetchall()
        for c in cols:
            print(c) # cid, name, type, notnull, dflt_value, pk
    except Exception as e:
        print(f"Error: {e}")
    conn.close()

if __name__ == "__main__":
    inspect()
