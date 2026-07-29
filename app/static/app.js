const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const appEl = $('#app');

const state = { config: null, player: null, builderEvents: null, builderLoadedFor: null, metronome: null };

function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}
function fmtSeconds(seconds) {
  seconds = Math.max(0, Math.round(Number(seconds || 0)));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
function tagsHtml(tags = []) { return `<div class="pills">${(tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>`; }
function notify(message, type = 'ok') { const box = document.createElement('div'); box.className = `toast ${type}`; box.textContent = message; $('#toast').appendChild(box); setTimeout(() => box.remove(), 3600); }

async function api(path, options = {}) {
  const opts = { method: options.method || (options.body || options.form ? 'POST' : 'GET'), headers: options.headers || {} };
  if (options.form) opts.body = options.form;
  else if (options.body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(options.body); }
  const res = await fetch(path, opts);
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error(typeof data === 'object' ? (data.detail || JSON.stringify(data)) : data);
  return data;
}

function currentPath() { return (location.hash.replace(/^#\/?/, '') || 'home').split('?')[0]; }
function nav(path) { location.hash = `#${path}`; }

const navItems = [
  ['home', '⌂', 'Home'],
  ['scripts', '◧', 'Scripts'],
  ['builder/new', '✎', 'Builder'],
  ['media', '▣', 'Images & Videos'],
  ['metronome', '●', 'Metronome'],
  ['generators', '⚙', 'Generator'],
  ['games', '▶', 'Games'],
  ['about', '☼', 'About'],
];

function shell(title, subtitle, body) {
  state.player?.destroy?.(); state.player = null;
  state.metronome?.destroy?.(); state.metronome = null;
  const path = currentPath();
  appEl.innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand"><div class="logo-mark"><img src="/static/logo.svg" alt="FI logo"></div><div><strong>${escapeHtml(state.config?.appName || 'Fap Instructor')}</strong><div class="muted tiny">Simple local Docker app</div></div></div>
        <nav class="nav">${navItems.map(([href, icon, label]) => `<a href="#${href}" class="${path === href || path.startsWith(href + '/') ? 'active' : ''}"><span>${icon}</span> ${escapeHtml(label)}</a>`).join('')}</nav>
        <hr><div class="card small muted">No login, no toy integrations, no subscriptions. Just local scripts, media, and metronome playback.</div>
      </aside>
      <main class="main">
        <div class="topbar"><div class="page-title"><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle || '')}</p></div><div class="row"><a class="btn small-btn" href="#builder/new">New script</a><a class="btn primary small-btn" href="#media">Add media</a></div></div>
        <div id="page">${body}</div>
      </main>
    </div>`;
}

async function init() {
  state.config = await api('/api/config').catch(() => ({ appName: 'Fap Instructor Personal', eventCatalog: [] }));
  window.addEventListener('hashchange', render);
  render();
}

async function render() {
  const path = currentPath();
  try {
    if (path === 'home') return pageHome();
    if (path === 'scripts') return pageScripts();
    if (path.startsWith('script/')) return pageScript(Number(path.split('/')[1]));
    if (path.startsWith('builder/')) return pageBuilder(path.split('/')[1]);
    if (path === 'media') return pageMedia();
    if (path === 'metronome') return pageMetronome();
    if (path === 'generators') return pageGenerators();
    if (path === 'games') return pageGames();
    if (path.startsWith('game/')) return pageGame(Number(path.split('/')[1]));
    if (path === 'about') return pageAbout();
    nav('home');
  } catch (err) {
    shell('Error', 'Something went wrong', `<div class="card"><h2 class="danger">${escapeHtml(err.message)}</h2><button class="btn" onclick="history.back()">Back</button></div>`);
  }
}

async function pageHome() {
  const [scripts, media, games] = await Promise.all([api('/api/scripts?limit=4'), api('/api/media'), api('/api/games?limit=4')]);
  shell('Home', 'Images, videos, scripts, and metronome', `
    <section class="stats">
      <div class="stat"><span class="muted small">Scripts</span><strong>${scripts.items.length}</strong></div>
      <div class="stat"><span class="muted small">Media</span><strong>${media.items.length}</strong></div>
      <div class="stat"><span class="muted small">Games</span><strong>${games.items.length}</strong></div>
      <div class="stat"><span class="muted small">Mode</span><strong>Core</strong></div>
    </section>
    <div class="grid two" style="margin-top:1rem">
      <section class="panel card"><h2>Quick play</h2><div class="grid">${scripts.items.map(scriptCard).join('') || '<p>No scripts yet.</p>'}</div></section>
      <section class="panel card"><h2>Quick actions</h2><div class="grid"><a class="btn primary" href="#media">Add image/video</a><a class="btn" href="#metronome">Open metronome</a><a class="btn" href="#builder/new">Create script</a><a class="btn" href="#generators">Generate timed game</a></div></section>
    </div>`);
  attachCardActions();
}

function scriptCard(s) {
  return `<article class="card"><div class="row between"><h3>${escapeHtml(s.title)}</h3><span class="badge">${fmtSeconds(s.durationSeconds)}</span></div><p class="muted small">${escapeHtml(s.description || '')}</p>${tagsHtml(s.tags)}<div class="row" style="margin-top:.8rem"><a class="btn primary small-btn" href="#script/${s.id}">Play</a><a class="btn small-btn" href="#builder/${s.id}">Edit</a><button class="btn small-btn vote" data-id="${s.id}">▲ ${s.votes || 0}</button></div></article>`;
}
function attachCardActions() { $$('.vote').forEach(b => b.addEventListener('click', async () => { try { const d = await api(`/api/scripts/${b.dataset.id}/vote`, { body: { vote: 1 } }); b.textContent = `▲ ${d.votes}`; } catch (e) { notify(e.message, 'error'); } })); }

async function pageScripts() {
  shell('Scripts', 'Search, play, and edit local scripts', `<div class="panel card"><div class="row"><input id="script-search" placeholder="Search"><input id="script-tag" placeholder="Tag"><button class="btn primary" id="script-go">Search</button><a class="btn" href="#builder/new">Create</a></div></div><div id="script-results" class="grid auto" style="margin-top:1rem"></div>`);
  async function load() { const q = encodeURIComponent($('#script-search').value); const tag = encodeURIComponent($('#script-tag').value); const data = await api(`/api/scripts?search=${q}&tag=${tag}`); $('#script-results').innerHTML = data.items.map(scriptCard).join('') || '<div class="card">No scripts found.</div>'; attachCardActions(); }
  $('#script-go').addEventListener('click', load); $('#script-search').addEventListener('keydown', e => { if (e.key === 'Enter') load(); }); await load();
}

async function pageScript(id) {
  const { item } = await api(`/api/scripts/${id}`);
  shell(item.title, item.description, `<div class="grid two"><section class="card"><div class="row between"><h2>${escapeHtml(item.title)}</h2><span class="badge">${fmtSeconds(item.durationSeconds)}</span></div><p class="muted">${escapeHtml(item.description || '')}</p>${tagsHtml(item.tags)}<div class="row" style="margin-top:1rem"><a class="btn" href="#builder/${item.id}">Edit</a><a class="btn" href="/api/scripts/${item.id}/export/funscript" target="_blank">Export FunScript</a><button class="btn" id="copy-json">Copy JSON</button></div></section><section class="card"><h3>Events</h3><pre>${escapeHtml(JSON.stringify(item.events.slice(0, 8), null, 2))}${item.events.length > 8 ? '\n…' : ''}</pre></section></div><div id="player-mount" style="margin-top:1rem"></div>`);
  $('#copy-json').addEventListener('click', async () => { await navigator.clipboard.writeText(JSON.stringify(item, null, 2)); notify('Copied'); });
  state.player = createPlayer($('#player-mount'), item, 'script');
}

function defaultScript() { return [{ type: 'chat-message', text: 'Welcome. Follow the metronome.', speech: 'Welcome. Follow the metronome.', duration: 4 }, { type: 'metronome', tempo: 60 }, { type: 'stroke', tempo: 60, duration: 20, grip: 'normal', style: 'full' }, { type: 'wait', duration: 8 }, { type: 'game-over', message: 'Complete' }]; }
async function pageBuilder(idOrNew) {
  let item = null; if (idOrNew !== 'new') item = (await api(`/api/scripts/${Number(idOrNew)}`)).item;
  if (state.builderLoadedFor !== idOrNew) { state.builderEvents = item ? structuredClone(item.events) : defaultScript(); state.builderLoadedFor = idOrNew; }
  shell(item ? `Edit: ${item.title}` : 'Script Builder', 'Use JSON events. Add media cues by pasting URLs from the Media page.', `<form id="script-form" class="panel card"><div class="grid two"><div class="field"><label>Title</label><input name="title" value="${escapeHtml(item?.title || 'Untitled script')}" required></div><div class="field"><label>Difficulty</label><select name="difficulty"><option>easy</option><option selected>normal</option><option>advanced</option></select></div></div><div class="field"><label>Description</label><textarea name="description">${escapeHtml(item?.description || '')}</textarea></div><div class="field"><label>Tags</label><input name="tags" value="${escapeHtml((item?.tags || ['draft']).join(', '))}"></div></form><div class="grid two" style="margin-top:1rem"><section class="panel card"><h2>Add event</h2><div class="grid auto">${(state.config?.eventCatalog || []).filter(e => !['device','anal','cbt','nipples','mouth','lungs','moan','cei'].includes(e.type)).map(e => `<button class="btn add-event" data-type="${e.type}">${escapeHtml(e.label || e.type)}</button>`).join('')}</div></section><section class="panel card"><h2>Import / Export</h2><div class="row"><button class="btn" id="export-events">Copy events</button><button class="btn" id="import-events">Import events</button><button class="btn danger-bg" id="reset-events">Reset</button></div><div class="field"><label>Bulk JSON</label><textarea id="bulk-json" style="min-height:180px">${escapeHtml(JSON.stringify(state.builderEvents, null, 2))}</textarea></div><button class="btn" id="apply-bulk">Apply JSON</button></section></div><section class="panel card" style="margin-top:1rem"><div class="row between"><h2>Events <span class="badge">${state.builderEvents.length}</span></h2><span class="muted">Duration: <strong id="duration-est">0:00</strong></span></div><div id="events-list" class="grid"></div><div class="toolbar row between"><button class="btn" id="preview-player">Preview</button><button class="btn primary" id="save-script">Save</button></div></section><div id="preview-mount" style="margin-top:1rem"></div>`);
  renderEventRows();
  $$('.add-event').forEach(btn => btn.addEventListener('click', () => addBuilderEvent(btn.dataset.type)));
  $('#export-events').addEventListener('click', async () => { await navigator.clipboard.writeText(JSON.stringify(readBuilderEvents(), null, 2)); notify('Copied events'); });
  $('#import-events').addEventListener('click', () => { const text = prompt('Paste events JSON array'); if (!text) return; try { state.builderEvents = JSON.parse(text); renderEventRows(); } catch (e) { notify(e.message, 'error'); } });
  $('#reset-events').addEventListener('click', () => { if (confirm('Reset events?')) { state.builderEvents = defaultScript(); renderEventRows(); } });
  $('#apply-bulk').addEventListener('click', () => { try { state.builderEvents = JSON.parse($('#bulk-json').value); renderEventRows(); } catch (e) { notify(e.message, 'error'); } });
  $('#preview-player').addEventListener('click', () => { const draft = collectScriptForm(); draft.id = 'draft'; draft.events = readBuilderEvents(); state.player?.destroy?.(); state.player = createPlayer($('#preview-mount'), draft, 'draft'); });
  $('#save-script').addEventListener('click', async () => { try { const payload = collectScriptForm(); payload.events = readBuilderEvents(); const data = item ? await api(`/api/scripts/${item.id}`, { method: 'PUT', body: payload }) : await api('/api/scripts', { body: payload }); state.builderLoadedFor = null; notify('Saved'); nav(`script/${data.item.id}`); } catch (e) { notify(e.message, 'error'); } });
}
function collectScriptForm() { const fd = new FormData($('#script-form')); return { title: fd.get('title'), description: fd.get('description'), difficulty: fd.get('difficulty'), tags: String(fd.get('tags') || '').split(',').map(s => s.trim()).filter(Boolean) }; }
function readBuilderEvents() { return $$('.event-json').map(t => JSON.parse(t.value)); }
function renderEventRows() { const list = $('#events-list'); if (!list) return; const events = state.builderEvents || []; list.innerHTML = events.map((ev, idx) => `<div class="event-row" data-idx="${idx}"><div class="row between"><strong>${idx + 1}. ${escapeHtml(ev.type)}</strong><div class="row"><button class="btn small-btn up">↑</button><button class="btn small-btn down">↓</button><button class="btn small-btn duplicate">Duplicate</button><button class="btn small-btn danger-bg delete">Delete</button></div></div><textarea class="event-json">${escapeHtml(JSON.stringify(ev, null, 2))}</textarea></div>`).join('') || '<p class="muted">No events.</p>'; $$('.event-row').forEach(row => { const idx = Number(row.dataset.idx); $('.event-json', row).addEventListener('change', () => { try { state.builderEvents[idx] = JSON.parse($('.event-json', row).value); syncBulkAndDuration(); } catch { notify(`Event ${idx + 1} JSON invalid`, 'error'); } }); $('.delete', row).addEventListener('click', () => { state.builderEvents.splice(idx, 1); renderEventRows(); }); $('.duplicate', row).addEventListener('click', () => { state.builderEvents.splice(idx + 1, 0, structuredClone(state.builderEvents[idx])); renderEventRows(); }); $('.up', row).addEventListener('click', () => { if (idx > 0) { [state.builderEvents[idx - 1], state.builderEvents[idx]] = [state.builderEvents[idx], state.builderEvents[idx - 1]]; renderEventRows(); } }); $('.down', row).addEventListener('click', () => { if (idx < state.builderEvents.length - 1) { [state.builderEvents[idx + 1], state.builderEvents[idx]] = [state.builderEvents[idx], state.builderEvents[idx + 1]]; renderEventRows(); } }); }); syncBulkAndDuration(); }
function syncBulkAndDuration() { $('#bulk-json') && ($('#bulk-json').value = JSON.stringify(state.builderEvents, null, 2)); $('#duration-est') && ($('#duration-est').textContent = fmtSeconds((state.builderEvents || []).reduce((s, e) => s + eventDuration(e), 0))); }
function addBuilderEvent(type) { const item = (state.config?.eventCatalog || []).find(e => e.type === type); const ev = { type, ...(structuredClone(item?.defaults || {})) }; ev.type = type; state.builderEvents.push(ev); renderEventRows(); }

async function pageMedia() { const data = await api('/api/media'); shell('Images & Videos', 'Upload files or add direct URLs', `<div class="grid two"><section class="panel card"><h2>Add URL</h2><form id="media-url-form"><div class="field"><label>Title</label><input name="title" required></div><div class="field"><label>Type</label><select name="mediaType"><option>video</option><option>image</option><option>audio</option><option>embed</option></select></div><div class="field"><label>URL</label><input name="url" required placeholder="https://..."></div><div class="field"><label>Tags</label><input name="tags"></div><button class="btn primary">Add URL</button></form></section><section class="panel card"><h2>Upload file</h2><form id="media-upload-form"><div class="field"><label>Title</label><input name="title" required></div><div class="field"><label>Type</label><select name="mediaType"><option>video</option><option>image</option><option>audio</option></select></div><div class="field"><label>File</label><input name="file" type="file" accept="image/*,video/*,audio/*" required></div><div class="field"><label>Tags</label><input name="tags"></div><button class="btn">Upload</button></form></section></div><div class="grid auto" style="margin-top:1rem">${data.items.map(m => `<article class="card"><h3>${escapeHtml(m.title)}</h3><div class="media-stage">${mediaEmbed(m.url, m.mediaType)}</div><div class="row between" style="margin-top:.7rem"><span class="badge">${escapeHtml(m.mediaType)}</span><button class="btn small-btn copy-media" data-url="${escapeHtml(m.url)}">Copy URL</button></div>${tagsHtml(m.tags)}</article>`).join('') || '<div class="card">No media yet.</div>'}</div>`); $('#media-url-form').addEventListener('submit', async e => { e.preventDefault(); const fd = Object.fromEntries(new FormData(e.target)); fd.tags = String(fd.tags || '').split(',').map(s => s.trim()).filter(Boolean); try { await api('/api/media', { body: fd }); notify('Added'); pageMedia(); } catch (err) { notify(err.message, 'error'); } }); $('#media-upload-form').addEventListener('submit', async e => { e.preventDefault(); try { await api('/api/media/upload', { form: new FormData(e.target) }); notify('Uploaded'); pageMedia(); } catch (err) { notify(err.message, 'error'); } }); $$('.copy-media').forEach(b => b.addEventListener('click', async () => { await navigator.clipboard.writeText(b.dataset.url); notify('URL copied'); })); }
function mediaEmbed(url, type) { const u = escapeHtml(url); if (!url) return '<span class="muted">No URL configured</span>'; if (type === 'audio') return `<audio controls src="${u}"></audio>`; if (type === 'image') return `<img src="${u}" alt="media">`; if (type === 'embed') return `<iframe src="${u}" style="width:100%;min-height:220px;border:0;border-radius:14px" allowfullscreen></iframe>`; return `<video controls src="${u}"></video>`; }

function pageMetronome() { shell('Metronome', 'Simple standalone BPM clicker', `<section class="panel card"><div class="grid two"><div><div class="field"><label>BPM</label><input id="metro-bpm" type="number" value="80" min="20" max="240"></div><div class="row"><button class="btn primary" id="metro-start">Start</button><button class="btn" id="metro-stop">Stop</button></div></div><div class="event-display center"><div class="beat-dot" id="standalone-beat" style="margin:2rem auto;width:80px;height:80px"></div><div class="countdown" id="metro-label">80</div><p class="muted">BPM</p></div></div></section>`); state.metronome = createStandaloneMetronome(); }
function createStandaloneMetronome() { let timer = null, audioCtx = null; const dot = $('#standalone-beat'); function pulse() { dot.classList.add('on'); setTimeout(() => dot.classList.remove('on'), 90); try { audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)(); const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain(); osc.frequency.value = 880; gain.gain.value = 0.045; osc.connect(gain); gain.connect(audioCtx.destination); osc.start(); osc.stop(audioCtx.currentTime + 0.04); } catch {} } function start() { stop(); const bpm = Math.max(20, Math.min(240, Number($('#metro-bpm').value || 80))); $('#metro-label').textContent = bpm; pulse(); timer = setInterval(pulse, 60000 / bpm); } function stop() { if (timer) clearInterval(timer); timer = null; dot?.classList.remove('on'); } $('#metro-start').addEventListener('click', start); $('#metro-stop').addEventListener('click', stop); $('#metro-bpm').addEventListener('input', e => $('#metro-label').textContent = e.target.value || '80'); return { destroy: stop }; }

async function pageGenerators() { const gens = await api('/api/game-generators'); shell('Generator', 'Generate a timed metronome game', `<div class="grid auto">${gens.items.map(g => `<article class="card"><div class="row between"><h3>${escapeHtml(g.name)}</h3><span class="badge">runs ${g.runs || 0}</span></div><p class="muted small">${escapeHtml(g.description || '')}</p>${tagsHtml(g.tags)}<button class="btn primary start-gen" data-id="${g.id}" style="margin-top:.8rem">Start generator</button></article>`).join('') || '<div class="card">No generator seeded.</div>'}</div>`); $$('.start-gen').forEach(b => b.addEventListener('click', async () => { try { const d = await api(`/api/game-generators/${b.dataset.id}/start`, { body: {} }); notify('Game generated'); nav(`game/${d.item.id}`); } catch (e) { notify(e.message, 'error'); } })); }
async function pageGames() { const games = await api('/api/games'); shell('Games', 'Generated sessions', `<div class="grid auto">${games.items.map(g => `<article class="card"><div class="row between"><h3>${escapeHtml(g.title)}</h3><span class="badge">${fmtSeconds(g.durationSeconds)}</span></div><p class="muted small">${escapeHtml(g.description || '')}</p>${tagsHtml(g.tags)}<a class="btn primary small-btn" href="#game/${g.id}" style="margin-top:.8rem">Play</a></article>`).join('') || '<div class="card">No generated games yet.</div>'}</div>`); }
async function pageGame(id) { const { item } = await api(`/api/games/${id}`); shell(item.title, 'Generated game', `<div class="card"><div class="row between">${tagsHtml(item.tags)}<span class="badge">${fmtSeconds(item.durationSeconds)}</span></div></div><div id="player-mount" style="margin-top:1rem"></div>`); state.player = createPlayer($('#player-mount'), item, 'game'); }
function pageAbout() { shell('About', 'Simple core build', `<section class="panel card"><h2>What this includes</h2><ul><li>Add/upload images and videos</li><li>Build scripts with media cues</li><li>Play scripts with timers and metronome</li><li>Standalone metronome</li><li>Generated timed games</li></ul><h2>What was removed</h2><ul><li>Login/admin</li><li>Age gate</li><li>Payments/subscriptions</li><li>Toy/device integrations</li><li>Challenger/WebSockets</li></ul></section>`); }

function eventDuration(ev) { if (!ev) return 0; if (Number.isFinite(Number(ev.duration))) return Math.max(0, Number(ev.duration)); if (ev.type === 'metronome-wait') return Math.ceil((60 / Number(ev.tempo || 60)) * Number(ev.count || 4)); if (['metronome', 'stroke-tempo', 'stroke-grip', 'stroke-style', 'stroke-hand'].includes(ev.type)) return 1; if (ev.type === 'chat-message') return Math.max(3, Math.min(20, String(ev.speech || ev.text || '').length / 12)); if (ev.type === 'instruction') return 8; return ev.type === 'game-over' ? 0 : 5; }
function describeEvent(ev) { if (!ev) return ''; if (ev.type === 'stroke') return `${ev.tempo || ''} BPM · ${ev.grip || 'normal'} · ${ev.style || 'full'}`; if (ev.type === 'chat-message') return ev.text || ev.speech || ''; if (ev.type === 'instruction') return ev.description || ''; if (ev.type === 'wait') return 'Rest / wait'; if (ev.type === 'media') return ev.url || 'Media cue'; return JSON.stringify(Object.fromEntries(Object.entries(ev).filter(([k]) => k !== 'id'))); }
function createPlayer(mount, item, kind = 'script') { let events = structuredClone(item.events || []), index = -1, running = false, paused = false, remaining = 0, elapsed = 0, tempo = 0, tickTimer = null, metroTimer = null, audioCtx = null; let totalDuration = events.reduce((s, e) => s + eventDuration(e), 0); mount.innerHTML = `<section class="player"><div class="player-head"><div><strong>${escapeHtml(item.title)}</strong><div class="muted small"><span id="player-count">0/${events.length}</span> · <span id="player-time">0:00 / ${fmtSeconds(totalDuration)}</span></div></div><div class="row"><button class="btn primary" id="player-start">Start</button><button class="btn" id="player-pause">Pause</button><button class="btn" id="player-next">Next</button><button class="btn danger-bg" id="player-stop">Stop</button></div></div><div style="padding:1rem"><div class="progress"><div id="player-progress"></div></div></div><div class="player-body"><div class="event-display"><div class="event-type" id="event-type">Ready</div><div class="countdown" id="countdown">${fmtSeconds(totalDuration)}</div><h2 id="event-title">Press Start</h2><p class="muted" id="event-desc">${escapeHtml(item.description || '')}</p><div id="event-options" class="row"></div><div class="metronome" style="margin-top:1rem"><div class="beat-dot" id="beat-dot"></div><div><strong id="tempo-label">No tempo</strong><div class="muted tiny">Metronome follows tempo events.</div></div></div></div><aside class="grid"><div class="card"><h3>Media</h3><div class="media-stage" id="player-media"><span class="muted">No media cue yet</span></div></div><div class="card"><h3>Messages</h3><div class="chat-log" id="player-chat"></div></div></aside></div></section>`; $('#player-start', mount).addEventListener('click', start); $('#player-pause', mount).addEventListener('click', togglePause); $('#player-next', mount).addEventListener('click', next); $('#player-stop', mount).addEventListener('click', stop); function start() { if (running && paused) return togglePause(); if (running) return; api(kind === 'game' ? `/api/games/${item.id}/play` : (kind === 'script' ? `/api/scripts/${item.id}/play` : '/api/health'), { method: kind === 'draft' ? 'GET' : 'POST', body: kind === 'draft' ? undefined : {} }).catch(() => {}); running = true; paused = false; index = -1; elapsed = 0; $('#player-chat', mount).innerHTML = ''; next(); } function stop() { running = false; paused = false; clearTimers(); stopMetronome(); index = -1; remaining = totalDuration; updateMeta(); $('#event-type', mount).textContent = 'Stopped'; $('#event-title', mount).textContent = 'Stopped'; $('#countdown', mount).textContent = fmtSeconds(totalDuration); } function togglePause() { if (!running) return; paused = !paused; $('#player-pause', mount).textContent = paused ? 'Resume' : 'Pause'; if (paused) { clearTimers(); stopMetronome(); } else { if (tempo) startMetronome(tempo); runCountdown(); } } function clearTimers() { if (tickTimer) clearInterval(tickTimer); tickTimer = null; } function next() { if (!running) return; clearTimers(); index++; if (index >= events.length) { complete(); return; } const ev = events[index]; applyEvent(ev); remaining = eventDuration(ev); if (remaining <= 0) { setTimeout(next, 450); return; } runCountdown(); } function runCountdown() { clearTimers(); updateMeta(); tickTimer = setInterval(() => { if (paused || !running) return; remaining -= 1; elapsed += 1; updateMeta(); if (remaining <= 0) next(); }, 1000); } function updateMeta() { $('#player-count', mount).textContent = `${Math.max(index + 1, 0)}/${events.length}`; $('#player-time', mount).textContent = `${fmtSeconds(elapsed)} / ${fmtSeconds(totalDuration)}`; $('#countdown', mount).textContent = fmtSeconds(remaining || 0); $('#player-progress', mount).style.width = `${Math.min(100, totalDuration ? (elapsed / totalDuration) * 100 : 0)}%`; } function complete() { clearTimers(); stopMetronome(); running = false; $('#event-type', mount).textContent = 'Complete'; $('#event-title', mount).textContent = 'Session complete'; $('#event-desc', mount).textContent = 'Done.'; $('#countdown', mount).textContent = '0:00'; $('#player-progress', mount).style.width = '100%'; } function applyEvent(ev) { $('#event-type', mount).textContent = ev.type; $('#event-title', mount).textContent = ev.title || ev.message || ev.type; $('#event-desc', mount).textContent = describeEvent(ev); $('#event-options', mount).innerHTML = ''; if (['metronome', 'stroke', 'stroke-tempo'].includes(ev.type)) { tempo = Number(ev.tempo || tempo || 60); $('#tempo-label', mount).textContent = `${tempo} BPM`; startMetronome(tempo); } if (ev.type === 'wait') stopMetronome(); if (ev.type === 'chat-message') { addChat(ev.text || ev.speech || ''); speak(ev.speech || ev.text || ''); } if (ev.type === 'instruction') { addChat(`${ev.title || 'Instruction'}: ${ev.description || ''}`); (ev.options || []).forEach(opt => { const btn = document.createElement('button'); btn.className = 'btn small-btn'; btn.textContent = opt.title || 'Option'; btn.addEventListener('click', () => { if (Array.isArray(opt.events) && opt.events.length) { events.splice(index + 1, 0, ...structuredClone(opt.events)); totalDuration += opt.events.reduce((s, e) => s + eventDuration(e), 0); notify('Option queued'); } }); $('#event-options', mount).appendChild(btn); }); } if (ev.type === 'media') $('#player-media', mount).innerHTML = mediaEmbed(ev.url, ev.mediaType || 'video'); if (ev.type === 'game-over') complete(); updateMeta(); } function addChat(text) { if (text) $('#player-chat', mount).insertAdjacentHTML('beforeend', `<div class="chat-msg">${escapeHtml(text)}</div>`); } function speak(text) { if (!('speechSynthesis' in window) || !text) return; if (localStorage.getItem('fi-tts') === 'off') return; speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text)); } function startMetronome(bpm) { stopMetronome(); if (!bpm || bpm <= 0 || paused || !running) return; pulseBeat(); metroTimer = setInterval(pulseBeat, 60000 / bpm); } function stopMetronome() { if (metroTimer) clearInterval(metroTimer); metroTimer = null; $('#beat-dot', mount)?.classList.remove('on'); } function pulseBeat() { const dot = $('#beat-dot', mount); dot.classList.add('on'); setTimeout(() => dot.classList.remove('on'), 90); try { audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)(); const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain(); osc.frequency.value = 880; gain.gain.value = 0.035; osc.connect(gain); gain.connect(audioCtx.destination); osc.start(); osc.stop(audioCtx.currentTime + 0.035); } catch {} } return { destroy() { clearTimers(); stopMetronome(); window.speechSynthesis?.cancel?.(); } }; }

init();
