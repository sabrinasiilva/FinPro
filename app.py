from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import os
import secrets
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
from functools import wraps
import pandas as pd
from io import BytesIO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
# Em produção a chave vem da variável de ambiente SECRET_KEY (configurada no Render)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['DATABASE'] = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'database.db'))
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

MESES = [
    ('01', 'Janeiro'), ('02', 'Fevereiro'), ('03', 'Março'), ('04', 'Abril'),
    ('05', 'Maio'), ('06', 'Junho'), ('07', 'Julho'), ('08', 'Agosto'),
    ('09', 'Setembro'), ('10', 'Outubro'), ('11', 'Novembro'), ('12', 'Dezembro'),
]
MESES_ABREV = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']

# Conta aberta para quem quiser testar o app sem se cadastrar
DEMO_USUARIO = 'demo'
DEMO_SENHA = 'demo123'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receitas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL NOT NULL,
    categoria TEXT,
    descricao TEXT,
    data TEXT DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS despesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL NOT NULL,
    categoria TEXT,
    descricao TEXT,
    data TEXT DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES usuarios(id)
);

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
);
'''

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Cria as tabelas que ainda não existem. Não apaga nenhum dado."""
    conn = get_db_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ---------------------------
# Conta demo
# ---------------------------
def mes_relativo(meses_atras):
    """Retorna (ano, mes) de N meses atrás a partir de hoje."""
    hoje = date.today()
    total = hoje.year * 12 + (hoje.month - 1) - meses_atras
    return total // 12, total % 12 + 1

def criar_conta_demo():
    """Cria a conta demo com lançamentos dos últimos 6 meses. Se ela já existe, não faz nada."""
    conn = get_db_connection()
    if conn.execute('SELECT 1 FROM usuarios WHERE username = ?', (DEMO_USUARIO,)).fetchone():
        conn.close()
        return

    try:
        cursor = conn.execute(
            'INSERT INTO usuarios (username, senha_hash) VALUES (?, ?)',
            (DEMO_USUARIO, generate_password_hash(DEMO_SENHA))
        )
    except sqlite3.IntegrityError:
        # outro processo do servidor criou a conta ao mesmo tempo
        conn.close()
        return
    user_id = cursor.lastrowid

    hoje = date.today()
    receitas = []
    despesas = []
    for meses_atras in range(5, -1, -1):
        ano, mes = mes_relativo(meses_atras)

        def dia(d):
            # no mês atual, nada é lançado depois de hoje
            if (ano, mes) == (hoje.year, hoje.month):
                d = min(d, hoje.day)
            return date(ano, mes, d).isoformat()

        receitas.append((4500.00, 'Salário', 'Salário mensal', dia(5)))
        if meses_atras % 2 == 0:
            receitas.append((850.00, 'Freelance', 'Site para cliente', dia(18)))

        despesas += [
            (1500.00, 'Moradia', 'Aluguel', dia(10)),
            (620.00 + meses_atras * 35, 'Mercado', 'Compras do mês', dia(12)),
            (180.00, 'Transporte', 'Bilhete único', dia(3)),
            (99.90, 'Contas', 'Internet', dia(15)),
            (210.00 + meses_atras * 20, 'Lazer', 'Cinema e restaurantes', dia(22)),
        ]

    conn.executemany(
        'INSERT INTO receitas (valor, categoria, descricao, data, user_id) VALUES (?, ?, ?, ?, ?)',
        [r + (user_id,) for r in receitas]
    )
    conn.executemany(
        'INSERT INTO despesas (valor, categoria, descricao, data, user_id) VALUES (?, ?, ?, ?, ?)',
        [d + (user_id,) for d in despesas]
    )

    investimentos = [
        ('Tesouro', 'Tesouro Selic 2029', 2, 14850.00, 15240.00, 5, 'Reserva de emergência'),
        ('Ações', 'ITSA4', 100, 9.80, 10.65, 4, 'Foco em dividendos'),
        ('Fundos', 'MXRF11', 150, 10.20, 9.95, 2, 'Renda mensal'),
        ('CDB', 'CDB 110% CDI', 1, 2000.00, 2085.40, 1, 'Liquidez diária'),
    ]
    for tipo, ativo, qtd, unitario, atual, meses_atras, descricao in investimentos:
        ano, mes = mes_relativo(meses_atras)
        conn.execute('''
            INSERT INTO investimentos (user_id, tipo, ativo, quantidade, valor_unitario, valor_atual, data_compra, descricao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, tipo, ativo, qtd, unitario, atual, date(ano, mes, 8).isoformat(), descricao))

    conn.commit()
    conn.close()


# ---------------------------
# Formatação nos templates
# ---------------------------
@app.template_filter('brl')
def formatar_brl(valor):
    """1234.5 -> '1.234,50'"""
    texto = f'{valor or 0:,.2f}'
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')

@app.template_filter('data_br')
def formatar_data(valor):
    """'2025-10-14' -> '14/10/2025'"""
    try:
        return datetime.strptime(str(valor)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return valor

@app.context_processor
def variaveis_dos_templates():
    return {
        'meses_nomes': MESES,
        'demo_ativo': os.environ.get('FINPRO_DEMO', '1') == '1',
        'demo_usuario': DEMO_USUARIO,
        'demo_senha': DEMO_SENHA,
    }


# ---------------------------
# Autenticação
# ---------------------------
def login_obrigatorio(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapper

def voltar(padrao):
    """Volta para a página de onde o formulário veio (mantendo o filtro), ou para a padrão."""
    origem = request.referrer
    if origem and origem.startswith(request.host_url):
        return redirect(origem)
    return redirect(padrao)

@app.route('/')
def inicial_pag():
    return render_template('inicial_pag.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        senha = request.form['senha']
        senha_hash = generate_password_hash(senha)

        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO usuarios (username, senha_hash) VALUES (?, ?)',
                (username, senha_hash)
            )
            conn.commit()
            flash('Usuário registrado com sucesso! Faça login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Nome de usuário já existe.')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        senha = request.form['senha']

        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM usuarios WHERE username = ?', (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user['senha_hash'], senha):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu da conta.')
    return redirect(url_for('login'))


# ---------------------------
# Filtro por período
# ---------------------------
def get_mes_ano_from_request(padrao_mes_atual=True):
    """Retorna (mes, ano) como '01'..'12' e '2025', ou None para "Todos".

    Sem nenhum filtro na URL, usa o mês atual (ou tudo, se padrao_mes_atual=False).
    """
    mes = request.args.get('mes')
    ano = request.args.get('ano')

    if mes is None and ano is None:
        if not padrao_mes_atual:
            return None, None
        hoje = date.today()
        return hoje.strftime('%m'), hoje.strftime('%Y')

    # string vazia ("Todos") ou valor inválido vira None
    mes = mes if mes in dict(MESES) else None
    ano = ano if ano and ano.isdigit() and len(ano) == 4 else None
    return mes, ano

def filtro_periodo(user_id, mes, ano, coluna='data'):
    """Monta o WHERE com o usuário e o período. `coluna` é sempre um nome fixo do código."""
    where = 'user_id = ?'
    params = [user_id]
    if mes:
        where += f" AND strftime('%m', {coluna}) = ?"
        params.append(mes)
    if ano:
        where += f" AND strftime('%Y', {coluna}) = ?"
        params.append(ano)
    return where, params

def gerar_lista_anos(user_id):
    """Anos que têm lançamentos do usuário, mais o ano atual, do mais recente pro mais antigo."""
    conn = get_db_connection()
    linhas = conn.execute('''
        SELECT strftime('%Y', data) AS ano FROM receitas WHERE user_id = ?
        UNION
        SELECT strftime('%Y', data) FROM despesas WHERE user_id = ?
        UNION
        SELECT strftime('%Y', data_compra) FROM investimentos WHERE user_id = ?
    ''', (user_id, user_id, user_id)).fetchall()
    conn.close()
    anos = {linha['ano'] for linha in linhas if linha['ano']}
    anos.add(str(date.today().year))
    return sorted(anos, reverse=True)


# ---------------------------
# DASHBOARD (index)
# ---------------------------
@app.route('/dashboard')
@login_obrigatorio
def index():
    user_id = session['user_id']
    mes, ano = get_mes_ano_from_request()
    where, params = filtro_periodo(user_id, mes, ano)

    conn = get_db_connection()

    total_receitas = conn.execute(
        f'SELECT IFNULL(SUM(valor), 0) FROM receitas WHERE {where}', params
    ).fetchone()[0]
    total_despesas = conn.execute(
        f'SELECT IFNULL(SUM(valor), 0) FROM despesas WHERE {where}', params
    ).fetchone()[0]
    saldo = total_receitas - total_despesas

    # Evolução mês a mês dentro do ano escolhido (ou somando todos os anos, se "Todos")
    where_ano, params_ano = filtro_periodo(user_id, None, ano)
    por_mes = {}
    for tabela in ('receitas', 'despesas'):
        linhas = conn.execute(f'''
            SELECT strftime('%m', data) AS mes, SUM(valor) AS total
            FROM {tabela} WHERE {where_ano}
            GROUP BY mes
        ''', params_ano).fetchall()
        for linha in linhas:
            if linha['mes']:
                por_mes.setdefault(linha['mes'], {'receitas': 0, 'despesas': 0})[tabela] = linha['total']

    meses_nums = sorted(por_mes)
    meses = [MESES_ABREV[int(m) - 1] for m in meses_nums]
    valores_receitas = [round(por_mes[m]['receitas'], 2) for m in meses_nums]
    valores_despesas = [round(por_mes[m]['despesas'], 2) for m in meses_nums]

    transactions = conn.execute(f'''
        SELECT data, descricao, categoria, valor, 'Receita' AS tipo FROM receitas WHERE {where}
        UNION ALL
        SELECT data, descricao, categoria, valor, 'Despesa' AS tipo FROM despesas WHERE {where}
        ORDER BY data DESC LIMIT 10
    ''', params + params).fetchall()

    despesas_por_categoria = conn.execute(f'''
        SELECT categoria, SUM(valor) AS total
        FROM despesas WHERE {where}
        GROUP BY categoria
        ORDER BY total DESC
    ''', params).fetchall()

    conn.close()

    return render_template(
        'index.html',
        saldo=saldo,
        total_receitas=total_receitas,
        total_despesas=total_despesas,
        transactions=transactions,
        meses=meses,
        valores_receitas=valores_receitas,
        valores_despesas=valores_despesas,
        categorias=[linha['categoria'] for linha in despesas_por_categoria],
        valores_categorias=[round(linha['total'], 2) for linha in despesas_por_categoria],
        mes=mes,
        ano=ano,
        anos=gerar_lista_anos(user_id)
    )


# ---------------------------
# RECEITAS e DESPESAS (mesma estrutura, tabelas diferentes)
# ---------------------------
def ler_lancamento(form):
    """Lê os campos de uma receita/despesa. Retorna None se o valor ou a data forem inválidos."""
    try:
        valor = float(form['valor'].replace(',', '.'))
        data = datetime.strptime(form['data'], '%Y-%m-%d').date().isoformat()
    except (KeyError, ValueError):
        return None
    if valor <= 0:
        return None
    return {
        'valor': valor,
        'categoria': form.get('categoria', '').strip(),
        'descricao': form.get('descricao', '').strip(),
        'data': data,
    }

def listar_lancamentos(tabela, user_id, mes, ano):
    where, params = filtro_periodo(user_id, mes, ano)
    conn = get_db_connection()
    itens = conn.execute(f'SELECT * FROM {tabela} WHERE {where} ORDER BY data DESC', params).fetchall()
    total = conn.execute(f'SELECT IFNULL(SUM(valor), 0) FROM {tabela} WHERE {where}', params).fetchone()[0]
    conn.close()
    return itens, total

def inserir_lancamento(tabela, user_id, lancamento):
    conn = get_db_connection()
    conn.execute(
        f'INSERT INTO {tabela} (valor, categoria, descricao, data, user_id) VALUES (?, ?, ?, ?, ?)',
        (lancamento['valor'], lancamento['categoria'], lancamento['descricao'], lancamento['data'], user_id)
    )
    conn.commit()
    conn.close()

def atualizar_lancamento(tabela, user_id, id, lancamento):
    conn = get_db_connection()
    conn.execute(
        f'UPDATE {tabela} SET valor = ?, categoria = ?, descricao = ?, data = ? WHERE id = ? AND user_id = ?',
        (lancamento['valor'], lancamento['categoria'], lancamento['descricao'], lancamento['data'], id, user_id)
    )
    conn.commit()
    conn.close()

def excluir_lancamento(tabela, user_id, id):
    conn = get_db_connection()
    conn.execute(f'DELETE FROM {tabela} WHERE id = ? AND user_id = ?', (id, user_id))
    conn.commit()
    conn.close()

@app.route('/receitas', methods=['GET', 'POST'])
@login_obrigatorio
def gerenciar_receitas():
    user_id = session['user_id']

    if request.method == 'POST':
        lancamento = ler_lancamento(request.form)
        if lancamento:
            inserir_lancamento('receitas', user_id, lancamento)
            flash('Receita adicionada.')
        else:
            flash('Confira o valor e a data da receita.')
        return redirect(url_for('gerenciar_receitas', **request.args))

    mes, ano = get_mes_ano_from_request()
    receitas, total_receitas = listar_lancamentos('receitas', user_id, mes, ano)
    return render_template('receita.html', receitas=receitas, total_receitas=total_receitas,
                           mes=mes, ano=ano, anos=gerar_lista_anos(user_id))

@app.route('/receita/update', methods=['POST'])
@login_obrigatorio
def update_receita():
    lancamento = ler_lancamento(request.form)
    if lancamento and request.form.get('id', '').isdigit():
        atualizar_lancamento('receitas', session['user_id'], int(request.form['id']), lancamento)
        flash('Receita atualizada.')
    else:
        flash('Confira o valor e a data da receita.')
    return voltar(url_for('gerenciar_receitas'))

@app.route('/receita/delete/<int:id>', methods=['POST'])
@login_obrigatorio
def delete_receita(id):
    excluir_lancamento('receitas', session['user_id'], id)
    flash('Receita excluída.')
    return voltar(url_for('gerenciar_receitas'))

@app.route('/despesas', methods=['GET', 'POST'])
@login_obrigatorio
def gerenciar_despesas():
    user_id = session['user_id']

    if request.method == 'POST':
        lancamento = ler_lancamento(request.form)
        if lancamento:
            inserir_lancamento('despesas', user_id, lancamento)
            flash('Despesa adicionada.')
        else:
            flash('Confira o valor e a data da despesa.')
        return redirect(url_for('gerenciar_despesas', **request.args))

    mes, ano = get_mes_ano_from_request()
    despesas, total_despesas = listar_lancamentos('despesas', user_id, mes, ano)
    return render_template('despesa.html', despesas=despesas, total_despesas=total_despesas,
                           mes=mes, ano=ano, anos=gerar_lista_anos(user_id))

@app.route('/despesa/update', methods=['POST'])
@login_obrigatorio
def update_despesa():
    lancamento = ler_lancamento(request.form)
    if lancamento and request.form.get('id', '').isdigit():
        atualizar_lancamento('despesas', session['user_id'], int(request.form['id']), lancamento)
        flash('Despesa atualizada.')
    else:
        flash('Confira o valor e a data da despesa.')
    return voltar(url_for('gerenciar_despesas'))

@app.route('/despesa/delete/<int:id>', methods=['POST'])
@login_obrigatorio
def delete_despesa(id):
    excluir_lancamento('despesas', session['user_id'], id)
    flash('Despesa excluída.')
    return voltar(url_for('gerenciar_despesas'))


# ---------------------------
# INVESTIMENTOS
# ---------------------------
def ler_investimento(form):
    """Lê os campos de um investimento. Retorna None se algum número ou a data forem inválidos."""
    try:
        investimento = {
            'tipo': form['tipo'].strip(),
            'ativo': form['ativo'].strip(),
            'quantidade': int(form['quantidade']),
            'valor_unitario': float(form['valor_unitario'].replace(',', '.')),
            'valor_atual': float(form['valor_atual'].replace(',', '.')),
            'data_compra': datetime.strptime(form['data_compra'], '%Y-%m-%d').date().isoformat(),
            'descricao': form.get('descricao', '').strip(),
        }
    except (KeyError, ValueError):
        return None
    if not investimento['tipo'] or not investimento['ativo']:
        return None
    if investimento['quantidade'] <= 0 or investimento['valor_unitario'] <= 0 or investimento['valor_atual'] < 0:
        return None
    return investimento

@app.route('/investimentos', methods=['GET', 'POST'])
@login_obrigatorio
def gerenciar_investimentos():
    user_id = session['user_id']

    if request.method == 'POST':
        investimento = ler_investimento(request.form)
        if investimento:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO investimentos (user_id, tipo, ativo, quantidade, valor_unitario, valor_atual, data_compra, descricao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, investimento['tipo'], investimento['ativo'], investimento['quantidade'],
                  investimento['valor_unitario'], investimento['valor_atual'],
                  investimento['data_compra'], investimento['descricao']))
            conn.commit()
            conn.close()
            flash('Investimento adicionado.')
        else:
            flash('Confira os números e a data do investimento.')
        return redirect(url_for('gerenciar_investimentos', **request.args))

    # Aqui o padrão é mostrar a carteira inteira, não só o que foi comprado no mês
    mes, ano = get_mes_ano_from_request(padrao_mes_atual=False)
    where, params = filtro_periodo(user_id, mes, ano, coluna='data_compra')

    conn = get_db_connection()
    investimentos = conn.execute(
        f'SELECT * FROM investimentos WHERE {where} ORDER BY data_compra DESC', params
    ).fetchall()
    conn.close()

    total_investido = sum(i['quantidade'] * i['valor_unitario'] for i in investimentos)
    valor_atual_total = sum(i['quantidade'] * i['valor_atual'] for i in investimentos)
    rentabilidade = ((valor_atual_total - total_investido) / total_investido * 100) if total_investido > 0 else 0

    tipos_dict = {}
    for i in investimentos:
        tipos_dict[i['tipo']] = tipos_dict.get(i['tipo'], 0) + i['quantidade'] * i['valor_unitario']

    ativos = []
    valores_rent = []
    for i in investimentos:
        investido = i['quantidade'] * i['valor_unitario']
        atual = i['quantidade'] * i['valor_atual']
        ativos.append(i['ativo'])
        valores_rent.append(round((atual - investido) / investido * 100, 2) if investido > 0 else 0)

    return render_template(
        'investimentos.html',
        investimentos=investimentos,
        total_investido=total_investido,
        valor_atual=valor_atual_total,
        rentabilidade=round(rentabilidade, 2),
        tipos=list(tipos_dict.keys()),
        valores_tipo=[round(v, 2) for v in tipos_dict.values()],
        ativos=ativos,
        valores_rent=valores_rent,
        mes=mes,
        ano=ano,
        anos=gerar_lista_anos(user_id)
    )

@app.route('/investimentos/editar/<int:id>', methods=['POST'])
@login_obrigatorio
def edit_investimento(id):
    investimento = ler_investimento(request.form)
    if not investimento:
        flash('Confira os números e a data do investimento.')
        return voltar(url_for('gerenciar_investimentos'))

    conn = get_db_connection()
    conn.execute('''
        UPDATE investimentos SET tipo = ?, ativo = ?, quantidade = ?, valor_unitario = ?, valor_atual = ?, data_compra = ?, descricao = ?
        WHERE id = ? AND user_id = ?
    ''', (investimento['tipo'], investimento['ativo'], investimento['quantidade'], investimento['valor_unitario'],
          investimento['valor_atual'], investimento['data_compra'], investimento['descricao'], id, session['user_id']))
    conn.commit()
    conn.close()

    flash('Investimento atualizado.')
    return voltar(url_for('gerenciar_investimentos'))

@app.route('/delete_investimento/<int:id>', methods=['POST'])
@login_obrigatorio
def delete_investimento(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM investimentos WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Investimento excluído.')
    return voltar(url_for('gerenciar_investimentos'))


# ---------------------------
# Relatório Excel
# ---------------------------
@app.route('/gerar_relatorio')
@login_obrigatorio
def gerar_relatorio():
    user_id = session['user_id']
    conn = get_db_connection()

    receitas = pd.read_sql_query(
        'SELECT data, descricao, categoria, valor FROM receitas WHERE user_id = ? ORDER BY data DESC',
        conn, params=(user_id,)
    )
    despesas = pd.read_sql_query(
        'SELECT data, descricao, categoria, valor FROM despesas WHERE user_id = ? ORDER BY data DESC',
        conn, params=(user_id,)
    )
    investimentos = pd.read_sql_query(
        'SELECT tipo, ativo, quantidade, valor_unitario, valor_atual, data_compra, descricao FROM investimentos WHERE user_id = ?',
        conn, params=(user_id,)
    )
    conn.close()

    # Arquivo Excel em memória, uma aba por tipo de lançamento
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        receitas.to_excel(writer, index=False, sheet_name='Receitas')
        despesas.to_excel(writer, index=False, sheet_name='Despesas')
        investimentos.to_excel(writer, index=False, sheet_name='Investimentos')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='relatorio_financeiro.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# Garante que o banco existe sempre que o app sobe (local ou no Render)
init_db()
if os.environ.get('FINPRO_DEMO', '1') == '1':
    criar_conta_demo()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
