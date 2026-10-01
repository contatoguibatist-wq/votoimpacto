import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

# 1. Instancia o Flask
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "chave-secreta-padrao")

# 2. Registra o Blueprint de autenticação e utilitários de banco
from auth import auth_bp, get_db_connection
app.register_blueprint(auth_bp)

# ----------------- CONTROLE DE ACESSO ----------------- #

def login_required_cliente(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Faça login para acessar o painel.', 'error')
            return redirect(url_for('auth.login'))
        if session.get('is_admin'):
            return redirect('/workbench')
        if not session.get('id_account'):
            flash('Conta de gabinete não vinculada.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------- ROTAS INSTITUCIONAIS ----------------- #

@app.route('/')
def index():
    clientes_dir = os.path.join(app.static_folder, 'img/clientes')
    clientes_logos = []
    if os.path.exists(clientes_dir):
        clientes_logos = [f for f in os.listdir(clientes_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp'))]
    return render_template('index.html', clientes_logos=clientes_logos)

@app.route('/servicosdetalhe')
def servicos():
    return render_template('servicosdetalhe.html')

@app.route('/workbench')
def workbench_home():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Acesso restrito à administração.', 'error')
        return redirect(url_for('auth.login'))
    return "Bem-vindo à Workbench (Admin VotoImpacto)"

# ----------------- SAAS DO GABINETE (/painel) ----------------- #

@app.route('/painel')
@login_required_cliente
def painel_home():
    id_account = session['id_account']
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Dados cadastrais do Gabinete
    cur.execute("""
        SELECT candidato_nome, cargo_eletivo, cidade, estado 
        FROM account 
        WHERE id = %s
    """, (id_account,))
    gabinete = cur.fetchone()

    # 2. Métricas consolidadas em consulta única
    cur.execute("""
        SELECT 
            (SELECT COUNT(*) FROM eventos_transicao WHERE id_account = %s AND status = 'Concluído'),
            (SELECT COUNT(*) FROM cronograma_posts WHERE id_account = %s AND status = 'Publicado'),
            (SELECT COUNT(*) FROM materias_jornal WHERE id_account = %s AND status = 'Aprovada'),
            (SELECT COUNT(*) FROM cronograma_posts WHERE id_account = %s AND status = 'Aguardando Aprovação')
    """, (id_account, id_account, id_account, id_account))
    metricas = cur.fetchone()

    # 3. Próximos Eventos de Transição
    cur.execute("""
        SELECT id, titulo, tipo, data_evento, localizacao, status, analista_responsavel
        FROM eventos_transicao 
        WHERE id_account = %s 
        ORDER BY data_evento ASC 
        LIMIT 5
    """, (id_account,))
    eventos = cur.fetchall()

    # 4. Cronograma de Conteúdo Imediato
    cur.execute("""
        SELECT id, titulo, canal, data_programada, status, copy_texto
        FROM cronograma_posts 
        WHERE id_account = %s 
        ORDER BY data_programada ASC 
        LIMIT 6
    """, (id_account,))
    posts = cur.fetchall()

    cur.close()
    conn.close()

    # Contagem regressiva até 1º de Janeiro da posse oficial
    hoje = datetime.now()
    ano_posse = hoje.year + 1 if hoje.month >= 10 else hoje.year
    dias_posse = max(0, (datetime(ano_posse, 1, 1) - hoje).days)

    return render_template('painel/index.html',
                           gabinete=gabinete,
                           eventos=eventos,
                           posts=posts,
                           metricas=metricas,
                           dias_posse=dias_posse)

@app.route('/painel/cronograma', methods=['GET', 'POST'])
@login_required_cliente
def painel_cronograma():
    id_account = session['id_account']
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'novo_evento':
            cur.execute("""
                INSERT INTO eventos_transicao 
                (id_account, titulo, tipo, data_evento, localizacao, analista_responsavel, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (id_account, request.form.get('titulo'), request.form.get('tipo'), request.form.get('data_evento'),
                  request.form.get('localizacao'), request.form.get('analista_responsavel'), request.form.get('observacoes')))
            conn.commit()
            flash('Agenda registrada com sucesso!', 'success')

        elif acao == 'novo_post':
            cur.execute("""
                INSERT INTO cronograma_posts 
                (id_account, id_evento, titulo, canal, data_programada, copy_texto)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_account, request.form.get('id_evento') or None, request.form.get('titulo'),
                  request.form.get('canal'), request.form.get('data_programada'), request.form.get('copy_texto')))
            conn.commit()
            flash('Post agendado!', 'success')

    # 1. Eventos cadastrados
    cur.execute("""
        SELECT id, titulo, tipo, data_evento, localizacao, status, analista_responsavel, observacoes
        FROM eventos_transicao 
        WHERE id_account = %s 
        ORDER BY data_evento DESC
    """, (id_account,))
    todos_eventos = cur.fetchall()

    # 2. Posts cadastrados
    cur.execute("""
        SELECT p.id, p.id_account, p.titulo, p.canal, p.data_programada, p.status, p.copy_texto, e.titulo as evento_origem
        FROM cronograma_posts p
        LEFT JOIN eventos_transicao e ON p.id_evento = e.id
        WHERE p.id_account = %s 
        ORDER BY p.data_programada ASC
    """, (id_account,))
    todos_posts = cur.fetchall()

    # 3. Puxa TODOS os usuários vinculados à conta para servir de Analistas/Operadores
    cur.execute("""
        SELECT id, nome, email 
        FROM users 
        WHERE id_account = %s 
        ORDER BY nome ASC
    """, (id_account,))
    analistas_conta = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'painel/cronograma.html', 
        eventos=todos_eventos, 
        posts=todos_posts, 
        analistas=analistas_conta
    )

@app.route('/painel/relatorios/cronograma')
@login_required_cliente
def relatorio_cronograma():
    id_account = session['id_account']
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT candidato_nome, cargo_eletivo, cidade, estado 
        FROM account 
        WHERE id = %s
    """, (id_account,))
    gabinete = cur.fetchone()

    cur.execute("""
        SELECT e.titulo, e.tipo, e.data_evento, e.localizacao, e.status, e.analista_responsavel,
               COUNT(p.id) as total_posts_gerados
        FROM eventos_transicao e
        LEFT JOIN cronograma_posts p ON p.id_evento = e.id
        WHERE e.id_account = %s
        GROUP BY e.id, e.titulo, e.tipo, e.data_evento, e.localizacao, e.status, e.analista_responsavel
        ORDER BY e.data_evento DESC
    """, (id_account,))
    relatorio_eventos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('painel/relatorio_cronograma.html', 
                           gabinete=gabinete, 
                           relatorio=relatorio_eventos, 
                           data_geracao=datetime.now())

# ----------------- API DO CALENDÁRIO SEMANAL (SEM F5) ----------------- #

@app.route('/api/eventos', methods=['GET', 'POST'])
@login_required_cliente
def api_eventos():
    id_account = session['id_account']
    conn = get_db_connection()
    cur = conn.cursor()

    # GET: Carrega eventos no formato ISO para renderização no calendário
    if request.method == 'GET':
        start = request.args.get('start')
        end = request.args.get('end')

        query = """
            SELECT id, titulo, tipo, data_evento, localizacao, status, analista_responsavel
            FROM eventos_transicao
            WHERE id_account = %s
        """
        params = [id_account]

        if start and end:
            query += " AND data_evento >= %s AND data_evento <= %s"
            params.extend([start, end])

        query += " ORDER BY data_evento ASC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        cur.close()
        conn.close()

        eventos_json = []
        for r in rows:
            # Formato esperado pelo FullCalendar
            eventos_json.append({
                "id": r[0],
                "title": r[1],
                "start": r[3].strftime('%Y-%m-%dT%H:%M:%S'),
                "extendedProps": {
                    "tipo": r[2],
                    "localizacao": r[4],
                    "status": r[5],
                    "analista": r[6] or 'Não atribuído'
                }
            })
        return jsonify(eventos_json)

    # POST: Criação dinâmica via Modal/Clique no Calendário
    data = request.get_json()
    if not data:
        return jsonify({"erro": "Dados inválidos"}), 400

    titulo = data.get('titulo')
    tipo = data.get('tipo', 'Reunião Política')
    data_evento = data.get('data_evento') # Formato YYYY-MM-DDTHH:MM
    localizacao = data.get('localizacao', 'Gabinete')
    analista = data.get('analista_responsavel', '')
    observacoes = data.get('observacoes', '')

    try:
        # 1. Salva o evento no calendário
        cur.execute("""
            INSERT INTO eventos_transicao 
            (id_account, titulo, tipo, data_evento, localizacao, analista_responsavel, observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, titulo, data_evento
        """, (id_account, titulo, tipo, data_evento, localizacao, analista, observacoes))
        novo_evento = cur.fetchone()
        evento_id = novo_evento[0]

        # 2. AUTOMAÇÃO: Envia imediatamente para a fila de "Notícias do Portal"
        # Cria uma pauta rascunho com os dados já preenchidos da agenda
        chapeu_padrao = tipo.upper()
        subtitulo_padrao = f"Cobertura oficial de compromisso em {localizacao} realizado no período de transição."
        conteudo_padrao = f"""Pauta gerada a partir da agenda de transição:

Evento: {titulo}
Tipo: {tipo}
Local: {localizacao}
Equipe em campo: {analista or 'Equipe de Comunicação'}
Orientações de pauta: {observacoes or 'Registrar discursos, fotos com lideranças e articulações da semana.'}

[Redação VotoImpacto: Redigir texto final a partir do material colhido pelos analistas de rua]."""

        cur.execute("""
            INSERT INTO materias_jornal
            (id_account, titulo, chapeu, subtitulo, conteudo, status, autor_redacao)
            VALUES (%s, %s, %s, %s, %s, 'Rascunho', 'Redação VotoImpacto')
        """, (id_account, f"Cobertura: {titulo}", chapeu_padrao, subtitulo_padrao, conteudo_padrao))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "id": evento_id,
            "title": titulo,
            "start": data_evento
        }), 201

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"erro": str(e)}), 500
# ----------------- GESTÃO EDITORIAL DE MATÉRIAS ----------------- #

@app.route('/painel/materias')
@login_required_cliente
def painel_materias():
    id_account = session['id_account']
    aba = request.args.get('aba', 'rascunho')

    # Mapeamento 1:1 com a coluna "status" do banco
    status_map = {
        'rascunho': 'Rascunho',
        'publicados': 'Publicado',
        'cancelados': 'Cancelado'
    }
    status_atual = status_map.get(aba, 'Rascunho')

    conn = get_db_connection()
    cur = conn.cursor()

    # Contadores exatos das 3 abas
    cur.execute("""
        SELECT 
            (SELECT COUNT(*) FROM materias_jornal WHERE id_account = %s AND status = 'Rascunho'),
            (SELECT COUNT(*) FROM materias_jornal WHERE id_account = %s AND status = 'Publicado'),
            (SELECT COUNT(*) FROM materias_jornal WHERE id_account = %s AND status = 'Cancelado')
    """, (id_account, id_account, id_account))
    contadores = cur.fetchone()

    # Lista filtrada pela aba ativa
    cur.execute("""
        SELECT id, titulo, chapeu, subtitulo, status, autor_redacao, foto_destaque_url, criado_em, publicado_em
        FROM materias_jornal
        WHERE id_account = %s AND status = %s
        ORDER BY criado_em DESC
    """, (id_account, status_atual))
    materias = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'painel/materias.html',
        materias=materias,
        aba_ativa=aba,
        qtd_rascunho=contadores[0],
        qtd_publicados=contadores[1],
        qtd_cancelados=contadores[2]
    )


@app.route('/painel/materias/<int:id_materia>', methods=['GET', 'POST'])
@login_required_cliente
def materia_detalhe(id_materia):
    id_account = session['id_account']
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        chapeu = request.form.get('chapeu', '').strip()
        subtitulo = request.form.get('subtitulo', '').strip()
        conteudo = request.form.get('conteudo', '').strip()
        foto_destaque_url = request.form.get('foto_destaque_url', '').strip()
        acao = request.form.get('acao')
        data_agendada = request.form.get('data_agendada', '').strip()

        # Validação estrita para publicação (imediata ou agendada)
        if acao in ['publicar', 'agendar']:
            if not titulo or not conteudo or not foto_destaque_url:
                flash('Para publicar ou agendar, é obrigatório preencher Título, Imagem Principal e o Corpo da matéria.', 'error')
                cur.close()
                conn.close()
                return redirect(url_for('materia_detalhe', id_materia=id_materia))

        if acao == 'publicar':
            novo_status = 'Publicado'
            cur.execute("""
                UPDATE materias_jornal
                SET titulo = %s, chapeu = %s, subtitulo = %s, conteudo = %s,
                    foto_destaque_url = %s, status = %s, publicado_em = CURRENT_TIMESTAMP
                WHERE id = %s AND id_account = %s
            """, (titulo, chapeu, subtitulo, conteudo, foto_destaque_url, novo_status, id_materia, id_account))
            flash('Matéria publicada com sucesso!', 'success')

        elif acao == 'agendar':
            novo_status = 'Agendado'
            # Se não definiu data, usa data atual + 1 hora
            publicar_em = data_agendada if data_agendada else datetime.now()
            cur.execute("""
                UPDATE materias_jornal
                SET titulo = %s, chapeu = %s, subtitulo = %s, conteudo = %s,
                    foto_destaque_url = %s, status = %s, publicado_em = %s
                WHERE id = %s AND id_account = %s
            """, (titulo, chapeu, subtitulo, conteudo, foto_destaque_url, novo_status, publicar_em, id_materia, id_account))
            flash('Publicação agendada com sucesso!', 'success')

        elif acao == 'cancelar':
            novo_status = 'Cancelado'
            cur.execute("""
                UPDATE materias_jornal
                SET titulo = %s, chapeu = %s, subtitulo = %s, conteudo = %s,
                    foto_destaque_url = %s, status = %s
                WHERE id = %s AND id_account = %s
            """, (titulo, chapeu, subtitulo, conteudo, foto_destaque_url, novo_status, id_materia, id_account))
            flash('Matéria cancelada.', 'info')

        else:  # salvar rascunho
            novo_status = 'Rascunho'
            cur.execute("""
                UPDATE materias_jornal
                SET titulo = %s, chapeu = %s, subtitulo = %s, conteudo = %s,
                    foto_destaque_url = %s, status = %s
                WHERE id = %s AND id_account = %s
            """, (titulo, chapeu, subtitulo, conteudo, foto_destaque_url, novo_status, id_materia, id_account))
            flash('Rascunho salvo com sucesso!', 'success')

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('materia_detalhe', id_materia=id_materia))

    # GET
    cur.execute("""
        SELECT id, titulo, chapeu, subtitulo, conteudo, status, autor_redacao, foto_destaque_url, criado_em, publicado_em
        FROM materias_jornal
        WHERE id = %s AND id_account = %s
    """, (id_materia, id_account))
    materia = cur.fetchone()

    cur.close()
    conn.close()

    if not materia:
        flash('Matéria não localizada.', 'error')
        return redirect(url_for('painel_materias'))

    return render_template('painel/materia_detalhe.html', m=materia)

# ----------------- EXECUÇÃO LOCAL ----------------- #



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)