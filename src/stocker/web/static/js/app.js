/**
 * Stocker Frontend Application
 */
document.addEventListener('DOMContentLoaded', () => {
  initChat();
  initPortfolio();
  initReports();
  initTrades();
  initLogs();
  initStrategy();
  initModes();
  initSettings();
  Router.init();
  checkSystemStatus();
});

// ============================================================
// Toast notifications
// ============================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ============================================================
// System status check
// ============================================================
async function checkSystemStatus() {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  try {
    const res = await API.getHealth();
    if (res.status === 'ok') {
      dot.className = 'status-dot';
      text.textContent = '系统运行中';
    }
  } catch {
    dot.className = 'status-dot offline';
    text.textContent = '连接失败';
  }
}

// ============================================================
// Chat Page
// ============================================================
function initChat() {
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  const messages = document.getElementById('chat-messages');

  function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    appendMessage('user', text);
    input.value = '';
    input.style.height = '44px';
    sendBtn.disabled = true;

    // Create dispatch log area + typing indicator
    const logEl = appendDispatchLog();
    addLogEntry(logEl, 'system', '发送请求到 Supervisor...');

    // Use SSE streaming endpoint
    fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    }).then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) {
            // Stream ended without done event — shouldn't happen but handle gracefully
            finishStream(logEl);
            return;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let eventType = '';
          let eventData = '';

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6);
            } else if (line === '' && eventType && eventData) {
              handleSSEEvent(logEl, eventType, eventData);
              eventType = '';
              eventData = '';
            }
          }

          read();
        }).catch(err => {
          addLogEntry(logEl, 'error', `流式读取失败: ${err.message}`);
          finishStream(logEl);
        });
      }
      read();
    }).catch(err => {
      addLogEntry(logEl, 'error', `请求失败: ${err.message}`);
      finishStream(logEl);
    });

    function handleSSEEvent(logEl, type, dataStr) {
      try {
        const data = JSON.parse(dataStr);
        if (type === 'log') {
          const icon = getStepIcon(data.source, data.action);
          addLogEntry(logEl, data.source, `${icon} ${data.message}`);
        } else if (type === 'done') {
          finishStream(logEl);
          appendMessage('assistant', data.response);
        } else if (type === 'error') {
          addLogEntry(logEl, 'error', `${data.message}`);
          finishStream(logEl);
          appendMessage('assistant', `Supervisor 错误: ${data.message}`);
        }
      } catch (e) {
        console.error('SSE parse error:', e, dataStr);
      }
    }

    function finishStream(logEl) {
      // Mark dispatch log as completed
      const spinner = logEl.querySelector('.dispatch-spinner');
      if (spinner) spinner.remove();
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = '44px';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  });

  // Quick action chips
  document.querySelectorAll('.quick-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      input.value = chip.dataset.msg;
      input.focus();
    });
  });
}

function appendMessage(role, text) {
  const messages = document.getElementById('chat-messages');
  const empty = document.getElementById('chat-empty');
  if (empty) empty.style.display = 'none';

  const now = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const avatar = role === 'user' ? 'U' : 'S';

  const div = document.createElement('div');
  div.className = `chat-msg ${role} fade-in`;

  // User messages: plain text; Assistant messages: render Markdown
  let formatted;
  if (role === 'assistant' && typeof marked !== 'undefined') {
    formatted = marked.parse(text);
  } else {
    formatted = escapeHtml(text).replace(/\n/g, '<br>');
  }

  div.innerHTML = `
    <div class="chat-avatar">${avatar}</div>
    <div>
      <div class="chat-bubble">${formatted}</div>
      <div class="chat-time">${now}</div>
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function appendTyping() {
  const messages = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'chat-msg assistant fade-in';
  div.innerHTML = `
    <div class="chat-avatar">S</div>
    <div>
      <div class="chat-bubble"><span class="spinner" style="display:inline-block;width:16px;height:16px;vertical-align:middle;"></span> Supervisor 正在思考和调度...</div>
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

// --- Dispatch log (real-time flow visualization) ---

function appendDispatchLog() {
  const messages = document.getElementById('chat-messages');
  const empty = document.getElementById('chat-empty');
  if (empty) empty.style.display = 'none';

  const div = document.createElement('div');
  div.className = 'chat-msg assistant fade-in';
  div.innerHTML = `
    <div class="chat-avatar">S</div>
    <div style="flex:1;min-width:0;">
      <div class="dispatch-log">
        <div class="dispatch-header">
          <span class="dispatch-spinner"><span class="spinner" style="display:inline-block;width:12px;height:12px;vertical-align:middle;"></span></span>
          <span class="dispatch-title">Supervisor 调度流程</span>
        </div>
        <div class="dispatch-steps"></div>
      </div>
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function addLogEntry(logEl, source, message) {
  const steps = logEl.querySelector('.dispatch-steps');
  if (!steps) return;

  const now = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const entry = document.createElement('div');
  entry.className = `dispatch-step dispatch-${source} fade-in`;
  entry.innerHTML = `<span class="dispatch-time">${now}</span> <span class="dispatch-msg">${escapeHtml(message)}</span>`;
  steps.appendChild(entry);

  // Auto-scroll
  const messages = document.getElementById('chat-messages');
  messages.scrollTop = messages.scrollHeight;
}

function getStepIcon(source, action) {
  const icons = {
    'system:start': '\u25B6',
    'supervisor:thinking': '\u{1F9E0}',
    'supervisor:tool_decision': '\u{1F3AF}',
    'supervisor:responding': '\u2705',
    'tool:calling': '\u{1F527}',
    'tool:completed': '\u2705',
  };
  return icons[`${source}:${action}`] || '\u2022';
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

// ============================================================
// Portfolio Page
// ============================================================
function initPortfolio() {
  Router.register('portfolio', loadPortfolio);

  document.getElementById('btn-add-position')?.addEventListener('click', showAddPositionDialog);
  document.getElementById('btn-refresh-portfolio')?.addEventListener('click', loadPortfolio);
}

async function loadPortfolio() {
  const tbody = document.getElementById('portfolio-tbody');
  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;"><div class="spinner" style="margin:0 auto;"></div></td></tr>';

  try {
    const res = await API.listPortfolio();
    const positions = res.positions || [];

    if (positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center;padding:30px;">暂无持仓数据</td></tr>';
      updatePortfolioSummary([]);
      return;
    }

    tbody.innerHTML = positions.map(p => `
      <tr>
        <td><span class="ticker-tag">${p.ticker}</span></td>
        <td>${p.name || '-'}</td>
        <td>${p.quantity}</td>
        <td>${p.avg_cost?.toFixed(2) || '-'}</td>
        <td>${p.current_price?.toFixed(2) || '-'}</td>
        <td class="${(p.unrealized_pnl || 0) >= 0 ? 'positive' : 'negative'}">
          ${p.unrealized_pnl != null ? (p.unrealized_pnl >= 0 ? '+' : '') + p.unrealized_pnl.toFixed(2) : '-'}
        </td>
        <td class="${(() => { const pct = p.avg_cost > 0 ? ((p.current_price - p.avg_cost) / p.avg_cost * 100) : 0; return pct >= 0 ? 'positive' : 'negative'; })()}">
          ${p.avg_cost > 0 ? (() => { const pct = (p.current_price - p.avg_cost) / p.avg_cost * 100; return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'; })() : '-'}
        </td>
        <td>
          <button class="btn btn-sm" onclick="analyzeFromPortfolio('${p.ticker}')">分析</button>
          <button class="btn btn-sm btn-danger" onclick="removePosition('${p.ticker}')">删除</button>
        </td>
      </tr>
    `).join('');

    updatePortfolioSummary(positions);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--red);">加载失败: ${e.message}</td></tr>`;
  }
}

function updatePortfolioSummary(positions) {
  const total = positions.reduce((s, p) => s + (p.quantity || 0) * (p.current_price || p.avg_cost || 0), 0);
  const pnl = positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const count = positions.length;

  document.getElementById('summary-total-value').textContent = `$${total.toFixed(2)}`;
  document.getElementById('summary-total-pnl').textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
  document.getElementById('summary-total-pnl').className = `summary-card-value ${pnl >= 0 ? 'positive' : 'negative'}`;
  document.getElementById('summary-position-count').textContent = count;
}

function showAddPositionDialog() {
  const ticker = prompt('请输入股票代码（如 AAPL、TSLA、600519.SS）:');
  if (!ticker) return;
  const qty = parseInt(prompt('数量:', '100'), 10);
  if (isNaN(qty) || qty <= 0) return;
  const cost = parseFloat(prompt('成本价:', '0'));

  API.addPosition(ticker.toUpperCase(), qty, cost)
    .then(() => {
      showToast(`已添加 ${ticker.toUpperCase()}`, 'success');
      loadPortfolio();
    })
    .catch(e => showToast(`添加失败: ${e.message}`, 'error'));
}

window.removePosition = function(ticker) {
  if (!confirm(`确定删除 ${ticker}？`)) return;
  API.removePosition(ticker)
    .then(() => {
      showToast(`已删除 ${ticker}`, 'success');
      loadPortfolio();
    })
    .catch(e => showToast(`删除失败: ${e.message}`, 'error'));
};

window.analyzeFromPortfolio = function(ticker) {
  Router.navigate('chat');
  setTimeout(() => {
    const input = document.getElementById('chat-input');
    input.value = `分析 ${ticker}，给出投资建议`;
    input.focus();
  }, 100);
};

// ============================================================
// Reports Page
// ============================================================
function initReports() {
  Router.register('reports', loadReports);
}

async function loadReports() {
  const grid = document.getElementById('reports-grid');
  grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><div class="spinner" style="margin:0 auto;"></div></div>';

  let reports = [];

  // Try real API first
  try {
    const res = await API.getReports();
    if (res.reports && res.reports.length > 0) {
      reports = res.reports;
    }
  } catch (e) {
    console.warn('Reports API unavailable:', e);
  }

  // Fallback to demo data if API returns nothing
  if (reports.length === 0) {
    reports = getDemoReports();
  }

  if (reports.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <div class="empty-state-icon">&#128202;</div>
        <div class="empty-state-title">暂无报告</div>
        <div class="empty-state-hint">通过对话或持仓扫描生成分析报告</div>
      </div>`;
    return;
  }

  grid.innerHTML = reports.map((r, i) => `
    <div class="report-card" onclick="showReportDetail(${i})">
      <div class="report-card-header">
        <span class="report-card-ticker">${escapeHtml(r.ticker || 'N/A')}</span>
        <span class="report-card-date">${escapeHtml(r.date || r.timestamp || '')}</span>
      </div>
      <div class="report-card-body">${escapeHtml(r.summary || r.response || JSON.stringify(r).slice(0, 200))}</div>
      <div class="report-card-footer">
        ${r.rating ? `<span class="badge badge-${r.rating.toLowerCase()}">${r.rating}</span>` : ''}
        ${r.environment ? `<span class="report-tag">${escapeHtml(r.environment)}</span>` : ''}
        ${r.confidence != null ? `<span class="report-tag">置信度 ${(r.confidence * 100).toFixed(0)}%</span>` : ''}
      </div>
    </div>
  `).join('');

  // Store for detail view
  window._cachedReports = reports;
}

function getDemoReports() {
  return [
    {
      ticker: 'AAPL', date: '2026-04-06', rating: 'HOLD',
      summary: 'Apple 目前处于区间震荡中段，RSI 52.3 中性，MACD 轻微看涨。支撑位 $168，阻力位 $178。基本面稳健，PE 28.5 合理。',
      environment: '区间震荡', confidence: 0.72,
    },
    {
      ticker: 'TSLA', date: '2026-04-06', rating: 'SELL',
      summary: 'Tesla 接近阻力位，RSI 71.2 超买区域。社交媒体情绪过热，出现反向信号。建议减仓观望。',
      environment: '趋势上行', confidence: 0.65,
    },
    {
      ticker: 'NVDA', date: '2026-04-05', rating: 'BUY',
      summary: 'NVIDIA 回调至关键支撑区域，基本面强劲（AI 需求持续），情绪评分 0.68。建议分批建仓。',
      environment: '回调支撑', confidence: 0.81,
    },
  ];
}

window.showReportDetail = function(index) {
  const reports = window._cachedReports || getDemoReports();
  const r = typeof index === 'number' ? reports[index] : reports.find(x => x.ticker === index);
  if (!r) return;
  const detail = document.getElementById('report-detail-panel');
  const ticker = r.ticker || 'N/A';
  document.getElementById('report-detail-content').innerHTML = `
    <div class="report-detail fade-in">
      <div class="flex items-center justify-between mb-4">
        <h2>${escapeHtml(ticker)} 分析报告</h2>
        <button class="btn btn-sm" onclick="document.getElementById('report-detail-panel').classList.add('hidden')">关闭</button>
      </div>
      <div class="report-detail-metrics mb-4">
        ${r.rating ? `<div class="metric-item"><div class="metric-label">评级</div><div class="metric-value"><span class="badge badge-${r.rating.toLowerCase()}">${r.rating}</span></div></div>` : ''}
        ${r.confidence != null ? `<div class="metric-item"><div class="metric-label">置信度</div><div class="metric-value">${(r.confidence * 100).toFixed(0)}%</div></div>` : ''}
        ${r.environment ? `<div class="metric-item"><div class="metric-label">市场环境</div><div class="metric-value">${escapeHtml(r.environment)}</div></div>` : ''}
        <div class="metric-item"><div class="metric-label">日期</div><div class="metric-value">${escapeHtml(r.date || r.timestamp || '-')}</div></div>
      </div>
      <div class="report-detail-section">
        <h3>分析摘要</h3>
        <p>${escapeHtml(r.summary || r.response || JSON.stringify(r))}</p>
      </div>
      <div class="report-detail-section">
        <h3>后续操作</h3>
        <div class="flex gap-2 mt-2">
          <button class="btn btn-primary btn-sm" onclick="Router.navigate('chat');document.getElementById('chat-input').value='对 ${ticker} 进行风险评估';">深入分析</button>
          <button class="btn btn-sm" onclick="Router.navigate('chat');document.getElementById('chat-input').value='${ticker} 的技术面如何';">技术面</button>
        </div>
      </div>
    </div>
  `;
  detail.classList.remove('hidden');
};

// ============================================================
// Modes Page
// ============================================================
let currentExecutionMode = 'observe'; // safe default

function initModes() {
  Router.register('modes', loadModes);

  // Mode card click → toggle between ACTIVE/OBSERVE
  document.querySelectorAll('#page-modes .mode-card').forEach(card => {
    card.addEventListener('click', () => {
      const mode = card.dataset.mode;
      setExecutionMode(mode);
    });
  });

  // Top-bar toggle
  const modeToggle = document.getElementById('execution-mode-toggle');
  if (modeToggle) {
    modeToggle.addEventListener('change', () => {
      const mode = modeToggle.checked ? 'active' : 'observe';
      setExecutionMode(mode);
    });
  }

  // Init UI to default
  syncModeUI('observe');
}

async function setExecutionMode(mode) {
  // Call backend to persist
  try {
    await API.setExecutionMode(mode);
  } catch (e) {
    console.warn('Failed to set execution mode on backend:', e);
  }
  currentExecutionMode = mode;
  syncModeUI(mode);
  const label = mode === 'active' ? 'ACTIVE（执行模式）' : 'OBSERVE（观察模式）';
  showToast(`已切换到：${label}`, mode === 'active' ? 'success' : 'info');
}

function syncModeUI(mode) {
  // Update mode cards
  document.querySelectorAll('#page-modes .mode-card').forEach(c => c.classList.remove('active'));
  const target = document.querySelector(`#page-modes .mode-card[data-mode="${mode}"]`);
  if (target) target.classList.add('active');

  // Update top-bar toggle
  const modeToggle = document.getElementById('execution-mode-toggle');
  if (modeToggle) modeToggle.checked = (mode === 'active');

  // Update top-bar label
  const label = document.getElementById('execution-mode-label');
  if (label) label.textContent = mode === 'active' ? 'ACTIVE' : 'OBSERVE';
}

async function loadModes() {
  try {
    const res = await API.getStatus();
    updateStatusPanel(res);
    // Sync mode from server
    if (res.execution_mode) {
      currentExecutionMode = res.execution_mode;
      syncModeUI(res.execution_mode);
    }
  } catch {
    // ignore
  }
}

function updateStatusPanel(data) {
  if (!data) return;

  const setVal = (id, text, dotClass) => {
    const el = document.getElementById(`val-${id}`);
    if (el) el.textContent = text;
    const dot = document.getElementById(`dot-${id}`);
    if (dot) dot.className = `status-dot${dotClass ? ' ' + dotClass : ''}`;
  };

  // Supervisor
  const sup = data.supervisor || 'unknown';
  setVal('supervisor', sup === 'ready' ? '就绪' : sup === 'no_llm' ? 'LLM 未就绪' : sup, sup === 'ready' ? '' : 'warning');

  // Teams
  const teams = data.teams || {};
  setVal('intelligence', teams.intelligence === 'idle' ? '空闲' : teams.intelligence || '-', '');
  setVal('risk', teams.risk_assessment === 'idle' ? '空闲' : teams.risk_assessment || '-', '');
  setVal('execution', teams.execution === 'ready' ? '就绪' : teams.execution === 'idle' ? '未接入' : teams.execution || '-',
    teams.execution === 'ready' ? '' : 'warning');

  // Scheduler
  setVal('scheduler', data.scheduler === 'running' ? '运行中' : data.scheduler || '-', '');

  // Broker
  const brokerName = data.broker || 'none';
  const brokerLabel = brokerName === 'simulated' ? '模拟盘' : brokerName === 'futu' ? '富途' : brokerName;
  setVal('broker', brokerLabel, brokerName === 'simulated' ? 'warning' : '');

  // Positions
  setVal('positions', data.positions_count != null ? `${data.positions_count} 个` : '-', '');

  // Execution mode
  const em = data.execution_mode || 'observe';
  setVal('exec-mode', em.toUpperCase(), em === 'active' ? 'warning' : '');
}

// ============================================================
// Strategy Page
// ============================================================

// Field mapping: HTML id → strategy JSON path
const STRATEGY_FIELDS = [
  // Technical
  { id: 'rsi-window',    path: 'technical.rsi_window',    type: 'int',   def: 14 },
  { id: 'macd-fast',     path: 'technical.macd_fast',     type: 'int',   def: 12 },
  { id: 'macd-slow',     path: 'technical.macd_slow',     type: 'int',   def: 26 },
  { id: 'macd-signal',   path: 'technical.macd_signal',   type: 'int',   def: 9 },
  { id: 'bb-window',     path: 'technical.bb_window',     type: 'int',   def: 20 },
  { id: 'bb-std',        path: 'technical.bb_std',        type: 'float', def: 2.0 },
  { id: 'atr-window',    path: 'technical.atr_window',    type: 'int',   def: 14 },
  { id: 'sma-short',     path: 'technical.sma_short',     type: 'int',   def: 50 },
  { id: 'sma-long',      path: 'technical.sma_long',      type: 'int',   def: 200 },
  // Risk
  { id: 'stop-loss-min',     path: 'risk.stop_loss_min_pct',      type: 'float', def: 2.0 },
  { id: 'stop-loss-max',     path: 'risk.stop_loss_max_pct',      type: 'float', def: 10.0 },
  { id: 'position-min',      path: 'risk.position_size_min_pct',  type: 'float', def: 2.0 },
  { id: 'position-max',      path: 'risk.position_size_max_pct',  type: 'float', def: 10.0 },
  { id: 'risk-reward',       path: 'risk.take_profit_min_ratio',  type: 'float', def: 1.5 },
  { id: 'min-stop-distance', path: 'risk.price_validation_min_pct',  type: 'float', def: 1.0 },
  // Data
  { id: 'kline-count',  path: 'data.kline_count',        type: 'int',   def: 120 },
  { id: 'lookback-days', path: 'data.lookback_days',      type: 'int',   def: 30 },
  { id: 'news-ticker',  path: 'data.news_ticker_limit',  type: 'int',   def: 10 },
  { id: 'news-global',  path: 'data.news_global_limit',  type: 'int',   def: 8 },
  { id: 'rss-timeout',  path: 'data.rss_timeout',        type: 'int',   def: 10 },
  // Market
  { id: 'bb-squeeze',    path: 'market.bb_squeeze_threshold',  type: 'float', def: 0.04 },
  { id: 'atr-trend',     path: 'market.atr_trend_threshold',   type: 'float', def: 1.5 },
  { id: 'zone-threshold', path: 'market.zone_threshold_pct',   type: 'float', def: 2.0 },
  { id: 'min-bars',      path: 'market.min_bars_required',     type: 'int',   def: 50 },
];

let _strategyLoaded = false;

function initStrategy() {
  Router.register('strategy', loadStrategy);

  // Preset switch
  const presetSelect = document.getElementById('strategy-preset-select');
  if (presetSelect) {
    presetSelect.addEventListener('change', async () => {
      const name = presetSelect.value;
      if (!name) return;
      try {
        const res = await API.switchPreset(name);
        if (res.error) { showToast(res.message || res.error, 'error'); return; }
        fillStrategyForm(res.strategy);
        showToast(`已切换到「${name}」预设`, 'success');
      } catch (e) {
        showToast(`切换失败: ${e.message}`, 'error');
      }
    });
  }

  // Save button
  document.getElementById('btn-strategy-save')?.addEventListener('click', saveStrategy);

  // Reset button
  document.getElementById('btn-strategy-reset')?.addEventListener('click', async () => {
    if (!confirm('确定重置策略为默认（均衡型）？')) return;
    try {
      const res = await API.resetStrategy();
      if (res.error) { showToast(res.message, 'error'); return; }
      fillStrategyForm(res.strategy);
      const sel = document.getElementById('strategy-preset-select');
      if (sel) sel.value = 'balanced';
      showToast('策略已重置为默认', 'success');
    } catch (e) {
      showToast(`重置失败: ${e.message}`, 'error');
    }
  });

  // Fill defaults immediately so the form is never empty
  fillDefaults();

  // Also try to load from API right away (non-blocking)
  loadStrategy();
}

function fillDefaults() {
  STRATEGY_FIELDS.forEach(f => {
    const el = document.getElementById(`s-${f.id}`);
    if (el) el.value = f.def;
  });
}

async function loadStrategy() {
  // Try to load from API; if it fails, form still has defaults
  try {
    const [stratRes, presetsRes] = await Promise.all([
      API.getStrategy(),
      API.listPresets(),
    ]);

    if (stratRes.strategy) {
      fillStrategyForm(stratRes.strategy);
    }

    // Warnings
    const warningsEl = document.getElementById('strategy-warnings');
    if (stratRes.warnings && stratRes.warnings.length > 0) {
      warningsEl.innerHTML = stratRes.warnings.map(w =>
        `<div style="padding:2px 0;">&#9888; ${escapeHtml(w)}</div>`
      ).join('');
      warningsEl.classList.remove('hidden');
      warningsEl.style.cssText = 'background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:12px 16px;margin-bottom:12px;font-size:.8rem;color:#92400e;';
    } else if (warningsEl) {
      warningsEl.classList.add('hidden');
    }

    // Fill preset selector
    if (presetsRes.presets) {
      const sel = document.getElementById('strategy-preset-select');
      sel.innerHTML = Object.entries(presetsRes.presets).map(([key, p]) =>
        `<option value="${key}">${p.name}</option>`
      ).join('');
      sel.value = presetsRes.current || 'balanced';
    }

    _strategyLoaded = true;
  } catch (e) {
    console.error('Strategy load failed:', e);
    // Form already has defaults, just show a toast
    if (!_strategyLoaded) {
      showToast('策略 API 未就绪，使用默认值', 'info');
    }
  }
}

function fillStrategyForm(strategy) {
  if (!strategy) return;
  STRATEGY_FIELDS.forEach(f => {
    const el = document.getElementById(`s-${f.id}`);
    if (!el) return;

    const parts = f.path.split('.');
    let val = strategy;
    for (const p of parts) {
      if (val == null) break;
      val = val[p];
    }

    el.value = (val != null) ? (f.type === 'int' ? Math.round(val) : val) : f.def;
  });
}

async function saveStrategy() {
  const update = {};
  STRATEGY_FIELDS.forEach(f => {
    const el = document.getElementById(`s-${f.id}`);
    if (!el) return;
    const val = f.type === 'int' ? parseInt(el.value, 10) : parseFloat(el.value);
    if (isNaN(val)) return;

    const parts = f.path.split('.');
    let obj = update;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!obj[parts[i]]) obj[parts[i]] = {};
      obj = obj[parts[i]];
    }
    obj[parts[parts.length - 1]] = val;
  });

  try {
    const res = await API.updateStrategy(update);
    if (res.error) { showToast(`验证失败: ${res.error}`, 'error'); return; }
    fillStrategyForm(res.strategy);

    const warningsEl = document.getElementById('strategy-warnings');
    if (res.warnings && res.warnings.length > 0) {
      warningsEl.innerHTML = res.warnings.map(w =>
        `<div style="padding:2px 0;">&#9888; ${escapeHtml(w)}</div>`
      ).join('');
      warningsEl.classList.remove('hidden');
      warningsEl.style.cssText = 'background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:12px 16px;margin-bottom:12px;font-size:.8rem;color:#92400e;';
    } else if (warningsEl) {
      warningsEl.classList.add('hidden');
    }

    showToast(res.message || '策略已保存', 'success');
  } catch (e) {
    showToast(`保存失败: ${e.message}`, 'error');
  }
}

// ============================================================
// Trades Page
// ============================================================
function initTrades() {
  Router.register('trades', loadTrades);
  document.getElementById('btn-refresh-trades')?.addEventListener('click', loadTrades);
}

async function loadTrades() {
  const tbody = document.getElementById('trades-tbody');
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;"><div class="spinner" style="margin:0 auto;"></div></td></tr>';

  // Load account info + trades in parallel
  try {
    const [accountRes, tradesRes] = await Promise.all([
      API.getAccount(),
      API.getTradeHistory(),
    ]);

    // Account summary
    if (accountRes.account) {
      const a = accountRes.account;
      document.getElementById('account-total-value').textContent = `$${(a.total_value || 0).toFixed(2)}`;
      document.getElementById('account-cash').textContent = `$${(a.cash || 0).toFixed(2)}`;
      document.getElementById('account-buying-power').textContent = `$${(a.buying_power || 0).toFixed(2)}`;
      document.getElementById('account-broker').textContent = a.broker || '-';
    }

    // Trades table
    const trades = tradesRes.trades || [];
    if (trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-muted" style="text-align:center;padding:30px;">暂无交易记录</td></tr>';
      return;
    }

    tbody.innerHTML = trades.map(t => {
      const time = t.timestamp ? new Date(t.timestamp).toLocaleString('zh-CN') : '-';
      const sideClass = t.side === 'buy' ? 'positive' : 'negative';
      const statusClass = t.status === 'filled' ? 'positive' : t.status === 'rejected' ? 'negative' : '';
      return `
        <tr>
          <td style="font-size:.8rem;">${escapeHtml(time)}</td>
          <td><span class="ticker-tag">${escapeHtml(t.ticker || '-')}</span></td>
          <td class="${sideClass}" style="font-weight:600;">${(t.side || '-').toUpperCase()}</td>
          <td>${t.quantity || 0}</td>
          <td>${t.price ? `$${t.price.toFixed(2)}` : '-'}</td>
          <td><span class="${statusClass}" style="font-weight:500;">${escapeHtml(t.status || '-')}</span></td>
          <td style="font-family:var(--mono);font-size:.75rem;">${escapeHtml(t.trade_id || '-')}</td>
        </tr>`;
    }).join('');

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--red);">加载失败: ${e.message}</td></tr>`;
  }
}

// ============================================================
// Logs Page
// ============================================================
function initLogs() {
  Router.register('logs', loadLogs);
  document.getElementById('btn-refresh-logs')?.addEventListener('click', loadLogs);
  document.getElementById('log-lines-select')?.addEventListener('change', loadLogs);
}

async function loadLogs() {
  const container = document.getElementById('logs-container');
  container.textContent = '加载中...';

  const linesSelect = document.getElementById('log-lines-select');
  const lines = linesSelect ? parseInt(linesSelect.value, 10) : 100;

  try {
    const res = await API.getLogs(lines);
    const logs = res.logs || [];

    if (logs.length === 0) {
      container.textContent = res.message || '暂无日志';
      return;
    }

    // Color-code log levels
    container.innerHTML = logs.map(line => {
      let cls = '';
      if (line.includes('| ERROR')) cls = 'color:var(--red);';
      else if (line.includes('| WARNING')) cls = 'color:#eab308;';
      else if (line.includes('[dispatch]')) cls = 'color:var(--blue);';
      return `<div style="${cls}">${escapeHtml(line)}</div>`;
    }).join('');

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;

    if (res.total) {
      showToast(`已加载 ${logs.length} / ${res.total} 条日志`, 'info');
    }
  } catch (e) {
    container.textContent = `加载失败: ${e.message}`;
  }
}

// ============================================================
// Settings Page
// ============================================================
let _currentBrokerType = 'futu';

function initSettings() {
  const saveBtn = document.getElementById('btn-save-settings');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      showToast('设置已保存（运行时生效，重启后需更新 .env）', 'success');
    });
  }

  // Load broker config from backend
  loadBrokerConfig();
}

async function loadBrokerConfig() {
  try {
    const res = await API.getBrokerConfig();
    _currentBrokerType = res.broker_type || 'futu';
    updateBrokerTypeUI(_currentBrokerType);

    // Fill futu fields
    const hostEl = document.getElementById('setting-futu-host');
    if (hostEl) hostEl.value = res.futu_host || '127.0.0.1';
    const portEl = document.getElementById('setting-futu-port');
    if (portEl) portEl.value = res.futu_port || 11111;
    const envEl = document.getElementById('setting-futu-trd-env');
    if (envEl) envEl.value = res.futu_trd_env || 'simulate';
    const mktEl = document.getElementById('setting-futu-market');
    if (mktEl) mktEl.value = res.futu_market || 'HK';

    // Connection badge
    const badge = document.getElementById('broker-connection-badge');
    if (badge) {
      if (res.connected) {
        badge.textContent = `已连接 (${res.broker_name})`;
        badge.style.background = '#dcfce7';
        badge.style.color = '#166534';
      } else {
        badge.textContent = '未连接';
        badge.style.background = '#f5f5f5';
        badge.style.color = 'var(--text-muted)';
      }
    }
  } catch (e) {
    console.warn('Failed to load broker config:', e);
  }
}

window.selectBrokerType = function(type) {
  _currentBrokerType = type;
  updateBrokerTypeUI(type);
  showToast(`已选择 ${type === 'futu' ? '富途模拟盘' : '内置模拟盘'}（需重启生效）`, 'info');
};

function updateBrokerTypeUI(type) {
  const simBtn = document.getElementById('btn-broker-simulated');
  const futuBtn = document.getElementById('btn-broker-futu');
  const futuPanel = document.getElementById('futu-settings-panel');

  if (simBtn) {
    simBtn.className = type === 'simulated' ? 'btn btn-sm btn-primary' : 'btn btn-sm';
  }
  if (futuBtn) {
    futuBtn.className = type === 'futu' ? 'btn btn-sm btn-primary' : 'btn btn-sm';
  }
  if (futuPanel) {
    if (type === 'futu') {
      futuPanel.classList.remove('hidden');
    } else {
      futuPanel.classList.add('hidden');
    }
  }
}
