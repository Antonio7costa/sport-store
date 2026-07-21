import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua-chave-provisoria-para-testes')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///catalogo.db'
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modelos do Banco de Dados
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Shirt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    price = db.Column(db.String(20), nullable=False)
    stock_p = db.Column(db.Integer, default=0, nullable=False)
    stock_m = db.Column(db.Integer, default=0, nullable=False)
    stock_g = db.Column(db.Integer, default=0, nullable=False)
    stock_gg = db.Column(db.Integer, default=0, nullable=False)
    stock_xg = db.Column(db.Integer, default=0, nullable=False)
    images = db.relationship('ShirtImage', backref='shirt', cascade='all, delete-orphan', lazy=True)
    
class ShirtImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_url = db.Column(db.String(300), nullable=False)
    shirt_id = db.Column(db.Integer, db.ForeignKey('shirt.id'), nullable=False)     

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Rota Pública: Catálogo
@app.route('/')
def index():
    shirts = Shirt.query.all()
    shirts_list = []
    
    for shirt in shirts:
        preco_limpo = shirt.price.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try:
            valor_numerico = float(preco_limpo)
        except ValueError:
            valor_numerico = 0.0

        # Cálculos de 10% no Pix e parcelamento em 6x
        preco_pix = valor_numerico * 0.90
        parcela_6x = valor_numerico / 6 if valor_numerico > 0 else 0.0

        # Função auxiliar para formatar de volta para o padrão de moeda Real (R$)
        def formata_real(val):
            return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        estoque_tamanhos = {
            'P': shirt.stock_p,
            'M': shirt.stock_m,
            'G': shirt.stock_g,
            'GG': shirt.stock_gg,
            'XG': shirt.stock_xg
        }
        
        disponiveis = [tamanho for tamanho, qtd in estoque_tamanhos.items() if qtd > 0]
        
        shirts_list.append({
            'id': shirt.id,
            'title': shirt.title,
            'price': shirt.price,
            'preco_pix': formata_real(preco_pix),
            'parcela_6x': formata_real(parcela_6x),
            'image_url': shirt.images[0].image_url if shirt.images else '',
            'images': shirt.images,
            'estoque': estoque_tamanhos,
            'todos_tamanhos': ['P', 'M', 'G', 'GG', 'XG'],
            'disponiveis': disponiveis
        })
        
    return render_template('index.html', shirts=shirts_list)

# Rota de detalhes da camisa
@app.route('/shirt/<int:id>')
def shirt_detail(id):
    shirt = Shirt.query.get_or_404(id)
    
    preco_limpo = shirt.price.replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        valor_numerico = float(preco_limpo)
    except ValueError:
        valor_numerico = 0.0

    preco_pix = valor_numerico * 0.90
    parcela_6x = valor_numerico / 6 if valor_numerico > 0 else 0.0

    def formata_real(val):
        return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    estoque_tamanhos = {
        'P': shirt.stock_p,
        'M': shirt.stock_m,
        'G': shirt.stock_g,
        'GG': shirt.stock_gg,
        'XG': shirt.stock_xg
    }
    
    disponiveis = [tamanho for tamanho, qtd in estoque_tamanhos.items() if qtd > 0]
    
    shirt_data = {
        'id': shirt.id,
        'title': shirt.title,
        'price': shirt.price,
        'preco_pix': formata_real(preco_pix),
        'parcela_6x': formata_real(parcela_6x),
        'images': shirt.images,  # <--- ESSA LINHA É A QUE FAZ A IMAGEM APARECER NO DETALHE
        'estoque': estoque_tamanhos,
        'todos_tamanhos': ['P', 'M', 'G', 'GG', 'XG'],
        'disponiveis': disponiveis
    }
    
    return render_template('shirt_detail.html', shirt=shirt_data)

# Rota de Login do Admin
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        # Compara a senha digitada com o hash seguro salvo no banco
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin'))
            
        flash('Usuário ou senha inválidos.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Rota Admin: Gerenciar Catálogo
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category')
        price = request.form.get('price')
        
        stock_p = int(request.form.get('stock_p', 0) or 0)
        stock_m = int(request.form.get('stock_m', 0) or 0)
        stock_g = int(request.form.get('stock_g', 0) or 0)
        stock_gg = int(request.form.get('stock_gg', 0) or 0)
        stock_xg = int(request.form.get('stock_xg', 0) or 0)
        
        new_shirt = Shirt(
            title=title, 
            price=price,
            stock_p=stock_p,
            stock_m=stock_m,
            stock_g=stock_g,
            stock_gg=stock_gg,
            stock_xg=stock_xg
        )
        db.session.add(new_shirt)
        db.session.commit()
        
        urls_texto = request.form.get('image_urls', '')
        for url in urls_texto.splitlines():
            url_limpa = url.strip()
            if url_limpa:
                nova_foto = ShirtImage(image_url=url_limpa, shirt_id=new_shirt.id)
                db.session.add(nova_foto)
        db.session.commit()
        return redirect(url_for('admin'))
    
    shirts = Shirt.query.all()
    return render_template('admin.html', shirts=shirts)

# Rota para Deletar Produto
@app.route('/admin/delete/<int:id>')
@login_required
def delete_shirt(id):
    shirt = Shirt.query.get_or_404(id)
    db.session.delete(shirt)
    db.session.commit()
    return redirect(url_for('admin'))

# Rota Admin: Editar Camisa Existente
@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_shirt(id):
    shirt = Shirt.query.get_or_404(id)
    
    if request.method == 'POST':
        shirt.title = request.form.get('title')
        shirt.price = request.form.get('price')
        
        shirt.stock_p = int(request.form.get('stock_p', 0) or 0)
        shirt.stock_m = int(request.form.get('stock_m', 0) or 0)
        shirt.stock_g = int(request.form.get('stock_g', 0) or 0)
        shirt.stock_gg = int(request.form.get('stock_gg', 0) or 0)
        shirt.stock_xg = int(request.form.get('stock_xg', 0) or 0)
        
        # Pega os links digitados na textarea
        urls_texto = request.form.get('image_urls', '')
        
        # Se o usuário preencheu algo, atualiza a lista de imagens
        if urls_texto.strip():
            # 1. Apaga todas as imagens antigas desta camisa para evitar duplicação
            ShirtImage.query.filter_by(shirt_id=shirt.id).delete()
            
            # 2. Adiciona apenas os links limpos que estão escritos agora na caixa
            for url in urls_texto.splitlines():
                url_limpa = url.strip()
                if url_limpa:
                    nova_foto = ShirtImage(image_url=url_limpa, shirt_id=shirt.id)
                    db.session.add(nova_foto)
                    
        db.session.commit()
        return redirect(url_for('admin'))
        
    return render_template('edit_shirt.html', shirt=shirt)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Cria um admin padrão com senha criptografada se não existir
        if not User.query.filter_by(username='admin').first():
            senha_criptografada = generate_password_hash('123')
            admin_user = User(username='admin', password=senha_criptografada)
            db.session.add(admin_user)
            db.session.commit()
    app.run(debug=False)