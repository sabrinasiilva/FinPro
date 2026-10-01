# Cria as tabelas do banco sem apagar dados.
# O app já faz isso sozinho ao iniciar; este script é só um atalho para rodar à mão.
from app import init_db

init_db()
print("Banco pronto!")
