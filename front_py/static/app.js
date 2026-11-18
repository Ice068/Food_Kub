/* Progressive enhancement: server forms remain the source of truth. */
(() => {
  'use strict';
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const tableQuery = document.body.dataset.tableQuery || '';
  const money = value => `฿${Number(value || 0).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const reducedMotion = () => document.documentElement.dataset.motion === 'reduce' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const storage = {
    get(key, fallback) { try { return localStorage.getItem(`foodkub.${key}`) ?? fallback; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(`foodkub.${key}`, value); } catch { /* Preferences remain available for this visit. */ } }
  };
  function svg(name) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    node.classList.add('icon'); node.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(node.namespaceURI, 'use');
    use.setAttribute('href', `#icon-${name}`); node.append(use); return node;
  }
  function element(tag, className, text) {
    const node = document.createElement(tag); if (className) node.className = className;
    if (text !== undefined) node.textContent = text; return node;
  }

  // Toasts are capped, keyboard dismissible, pause on hover/focus, and support swiping.
  const toastCleanups = new WeakMap();
  function toast(message, type = 'success') {
    const region = $('#toast-region'); if (!region) return;
    if (region.children.length >= 4) {
      const oldest = region.firstElementChild;
      toastCleanups.get(oldest)?.(); oldest.remove();
    }
    const node = element('div', 'glass-toast'); node.dataset.type = type;
    const symbol = element('span', 'toast-symbol'); symbol.append(svg(type === 'error' ? 'info' : 'check'));
    const close = element('button', 'icon-button'); close.type = 'button'; close.setAttribute('aria-label', 'ปิดการแจ้งเตือน'); close.append(svg('x'));
    const progress = element('span', 'toast-progress'); progress.setAttribute('aria-hidden', 'true');
    node.append(symbol, element('span', '', String(message)), close, progress); region.append(node);
    let timer; let started = performance.now(); let remaining = 5000; let pointerStart = null; let dismissed = false; let paused = false;
    toastCleanups.set(node, () => { clearTimeout(timer); dismissed = true; });
    const dismiss = () => {
      if (dismissed) return;
      clearTimeout(timer); dismissed = true;
      if (reducedMotion()) { node.remove(); return; }
      node.animate([{ opacity: 1, transform: 'translateX(0)' }, { opacity: 0, transform: 'translateX(35px)' }], { duration: 180 }).finished.then(() => node.remove()).catch(() => node.remove());
    };
    const resume = () => { if (dismissed || node.matches(':hover,:focus-within')) return; clearTimeout(timer); paused = false; started = performance.now(); timer = setTimeout(dismiss, remaining); };
    const pause = () => { if (paused) return; clearTimeout(timer); remaining = Math.max(100, remaining - (performance.now() - started)); paused = true; };
    close.addEventListener('click', dismiss); node.addEventListener('pointerenter', pause); node.addEventListener('pointerleave', resume);
    node.addEventListener('focusin', pause); node.addEventListener('focusout', () => queueMicrotask(resume));
    node.addEventListener('pointerdown', event => { pointerStart = event.clientX; });
    node.addEventListener('pointerup', event => { if (pointerStart !== null && Math.abs(event.clientX - pointerStart) > 65) dismiss(); pointerStart = null; });
    resume(); return node;
  }
  window.FoodKub = { toast };

  // Native dialog supplies focus containment and restores focus to its invoker.
  const dialogInvokers = new WeakMap();
  function openDialog(id, invoker) {
    const dialog = document.getElementById(id); if (!dialog || dialog.open) return;
    dialogInvokers.set(dialog, invoker || document.activeElement); dialog.showModal();
    if (id === 'command-dialog') { $('#command-search').value = ''; renderCommands(); }
    requestAnimationFrame(updateIndicators);
  }
  function closeDialog(dialog) { if (dialog?.open) dialog.close(); }
  document.addEventListener('click', event => {
    const opener = event.target.closest('[data-open-dialog]');
    if (opener) { event.preventDefault(); openDialog(opener.dataset.openDialog, opener); }
    const closer = event.target.closest('[data-close-dialog]');
    if (closer) { event.preventDefault(); closeDialog(closer.closest('dialog')); }
  });
  $$('dialog[data-dialog]').forEach(dialog => {
    dialog.addEventListener('click', event => { if (event.target !== dialog) return; const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); });
    dialog.addEventListener('close', () => {
      const invoker = dialogInvokers.get(dialog); dialogInvokers.delete(dialog);
      if (!$('dialog[open]') && invoker?.isConnected) invoker.focus({ preventScroll: true });
    });
  });
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); const existing = $('dialog[open]'); if (existing) existing.close(); openDialog('command-dialog'); }
  });

  // Composited sliding highlights share their parent coordinate system.
  function updateIndicators() {
    $$('.liquid-tabs').forEach(tabs => {
      const indicator = $('.liquid-indicator', tabs); const active = $('.is-active,[aria-selected="true"]', tabs);
      if (!indicator) return;
      if (!active) { indicator.style.setProperty('--pill-width', '0px'); return; }
      indicator.style.setProperty('--pill-x', `${active.offsetLeft}px`); indicator.style.setProperty('--pill-y', `${active.offsetTop}px`);
      indicator.style.setProperty('--pill-width', `${active.offsetWidth}px`); indicator.style.setProperty('--pill-height', `${active.offsetHeight}px`);
    });
  }
  const resizeObserver = new ResizeObserver(updateIndicators); $$('.liquid-tabs').forEach(node => resizeObserver.observe(node));

  function applyTheme(mode) {
    const theme = ['light', 'dark', 'system'].includes(mode) ? mode : 'system';
    document.documentElement.dataset.theme = theme === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme;
    $$('[data-theme-choice]').forEach(button => { const active = button.dataset.themeChoice === theme; button.classList.toggle('is-active', active); button.setAttribute('aria-pressed', String(active)); });
    updateIndicators();
  }
  $$('[data-theme-choice]').forEach(button => button.addEventListener('click', () => { storage.set('theme', button.dataset.themeChoice); applyTheme(button.dataset.themeChoice); }));
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (storage.get('theme', 'system') === 'system') applyTheme('system'); });
  applyTheme(storage.get('theme', 'system'));
  const motionToggle = $('#reduce-motion');
  if (motionToggle) { motionToggle.checked = storage.get('motion', 'system') === 'reduce'; motionToggle.addEventListener('change', () => { const mode = motionToggle.checked ? 'reduce' : 'system'; document.documentElement.dataset.motion = mode; storage.set('motion', mode); }); }

  function readFavorites() {
    try { const raw = JSON.parse(storage.get('favorites', '[]')); return new Set(Array.isArray(raw) ? raw.filter(id => /^\d+$/.test(String(id))).map(String) : []); } catch { return new Set(); }
  }
  let favorites = readFavorites();
  function syncFavorites() {
    $$('[data-favorite]').forEach(button => { const active = favorites.has(button.dataset.favorite); button.setAttribute('aria-pressed', String(active)); const name = button.closest('[data-food-id]')?.dataset.name || ''; button.setAttribute('aria-label', `${active ? 'นำ' : 'บันทึก'} ${name} ${active ? 'ออกจากจานโปรด' : 'เป็นจานโปรด'}`); });
    $$('[data-favorites-count]').forEach(node => { node.textContent = String(favorites.size); });
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-favorite]'); if (!button) return;
    const id = button.dataset.favorite; const existed = favorites.has(id); if (existed) favorites.delete(id); else favorites.add(id);
    storage.set('favorites', JSON.stringify([...favorites])); syncFavorites(); if (onlyFavorites) filterCatalog();
    toast(existed ? 'นำออกจากจานโปรดแล้ว' : 'เก็บจานโปรดไว้ให้แล้ว');
  });
  $('#clear-favorites')?.addEventListener('click', () => { favorites.clear(); storage.set('favorites', '[]'); syncFavorites(); filterCatalog(); toast('ล้างรายการจานโปรดแล้ว'); });
  window.addEventListener('storage', event => { if (event.key === 'foodkub.favorites') { favorites = readFavorites(); syncFavorites(); filterCatalog(); } if (event.key === 'foodkub.theme') applyTheme(storage.get('theme', 'system')); });
  syncFavorites();

  // Multi-criteria catalog filtering, stable sorting, and FLIP list transitions.
  const grid = $('#menu-grid'); const cards = grid ? $$('[data-food-id]', grid) : [];
  const catalog = $$('[data-food-id]').map(card => ({ ...card.dataset }));
  const selectedCategories = new Set([grid?.dataset.selectedCategory].filter(Boolean));
  let onlyFavorites = new URLSearchParams(location.search).get('favorites') === '1';
  const searchInput = $('#menu-search'); const sortInput = $('#menu-sort');
  function filterCatalog(animate = true) {
    if (!grid) return;
    const query = (searchInput?.value || '').trim().toLocaleLowerCase('th-TH');
    const before = new Map(cards.filter(card => !card.hidden).map(card => [card, card.getBoundingClientRect()]));
    const sort = sortInput?.value || 'recommended';
    const ordered = [...cards].sort((a, b) => sort === 'price-asc' ? Number(a.dataset.price) - Number(b.dataset.price) : sort === 'price-desc' ? Number(b.dataset.price) - Number(a.dataset.price) : sort === 'name' ? a.dataset.name.localeCompare(b.dataset.name, 'th') : Number(a.dataset.index) - Number(b.dataset.index));
    let count = 0;
    ordered.forEach(card => {
      const match = (!selectedCategories.size || selectedCategories.has(card.dataset.category)) && (!onlyFavorites || favorites.has(card.dataset.foodId)) && (!query || `${card.dataset.name} ${card.dataset.category}`.toLocaleLowerCase('th-TH').includes(query));
      card.hidden = !match; grid.append(card); if (match) count++;
    });
    if (animate && !reducedMotion()) ordered.filter(card => !card.hidden).forEach(card => {
      const old = before.get(card); const current = card.getBoundingClientRect();
      card.animate(old ? [{ transform: `translate(${old.left - current.left}px,${old.top - current.top}px)`, opacity: 1 }, { transform: 'translate(0,0)', opacity: 1 }] : [{ transform: 'translateY(12px)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1 }], { duration: 330, easing: 'cubic-bezier(.2,.85,.25,1)' });
    });
    $('#visible-count').textContent = String(count); $('#catalog-empty').hidden = count > 0;
    $('#favorites-filter').setAttribute('aria-pressed', String(onlyFavorites));
    $$('.category-chip').forEach(chip => { const active = chip.dataset.category ? selectedCategories.has(chip.dataset.category) : !selectedCategories.size; chip.classList.toggle('is-active', active); chip.removeAttribute('aria-current'); chip.setAttribute('role', 'button'); chip.setAttribute('aria-pressed', String(active)); });
    $('.category-bar').dataset.multi = String(selectedCategories.size > 1);
    const hasFilters = Boolean(query || selectedCategories.size || onlyFavorites); $('#active-filters').hidden = !hasFilters;
    $('#filter-description').textContent = [...selectedCategories, onlyFavorites ? 'จานโปรด' : '', query ? `“${query}”` : ''].filter(Boolean).join(' · ');
    updateIndicators();
  }
  function resetFilters() { selectedCategories.clear(); onlyFavorites = false; if (searchInput) searchInput.value = ''; filterCatalog(); }
  $$('.category-chip').forEach(chip => {
    chip.addEventListener('click', event => {
      if (!grid || event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault(); const value = chip.dataset.category;
      if (!value) selectedCategories.clear(); else if (selectedCategories.has(value)) selectedCategories.delete(value); else selectedCategories.add(value);
      filterCatalog();
    });
    chip.addEventListener('keydown', event => { if (event.key === ' ') { event.preventDefault(); chip.click(); } });
  });
  searchInput?.addEventListener('input', () => filterCatalog()); sortInput?.addEventListener('change', () => filterCatalog());
  $('#favorites-filter')?.addEventListener('click', () => { onlyFavorites = !onlyFavorites; filterCatalog(); });
  $('#reset-filters')?.addEventListener('click', resetFilters); $('#empty-reset')?.addEventListener('click', resetFilters);
  $('[data-favorites-nav]')?.addEventListener('click', event => { if (!grid || event.metaKey || event.ctrlKey) return; event.preventDefault(); onlyFavorites = true; selectedCategories.clear(); if (searchInput) searchInput.value = ''; filterCatalog(); $('#menu').scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth' }); });
  if (grid) { const query = new URLSearchParams(location.search).get('q'); if (query && searchInput) searchInput.value = query; filterCatalog(false); }

  function showDish(data, invoker) {
    $('#dish-image').src = data.image; $('#dish-image').alt = data.name;
    $('#dish-title').textContent = data.name; $('#dish-category').textContent = data.category;
    $('#dish-price').textContent = money(data.price); const form = $('#dish-add-form');
    form.action = `/cart/add/${encodeURIComponent(data.foodId)}${tableQuery}`; form.dataset.itemName = data.name;
    $('button', form).disabled = data.available === 'false'; $('button', form).classList.remove('is-busy'); openDialog('dish-dialog', invoker);
  }
  document.addEventListener('click', event => { const button = event.target.closest('[data-dish-detail]'); if (button) showDish(button.closest('[data-food-id]').dataset, button); });
  const commands = [{ name: 'เมนูอาหารทั้งหมด', path: '/', icon: 'grid' }, { name: 'ตะกร้าและรายการที่สั่ง', path: '/cart', icon: 'bag' }, { name: 'วงล้อ มื้อนี้กินอะไร', path: '/random', icon: 'shuffle' }, { name: 'แดชบอร์ดสำหรับทีมร้าน', path: '/admin/dashboard', icon: 'monitor' }];
  function renderCommands() {
    const host = $('#command-results'); if (!host) return; host.replaceChildren();
    const query = ($('#command-search')?.value || '').trim().toLocaleLowerCase('th-TH');
    const matched = catalog.filter(item => `${item.name} ${item.category}`.toLocaleLowerCase('th-TH').includes(query)).slice(0, 8);
    if (query) matched.forEach(item => { const button = element('button', 'command-result'); button.type = 'button'; button.append(svg('utensils'), element('span', '', item.name), element('small', '', money(item.price))); button.addEventListener('click', () => { closeDialog($('#command-dialog')); showDish(item, $('[data-open-dialog="command-dialog"]')); }); host.append(button); });
    commands.filter(command => !query || command.name.toLocaleLowerCase('th-TH').includes(query)).forEach(command => { const link = element('a', 'command-result'); link.href = command.path + (command.path.startsWith('/admin') ? '' : tableQuery); link.append(svg(command.icon), element('span', '', command.name), element('small', '', '↗')); host.append(link); });
    if (query && !grid) { const link = element('a', 'command-result'); link.href = `/${tableQuery}${tableQuery ? '&' : '?'}q=${encodeURIComponent(query)}#menu`; link.append(svg('search'), element('span', '', `ค้นหา “${query}” ในเมนูอาหาร`)); host.append(link); }
    if (!host.children.length) host.append(element('p', 'command-empty', 'ไม่พบเมนู ลองค้นหาด้วยคำอื่น'));
  }
  $('#command-search')?.addEventListener('input', renderCommands);

  // Serialize cookie-backed cart mutations so rapid adds cannot overwrite each other.
  let cartQueue = Promise.resolve(); let cartState = null; let pendingAdds = 0;
  const initialCount = Number($('[data-cart-count]')?.textContent || 0);
  function paintCount(count) { $$('[data-cart-count]').forEach(node => { node.textContent = String(count); }); document.body.dataset.cartFilled = String(count > 0); }
  async function cartFetch(url, options = {}) {
    const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 12000);
    try { return await fetch(url, { ...options, signal: controller.signal }); }
    catch (error) { if (error.name === 'AbortError') throw new Error('การเชื่อมต่อใช้เวลานาน กรุณาตรวจสอบตะกร้าก่อนลองใหม่'); throw new Error('ติดต่อครัวไม่ได้ กรุณาตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง'); }
    finally { clearTimeout(timeout); }
  }
  async function fetchState() {
    const response = await cartFetch(`/cart/state${tableQuery}`, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!response.ok) throw new Error('ยังโหลดตะกร้าไม่ได้ กรุณาลองอีกครั้ง');
    return response.json();
  }
  function paintCart(state) {
    cartState = state; paintCount(Number(state.cart_count) + pendingAdds);
    const host = $('#sidebar-items'); if (!host) return;
    $('#sidebar-total').textContent = money(state.total); host.replaceChildren();
    if (!state.items?.length) {
      const empty = element('div', 'order-empty'); const bag = element('span', 'empty-bag'); bag.append(svg('bag'));
      empty.append(bag, element('strong', '', 'มื้ออร่อยกำลังรออยู่'), element('p', '', 'เลือกเมนูที่ชอบ แล้วเพิ่มลงตะกร้า เริ่มต้นความอร่อยได้เลย')); host.append(empty); return;
    }
    state.items.forEach(item => {
      const row = element('div', 'sidebar-item'); const img = element('img'); img.src = item.image_url || '/static/images/menu-placeholder.svg'; img.alt = item.name; img.width = 43; img.height = 43;
      const bottom = element('div', 'sidebar-item-bottom'); const quantity = element('div', 'sidebar-quantity');
      for (const [delta, icon] of [[-1, 'minus'], [1, 'plus']]) {
        const button = element('button'); button.type = 'button'; button.append(svg(icon)); button.setAttribute('aria-label', `${delta < 0 ? 'ลด' : 'เพิ่ม'}จำนวน ${item.name}`);
        button.addEventListener('click', () => { button.disabled = true; mutateQuantity(item.id, delta).finally(() => { button.disabled = false; }); });
        quantity.append(button); if (delta === -1) quantity.append(element('span', '', String(item.qty)));
      }
      bottom.append(element('span', 'sidebar-item-price', money(Number(item.price) * item.qty)), quantity);
      row.append(img, element('span', 'sidebar-item-name', item.name), bottom); host.append(row);
    });
  }
  async function responseMessage(response) { try { const result = await response.json(); return typeof result.detail === 'string' ? result.detail : result.message || 'เพิ่มรายการไม่ได้ กรุณาลองใหม่'; } catch { return 'ติดต่อครัวไม่ได้ กรุณาลองอีกครั้ง'; } }
  function queueMutation(work) { const task = cartQueue.then(work, work); cartQueue = task.catch(() => {}); return task; }
  function mutateQuantity(id, delta) {
    return queueMutation(async () => {
      try {
        const current = cartState?.items?.find(item => String(item.id) === String(id));
        if (!current) return;
        const response = await cartFetch(`/cart/update/${encodeURIComponent(id)}${tableQuery}`, { method: 'POST', headers: { Accept: 'application/json' }, body: new URLSearchParams({ quantity: String(Math.max(0, current.qty + delta)) }) });
        if (!response.ok) throw new Error(await responseMessage(response));
        const state = await response.json(); paintCart(state);
      } catch (error) { toast(error.message, 'error'); }
    });
  }
  document.addEventListener('submit', event => {
    const form = event.target.closest('form[data-cart-add]'); if (!form) return;
    event.preventDefault(); const button = $('button[type=submit]', form); if (button?.disabled) return;
    const action = form.action; const payload = new FormData(form); const itemName = form.dataset.itemName || 'อาหาร';
    if (button) { button.disabled = true; button.classList.add('is-busy'); }
    pendingAdds++; paintCount((cartState?.cart_count ?? initialCount) + pendingAdds);
    queueMutation(async () => {
      try {
        const response = await cartFetch(action, { method: 'POST', body: payload, headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error(await responseMessage(response));
        const state = await response.json(); pendingAdds--; paintCart(state);
        toast(`เพิ่ม${itemName}ลงตะกร้าแล้ว`);
        if (form.id === 'dish-add-form' && form.action === action) closeDialog($('#dish-dialog'));
      } catch (error) {
        pendingAdds--; paintCount((cartState?.cart_count ?? initialCount) + pendingAdds); toast(error.message, 'error');
        try { paintCart(await fetchState()); } catch { /* Keep last confirmed state and show the error. */ }
      } finally { if (button && form.action === action) { button.disabled = false; button.classList.remove('is-busy'); } }
    });
  });
  function loadCart() {
    const host = $('#sidebar-items');
    if (host && !cartState && initialCount > 0) {
      const loading = element('div', 'sidebar-skeleton'); loading.setAttribute('aria-label', 'กำลังโหลดรายการในตะกร้า');
      for (let index = 0; index < Math.min(3, initialCount); index++) loading.append(element('i', 'skeleton'));
      host.replaceChildren(loading);
    }
    return queueMutation(async () => {
      try { paintCart(await fetchState()); }
      catch {
        const host = $('#sidebar-items'); if (!host) return;
        const error = element('div', 'sidebar-error', 'ยังโหลดตะกร้าไม่ได้ รายการที่บันทึกไว้ยังอยู่'); const retry = element('button', 'text-button', 'ลองอีกครั้ง'); retry.type = 'button'; retry.addEventListener('click', loadCart); error.append(retry); host.replaceChildren(error); $('#sidebar-total').textContent = '—';
      }
    });
  }
  // Native cart/checkout pages already render current state. A concurrent GET there
  // could return an older signed session cookie after a form POST completed.
  const needsCartState = Boolean(grid) || location.pathname === '/random';
  if (needsCartState) loadCart();
  window.addEventListener('pageshow', event => { if (event.persisted && needsCartState) loadCart(); });
  // Lock native submissions only after page-specific validators have run.
  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.matches('[data-cart-add]') || form.method === 'dialog') return;
    queueMicrotask(() => {
      if (event.defaultPrevented) return;
      const button = event.submitter;
      if (button instanceof HTMLButtonElement) { button.disabled = true; button.classList.add('is-busy'); button.dataset.nativeBusy = 'true'; }
    });
  });
  window.addEventListener('pageshow', () => $$('[data-native-busy]').forEach(button => { button.disabled = false; button.classList.remove('is-busy'); delete button.dataset.nativeBusy; }));

  // Preserve native disclosure semantics while animating its measured height.
  const disclosureAnimations = new WeakMap();
  document.addEventListener('click', event => {
    const summary = event.target.closest('summary');
    if (!summary || reducedMotion()) return;
    const details = summary.parentElement;
    if (!(details instanceof HTMLDetailsElement)) return;
    event.preventDefault();
    const prior = disclosureAnimations.get(details);
    const opening = prior ? !prior.opening : !details.open;
    const from = details.getBoundingClientRect().height;
    prior?.animation.cancel();
    details.style.height = ''; details.style.overflow = 'clip';
    details.open = opening;
    const to = details.getBoundingClientRect().height;
    details.open = true;
    const animation = details.animate([{ height: `${from}px` }, { height: `${to}px` }], { duration: 320, easing: 'cubic-bezier(.2,.85,.25,1)' });
    disclosureAnimations.set(details, { animation, opening });
    animation.finished.then(() => {
      if (disclosureAnimations.get(details)?.animation !== animation) return;
      details.open = opening; details.style.overflow = ''; disclosureAnimations.delete(details);
    }).catch(() => { /* A subsequent toggle owns the replacement animation. */ });
  });

  // A single animation-frame write avoids per-pointer-event layout thrashing.
  let spotlightFrame = 0; let spotlightPanel; let pointerX = 0; let pointerY = 0;
  if (matchMedia('(pointer:fine)').matches) document.addEventListener('pointermove', event => {
    if (reducedMotion()) return; const panel = event.target.closest('.glass-panel'); if (!panel) return;
    spotlightPanel = panel; pointerX = event.clientX; pointerY = event.clientY;
    if (!spotlightFrame) spotlightFrame = requestAnimationFrame(() => { const rect = spotlightPanel.getBoundingClientRect(); spotlightPanel.style.setProperty('--pointer-x', `${pointerX - rect.left}px`); spotlightPanel.style.setProperty('--pointer-y', `${pointerY - rect.top}px`); spotlightFrame = 0; });
  }, { passive: true });
  document.addEventListener('error', event => { if (event.target instanceof HTMLImageElement && !event.target.classList.contains('qr-image') && !event.target.closest('.qr-code,.table-qr') && !event.target.src.startsWith('data:') && !event.target.src.endsWith('menu-placeholder.svg')) event.target.src = '/static/images/menu-placeholder.svg'; }, true);
  document.addEventListener('visibilitychange', () => { document.querySelectorAll('.ambient-canvas i').forEach(node => { node.style.animationPlayState = document.hidden ? 'paused' : 'running'; }); });
  updateIndicators();
})();
