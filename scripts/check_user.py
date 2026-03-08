import sqlite3
import sys

def check_user(cpf_cnpj):
    try:
        conn = sqlite3.connect("fintech.db")
        cursor = conn.cursor()

        print(f"Checking database: fintech.db")

        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if not cursor.fetchone():
            print("Table 'users' does not exist!")
            return

        cursor.execute("SELECT id, name, cpf_cnpj, email FROM users WHERE cpf_cnpj = ?", (cpf_cnpj,))
        user = cursor.fetchone()

        if user:
            print(f"User Found: ID={user[0]}, Name={user[1]}, CPF={user[2]}, Email={user[3]}")
        else:
            print(f"User with CPF {cpf_cnpj} NOT FOUND in fintech.db")

            # List all users
            print("\nList of all users in DB:")
            cursor.execute("SELECT cpf_cnpj, name FROM users")
            rows = cursor.fetchall()
            for row in rows:
                print(f" - {row[0]}: {row[1]}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_user("61.425.124/0001-03")
