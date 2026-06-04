/**
 * Stocker Frontend Application
 */
document.addEventListener('DOMContentLoaded', () => {
  initChat();
  initStocks();
  initTrading();
  initReports();
  initLogs();
  initStrategy();
  initModes();
  initEvolution();
  initSettings();

  Router.init();
  checkSystemStatus();
  setInterval(checkSystemStatus, 10000);
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
  const detail = document.getElementById('runtime-detail');
  const pill = document.getElementById('runtime-status-pill');
  try {
    const [healthRes, statusRes, autoPilotRes] = await Promise.all([
      API.getHealth().catch(() => null),
      API.getStatus(),
      API.getAutoPilot().catch(() => null),
    ]);
    if (healthRes && healthRes.status === 'ok') {
      dot.className = 'status-dot';
    }
    updateRuntimeStatus(statusRes, autoPilotRes);
    updateStatusPanel(statusRes);
    if (autoPilotRes) {
      currentAutoPilot = Boolean(autoPilotRes.enabled);
      syncAutoPilotUI(currentAutoPilot);
    }
    if (statusRes.execution_mode) {
      syncModeUI(statusRes.execution_mode);
    }
  } catch {
    if (dot) dot.className = 'status-dot offline';
    if (text) text.textContent = '连接失败';
    if (detail) detail.textContent = '无法读取运行状态';
    if (pill) {
      pill.className = 'runtime-pill offline';
      pill.textContent = '服务未连接';
    }
  }
}

function updateRuntimeStatus(status, autoPilot) {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  const detail = document.getElementById('runtime-detail');
  const pill = document.getElementById('runtime-status-pill');
  const monitoring = status?.monitoring || {};
  const running = Boolean(monitoring.enabled && monitoring.running);
  const inCycle = Boolean(monitoring.in_cycle);
  const interval = monitoring.interval_seconds || '-';
  const cycles = monitoring.cycle_count || 0;
  const summary = monitoring.last_summary || {};
  const mode = (status?.execution_mode || 'observe').toUpperCase();
  const broker = status?.broker || '-';
  const autoPilotOn = Boolean(autoPilot?.enabled);

  let label = '监控关闭';
  let cls = 'warning';
  if (running && inCycle) {
    label = '监控扫描中';
    cls = 'running';
  } else if (running) {
    label = '监控运行中';
    cls = 'running';
  } else if (monitoring.enabled) {
    label = '监控待启动';
    cls = 'warning';
  }

  if (dot) dot.className = `status-dot${cls === 'running' ? '' : ' warning'}`;
  if (text) text.textContent = label;
  if (detail) {
    detail.textContent = `周期 ${interval}s · 已跑 ${cycles} 轮 · 新预警 ${summary.new_alerts ?? 0} · 持仓预警 ${summary.position_alerts ?? 0}`;
  }
  if (pill) {
    pill.className = `runtime-pill ${cls}`;
    pill.textContent = `${label} · ${mode} · ${broker}${autoPilotOn ? ' · AutoPilot' : ''}`;
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
// Stocks Page (merged Portfolio + Watchlist)
// ============================================================
let _stocksData = []; // merged dataset
let _stocksTab = 'all';

function initStocks() {
  Router.register('stocks', loadStocks);

  // Tab switching
  document.querySelectorAll('#page-stocks .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _stocksTab = btn.dataset.tab;
      document.querySelectorAll('#page-stocks .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderStocksTable();
    });
  });

  document.getElementById('btn-add-stock')?.addEventListener('click', showAddStockDialog);
  document.getElementById('btn-refresh-stocks')?.addEventListener('click', loadStocks);
  document.getElementById('btn-scan-stocks')?.addEventListener('click', scanStocks);
}

async function loadStocks() {
  const tbody = document.getElementById('stocks-tbody');
  tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:20px;"><div class="spinner" style="margin:0 auto;"></div></td></tr>';

  try {
    const [portfolioRes, watchlistRes] = await Promise.all([
      API.listPortfolio(),
      fetch('/api/v1/watchlist').then(r => r.json()),
    ]);
    const positions = portfolioRes.positions || [];
    const watchItems = watchlistRes.items || [];
    _stocksData = mergeStocksData(positions, watchItems);
    renderStocksTable();
    updateStocksSummary();

    // Fetch real-time prices for stocks missing price data
    const needPrice = _stocksData.filter(s => !s.current_price || s.current_price <= 0).map(s => s.ticker);
    if (needPrice.length > 0) {
      try {
        const qRes = await fetch('/api/v1/quotes', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({tickers: needPrice})
        }).then(r => r.json());

        const quotes = qRes.quotes || {};
        let updated = false;
        for (const s of _stocksData) {
          const q = quotes[s.ticker];
          if (q && q.price > 0) {
            s.current_price = q.price;
            s.name = s.name || q.name || '';
            if (s.type === 'held' && s.avg_cost > 0) {
              s.unrealized_pnl = (q.price - s.avg_cost) * s.quantity;
            }
            updated = true;
          }
        }
        if (updated) {
          renderStocksTable();
          updateStocksSummary();
        }
      } catch { /* ignore price fetch failure */ }
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;padding:20px;color:var(--red);">加载失败: ${e.message}</td></tr>`;
  }
}

function mergeStocksData(positions, watchItems) {
  const map = {};

  // Index positions by ticker
  for (const p of positions) {
    const t = (p.ticker || '').toUpperCase();
    map[t] = {
      ticker: t,
      name: p.name || '',
      market: p.market_type || '',
      tags: [],
      quantity: p.quantity || 0,
      avg_cost: p.avg_cost || 0,
      current_price: p.current_price || 0,
      unrealized_pnl: p.unrealized_pnl || 0,
      signal: null,
      type: 'held',
    };
  }

  // Merge watchlist items
  for (const wi of watchItems) {
    const t = (wi.ticker || '').toUpperCase();
    if (map[t]) {
      // Exists in portfolio — enrich with watchlist data
      map[t].name = map[t].name || wi.name || '';
      map[t].market = map[t].market || wi.market || '';
      map[t].tags = wi.tags || [];
      map[t].signal = wi.latest_signal || null;
    } else {
      // Watching only
      const sig = wi.latest_signal || {};
      map[t] = {
        ticker: t,
        name: wi.name || '',
        market: wi.market || '',
        tags: wi.tags || [],
        quantity: 0,
        avg_cost: 0,
        current_price: sig.indicators?.current_price || sig.suggested_price || 0,
        unrealized_pnl: 0,
        signal: wi.latest_signal || null,
        type: 'watching',
      };
    }
  }

  return Object.values(map);
}

function renderStocksTable() {
  const tbody = document.getElementById('stocks-tbody');
  let items = _stocksData;

  if (_stocksTab === 'held') items = items.filter(s => s.type === 'held');
  if (_stocksTab === 'watching') items = items.filter(s => s.type === 'watching');

  if (items.length === 0) {
    const msg = _stocksTab === 'held' ? '暂无持仓' : _stocksTab === 'watching' ? '暂无观察股票' : '股票池为空，点击"+ 添加"开始';
    tbody.innerHTML = `<tr><td colspan="11" class="text-muted" style="text-align:center;padding:30px;">${msg}</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(s => {
    const isHeld = s.type === 'held';
    const sig = s.signal || {};
    const sigType = sig.signal_type || '';
    const sigEmoji = sigType === 'entry_long' ? '<span style="color:var(--green);">买入</span>' :
                     sigType === 'exit_long' ? '<span style="color:var(--red);">卖出</span>' : '-';
    const strength = sig.strength || 0;
    const tags = (s.tags || []).map(t => `<span class="wl-tag">${t}</span>`).join(' ');
    const pnl = s.unrealized_pnl || 0;
    const pnlPct = s.avg_cost > 0 ? ((s.current_price - s.avg_cost) / s.avg_cost * 100) : 0;

    return `<tr>
      <td><span class="ticker-tag">${s.ticker}</span></td>
      <td>${s.name || '-'}</td>
      <td>${s.market || '-'}</td>
      <td>${tags || '-'}</td>
      <td>${isHeld ? s.quantity : '<span class="cell-dim">--</span>'}</td>
      <td>${isHeld ? (s.avg_cost > 0 ? s.avg_cost.toFixed(2) : '-') : '<span class="cell-dim">--</span>'}</td>
      <td>${s.current_price > 0 ? s.current_price.toFixed(2) : '-'}</td>
      <td>${isHeld ? `<span class="${pnl >= 0 ? 'positive' : 'negative'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%)</span>` : '<span class="cell-dim">--</span>'}</td>
      <td>${sigEmoji}</td>
      <td><div class="signal-bar"><div class="signal-bar-fill" style="width:${strength}%;background:${strength>60?'var(--green)':strength>30?'var(--yellow)':'var(--text-muted)'};"></div></div><span class="text-sm">${strength > 0 ? strength.toFixed(0) : '-'}</span></td>
      <td>
        ${!isHeld ? `<button class="btn btn-sm${sigType === 'entry_long' ? ' btn-primary' : ''}" onclick="tradeStock('${s.ticker}', 'buy', ${s.current_price})">建仓</button>` : ''}
        ${isHeld ? `<button class="btn btn-sm btn-danger" onclick="tradeStock('${s.ticker}', 'sell', ${s.current_price}, ${s.quantity})">平仓</button>` : ''}
        <button class="btn btn-sm" onclick="analyzeStock('${s.ticker}')">分析</button>
        <button class="btn btn-sm" style="color:var(--text-muted);border-color:var(--border);" onclick="removeStock('${s.ticker}', ${isHeld})">移除</button>
      </td>
    </tr>`;
  }).join('');
}

function updateStocksSummary() {
  const held = _stocksData.filter(s => s.type === 'held');
  const total = held.reduce((sum, s) => sum + (s.quantity || 0) * (s.current_price || s.avg_cost || 0), 0);
  const pnl = held.reduce((sum, s) => sum + (s.unrealized_pnl || 0), 0);

  let signalCount = 0;
  _stocksData.forEach(s => {
    const st = s.signal?.signal_type;
    if (st === 'entry_long' || st === 'exit_long') signalCount++;
  });

  document.getElementById('stocks-total-value').textContent = `$${total.toFixed(2)}`;
  const pnlEl = document.getElementById('stocks-total-pnl');
  pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
  pnlEl.className = `summary-card-value ${pnl >= 0 ? 'positive' : 'negative'}`;
  document.getElementById('stocks-count').textContent = _stocksData.length;
  document.getElementById('stocks-signals').textContent = signalCount;
}

function showAddStockDialog() {
  const ticker = prompt('输入股票代码 (例: AAPL, 0700.HK):');
  if (!ticker) return;
  const name = prompt('名称 (可留空):') || '';
  const market = prompt('市场 (HK/US/CN, 可留空):') || '';
  const hasPosition = confirm('是否有持仓？（确定=有，取消=仅观察）');

  if (hasPosition) {
    const qty = parseInt(prompt('持仓数量:', '100'), 10);
    if (isNaN(qty) || qty <= 0) { showToast('无效数量', 'error'); return; }
    const cost = parseFloat(prompt('成本价:', '0'));

    // Add to both portfolio and watchlist
    Promise.all([
      API.addPosition(ticker.toUpperCase(), qty, cost),
      fetch('/api/v1/watchlist', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ticker: ticker.trim(), name, market})
      }),
    ]).then(() => {
      showToast(`已添加 ${ticker.toUpperCase()}（含持仓）`, 'success');
      loadStocks();
    }).catch(e => showToast(`添加失败: ${e.message}`, 'error'));
  } else {
    // Add to watchlist only
    fetch('/api/v1/watchlist', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ticker: ticker.trim(), name, market})
    })
    .then(r => r.json())
    .then(() => {
      showToast(`已添加 ${ticker.toUpperCase()} 到观察列表`, 'success');
      loadStocks();
    })
    .catch(e => showToast(`添加失败: ${e.message}`, 'error'));
  }
}

window.analyzeStock = function(ticker) {
  Router.navigate('chat');
  setTimeout(() => {
    const input = document.getElementById('chat-input');
    if (input) { input.value = `分析 ${ticker}，给出投资建议`; input.focus(); }
  }, 100);
};

window.removeStock = function(ticker, isHeld) {
  if (!confirm(`确定移除 ${ticker}？`)) return;

  const promises = [];
  if (isHeld) promises.push(API.removePosition(ticker));
  promises.push(fetch(`/api/v1/watchlist/${ticker}`, {method: 'DELETE'}));

  Promise.all(promises)
    .then(() => { showToast(`已移除 ${ticker}`, 'success'); loadStocks(); })
    .catch(e => showToast(`移除失败: ${e.message}`, 'error'));
};

window.tradeStock = async function(ticker, side, fallbackPrice, maxQty) {
  const action = side === 'buy' ? '建仓' : '平仓';

  // 1. Fetch real-time price via westock-data
  showToast(`正在获取 ${ticker} 实时报价...`, 'info');
  let price = fallbackPrice || 0;
  let priceName = '';
  try {
    const q = await fetch(`/api/v1/quote/${encodeURIComponent(ticker)}`).then(r => r.json());
    if (q.price && q.price > 0) {
      price = q.price;
      priceName = q.name ? ` (${q.name})` : '';
      const chg = q.change_pct ? ` ${q.change_pct >= 0 ? '+' : ''}${q.change_pct.toFixed(2)}%` : '';
      showToast(`${ticker}${priceName} 实时价: $${price.toFixed(2)}${chg}`, 'success');
    } else {
      showToast(`获取报价失败${q.error ? ': ' + q.error : ''}`, 'error');
    }
  } catch (e) {
    showToast(`报价服务不可用: ${e.message}`, 'error');
  }

  // Block trade if no price
  if (price <= 0) {
    showToast(`无法获取 ${ticker} 的实时价格，请检查股票代码是否正确（如 AAPL 而非 APPL）`, 'error');
    return;
  }

  // 2. Confirm with user
  const defaultQty = side === 'sell' ? (maxQty || 100) : 100;
  const priceStr = price > 0 ? `$${price.toFixed(2)}` : '未知';
  const qtyStr = prompt(
    `${action} ${ticker}${priceName}\n` +
    `实时价格: ${priceStr}\n` +
    `${side === 'sell' ? `持仓数量: ${maxQty || '?'}\n` : ''}` +
    `\n请输入${side === 'sell' ? '平仓' : '建仓'}数量:`,
    String(defaultQty)
  );
  if (!qtyStr) return;
  const qty = parseInt(qtyStr, 10);
  if (isNaN(qty) || qty <= 0) { showToast('无效数量', 'error'); return; }
  if (side === 'sell' && maxQty && qty > maxQty) {
    showToast(`数量不能超过持仓 ${maxQty}`, 'error');
    return;
  }

  // 3. Execute trade via broker
  showToast(`正在${action} ${ticker} x${qty}...`, 'info');

  API.trade(ticker, side, qty, price > 0 ? price : null)
    .then(res => {
      if (res.status === 'filled') {
        showToast(`${action}成功: ${ticker} x${qty} @ $${res.filled_price?.toFixed(2) || '?'}`, 'success');
        loadStocks();
      } else if (res.status === 'rejected') {
        showToast(res.response || `${action}被拒绝`, 'error');
      } else {
        showToast(res.response || `${action}状态: ${res.status}`, 'info');
      }
    })
    .catch(e => showToast(`${action}失败: ${e.message}`, 'error'));
};

async function scanStocks() {
  showToast('正在扫描所有股票...', 'info');
  const wrap = document.getElementById('stocks-scan-wrap');
  const content = document.getElementById('stocks-scan-content');
  wrap.style.display = 'block';
  content.innerHTML = '<div class="spinner" style="margin:20px auto;"></div>';

  try {
    const res = await fetch('/api/v1/watchlist/scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({min_strength: 20})
    }).then(r => r.json());

    const results = res.results || [];
    if (!results.length) {
      content.innerHTML = '<p style="text-align:center;padding:20px;color:var(--text-muted);">无信号结果</p>';
      return;
    }

    content.innerHTML = '<table><thead><tr><th>代码</th><th>信号</th><th>强度</th><th>价格</th><th>环境</th><th>原因</th></tr></thead><tbody>' +
      results.map(r => {
        const emoji = r.signal_type === 'entry_long' ? '<span style="color:var(--green);">买入</span>' :
                      r.signal_type === 'exit_long' ? '<span style="color:var(--red);">卖出</span>' : '中性';
        const reasons = (r.reasons || []).join('; ');
        return `<tr><td><strong>${r.ticker}</strong></td><td>${emoji}</td><td>${(r.strength||0).toFixed(0)}</td><td>${(r.suggested_price||0).toFixed(2)}</td><td>${r.market_environment||'-'}</td><td class="text-sm">${reasons}</td></tr>`;
      }).join('') +
      '</tbody></table>';

    showToast(`扫描完成，${results.length} 个结果`, 'success');
    loadStocks(); // Refresh to show updated signals
  } catch (e) {
    content.innerHTML = `<p style="color:var(--red);padding:20px;">扫描失败: ${e.message}</p>`;
  }
}

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
let currentAutoPilot = false;

function initModes() {
  Router.register('modes', loadModes);

  // Mode card click → toggle between ACTIVE/OBSERVE
  document.querySelectorAll('#page-modes .mode-card[data-mode]').forEach(card => {
    card.addEventListener('click', () => {
      const mode = card.dataset.mode;
      setExecutionMode(mode);
    });
  });

  // AutoPilot card click
  document.getElementById('autopilot-card')?.addEventListener('click', toggleAutoPilot);

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
    const [statusRes, apRes] = await Promise.all([
      API.getStatus(),
      API.getAutoPilot(),
    ]);
    updateStatusPanel(statusRes);
    // Sync mode from server
    if (statusRes.execution_mode) {
      currentExecutionMode = statusRes.execution_mode;
      syncModeUI(statusRes.execution_mode);
    }
    // Sync auto-pilot
    if (apRes) {
      currentAutoPilot = apRes.enabled || false;
      syncAutoPilotUI(currentAutoPilot);
    }
  } catch {
    // ignore
  }
}

async function toggleAutoPilot() {
  const newState = !currentAutoPilot;
  try {
    await API.setAutoPilot(newState);
    currentAutoPilot = newState;
    syncAutoPilotUI(newState);
    showToast(`AutoPilot ${newState ? '已开启' : '已关闭'}`, newState ? 'success' : 'info');
  } catch (e) {
    showToast(`切换失败: ${e.message}`, 'error');
  }
}

function syncAutoPilotUI(enabled) {
  const card = document.getElementById('autopilot-card');
  const title = document.getElementById('autopilot-title');
  if (card) {
    card.classList.toggle('active', enabled);
  }
  if (title) {
    title.textContent = enabled ? 'AutoPilot — 运行中' : 'AutoPilot — 已关闭';
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

  // Continuous monitoring
  const monitoring = data.monitoring || {};
  const monText = monitoring.enabled
    ? `${monitoring.running ? (monitoring.in_cycle ? '扫描中' : '运行中') : '待启动'} · ${monitoring.cycle_count || 0} 轮`
    : '已关闭';
  setVal('monitoring', monText, monitoring.enabled && monitoring.running ? '' : 'warning');

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
// Trading Page (merged Swing Trades + Trade History)
// ============================================================
let _tradingTab = 'swing';

function initTrading() {
  Router.register('trading', loadTrading);

  // Tab switching
  document.querySelectorAll('#page-trading .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _tradingTab = btn.dataset.tab;
      document.querySelectorAll('#page-trading .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      // Toggle panes
      document.getElementById('pane-swing').classList.toggle('active', _tradingTab === 'swing');
      document.getElementById('pane-history').classList.toggle('active', _tradingTab === 'history');

      // Toggle filter visibility (only show for swing tab)
      const swFilter = document.getElementById('trading-sw-filter');
      if (swFilter) swFilter.style.display = _tradingTab === 'swing' ? '' : 'none';

      // Load active tab data
      if (_tradingTab === 'swing') loadSwingPane();
      else loadHistoryPane();
    });
  });

  document.getElementById('btn-refresh-trading')?.addEventListener('click', loadTrading);
  document.getElementById('trading-sw-filter')?.addEventListener('change', loadSwingPane);
}

async function loadTrading() {
  if (_tradingTab === 'swing') await loadSwingPane();
  else await loadHistoryPane();

  // Load account info for summary cards
  try {
    const accountRes = await API.getAccount();
    if (accountRes.account) {
      const a = accountRes.account;
      document.getElementById('trading-account-value').textContent = `$${(a.total_value || 0).toFixed(2)}`;
      document.getElementById('trading-cash').textContent = `$${(a.cash || 0).toFixed(2)}`;
    }
  } catch { /* ignore */ }
}

async function loadSwingPane() {
  const tbody = document.getElementById('trading-swing-tbody');
  tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:20px;"><div class="spinner" style="margin:0 auto;"></div></td></tr>';

  const statusFilter = document.getElementById('trading-sw-filter')?.value || '';

  try {
    const [tradesRes, statsRes] = await Promise.all([
      fetch(`/api/v1/swing-trades?status=${statusFilter}`).then(r => r.json()),
      fetch('/api/v1/swing-trades/stats').then(r => r.json()),
    ]);

    const trades = tradesRes.trades || [];
    const stats = statsRes.stats || {};

    // Update summary cards
    document.getElementById('trading-winrate').textContent = (stats.win_rate || 0).toFixed(1) + '%';
    const pnlEl = document.getElementById('trading-pnl');
    const pnlVal = stats.total_pnl || 0;
    pnlEl.textContent = (pnlVal >= 0 ? '+' : '') + '$' + pnlVal.toFixed(2);
    pnlEl.className = 'summary-card-value ' + (pnlVal >= 0 ? 'positive' : 'negative');

    if (!trades.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="text-muted" style="text-align:center;padding:30px;">暂无波段操作记录</td></tr>';
      return;
    }

    tbody.innerHTML = trades.map(t => {
      const isOpen = t.status === 'open';
      const statusBadge = isOpen ? '<span class="badge badge-open">进行中</span>' : '<span class="badge badge-closed">已完结</span>';
      const pnl = t.pnl || 0;
      const pnlPct = t.pnl_pct || 0;
      const pnlClass = pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : '';
      const entryDate = t.entry_time ? new Date(t.entry_time).toLocaleDateString('zh-CN') : '-';
      const exitPrice = t.exit_price != null ? t.exit_price.toFixed(2) : '-';
      const pnlStr = isOpen ? '-' : `<span class="${pnlClass}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span>`;
      const pnlPctStr = isOpen ? '-' : `<span class="${pnlClass}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</span>`;
      const actions = isOpen ? `<a href="#stocks" class="btn btn-sm" style="font-size:.75rem;" onclick="Router.navigate('stocks')">去平仓</a>` : '';

      return `<tr>
        <td class="text-sm">${t.trade_id}</td>
        <td><strong>${t.ticker}</strong></td>
        <td>${statusBadge}</td>
        <td>${(t.entry_price||0).toFixed(2)}</td>
        <td>${entryDate}</td>
        <td>${exitPrice}</td>
        <td>${pnlStr}</td>
        <td>${pnlPctStr}</td>
        <td>${t.hold_days || (isOpen ? Math.floor((Date.now() - new Date(t.entry_time).getTime()) / 86400000) : 0)}</td>
        <td>${actions}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:20px;color:var(--red);">加载失败: ${e.message}</td></tr>`;
  }
}

async function loadHistoryPane() {
  const tbody = document.getElementById('trading-history-tbody');
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;"><div class="spinner" style="margin:0 auto;"></div></td></tr>';

  try {
    const tradesRes = await API.getTradeHistory();
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
// EvolutionSkill Page
// ============================================================
function initEvolution() {
  Router.register('evolution', loadEvolution);
  document.getElementById('btn-evolution-refresh')?.addEventListener('click', loadEvolution);
  document.getElementById('btn-evolution-seed')?.addEventListener('click', async () => {
    try {
      const res = await API.seedEvolutionSkills(false);
      showToast(`已创建 ${res.created?.length || 0} 个默认 skill`, 'success');
      loadEvolution();
    } catch (e) {
      showToast(`初始化失败: ${e.message}`, 'error');
    }
  });
  document.getElementById('btn-evolution-review')?.addEventListener('click', runEvolutionReview);
}

async function loadEvolution() {
  const skillBody = document.getElementById('evolution-skills-tbody');
  const patchBody = document.getElementById('evolution-patches-tbody');
  const tracesEl = document.getElementById('evolution-traces-list');
  try {
    const [skillsRes, patchesRes, tracesRes] = await Promise.all([
      API.listEvolutionSkills(),
      API.listEvolutionPatches('', 50),
      API.listEvolutionTraces(50),
    ]);
    const skills = skillsRes.skills || [];
    const patches = patchesRes.patches || [];
    const traces = tracesRes.traces || [];
    document.getElementById('evo-skill-count').textContent = skills.length;
    document.getElementById('evo-patch-count').textContent = patches.filter(p => ['draft', 'validated', 'approved'].includes(p.status)).length;
    document.getElementById('evo-trace-count').textContent = traces.length;
    document.getElementById('evo-status').textContent = 'READY';

    skillBody.innerHTML = skills.length ? skills.map(s => `
      <tr>
        <td style="font-family:var(--mono);font-size:.72rem;">${escapeHtml(s.id || '-')}</td>
        <td>${escapeHtml(s.team || '-')}/${escapeHtml(s.node || '-')}</td>
        <td><span class="report-tag">${escapeHtml(s.status || '-')}</span></td>
        <td>${escapeHtml(s.risk_level || '-')}</td>
        <td>v${s.version || 1}</td>
        <td>${escapeHtml(s.description || '')}</td>
      </tr>
    `).join('') : '<tr><td colspan="6" class="text-muted" style="text-align:center;padding:20px;">暂无 EvolutionSkill，点击“初始化默认 Skill”。</td></tr>';

    patchBody.innerHTML = patches.length ? patches.map(p => `
      <tr>
        <td style="font-family:var(--mono);font-size:.72rem;">${escapeHtml((p.patch_id || '').slice(0, 10))}</td>
        <td style="font-family:var(--mono);font-size:.72rem;">${escapeHtml(p.target_skill_id || '-')}</td>
        <td><span class="report-tag">${escapeHtml(p.status || '-')}</span></td>
        <td>${escapeHtml(p.risk_level || '-')}</td>
        <td>${escapeHtml(p.reason || '')}</td>
        <td>
          <button class="btn btn-sm" onclick="validateEvolutionPatch('${escapeHtml(p.patch_id)}')">校验</button>
          <button class="btn btn-sm" onclick="approveEvolutionPatch('${escapeHtml(p.patch_id)}')">审批</button>
          <button class="btn btn-sm btn-primary" onclick="applyEvolutionPatch('${escapeHtml(p.patch_id)}')">应用</button>
        </td>
      </tr>
    `).join('') : '<tr><td colspan="6" class="text-muted" style="text-align:center;padding:20px;">暂无 patch 草案。</td></tr>';

    tracesEl.innerHTML = traces.length ? traces.slice(0, 20).map(t => `
      <div style="padding:8px 0;border-bottom:1px solid var(--border);">
        <div><b>${escapeHtml(t.team || '-')}/${escapeHtml(t.node || '-')}</b> ${escapeHtml(t.ticker || '')} ${t.skill_id ? `<span class="report-tag">${escapeHtml(t.skill_id)}</span>` : ''}</div>
        <div class="text-muted">${escapeHtml(t.output_summary || t.input_summary || '').slice(0, 220)}</div>
      </div>
    `).join('') : '<div class="text-muted">暂无节点轨迹。运行分析或风险评估后会自动记录。</div>';
  } catch (e) {
    document.getElementById('evo-status').textContent = 'ERROR';
    skillBody.innerHTML = `<tr><td colspan="6" class="text-muted" style="text-align:center;padding:20px;">加载失败: ${escapeHtml(e.message)}</td></tr>`;
    patchBody.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center;padding:20px;">加载失败</td></tr>';
    tracesEl.textContent = `加载失败: ${e.message}`;
  }
}

async function runEvolutionReview() {
  const box = document.getElementById('evolution-review-box');
  box.textContent = '生成中...';
  try {
    const res = await API.runEvolutionWeeklyReview({ persist: true });
    const review = res.review || {};
    const stats = review.stats || {};
    const recs = review.recommendations || [];
    box.innerHTML = `
      <div style="margin-bottom:8px;">Skills: ${stats.skills || 0}，Traces: ${stats.traces || 0}，Pending patches: ${stats.pending_patches || 0}</div>
      ${recs.length ? recs.map(r => `<div style="padding:6px 0;border-top:1px solid var(--border);">${escapeHtml(r)}</div>`).join('') : '<div class="text-muted">暂无建议。</div>'}
    `;
    showToast('周复盘已生成', 'success');
  } catch (e) {
    box.textContent = `生成失败: ${e.message}`;
  }
}

window.validateEvolutionPatch = async function(patchId) {
  try {
    const res = await API.validateEvolutionPatch(patchId);
    showToast(res.success ? 'patch 校验通过' : 'patch 校验失败', res.success ? 'success' : 'error');
    loadEvolution();
  } catch (e) {
    showToast(`校验失败: ${e.message}`, 'error');
  }
};

window.approveEvolutionPatch = async function(patchId) {
  const evidence = prompt('如为高风险 patch，请输入 paper:/backtest: 证据 ID；低风险可留空。') || '';
  try {
    const res = await API.approveEvolutionPatch(patchId, {
      approved_by: 'web-user',
      evidence_ids: evidence.trim() ? [evidence.trim()] : [],
    });
    showToast(res.success ? 'patch 已审批' : 'patch 审批失败', res.success ? 'success' : 'error');
    loadEvolution();
  } catch (e) {
    showToast(`审批失败: ${e.message}`, 'error');
  }
};

window.applyEvolutionPatch = async function(patchId) {
  if (!confirm('确认应用该 patch？高风险 patch 需要已审批并绑定 paper/backtest 证据。')) return;
  try {
    const res = await API.applyEvolutionPatch(patchId);
    showToast(res.success ? 'patch 已应用' : (res.error || 'patch 应用失败'), res.success ? 'success' : 'error');
    loadEvolution();
  } catch (e) {
    showToast(`应用失败: ${e.message}`, 'error');
  }
};

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
