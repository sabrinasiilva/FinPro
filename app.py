from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import calendar
import pandas as pd
from io import BytesIO

app = Flask(__name__)
# troque por uma chave forte em produção
app.secret_key = 'chave_nova_sabrina_trocar_em_producao'

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def inicial_pag():
    return render_template('inicial_pag.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
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
        username = request.form['username']
        senha = request.form['senha']

        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM usuarios WHERE username = ?', (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user['senha_hash'], senha):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login efetuado com sucesso!')
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu da conta.')
    return redirect(url_for('inicial_pag'))


# ---------------------------
# Helper: parse month/year from request (default to current)
# ---------------------------
def get_mes_ano_from_request():
    """Retorna (mes, ano) em strings ('01'..'12', '2025'), ou None se 'Todos' foi selecionado."""
    mes = request.args.get('mes')
    ano = request.args.get('ano')

    # Se nenhum foi enviado, por padrão usamos mês e ano atuais
    if mes is None and ano is None:
        hoje = datetime.now()
        mes = hoje.strftime('%m')
        ano = hoje.strftime('%Y')
    # Se um dos dois vier como string vazia (""), interpretamos como 'Todos' -> manter None
    if mes == "":
        mes = None
    if ano == "":
        ano = None

    return mes, ano

def gerar_lista_anos():
    """Retorna lista de anos disponíveis nas tabelas receitas e despesas (strings), ordenada desc."""
    conn = get_db_connection()
    anos_raw = conn.execute("""
        SELECT DISTINCT strftime('%Y', data) as ano FROM receitas
        UNION
        SELECT DISTINCT strftime('%Y', data) FROM despesas
        ORDER BY ano DESC
    """).fetchall()
    conn.close()
    anos = [row['ano'] for row in anos_raw if row['ano']]
    return anos


# ---------------------------
# DASHBOARD (index)
# ---------------------------
@app.route('/dashboard')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Pega filtros (mes, ano). Se o usuário não passou nada, por padrão usamos mês e ano atuais.
    mes, ano = get_mes_ano_from_request()

    conn = get_db_connection()

    # BUILD queries com filtros opcionais
    # Receitas totais (filtradas)
    params_receitas = [user_id]
    where_receitas = "user_id = ?"
    if mes:
        where_receitas += " AND strftime('%m', data) = ?"
        params_receitas.append(mes)
    if ano:
        where_receitas += " AND strftime('%Y', data) = ?"
        params_receitas.append(ano)

    total_receitas = conn.execute(
        f"SELECT IFNULL(SUM(valor), 0) FROM receitas WHERE {where_receitas}",
        tuple(params_receitas)
    ).fetchone()[0]

    # Despesas totais (filtradas)
    params_despesas = [user_id]
    where_despesas = "user_id = ?"
    if mes:
        where_despesas += " AND strftime('%m', data) = ?"
        params_despesas.append(mes)
    if ano:
        where_despesas += " AND strftime('%Y', data) = ?"
        params_despesas.append(ano)

    total_despesas = conn.execute(
        f"SELECT IFNULL(SUM(valor), 0) FROM despesas WHERE {where_despesas}",
        tuple(params_despesas)
    ).fetchone()[0]

    saldo = total_receitas - total_despesas

    # Para os gráficos de evolução por mês: pegamos por mês dentro do ano selecionado (se ano definido)
    receitas_por_mes = []
    despesas_por_mes = []
    meses = []
    valores_receitas = []
    valores_despesas = []

    # Se o ano for None -> podemos pegar últimos meses disponíveis combinados
    if ano:
        receitas_por_mes = conn.execute('''
            SELECT strftime('%m', data) AS mes, SUM(valor) AS total
            FROM receitas
            WHERE user_id = ? AND strftime('%Y', data) = ?
            GROUP BY mes
            ORDER BY mes
        ''', (user_id, ano)).fetchall()

        despesas_por_mes = conn.execute('''
            SELECT strftime('%m', data) AS mes, SUM(valor) AS total
            FROM despesas
            WHERE user_id = ? AND strftime('%Y', data) = ?
            GROUP BY mes
            ORDER BY mes
        ''', (user_id, ano)).fetchall()

        meses_nums = sorted(set([row['mes'] for row in receitas_por_mes] + [row['mes'] for row in despesas_por_mes]))
        meses = [calendar.month_abbr[int(m)] for m in meses_nums]
        for m in meses_nums:
            total_r = next((row['total'] for row in receitas_por_mes if row['mes'] == m), 0)
            total_d = next((row['total'] for row in despesas_por_mes if row['mes'] == m), 0)
            valores_receitas.append(total_r)
            valores_despesas.append(total_d)
    else:
        # ano == None (Todos): agregamos por mês em todos os anos
        receitas_por_mes = conn.execute('''
            SELECT strftime('%m', data) AS mes, SUM(valor) AS total
            FROM receitas
            WHERE user_id = ?
            GROUP BY mes
            ORDER BY mes
        ''', (user_id,)).fetchall()

        despesas_por_mes = conn.execute('''
            SELECT strftime('%m', data) AS mes, SUM(valor) AS total
            FROM despesas
            WHERE user_id = ?
            GROUP BY mes
            ORDER BY mes
        ''', (user_id,)).fetchall()

        meses_nums = sorted(set([row['mes'] for row in receitas_por_mes] + [row['mes'] for row in despesas_por_mes]))
        meses = [calendar.month_abbr[int(m)] for m in meses_nums]
        for m in meses_nums:
            total_r = next((row['total'] for row in receitas_por_mes if row['mes'] == m), 0)
            total_d = next((row['total'] for row in despesas_por_mes if row['mes'] == m), 0)
            valores_receitas.append(total_r)
            valores_despesas.append(total_d)

    # Últimas transações (sempre filtradas por user; se desejar, poderia também respeitar mes/ano)
    transactions = conn.execute('''
        SELECT data, descricao, categoria, valor, 'Receita' as tipo FROM receitas WHERE user_id = ?
        UNION ALL
        SELECT data, descricao, categoria, valor, 'Despesa' as tipo FROM despesas WHERE user_id = ?
        ORDER BY data DESC LIMIT 10
    ''', (user_id, user_id)).fetchall()

    # Despesas por categoria (dentro do filtro mes/ano)
    despesas_por_categoria = conn.execute(f'''
        SELECT categoria, SUM(valor) AS total
        FROM despesas
        WHERE {where_despesas}
        GROUP BY categoria
    ''', tuple(params_despesas)).fetchall()

    categorias = [row['categoria'] for row in despesas_por_categoria]
    valores_categorias = [row['total'] for row in despesas_por_categoria]

    # lista de anos para o select
    anos = gerar_lista_anos()

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
        categorias=categorias,
        valores_categorias=valores_categorias,
        mes=mes,
        ano=ano,
        anos=anos
    )


# ---------------------------
# RECEITAS (list / create / update / delete) com filtro por mes/ano
# ---------------------------
@app.route('/receitas', methods=['GET', 'POST'])
def gerenciar_receitas():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == 'POST':
        valor = float(request.form['valor'])
        categoria = request.form['categoria']
        descricao = request.form['descricao']
        data = request.form['data']

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO receitas (valor, categoria, descricao, data, user_id) VALUES (?, ?, ?, ?, ?)',
            (valor, categoria, descricao, data, user_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('gerenciar_receitas'))

    # GET: lista com filtro
    mes, ano = get_mes_ano_from_request()
    conn = get_db_connection()

    params = [user_id]
    where = "user_id = ?"
    if mes:
        where += " AND strftime('%m', data) = ?"
        params.append(mes)
    if ano:
        where += " AND strftime('%Y', data) = ?"
        params.append(ano)

    receitas = conn.execute(f'SELECT * FROM receitas WHERE {where} ORDER BY data DESC', tuple(params)).fetchall()

    # Totais para exibição
    total_receitas = conn.execute(f"SELECT IFNULL(SUM(valor), 0) FROM receitas WHERE {where}", tuple(params)).fetchone()[0]

    anos = gerar_lista_anos()
    conn.close()

    return render_template('receita.html', receitas=receitas, total_receitas=total_receitas, mes=mes, ano=ano, anos=anos)


@app.route('/receita/update', methods=['POST'])
def update_receita():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    receita_id = request.form['id']
    valor = float(request.form['valor'])
    categoria = request.form['categoria']
    descricao = request.form['descricao']
    data = request.form['data']

    conn = get_db_connection()
    conn.execute(
        'UPDATE receitas SET valor = ?, categoria = ?, descricao = ?, data = ? WHERE id = ? AND user_id = ?',
        (valor, categoria, descricao, data, receita_id, user_id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('gerenciar_receitas'))


@app.route('/receita/delete/<int:id>', methods=['POST'])
def delete_receita(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM receitas WHERE id = ? AND user_id = ?', (id, user_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('gerenciar_receitas'))


# ---------------------------
# DESPESAS (list / create / update / delete) com filtro por mes/ano
# ---------------------------
@app.route('/despesas', methods=['GET', 'POST'])
def gerenciar_despesas():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == 'POST':
        valor = float(request.form['valor'])
        categoria = request.form['categoria']
        descricao = request.form['descricao']
        data = request.form['data']

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO despesas (valor, categoria, descricao, data, user_id) VALUES (?, ?, ?, ?, ?)',
            (valor, categoria, descricao, data, user_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('gerenciar_despesas'))

    mes, ano = get_mes_ano_from_request()
    conn = get_db_connection()

    params = [user_id]
    where = "user_id = ?"
    if mes:
        where += " AND strftime('%m', data) = ?"
        params.append(mes)
    if ano:
        where += " AND strftime('%Y', data) = ?"
        params.append(ano)

    despesas = conn.execute(f'SELECT * FROM despesas WHERE {where} ORDER BY data DESC', tuple(params)).fetchall()
    total_despesas = conn.execute(f"SELECT IFNULL(SUM(valor), 0) FROM despesas WHERE {where}", tuple(params)).fetchone()[0]

    anos = gerar_lista_anos()
    conn.close()

    return render_template('despesa.html', despesas=despesas, total_despesas=total_despesas, mes=mes, ano=ano, anos=anos)


@app.route('/despesa/update', methods=['POST'])
def update_despesa():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    despesa_id = request.form['id']
    valor = float(request.form['valor'])
    categoria = request.form['categoria']
    descricao = request.form['descricao']
    data = request.form['data']

    conn = get_db_connection()
    conn.execute(
        'UPDATE despesas SET valor = ?, categoria = ?, descricao = ?, data = ? WHERE id = ? AND user_id = ?',
        (valor, categoria, descricao, data, despesa_id, user_id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('gerenciar_despesas'))


@app.route('/despesa/delete/<int:id>', methods=['POST'])
def delete_despesa(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM despesas WHERE id = ? AND user_id = ?', (id, user_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('gerenciar_despesas'))


# ---------------------------
# INVESTIMENTOS (list / create / edit / delete) COM FILTRO POR MÊS/ANO (data_compra)
# ---------------------------
@app.route('/investimentos', methods=['GET', 'POST'])
def gerenciar_investimentos():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        tipo = request.form['tipo']
        ativo = request.form['ativo']
        quantidade = int(request.form['quantidade'])
        valor_unitario = float(request.form['valor_unitario'])
        data_compra = request.form['data_compra']
        valor_atual = float(request.form['valor_atual'])
        descricao = request.form['descricao']

        conn.execute('''
            INSERT INTO investimentos (user_id, tipo, ativo, quantidade, valor_unitario, valor_atual, data_compra, descricao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, tipo, ativo, quantidade, valor_unitario, valor_atual, data_compra, descricao))
        conn.commit()

    # Filtragem por mes/ano sobre data_compra
    mes, ano = get_mes_ano_from_request()

    params = [user_id]
    where = "user_id = ?"
    if mes:
        where += " AND strftime('%m', data_compra) = ?"
        params.append(mes)
    if ano:
        where += " AND strftime('%Y', data_compra) = ?"
        params.append(ano)

    investimentos = conn.execute(f'SELECT * FROM investimentos WHERE {where} ORDER BY data_compra DESC', tuple(params)).fetchall()

    total_investido = sum(i['quantidade'] * i['valor_unitario'] for i in investimentos)
    valor_atual_total = sum(i['quantidade'] * i['valor_atual'] for i in investimentos)
    rentabilidade = ((valor_atual_total - total_investido) / total_investido * 100) if total_investido > 0 else 0

    tipos_dict = {}
    for i in investimentos:
        valor_investido = i['quantidade'] * i['valor_unitario']
        tipos_dict[i['tipo']] = tipos_dict.get(i['tipo'], 0) + valor_investido

    tipos = list(tipos_dict.keys())
    valores_tipo = [round(v, 2) for v in tipos_dict.values()]

    ativos = []
    valores_rent = []
    for i in investimentos:
        ativos.append(i['ativo'])
        investido = i['quantidade'] * i['valor_unitario'] if i['quantidade'] and i['valor_unitario'] else 0
        valor_atual_calc = i['quantidade'] * i['valor_atual'] if i['quantidade'] and i['valor_atual'] else 0
        rent = ((valor_atual_calc - investido) / investido * 100) if investido > 0 else 0
        valores_rent.append(round(rent, 2))

    anos = gerar_lista_anos()
    conn.close()

    return render_template(
        'investimentos.html',
        investimentos=investimentos,
        total_investido=round(total_investido, 2),
        valor_atual=round(valor_atual_total, 2),
        rentabilidade=round(rentabilidade, 2),
        tipos=tipos,
        valores_tipo=valores_tipo,
        ativos=ativos,
        valores_rent=valores_rent,
        mes=mes,
        ano=ano,
        anos=anos
    )


@app.route('/investimentos/editar/<int:id>', methods=['POST'])
def edit_investimento(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    tipo = request.form['tipo']
    ativo = request.form['ativo']
    quantidade = int(request.form['quantidade'])
    valor_unitario = float(request.form['valor_unitario'])
    valor_atual = float(request.form['valor_atual'])
    data_compra = request.form['data_compra']
    descricao = request.form['descricao']

    conn.execute('''
        UPDATE investimentos SET tipo = ?, ativo = ?, quantidade = ?, valor_unitario = ?, valor_atual = ?, data_compra = ?, descricao = ?
        WHERE id = ? AND user_id = ?
    ''', (tipo, ativo, quantidade, valor_unitario, valor_atual, data_compra, descricao, id, session['user_id']))
    conn.commit()
    conn.close()

    flash('Investimento atualizado com sucesso!', 'success')
    return redirect(url_for('gerenciar_investimentos'))


@app.route('/delete_investimento/<int:id>', methods=['POST'])
def delete_investimento(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM investimentos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Investimento deletado com sucesso!', 'success')
    return redirect(url_for('gerenciar_investimentos'))


# ---------------------------
# Relatório Excel (mantive como antes)
# ---------------------------
@app.route('/gerar_relatorio')
def gerar_relatorio():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()

    # Consultar receitas
    receitas = pd.read_sql_query(
        'SELECT data, descricao, categoria, valor FROM receitas WHERE user_id = ? ORDER BY data DESC',
        conn, params=(user_id,)
    )

    # Consultar despesas
    despesas = pd.read_sql_query(
        'SELECT data, descricao, categoria, valor FROM despesas WHERE user_id = ? ORDER BY data DESC',
        conn, params=(user_id,)
    )

    # Consultar investimentos
    investimentos = pd.read_sql_query(
        'SELECT tipo, ativo, quantidade, valor_unitario, valor_atual, data_compra, descricao FROM investimentos WHERE user_id = ?',
        conn, params=(user_id,)
    )

    conn.close()

    # Criar arquivo Excel em memória
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        receitas.to_excel(writer, index=False, sheet_name='Receitas')
        despesas.to_excel(writer, index=False, sheet_name='Despesas')
        investimentos.to_excel(writer, index=False, sheet_name='Investimentos')

    output.seek(0)

    # Enviar para download
    return send_file(
        output,
        as_attachment=True,
        download_name='relatorio_financeiro.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
