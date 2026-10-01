import os
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    clientes_dir = os.path.join(app.static_folder, 'img/clientes')
    clientes_logos = []
    
    if os.path.exists(clientes_dir):
        clientes_logos = [f for f in os.listdir(clientes_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp'))]
        
    return render_template('index.html', clientes_logos=clientes_logos)

@app.route('/sobre')
def sobre():
    return render_template('sobre.html')

@app.route('/servicosdetalhe')
def servicos():
    return render_template('servicosdetalhe.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)