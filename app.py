from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Product, Category, Sale, SaleItem
from functools import wraps
from datetime import datetime, timedelta
from sqlalchemy import func

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-to-a-random-string-please'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------- Декораторы ролей ----------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def cashier_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('admin', 'cashier'):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ---------- Логин / логаут ----------
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('cashier_pos'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user)
            return redirect(url_for('index'))
        flash('Неверный логин или пароль', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# =====================================================
#                    АДМИН
# =====================================================
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    sales_today = Sale.query.filter(Sale.created_at >= today_start).all()
    revenue_today = sum(s.total for s in sales_today)
    products_count = Product.query.filter_by(is_active=True).count()
    low_stock = Product.query.filter(Product.stock <= 5, Product.is_active == True).all()

    return render_template('admin/dashboard.html',
                           revenue_today=revenue_today,
                           sales_count=len(sales_today),
                           products_count=products_count,
                           low_stock=low_stock)


# ----- Товары -----
@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    q = request.args.get('q', '').strip()
    query = Product.query
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    products = query.order_by(Product.id.desc()).all()
    return render_template('admin/products.html', products=products, q=q)


@app.route('/admin/products/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_product_new():
    categories = Category.query.all()
    if request.method == 'POST':
        try:
            p = Product(
                name=request.form['name'].strip(),
                barcode=request.form.get('barcode', '').strip() or None,
                price=float(request.form['price']),
                stock=int(request.form['stock']),
                category_id=int(request.form['category_id']) if request.form.get('category_id') else None,
                description=request.form.get('description', '').strip(),
            )
            db.session.add(p)
            db.session.commit()
            flash('Товар добавлен', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'error')
    return render_template('admin/product_form.html', product=None, categories=categories)


@app.route('/admin/products/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_product_edit(pid):
    p = Product.query.get_or_404(pid)
    categories = Category.query.all()
    if request.method == 'POST':
        try:
            p.name = request.form['name'].strip()
            p.barcode = request.form.get('barcode', '').strip() or None
            p.price = float(request.form['price'])
            p.stock = int(request.form['stock'])
            p.category_id = int(request.form['category_id']) if request.form.get('category_id') else None
            p.description = request.form.get('description', '').strip()
            db.session.commit()
            flash('Товар обновлён', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'error')
    return render_template('admin/product_form.html', product=p, categories=categories)


@app.route('/admin/products/<int:pid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_product_delete(pid):
    p = Product.query.get_or_404(pid)
    p.is_active = False  # мягкое удаление
    db.session.commit()
    flash('Товар удалён', 'success')
    return redirect(url_for('admin_products'))


# ----- Категории -----
@app.route('/admin/categories', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_categories():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if name and not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))
            db.session.commit()
            flash('Категория добавлена', 'success')
    cats = Category.query.all()
    return render_template('admin/categories.html', categories=cats)


@app.route('/admin/categories/<int:cid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_category_delete(cid):
    c = Category.query.get_or_404(cid)
    if c.products:
        flash('Нельзя удалить: в категории есть товары', 'error')
    else:
        db.session.delete(c)
        db.session.commit()
        flash('Категория удалена', 'success')
    return redirect(url_for('admin_categories'))


# ----- Пользователи -----
@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_users():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', 'cashier')

        if User.query.filter_by(username=username).first():
            flash('Такой логин уже существует', 'error')
        elif not username or not password or not full_name:
            flash('Заполните все поля', 'error')
        else:
            u = User(username=username, full_name=full_name, role=role)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash('Пользователь создан', 'success')

    users = User.query.order_by(User.id).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/<int:uid>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_user_toggle(uid):
    u = User.query.get_or_404(uid)
    if u.id == current_user.id:
        flash('Нельзя заблокировать себя', 'error')
    else:
        u.is_active_user = not u.is_active_user
        db.session.commit()
        flash('Статус изменён', 'success')
    return redirect(url_for('admin_users'))


# ----- Отчёты -----
@app.route('/admin/reports')
@login_required
@admin_required
def admin_reports():
    period = request.args.get('period', 'today')
    now = datetime.utcnow()

    if period == 'today':
        start = datetime.combine(now.date(), datetime.min.time())
    elif period == 'week':
        start = now - timedelta(days=7)
    elif period == 'month':
        start = now - timedelta(days=30)
    else:
        start = datetime(2000, 1, 1)

    sales = Sale.query.filter(Sale.created_at >= start).order_by(Sale.created_at.desc()).all()
    total = sum(s.total for s in sales)

    # Топ товаров
    top = db.session.query(
        SaleItem.product_name,
        func.sum(SaleItem.quantity).label('qty'),
        func.sum(SaleItem.price * SaleItem.quantity).label('sum')
    ).join(Sale).filter(Sale.created_at >= start)\
     .group_by(SaleItem.product_name)\
     .order_by(func.sum(SaleItem.quantity).desc()).limit(10).all()

    return render_template('admin/reports.html',
                           sales=sales, total=total, period=period, top=top)


# =====================================================
#                    КАССИР
# =====================================================
@app.route('/pos')
@login_required
@cashier_required
def cashier_pos():
    categories = Category.query.all()
    return render_template('cashier/pos.html', categories=categories)


# API для поиска товаров (используется в JS)
@app.route('/api/products')
@login_required
@cashier_required
def api_products():
    q = request.args.get('q', '').strip()
    cat = request.args.get('category', '').strip()
    query = Product.query.filter(Product.is_active == True, Product.stock > 0)
    if q:
        query = query.filter(
            db.or_(Product.name.ilike(f'%{q}%'), Product.barcode == q)
        )
    if cat:
        query = query.filter(Product.category_id == int(cat))
    products = query.limit(50).all()
    return jsonify([{
        'id': p.id, 'name': p.name, 'price': p.price,
        'stock': p.stock, 'barcode': p.barcode,
        'category': p.category.name if p.category else ''
    } for p in products])


# Оформление продажи
@app.route('/api/checkout', methods=['POST'])
@login_required
@cashier_required
def api_checkout():
    data = request.get_json()
    items = data.get('items', [])
    payment_method = data.get('payment_method', 'cash')
    discount = float(data.get('discount', 0))

    if not items:
        return jsonify({'ok': False, 'error': 'Корзина пуста'}), 400

    try:
        sale = Sale(cashier_id=current_user.id,
                    payment_method=payment_method,
                    discount=discount)
        db.session.add(sale)
        db.session.flush()

        total = 0
        for it in items:
            p = Product.query.get(it['id'])
            if not p or p.stock < it['qty']:
                db.session.rollback()
                return jsonify({'ok': False, 'error': f'Недостаточно товара: {p.name if p else "?"}'}), 400
            p.stock -= it['qty']
            line = p.price * it['qty']
            total += line
            db.session.add(SaleItem(
                sale_id=sale.id, product_id=p.id,
                product_name=p.name, price=p.price, quantity=it['qty']
            ))

        # Скидка применяется ко всей сумме
        total_after_discount = round(total * (1 - discount / 100), 2)
        sale.total = total_after_discount
        db.session.commit()

        return jsonify({
            'ok': True,
            'sale_id': sale.id,
            'total': total_after_discount,
            'discount': discount
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


# Просмотр чека
@app.route('/receipt/<int:sale_id>')
@login_required
@cashier_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return render_template('cashier/receipt.html', sale=sale)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)