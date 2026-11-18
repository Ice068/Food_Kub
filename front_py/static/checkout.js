/* Integer cents keep the preview in sync with the server's Decimal validation. */
(() => {
  'use strict';
  const dataElement = document.getElementById('checkout-data');
  const form = document.getElementById('checkout-form');
  if (!dataElement || !form) return;
  const { items, total, sharedPaid, sharedIds } = JSON.parse(dataElement.textContent);
  const byId = new Map(items.map(item => [Number(item.id), item]));
  const shared = new Set(sharedIds.map(Number));
  const cents = value => Math.round(Number(value) * 100);
  const money = value => (value / 100).toFixed(2);
  const get = id => document.getElementById(id);
  let mode = 'full';
  let people = 2;
  let submitting = false;
  try { people = Math.max(1, Math.min(20, Number(localStorage.getItem('foodkub.splitPeople')) || 2)); } catch { /* Storage is optional. */ }
  people = Math.floor(people);

  function renderShared() {
    const tags = get('shared-items-list');
    tags.replaceChildren();
    let pool = 0;
    items.forEach(item => {
      const isShared = shared.has(item.id);
      const check = get(`check-${item.id}`);
      const button = get(`btn-shared-${item.id}`);
      check.disabled = isShared;
      if (isShared) check.checked = false;
      button.setAttribute('aria-pressed', String(isShared));
      button.textContent = isShared ? '✓ ของกลาง' : '＋ ตั้งเป็นของกลาง';
      get(`card-${item.id}`).classList.toggle('is-shared-item', isShared);
      get(`qty-${item.id}`).disabled = isShared;
      if (!isShared) return;
      pool += cents(item.price) * item.qty;
      const tag = document.createElement('button');
      tag.type = 'button';
      tag.className = 'shared-mini-tag';
      tag.textContent = `${item.name} × ${item.qty}  ×`;
      tag.setAttribute('aria-label', `นำ ${item.name} ออกจากของกลาง`);
      tag.addEventListener('click', () => toggleShared(item.id));
      tags.appendChild(tag);
    });
    const paid = Math.min(pool, cents(sharedPaid));
    get('shared-pool-total-badge').textContent = pool
      ? `รวม ฿${money(pool)}${paid ? ` · ชำระแล้ว ฿${money(paid)}` : ''}`
      : 'ยังไม่มีของกลาง เลือกรายการที่ต้องการแบ่งกันด้านบน';
  }

  function recalculate() {
    if (submitting) return;
    const selected = {};
    let personal = 0;
    let pool = 0;
    items.forEach(item => {
      const quantity = Math.max(1, Math.min(item.qty, Number(get(`qty-${item.id}`).value) || 1));
      const chosen = get(`check-${item.id}`).checked && !shared.has(item.id);
      const cost = cents(item.price) * quantity;
      get(`price-display-${item.id}`).textContent = `฿${money(shared.has(item.id) ? cents(item.price) * item.qty : cost)}`;
      get(`card-${item.id}`).classList.toggle('is-selected', chosen);
      if (chosen) { selected[item.id] = quantity; personal += cost; }
      if (shared.has(item.id)) pool += cents(item.price) * item.qty;
    });
    const paid = Math.min(pool, cents(sharedPaid));
    const remaining = Math.max(0, pool - paid);
    const perPerson = Math.min(remaining, Math.round(remaining / people));
    const include = get('include-shared-check');
    include.disabled = remaining === 0;
    if (!remaining) include.checked = false;
    const sharedAmount = include.checked ? perPerson : 0;
    const payable = mode === 'full' ? cents(total) : personal + sharedAmount;
    get('people-count-text').textContent = `${people} คน`;
    document.querySelector('[data-people-delta="-1"]').disabled = people <= 1;
    document.querySelector('[data-people-delta="1"]').disabled = people >= 20;
    get('shared-per-person-amount').textContent = money(perPerson);
    get('summary-personal-amount').textContent = `฿${money(personal)}`;
    get('summary-shared-amount').textContent = `฿${money(sharedAmount)}`;
    get('summary-total-amount').textContent = `฿${money(payable)}`;
    get('input-split-mode').value = mode;
    get('input-selected-items').value = mode === 'split' ? JSON.stringify(selected) : '{}';
    get('input-shared-amount').value = mode === 'split' ? money(sharedAmount) : '0.00';
    get('input-shared-item-ids').value = mode === 'split' ? JSON.stringify([...shared]) : '[]';
    get('input-shared-note').value = mode === 'split' && sharedAmount
      ? `ของกลาง ฿${money(pool)} · ชำระแล้ว ฿${money(paid)} · หาร ${people} คน` : '';
    const button = get('submit-pay-button');
    button.disabled = payable <= 0 || payable > cents(total);
    button.textContent = payable > 0 ? 'สร้างคำขอชำระเงิน →' : 'เลือกรายการที่ต้องการชำระ';
  }

  function toggleShared(id) {
    if (submitting || !byId.has(id)) return;
    if (shared.has(id)) shared.delete(id); else shared.add(id);
    renderShared();
    recalculate();
  }

  function switchMode(next) {
    if (submitting) return;
    mode = next;
    document.querySelector('.checkout-tabs').classList.toggle('is-split', mode === 'split');
    for (const candidate of ['full', 'split']) {
      const active = candidate === mode;
      const tab = get(`tab-btn-${candidate}`);
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      get(`panel-${candidate}`).hidden = !active;
    }
    get('personal-summary').hidden = mode !== 'split';
    recalculate();
  }

  document.querySelectorAll('[data-checkout-mode]').forEach(tab => {
    tab.addEventListener('click', () => switchMode(tab.dataset.checkoutMode));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 'full' : event.key === 'End' ? 'split' : mode === 'full' ? 'split' : 'full';
      switchMode(next);
      get(`tab-btn-${next}`).focus();
    });
  });
  document.querySelectorAll('[data-shared-toggle]').forEach(button => button.addEventListener('click', () => toggleShared(Number(button.dataset.sharedToggle))));
  document.querySelectorAll('[data-item-check], [data-item-qty], #include-shared-check').forEach(control => control.addEventListener('change', recalculate));
  document.querySelectorAll('[data-select-all]').forEach(button => button.addEventListener('click', () => {
    if (submitting) return;
    items.forEach(item => { if (!shared.has(item.id)) get(`check-${item.id}`).checked = button.dataset.selectAll === 'true'; });
    recalculate();
  }));
  document.querySelectorAll('[data-people-delta]').forEach(button => button.addEventListener('click', () => {
    if (submitting) return;
    people = Math.max(1, Math.min(20, people + Number(button.dataset.peopleDelta)));
    try { localStorage.setItem('foodkub.splitPeople', String(people)); } catch { /* Storage is optional. */ }
    recalculate();
  }));
  form.addEventListener('submit', event => {
    if (submitting) { event.preventDefault(); return; }
    recalculate();
    if (!form.elements.payment_token.value || get('submit-pay-button').disabled) {
      event.preventDefault();
      const error = get('checkout-error');
      error.hidden = false;
      error.textContent = form.elements.payment_token.value ? 'กรุณาเลือกรายการที่ต้องการชำระ' : 'กรุณาเปิดหน้าชำระเงินใหม่ก่อนทำรายการ';
      return;
    }
    submitting = true;
    get('checkout-app').setAttribute('aria-busy', 'true');
    get('submit-pay-button').disabled = true;
    get('submit-pay-button').textContent = 'กำลังส่งคำขอ…';
  });
  window.addEventListener('pageshow', () => {
    submitting = false;
    get('checkout-app').removeAttribute('aria-busy');
    recalculate();
  });
  renderShared();
  recalculate();
})();
