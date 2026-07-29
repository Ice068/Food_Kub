/**
 * Cart class จัดการตะกร้าสินค้าฝั่ง frontend ทั้งหมด
 * เก็บข้อมูลไว้ใน localStorage เพราะโปรเจกต์นี้ไม่มี backend/DB จริง
 */
class Cart {
    constructor(storageKey = "food_cart") {
        this.storageKey = storageKey;
        this.items = this._loadFromStorage();
    }

    // ---------- Storage ----------
    _loadFromStorage() {
        const raw = localStorage.getItem(this.storageKey);
        return raw ? JSON.parse(raw) : [];
    }

    _saveToStorage() {
        localStorage.setItem(this.storageKey, JSON.stringify(this.items));
    }

    // ---------- Core operations ----------
    addItem(id, name, price) {
        const existing = this.items.find((i) => i.id === id);
        if (existing) {
            existing.qty += 1;
        } else {
            this.items.push({ id, name, price, qty: 1 });
        }
        this._saveToStorage();
        this._refreshUI();
        this._toast(`เพิ่ม "${name}" ลงตะกร้าแล้ว`);
    }

    increaseQty(id) {
        const item = this.items.find((i) => i.id === id);
        if (item) item.qty += 1;
        this._saveToStorage();
        this._refreshUI();
    }

    decreaseQty(id) {
        const item = this.items.find((i) => i.id === id);
        if (item) {
            item.qty -= 1;
            if (item.qty <= 0) {
                this.removeItem(id);
                return;
            }
        }
        this._saveToStorage();
        this._refreshUI();
    }

    removeItem(id) {
        this.items = this.items.filter((i) => i.id !== id);
        this._saveToStorage();
        this._refreshUI();
    }

    clearCart() {
        this.items = [];
        this._saveToStorage();
        this._refreshUI();
    }

    getTotal() {
        return this.items.reduce((sum, i) => sum + i.price * i.qty, 0);
    }

    getItemCount() {
        return this.items.reduce((sum, i) => sum + i.qty, 0);
    }

    checkout() {
        if (this.items.length === 0) {
            alert("ตะกร้าว่าง กรุณาเลือกเมนูก่อนสั่งซื้อ");
            return;
        }
        alert(
            `สั่งซื้อสำเร็จ! ยอดรวม ${this.getTotal()} บาท\n(ตัวอย่างนี้ยังไม่เชื่อมระบบชำระเงินจริง)`
        );
        this.clearCart();
        window.location.href = "/";
    }

    // ---------- UI rendering ----------
    _refreshUI() {
        this._updateBadge();
        this._renderCartPage();
    }

    _updateBadge() {
        const badge = document.getElementById("cart-count");
        if (badge) badge.textContent = this.getItemCount();
    }

    _renderCartPage() {
        const container = document.getElementById("cart-container");
        const totalEl = document.getElementById("cart-total");
        if (!container) return; // ไม่ได้อยู่หน้าตะกร้า ไม่ต้อง render

        if (this.items.length === 0) {
            container.innerHTML = `<p class="empty-message">ยังไม่มีสินค้าในตะกร้า</p>`;
        } else {
            container.innerHTML = this.items
                .map(
                    (item) => `
                <div class="cart-item">
                    <div class="cart-item-info">
                        <strong>${item.name}</strong>
                        <span>${item.price} บาท / ชิ้น</span>
                    </div>
                    <div class="cart-item-controls">
                        <button onclick="cart.decreaseQty(${item.id})">-</button>
                        <span>${item.qty}</span>
                        <button onclick="cart.increaseQty(${item.id})">+</button>
                        <button class="btn-remove" onclick="cart.removeItem(${item.id})">ลบ</button>
                    </div>
                </div>`
                )
                .join("");
        }

        if (totalEl) totalEl.textContent = this.getTotal();
    }

    _toast(message) {
        // ระบบแจ้งเตือนแบบง่ายๆ ด้วย DOM
        const toast = document.createElement("div");
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed; bottom: 20px; right: 20px;
            background: #2b8a3e; color: #fff; padding: 12px 18px;
            border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 999; font-size: 0.9rem;
        `;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2000);
    }
}

// สร้าง instance เดียวใช้ทั้งเว็บ (global)
const cart = new Cart();

// อัปเดต badge + render ตะกร้าทันทีที่โหลดหน้า
document.addEventListener("DOMContentLoaded", () => {
    cart._refreshUI();
});
