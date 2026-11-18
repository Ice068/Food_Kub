(() => {
  'use strict';
  const qrImage = document.querySelector('.qr-image');
  if (qrImage) {
    const showQrError = () => {
      const frame = qrImage.closest('.qr-frame');
      if (!frame) return;
      const warning = document.createElement('p');
      warning.className = 'status-banner';
      warning.setAttribute('role', 'alert');
      warning.textContent = 'แสดง QR ไม่สำเร็จ กรุณาตรวจสอบสถานะรายการหรือติดต่อพนักงานก่อนชำระเงิน';
      frame.replaceChildren(warning);
    };
    qrImage.addEventListener('error', showQrError, { once: true });
    if (qrImage.complete && !qrImage.naturalWidth) showQrError();
  }
  const dialog = document.getElementById('payment-success-dialog');
  if (dialog && typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
  const message = document.getElementById('payment-status-live');
  if (!message) return;
  let stopped = false;
  let inFlight = false;
  let timer;
  let activeRequest;

  async function checkPayment() {
    if (stopped || inFlight) return;
    if (document.hidden) { timer = setTimeout(checkPayment, 5000); return; }
    inFlight = true;
    activeRequest = new AbortController();
    const timeout = setTimeout(() => activeRequest.abort(), 8000);
    try {
      const response = await fetch(message.dataset.statusUrl, { cache:'no-store', credentials:'same-origin', signal:activeRequest.signal });
      if (!response.ok) throw new Error('Status unavailable');
      const data = await response.json();
      if (stopped) return;
      if (data.payment_confirmed === true) {
        stopped = true;
        message.textContent = 'ยืนยันรับเงินแล้ว กำลังแสดงผลการชำระ';
        window.location.replace(message.dataset.checkoutUrl);
        return;
      }
      message.textContent = 'กำลังรอพนักงานยืนยันรับเงิน';
    } catch {
      if (!stopped) message.textContent = 'ยังตรวจสอบสถานะไม่ได้ กำลังลองใหม่ กรุณาอย่าจ่ายซ้ำ';
    } finally {
      inFlight = false;
      clearTimeout(timeout);
      if (!stopped) timer = setTimeout(checkPayment, 5000);
    }
  }
  window.addEventListener('pagehide', () => { stopped = true; clearTimeout(timer); activeRequest?.abort(); });
  window.addEventListener('pageshow', event => { if (event.persisted && stopped) { stopped = false; checkPayment(); } });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !stopped) { clearTimeout(timer); checkPayment(); } });
  checkPayment();
})();
