import sqlite3
import os

DB_PATH = "fintech.db"

def fix_database():
    if not os.path.exists(DB_PATH):
        print(f"Banco de dados {DB_PATH} não encontrado.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print(f"Verificando esquema em {DB_PATH}...")

        # 1. Verificar tabela transacoes_pix
        cursor.execute("PRAGMA table_info(transacoes_pix)")
        columns = [info[1] for info in cursor.fetchall()]

        if 'user_id' not in columns:
            print("Coluna 'user_id' ausente em 'transacoes_pix'. Adicionando...")
            cursor.execute("ALTER TABLE transacoes_pix ADD COLUMN user_id VARCHAR(36)")
            conn.commit()
            print("Coluna 'user_id' adicionada com sucesso.")
        else:
            print("Coluna 'user_id' já existe em 'transacoes_pix'.")

        # 2. Verificar se há outras tabelas críticas (opcional, foco no erro reportado)

    except Exception as e:
        print(f"Erro ao atualizar banco de dados: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database()
