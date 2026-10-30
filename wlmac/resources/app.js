// 本文件为 macOS 版界面逻辑(本仓库新增),数据来自本地 Flask API。
// 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,维护者 YZBRH / lxbsdsg · GPLv3
/* WeLearn Helper for macOS —— 界面逻辑(轮询本地 API,渲染状态) */

const $ = (id) => document.getElementById(id);

const PRESETS = {
  accuracy: ['100', '95', '90', '80', '70,100', '85,100'],
  time: ['30', '60', '120', '300', '20,60', '60,180'],
};

const HELP = {
  accuracy: '每个练习写入的完成度正确率。固定值填 <code>100</code>;随机区间填 <code>70,100</code>(下限,上限)。',
  time: '每个小节累计的学习秒数。固定值填 <code>30</code>;随机区间填 <code>20,60</code>。',
};

const S = {
  snap: null,
  seq: 0,
  mode: 'accuracy',
  selectedCid: null,
  selectedUnit: 0,
  checkedByUnit: {},     // {unitNo: Set(sectionNo)}
  sectionsSeen: {},
  noticeSeq: 0,
  lastSig: {},
  loggingIn: false,
  dragging: false,
};

/* ------------------------------------------------------------------ 工具 */
async function api(path, body) {
  const opts = body === undefined
    ? { method: 'GET' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  try {
    const res = await fetch(path, opts);
    return await res.json();
  } catch (err) {
    return { ok: false, error: '本地服务未响应:' + err };
  }
}

let toastTimer = null;
function toast(text, kind = '') {
  const el = $('toast');
  el.textContent = text;
  el.className = 'toast show ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast hidden ' + kind; }, 5200);
}

function classify(text) {
  if (/^\[提交中\]|^\s+└/.test(text)) return 'lv-run';
  if (/^\[已完成\]|^\[跳过\]/.test(text)) return 'lv-dim';
  if (/^\[!\]/.test(text)) return 'lv-warn';
  if (/^\[错误\]|^\[网络错误\]/.test(text)) return 'lv-err';
  if (/^方式[12]|^本次共|^开始任务|^登录成功|^已切换到|^已停止|^已请求停止/.test(text)) return 'lv-strong';
  if (/^(账号或密码错误|登录.|网络请求失败|未预期)/.test(text)) return 'lv-err';
  return '';
}

/* ------------------------------------------------------------------ 顶栏 */
function moveThumb() {
  const active = document.querySelector('.seg-item.is-active');
  const thumb = $('seg-thumb');
  if (!active || !thumb) return;
  thumb.style.width = active.offsetWidth + 'px';
  thumb.style.transform = `translateX(${active.offsetLeft - active.parentElement.querySelector('.seg-item').offsetLeft}px)`;
}

function setMode(mode, push = true) {
  if (S.mode === mode) return;
  S.mode = mode;
  document.querySelectorAll('.seg-item').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.mode === mode);
  });
  moveThumb();
  renderParam();
  if (push) {
    api('/api/mode', { mode }).then((res) => {
      if (!res.ok) toast(res.error || '切换模式失败', 'err');
    });
    api('/api/prefs', { mode, ['param_' + mode]: $('param-input').value.trim() });
  }
}

function updateStatus(snap) {
  const pill = $('status-pill');
  const text = $('status-text');
  pill.classList.remove('is-busy', 'is-run', 'is-err');
  if (snap.running) pill.classList.add('is-run');
  else if (snap.busy) pill.classList.add('is-busy');
  text.textContent = snap.stage_text || '待命';

  document.querySelectorAll('.seg-item').forEach((btn) => { btn.disabled = snap.busy; });
  $('login-btn').disabled = snap.busy || S.loggingIn;
  $('login-btn').textContent = S.loggingIn ? '登录中…' : '登录';
  $('refresh-btn').disabled = snap.busy || !snap.has_task;
  $('start-btn').disabled = snap.busy || !snap.has_task || !snap.units.length;
  $('stop-btn').classList.toggle('hidden', !snap.busy);
  $('logout-btn').disabled = snap.busy;
}

/* ------------------------------------------------------------------ 账号 */
function renderAccount(snap) {
  const logged = !!snap.has_task;
  $('login-form').classList.toggle('hidden', logged);
  $('account-info').classList.toggle('hidden', !logged);
  $('account-hint').textContent = logged ? '已登录' : (snap.busy ? (snap.stage_text || '') : '未登录');
  if (logged) {
    const name = snap.username || '—';
    $('account-name').textContent = name;
    $('account-sub').textContent = snap.mode === 'time' ? '刷学习时长' : '刷完成度 / 正确率';
    $('avatar').textContent = (name[0] || 'W').toUpperCase();
    if (S.selectedCid === null && snap.active_cid !== null && snap.active_cid !== undefined) {
      S.selectedCid = snap.active_cid;
    }
  }
  $('welcome').classList.toggle('hidden', logged);
  $('workspace').classList.toggle('hidden', !logged);
}

function renderCourses(snap) {
  const box = $('course-list');
  const sig = JSON.stringify(snap.courses.map((c) => [c.cid, c.per, c.name])) +
              '|' + S.selectedCid;
  if (S.lastSig.courses === sig) return;
  S.lastSig.courses = sig;

  if (!snap.courses.length) {
    box.innerHTML = '<p class="empty">' +
      (snap.has_task ? '没有课程数据' : '登录后显示课程') + '</p>';
    return;
  }
  box.innerHTML = '';
  snap.courses.forEach((course, i) => {
    const row = document.createElement('div');
    row.className = 'row' + (String(course.cid) === String(S.selectedCid) ? ' is-active' : '');
    const per = Number(course.per) || 0;
    row.innerHTML = `
      <span class="idx">${i + 1}</span>
      <div class="row-main">
        <span class="row-title" title="${escapeHtml(course.name)}">${escapeHtml(course.name)}</span>
        <div class="bar"><i style="width:${Math.min(100, per)}%"></i></div>
      </div>
      <span class="badge ${per >= 100 ? 'ok' : ''}">${per}%</span>`;
    row.onclick = () => selectCourse(course.cid);
    box.appendChild(row);
  });
}

function renderUnits(snap) {
  const box = $('unit-list');
  const sig = JSON.stringify(snap.units.map((u) => [u.no, u.name, u.visible])) +
              '|' + S.selectedUnit + '|' + !!snap.units.length;
  if (S.lastSig.units === sig) return;
  S.lastSig.units = sig;

  if (!snap.units.length) {
    box.innerHTML = '<p class="empty">选择课程后显示单元</p>';
    $('unit-hint').textContent = '';
    return;
  }
  $('unit-hint').textContent = `共 ${snap.units.length} 个`;
  box.innerHTML = '';

  const allRow = document.createElement('div');
  allRow.className = 'row' + (S.selectedUnit === 0 ? ' is-active' : '');
  allRow.innerHTML = `<span class="idx">0</span>
    <div class="row-main"><span class="row-title">全部单元</span>
    <span class="row-sub">按顺序处理所有单元(遇到不可用单元停止)</span></div>`;
  allRow.onclick = () => selectUnit(0);
  box.appendChild(allRow);

  snap.units.forEach((unit) => {
    const row = document.createElement('div');
    row.className = 'row' + (S.selectedUnit === unit.no ? ' is-active' : '') +
                    (unit.visible ? '' : ' is-muted');
    row.innerHTML = `<span class="idx">${unit.no}</span>
      <div class="row-main">
        <span class="row-title">${escapeHtml(unit.name || unit.unitname || '单元 ' + unit.no)}</span>
        <span class="row-sub">${escapeHtml(unit.unitname || '')}</span>
      </div>
      <span class="badge ${unit.visible ? 'ok' : 'warn'}">${unit.visible ? '已开放' : '未开放'}</span>`;
    row.onclick = () => selectUnit(unit.no);
    box.appendChild(row);
  });
}

function renderSections(snap) {
  const box = $('section-list');
  const unit = S.selectedUnit;
  const wrap = $('select-all-wrap');
  document.querySelector('.section-card').classList.toggle('is-idle', !unit);

  if (!unit) {
    box.innerHTML = '<p class="empty">选择具体单元后可勾选小节(选「全部单元」时按整单元处理)</p>';
    $('section-hint').textContent = '';
    wrap.classList.add('hidden');
    return;
  }

  const items = snap.sections[String(unit)];
  if (!items) {
    const loading = snap.stage === 'sections';
    box.innerHTML = `<p class="empty">${loading ? '正在加载小节…' : '尚未加载该单元的小节'}</p>`;
    $('section-hint').textContent = loading ? '' : '切换单元后自动加载';
    wrap.classList.add('hidden');
    if (!loading && !snap.busy) api('/api/sections', { unit });
    return;
  }

  wrap.classList.remove('hidden');
  const checked = getChecked(unit);
  const sig = unit + '|' + items.map((x) => x.location + x.complete + x.visible).join() +
              '|' + [...checked].join(',');
  if (S.lastSig.sections === sig) return;
  S.lastSig.sections = sig;

  box.innerHTML = '';
  items.forEach((item, i) => {
    const no = i + 1;
    const row = document.createElement('label');
    row.className = 'row' + (item.visible ? '' : ' is-muted');
    row.innerHTML = `
      <input type="checkbox" class="sec-check" ${checked.has(no) ? 'checked' : ''}>
      <span class="idx">${no}</span>
      <div class="row-main">
        <span class="row-title">${escapeHtml(item.location || '小节 ' + no)}</span>
      </div>
      <span class="badge ${item.complete ? 'ok' : 'warn'}">${item.complete ? '已完成' : '未完成'}</span>
      ${item.visible ? '' : '<span class="badge">未开放</span>'}`;
    row.querySelector('input').onchange = (ev) => {
      const set = getChecked(unit);
      if (ev.target.checked) set.add(no); else set.delete(no);
      S.lastSig.sections = '';
      updateSectionHint(unit, items);
    };
    box.appendChild(row);
  });
  updateSectionHint(unit, items);
}

function updateSectionHint(unit, items) {
  const checked = getChecked(unit).size;
  $('section-hint').textContent = checked ? `已选 ${checked} / ${items.length} 个小节` : `共 ${items.length} 个,未勾选则整单元`;
  const all = $('select-all');
  all.checked = checked === items.length && items.length > 0;
  all.indeterminate = checked > 0 && checked < items.length;
  all.onchange = () => {
    const set = getChecked(unit);
    set.clear();
    if (all.checked) items.forEach((_, i) => set.add(i + 1));
    S.lastSig.sections = '';
    renderSections(S.snap);
  };
}

function getChecked(unit) {
  if (!S.checkedByUnit[unit]) S.checkedByUnit[unit] = new Set();
  return S.checkedByUnit[unit];
}

/* ------------------------------------------------------------------ 参数 */
function renderParam() {
  const box = $('presets');
  box.innerHTML = '';
  PRESETS[S.mode].forEach((value) => {
    const btn = document.createElement('button');
    btn.className = 'preset';
    btn.textContent = value;
    btn.onclick = () => {
      $('param-input').value = value;
      persistParam();
    };
    box.appendChild(btn);
  });
  $('param-hint').textContent = S.mode === 'time' ? '单位:秒' : '单位:%';
  $('param-help').innerHTML = HELP[S.mode];
  $('param-input').placeholder = S.mode === 'time' ? '30' : '100';
}

function persistParam() {
  const value = $('param-input').value.trim();
  api('/api/prefs', { ['param_' + S.mode]: value });
}

/* ------------------------------------------------------------------ 日志 */
function appendLogs(entries) {
  if (!entries.length) return;
  const body = $('log-body');
  const empty = $('log-empty');
  if (empty) empty.remove();

  const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 60;
  const frag = document.createDocumentFragment();
  entries.forEach(([, ts, text]) => {
    const line = document.createElement('div');
    line.className = 'log-line ' + classify(text);
    const t = document.createElement('span');
    t.className = 'ts';
    t.textContent = ts;
    const m = document.createElement('span');
    m.className = 'msg';
    m.textContent = text;
    line.append(t, m);
    frag.appendChild(line);
  });
  body.appendChild(frag);
  while (body.childElementCount > 3000) body.removeChild(body.firstElementChild);
  if (nearBottom) body.scrollTop = body.scrollHeight;
}

/* ------------------------------------------------------------------ 轮询 */
async function poll() {
  const snap = await api('/api/state?after=' + S.seq);
  if (!snap || snap.ok === false) { setTimeout(poll, 1200); return; }
  S.snap = snap;
  if (snap.logs && snap.logs.length) S.seq = snap.logs[snap.logs.length - 1][0];
  if (S.loggingIn && (snap.has_task || !snap.busy)) S.loggingIn = false;

  if (snap.notice && snap.notice.seq !== S.noticeSeq) {
    S.noticeSeq = snap.notice.seq;
    toast(snap.notice.text, snap.notice.level === 'error' ? 'err' : 'ok');
  }

  updateStatus(snap);
  renderAccount(snap);
  renderCourses(snap);
  renderUnits(snap);
  renderSections(snap);
  appendLogs(snap.logs || []);
  setTimeout(poll, snap.busy ? 600 : 1100);
}

/* ------------------------------------------------------------------ 动作 */
async function selectCourse(cid) {
  if (S.snap && S.snap.busy) return;
  S.selectedCid = cid;
  S.selectedUnit = 0;
  S.checkedByUnit = {};
  S.lastSig.units = '';
  S.lastSig.sections = '';
  const res = await api('/api/course', { cid });
  if (!res.ok) toast(res.error || '加载单元失败', 'err');
  api('/api/prefs', { last_cid: cid });
}

function selectUnit(unit) {
  if (S.snap && S.snap.busy) return;
  S.selectedUnit = unit;
  S.lastSig.units = '';
  S.lastSig.sections = '';
  renderUnits(S.snap);
  renderSections(S.snap);
}

async function startTask() {
  if (!S.snap || S.snap.busy || !S.snap.has_task) return;
  const param = $('param-input').value.trim();
  if (!param) { toast('请先填写任务参数', 'err'); $('param-input').focus(); return; }

  let sections = null;
  if (S.selectedUnit > 0) {
    const set = getChecked(S.selectedUnit);
    if (set.size) sections = { [S.selectedUnit]: [...set] };
  } else if (Object.values(S.checkedByUnit).some((s) => s.size)) {
    toast('选择「全部单元」时不支持按小节过滤', 'err');
    return;
  }

  const res = await api('/api/start', {
    units: S.selectedUnit,
    sections,
    param,
  });
  if (!res.ok) toast(res.error || '启动失败', 'err');
  else persistParam();
}

async function login() {
  const username = $('username').value.trim();
  const password = $('password').value;
  if (!username || !password) { toast('请输入账号和密码', 'err'); return; }
  $('login-btn').disabled = true;
  S.loggingIn = true;
  const res = await api('/api/login', {
    username, password, mode: S.mode, remember: $('remember').checked,
  });
  S.loggingIn = false;
  if (!res.ok) {
    $('login-btn').disabled = false;
    $('login-btn').textContent = '登录';
    toast(res.error || '登录失败', 'err');
  }
}

/* ------------------------------------------------------------------ 初始化 */
function applyTheme() {
  const theme = new URLSearchParams(location.search).get('theme');
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
}

function escapeHtml(str) {
  return String(str == null ? '' : str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

async function boot() {
  applyTheme();
  const info = await api('/api/boot');
  if (info && info.ok) {
    $('version').textContent = 'v' + info.version;
    $('help-credit').innerHTML =
      `协议来自 <code>Welearn_helper</code>(原作者 ${escapeHtml(info.author)},` +
      `维护者 YZBRH / lxbsdsg)。本应用为其 macOS 重写版,遵循 GPLv3,免费开源,禁止售卖。`;
    const prefs = info.prefs || {};
    S.mode = prefs.mode === 'time' ? 'time' : 'accuracy';
    $('username').value = prefs.username || '';
    $('password').value = info.password || '';
    $('remember').checked = !!prefs.remember_password;
    $('param-input').value = prefs['param_' + S.mode] || PRESETS[S.mode][0];
    if (prefs.last_cid) S.selectedCid = prefs.last_cid;
    // 开发预览可直接带 ?unit=N 预选单元(正常使用不会触发)
    const preUnit = parseInt(new URLSearchParams(location.search).get('unit') || '0', 10);
    if (preUnit > 0) S.selectedUnit = preUnit;
    document.querySelectorAll('.seg-item').forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.mode === S.mode);
    });
  }

  moveThumb();
  renderParam();

  document.querySelectorAll('.seg-item').forEach((btn) => {
    btn.onclick = () => setMode(btn.dataset.mode);
  });
  $('login-form').onsubmit = (ev) => { ev.preventDefault(); login(); };
  $('logout-btn').onclick = async () => {
    const res = await api('/api/logout', {});
    if (!res.ok) toast(res.error || '退出失败', 'err');
    S.selectedCid = null; S.selectedUnit = 0; S.checkedByUnit = {};
    S.lastSig = {};
  };
  $('refresh-btn').onclick = async () => {
    const res = await api('/api/refresh', {});
    if (!res.ok) toast(res.error || '刷新失败', 'err');
  };
  $('start-btn').onclick = startTask;
  $('stop-btn').onclick = async () => {
    const res = await api('/api/stop', {});
    if (!res.ok) toast(res.error || '停止失败', 'err');
  };
  $('clear-btn').onclick = () => {
    $('log-body').innerHTML = '<p class="log-empty" id="log-empty">暂无日志</p>';
  };
  $('export-btn').onclick = async () => {
    const res = await api('/api/export-log', {});
    if (res.ok) toast('已导出到 ' + res.path, 'ok');
    else toast(res.error || '导出失败', 'err');
  };
  $('help-btn').onclick = () => $('help-modal').classList.remove('hidden');
  $('help-close').onclick = () => $('help-modal').classList.add('hidden');
  $('help-modal').onclick = (ev) => {
    if (ev.target === $('help-modal')) $('help-modal').classList.add('hidden');
  };
  $('param-input').addEventListener('blur', persistParam);
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') $('help-modal').classList.add('hidden');
    if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') { ev.preventDefault(); startTask(); }
  });
  window.addEventListener('resize', moveThumb);

  poll();
}

boot();
