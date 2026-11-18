/* Apply saved preferences before first paint to avoid theme flashes. */
(() => {
  try {
    const mode = localStorage.getItem('foodkub.theme') || 'system';
    document.documentElement.dataset.theme = mode === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : mode;
    document.documentElement.dataset.motion = localStorage.getItem('foodkub.motion') || 'system';
  } catch { /* Storage may be disabled. The default remains usable. */ }
})();
