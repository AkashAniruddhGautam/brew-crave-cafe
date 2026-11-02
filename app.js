let menu = [];
    const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
    const TAX_RATE = 0.05;
    const CAFE_TIME_ZONE = "Asia/Kolkata";
    const DEFAULT_CATEGORIES = ["All items", "Coffee", "Cold drinks", "Tea", "Bakery"];
    let activeCategory = "All items";
    let searchTerm = "";
    let cart = new Map();
    let orderMode = "Dine in";
    let paymentMethod = "Cash";
    let csrfToken = "";
    let currentUser = null;
    let editingProductId = null;
    let whatsappOrder = null;
    let serverClockOffsetMs = 0;
    let clockSyncWarningShown = false;
    let toastTimer;

    function formatMoney(amount) { return currency.format(amount); }
    function formatCafeTime(date, options) {
      return date.toLocaleTimeString("en-IN", { ...options, timeZone: CAFE_TIME_ZONE });
    }
    function formatCafeDate(date, options) {
      return date.toLocaleDateString("en-IN", { ...options, timeZone: CAFE_TIME_ZONE });
    }
    function formatCafeDateTime(date, options) {
      return date.toLocaleString("en-IN", { ...options, timeZone: CAFE_TIME_ZONE });
    }
    function normalizeWhatsappNumber(value) {
      const input = value.trim();
      if (!/^\+?[\d\s()-]+$/.test(input)) return null;
      let digits = input.replace(/\D/g, "");
      if (digits.length === 10) digits = `91${digits}`;
      else if (digits.length === 11 && digits.startsWith("0")) digits = `91${digits.slice(1)}`;
      if (digits.length < 11 || digits.length > 15 || digits.startsWith("0")) return null;
      return digits;
    }
    function syncServerClock(serverTime) {
      const serverTimeMs = Date.parse(serverTime);
      if (!Number.isFinite(serverTimeMs)) throw new Error("The server returned an invalid time.");
      serverClockOffsetMs = serverTimeMs - Date.now();
      clockSyncWarningShown = false;
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[character]);
    }
    async function apiRequest(path, options = {}) {
      const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
      if (csrfToken && !["GET", "HEAD"].includes(options.method || "GET")) headers["X-CSRF-Token"] = csrfToken;
      const response = await fetch(path, { ...options, headers, credentials: "same-origin", cache: "no-store" });
      const result = await response.json().catch(() => ({}));
      if (response.status === 401 && currentUser) {
        currentUser = null;
        csrfToken = "";
        showAuth("login", "Your session ended. Please sign in again.");
      }
      if (!response.ok) throw new Error(result.error || "The request could not be completed.");
      return result;
    }
    function showToast(message) {
      const toast = document.getElementById("toast");
      toast.textContent = message;
      toast.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove("show"), 2300);
    }
    function showAuth(mode, message = "") {
      document.getElementById("app-shell").hidden = true;
      document.getElementById("auth-screen").hidden = false;
      document.getElementById("login-card").hidden = mode !== "login";
      document.getElementById("setup-card").hidden = mode !== "setup";
      document.getElementById(mode === "setup" ? "setup-error" : "login-error").textContent = message;
    }
    async function enterApp(user, token) {
      currentUser = user;
      csrfToken = token;
      if (window.location.pathname === "/admin" && user.role !== "owner") {
        window.history.replaceState(null, "", "/");
        showToast("Admin access is available to the owner only.");
      }
      menu = await apiRequest("/api/menu");
      document.getElementById("user-name").textContent = user.username;
      document.getElementById("user-role").textContent = user.role === "owner" ? "Owner" : "Staff";
      document.getElementById("user-avatar").textContent = user.username.slice(0, 2).toUpperCase();
      document.getElementById("nav-admin").hidden = user.role !== "owner";
      document.getElementById("auth-screen").hidden = true;
      document.getElementById("app-shell").hidden = false;
      switchView("pos");
      renderCategories();
      renderMenu();
      renderCart();
      if (window.location.pathname === "/admin" && user.role === "owner") switchView("admin");
    }
    function getCategories() {
      return [...new Set([...DEFAULT_CATEGORIES, ...menu.map(item => item.category)])];
    }
    function renderCategories() {
      document.getElementById("categories").innerHTML = getCategories().map(category =>
        `<button class="category ${activeCategory === category ? "active" : ""}" data-category="${escapeHtml(category)}">${escapeHtml(category)}</button>`
      ).join("");
    }
    function renderMenu() {
      const filtered = menu.filter(item =>
        (activeCategory === "All items" || item.category === activeCategory) &&
        `${item.name} ${item.category}`.toLowerCase().includes(searchTerm)
      );
      document.getElementById("menu-count").textContent = `${filtered.length} delicious choices`;
      document.getElementById("product-grid").innerHTML = filtered.length ? filtered.map(item => `
        <button class="product" data-product="${escapeHtml(item.id)}" aria-label="Add ${escapeHtml(item.name)}, ${formatMoney(item.price)}">
          <span class="product-art art-${escapeHtml(item.art)}"><span class="product-emoji">${escapeHtml(item.emoji)}</span></span>
          <span class="product-name">${escapeHtml(item.name)}</span>
          <span class="product-type">${escapeHtml(item.type)}</span>
          <span class="product-bottom"><span class="product-price">${formatMoney(item.price)}</span><span class="add-icon">＋</span></span>
        </button>
      `).join("") : '<div class="empty-menu">No menu items match your search.</div>';
    }
    function getTotals() {
      const subtotal = Array.from(cart.values()).reduce((sum, item) => sum + item.product.price * item.quantity, 0);
      const tax = Math.round(subtotal * TAX_RATE * 100) / 100;
      return { subtotal, tax, total: subtotal + tax };
    }
    function renderCart() {
      const cartItems = document.getElementById("cart-items");
      const entries = Array.from(cart.values());
      if (!entries.length) {
        cartItems.innerHTML = '<div class="empty-cart"><div><div class="empty-cart-icon">🛍️</div>Your order is looking a little empty.<br>Add something delicious!</div></div>';
      } else {
        cartItems.innerHTML = entries.map(({ product, quantity }) => `
          <div class="cart-item">
            <div><div class="cart-item-name">${escapeHtml(product.name)}</div><div class="cart-item-price">${formatMoney(product.price)} each</div>
              <div class="quantity"><button class="qty-button" data-qty="-1" data-id="${escapeHtml(product.id)}" aria-label="Remove one ${escapeHtml(product.name)}">−</button><span class="qty-value">${quantity}</span><button class="qty-button" data-qty="1" data-id="${escapeHtml(product.id)}" aria-label="Add one ${escapeHtml(product.name)}">＋</button></div>
            </div>
            <div class="cart-item-total">${formatMoney(product.price * quantity)}</div>
          </div>
        `).join("");
      }
      const totals = getTotals();
      document.getElementById("subtotal").textContent = formatMoney(totals.subtotal);
      document.getElementById("tax").textContent = formatMoney(totals.tax);
      document.getElementById("total").textContent = formatMoney(totals.total);
      const chargeButton = document.getElementById("charge-button");
      chargeButton.textContent = `Complete bill · ${formatMoney(totals.total)}`;
      chargeButton.disabled = cart.size === 0;
    }
    function updateClock() {
      const now = new Date(Date.now() + serverClockOffsetMs);
      const time = formatCafeTime(now, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const localTime = new Intl.DateTimeFormat("en-IN", {
        timeZone: CAFE_TIME_ZONE, hour: "2-digit", minute: "2-digit", hourCycle: "h23"
      }).formatToParts(now);
      const localHour = Number(localTime.find(part => part.type === "hour").value);
      const localMinute = Number(localTime.find(part => part.type === "minute").value);
      const minuteOfDay = localHour * 60 + localMinute;
      const cafeIsOpen = minuteOfDay >= 9 * 60 && minuteOfDay < 22 * 60;
      document.getElementById("clock").textContent = `${time} IST`;
      document.getElementById("order-clock").textContent = formatCafeTime(now, { hour: "2-digit", minute: "2-digit" });
      document.getElementById("today-date").textContent = formatCafeDate(now, { day: "numeric", month: "long", year: "numeric" });
      document.getElementById("today-weekday").textContent = formatCafeDate(now, { weekday: "long" });
      document.getElementById("cafe-status").textContent = cafeIsOpen ? "Cafe is open" : "Cafe is closed";
      document.getElementById("cafe-status-dot").classList.toggle("live-dot-closed", !cafeIsOpen);
      document.getElementById("open-hours").textContent = "Today · 9:00 AM – 10:00 PM IST";
    }
    async function refreshServerClock() {
      try {
        const result = await apiRequest("/api/clock");
        syncServerClock(result.server_time);
        updateClock();
      } catch (error) {
        console.error("Could not synchronize the cafe clock.", error);
        if (!clockSyncWarningShown && currentUser) {
          showToast("Could not sync time with the server; showing device time.");
          clockSyncWarningShown = true;
        }
      }
    }
    function addToCart(id) {
      const product = menu.find(item => item.id === id);
      if (!product) return;
      const entry = cart.get(id);
      cart.set(id, { product, quantity: (entry?.quantity || 0) + 1 });
      renderCart();
    }
    function adjustQuantity(id, amount) {
      const entry = cart.get(id);
      if (!entry) return;
      const quantity = entry.quantity + amount;
      if (quantity <= 0) cart.delete(id);
      else cart.set(id, { ...entry, quantity });
      renderCart();
    }
    function switchView(view) {
      if (view === "admin" && currentUser?.role !== "owner") view = "pos";
      const showingHistory = view === "history";
      const showingAdmin = view === "admin";
      document.getElementById("pos-view").hidden = showingHistory;
      document.getElementById("history-view").hidden = !showingHistory;
      document.getElementById("admin-view").hidden = !showingAdmin;
      document.getElementById("page-title").textContent = showingHistory ? "A little look back" : showingAdmin ? "Cafe admin panel" : "Let's take an order";
      document.getElementById("nav-pos").classList.toggle("active", !showingHistory && !showingAdmin);
      document.getElementById("nav-history").classList.toggle("active", showingHistory);
      document.getElementById("nav-admin").classList.toggle("active", showingAdmin);
      if (showingHistory) renderHistory();
      if (showingAdmin) {
        renderUsers();
        renderProducts();
      }
    }
    async function renderHistory() {
      const body = document.getElementById("history-body");
      body.innerHTML = '<tr><td class="history-empty" colspan="6">Loading order history…</td></tr>';
      let orders;
      try {
        orders = await apiRequest("/api/orders");
      } catch (error) {
        body.innerHTML = '<tr><td class="history-empty" colspan="6">Order history could not be loaded.</td></tr>';
        showToast(error.message);
        return;
      }
      if (!orders.length) {
        body.innerHTML = '<tr><td class="history-empty" colspan="6">No orders yet. Your completed orders will show up here.</td></tr>';
        return;
      }
      body.innerHTML = orders.map(order => `
        <tr><td><div class="history-id">${escapeHtml(order.id)}</div><div class="history-meta">${order.items.reduce((sum, item) => sum + item.quantity, 0)} items</div></td>
          <td>${formatCafeDateTime(new Date(order.timestamp), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
          <td>${escapeHtml(order.mode)}</td><td>${escapeHtml(order.payment)}</td><td><span class="paid-pill">Paid</span></td><td class="history-total">${formatMoney(order.total)}</td></tr>
      `).join("");
    }
    function showReceipt(order) {
      whatsappOrder = order;
      const rows = order.items.map(item => `<div class="receipt-row"><span>${escapeHtml(item.name)} × ${item.quantity}</span><span>${formatMoney(item.price * item.quantity)}</span></div>`).join("");
      document.getElementById("receipt-content").innerHTML = `
        <div class="receipt-top"><div class="receipt-logo">☕</div><h2>Brew &amp; Crave Cafe</h2><div class="receipt-muted"><em>Where every sip meets your sweetest craving</em></div><div class="receipt-address">C4 G8A Shop, Janakpuri, New Delhi - 110058<br><span class="receipt-landmark">Landmark: Near Tihar Jail Gate Number 4</span></div><div class="receipt-muted receipt-visit-note">Thank you for stopping by!</div></div>
        <div class="receipt-meta"><span>${escapeHtml(order.id)}</span><span>${formatCafeDateTime(new Date(order.timestamp), { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })} IST</span></div>
        <div class="receipt-meta"><span>${escapeHtml(order.mode)}</span><span>Paid via ${escapeHtml(order.payment)}</span></div>
        <div class="receipt-items">${rows}<div class="receipt-row"><span>Subtotal</span><span>${formatMoney(order.subtotal)}</span></div><div class="receipt-row"><span>GST (5%)</span><span>${formatMoney(order.tax)}</span></div><div class="receipt-row receipt-total"><span>Total paid</span><span>${formatMoney(order.total)}</span></div></div>
        <div class="receipt-thanks">Made fresh, just for you ♡</div>
        <div class="receipt-actions"><button class="done-button" id="close-receipt">Done</button><button class="print-button" id="print-receipt">Print receipt</button></div>
        <button class="whatsapp-button" id="send-whatsapp" type="button">◉ &nbsp;Send bill on WhatsApp</button>
      `;
      document.getElementById("receipt-overlay").classList.add("open");
    }
    async function renderUsers() {
      const body = document.getElementById("staff-body");
      body.innerHTML = '<tr><td colspan="4">Loading staff accounts…</td></tr>';
      try {
        const users = await apiRequest("/api/users");
        body.replaceChildren();
        users.forEach(user => {
          body.insertAdjacentHTML("beforeend", `
            <tr><td>${escapeHtml(user.username)}</td><td>${user.role === "owner" ? "Owner" : "Staff"}</td>
            <td>${user.active ? "Active" : "Disabled"}</td><td>${user.role === "staff" ? `
              <button class="staff-toggle" data-user-id="${user.id}" data-active="${!user.active}">${user.active ? "Disable" : "Enable"}</button>` : "—"}</td></tr>
          `);
        });
      } catch (error) {
        body.innerHTML = '<tr><td colspan="4">Staff accounts could not be loaded.</td></tr>';
        showToast(error.message);
      }
    }
    async function renderProducts() {
      const body = document.getElementById("products-body");
      body.innerHTML = '<tr><td colspan="5">Loading products…</td></tr>';
      try {
        const products = await apiRequest("/api/products");
        if (!products.length) {
          body.innerHTML = '<tr><td colspan="5">No products yet. Add the first item using the form.</td></tr>';
          return;
        }
        body.innerHTML = products.map(product => `
          <tr><td><div class="admin-product-name"><span class="admin-product-emoji">${escapeHtml(product.emoji)}</span><span>${escapeHtml(product.name)}</span></div></td>
          <td>${escapeHtml(product.category)}</td><td>${formatMoney(product.price)}</td><td>${product.active ? "Available" : "Hidden"}</td>
          <td><div class="admin-actions"><button class="staff-toggle" data-edit-product="${escapeHtml(product.id)}">Edit</button>
          <button class="staff-toggle" data-product-id="${escapeHtml(product.id)}" data-active="${!product.active}">${product.active ? "Hide" : "Show"}</button></div></td></tr>
        `).join("");
      } catch (error) {
        body.innerHTML = '<tr><td colspan="5">Products could not be loaded.</td></tr>';
        showToast(error.message);
      }
    }
    async function refreshMenuAndCart() {
      const updatedMenu = await apiRequest("/api/menu");
      const currentProducts = new Map(updatedMenu.map(product => [product.id, product]));
      let removedItems = false;
      for (const [id, entry] of cart) {
        const updatedProduct = currentProducts.get(id);
        if (updatedProduct) cart.set(id, { ...entry, product: updatedProduct });
        else {
          cart.delete(id);
          removedItems = true;
        }
      }
      menu = updatedMenu;
      if (!getCategories().includes(activeCategory)) activeCategory = "All items";
      renderCategories();
      renderMenu();
      renderCart();
      if (removedItems) showToast("Unavailable products were removed from the current order.");
    }
    function resetProductForm() {
      editingProductId = null;
      document.getElementById("product-form").reset();
      document.getElementById("product-form-title").textContent = "Add a product";
      document.getElementById("product-submit").textContent = "Add product";
      document.getElementById("product-cancel").hidden = true;
      document.getElementById("product-error").textContent = "";
    }
    async function editProduct(productId) {
      try {
        const products = await apiRequest("/api/products");
        const product = products.find(item => item.id === productId);
        if (!product) throw new Error("Product was not found.");
        editingProductId = product.id;
        document.getElementById("product-name").value = product.name;
        document.getElementById("product-category").value = product.category;
        document.getElementById("product-price").value = product.price.toFixed(2);
        document.getElementById("product-emoji").value = product.emoji;
        document.getElementById("product-art").value = product.art;
        document.getElementById("product-type").value = product.type;
        document.getElementById("product-form-title").textContent = "Edit product";
        document.getElementById("product-submit").textContent = "Save changes";
        document.getElementById("product-cancel").hidden = false;
        document.getElementById("product-name").focus();
      } catch (error) {
        showToast(error.message);
      }
    }

    document.getElementById("categories").addEventListener("click", event => {
      const button = event.target.closest("[data-category]");
      if (!button) return;
      activeCategory = button.dataset.category;
      renderCategories();
      renderMenu();
    });
    document.getElementById("product-grid").addEventListener("click", event => {
      const product = event.target.closest("[data-product]");
      if (product) addToCart(product.dataset.product);
    });
    document.getElementById("search").addEventListener("input", event => {
      searchTerm = event.target.value.trim().toLowerCase();
      renderMenu();
    });
    document.getElementById("cart-items").addEventListener("click", event => {
      const button = event.target.closest("[data-qty]");
      if (button) adjustQuantity(button.dataset.id, Number(button.dataset.qty));
    });
    document.getElementById("clear-order").addEventListener("click", () => {
      if (!cart.size) return;
      cart.clear();
      renderCart();
      showToast("Order cleared.");
    });
    document.querySelectorAll(".mode-button").forEach(button => button.addEventListener("click", () => {
      orderMode = button.dataset.mode;
      document.querySelectorAll(".mode-button").forEach(option => option.classList.toggle("active", option === button));
    }));
    document.querySelectorAll(".payment-button").forEach(button => button.addEventListener("click", () => {
      paymentMethod = button.dataset.payment;
      document.querySelectorAll(".payment-button").forEach(option => option.classList.toggle("active", option === button));
    }));
    document.querySelectorAll(".nav-button").forEach(button => button.addEventListener("click", () => {
      const view = button.dataset.view;
      const path = view === "admin" ? "/admin" : "/";
      if (window.location.pathname !== path) window.history.pushState(null, "", path);
      switchView(view);
    }));
    window.addEventListener("popstate", () => {
      switchView(window.location.pathname === "/admin" ? "admin" : "pos");
    });
    document.getElementById("back-to-pos").addEventListener("click", () => switchView("pos"));
    document.getElementById("charge-button").addEventListener("click", async event => {
      if (!cart.size) return;
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const order = await apiRequest("/api/orders", {
          method: "POST",
          body: JSON.stringify({
            mode: orderMode,
            payment: paymentMethod,
            items: Array.from(cart.values()).map(({ product, quantity }) => ({ id: product.id, quantity }))
          })
        });
        cart.clear();
        document.getElementById("order-number").textContent = order.id;
        renderCart();
        showReceipt(order);
      } catch (error) {
        showToast(error.message);
      } finally {
        button.disabled = cart.size === 0;
        if (cart.size) renderCart();
      }
    });
    document.getElementById("login-form").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const errorNode = document.getElementById("login-error");
      errorNode.textContent = "";
      try {
        const result = await apiRequest("/api/login", {
          method: "POST",
          body: JSON.stringify({ username: form.username.value, password: form.password.value })
        });
        syncServerClock(result.server_time);
        updateClock();
        form.reset();
        await enterApp(result.user, result.csrf_token);
      } catch (error) {
        errorNode.textContent = error.message;
      }
    });
    document.getElementById("setup-form").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const errorNode = document.getElementById("setup-error");
      errorNode.textContent = "";
      try {
        const result = await apiRequest("/api/setup", {
          method: "POST",
          body: JSON.stringify({ username: form.username.value, password: form.password.value })
        });
        syncServerClock(result.server_time);
        updateClock();
        form.reset();
        await enterApp(result.user, result.csrf_token);
      } catch (error) {
        errorNode.textContent = error.message;
      }
    });
    document.getElementById("logout-button").addEventListener("click", async () => {
      try {
        await apiRequest("/api/logout", { method: "POST", body: "{}" });
      } catch (error) {
        showToast(error.message);
      }
      currentUser = null;
      csrfToken = "";
      cart.clear();
      showAuth("login", "You have been signed out.");
    });
    document.getElementById("staff-form").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const errorNode = document.getElementById("staff-error");
      errorNode.textContent = "";
      try {
        await apiRequest("/api/users", {
          method: "POST",
          body: JSON.stringify({ username: form.username.value, password: form.password.value })
        });
        form.reset();
        await renderUsers();
        showToast("Staff account created.");
      } catch (error) {
        errorNode.textContent = error.message;
      }
    });
    document.getElementById("staff-body").addEventListener("click", async event => {
      const button = event.target.closest("[data-user-id]");
      if (!button) return;
      button.disabled = true;
      try {
        await apiRequest(`/api/users/${button.dataset.userId}`, {
          method: "PATCH",
          body: JSON.stringify({ active: button.dataset.active === "true" })
        });
        await renderUsers();
        showToast("Staff access updated.");
      } catch (error) {
        button.disabled = false;
        showToast(error.message);
      }
    });
    document.getElementById("product-form").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const errorNode = document.getElementById("product-error");
      errorNode.textContent = "";
      const product = {
        name: form.elements.name.value,
        category: form.elements.category.value,
        price: form.elements.price.value,
        emoji: form.elements.emoji.value,
        art: form.elements.art.value,
        type: form.elements.type.value
      };
      const updatingProduct = Boolean(editingProductId);
      try {
        await apiRequest(editingProductId ? `/api/products/${encodeURIComponent(editingProductId)}` : "/api/products", {
          method: editingProductId ? "PUT" : "POST",
          body: JSON.stringify(product)
        });
        resetProductForm();
        await Promise.all([renderProducts(), refreshMenuAndCart()]);
        showToast(updatingProduct ? "Product updated." : "Product added to the menu.");
      } catch (error) {
        errorNode.textContent = error.message;
      }
    });
    document.getElementById("product-cancel").addEventListener("click", resetProductForm);
    document.getElementById("products-body").addEventListener("click", async event => {
      const editButton = event.target.closest("[data-edit-product]");
      if (editButton) {
        editProduct(editButton.dataset.editProduct);
        return;
      }
      const toggleButton = event.target.closest("[data-product-id]");
      if (!toggleButton) return;
      toggleButton.disabled = true;
      try {
        await apiRequest(`/api/products/${encodeURIComponent(toggleButton.dataset.productId)}`, {
          method: "PATCH",
          body: JSON.stringify({ active: toggleButton.dataset.active === "true" })
        });
        await Promise.all([renderProducts(), refreshMenuAndCart()]);
        showToast(toggleButton.dataset.active === "true" ? "Product is now available." : "Product hidden from the menu.");
      } catch (error) {
        toggleButton.disabled = false;
        showToast(error.message);
      }
    });
    document.getElementById("receipt-overlay").addEventListener("click", event => {
      if (event.target.id === "receipt-overlay" || event.target.id === "close-receipt") {
        document.getElementById("receipt-overlay").classList.remove("open");
      }
      if (event.target.id === "print-receipt") window.print();
      if (event.target.id === "send-whatsapp" && whatsappOrder) {
        document.getElementById("whatsapp-error").textContent = "";
        document.getElementById("whatsapp-dialog").showModal();
        document.getElementById("whatsapp-number").focus();
      }
    });
    document.getElementById("whatsapp-cancel").addEventListener("click", () => {
      document.getElementById("whatsapp-dialog").close();
    });
    document.getElementById("whatsapp-form").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const phone = normalizeWhatsappNumber(form.elements.phone.value);
      const errorNode = document.getElementById("whatsapp-error");
      const submitButton = document.getElementById("whatsapp-submit");
      if (!phone) {
        errorNode.textContent = "Enter a valid number with country code, or a 10-digit Indian number.";
        return;
      }
      if (!whatsappOrder) {
        errorNode.textContent = "This bill is no longer available. Complete the bill again to retry.";
        return;
      }
      const order = whatsappOrder;
      const message = `Hello! Thank you for visiting Brew & Crave Cafe. Your bill ${order.id} is attached.`;
      window.open(`https://wa.me/${phone}?text=${encodeURIComponent(message)}`, "_blank", "noopener,noreferrer");
      submitButton.disabled = true;
      errorNode.textContent = "";
      try {
        const response = await fetch(`/api/orders/${encodeURIComponent(order.id)}/pdf`, {
          credentials: "same-origin",
          cache: "no-store"
        });
        if (!response.ok) {
          const result = await response.json().catch(() => ({}));
          throw new Error(result.error || "The bill PDF could not be created.");
        }
        const pdf = await response.blob();
        const downloadUrl = URL.createObjectURL(pdf);
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.download = `Brew-and-Crave-${order.id}.pdf`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
        document.getElementById("whatsapp-dialog").close();
        showToast("PDF downloaded. Attach it in the WhatsApp chat and press Send.");
      } catch (error) {
        errorNode.textContent = error.message;
      } finally {
        submitButton.disabled = false;
      }
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") document.getElementById("receipt-overlay").classList.remove("open");
    });

    updateClock();
    setInterval(updateClock, 1000);
    setInterval(refreshServerClock, 60000);
    (async function start() {
      try {
        const status = await apiRequest("/api/bootstrap");
        syncServerClock(status.server_time);
        updateClock();
        if (status.setup_required) {
          showAuth("setup");
          return;
        }
        try {
          const result = await apiRequest("/api/me");
          await enterApp(result.user, result.csrf_token);
        } catch (error) {
          if (/sign in/i.test(error.message) || /inactive/i.test(error.message)) showAuth("login", "");
          else showAuth("login", error.message);
        }
      } catch (error) {
        showAuth("login", `Cannot connect to the cafe server. Start it with “python app.py”. ${error.message}`);
      }
    })();
  