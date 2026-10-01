import os
from flask import Flask, render_template

app = Flask(__name__, template_folder='templates')

@app.route('/')
def index():
    # Caminho para a pasta de clientes
    clientes_dir = os.path.join(app.static_folder, 'img/clientes')
    
    # Lê os arquivos da pasta se ela existir
    clientes_logos = []
    if os.path.exists(clientes_dir):
        # Filtra para garantir que só pegue imagens
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