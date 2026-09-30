let cart = [];

const barcodeInput = document.getElementById('barcodeInput');
const categoryFilter = document.getElementById('categoryFilter');
const productsGrid = document.getElementById('productsGrid');

// ---------- Загрузка товаров ----------
async function loadProducts() {
    const q = barcodeInput.value.trim();
    const cat = categoryFilter.value;
    const res = await fetch(`/api/products?q=${encodeURIComponent(q)}&category=${cat}`);
    const products = await res.json();

    productsGrid.innerHTML = products.length
        ? products.map(p => {
            const img = p.image
                ? `<img src="/static/uploads/${p.image}" class="pimg" alt="">`
                : `<div class="pimg pimg-empty">f</div>`;
            return `
                <div class="product-card" onclick="addToCart(${p.id}, '${escape(p.name)}', ${p.price}, ${p.stock})">
                    ${img}
                    <div class="pname">${escape(p.name)}</div>
                    <div class="pcat">${escape(p.category)}</div>
                    <div class="pprice">${p.price.toFixed(2)} ₽</div>
                    <div class="pstock">Остаток: ${p.stock}</div>
                </div>`;
        }).join('')
        : '<div class="empty">Ничего не найдено</div>';
}

function escape(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

// ---------- Ввод с клавиатуры / сканера ----------
let searchTimeout;

barcodeInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(loadProducts, 250);
});

barcodeInput.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        const code = barcodeInput.value.trim();
        if (!code) return;

        // 1. пробуем найти по штрихкоду
        const res = await fetch(`/api/product/by-barcode/${encodeURIComponent(code)}`);
        if (res.ok) {
            const p = await res.json();
            addToCart(p.id, p.name, p.price, p.stock);
            barcodeInput.value = '';
            loadProducts();
            return;
        }

        // 2. если по штрихкоду не нашли, а в списке ровно 1 товар — добавляем его
        const single = productsGrid.querySelectorAll('.product-card');
        if (single.length === 1) {
            single[0].click();
            barcodeInput.value = '';
            loadProducts();
        } else if (single.length === 0) {
            barcodeInput.classList.add('shake');
            setTimeout(() => barcodeInput.classList.remove('shake'), 400);
        }
    }
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

document.getElementById('checkoutBtn').addEventListener('click', async () => {
    if (!cart.length) { alert('Корзина пуста'); return; }
    const payment_method = document.querySelector('input[name="pay"]:checked').value;
    const discount = parseFloat(document.getElementById('discountInput').value) || 0;

    const res = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            items: cart.map(i => ({ id: i.id, qty: i.qty })),
            payment_method, discount
        })
    });
    const data = await res.json();
    if (data.ok) window.location.href = `/receipt/${data.sale_id}`;
    else alert('Ошибка: ' + data.error);
});

// автофокус на поле ввода, чтобы сканер всегда попадал
document.addEventListener('click', () => barcodeInput.focus());

loadProducts();