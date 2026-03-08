import sqlite3
import os

DB_PATH = "fintech.db"

def fix_schema():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if transacoes_pix table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transacoes_pix'")
        if not cursor.fetchone():
            print("Table transacoes_pix does not exist.")
            return

        # Get columns
        cursor.execute("PRAGMA table_info(transacoes_pix)")
        columns = [info[1] for info in cursor.fetchall()]

        print(f"Current columns in transacoes_pix: {columns}")

        if "tipo" not in columns:
            print("Adding missing column 'tipo' to transacoes_pix...")
            # SQLite does not support adding specific position or complex constraints easily on ADD COLUMN,
            # but usually VARCHAR DEFAULT is fine.
            # Using 'ENVIADO' as default match TransactionType.SENT
            cursor.execute("ALTER TABLE transacoes_pix ADD COLUMN tipo VARCHAR(20) DEFAULT 'ENVIADO' NOT NULL")
            print("Column 'tipo' added successfully.")
        else:
            print("Column 'tipo' already exists.")

    except Exception as e:
        print(f"Error updating schema: {e}")
        conn.rollback()
    else:
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_schema()
