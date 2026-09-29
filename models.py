from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='cashier')
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.is_active_user


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    barcode = db.Column(db.String(50), unique=True, nullable=True)
    price = db.Column(db.Float, nullable=False, default=0.0)             # розничная
    wholesale_price = db.Column(db.Float, nullable=True)                  # ← ОПТОВАЯ
    stock = db.Column(db.Integer, nullable=False, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(255), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)                       # ← СРОК ГОДНОСТИ
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def expiry_status(self):
        """Возвращает цветовой статус срока годности."""
        if not self.expiry_date:
            return None
        today = datetime.utcnow().date()
        days_left = (self.expiry_date - today).days
        if days_left < 0:
            return 'expired'      # просрочен
        if days_left <= 30:
            return 'critical'     # бордовый — 1 месяц
        if days_left <= 60:
            return 'danger'       # красный — 2 месяца
        if days_left <= 90:
            return 'warning'      # жёлтый — 3 месяца
        return 'ok'               # зелёный — всё хорошо

    @property
    def expiry_days_left(self):
        """Сколько дней осталось до истечения срока."""
        if not self.expiry_date:
            return None
        return (self.expiry_date - datetime.utcnow().date()).days


class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)
    opening_cash = db.Column(db.Float, default=0.0)
    closing_cash = db.Column(db.Float, nullable=True)
    expected_cash = db.Column(db.Float, nullable=True)
    note = db.Column(db.Text, nullable=True)

    cashier = db.relationship('User', backref='shifts')

    @property
    def is_open(self):
        return self.closed_at is None


class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=True)
    total = db.Column(db.Float, nullable=False, default=0.0)
    payment_method = db.Column(db.String(20), default='cash')
    discount = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cashier = db.relationship('User', backref='sales')
    shift = db.relationship('Shift', backref='sales')
    items = db.relationship('SaleItem', backref='sale', cascade='all, delete-orphan')


class SaleItem(db.Model):
    __tablename__ = 'sale_items'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float, nullable=True, default=0.0)   # ← НОВОЕ
    quantity = db.Column(db.Integer, nullable=False, default=1)

    product = db.relationship('Product')

    @property
    def profit(self):
        """Прибыль по этой позиции."""
        return (self.price - (self.cost_price or 0)) * self.quantity

class Supply(db.Model):
    __tablename__ = 'supplies'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    supplier = db.Column(db.String(200), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    total = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    items = db.relationship('SupplyItem', backref='supply', cascade='all, delete-orphan')
    author = db.relationship('User')


class SupplyItem(db.Model):
    __tablename__ = 'supply_items'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    purchase_price = db.Column(db.Float, nullable=False, default=0.0)

    product = db.relationship('Product')

    @property
    def line_total(self):
        return self.quantity * self.purchase_price