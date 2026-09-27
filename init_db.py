from app import app, db
from models import User, Category, Product

with app.app_context():
    db.create_all()

    # Админ
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', full_name='Администратор', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)

    # Кассир
    if not User.query.filter_by(username='cashier').first():
        cashier = User(username='cashier', full_name='Иванова Мария', role='cashier')
        cashier.set_password('cashier123')
        db.session.add(cashier)

    # Категории
    for cat_name in ['Уход за лицом', 'Макияж', 'Парфюм', 'Волосы', 'Ногти']:
        if not Category.query.filter_by(name=cat_name).first():
            db.session.add(Category(name=cat_name))

    db.session.commit()

    # Демо-товары
    if Product.query.count() == 0:
        cat = Category.query.first()
        demo = [
            Product(name='Крем для лица увлажняющий', price=890, stock=25, category_id=cat.id, barcode='1000001'),
            Product(name='Помада матовая красная', price=650, stock=40, barcode='1000002'),
            Product(name='Тушь для ресниц объёмная', price=720, stock=30, barcode='1000003'),
            Product(name='Тоник для лица', price=450, stock=50, barcode='1000004'),
            Product(name='Парфюм женский 50мл', price=3200, stock=10, barcode='1000005'),
        ]
        db.session.add_all(demo)
        db.session.commit()

    print("✅ База данных создана!")
    print("Логин админа:   admin / admin123")
    print("Логин кассира:  cashier / cashier123")