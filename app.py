from flask import Flask, render_template, redirect, url_for, request, flash, abort, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text
import os
import uuid
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Папки для загрузки
UPLOAD_FOLDER = os.path.join('static', 'uploads')
BG_FOLDER = os.path.join('static', 'backgrounds')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['BG_FOLDER'] = BG_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BG_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Сначала войдите в систему'
login_manager.login_message_category = 'warning'


# ---------- МОДЕЛИ ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), default='')
    items = db.relationship('Item', backref='category', cascade='all, delete-orphan')


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    content = db.Column(db.Text, default='')
    price = db.Column(db.Float, default=0.0)
    phone = db.Column(db.String(30), default='')
    image = db.Column(db.String(255), default='')
    lamps = db.Column(db.Integer, default=0)
    diameter = db.Column(db.String(50), default='')
    height = db.Column(db.String(50), default='')
    is_hit = db.Column(db.Boolean, default=False)
    is_popular = db.Column(db.Boolean, default=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)


class Setting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text, default='')


class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(255), default='/')
    order = db.Column(db.Integer, default=0)


class Page(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    comment = db.Column(db.Text, default='')
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=True)
    item = db.relationship('Item', backref='orders')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_processed = db.Column(db.Boolean, default=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file, folder):
    if not file or file.filename == '':
        return ''
    if not allowed_file(file.filename):
        return ''
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(folder, filename))
    return filename


# ---------- ХЕЛПЕРЫ НАСТРОЕК ----------
def get_setting(key, default=''):
    s = db.session.get(Setting, key)
    return s.value if s else default


def set_setting(key, value):
    s = db.session.get(Setting, key)
    if s:
        s.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


def get_current_city():
    """Город из cookie или из настроек по умолчанию."""
    city = request.cookies.get('user_city')
    if city:
        return city
    return get_setting('shop_city', 'Москва')


# ---------- ИНИЦИАЛИЗАЦИЯ ----------
def init_db():
    with app.app_context():
        db.create_all()

        # миграция старых таблиц item
        inspector = inspect(db.engine)
        cols = [c['name'] for c in inspector.get_columns('item')]
        with db.engine.connect() as conn:
            if 'price' not in cols:
                conn.execute(text('ALTER TABLE item ADD COLUMN price FLOAT DEFAULT 0'))
            if 'phone' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN phone VARCHAR(30) DEFAULT ''"))
            if 'image' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN image VARCHAR(255) DEFAULT ''"))
            if 'description' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN description TEXT DEFAULT ''"))
            if 'lamps' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN lamps INTEGER DEFAULT 0"))
            if 'diameter' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN diameter VARCHAR(50) DEFAULT ''"))
            if 'height' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN height VARCHAR(50) DEFAULT ''"))
            if 'is_hit' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN is_hit BOOLEAN DEFAULT 0"))
            if 'is_popular' not in cols:
                conn.execute(text("ALTER TABLE item ADD COLUMN is_popular BOOLEAN DEFAULT 0"))
            conn.commit()

        # настройки оформления
        if not db.session.get(Setting, 'bg_color'):
            set_setting('bg_color', '#f4f6f9')
        if not db.session.get(Setting, 'bg_image'):
            set_setting('bg_image', '')
        if not db.session.get(Setting, 'site_title'):
            set_setting('site_title', '💡 Гусь-Люстра')
        if not db.session.get(Setting, 'shop_phone'):
            set_setting('shop_phone', '+7 (999) 123-45-67')
        if not db.session.get(Setting, 'shop_schedule'):
            set_setting('shop_schedule', 'с 8:00 до 22:00 без выходных')
        if not db.session.get(Setting, 'shop_city'):
            set_setting('shop_city', 'Москва')
        if not db.session.get(Setting, 'cities_list'):
            set_setting('cities_list',
                'Москва,Санкт-Петербург,Новосибирск,Екатеринбург,Казань,'
                'Нижний Новгород,Челябинск,Самара,Омск,Ростов-на-Дону,'
                'Уфа,Красноярск,Воронеж,Пермь,Волгоград')

        # дефолтные страницы
        if not Page.query.filter_by(slug='about').first():
            db.session.add(Page(
                slug='about',
                title='О сайте',
                content='Мы — официальный производитель и поставщик люстр.\n\n'
                        'Более 10 лет успешной работы на рынке России.\n'
                        'Широчайший ассортимент, лучшие цены, доставка по всей стране.'
            ))
        if not Page.query.filter_by(slug='contacts').first():
            db.session.add(Page(
                slug='contacts',
                title='Контакты',
                content='📞 Телефон: +7 (999) 123-45-67\n'
                        '✉ Email: info@example.com\n'
                        '🏢 Адрес: г. Москва, ул. Примерная, д. 1\n'
                        '🕐 Часы работы: пн–вс, 8:00–22:00'
            ))
        if not Page.query.filter_by(slug='delivery').first():
            db.session.add(Page(
                slug='delivery',
                title='Доставка',
                content='Курьерская доставка по всей России.\n\n'
                        'Оплата при получении товара.\n'
                        'Сроки: 3–7 рабочих дней в зависимости от региона.'
            ))
        db.session.commit()

        # дефолтное меню
        if not MenuItem.query.first():
            db.session.add_all([
                MenuItem(title='Главная', url='/', order=0),
                MenuItem(title='Каталог', url='/catalog', order=1),
                MenuItem(title='Доставка', url='/page/delivery', order=2),
                MenuItem(title='О сайте', url='/page/about', order=3),
                MenuItem(title='Контакты', url='/page/contacts', order=4),
            ])
            db.session.commit()

        # авто-исправление старых ссылок "#"
        fixed = False
        for m in MenuItem.query.all():
            if m.title == 'Главная' and m.url == '#':
                m.url = '/'; fixed = True
            elif m.title == 'О сайте' and m.url == '#':
                m.url = '/page/about'; fixed = True
            elif m.title == 'Контакты' and m.url == '#':
                m.url = '/page/contacts'; fixed = True
        if fixed:
            db.session.commit()
            print('Ссылки в меню обновлены автоматически')

        # админ
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', is_admin=True)
            admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
            db.session.add(admin)
            db.session.commit()
            print('Создан админ: admin / admin123')

        # демо-категории и товары
        if not Category.query.first():
            c1 = Category(name='Хрустальные люстры', description='Классические хрустальные люстры')
            c2 = Category(name='Современные люстры', description='Стильные современные модели')
            c3 = Category(name='Настенные светильники', description='Бра и настенные светильники')
            c4 = Category(name='Подвесные светильники', description='Одиночные подвесы')
            db.session.add_all([c1, c2, c3, c4])
            db.session.commit()

            demo_items = [
                Item(title='Люстра хрустальная «Империя»', category_id=c1.id, price=125000,
                     lamps=12, diameter='750 мм', height='800 мм',
                     description='Роскошная люстра с хрустальными подвесками',
                     is_hit=True, is_popular=True),
                Item(title='Люстра «Классика»', category_id=c1.id, price=89000,
                     lamps=8, diameter='700 мм', height='750 мм',
                     description='Классическая хрустальная люстра',
                     is_popular=True),
                Item(title='Люстра «Модерн»', category_id=c2.id, price=45000,
                     lamps=6, diameter='600 мм', height='480 мм',
                     description='Стильная современная люстра',
                     is_popular=True),
                Item(title='Люстра «Минимализм»', category_id=c2.id, price=32000,
                     lamps=3, diameter='420 мм', height='230 мм',
                     description='Простая и элегантная'),
                Item(title='Бра «Версаль»', category_id=c3.id, price=12500,
                     lamps=1, diameter='200 мм', height='370 мм',
                     description='Настенный светильник',
                     is_hit=True),
                Item(title='Подвес «Шар»', category_id=c4.id, price=8900,
                     lamps=1, diameter='250 мм', height='450 мм',
                     description='Одиночный подвесной светильник',
                     is_popular=True),
            ]
            db.session.add_all(demo_items)
            db.session.commit()


# ---------- КОНТЕКСТ ДЛЯ ШАБЛОНОВ ----------
@app.context_processor
def inject_globals():
    cities_str = get_setting('cities_list',
        'Москва,Санкт-Петербург,Новосибирск,Екатеринбург,Казань,'
        'Нижний Новгород,Челябинск,Самара,Омск,Ростов-на-Дону,'
        'Уфа,Красноярск,Воронеж,Пермь,Волгоград')
    cities = [c.strip() for c in cities_str.split(',') if c.strip()]
    return {
        'menu_items': MenuItem.query.order_by(MenuItem.order).all(),
        'categories_for_menu': Category.query.all(),
        'site_title': get_setting('site_title', '💡 Гусь-Люстра'),
        'bg_color': get_setting('bg_color', '#f4f6f9'),
        'bg_image': get_setting('bg_image', ''),
        'shop_phone': get_setting('shop_phone', ''),
        'shop_schedule': get_setting('shop_schedule', ''),
        'shop_city': get_setting('shop_city', ''),
        'cities': cities,
        'current_city': get_current_city(),
    }

# ---------- СМЕНА ГОРОДА ----------
@app.route('/set-city', methods=['POST'])
def set_city():
    city = request.form.get('city', '').strip()
    next_url = request.form.get('next', '/') or '/'
    resp = make_response(redirect(next_url))
    if city:
        resp.set_cookie('user_city', city, max_age=60 * 60 * 24 * 365)
    return resp


# ---------- ГЛАВНАЯ ----------
@app.route('/')
def index():
    categories = Category.query.all()
    popular = Item.query.filter(
        (Item.is_popular == True) | (Item.is_hit == True)
    ).limit(8).all()
    return render_template('index.html', categories=categories, popular=popular)


# ---------- КАТАЛОГ ----------
@app.route('/catalog')
def catalog():
    categories = Category.query.all()
    cat_id = request.args.get('cat', type=int)
    if cat_id:
        items = Item.query.filter_by(category_id=cat_id).all()
        current_cat = Category.query.get(cat_id)
    else:
        items = Item.query.all()
        current_cat = None
    return render_template('catalog.html',
                           categories=categories,
                           items=items,
                           current_cat=current_cat)


# ---------- КАТЕГОРИЯ ----------
@app.route('/category/<int:cat_id>')
def category_view(cat_id):
    category = Category.query.get_or_404(cat_id)
    categories = Category.query.all()
    return render_template('category.html', category=category, categories=categories)


# ---------- ТОВАР ----------
@app.route('/item/<int:item_id>')
def item_view(item_id):
    item = Item.query.get_or_404(item_id)
    categories = Category.query.all()
    related = Item.query.filter(
        Item.category_id == item.category_id,
        Item.id != item.id
    ).limit(4).all()
    return render_template('item.html', item=item, categories=categories, related=related)


# ---------- СТРАНИЦЫ ----------
@app.route('/page/<slug>')
def page_view(slug):
    page = Page.query.filter_by(slug=slug).first_or_404()
    categories = Category.query.all()
    return render_template('page.html', page=page, categories=categories)


# ---------- ЗАЯВКИ ----------
@app.route('/order', methods=['POST'])
def create_order():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    comment = request.form.get('comment', '').strip()
    item_id = request.form.get('item_id')

    if not name or not phone:
        flash('Укажите имя и телефон', 'danger')
        return redirect(request.referrer or url_for('index'))

    order = Order(
        name=name,
        phone=phone,
        comment=comment,
        item_id=int(item_id) if item_id else None
    )
    db.session.add(order)
    db.session.commit()
    flash('Спасибо! Мы свяжемся с вами в ближайшее время.', 'success')
    return redirect(request.referrer or url_for('index'))


# ---------- АВТОРИЗАЦИЯ ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Вы вошли в систему', 'success')
            return redirect(url_for('admin_panel') if user.is_admin else url_for('index'))
        flash('Неверный логин или пароль', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Заполните все поля', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Такой пользователь уже есть', 'danger')
        else:
            u = User(username=username)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash('Регистрация успешна, войдите', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли', 'info')
    return redirect(url_for('index'))


# ---------- АДМИНКА ----------
def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@app.route('/admin')
@login_required
def admin_panel():
    admin_required()
    categories = Category.query.all()
    items = Item.query.all()
    users = User.query.all()
    menu = MenuItem.query.order_by(MenuItem.order).all()
    pages = Page.query.order_by(Page.id).all()
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin.html',
                           categories=categories,
                           items=items,
                           users=users,
                           menu=menu,
                           pages=pages,
                           orders=orders,
                           current_bg_color=get_setting('bg_color', '#f4f6f9'),
                           current_bg_image=get_setting('bg_image', ''),
                           current_site_title=get_setting('site_title', '💡 Гусь-Люстра'),
                           current_shop_phone=get_setting('shop_phone', ''),
                           current_shop_schedule=get_setting('shop_schedule', ''),
                           current_shop_city=get_setting('shop_city', ''),
                           current_cities_list=get_setting('cities_list',
                               'Москва,Санкт-Петербург,Новосибирск,Екатеринбург,Казань'))


# --- НАСТРОЙКИ САЙТА ---
@app.route('/admin/appearance', methods=['POST'])
@login_required
def update_appearance():
    admin_required()

    bg_color = request.form.get('bg_color', '#f4f6f9').strip()
    site_title = request.form.get('site_title', '').strip()
    shop_phone = request.form.get('shop_phone', '').strip()
    shop_schedule = request.form.get('shop_schedule', '').strip()
    shop_city = request.form.get('shop_city', '').strip()
    cities_list = request.form.get('cities_list', '').strip()

    if bg_color:
        set_setting('bg_color', bg_color)
    if site_title:
        set_setting('site_title', site_title)
    if shop_phone:
        set_setting('shop_phone', shop_phone)
    if shop_schedule:
        set_setting('shop_schedule', shop_schedule)
    if shop_city:
        set_setting('shop_city', shop_city)
    if cities_list:
        set_setting('cities_list', cities_list)

    bg_file = request.files.get('bg_image')
    if bg_file and bg_file.filename:
        old = get_setting('bg_image', '')
        if old:
            old_path = os.path.join(app.config['BG_FOLDER'], old)
            if os.path.exists(old_path):
                os.remove(old_path)
        new_name = save_image(bg_file, app.config['BG_FOLDER'])
        set_setting('bg_image', new_name)

    if request.form.get('remove_bg_image') == '1':
        old = get_setting('bg_image', '')
        if old:
            old_path = os.path.join(app.config['BG_FOLDER'], old)
            if os.path.exists(old_path):
                os.remove(old_path)
        set_setting('bg_image', '')

    flash('Настройки обновлены', 'success')
    return redirect(url_for('admin_panel'))


# --- МЕНЮ ---
@app.route('/admin/menu/add', methods=['POST'])
@login_required
def add_menu_item():
    admin_required()
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '/').strip() or '/'
    if title:
        max_order = db.session.query(db.func.max(MenuItem.order)).scalar() or 0
        db.session.add(MenuItem(title=title, url=url, order=max_order + 1))
        db.session.commit()
        flash('Пункт меню добавлен', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/menu/delete/<int:mid>', methods=['POST'])
@login_required
def delete_menu_item(mid):
    admin_required()
    item = MenuItem.query.get_or_404(mid)
    db.session.delete(item)
    db.session.commit()
    flash('Пункт меню удалён', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/admin/menu/edit/<int:mid>', methods=['POST'])
@login_required
def edit_menu_item(mid):
    admin_required()
    item = MenuItem.query.get_or_404(mid)
    item.title = request.form.get('title', '').strip() or item.title
    item.url = request.form.get('url', '/').strip() or '/'
    try:
        item.order = int(request.form.get('order', item.order))
    except ValueError:
        pass
    db.session.commit()
    flash('Пункт меню обновлён', 'success')
    return redirect(url_for('admin_panel'))


# --- СТРАНИЦЫ ---
@app.route('/admin/page/add', methods=['POST'])
@login_required
def add_page():
    admin_required()
    slug = request.form.get('slug', '').strip().lower()
    title = request.form.get('title', '').strip()

    if not re.fullmatch(r'[a-z0-9\-]+', slug):
        flash('URL может содержать только латиницу, цифры и дефис', 'danger')
        return redirect(url_for('admin_panel'))
    if Page.query.filter_by(slug=slug).first():
        flash('Страница с таким URL уже существует', 'danger')
        return redirect(url_for('admin_panel'))

    db.session.add(Page(slug=slug, title=title, content=''))
    db.session.commit()
    flash('Страница создана', 'success')
    return redirect(url_for('edit_page', slug=slug))


@app.route('/admin/page/edit/<slug>', methods=['GET', 'POST'])
@login_required
def edit_page(slug):
    admin_required()
    page = Page.query.filter_by(slug=slug).first_or_404()
    if request.method == 'POST':
        page.title = request.form.get('title', '').strip() or page.title
        page.content = request.form.get('content', '')
        db.session.commit()
        flash('Страница обновлена', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('admin_page_edit.html', page=page)


@app.route('/admin/page/delete/<slug>', methods=['POST'])
@login_required
def delete_page(slug):
    admin_required()
    page = Page.query.filter_by(slug=slug).first_or_404()
    db.session.delete(page)
    db.session.commit()
    flash('Страница удалена', 'info')
    return redirect(url_for('admin_panel'))


# --- КАТЕГОРИИ ---
@app.route('/admin/category/add', methods=['POST'])
@login_required
def add_category():
    admin_required()
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if name:
        if Category.query.filter_by(name=name).first():
            flash('Такая категория уже есть', 'danger')
        else:
            db.session.add(Category(name=name, description=desc))
            db.session.commit()
            flash('Категория добавлена', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/category/delete/<int:cat_id>', methods=['POST'])
@login_required
def delete_category(cat_id):
    admin_required()
    c = Category.query.get_or_404(cat_id)
    db.session.delete(c)
    db.session.commit()
    flash('Категория удалена', 'info')
    return redirect(url_for('admin_panel'))


# --- ТОВАРЫ ---
@app.route('/admin/item/add', methods=['POST'])
@login_required
def add_item():
    admin_required()
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    description = request.form.get('description', '').strip()
    price = request.form.get('price', '0') or '0'
    phone = request.form.get('phone', '').strip()
    cat_id = request.form.get('category_id')
    lamps = request.form.get('lamps', '0') or '0'
    diameter = request.form.get('diameter', '').strip()
    height = request.form.get('height', '').strip()
    is_hit = bool(request.form.get('is_hit'))
    is_popular = bool(request.form.get('is_popular'))

    try:
        price = float(price.replace(',', '.'))
    except ValueError:
        price = 0.0

    try:
        lamps = int(lamps)
    except ValueError:
        lamps = 0

    if title and cat_id:
        image_name = save_image(request.files.get('image'), app.config['UPLOAD_FOLDER'])
        db.session.add(Item(
            title=title,
            content=content,
            description=description,
            price=price,
            phone=phone,
            image=image_name,
            category_id=int(cat_id),
            lamps=lamps,
            diameter=diameter,
            height=height,
            is_hit=is_hit,
            is_popular=is_popular,
        ))
        db.session.commit()
        flash('Товар добавлен', 'success')
    else:
        flash('Заполните заголовок и категорию', 'danger')
    return redirect(url_for('admin_panel'))


@app.route('/admin/item/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    admin_required()
    it = Item.query.get_or_404(item_id)
    if it.image:
        path = os.path.join(app.config['UPLOAD_FOLDER'], it.image)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(it)
    db.session.commit()
    flash('Товар удалён', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/admin/item/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    admin_required()
    item = Item.query.get_or_404(item_id)
    categories = Category.query.all()
    if request.method == 'POST':
        item.title = request.form.get('title', '').strip()
        item.content = request.form.get('content', '').strip()
        item.description = request.form.get('description', '').strip()
        item.phone = request.form.get('phone', '').strip()
        item.category_id = int(request.form.get('category_id'))
        item.diameter = request.form.get('diameter', '').strip()
        item.height = request.form.get('height', '').strip()
        item.is_hit = bool(request.form.get('is_hit'))
        item.is_popular = bool(request.form.get('is_popular'))

        try:
            item.price = float((request.form.get('price') or '0').replace(',', '.'))
        except ValueError:
            item.price = 0.0

        try:
            item.lamps = int(request.form.get('lamps') or 0)
        except ValueError:
            item.lamps = 0

        new_file = request.files.get('image')
        if new_file and new_file.filename:
            if item.image:
                old = os.path.join(app.config['UPLOAD_FOLDER'], item.image)
                if os.path.exists(old):
                    os.remove(old)
            item.image = save_image(new_file, app.config['UPLOAD_FOLDER'])

        db.session.commit()
        flash('Товар обновлён', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('admin_edit.html', item=item, categories=categories)


# --- ЗАЯВКИ ---
@app.route('/admin/order/process/<int:order_id>', methods=['POST'])
@login_required
def process_order(order_id):
    admin_required()
    o = Order.query.get_or_404(order_id)
    o.is_processed = not o.is_processed
    db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/order/delete/<int:order_id>', methods=['POST'])
@login_required
def delete_order(order_id):
    admin_required()
    o = Order.query.get_or_404(order_id)
    db.session.delete(o)
    db.session.commit()
    flash('Заявка удалена', 'info')
    return redirect(url_for('admin_panel'))


# ---------- ОШИБКИ ----------
@app.errorhandler(403)
def forbidden(e):
    return render_template('base.html', error_message='Доступ запрещён (403)'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', error_message='Страница не найдена (404)'), 404


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)