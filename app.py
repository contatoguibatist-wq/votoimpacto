import os
from flask import Flask, render_template

# Configura explicitamente os caminhos absolutos para o Vercel encontrar as pastas
basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, 'templates')
static_dir = os.path.join(basedir, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

@app.route('/')
def index():
    clientes_dir = os.path.join(app.static_folder, 'img/clientes')
    clientes_logos = []
    
    if os.path.exists(clientes_dir):
        clientes_logos = [f for f in os.listdir(clientes_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp'))]
        
    return render_template('public/index.html', clientes_logos=clientes_logos)

@app.route('/sobre')
def sobre():
    return render_template('public/sobre.html')

@app.route('/servicosdetalhe')
def servicos():
    return render_template('public/servicosdetalhe.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)