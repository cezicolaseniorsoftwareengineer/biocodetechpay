import sqlite3
import os

DB_PATH = "fintech.db"

def check_users():
    if not os.path.exists(DB_PATH):
        print("ALERTA: O arquivo fintech.db não foi encontrado na raiz.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check users table
        cursor.execute("SELECT count(*) FROM users")
        count = cursor.fetchone()[0]

        print(f"STATUS DO BANCO DE DADOS:")
        print(f"- Arquivo: {os.path.abspath(DB_PATH)}")
        print(f"- Total de usuários ativos: {count}")

        if count > 0:
            print("\nUsuários encontrados (amostra):")
            cursor.execute("SELECT email, full_name FROM users LIMIT 5")
            for row in cursor.fetchall():
                print(f"  - {row[1]} ({row[0]})")

        conn.close()
    except Exception as e:
        print(f"Erro ao ler o banco: {e}")

if __name__ == "__main__":
    check_users()
