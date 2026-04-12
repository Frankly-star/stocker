/**
 * Stocker API Client
 */
const API = (() => {
  const BASE = '/api/v1';

  async function request(method, path, body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    try {
      const res = await fetch(`${BASE}${path}`, opts);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      console.error(`API ${method} ${path} failed:`, e);
      throw e;
    }
  }

  return {
    // Status
    getStatus:   ()                  => request('GET',  '/status'),
    getHealth:   ()                  => fetch('/health').then(r => r.json()),

    // Chat
    chat:        (message)           => request('POST', '/chat', { message }),
    resetChat:   ()                  => request('POST', '/chat/reset'),

    // Analysis
    analyze:     (ticker)            => request('POST', '/analyze', { ticker }),

    // Portfolio
    listPortfolio:   ()              => request('POST', '/portfolio', { action: 'list' }),
    addPosition:     (ticker, q, c)  => request('POST', '/portfolio', { action: 'add', ticker, quantity: q, avg_cost: c }),
    removePosition:  (ticker)        => request('POST', '/portfolio', { action: 'remove', ticker }),
    scanPortfolio:   ()              => request('POST', '/portfolio', { action: 'scan' }),

    // Trade
    trade:       (ticker, action, quantity, price) =>
      request('POST', '/trade', { ticker, action, quantity, price }),

    // Trade History
    getTradeHistory: ()              => request('GET',  '/trades'),

    // Account
    getAccount:      ()              => request('GET',  '/account'),

    // Logs
    getLogs:         (lines = 100)   => request('GET',  `/logs?lines=${lines}`),

    // Reports
    getReports:      ()              => request('GET',  '/reports'),

    // Broker Config
    getBrokerConfig: ()              => request('GET',  '/broker/config'),

    // Execution Mode
    setExecutionMode: (mode)         => request('POST', '/execution-mode', { mode }),

    // Skills
    listSkills:  ()                  => request('GET',  '/skills'),

    // Strategy
    getStrategy:       ()            => request('GET',  '/strategy'),
    updateStrategy:    (data)        => request('PUT',  '/strategy', data),
    listPresets:       ()            => request('GET',  '/strategy/presets'),
    switchPreset:      (name)        => request('POST', `/strategy/preset/${name}`),
    resetStrategy:     ()            => request('POST', '/strategy/reset'),
  };
})();
