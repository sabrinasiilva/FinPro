from flask import Flask, render_template, request, redirect, url_for, session, flash,  send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import calendar
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'chave_nova'  # tenho q trocar por uma chave forte sabrinaaaaaaaaaa

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

# dashboard
@app.route('/dashboard')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()

    total_receitas = conn.execute(
        'SELECT IFNULL(SUM(valor), 0) FROM receitas WHERE user_id = ?', (user_id,)
    ).fetchone()[0]

    total_despesas = conn.execute(
        'SELECT IFNULL(SUM(valor), 0) FROM despesas WHERE user_id = ?', (user_id,)
    ).fetchone()[0]

    saldo = total_receitas - total_despesas

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

    meses_nums = sorted(set(
        [row['mes'] for row in receitas_por_mes] +
        [row['mes'] for row in despesas_por_mes]
    ))
    meses = [calendar.month_abbr[int(m)] for m in meses_nums]

    valores_receitas = []
    valores_despesas = []

    for m in meses_nums:
        total_r = next((row['total'] for row in receitas_por_mes if row['mes'] == m), 0)
        total_d = next((row['total'] for row in despesas_por_mes if row['mes'] == m), 0)
        valores_receitas.append(total_r)
        valores_despesas.append(total_d)

    transactions = conn.execute('''
        SELECT data, descricao, categoria, valor, 'Receita' as tipo FROM receitas WHERE user_id = ?
        UNION ALL
        SELECT data, descricao, categoria, valor, 'Despesa' as tipo FROM despesas WHERE user_id = ?
        ORDER BY data DESC LIMIT 10
    ''', (user_id, user_id)).fetchall()

    despesas_por_categoria = conn.execute('''
        SELECT categoria, SUM(valor) AS total
        FROM despesas
        WHERE user_id = ?
        GROUP BY categoria
    ''', (user_id,)).fetchall()

    categorias = [row['categoria'] for row in despesas_por_categoria]
    valores_categorias = [row['total'] for row in despesas_por_categoria]

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
        valores_categorias=valores_categorias
    )

# gen receitas
@app.route('/receitas', methods=['GET', 'POST'])
def gerenciar_receitas():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        valor = float(request.form['valor'])
        categoria = request.form['categoria']
        descricao = request.form['descricao']
        data = request.form['data']

        conn.execute(
            'INSERT INTO receitas (valor, categoria, descricao, data, user_id) VALUES (?, ?, ?, ?, ?)',
            (valor, categoria, descricao, data, user_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('gerenciar_receitas'))

    receitas = conn.execute(
        'SELECT * FROM receitas WHERE user_id = ?', (user_id,)
    ).fetchall()
    conn.close()

    return render_template('receita.html', receitas=receitas)


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

# gen despesas
@app.route('/despesas', methods=['GET', 'POST'])
def gerenciar_despesas():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        valor = float(request.form['valor'])
        categoria = request.form['categoria']
        descricao = request.form['descricao']
        data = request.form['data']

        conn.execute(
            'INSERT INTO despesas (valor, categoria, descricao, data, user_id) VALUES (?, ?, ?, ?, ?)',
            (valor, categoria, descricao, data, user_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('gerenciar_despesas'))

    despesas = conn.execute(
        'SELECT * FROM despesas WHERE user_id = ?', (user_id,)
    ).fetchall()
    conn.close()

    return render_template('despesa.html', despesas=despesas)


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

# gen investimento
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

    investimentos = conn.execute(
        'SELECT * FROM investimentos WHERE user_id = ?', (user_id,)
    ).fetchall()

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
        investido = i['quantidade'] * i['valor_unitario']
        valor_atual = i['quantidade'] * i['valor_atual']
        rent = ((valor_atual - investido) / investido * 100) if investido > 0 else 0
        valores_rent.append(round(rent, 2))

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
        valores_rent=valores_rent
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

