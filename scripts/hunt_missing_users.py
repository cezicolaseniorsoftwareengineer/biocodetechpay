import sqlite3
import os

DB_FILES = ["fintech.db", "fintech_v2.db", "fintech_v3.db", "fintech_v4.db"]

def hunt_users():
    for db_file in DB_FILES:
        if not os.path.exists(db_file):
            continue

        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            print(f"\n--- Checking {db_file} ---")

            try:
                cursor.execute("SELECT name, email, cpf_cnpj FROM users")
                users = cursor.fetchall()
                if not users:
                    print("  No users found.")
                for u in users:
                    print(f"  FOUND: {u[0]} | {u[1]} | {u[2]}")
            except sqlite3.OperationalError:
                print("  Table 'users' not found or error reading.")

            conn.close()
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    hunt_users()
