import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse
import psycopg2
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from email.mime.image import MIMEImage

load_dotenv()

auth_bp = Blueprint('auth', __name__)

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    result = urlparse(db_url)
    return psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )

def disparar_codigo_email(destinatario, nome_usuario, candidato_nome, codigo):
    remetente = os.getenv("MAIL_USERNAME")
    senha_app = os.getenv("MAIL_PASSWORD")

    template_path = os.path.join('templates', 'email_primeiro_acesso.html')
    if not os.path.exists(template_path):
        template_path = os.path.join('templates', 'emails', 'email_primeiro_acesso.html')

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()
    except Exception as e:
        print(f"Erro ao ler template: {e}")
        return False

    corpo_html = html_template.format(
        nome_usuario=nome_usuario,
        candidato_nome=candidato_nome,
        codigo=codigo
    )

    msg = MIMEMultipart('related')
    msg['From'] = f"VotoImpacto <{remetente}>"
    msg['To'] = destinatario
    msg['Subject'] = f"Credencial Institucional de Acesso — {codigo}"

    msg_alt = MIMEMultipart('alternative')
    msg.attach(msg_alt)
    msg_alt.attach(MIMEText(corpo_html, 'html'))

    # Anexa o logomax.png como imagem embutida (CID)
    logo_path = os.path.join('static', 'img', 'logomax.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as img_file:
            img = MIMEImage(img_file.read())
            img.add_header('Content-ID', '<logo_votoimpacto>')
            img.add_header('Content-Disposition', 'inline', filename='logomax.png')
            msg.attach(img)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha_app)
        server.sendmail(remetente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Erro SMTP: {e}")
        return False
    
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # CASO 2: O usuário já recebeu o código e está submetendo a troca na MESMA PÁGINA
        if 'acao' in request.form and request.form.get('acao') == 'confirmar_codigo':
            if 'temp_user_id' not in session or 'temp_codigo' not in session:
                flash('Sessão expirada. Insira suas credenciais novamente.', 'error')
                return render_template('login.html')

            codigo_digitado = request.form.get('codigo', '').strip()
            nova_senha = request.form.get('nova_senha', '').strip()
            confirma_senha = request.form.get('confirma_senha', '').strip()

            if codigo_digitado != session.get('temp_codigo'):
                flash('Código incorreto.', 'error')
                return render_template('login.html')

            if nova_senha != confirma_senha or len(nova_senha) < 6:
                flash('Senhas não coincidem ou possuem menos de 6 caracteres.', 'error')
                return render_template('login.html')

            # CRIPTOGRAFA a nova senha definitiva criada pelo usuário
            senha_hash = generate_password_hash(nova_senha)

            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE users 
                    SET senha = %s, primeiro_acesso = FALSE 
                    WHERE id = %s
                    RETURNING is_admin, id_account, nome
                """, (senha_hash, session['temp_user_id']))
                user_data = cur.fetchone()
                conn.commit()
                cur.close()
                conn.close()

                session['user_id'] = session['temp_user_id']
                session['user_name'] = user_data[2]
                session['is_admin'] = user_data[0]
                session['id_account'] = user_data[1]

                session.pop('temp_user_id', None)
                session.pop('temp_codigo', None)

                return redirect('/workbench' if session['is_admin'] else '/painel')

            except Exception as e:
                flash(f'Erro ao atualizar credencial: {e}', 'error')
                return render_template('login.html')

        # CASO 1: Formulário inicial de Login (E-mail + Senha Provisória ou Definitiva)
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '').strip()

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT u.id, u.id_account, u.primeiro_acesso, u.nome, u.email, u.senha, u.is_admin,
                       COALESCE(a.candidato_nome, 'Gabinete') as candidato_nome
                FROM users u
                LEFT JOIN account a ON u.id_account = a.id
                WHERE LOWER(u.email) = LOWER(%s)
            """, (email,))
            user = cur.fetchone()
            cur.close()
            conn.close()

            if not user:
                flash('Credenciais não localizadas no sistema.', 'error')
                return render_template('login.html')

            user_id, id_account, primeiro_acesso, nome, db_email, db_senha, is_admin, candidato_nome = user

            # VALIDAÇÃO DE SENHA:
            # 1. Se primeiro acesso: compara texto puro (provisória visível no banco)
            # 2. Se já trocou: compara com o hash criptografado
            senha_valida = False
            if primeiro_acesso:
                senha_valida = (senha == db_senha)
            else:
                try:
                    senha_valida = check_password_hash(db_senha, senha)
                except Exception:
                    senha_valida = (senha == db_senha)

            if not senha_valida:
                flash('Senha incorreta.', 'error')
                return render_template('login.html')

            # É PRIMEIRO ACESSO COM A SENHA PROVISÓRIA CORRETA:
            if primeiro_acesso:
                codigo = str(random.randint(100000, 999999))
                
                enviou = disparar_codigo_email(db_email, nome, candidato_nome, codigo)
                if not enviou:
                    flash('Falha ao disparar o e-mail com o código. Verifique as credenciais SMTP no .env.', 'error')
                    return render_template('login.html')

                session['temp_user_id'] = user_id
                session['temp_codigo'] = codigo
                
                flash(f'Código enviado para {db_email}. Preencha abaixo para validar.', 'success')
                return render_template('login.html')

            # LOGIN NORMAL (DEFINITIVO)
            session['user_id'] = user_id
            session['user_name'] = nome
            session['is_admin'] = is_admin
            session['id_account'] = id_account

            return redirect('/workbench' if is_admin else '/painel')

        except Exception as e:
            flash(f'Erro de banco de dados: {e}', 'error')

    return render_template('login.html')

@auth_bp.route('/cancelar-validacao')
def cancelar_validacao():
    session.pop('temp_user_id', None)
    session.pop('temp_codigo', None)
    return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))