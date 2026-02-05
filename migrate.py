import sqlite3
import psycopg2

# ---------- SQLITE ----------
SQLITE_DB = "caixa.db"
sqlite_conn = sqlite3.connect(SQLITE_DB)
sqlite_cursor = sqlite_conn.cursor()

# ---------- POSTGRES ----------
pg_conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="caixa",
    user="pdv",
    password="pdv123"
)
pg_cursor = pg_conn.cursor()

# ---------- MIGRAR VENDAS ----------
sqlite_cursor.execute("SELECT produto, valor, pagamento, nota_dada, troco, data FROM vendas")
vendas = sqlite_cursor.fetchall()

for v in vendas:
    pg_cursor.execute("""
        INSERT INTO vendas (produto, valor, pagamento, nota_dada, troco, data)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, v)

# ---------- MIGRAR GASTOS ----------
sqlite_cursor.execute("SELECT descricao, valor, data FROM gastos")
gastos = sqlite_cursor.fetchall()

for g in gastos:
    pg_cursor.execute("""
        INSERT INTO gastos (descricao, valor, data)
        VALUES (%s, %s, %s)
    """, g)

pg_conn.commit()

sqlite_conn.close()
pg_conn.close()

print("✅ Migração concluída com sucesso")
