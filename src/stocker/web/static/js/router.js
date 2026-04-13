/**
 * Simple SPA Router
 */
const Router = (() => {
  const routes = {};
  let currentPage = null;

  // Alias map: old route → new route (backward compatibility)
  const aliases = {
    portfolio: 'stocks',
    watchlist: 'stocks',
    'swing-trades': 'trading',
    trades: 'trading',
  };

  function register(name, initFn) {
    routes[name] = initFn;
  }

  function navigate(page) {
    // Resolve aliases
    if (aliases[page]) page = aliases[page];

    if (currentPage === page) return;

    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

    // Show target page
    const el = document.getElementById(`page-${page}`);
    if (el) {
      el.classList.add('active');
      el.classList.add('fade-in');
      setTimeout(() => el.classList.remove('fade-in'), 200);
    }

    // Update sidebar active
    document.querySelectorAll('.sidebar-nav a').forEach(a => {
      a.classList.toggle('active', a.dataset.page === page);
    });

    // Update topbar title
    const titles = {
      chat: '对话',
      stocks: '股票池',
      trading: '交易',
      reports: '报告',
      logs: '运行日志',
      strategy: '策略配置',
      modes: '运行模式',
      settings: '设置',
    };
    const topTitle = document.getElementById('topbar-title');
    if (topTitle) topTitle.textContent = titles[page] || page;

    currentPage = page;
    window.location.hash = page;

    // Call init function if registered
    if (routes[page]) routes[page]();
  }

  function init() {
    // Bind sidebar nav clicks
    document.querySelectorAll('.sidebar-nav a[data-page]').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        navigate(a.dataset.page);
      });
    });

    // Navigate to hash or default
    const hash = window.location.hash.replace('#', '') || 'chat';
    navigate(hash);

    window.addEventListener('hashchange', () => {
      const h = window.location.hash.replace('#', '');
      if (h) navigate(h);
    });
  }

  return { register, navigate, init };
})();
