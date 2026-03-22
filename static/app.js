/* app.js — 船员激励系统前端逻辑 */

// ── 状态 ──────────────────────────────────────────────────────────────────────
const state = {
  crew: [],          // [{wechat_name, name, checkins, comment, message, skip, status}]
  filepath: '',
  executing: false,
  genAllSrc: null,   // EventSource for generate-all
  execSrc: null,     // EventSource for execute
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const fileInput   = $('fileInput');
const fileDrop    = $('fileDrop');
const csvName     = $('csvName');
const emptyState  = $('emptyState');
const missionTable = $('missionTable');
const tableBody   = $('tableBody');
const btnGenAll   = $('btnGenAll');
const btnSave     = $('btnSave');
const btnExecute  = $('btnExecute');
const btnStop     = $('btnStop');
const consoleBody = $('consoleBody');
const statTotal   = $('statTotal');
const statReady   = $('statReady');
const statSkip    = $('statSkip');

// ── 心跳 ──────────────────────────────────────────────────────────────────────
let heartbeatInterval = setInterval(sendHB, 5000);
function sendHB() { fetch('/api/heartbeat', { method: 'POST' }).catch(() => {}); }

document.addEventListener('visibilitychange', () => {
  clearInterval(heartbeatInterval);
  heartbeatInterval = setInterval(sendHB, document.hidden ? 15000 : 5000);
});

// ── 文件导入 ──────────────────────────────────────────────────────────────────
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) uploadCSV(fileInput.files[0]);
});

fileDrop.addEventListener('dragover', e => { e.preventDefault(); fileDrop.classList.add('drag-over'); });
fileDrop.addEventListener('dragleave', () => fileDrop.classList.remove('drag-over'));
fileDrop.addEventListener('drop', e => {
  e.preventDefault();
  fileDrop.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f && f.name.endsWith('.csv')) uploadCSV(f);
});

async function uploadCSV(file) {
  log(`正在加载 ${file.name} ...`, 'muted');
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/api/load-csv', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) { log(`❌ 加载失败: ${data.error}`, 'error'); return; }

    state.filepath = data.filepath;
    state.crew = data.crew.map(r => ({ ...r, status: r.message ? 'ready' : 'pending' }));
    csvName.textContent = data.filename;
    log(`✅ 已加载 ${data.crew.length} 位成员 — ${data.filename}`);
    renderTable();
    setButtonState();
  } catch (e) {
    log(`❌ 网络错误: ${e.message}`, 'error');
  }
}

// ── 渲染表格 ──────────────────────────────────────────────────────────────────
const RENDER_BATCH = 8;   // 每帧最多渲染行数，避免单帧阻塞 >50ms

function renderTable() {
  emptyState.hidden = true;
  missionTable.hidden = false;
  tableBody.innerHTML = '';
  renderBatch(0);
}

function renderBatch(startIdx) {
  const end = Math.min(startIdx + RENDER_BATCH, state.crew.length);
  const frag = document.createDocumentFragment();
  for (let i = startIdx; i < end; i++) {
    frag.appendChild(buildRow(state.crew[i], i));
  }
  tableBody.appendChild(frag);
  if (end < state.crew.length) {
    requestAnimationFrame(() => renderBatch(end));
  } else {
    updateStats();
  }
}

function buildRow(row, i) {
  const tr = document.createElement('tr');
  tr.dataset.idx = i;
  if (row.skip) tr.classList.add('skipped-row');

  const preview = row.message
    ? row.message.replace(/\n/g, ' ').slice(0, 55) + (row.message.length > 55 ? '…' : '')
    : '— 待生成 —';

  tr.innerHTML = `
    <td class="col-skip"><input type="checkbox" class="skip-check" ${row.skip ? 'checked' : ''}></td>
    <td class="col-idx"><span class="row-idx">${String(i + 1).padStart(2, '0')}</span></td>
    <td class="col-status">${renderBadge(row.status)}</td>
    <td class="col-name">
      <div class="name-text">${esc(row.name)}</div>
      <div class="wechat-name" title="${esc(row.wechat_name)}">${esc(row.wechat_name)}</div>
    </td>
    <td class="col-checkins" style="text-align:center;font-family:var(--font-mono)">${row.checkins}</td>
    <td class="col-preview">
      <div class="msg-preview ${row.message ? 'has-msg' : ''}" title="点击展开编辑">${esc(preview)}</div>
    </td>
    <td class="col-actions">
      <div class="row-actions">
        <button class="btn-row btn-gen-one" title="AI 生成">✨</button>
        <button class="btn-row btn-expand" title="展开编辑">✏️</button>
      </div>
    </td>`;

  // Skip checkbox
  tr.querySelector('.skip-check').addEventListener('change', e => {
    state.crew[i].skip = e.target.checked;
    tr.classList.toggle('skipped-row', e.target.checked);
    updateStats();
    setButtonState();
  });

  // Preview click = expand
  tr.querySelector('.msg-preview').addEventListener('click', () => toggleExpand(tr, i));
  tr.querySelector('.btn-expand').addEventListener('click', () => toggleExpand(tr, i));

  // Generate one
  tr.querySelector('.btn-gen-one').addEventListener('click', () => generateOne(i, tr));

  return tr;
}

function toggleExpand(tr, i) {
  const existing = tr.nextElementSibling;
  if (existing && existing.classList.contains('expand-row')) {
    // save content back
    state.crew[i].message = existing.querySelector('.msg-editor').value;
    if (state.crew[i].message) state.crew[i].status = 'ready';
    existing.remove();
    tr.classList.remove('expanded');
    refreshRow(i);
    return;
  }
  tr.classList.add('expanded');
  const expTr = document.createElement('tr');
  expTr.classList.add('expand-row');
  expTr.innerHTML = `<td colspan="7">
    <textarea class="msg-editor" rows="4">${esc(state.crew[i].message || '')}</textarea>
  </td>`;
  tr.after(expTr);
  expTr.querySelector('.msg-editor').focus();
}

function refreshRow(i) {
  const row = state.crew[i];
  const tr = tableBody.querySelector(`tr[data-idx="${i}"]`);
  if (!tr) return;
  tr.querySelector('.col-status').innerHTML = renderBadge(row.status);
  const preview = row.message
    ? row.message.replace(/\n/g, ' ').slice(0, 55) + (row.message.length > 55 ? '…' : '')
    : '— 待生成 —';
  const pDiv = tr.querySelector('.msg-preview');
  pDiv.textContent = preview;
  pDiv.classList.toggle('has-msg', !!row.message);
  updateStats();
}

function renderBadge(status) {
  const map = {
    pending:    ['PENDING',    'badge-pending'],
    ready:      ['READY ✓',   'badge-ready'],
    generating: ['GENERATING', 'badge-generating'],
    sending:    ['SENDING',    'badge-sending'],
    sent:       ['SENT ✓',    'badge-sent'],
    pasted:     ['PASTED ✓',  'badge-pasted'],
    skipped:    ['SKIPPED',   'badge-skipped'],
    fail:       ['FAIL ✗',    'badge-fail'],
    dry:        ['DRY-RUN',   'badge-dry'],
  };
  const [label, cls] = map[status] || ['—', 'badge-pending'];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ── 生成单条 ──────────────────────────────────────────────────────────────────
async function generateOne(i, tr) {
  const row = state.crew[i];
  state.crew[i].status = 'generating';
  refreshRow(i);
  const btn = tr.querySelector('.btn-gen-one');
  btn.disabled = true;

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: row.name, checkins: row.checkins, comment: row.comment }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    state.crew[i].message = data.message;
    state.crew[i].status = 'ready';

    // update open expand-row if present
    const expTr = tr.nextElementSibling;
    if (expTr && expTr.classList.contains('expand-row')) {
      expTr.querySelector('.msg-editor').value = data.message;
    }
    log(`✨ ${row.name} 消息生成完成`);
  } catch (e) {
    state.crew[i].status = 'pending';
    log(`❌ ${row.name} 生成失败: ${e.message}`, 'error');
  }
  btn.disabled = false;
  refreshRow(i);
  setButtonState();
}

// ── 全部生成 ──────────────────────────────────────────────────────────────────
btnGenAll.addEventListener('click', () => {
  if (state.genAllSrc) { state.genAllSrc.close(); state.genAllSrc = null; }

  // save any open editor
  saveOpenEditors();

  const toGen = state.crew.filter(r => !r.skip && !r.message);
  if (toGen.length === 0) { log('所有消息已就绪，无需重新生成', 'muted'); return; }

  log(`开始批量生成 ${toGen.length} 条消息 ...`);
  btnGenAll.disabled = true;

  const params = new URLSearchParams({ crew: JSON.stringify(state.crew) });
  const src = new EventSource(`/api/generate-all?${params}`);
  state.genAllSrc = src;

  src.onmessage = e => {
    if (e.data === 'DONE') { src.close(); state.genAllSrc = null; btnGenAll.disabled = false; setButtonState(); log('✅ 批量生成完成'); return; }
    const d = JSON.parse(e.data);
    const i = d.index;
    state.crew[i].message = d.message;
    state.crew[i].status = 'ready';
    refreshRow(i);
    log(`  [${String(i+1).padStart(2,'0')}] ${d.name} 已生成`);
  };
  src.onerror = () => { src.close(); state.genAllSrc = null; btnGenAll.disabled = false; log('❌ 批量生成中断', 'error'); };
});

// ── 保存 CSV ──────────────────────────────────────────────────────────────────
btnSave.addEventListener('click', async () => {
  saveOpenEditors();
  try {
    const res = await fetch('/api/save-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filepath: state.filepath, crew: state.crew }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    log(`💾 CSV 已保存 (${data.saved} 条)`, 'success');
  } catch (e) {
    log(`❌ 保存失败: ${e.message}`, 'error');
  }
});

// ── 执行发送 ──────────────────────────────────────────────────────────────────
btnExecute.addEventListener('click', async () => {
  if (state.executing) return;
  saveOpenEditors();

  // 执行前自动保存 CSV，确保消息已落盘
  try {
    const res = await fetch('/api/save-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filepath: state.filepath, crew: state.crew }),
    });
    if (!res.ok) throw new Error((await res.json()).error);
    log('💾 已自动保存 CSV', 'muted');
  } catch (e) {
    log(`❌ 自动保存失败，执行中止: ${e.message}`, 'error');
    return;
  }

  const mode = document.querySelector('input[name="mode"]:checked').value;
  const skipNames = state.crew.filter(r => r.skip).map(r => r.name).join(',');

  // reset statuses for non-skipped
  state.crew.forEach((r, i) => {
    if (!r.skip) { state.crew[i].status = 'ready'; refreshRow(i); }
    else { state.crew[i].status = 'skipped'; refreshRow(i); }
  });

  log(`\n▶ 开始执行 — 模式: ${mode}`);
  state.executing = true;
  btnExecute.disabled = true;
  btnStop.disabled = false;

  const params = new URLSearchParams({ filepath: state.filepath, mode, skip: skipNames });
  const src = new EventSource(`/api/execute?${params}`);
  state.execSrc = src;

  src.onmessage = e => {
    if (e.data === 'STREAM_END') {
      src.close(); state.execSrc = null; state.executing = false;
      btnExecute.disabled = false; btnStop.disabled = true;
      return;
    }
    try {
      const d = JSON.parse(e.data);
      handleProgressEvent(d);
    } catch { log(e.data, 'muted'); }
  };
  src.onerror = () => {
    src.close(); state.execSrc = null; state.executing = false;
    btnExecute.disabled = false; btnStop.disabled = true;
    log('⚠️ 执行流中断', 'warn');
  };
});

function handleProgressEvent(d) {
  switch (d.type) {
    case 'start':
      log(`📡 共 ${d.total} 位成员待处理`);
      break;
    case 'progress': {
      const idx = findCrewIndex(d.name);
      if (idx >= 0) { state.crew[idx].status = d.status === 'sending' ? 'sending' : d.status; refreshRow(idx); }
      const pad = String(d.index).padStart(2, '0') + '/' + String(d.total).padStart(2, '0');
      if (d.status === 'sent')    log(`✅ [${pad}] ${d.name} 已发送`, 'success');
      else if (d.status === 'pasted') log(`📋 [${pad}] ${d.name} 已粘贴`);
      else if (d.status === 'fail')   log(`❌ [${pad}] ${d.name} 失败: ${d.reason}`, 'error');
      else if (d.status === 'sending') log(`⏳ [${pad}] ${d.name} 发送中...`, 'muted');
      else if (d.status === 'dry_run') log(`🧪 [${pad}] ${d.name} 检测=${d.detect}`, 'muted');
      break;
    }
    case 'done': {
      const parts = [];
      if (d.sent)    parts.push(`已发 ${d.sent}`);
      if (d.pasted)  parts.push(`已粘贴 ${d.pasted}`);
      if (d.skipped) parts.push(`跳过 ${d.skipped}`);
      if (d.failed)  parts.push(`失败 ${d.failed}`);
      log(`━━━ 完成 ${parts.join(' / ')} ━━━`, 'done');
      break;
    }
  }
}

function findCrewIndex(name) {
  return state.crew.findIndex(r => r.name === name);
}

// ── 停止 ──────────────────────────────────────────────────────────────────────
btnStop.addEventListener('click', async () => {
  if (state.execSrc) { state.execSrc.close(); state.execSrc = null; }
  await fetch('/api/stop', { method: 'POST' });
  state.executing = false;
  btnExecute.disabled = false;
  btnStop.disabled = true;
  log('⏹ 已发送停止信号', 'warn');
});

// ── Console ───────────────────────────────────────────────────────────────────
const MAX_CONSOLE_NODES = 200;

function log(msg, cls = '') {
  const div = document.createElement('div');
  div.className = `console-line ${cls}`;
  div.textContent = msg;
  consoleBody.appendChild(div);
  // 超出上限时删除最旧的节点，防止 DOM 无限增长
  if (consoleBody.children.length > MAX_CONSOLE_NODES) {
    consoleBody.removeChild(consoleBody.firstChild);
  }
  consoleBody.scrollTop = consoleBody.scrollHeight;
}

$('consoleClear').addEventListener('click', () => {
  consoleBody.innerHTML = '<div class="console-line muted">— 已清空 —</div>';
});

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function saveOpenEditors() {
  document.querySelectorAll('.expand-row').forEach(expTr => {
    const mainTr = expTr.previousElementSibling;
    if (!mainTr) return;
    const i = parseInt(mainTr.dataset.idx, 10);
    if (isNaN(i)) return;
    const val = expTr.querySelector('.msg-editor').value;
    state.crew[i].message = val;
    if (val) state.crew[i].status = 'ready';
    refreshRow(i);
  });
}

function updateStats() {
  const total = state.crew.length;
  const ready = state.crew.filter(r => !r.skip && r.message).length;
  const skip  = state.crew.filter(r => r.skip).length;
  statTotal.textContent = total || '—';
  statReady.textContent = total ? ready : '—';
  statSkip.textContent  = total ? skip  : '—';
}

function setButtonState() {
  const hasData = state.crew.length > 0;
  const hasAny  = state.crew.some(r => !r.skip);
  btnGenAll.disabled  = !hasData || state.executing;
  btnSave.disabled    = !hasData;
  btnExecute.disabled = !hasData || !hasAny || state.executing;
}

// ── Mode card highlight ───────────────────────────────────────────────────────
document.querySelectorAll('.mode-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.mode-card').forEach(c => c.removeAttribute('data-active'));
    card.setAttribute('data-active', '1');
  });
});
