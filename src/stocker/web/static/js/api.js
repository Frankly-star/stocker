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

    // Auto-Pilot
    getAutoPilot:      ()            => request('GET',  '/auto-pilot'),
    setAutoPilot:      (enabled)     => request('POST', '/auto-pilot', { enabled }),

    // Skills
    listSkills:  ()                  => request('GET',  '/skills'),

    // Evolution Skill Runtime
    listEvolutionSkills:  (params = '') => request('GET', `/evolution/skills${params}`),
    viewEvolutionSkill:   (id)          => request('GET', `/evolution/skills/${encodeURIComponent(id)}`),
    seedEvolutionSkills:  (overwrite = false) => request('POST', '/evolution/skills/seed-defaults', { overwrite }),
    listEvolutionTraces:  (limit = 50)  => request('GET', `/evolution/traces?limit=${limit}`),
    listEvolutionPatches: (status = '', limit = 50) => request('GET', `/evolution/patches?status=${encodeURIComponent(status)}&limit=${limit}`),
    validateEvolutionPatch: (id)        => request('POST', `/evolution/patches/${encodeURIComponent(id)}/validate`),
    approveEvolutionPatch:  (id, body)  => request('POST', `/evolution/patches/${encodeURIComponent(id)}/approve`, body),
    applyEvolutionPatch:    (id)        => request('POST', `/evolution/patches/${encodeURIComponent(id)}/apply`),
    runEvolutionCurator:    (body = {}) => request('POST', '/evolution/curator/run', body),
    runEvolutionWeeklyReview: (body = {}) => request('POST', '/evolution/review/weekly', body),

    // Strategy

    getStrategy:       ()            => request('GET',  '/strategy'),
    updateStrategy:    (data)        => request('PUT',  '/strategy', data),
    listPresets:       ()            => request('GET',  '/strategy/presets'),
    switchPreset:      (name)        => request('POST', `/strategy/preset/${name}`),
    resetStrategy:     ()            => request('POST', '/strategy/reset'),
  };
})();
