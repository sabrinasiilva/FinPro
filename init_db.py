import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()

# Criar tabela usuarios
c.execute('''
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL
)
''')

# Recriar tabelas receitas e despesas com coluna user_id
c.execute('DROP TABLE IF EXISTS receitas')
c.execute('DROP TABLE IF EXISTS despesas')

c.execute('''
CREATE TABLE receitas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL NOT NULL,
    categoria TEXT,
    descricao TEXT,
    data TEXT DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES usuarios(id)
)
''')

c.execute('''
CREATE TABLE despesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL NOT NULL,
    categoria TEXT,
    descricao TEXT,
    data TEXT DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES usuarios(id)
)
''')
c.execute('''
CREATE TABLE IF NOT EXISTS investimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    ativo TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    valor_unitario REAL NOT NULL,
    data_compra TEXT NOT NULL,
    valor_atual REAL NOT NULL,
    descricao TEXT,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES usuarios(id)
)
''')
conn.commit()
conn.close()

print("Banco atualizado com investimento!")
