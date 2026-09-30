from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Product, Category, Sale, SaleItem, Shift, Supply, SupplyItem
from functools import wraps
from datetime import datetime, timedelta
from sqlalchemy import func
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-to-a-random-string-please'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


# ----- Вспомогательные функции -----
def save_product_image(file):
    """Сохраняет загруженный файл фото товара и возвращает имя файла."""
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"p_{int(datetime.utcnow().timestamp()*1000)}.{ext}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


# ----- Товары -----
@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    q = request.args.get('q', '').strip()
    show_archived = request.args.get('show_archived') == '1'

    query = Product.query
    if not show_archived:
        query = query.filter(Product.is_active == True)
    else:
        query = query.filter(Product.is_active == False)

    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))

    products = query.order_by(Product.id.desc()).all()
    return render_template('admin/products.html',
                           products=products, q=q,
                           show_archived=show_archived)


@app.route('/admin/products/<int:pid>/restore', methods=['POST'])
@login_required
@admin_required
def admin_product_restore(pid):
    p = Product.query.get_or_404(pid)
    p.is_active = True
    db.session.commit()
    flash('Товар восстановлен', 'success')
    return redirect(url_for('admin_products', show_archived=1))


@app.route('/admin/products/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_product_new():
    categories = Category.query.all()
    if request.method == 'POST':
        try:
            ws_raw = request.form.get('wholesale_price', '').strip()
            wholesale_price = float(ws_raw) if ws_raw else None

            exp_raw = request.form.get('expiry_date', '').strip()
            expiry_date = datetime.strptime(exp_raw, '%Y-%m-%d').date() if exp_raw else None

            p = Product(
                name=request.form['name'].strip(),
                barcode=request.form.get('barcode', '').strip() or None,
                price=float(request.form['price']),
                wholesale_price=wholesale_price,
                stock=int(request.form['stock']),
                category_id=int(request.form['category_id']) if request.form.get('category_id') else None,
                description=request.form.get('description', '').strip(),
                expiry_date=expiry_date,
            )
            img = save_product_image(request.files.get('image'))
            if img:
                p.image = img
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

            ws_raw = request.form.get('wholesale_price', '').strip()
            p.wholesale_price = float(ws_raw) if ws_raw else None

            exp_raw = request.form.get('expiry_date', '').strip()
            p.expiry_date = datetime.strptime(exp_raw, '%Y-%m-%d').date() if exp_raw else None

            p.stock = int(request.form['stock'])
            p.category_id = int(request.form['category_id']) if request.form.get('category_id') else None
            p.description = request.form.get('description', '').strip()

            img = save_product_image(request.files.get('image'))
            if img:
                if p.image:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], p.image)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                p.image = img

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
    p.is_active = False
    db.session.commit()
    flash('Товар удалён', 'success')
    return redirect(url_for('admin_products'))


# ----- Оприходование товара -----
@app.route('/admin/supplies')
@login_required
@admin_required
def admin_supplies():
    supplies = Supply.query.order_by(Supply.date.desc(), Supply.id.desc()).all()
    return render_template('admin/supplies.html', supplies=supplies)


@app.route('/admin/supplies/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_supply_new():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == 'POST':
        try:
            date_raw = request.form.get('date', '').strip()
            supplier = request.form.get('supplier', '').strip()
            comment = request.form.get('comment', '').strip()

            if not date_raw or not supplier:
                flash('Укажите дату и поставщика', 'error')
                return redirect(url_for('admin_supply_new'))

            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            prices = request.form.getlist('purchase_price[]')

            items_data = []
            for pid, qty, price in zip(product_ids, quantities, prices):
                if not pid or not qty or not price:
                    continue
                try:
                    qty = int(qty)
                    price = float(price)
                except ValueError:
                    continue
                if qty <= 0 or price < 0:
                    continue
                items_data.append((int(pid), qty, price))

            if not items_data:
                flash('Добавьте хотя бы одну позицию', 'error')
                return redirect(url_for('admin_supply_new'))

            supply = Supply(
                date=datetime.strptime(date_raw, '%Y-%m-%d').date(),
                supplier=supplier,
                comment=comment,
                created_by=current_user.id,
            )
            db.session.add(supply)
            db.session.flush()

            total = 0.0
            for pid, qty, price in items_data:
                p = Product.query.get(pid)
                if not p:
                    continue

                p.stock += qty
                p.wholesale_price = price

                line_total = qty * price
                total += line_total

                db.session.add(SupplyItem(
                    supply_id=supply.id,
                    product_id=p.id,
                    product_name=p.name,
                    quantity=qty,
                    purchase_price=price,
                ))

            supply.total = total
            db.session.commit()

            flash(f'Оприходование сохранено на сумму {total:.2f} ₽', 'success')
            return redirect(url_for('admin_supply_view', sid=supply.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'error')

    return render_template('admin/supply_form.html',
                           products=products,
                           now_date=datetime.utcnow().strftime('%Y-%m-%d'))


@app.route('/admin/supplies/<int:sid>')
@login_required
@admin_required
def admin_supply_view(sid):
    supply = Supply.query.get_or_404(sid)
    return render_template('admin/supply_view.html', supply=supply)


@app.route('/admin/supplies/<int:sid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_supply_delete(sid):
    supply = Supply.query.get_or_404(sid)
    try:
        for item in supply.items:
            if item.product:
                item.product.stock -= item.quantity
        db.session.delete(supply)
        db.session.commit()
        flash('Оприходование удалено (остатки пересчитаны)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {e}', 'error')
    return redirect(url_for('admin_supplies'))


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


@app.route('/admin/users/<int:uid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_user_edit(uid):
    u = User.query.get_or_404(uid)

    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name', '').strip()
            username = request.form.get('username', '').strip()
            new_password = request.form.get('password', '').strip()
            role = request.form.get('role', 'cashier')

            if not full_name or not username:
                flash('Заполните ФИО и логин', 'error')
                return redirect(url_for('admin_user_edit', uid=uid))

            existing = User.query.filter(User.username == username, User.id != uid).first()
            if existing:
                flash('Такой логин уже занят', 'error')
                return redirect(url_for('admin_user_edit', uid=uid))

            u.full_name = full_name
            u.username = username
            u.role = role

            if new_password:
                u.set_password(new_password)

            db.session.commit()
            flash('Пользователь обновлён', 'success')
            return redirect(url_for('admin_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'error')

    return render_template('admin/user_form.html', user=u)


@app.route('/admin/users/<int:uid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_user_delete(uid):
    u = User.query.get_or_404(uid)

    if u.id == current_user.id:
        flash('Нельзя удалить себя', 'error')
        return redirect(url_for('admin_users'))

    if u.role == 'admin':
        admins_count = User.query.filter_by(role='admin', is_active_user=True).count()
        if admins_count <= 1:
            flash('Нельзя удалить последнего администратора', 'error')
            return redirect(url_for('admin_users'))

    has_sales = Sale.query.filter_by(cashier_id=u.id).first() is not None
    has_shifts = Shift.query.filter_by(cashier_id=u.id).first() is not None

    if has_sales or has_shifts:
        u.is_active_user = False
        db.session.commit()
        flash('У пользователя есть история продаж/смен — он переведён в архив (заблокирован)', 'success')
    else:
        db.session.delete(u)
        db.session.commit()
        flash('Пользователь удалён', 'success')

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

    top = db.session.query(
        SaleItem.product_name,
        func.sum(SaleItem.quantity).label('qty'),
        func.sum(SaleItem.price * SaleItem.quantity).label('sum')
    ).join(Sale).filter(Sale.created_at >= start)\
     .group_by(SaleItem.product_name)\
     .order_by(func.sum(SaleItem.quantity).desc()).limit(10).all()

    return render_template('admin/reports.html',
                           sales=sales, total=total, period=period, top=top)


# ----- Отчёт о прибыли -----
@app.route('/admin/profit')
@login_required
@admin_required
def admin_profit():
    """Отчёт о прибыли: выручка − себестоимость по каждому товару."""
    from collections import defaultdict

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

    sales = Sale.query.filter(Sale.created_at >= start).all()

    stats = defaultdict(lambda: {'qty': 0, 'revenue': 0.0, 'cost': 0.0})
    total_revenue = 0.0
    total_cost = 0.0

    for sale in sales:
        discount_factor = 1 - (sale.discount or 0) / 100
        for item in sale.items:
            revenue = item.price * item.quantity * discount_factor
            cost = (item.cost_price or 0) * item.quantity

            stats[item.product_name]['qty'] += item.quantity
            stats[item.product_name]['revenue'] += revenue
            stats[item.product_name]['cost'] += cost

            total_revenue += revenue
            total_cost += cost

    total_profit = total_revenue - total_cost
    margin = (total_profit / total_revenue * 100) if total_revenue else 0

    items_list = []
    for name, s in stats.items():
        profit = s['revenue'] - s['cost']
        item_margin = (profit / s['revenue'] * 100) if s['revenue'] else 0
        items_list.append({
            'name': name,
            'qty': s['qty'],
            'revenue': s['revenue'],
            'cost': s['cost'],
            'profit': profit,
            'margin': item_margin,
        })
    items_list.sort(key=lambda x: x['profit'], reverse=True)

    return render_template('admin/profit.html',
                           items=items_list,
                           total_revenue=total_revenue,
                           total_cost=total_cost,
                           total_profit=total_profit,
                           margin=margin,
                           period=period,
                           sales_count=len(sales))


# ----- Смены (админ) -----
@app.route('/admin/shifts')
@login_required
@admin_required
def admin_shifts():
    shifts = Shift.query.order_by(Shift.opened_at.desc()).limit(100).all()
    return render_template('admin/shifts.html', shifts=shifts)


# =====================================================
#                    СМЕНЫ КАССИРА
# =====================================================
@app.route('/shift/open', methods=['GET', 'POST'])
@login_required
@cashier_required
def shift_open():
    existing = Shift.query.filter_by(cashier_id=current_user.id, closed_at=None).first()
    if existing:
        return redirect(url_for('cashier_pos'))

    if request.method == 'POST':
        try:
            opening = float(request.form.get('opening_cash', 0) or 0)
            shift = Shift(cashier_id=current_user.id, opening_cash=opening)
            db.session.add(shift)
            db.session.commit()
            flash(f'Смена открыта. Разменный фонд: {opening:.2f} ₽', 'success')
            return redirect(url_for('cashier_pos'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'error')

    return render_template('cashier/shift_open.html')


@app.route('/shift/close', methods=['GET', 'POST'])
@login_required
@cashier_required
def shift_close():
    shift = Shift.query.filter_by(cashier_id=current_user.id, closed_at=None).first()
    if not shift:
        flash('Нет открытой смены', 'error')
        return redirect(url_for('cashier_pos'))

    cash_sales = db.session.query(func.sum(Sale.total)).filter(
        Sale.shift_id == shift.id, Sale.payment_method == 'cash'
    ).scalar() or 0
    expected_cash = round(shift.opening_cash + cash_sales, 2)

    if request.method == 'POST':
        try:
            closing = float(request.form.get('closing_cash', 0) or 0)
            shift.closing_cash = closing
            shift.expected_cash = expected_cash
            shift.note = request.form.get('note', '').strip()
            shift.closed_at = datetime.utcnow()
            db.session.commit()
            flash('Смена закрыта', 'success')
            return redirect(url_for('shift_report', shift_id=shift.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'error')

    sales = Sale.query.filter_by(shift_id=shift.id).all()
    total_revenue = sum(s.total for s in sales)
    card_revenue = sum(s.total for s in sales if s.payment_method == 'card')
    cash_revenue = sum(s.total for s in sales if s.payment_method == 'cash')

    return render_template('cashier/shift_close.html',
                           shift=shift,
                           sales_count=len(sales),
                           total_revenue=total_revenue,
                           cash_revenue=cash_revenue,
                           card_revenue=card_revenue,
                           expected_cash=expected_cash)


@app.route('/shift/<int:shift_id>/report')
@login_required
@cashier_required
def shift_report(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    if current_user.role != 'admin' and shift.cashier_id != current_user.id:
        abort(403)
    sales = Sale.query.filter_by(shift_id=shift.id).order_by(Sale.created_at).all()
    cash_revenue = sum(s.total for s in sales if s.payment_method == 'cash')
    card_revenue = sum(s.total for s in sales if s.payment_method == 'card')
    diff = None
    if shift.closing_cash is not None and shift.expected_cash is not None:
        diff = round(shift.closing_cash - shift.expected_cash, 2)
    return render_template('cashier/shift_report.html',
                           shift=shift, sales=sales,
                           cash_revenue=cash_revenue,
                           card_revenue=card_revenue,
                           diff=diff)


# =====================================================
#                    КАССИР
# =====================================================
@app.route('/pos')
@login_required
@cashier_required
def cashier_pos():
    shift = Shift.query.filter_by(cashier_id=current_user.id, closed_at=None).first()
    if not shift:
        return redirect(url_for('shift_open'))
    categories = Category.query.all()
    return render_template('cashier/pos.html', categories=categories, shift=shift)


@app.route('/api/products')
@login_required
@cashier_required
def api_products():
    q = request.args.get('q', '').strip()
    cat = request.args.get('category', '').strip()
    query = Product.query.filter(Product.is_active == True, Product.stock > 0)
    if q:
        exact = Product.query.filter(
            Product.barcode == q, Product.is_active == True
        ).first()
        if exact:
            query = query.filter(Product.id == exact.id)
        else:
            query = query.filter(
                db.or_(Product.name.ilike(f'%{q}%'), Product.barcode.ilike(f'%{q}%'))
            )
    if cat:
        query = query.filter(Product.category_id == int(cat))
    products = query.limit(50).all()
    return jsonify([{
        'id': p.id, 'name': p.name, 'price': p.price,
        'stock': p.stock, 'barcode': p.barcode,
        'category': p.category.name if p.category else '',
        'image': p.image
    } for p in products])


@app.route('/api/product/by-barcode/<barcode>')
@login_required
@cashier_required
def api_product_by_barcode(barcode):
    p = Product.query.filter_by(barcode=barcode, is_active=True).first()
    if not p:
        return jsonify({'ok': False}), 404
    return jsonify({
        'ok': True, 'id': p.id, 'name': p.name, 'price': p.price,
        'stock': p.stock, 'barcode': p.barcode,
        'category': p.category.name if p.category else '',
        'image': p.image
    })


@app.route('/api/checkout', methods=['POST'])
@login_required
@cashier_required
def api_checkout():
    shift = Shift.query.filter_by(cashier_id=current_user.id, closed_at=None).first()
    if not shift:
        return jsonify({'ok': False, 'error': 'Смена не открыта'}), 400

    data = request.get_json()
    items = data.get('items', [])
    payment_method = data.get('payment_method', 'cash')
    discount = float(data.get('discount', 0))

    if not items:
        return jsonify({'ok': False, 'error': 'Корзина пуста'}), 400

    try:
        sale = Sale(cashier_id=current_user.id,
                    shift_id=shift.id,
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
            total += p.price * it['qty']
            db.session.add(SaleItem(
                sale_id=sale.id, product_id=p.id,
                product_name=p.name, price=p.price,
                cost_price=p.wholesale_price or 0,
                quantity=it['qty']
            ))

        total_after_discount = round(total * (1 - discount / 100), 2)
        sale.total = total_after_discount
        db.session.commit()

        return jsonify({'ok': True, 'sale_id': sale.id,
                        'total': total_after_discount, 'discount': discount})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/receipt/<int:sale_id>')
@login_required
@cashier_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return render_template('cashier/receipt.html', sale=sale)


# =====================================================
#      АВТО-СОЗДАНИЕ БД ПРИ СТАРТЕ
# =====================================================
def ensure_db():
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', full_name='Администратор', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)

            cashier = User(username='cashier', full_name='Иванова Мария', role='cashier')
            cashier.set_password('cashier123')
            db.session.add(cashier)

            for cat_name in ['Уход за лицом', 'Макияж', 'Парфюм', 'Волосы', 'Ногти']:
                if not Category.query.filter_by(name=cat_name).first():
                    db.session.add(Category(name=cat_name))

            db.session.commit()

            if Product.query.count() == 0:
                cat = Category.query.first()
                demo = [
                    Product(name='Крем для лица увлажняющий', price=890, wholesale_price=580, stock=25,
                            category_id=cat.id, barcode='1000001'),
                    Product(name='Помада матовая красная', price=650, wholesale_price=400, stock=40,
                            barcode='1000002'),
                    Product(name='Тушь для ресниц объёмная', price=720, wholesale_price=460, stock=30,
                            barcode='1000003'),
                    Product(name='Тоник для лица', price=450, wholesale_price=280, stock=50,
                            barcode='1000004'),
                    Product(name='Парфюм женский 50мл', price=3200, wholesale_price=2100, stock=10,
                            barcode='1000005'),
                ]
                db.session.add_all(demo)
                db.session.commit()


ensure_db()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)