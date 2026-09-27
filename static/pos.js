let cart = [];

// ---------- Поиск товаров ----------
const searchInput = document.getElementById('searchInput');
const categoryFilter = document.getElementById('categoryFilter');
const productsGrid = document.getElementById('productsGrid');

async function loadProducts() {
    const q = searchInput.value.trim();
    const cat = categoryFilter.value;
    const url = `/api/products?q=${encodeURIComponent(q)}&category=${cat}`;
    const res = await fetch(url);
    const products = await res.json();

    productsGrid.innerHTML = products.length
        ? products.map(p => `
            <div class="product-card" onclick="addToCart(${p.id}, '${escape(p.name)}', ${p.price}, ${p.stock})">
                <div class="pname">${escape(p.name)}</div>
                <div class="pcat">${escape(p.category)}</div>
                <div class="pprice">${p.price.toFixed(2)} ₽</div>
                <div class="pstock">Остаток: ${p.stock}</div>
            </div>
        `).join('')
        : '<div class="empty">Ничего не найдено</div>';
}

function escape(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

let searchTimeout;
searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(loadProducts, 200);
});
categoryFilter.addEventListener('change', loadProducts);

// ---------- Корзина ----------
function addToCart(id, name, price, maxStock) {
    const existing = cart.find(i => i.id === id);
    if (existing) {
        if (existing.qty < maxStock) existing.qty++;
        else alert('Достигнут максимум на складе');
    } else {
        cart.push({ id, name, price, qty: 1, maxStock });
    }
    renderCart();
}

function changeQty(id, delta) {
    const item = cart.find(i => i.id === id);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) cart = cart.filter(i => i.id !== id);
    else if (item.qty > item.maxStock) item.qty = item.maxStock;
    renderCart();
}

function renderCart() {
    const list = document.getElementById('cartList');
    if (!cart.length) {
        list.innerHTML = '<div class="empty">Добавьте товары</div>';
    } else {
        list.innerHTML = cart.map(i => `
            <div class="cart-item">
                <div class="cname">${i.name}</div>
                <div class="cqty">
                    <button onclick="changeQty(${i.id}, -1)">−</button>
                    <span>${i.qty}</span>
                    <button onclick="changeQty(${i.id}, 1)">+</button>
                </div>
                <div class="csum">${(i.price * i.qty).toFixed(2)} ₽</div>
            </div>
        `).join('');
    }
    updateTotal();
}

function updateTotal() {
    const subtotal = cart.reduce((s, i) => s + i.price * i.qty, 0);
    const discount = parseFloat(document.getElementById('discountInput').value) || 0;
    const total = subtotal * (1 - discount / 100);
    document.getElementById('totalAmount').textContent = total.toFixed(2);
}

document.getElementById('discountInput').addEventListener('input', updateTotal);

// ---------- Оформление ----------
document.getElementById('checkoutBtn').addEventListener('click', async () => {
    if (!cart.length) { alert('Корзина пуста'); return; }

    const payment_method = document.querySelector('input[name="pay"]:checked').value;
    const discount = parseFloat(document.getElementById('discountInput').value) || 0;

    const res = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            items: cart.map(i => ({ id: i.id, qty: i.qty })),
            payment_method,
            discount
        })
    });
    const data = await res.json();
    if (data.ok) {
        window.location.href = `/receipt/${data.sale_id}`;
    } else {
        alert('Ошибка: ' + data.error);
    }
});

// Загрузка при старте
loadProducts();