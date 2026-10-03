import os
from sqlalchemy import case
from sqlalchemy.orm import selectinload  # [ALTERADO 1] carrega as fotos de todas as camisas em 1 consulta só
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

# [ALTERADO 2] compressão gzip das respostas (pip install flask-compress)
try:
    from flask_compress import Compress
except ImportError:
    Compress = None

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua-chave-provisoria-para-testes')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Configuração dinâmica: usa PostgreSQL na nuvem se disponível, ou SQLite localmente
database_url = os.environ.get('DATABASE_URL', 'sqlite:///catalogo.db')

# Correção de compatibilidade caso a URL fornecida comece com postgres:// em vez de postgresql://
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url

# [ALTERADO 3] mantém conexões com o banco vivas
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
}

db = SQLAlchemy(app)
migrate = Migrate(app, db)

csrf = CSRFProtect(app)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

# [NOVO] Limitador de tentativas
limiter = Limiter(get_remote_address, app=app, default_limits=[])

# [ALTERADO 2] ativa a compressão
if Compress:
    Compress(app)


# [ALTERADO 4] cache no navegador para arquivos da pasta /static (1 ano)
@app.after_request
def adicionar_cache_estatico(resp):
    if request.path.startswith('/static/'):
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return resp


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modelos do Banco de Dados
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

class Shirt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ordem = db.Column(db.Integer, default=0, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    price = db.Column(db.String(20), nullable=False)
    desconto_pix = db.Column(db.Float, default=10.0, nullable=False)
    destaque_promocao = db.Column(db.Boolean, default=False, nullable=False)
    publicado = db.Column(db.Boolean, default=True, nullable=False)
    alteracoes_pendentes = db.Column(db.JSON, nullable=True)
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


with app.app_context():
    db.create_all()
    
    # Puxa a senha diretamente do arquivo .env
    senha_admin = os.environ.get('ADMIN_PASSWORD')
    
    admin_existente = User.query.filter_by(username='admin').first()
    if not admin_existente:
        if not senha_admin:
            raise ValueError("A variável ADMIN_PASSWORD não está definida no arquivo .env!")
            
        novo_admin = User(username='admin', password=generate_password_hash(senha_admin))
        db.session.add(novo_admin)
        db.session.commit()
    else:
        # Garante que se você alterar a senha no .env, ela atualiza no banco ao reiniciar
        if senha_admin:
            admin_existente.password = generate_password_hash(senha_admin)
            db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # [ALTERADO 5] User.query.get() está obsoleto


# ---------------------------------------------------------------------------
# [ALTERADO 6] Funções auxiliares: esse código estava copiado 3 vezes
# ---------------------------------------------------------------------------
def formata_real(val):
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def montar_shirt_dict(shirt):
    preco_limpo = shirt.price.replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        valor_numerico = float(preco_limpo)
    except ValueError:
        valor_numerico = 0.0

    desconto_pix = shirt.desconto_pix if shirt.desconto_pix is not None else 10.0
    preco_pix = valor_numerico * (1 - desconto_pix / 100)
    parcela_5x = valor_numerico / 5 if valor_numerico > 0 else 0.0

    estoque_tamanhos = {
        'P': shirt.stock_p,
        'M': shirt.stock_m,
        'G': shirt.stock_g,
        'GG': shirt.stock_gg,
        'XG': shirt.stock_xg
    }
    disponiveis = [tamanho for tamanho, qtd in estoque_tamanhos.items() if qtd > 0]

    return {
        'id': shirt.id,
        'title': shirt.title,
        'category': shirt.category,
        'price': shirt.price,
        'preco_pix': formata_real(preco_pix),
        'desconto_pix': desconto_pix,
        'parcela_5x': formata_real(parcela_5x),
        'image_url': shirt.images[0].image_url if shirt.images else '',
        'images': shirt.images,
        'estoque': estoque_tamanhos,
        'todos_tamanhos': ['P', 'M', 'G', 'GG', 'XG'],
        'disponiveis': disponiveis
    }


def destaque_efetivo(shirt):
    if shirt.alteracoes_pendentes and 'destaque_promocao' in shirt.alteracoes_pendentes:
        return shirt.alteracoes_pendentes['destaque_promocao']
    return shirt.destaque_promocao


def consultar_catalogo(categoria=None, limite=None, excluir_ids=None):
    estoque_total = (Shirt.stock_p + Shirt.stock_m + Shirt.stock_g + Shirt.stock_gg + Shirt.stock_xg)

    query = Shirt.query.options(selectinload(Shirt.images)).filter_by(publicado=True)
    if categoria:
        query = query.filter_by(category=categoria)
    if excluir_ids:
        query = query.filter(Shirt.id.notin_(excluir_ids))

    query = query.order_by(
        case(
            (estoque_total > 0, 0),
            else_=1
        ).asc(),
        Shirt.ordem.asc(),
        Shirt.id.desc()
    )

    if limite:
        query = query.limit(limite)

    return query.all()


def consultar_promocoes(limite=10):
    estoque_total = (Shirt.stock_p + Shirt.stock_m + Shirt.stock_g + Shirt.stock_gg + Shirt.stock_xg)

    query = Shirt.query.options(selectinload(Shirt.images)).filter_by(destaque_promocao=True, publicado=True)
    query = query.order_by(
        case(
            (estoque_total > 0, 0),
            else_=1
        ).asc(),
        Shirt.ordem.asc(),
        Shirt.id.desc()
    )

    if limite:
        query = query.limit(limite)

    return query.all()

# Ordem de preferência das categorias na home; qualquer categoria nova cadastrada
# no admin aparece automaticamente no fim, em ordem alfabética.
ORDEM_CATEGORIAS_HOME = ['Brasileiros', 'Internacionais', 'Feminino', 'Manga Longa']


def categorias_para_home():
    linhas = db.session.query(Shirt.category).filter(Shirt.category.isnot(None)).distinct().all()
    existentes = {c[0] for c in linhas if c[0]}
    ordenadas = [c for c in ORDEM_CATEGORIAS_HOME if c in existentes]
    extras = sorted(existentes - set(ORDEM_CATEGORIAS_HOME))
    return ordenadas + extras


def montar_secoes_home(por_categoria=10):
    secoes = []

    promocoes = consultar_promocoes(limite=por_categoria)
    ids_em_promocao = {s.id for s in promocoes}

    if promocoes:
        secoes.append({
            'nome': 'Promoções',
            'shirts': [montar_shirt_dict(s) for s in promocoes]
        })

    for categoria in categorias_para_home():
        shirts = consultar_catalogo(categoria=categoria, limite=por_categoria, excluir_ids=ids_em_promocao)
        if shirts:
            secoes.append({
                'nome': categoria,
                'shirts': [montar_shirt_dict(s) for s in shirts]
            })
    return secoes


@app.route('/')
def index():
    secoes = montar_secoes_home()
    return render_template('index.html', secoes=secoes)

@app.route('/shirt/<int:id>')
def shirt_detail(id):
    shirt = Shirt.query.options(selectinload(Shirt.images)).filter_by(id=id, publicado=True).first_or_404()
    return render_template('shirt_detail.html', shirt=montar_shirt_dict(shirt))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
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
        ordem = int(request.form.get('ordem', 0) or 0)
        desconto_pix = float(request.form.get('desconto_pix', 10) or 10)
        destaque_promocao = request.form.get('destaque_promocao') == 'on'

        stock_p = int(request.form.get('stock_p', 0) or 0)
        stock_m = int(request.form.get('stock_m', 0) or 0)
        stock_g = int(request.form.get('stock_g', 0) or 0)
        stock_gg = int(request.form.get('stock_gg', 0) or 0)
        stock_xg = int(request.form.get('stock_xg', 0) or 0)

        new_shirt = Shirt(
            title=title,
            category=category,
            price=price,
            ordem=ordem,
            desconto_pix=desconto_pix,
            destaque_promocao=destaque_promocao,
            publicado=False,
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

    todas = Shirt.query.options(selectinload(Shirt.images)).order_by(Shirt.ordem.asc(), Shirt.id.desc()).all()

    pendentes = [s for s in todas if not s.publicado or s.alteracoes_pendentes]
    em_promocao = [s for s in todas if s.publicado and destaque_efetivo(s)]

    categorias_existentes = []
    for s in todas:
        nome = s.category or 'Sem categoria'
        if nome not in categorias_existentes:
            categorias_existentes.append(nome)

    publicadas_por_categoria = []
    for nome in categorias_existentes:
        shirts_categoria = [s for s in todas if s.publicado and (s.category or 'Sem categoria') == nome]
        if shirts_categoria:
            publicadas_por_categoria.append({'nome': nome, 'shirts': shirts_categoria})

    return render_template('admin.html', pendentes=pendentes, em_promocao=em_promocao, publicadas_por_categoria=publicadas_por_categoria)


# Rota para Deletar Produto
@app.route('/admin/delete/<int:id>', methods=['POST'])
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
        novos_dados = {
            'title': request.form.get('title'),
            'category': request.form.get('category'),
            'price': request.form.get('price'),
            'ordem': int(request.form.get('ordem', 0) or 0),
            'desconto_pix': float(request.form.get('desconto_pix', 10) or 10),
            'destaque_promocao': request.form.get('destaque_promocao') == 'on',
            'stock_p': int(request.form.get('stock_p', 0) or 0),
            'stock_m': int(request.form.get('stock_m', 0) or 0),
            'stock_g': int(request.form.get('stock_g', 0) or 0),
            'stock_gg': int(request.form.get('stock_gg', 0) or 0),
            'stock_xg': int(request.form.get('stock_xg', 0) or 0),
        }

        urls_texto = request.form.get('image_urls', '')
        if urls_texto.strip():
            novos_dados['image_urls'] = [u.strip() for u in urls_texto.splitlines() if u.strip()]

        if shirt.publicado:
            # já está no ar: guarda como rascunho, não mexe no que o cliente vê
            shirt.alteracoes_pendentes = novos_dados
        else:
            # ainda não publicada: pode gravar direto, ninguém vê mesmo
            for campo, valor in novos_dados.items():
                if campo == 'image_urls':
                    ShirtImage.query.filter_by(shirt_id=shirt.id).delete()
                    for url in valor:
                        db.session.add(ShirtImage(image_url=url, shirt_id=shirt.id))
                else:
                    setattr(shirt, campo, valor)

        db.session.commit()
        return redirect(url_for('admin'))

    dados_exibicao = {
        'title': shirt.title,
        'category': shirt.category,
        'price': shirt.price,
        'ordem': shirt.ordem,
        'desconto_pix': shirt.desconto_pix,
        'destaque_promocao': shirt.destaque_promocao,
        'stock_p': shirt.stock_p,
        'stock_m': shirt.stock_m,
        'stock_g': shirt.stock_g,
        'stock_gg': shirt.stock_gg,
        'stock_xg': shirt.stock_xg,
    }
    if shirt.alteracoes_pendentes:
        dados_exibicao.update(shirt.alteracoes_pendentes)

    return render_template('edit_shirt.html', shirt=shirt, dados_exibicao=dados_exibicao)


@app.route('/admin/publicar', methods=['POST'])
@login_required
def publicar():
    novas = Shirt.query.filter_by(publicado=False).all()
    for camisa in novas:
        camisa.publicado = True

    com_rascunho = [s for s in Shirt.query.all() if s.alteracoes_pendentes]
    for camisa in com_rascunho:
        dados = dict(camisa.alteracoes_pendentes)
        if 'image_urls' in dados:
            ShirtImage.query.filter_by(shirt_id=camisa.id).delete()
            for url in dados.pop('image_urls'):
                db.session.add(ShirtImage(image_url=url, shirt_id=camisa.id))
        for campo, valor in dados.items():
            setattr(camisa, campo, valor)
        camisa.alteracoes_pendentes = None

    db.session.commit()
    flash(f'{len(novas) + len(com_rascunho)} camisa(s) publicada(s) com sucesso!')
    return redirect(url_for('admin'))


@app.route('/admin/aplicar-categoria', methods=['POST'])
@login_required
def aplicar_categoria():
    categoria = request.form.get('categoria', '').strip()
    desconto_pix = request.form.get('desconto_pix', '').strip()
    destaque_promocao = 'destaque_promocao' in request.form

    if not categoria:
        flash('Escolha uma categoria.')
        return redirect(url_for('admin'))

    shirts = Shirt.query.filter_by(category=categoria).all()
    for camisa in shirts:
        if camisa.publicado:
            dados = dict(camisa.alteracoes_pendentes) if camisa.alteracoes_pendentes else {}
            if desconto_pix:
                dados['desconto_pix'] = float(desconto_pix)
            if destaque_promocao:
                dados['destaque_promocao'] = True
            camisa.alteracoes_pendentes = dados
        else:
            if desconto_pix:
                camisa.desconto_pix = float(desconto_pix)
            if destaque_promocao:
                camisa.destaque_promocao = True

    db.session.commit()
    flash(f'{len(shirts)} camisa(s) da categoria "{categoria}" marcada(s).')
    return redirect(url_for('admin'))


@app.route('/admin/remover-promocao/<int:id>', methods=['POST'])
@login_required
def remover_promocao(id):
    shirt = Shirt.query.get_or_404(id)
    if shirt.publicado:
        dados = dict(shirt.alteracoes_pendentes) if shirt.alteracoes_pendentes else {}
        dados['destaque_promocao'] = False
        shirt.alteracoes_pendentes = dados
    else:
        shirt.destaque_promocao = False
    db.session.commit()
    flash(f'"{shirt.title}" marcada para sair da promoção (fica pendente até você publicar).')
    return redirect(url_for('admin'))


# Rota para filtrar camisas por categoria
@app.route('/categoria/<string:nome_categoria>')
def filtrar_categoria(nome_categoria):
    shirts = consultar_catalogo(categoria=nome_categoria)
    shirts_list = [montar_shirt_dict(s) for s in shirts]
    return render_template('index.html', shirts=shirts_list, categoria_atual=nome_categoria)

@app.route('/promocoes')
def ver_promocoes():
    shirts = consultar_promocoes(limite=None)
    shirts_list = [montar_shirt_dict(s) for s in shirts]
    return render_template('index.html', shirts=shirts_list, categoria_atual='Promoções')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False)