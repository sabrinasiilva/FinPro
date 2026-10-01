import os
import sys
import tempfile

import pytest

# Banco temporário e sem conta demo. Precisa ser definido antes de importar o app.
_pasta = tempfile.mkdtemp()
os.environ['DATABASE_PATH'] = os.path.join(_pasta, 'teste.db')
os.environ['FINPRO_DEMO'] = '0'
os.environ['SECRET_KEY'] = 'chave-de-teste'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as finpro  # noqa: E402


@pytest.fixture
def app():
    """App com o banco zerado a cada teste."""
    caminho = finpro.app.config['DATABASE']
    if os.path.exists(caminho):
        os.remove(caminho)
    finpro.init_db()
    finpro.app.config['TESTING'] = True
    return finpro.app


@pytest.fixture
def client(app):
    return app.test_client()
