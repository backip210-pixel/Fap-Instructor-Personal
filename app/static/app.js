const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const appEl = $('#app');

const state = {
  config: null,
  user: null,
  route: '',
  builderEvents: null,
  builderLoadedFor: null,
  player: null,
  ws: null,
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function fmtSeconds(seconds) {
  seconds = Math.max(0, Math.round(Number(seconds || 0)));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function tagsHtml(tags = []) {
  return `<div class="pills">${(tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>`;
}

function notify(message, type = 'ok') {
  const box = document.createElement('div');
  box.className = `toast ${type}`;
  box.textContent = message;
  $('#toast').appendChild(box);
  setTimeout(() => box.remove(), 4300);
}

async function api(path, options = {}) {
  const opts = { method: options.method || (options.body || options.form ? 'POST' : 'GET'), credentials: 'include', headers: options.headers || {} };
  if (options.form) {
    opts.body = options.form;
  } else if (options.body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, opts);
  const ct = res.headers.get('content-type') || '';
  let data = null;
  if (ct.includes('json')) data = await res.json();
  else data = await res.text();
  if (!res.ok) {
    const msg = typeof data === 'object' ? (data.detail || data.message || JSON.stringify(data)) : data;
    if (res.status === 401) {
      state.user = null;
      if (!location.hash.startsWith('#login')) render();
    }
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

function currentPath() {
  return (location.hash.replace(/^#\/?/, '') || 'home').split('?')[0];
}
function nav(path) { location.hash = `#${path}`; }

async function init() {
  state.config = await api('/api/config').catch(() => ({ appName: 'Fap Instructor Docker', eventCatalog: [] }));
  try {
    const me = await api('/api/auth/me');
    state.user = me.user;
  } catch { state.user = null; }
  window.addEventListener('hashchange', render);
  render();
}

function landing() {
  appEl.innerHTML = `
    <div class="landing">
      <section class="hero">
        <div class="logo-mark"><img src="/static/logo.svg" alt="FI logo"></div>
        <h1>${escapeHtml(state.config?.appName || 'Fap Instructor')}</h1>
        <p>A Dockerized, personal-use recreation with local accounts, script library, script builder, game generator, player, metronome, media, WebSocket challenger rooms, and hardware integration hooks.</p>
        <div class="grid auto" style="margin-top:1.5rem">
          ${['Private local accounts', 'Script builder/player', 'Game generators', 'Media library', 'The Handy / Lovense / Autoblow hooks', 'SQLite persistence', 'No payments or subscriptions', 'Admin dashboard'].map(x => `<div class="card"><strong>${escapeHtml(x)}</strong><p class="muted small">Included in this local build.</p></div>`).join('')}
        </div>
      </section>
      <section class="auth-card">
        <h2>Sign in</h2>
        <p class="muted small">Seed admin: <code>admin@example.com</code> / <code>admin123!</code> unless changed in <code>.env</code>.</p>
        <form id="login-form">
          <div class="field"><label>Email</label><input name="email" type="email" value="admin@example.com" required></div>
          <div class="field"><label>Password</label><input name="password" type="password" value="admin123!" required></div>
          <button class="btn primary block">Sign in</button>
        </form>
        <hr>
        <h3>Create account</h3>
        <form id="register-form">
          <div class="field"><label>Email</label><input name="email" type="email" required></div>
          <div class="field"><label>Username</label><input name="username" required></div>
          <div class="field"><label>Password</label><input name="password" type="password" minlength="8" required></div>
          <button class="btn block" ${state.config?.allowRegistration ? '' : 'disabled'}>Register</button>
        </form>
        <p class="muted tiny">By continuing, you accept the local adult-only terms and privacy notices.</p>
      </section>
    </div>`;
  $('#login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const form = Object.fromEntries(new FormData(e.target));
    try { const data = await api('/api/auth/login', { body: form }); state.user = data.user; notify('Signed in'); nav('home'); } catch (err) { notify(err.message, 'error'); }
  });
  $('#register-form').addEventListener('submit', async e => {
    e.preventDefault();
    const form = Object.fromEntries(new FormData(e.target));
    try { const data = await api('/api/auth/register', { body: form }); state.user = data.user; notify('Registered'); nav('home'); } catch (err) { notify(err.message, 'error'); }
  });
}

const navItems = [
  ['home', '⌂', 'Home'],
  ['scripts', '◧', 'Explore Scripts'],
  ['builder/new', '✎', 'Script Builder'],
  ['generators', '⚙', 'Game Generators'],
  ['games', '▶', 'Your Games'],
  ['challenger', '◉', 'Challenger'],
  ['media', '▣', 'Media'],
  ['devices', '⌁', 'Devices'],
  ['settings', '☼', 'Settings'],
];

function shell(title, subtitle, body) {
  const path = currentPath();
  const items = [...navItems];
  if (state.user?.role === 'admin') items.push(['admin', '◆', 'Admin']);
  appEl.innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand"><div class="logo-mark"><img src="/static/logo.svg" alt="FI logo"></div><div><strong>${escapeHtml(state.config?.appName || 'Fap Instructor')}</strong><div class="muted tiny">Self-hosted Docker</div></div></div>
        <nav class="nav">
          ${items.map(([href, icon, label]) => `<a href="#${href}" class="${path === href || path.startsWith(href + '/') ? 'active' : ''}"><span>${icon}</span> ${escapeHtml(label)}</a>`).join('')}
        </nav>
        <hr>
        <div class="card">
          <strong>${escapeHtml(state.user?.username || '')}</strong>
          <div class="muted tiny">${escapeHtml(state.user?.email || '')}</div>
          <div class="row" style="margin-top:.65rem"><span class="badge">${escapeHtml(state.user?.role)}</span><span class="badge">personal</span></div>
          <button class="btn small-btn block" id="logout" style="margin-top:.8rem">Sign out</button>
        </div>
      </aside>
      <main class="main">
        <div class="topbar"><div class="page-title"><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle || '')}</p></div><div class="row"><a class="btn small-btn" href="#builder/new">New script</a><a class="btn primary small-btn" href="#generators">Generate game</a></div></div>
        <div id="page">${body}</div>
      </main>
    </div>`;
  $('#logout')?.addEventListener('click', async () => { await api('/api/auth/logout', { method: 'POST', body: {} }).catch(()=>{}); state.user = null; notify('Signed out'); location.hash = ''; render(); });
}

async function render() {
  if (state.player) { state.player.destroy?.(); state.player = null; }
  if (!state.user) return landing();
  const path = currentPath();
  try {
    if (path === 'home') return await pageHome();
    if (path === 'scripts') return await pageScripts();
    if (path.startsWith('script/')) return await pageScript(Number(path.split('/')[1]));
    if (path.startsWith('builder/')) return await pageBuilder(path.split('/')[1]);
    if (path === 'generators') return await pageGenerators();
    if (path === 'games') return await pageGames();
    if (path.startsWith('game/')) return await pageGame(Number(path.split('/')[1]));
    if (path === 'challenger' || path.startsWith('challenger/')) return await pageChallenger(path.split('/')[1]);
    if (path === 'media') return await pageMedia();
    if (path === 'devices') return await pageDevices();
    if (path === 'settings') return await pageSettings();
    if (path === 'admin') return await pageAdmin();
    if (path.startsWith('legal/')) return await pageLegal(path.split('/')[1]);
    nav('home');
  } catch (err) {
    shell('Error', 'Something went wrong', `<div class="card"><h2 class="danger">${escapeHtml(err.message)}</h2><button class="btn" onclick="history.back()">Back</button></div>`);
  }
}

async function pageHome() {
  const [scripts, gens, stats] = await Promise.all([
    api('/api/scripts?limit=6'),
    api('/api/game-generators?limit=4'),
    api('/api/challenger/stats').catch(() => ({ activeRooms: 0, generatedGames: 0, totalRooms: 0, livePlayers: 0 })),
  ]);
  shell('Home', 'Dashboard and quick start', `
    <section class="stats">
      <div class="stat"><span class="muted small">Scripts</span><strong>${scripts.items.length}+</strong></div>
      <div class="stat"><span class="muted small">Generators</span><strong>${gens.items.length}+</strong></div>
      <div class="stat"><span class="muted small">Rooms</span><strong>${stats.activeRooms}</strong></div>
      <div class="stat"><span class="muted small">Generated games</span><strong>${stats.generatedGames}</strong></div>
    </section>
    <div class="grid two" style="margin-top:1rem">
      <div class="panel card">
        <h2>Quick play</h2>
        <p class="muted">Launch the seeded demo, export a FunScript, or wire the player to mock/hardware devices.</p>
        <div class="grid">${scripts.items.slice(0,3).map(scriptCard).join('')}</div>
      </div>
      <div class="panel card">
        <h2>Quick generate</h2>
        <p class="muted">Start a local game from a generator. Runs are stored under Your Games.</p>
        <div class="grid">${gens.items.map(generatorCard).join('')}</div>
      </div>
    </div>`);
  attachCardActions();
}

function scriptCard(s) {
  return `<article class="card">
    <div class="row between"><h3>${escapeHtml(s.title)}</h3><span class="badge">${fmtSeconds(s.durationSeconds)}</span></div>
    <p class="muted small">${escapeHtml(s.description || '')}</p>
    ${tagsHtml(s.tags)}
    <div class="row" style="margin-top:.8rem">
      <a class="btn primary small-btn" href="#script/${s.id}">Play</a>
      <a class="btn small-btn" href="#builder/${s.id}">Edit</a>
      <button class="btn small-btn vote" data-id="${s.id}" data-vote="1">▲ ${s.votes ?? 0}</button>
    </div>
  </article>`;
}
function generatorCard(g) {
  return `<article class="card">
    <div class="row between"><h3>${escapeHtml(g.name)}</h3><span class="badge">runs ${g.runs || 0}</span></div>
    <p class="muted small">${escapeHtml(g.description || '')}</p>${tagsHtml(g.tags)}
    <div class="row" style="margin-top:.8rem"><button class="btn primary small-btn start-gen" data-id="${g.id}">Start</button><button class="btn small-btn edit-gen" data-id="${g.id}">Edit JSON</button></div>
  </article>`;
}
function attachCardActions() {
  $$('.vote').forEach(b => b.addEventListener('click', async () => { try { const d = await api(`/api/scripts/${b.dataset.id}/vote`, { body: { vote: Number(b.dataset.vote) } }); b.textContent = `▲ ${d.votes}`; } catch (e) { notify(e.message, 'error'); } }));
  $$('.start-gen').forEach(b => b.addEventListener('click', async () => { try { const d = await api(`/api/game-generators/${b.dataset.id}/start`, { body: {} }); notify('Game generated'); nav(`game/${d.item.id}`); } catch (e) { notify(e.message, 'error'); } }));
}

async function pageScripts() {
  shell('Explore Scripts', 'Search, vote, play, and edit scripts', `
    <div class="panel card">
      <div class="row"><input id="script-search" placeholder="Search title, description, tags"><input id="script-tag" placeholder="Tag"><button class="btn primary" id="script-go">Search</button><a class="btn" href="#builder/new">Create</a></div>
    </div>
    <div id="script-results" class="grid auto" style="margin-top:1rem"></div>`);
  async function load() {
    const q = encodeURIComponent($('#script-search').value);
    const tag = encodeURIComponent($('#script-tag').value);
    const data = await api(`/api/scripts?search=${q}&tag=${tag}`);
    $('#script-results').innerHTML = data.items.map(scriptCard).join('') || '<div class="card">No scripts found.</div>';
    attachCardActions();
  }
  $('#script-go').addEventListener('click', load);
  $('#script-search').addEventListener('keydown', e => { if (e.key === 'Enter') load(); });
  await load();
}

async function pageScript(id) {
  const { item } = await api(`/api/scripts/${id}`);
  shell(item.title, item.description, `
    <div class="grid two">
      <section class="card">
        <div class="row between"><h2>${escapeHtml(item.title)}</h2><span class="badge">${fmtSeconds(item.durationSeconds)}</span></div>
        <p class="muted">${escapeHtml(item.description)}</p>
        ${tagsHtml(item.tags)}
        <div class="row" style="margin-top:1rem">
          <a class="btn" href="#builder/${item.id}">Edit</a>
          <a class="btn" href="/api/scripts/${item.id}/export/funscript" target="_blank">Export FunScript</a>
          <button class="btn" id="dialog-create">Create dialogue</button>
          <button class="btn" id="copy-json">Copy JSON</button>
        </div>
        <div id="dialog-output" style="margin-top:1rem"></div>
      </section>
      <section class="card">
        <h3>Events</h3>
        <p class="muted small">${item.events.length} events. Event JSON is portable and can be imported in the builder.</p>
        <pre>${escapeHtml(JSON.stringify(item.events.slice(0, 8), null, 2))}${item.events.length > 8 ? '\n…' : ''}</pre>
      </section>
    </div>
    <div id="player-mount" style="margin-top:1rem"></div>`);
  $('#copy-json').addEventListener('click', async () => { await navigator.clipboard.writeText(JSON.stringify(item, null, 2)); notify('Script JSON copied'); });
  $('#dialog-create').addEventListener('click', async () => {
    try {
      const d = await api('/api/dialog', { body: { scriptId: item.id, style: 'balanced' } });
      $('#dialog-output').innerHTML = `<div class="card"><strong>${escapeHtml(d.item.title)}</strong><pre>${escapeHtml(d.item.text)}</pre></div>`;
    } catch (e) { notify(e.message, 'error'); }
  });
  state.player = createPlayer($('#player-mount'), item, 'script');
}

function defaultScript() {
  const catalog = state.config?.eventCatalog || [];
  const byType = t => structuredClone(catalog.find(e => e.type === t)?.defaults || { type: t });
  return [
    { type: 'chat-message', ...(byType('chat-message')), text: 'Welcome. Confirm consent and follow the timer.', speech: 'Welcome. Confirm consent and follow the timer.' },
    { type: 'metronome', tempo: 60, measure: '4/4' },
    { type: 'stroke', tempo: 60, duration: 20, grip: 'normal', style: 'full' },
    { type: 'wait', duration: 8 },
    { type: 'game-over', message: 'Complete' },
  ];
}

async function pageBuilder(idOrNew) {
  let item = null;
  if (idOrNew !== 'new') item = (await api(`/api/scripts/${Number(idOrNew)}`)).item;
  if (state.builderLoadedFor !== idOrNew) {
    state.builderEvents = item ? structuredClone(item.events) : defaultScript();
    state.builderLoadedFor = idOrNew;
  }
  const instructors = (await api('/api/instructors')).items;
  shell(item ? `Edit: ${item.title}` : 'Script Builder', 'Create, import/export, validate, and save event scripts', `
    <form id="script-form" class="panel card">
      <div class="grid two">
        <div class="field"><label>Title</label><input name="title" value="${escapeHtml(item?.title || 'Untitled script')}" required></div>
        <div class="field"><label>Instructor</label><select name="instructorId"><option value="">None</option>${instructors.map(i => `<option value="${i.id}" ${item?.instructor_id === i.id ? 'selected' : ''}>${escapeHtml(i.name)}</option>`).join('')}</select></div>
      </div>
      <div class="field"><label>Description</label><textarea name="description">${escapeHtml(item?.description || '')}</textarea></div>
      <div class="grid three">
        <div class="field"><label>Tags (comma separated)</label><input name="tags" value="${escapeHtml((item?.tags || ['draft']).join(', '))}"></div>
        <div class="field"><label>Visibility</label><select name="visibility"><option ${item?.visibility === 'private' ? 'selected' : ''}>private</option><option ${item?.visibility === 'public' ? 'selected' : ''}>public</option></select></div>
        <div class="field"><label>Difficulty</label><select name="difficulty"><option>easy</option><option selected>normal</option><option>advanced</option></select></div>
      </div>
    </form>
    <div class="grid two" style="margin-top:1rem">
      <section class="panel card">
        <div class="row between"><h2>Event library</h2><button class="btn small-btn" id="validate-events">Validate</button></div>
        <div class="grid auto">${(state.config?.eventCatalog || []).map(e => `<button class="btn add-event" data-type="${e.type}">${escapeHtml(e.label || e.type)}</button>`).join('')}</div>
      </section>
      <section class="panel card">
        <h2>Import / Export</h2>
        <div class="row"><button class="btn" id="export-events">Copy events JSON</button><button class="btn" id="import-events">Import events JSON</button><button class="btn danger-bg" id="reset-events">Reset template</button></div>
        <div class="field"><label>Bulk JSON editor</label><textarea id="bulk-json" style="min-height:180px">${escapeHtml(JSON.stringify(state.builderEvents, null, 2))}</textarea></div>
        <button class="btn" id="apply-bulk">Apply bulk JSON</button>
      </section>
    </div>
    <section class="panel card" style="margin-top:1rem">
      <div class="row between"><h2>Events <span class="badge">${state.builderEvents.length}</span></h2><div class="muted small">Drag/drop is intentionally omitted; use ↑ ↓ buttons.</div></div>
      <div id="events-list" class="grid"></div>
      <div class="toolbar row between"><span class="muted">Duration estimate: <strong id="duration-est">0:00</strong></span><div class="row"><button class="btn" id="preview-player">Preview</button><button class="btn primary" id="save-script">Save script</button></div></div>
    </section>
    <div id="preview-mount" style="margin-top:1rem"></div>`);
  renderEventRows();
  $$('.add-event').forEach(btn => btn.addEventListener('click', () => { addBuilderEvent(btn.dataset.type); }));
  $('#validate-events').addEventListener('click', validateBuilderEvents);
  $('#export-events').addEventListener('click', async () => { await navigator.clipboard.writeText(JSON.stringify(readBuilderEvents(), null, 2)); notify('Events copied'); });
  $('#import-events').addEventListener('click', async () => { const text = prompt('Paste events JSON array'); if (!text) return; try { state.builderEvents = JSON.parse(text); renderEventRows(); notify('Imported'); } catch (e) { notify('Invalid JSON', 'error'); } });
  $('#reset-events').addEventListener('click', () => { if (confirm('Reset events to template?')) { state.builderEvents = defaultScript(); renderEventRows(); } });
  $('#apply-bulk').addEventListener('click', () => { try { state.builderEvents = JSON.parse($('#bulk-json').value); renderEventRows(); notify('Bulk JSON applied'); } catch (e) { notify(e.message, 'error'); } });
  $('#preview-player').addEventListener('click', () => { const draft = collectScriptForm(); draft.id = item?.id || 'draft'; draft.events = readBuilderEvents(); if (state.player) state.player.destroy?.(); state.player = createPlayer($('#preview-mount'), draft, 'draft'); $('#preview-mount').scrollIntoView({ behavior: 'smooth' }); });
  $('#save-script').addEventListener('click', async () => {
    try {
      const payload = collectScriptForm(); payload.events = readBuilderEvents();
      const data = item ? await api(`/api/scripts/${item.id}`, { method: 'PUT', body: payload }) : await api('/api/scripts', { body: payload });
      state.builderLoadedFor = null;
      notify('Script saved');
      nav(`script/${data.item.id}`);
    } catch (e) { notify(e.message, 'error'); }
  });
}

function collectScriptForm() {
  const fd = new FormData($('#script-form'));
  const obj = Object.fromEntries(fd);
  obj.instructorId = obj.instructorId ? Number(obj.instructorId) : null;
  obj.tags = String(obj.tags || '').split(',').map(s => s.trim()).filter(Boolean);
  return obj;
}
function readBuilderEvents() {
  const rows = $$('.event-json');
  if (!rows.length) return state.builderEvents || [];
  return rows.map(t => JSON.parse(t.value));
}
function builderDuration(events) { return events.reduce((sum, ev) => sum + eventDuration(ev), 0); }
function renderEventRows() {
  const list = $('#events-list');
  if (!list) return;
  const events = state.builderEvents || [];
  list.innerHTML = events.map((ev, idx) => `<div class="event-row" data-idx="${idx}">
    <div class="row between"><strong>${idx + 1}. ${escapeHtml(ev.type)}</strong><div class="row"><button class="btn small-btn up">↑</button><button class="btn small-btn down">↓</button><button class="btn small-btn duplicate">Duplicate</button><button class="btn small-btn danger-bg delete">Delete</button></div></div>
    <textarea class="event-json">${escapeHtml(JSON.stringify(ev, null, 2))}</textarea>
  </div>`).join('') || '<p class="muted">No events. Add one from the library.</p>';
  $$('.event-row').forEach(row => {
    const idx = Number(row.dataset.idx);
    $('.event-json', row).addEventListener('change', () => { try { state.builderEvents[idx] = JSON.parse($('.event-json', row).value); syncBulkAndDuration(); } catch { notify(`Event ${idx + 1} JSON invalid`, 'error'); } });
    $('.delete', row).addEventListener('click', () => { state.builderEvents.splice(idx, 1); renderEventRows(); });
    $('.duplicate', row).addEventListener('click', () => { state.builderEvents.splice(idx + 1, 0, structuredClone(state.builderEvents[idx])); renderEventRows(); });
    $('.up', row).addEventListener('click', () => { if (idx > 0) { [state.builderEvents[idx-1], state.builderEvents[idx]] = [state.builderEvents[idx], state.builderEvents[idx-1]]; renderEventRows(); } });
    $('.down', row).addEventListener('click', () => { if (idx < state.builderEvents.length - 1) { [state.builderEvents[idx+1], state.builderEvents[idx]] = [state.builderEvents[idx], state.builderEvents[idx+1]]; renderEventRows(); } });
  });
  syncBulkAndDuration();
}
function syncBulkAndDuration() {
  try { $('#bulk-json').value = JSON.stringify(state.builderEvents, null, 2); } catch {}
  $('#duration-est') && ($('#duration-est').textContent = fmtSeconds(builderDuration(state.builderEvents || [])));
}
function addBuilderEvent(type) {
  const catalogItem = (state.config?.eventCatalog || []).find(e => e.type === type);
  const ev = { type, ...(structuredClone(catalogItem?.defaults || {})) };
  ev.type = type;
  state.builderEvents.push(ev);
  renderEventRows();
}
function validateBuilderEvents() {
  try {
    const events = readBuilderEvents();
    if (!Array.isArray(events)) throw new Error('Events must be an array');
    for (const [i, ev] of events.entries()) if (!ev.type) throw new Error(`Event ${i + 1} missing type`);
    notify(`Validated ${events.length} events (${fmtSeconds(builderDuration(events))})`);
  } catch (e) { notify(e.message, 'error'); }
}

async function pageGenerators() {
  const gens = await api('/api/game-generators');
  shell('Game Generators', 'Create or run procedural game generators', `
    <div class="grid two">
      <section class="panel card">
        <h2>Create generator</h2>
        <form id="gen-form">
          <div class="field"><label>Name</label><input name="name" value="Custom generator" required></div>
          <div class="field"><label>Description</label><textarea name="description">Procedural session generator.</textarea></div>
          <div class="grid two">
            <div class="field"><label>Duration minutes</label><input name="durationMinutes" type="number" value="6" min="1" max="120"></div>
            <div class="field"><label>Intensity</label><select name="intensity"><option>low</option><option selected>medium</option><option>high</option></select></div>
            <div class="field"><label>Min tempo</label><input name="minTempo" type="number" value="45"></div>
            <div class="field"><label>Max tempo</label><input name="maxTempo" type="number" value="120"></div>
            <div class="field"><label>Outcome</label><select name="outcome"><option>deny</option><option>edge</option><option>finish</option></select></div>
            <div class="field"><label>Tags</label><input name="tags" value="custom, generator"></div>
          </div>
          <label class="row"><input name="includeEdges" type="checkbox" style="width:auto" checked> Include edge markers</label>
          <label class="row"><input name="includeInstructions" type="checkbox" style="width:auto" checked> Include interactive check-ins</label>
          <button class="btn primary">Save generator</button>
        </form>
      </section>
      <section class="panel card"><h2>Existing</h2><div class="grid">${gens.items.map(generatorCard).join('') || '<p>No generators.</p>'}</div></section>
    </div>`);
  $('#gen-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const config = {
      durationMinutes: Number(fd.get('durationMinutes')),
      intensity: fd.get('intensity'),
      minTempo: Number(fd.get('minTempo')),
      maxTempo: Number(fd.get('maxTempo')),
      outcome: fd.get('outcome'),
      includeEdges: fd.has('includeEdges'),
      includeInstructions: fd.has('includeInstructions'),
    };
    try { await api('/api/game-generators', { body: { name: fd.get('name'), description: fd.get('description'), tags: String(fd.get('tags')).split(',').map(s=>s.trim()).filter(Boolean), visibility: 'private', config } }); notify('Generator saved'); pageGenerators(); } catch (err) { notify(err.message, 'error'); }
  });
  attachCardActions();
  $$('.edit-gen').forEach(btn => btn.addEventListener('click', async () => {
    const g = (await api(`/api/game-generators/${btn.dataset.id}`)).item;
    const json = prompt('Edit config JSON, then OK to save', JSON.stringify(g.config, null, 2));
    if (!json) return;
    try { await api(`/api/game-generators/${g.id}`, { method: 'PUT', body: { ...g, config: JSON.parse(json) } }); notify('Generator updated'); pageGenerators(); } catch (e) { notify(e.message, 'error'); }
  }));
}

async function pageGames() {
  const games = await api('/api/games?mine=true');
  shell('Your Games', 'Generated sessions saved from generators', `<div class="grid auto">${games.items.map(g => `<article class="card"><div class="row between"><h3>${escapeHtml(g.title)}</h3><span class="badge">${fmtSeconds(g.durationSeconds)}</span></div><p class="muted small">${escapeHtml(g.description)}</p>${tagsHtml(g.tags)}<div class="row" style="margin-top:.8rem"><a class="btn primary small-btn" href="#game/${g.id}">Play</a><button class="btn small-btn danger-bg del-game" data-id="${g.id}">Delete</button></div></article>`).join('') || '<div class="card">No generated games yet.</div>'}</div>`);
  $$('.del-game').forEach(b => b.addEventListener('click', async () => { if (!confirm('Delete game?')) return; await api(`/api/games/${b.dataset.id}`, { method: 'DELETE' }); notify('Deleted'); pageGames(); }));
}

async function pageGame(id) {
  const { item } = await api(`/api/games/${id}`);
  shell(item.title, 'Generated game run', `<div class="card"><div class="row between"><div>${tagsHtml(item.tags)}</div><span class="badge">${fmtSeconds(item.durationSeconds)}</span></div></div><div id="player-mount" style="margin-top:1rem"></div>`);
  state.player = createPlayer($('#player-mount'), item, 'game');
}

async function pageMedia() {
  const data = await api('/api/media');
  shell('Media', 'Add remote URLs or upload local media for scripts', `
    <div class="grid two">
      <section class="panel card">
        <h2>Add URL</h2><form id="media-url-form"><div class="field"><label>Title</label><input name="title" required></div><div class="field"><label>Type</label><select name="mediaType"><option>video</option><option>audio</option><option>image</option><option>embed</option></select></div><div class="field"><label>URL</label><input name="url" required placeholder="https://..."></div><div class="field"><label>Tags</label><input name="tags"></div><button class="btn primary">Add</button></form>
      </section>
      <section class="panel card">
        <h2>Upload</h2><form id="media-upload-form"><div class="field"><label>Title</label><input name="title" required></div><div class="field"><label>Type</label><select name="mediaType"><option>video</option><option>audio</option><option>image</option></select></div><div class="field"><label>File</label><input name="file" type="file" required></div><div class="field"><label>Tags</label><input name="tags"></div><button class="btn">Upload</button></form>
      </section>
    </div>
    <div class="grid auto" style="margin-top:1rem">${data.items.map(m => `<article class="card"><h3>${escapeHtml(m.title)}</h3><div class="media-stage">${mediaEmbed(m.url, m.mediaType)}</div><div class="row between" style="margin-top:.7rem"><span class="badge">${escapeHtml(m.mediaType)}</span><button class="btn small-btn copy-media" data-url="${escapeHtml(m.url)}">Copy URL</button></div>${tagsHtml(m.tags)}</article>`).join('') || '<div class="card">No media yet.</div>'}</div>`);
  $('#media-url-form').addEventListener('submit', async e => { e.preventDefault(); const fd = Object.fromEntries(new FormData(e.target)); fd.tags = String(fd.tags || '').split(',').map(s=>s.trim()).filter(Boolean); try { await api('/api/media', { body: fd }); notify('Media added'); pageMedia(); } catch (err) { notify(err.message, 'error'); } });
  $('#media-upload-form').addEventListener('submit', async e => { e.preventDefault(); const fd = new FormData(e.target); try { await api('/api/media/upload', { form: fd }); notify('Uploaded'); pageMedia(); } catch (err) { notify(err.message, 'error'); } });
  $$('.copy-media').forEach(b => b.addEventListener('click', async () => { await navigator.clipboard.writeText(b.dataset.url); notify('URL copied'); }));
}
function mediaEmbed(url, type) {
  if (!url) return '<span class="muted">No URL configured</span>';
  const u = escapeHtml(url);
  if (type === 'audio') return `<audio controls src="${u}"></audio>`;
  if (type === 'image') return `<img src="${u}" alt="media">`;
  if (type === 'embed') return `<iframe src="${u}" style="width:100%;min-height:220px;border:0;border-radius:14px" allowfullscreen></iframe>`;
  return `<video controls src="${u}"></video>`;
}

async function pageDevices() {
  const data = await api('/api/devices');
  shell('Devices', 'Manage The Handy, Lovense, Autoblow, or mock integrations', `
    <div class="grid two">
      <section class="panel card">
        <h2>Add device</h2>
        <form id="device-form">
          <div class="field"><label>Type</label><select name="deviceType"><option>mock</option><option>handy</option><option>lovense</option><option>autoblow</option></select></div>
          <div class="field"><label>Label</label><input name="label" value="Local mock device"></div>
          <div class="field"><label>Config JSON</label><textarea name="config">{
  "connectionKey": "",
  "uid": "",
  "endpoint": ""
}</textarea></div>
          <button class="btn primary">Save device</button>
        </form>
      </section>
      <section class="panel card"><h2>Integration status</h2><p class="muted">Remote calls are <strong>${state.config?.integrationsRemoteEnabled ? 'enabled' : 'disabled/mock mode'}</strong>. Set <code>ENABLE_REMOTE_INTEGRATIONS=true</code> and provider credentials in <code>.env</code> to use real hardware.</p></section>
    </div>
    <div class="grid auto" style="margin-top:1rem">${data.items.map(d => `<article class="card"><div class="row between"><h3>${escapeHtml(d.label)}</h3><span class="badge">${escapeHtml(d.status)}</span></div><p class="muted small">${escapeHtml(d.deviceType)}</p><pre>${escapeHtml(JSON.stringify(d.config, null, 2))}</pre><div class="row"><button class="btn small-btn test-device" data-id="${d.id}">Test</button><button class="btn small-btn command-device" data-id="${d.id}">Send tempo</button><button class="btn small-btn danger-bg del-device" data-id="${d.id}">Delete</button></div><div id="device-result-${d.id}" class="small" style="margin-top:.6rem"></div></article>`).join('') || '<div class="card">No devices yet.</div>'}</div>`);
  $('#device-form').addEventListener('submit', async e => { e.preventDefault(); const fd = new FormData(e.target); try { await api('/api/devices', { body: { deviceType: fd.get('deviceType'), label: fd.get('label'), config: JSON.parse(fd.get('config')) } }); notify('Device saved'); pageDevices(); } catch (err) { notify(err.message, 'error'); } });
  $$('.test-device').forEach(b => b.addEventListener('click', async () => { try { const r = await api(`/api/devices/${b.dataset.id}/test`, { body: {} }); $(`#device-result-${b.dataset.id}`).innerHTML = `<pre>${escapeHtml(JSON.stringify(r, null, 2))}</pre>`; } catch (e) { notify(e.message, 'error'); } }));
  $$('.command-device').forEach(b => b.addEventListener('click', async () => { try { const tempo = Number(prompt('Tempo / strength value', '70') || 70); const r = await api(`/api/devices/${b.dataset.id}/command`, { body: { command: { action: 'tempo', tempo } } }); $(`#device-result-${b.dataset.id}`).innerHTML = `<pre>${escapeHtml(JSON.stringify(r, null, 2))}</pre>`; } catch (e) { notify(e.message, 'error'); } }));
  $$('.del-device').forEach(b => b.addEventListener('click', async () => { if (!confirm('Delete device?')) return; await api(`/api/devices/${b.dataset.id}`, { method: 'DELETE' }); notify('Deleted'); pageDevices(); }));
}

async function pageSettings() {
  const settings = await api('/api/account/settings');
  shell('Settings', 'Account, playback, devices, and local legal notices', `
    <div class="grid two">
      <section class="panel card"><h2>Profile and playback</h2><form id="settings-form"><div class="field"><label>Username</label><input name="username" value="${escapeHtml(state.user.username)}"></div><label class="row"><input name="tts" type="checkbox" style="width:auto" ${settings.settings.tts !== false ? 'checked' : ''}> Browser text-to-speech</label><label class="row"><input name="metronomeAudio" type="checkbox" style="width:auto" ${settings.settings.metronomeAudio !== false ? 'checked' : ''}> Metronome audio click</label><button class="btn primary" style="margin-top:.8rem">Save</button></form></section>
      <section class="panel card"><h2>Personal-use mode</h2><p class="muted">Payments, subscriptions, and paywalls are not included. All local scripts, generators, media, devices, and challenger rooms are available to your local users.</p><div class="row"><a class="btn" href="#devices">Configure devices</a><a class="btn" href="#builder/new">Create script</a></div></section>
      <section class="panel card"><h2>Legal</h2><div class="row"><a class="btn" href="#legal/terms">Terms</a><a class="btn" href="#legal/privacy">Privacy</a><a class="btn" href="#legal/age-verification">Age verification</a></div></section>
    </div>`);
  $('#settings-form').addEventListener('submit', async e => { e.preventDefault(); const fd = new FormData(e.target); const payload = { username: fd.get('username'), settings: { tts: fd.has('tts'), metronomeAudio: fd.has('metronomeAudio') } }; try { await api('/api/account/settings', { body: payload }); state.user.username = payload.username; notify('Settings saved'); pageSettings(); } catch (err) { notify(err.message, 'error'); } });
}


async function pageAdmin() {
  const [stats, users, live, queue] = await Promise.all([api('/api/admin/stats'), api('/api/admin/users'), api('/api/admin/challenger/live'), api('/api/admin/instruction/generate/status')]);
  shell('Admin', 'Local administration and diagnostics', `
    <section class="stats">${Object.entries(stats.counts).map(([k,v]) => `<div class="stat"><span class="muted small">${escapeHtml(k)}</span><strong>${v}</strong></div>`).join('')}</section>
    <div class="grid two" style="margin-top:1rem">
      <section class="panel card"><h2>Users</h2><div class="grid">${users.items.map(u => `<div class="card"><div class="row between"><strong>${escapeHtml(u.username)}</strong><span class="badge">${escapeHtml(u.role)}</span></div><div class="muted small">${escapeHtml(u.email)}</div><div class="row" style="margin-top:.6rem"><button class="btn small-btn admin-role" data-id="${u.id}">Set role</button></div></div>`).join('')}</div></section>
      <section class="panel card"><h2>Queues / live</h2><pre>${escapeHtml(JSON.stringify({ queue, live }, null, 2))}</pre><h3>Recent audit</h3><pre>${escapeHtml(JSON.stringify(stats.recentAudit.slice(0, 10), null, 2))}</pre></section>
    </div>`);
  $$('.admin-role').forEach(b => b.addEventListener('click', async () => { const role = prompt('role (admin/user)', 'admin'); if (!role) return; await api(`/api/admin/users/${b.dataset.id}`, { method: 'PUT', body: { role } }); notify('Updated'); pageAdmin(); }));
}

async function pageLegal(doc) {
  const d = await api(`/api/legal/${doc}`);
  shell(d.title, 'Local legal notice', `<section class="panel card"><p>${escapeHtml(d.body)}</p><p class="muted small">Replace these placeholder documents with your counsel-approved policies before production deployment.</p></section>`);
}

async function pageChallenger(code) {
  if (!code) {
    const stats = await api('/api/challenger/stats');
    shell('Challenger', 'Create or join a WebSocket multiplayer room', `
      <div class="grid two">
        <section class="panel card"><h2>Create room</h2><form id="room-form"><div class="field"><label>Title</label><input name="title" value="Local challenge room"></div><button class="btn primary">Create</button></form></section>
        <section class="panel card"><h2>Join room</h2><form id="join-form"><div class="field"><label>Room code</label><input name="code" placeholder="ABC123"></div><button class="btn">Join</button></form></section>
      </div><div class="card" style="margin-top:1rem"><pre>${escapeHtml(JSON.stringify(stats, null, 2))}</pre></div>`);
    $('#room-form').addEventListener('submit', async e => { e.preventDefault(); const d = await api('/api/challenger/rooms', { body: Object.fromEntries(new FormData(e.target)) }); nav(`challenger/${d.item.code}`); });
    $('#join-form').addEventListener('submit', e => { e.preventDefault(); nav(`challenger/${new FormData(e.target).get('code').toUpperCase()}`); });
    return;
  }
  const room = await api(`/api/challenger/rooms/${code}`);
  shell(`Room ${code}`, room.item.title, `
    <div class="grid two">
      <section class="panel card"><h2>Room snapshot</h2><pre id="room-snapshot">${escapeHtml(JSON.stringify(room.item.snapshot, null, 2))}</pre><div class="row"><button class="btn primary" id="room-start">Broadcast start</button><button class="btn" id="room-pause">Broadcast pause</button><button class="btn" id="room-event">Broadcast event</button></div></section>
      <section class="panel card"><h2>Chat</h2><div id="room-chat" class="chat-log"></div><div class="row" style="margin-top:.7rem"><input id="room-chat-input" placeholder="Message"><button class="btn" id="room-chat-send">Send</button></div></section>
    </div>`);
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  if (state.ws) state.ws.close();
  const ws = new WebSocket(`${protocol}://${location.host}/ws/challenger/${code}`);
  state.ws = ws;
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'chat') $('#room-chat').insertAdjacentHTML('beforeend', `<div class="chat-msg"><strong>${escapeHtml(msg.message.user)}</strong><br>${escapeHtml(msg.message.text)}</div>`);
    if (msg.room) $('#room-snapshot').textContent = JSON.stringify(msg.room, null, 2);
    if (msg.type === 'event') $('#room-chat').insertAdjacentHTML('beforeend', `<div class="log-msg"><span class="badge">event</span> ${escapeHtml(JSON.stringify(msg.event))}</div>`);
  };
  ws.onopen = () => notify('Room connected');
  ws.onclose = () => notify('Room disconnected', 'error');
  $('#room-chat-send').addEventListener('click', () => { ws.send(JSON.stringify({ type: 'chat', text: $('#room-chat-input').value })); $('#room-chat-input').value = ''; });
  $('#room-start').addEventListener('click', () => ws.send(JSON.stringify({ type: 'state', state: 'playing', position: Date.now() })));
  $('#room-pause').addEventListener('click', () => ws.send(JSON.stringify({ type: 'state', state: 'paused', position: Date.now() })));
  $('#room-event').addEventListener('click', () => ws.send(JSON.stringify({ type: 'event', event: { type: 'manual-cue', text: prompt('Event text', 'Cue') || 'Cue' } })));
}

function eventDuration(ev) {
  if (!ev) return 0;
  if (Number.isFinite(Number(ev.duration))) return Math.max(0, Number(ev.duration));
  if (ev.type === 'metronome-wait') return Math.ceil((60 / Number(ev.tempo || 60)) * Number(ev.count || 4));
  if (['metronome', 'stroke-tempo', 'stroke-grip', 'stroke-style', 'stroke-hand'].includes(ev.type)) return 1;
  if (ev.type === 'chat-message') return Math.max(3, Math.min(20, String(ev.speech || ev.text || '').length / 12));
  if (ev.type === 'instruction') return 8;
  if (ev.type === 'game-over') return 0;
  return 5;
}

function describeEvent(ev) {
  if (!ev) return '';
  if (ev.type === 'stroke') return `${ev.tempo || ''} BPM · ${ev.grip || 'normal'} · ${ev.style || 'full'}`;
  if (ev.type === 'chat-message') return ev.text || ev.speech || '';
  if (ev.type === 'instruction') return ev.description || '';
  if (ev.type === 'wait') return 'Rest / wait';
  if (ev.type === 'orgasm') return `Outcome: ${ev.orgasm?.type || 'unspecified'}`;
  if (ev.type === 'media') return ev.url || 'Media cue';
  if (ev.type === 'device') return JSON.stringify(ev.command || {});
  return JSON.stringify(Object.fromEntries(Object.entries(ev).filter(([k]) => !['id'].includes(k))));
}

function createPlayer(mount, item, kind = 'script') {
  let events = structuredClone(item.events || []);
  let index = -1;
  let running = false;
  let paused = false;
  let remaining = 0;
  let totalDuration = events.reduce((s, e) => s + eventDuration(e), 0);
  let elapsed = 0;
  let tempo = 0;
  let tickTimer = null;
  let metroTimer = null;
  let audioCtx = null;
  let devices = [];
  let currentDeviceId = '';
  mount.innerHTML = `
    <section class="player">
      <div class="player-head">
        <div><strong>${escapeHtml(item.title)}</strong><div class="muted small"><span id="player-count">0/${events.length}</span> · <span id="player-time">0:00 / ${fmtSeconds(totalDuration)}</span></div></div>
        <div class="row"><select id="player-device"><option value="">No device</option></select><label class="row small"><input id="player-auto-device" type="checkbox" style="width:auto"> auto-send</label><button class="btn primary" id="player-start">Start</button><button class="btn" id="player-pause">Pause</button><button class="btn" id="player-next">Next</button><button class="btn danger-bg" id="player-stop">Stop</button></div>
      </div>
      <div style="padding:1rem"><div class="progress"><div id="player-progress"></div></div></div>
      <div class="player-body">
        <div class="event-display">
          <div class="event-type" id="event-type">Ready</div>
          <div class="countdown" id="countdown">${fmtSeconds(totalDuration)}</div>
          <h2 id="event-title">Press Start</h2>
          <p class="muted" id="event-desc">${escapeHtml(item.description || '')}</p>
          <div id="event-options" class="row"></div>
          <div class="metronome" style="margin-top:1rem"><div class="beat-dot" id="beat-dot"></div><div><strong id="tempo-label">No tempo</strong><div class="muted tiny">Visual/audio metronome follows stroke tempo events.</div></div></div>
        </div>
        <aside class="grid">
          <div class="card"><h3>Media</h3><div class="media-stage" id="player-media"><span class="muted">No media cue yet</span></div></div>
          <div class="card"><h3>Messages</h3><div class="chat-log" id="player-chat"></div></div>
          <div class="card"><h3>Device log</h3><div class="device-log" id="player-device-log"></div></div>
        </aside>
      </div>
    </section>`;
  api('/api/devices').then(d => { devices = d.items || []; $('#player-device', mount).innerHTML = '<option value="">No device</option>' + devices.map(dev => `<option value="${dev.id}">${escapeHtml(dev.label)} (${escapeHtml(dev.deviceType)})</option>`).join(''); }).catch(()=>{});
  $('#player-device', mount).addEventListener('change', e => currentDeviceId = e.target.value);
  $('#player-start', mount).addEventListener('click', start);
  $('#player-pause', mount).addEventListener('click', togglePause);
  $('#player-next', mount).addEventListener('click', next);
  $('#player-stop', mount).addEventListener('click', stop);

  function start() {
    if (running && paused) return togglePause();
    if (running) return;
    api(kind === 'game' ? `/api/games/${item.id}/play` : (kind === 'script' ? `/api/scripts/${item.id}/play` : '/api/health'), { method: kind === 'draft' ? 'GET' : 'POST', body: kind === 'draft' ? undefined : {} }).catch(()=>{});
    running = true; paused = false; index = -1; elapsed = 0; $('#player-chat', mount).innerHTML = ''; $('#player-device-log', mount).innerHTML = ''; next();
  }
  function stop() { running = false; paused = false; clearTimers(); stopMetronome(); index = -1; remaining = totalDuration; updateMeta(); $('#event-type', mount).textContent = 'Stopped'; $('#event-title', mount).textContent = 'Stopped'; $('#countdown', mount).textContent = fmtSeconds(totalDuration); }
  function togglePause() { if (!running) return; paused = !paused; $('#player-pause', mount).textContent = paused ? 'Resume' : 'Pause'; if (paused) { clearTimers(); stopMetronome(); } else { if (tempo) startMetronome(tempo); runCountdown(); } }
  function clearTimers() { if (tickTimer) clearInterval(tickTimer); tickTimer = null; }
  function next() {
    if (!running) return;
    clearTimers();
    index++;
    if (index >= events.length) { complete(); return; }
    const ev = events[index];
    applyEvent(ev);
    remaining = eventDuration(ev);
    if (remaining <= 0) { setTimeout(next, 450); return; }
    runCountdown();
  }
  function runCountdown() {
    clearTimers();
    updateMeta();
    tickTimer = setInterval(() => {
      if (paused || !running) return;
      remaining -= 1;
      elapsed += 1;
      updateMeta();
      if (remaining <= 0) next();
    }, 1000);
  }
  function updateMeta() {
    $('#player-count', mount).textContent = `${Math.max(index + 1, 0)}/${events.length}`;
    $('#player-time', mount).textContent = `${fmtSeconds(elapsed)} / ${fmtSeconds(totalDuration)}`;
    $('#countdown', mount).textContent = fmtSeconds(remaining || 0);
    $('#player-progress', mount).style.width = `${Math.min(100, totalDuration ? (elapsed / totalDuration) * 100 : 0)}%`;
  }
  function complete() { clearTimers(); stopMetronome(); running = false; $('#event-type', mount).textContent = 'Complete'; $('#event-title', mount).textContent = 'Session complete'; $('#event-desc', mount).textContent = 'Reset, hydrate, and close any device sessions.'; $('#countdown', mount).textContent = '0:00'; $('#player-progress', mount).style.width = '100%'; }
  function applyEvent(ev) {
    $('#event-type', mount).textContent = ev.type;
    $('#event-title', mount).textContent = ev.title || ev.message || ev.type;
    $('#event-desc', mount).textContent = describeEvent(ev);
    $('#event-options', mount).innerHTML = '';
    if (ev.type === 'metronome' || ev.type === 'stroke' || ev.type === 'stroke-tempo') {
      tempo = Number(ev.tempo || tempo || 60);
      $('#tempo-label', mount).textContent = `${tempo} BPM`;
      startMetronome(tempo);
    }
    if (ev.type === 'wait') { stopMetronome(); }
    if (ev.type === 'chat-message') {
      addChat(ev.text || ev.speech || '');
      speak(ev.speech || ev.text || '');
    }
    if (ev.type === 'instruction') {
      addChat(`${ev.title || 'Instruction'}: ${ev.description || ''}`);
      (ev.options || []).forEach(opt => {
        const btn = document.createElement('button'); btn.className = 'btn small-btn'; btn.textContent = opt.title || 'Option';
        btn.addEventListener('click', () => { if (Array.isArray(opt.events) && opt.events.length) { events.splice(index + 1, 0, ...structuredClone(opt.events)); totalDuration += opt.events.reduce((s,e)=>s+eventDuration(e),0); notify('Option events queued'); } });
        $('#event-options', mount).appendChild(btn);
      });
    }
    if (ev.type === 'media') $('#player-media', mount).innerHTML = mediaEmbed(ev.url, ev.mediaType || 'video');
    if (ev.type === 'game-over') complete();
    maybeSendDevice(ev);
    updateMeta();
  }
  function addChat(text) { if (!text) return; $('#player-chat', mount).insertAdjacentHTML('beforeend', `<div class="chat-msg">${escapeHtml(text)}</div>`); }
  function addDeviceLog(text) { $('#player-device-log', mount).insertAdjacentHTML('beforeend', `<div class="log-msg">${escapeHtml(text)}</div>`); }
  function speak(text) { if (!state.user?.settings?.tts || !('speechSynthesis' in window) || !text) return; speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); speechSynthesis.speak(u); }
  async function maybeSendDevice(ev) {
    if (!$('#player-auto-device', mount).checked || !currentDeviceId) return;
    let command = null;
    if (ev.type === 'stroke' || ev.type === 'stroke-tempo' || ev.type === 'metronome') command = { action: 'tempo', tempo: Number(ev.tempo || tempo || 60), duration: eventDuration(ev) };
    if (ev.type === 'device') command = ev.command || ev;
    if (!command) return;
    try { const r = await api(`/api/devices/${currentDeviceId}/command`, { body: { command } }); addDeviceLog(`${r.status}: ${JSON.stringify(r.response).slice(0, 260)}`); } catch (e) { addDeviceLog(`error: ${e.message}`); }
  }
  function startMetronome(bpm) {
    stopMetronome();
    if (!bpm || bpm <= 0 || paused || !running) return;
    const beatMs = 60000 / bpm;
    pulseBeat();
    metroTimer = setInterval(pulseBeat, beatMs);
  }
  function stopMetronome() { if (metroTimer) clearInterval(metroTimer); metroTimer = null; $('#beat-dot', mount)?.classList.remove('on'); }
  function pulseBeat() {
    const dot = $('#beat-dot', mount); dot.classList.add('on'); setTimeout(() => dot.classList.remove('on'), 90);
    if (state.user?.settings?.metronomeAudio === false) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain();
      osc.frequency.value = 880; gain.gain.value = 0.035; osc.connect(gain); gain.connect(audioCtx.destination); osc.start(); osc.stop(audioCtx.currentTime + 0.035);
    } catch {}
  }
  return { destroy() { clearTimers(); stopMetronome(); window.speechSynthesis?.cancel?.(); } };
}

init();
