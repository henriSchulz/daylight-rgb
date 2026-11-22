import { buildSequence, defaultZone, FONTS, MAX_FRAMES, UNIT_MS } from './render.js';
import { pixelLine } from './font5x8.js';
import { LedPreview } from './preview.js';
import * as api from './api.js';
import { initScenes } from './scenes-ui.js';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const store = {
  get: (k, d) => { try { return JSON.parse(localStorage.getItem(`daylight.${k}`)) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(`daylight.${k}`, JSON.stringify(v)); } catch { /* full or blocked */ } },
};
const clone = (o) => JSON.parse(JSON.stringify(o));
const fmt = (n, d = 1) => n.toLocaleString('de-DE', { maximumFractionDigits: d });
const clock = (t) => new Date(t).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });

const TEXT_COLORS = [
  ['#ff0000', 'Rot'], ['#ff5a00', 'Orange'], ['#ffb000', 'Bernstein'], ['#ffff00', 'Gelb'],
  ['#00ff00', 'Grün'], ['#00ff90', 'Mint'], ['#00ffff', 'Cyan'], ['#0050ff', 'Blau'],
  ['#8a00ff', 'Violett'], ['#ff00b4', 'Pink'], ['#ffffff', 'Weiß'], ['#ffc88a', 'Warmweiß'],
];
const BG_COLORS = [
  ['#000000', 'Schwarz'], ['#00081c', 'Nachtblau'], ['#1c0000', 'Tiefrot'], ['#001200', 'Waldgrün'], ['#10001c', 'Dunkelviolett'],
];

// ---------- state ----------
let config = api.FALLBACK_CONFIG;
let panels = config.panels;
const state = Object.assign({ layout: 'same', zones: [defaultZone()], selected: 0, eachInit: false }, store.get('draft', {}));
state.zones = state.zones.map((z) => ({ ...defaultZone(), ...z }));
const bright = Object.assign({ mode: 'level', pct: 60 }, store.get('brightness', {}));
let lastSent = store.get('lastSent', null);
let history = store.get('history', []);
let seq = null;
let sending = false;
let mode = store.get('mode', 'text');
let sceneCanSend = false;

const zoneIndex = () => (state.layout === 'each' ? state.selected : 0);
const zone = () => state.zones[zoneIndex()];
const signature = () => JSON.stringify({ layout: state.layout, zones: state.layout === 'each' ? state.zones.slice(0, panels.length) : [state.zones[0]] });

function ensureZones() {
  while (state.zones.length < panels.length) state.zones.push(clone(state.zones[0]));
  if (state.selected >= panels.length) state.selected = 0;
}

// ---------- preview ----------
const preview = new LedPreview($('#led'));
preview.onPanelClick = (i) => {
  if (state.layout !== 'each') return;
  state.selected = i;
  syncForm();
  $(`#panelTabs input[value="${i}"]`)?.focus();
};
preview.onFrame = (i, n) => {
  $('#frameInfo').textContent = n > 1 ? `Bild ${i + 1} von ${n}` : '';
  if (mode === 'scenes') scenes.onFrame(i);
};

// ---------- animations (ko5g-scene) ----------
const scenes = initScenes({
  preview,
  size: () => ({ W: config.width, H: config.height, panels }),
  setSummary(text, warn) {
    if (mode !== 'scenes') return;
    $('#summary').textContent = text;
    $('#warn').textContent = warn;
    $('#transport').hidden = false;
  },
  setDraft(html) { if (mode === 'scenes') $('#draftState').innerHTML = html; },
  setCanSend(ok) { sceneCanSend = ok; updateSendButton(); },
});

function setMode(m) {
  mode = m;
  store.set('mode', m);
  const sc = m === 'scenes';
  $('#tabText').setAttribute('aria-selected', String(!sc));
  $('#tabScenes').setAttribute('aria-selected', String(sc));
  $('#tabText').tabIndex = sc ? -1 : 0;
  $('#tabScenes').tabIndex = sc ? 0 : -1;
  $('#controls').hidden = sc;
  $('#scenesPanel').hidden = !sc;
  renderHistory();
  if (sc) {
    preview.setSelected(null);
    $('#warn').textContent = '';
    scenes.activate();
  } else syncForm();
  updateSendButton();
}
$('#tabText').addEventListener('click', () => setMode('text'));
$('#tabScenes').addEventListener('click', () => setMode('scenes'));
$('.modes').addEventListener('keydown', (e) => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  const next = mode === 'text' ? 'scenes' : 'text';
  setMode(next);
  $(next === 'text' ? '#tabText' : '#tabScenes').focus();
});

// ---------- building the static parts of the form ----------
function buildFontTiles() {
  const box = $('#fontTiles');
  box.innerHTML = '';
  for (const [key, f] of Object.entries(FONTS)) {
    const label = document.createElement('label');
    label.innerHTML = `<input type="radio" name="z-font" value="${key}"><span class="tile"><b class="sample"></b>${f.label}</span>`;
    const sample = $('.sample', label);
    if (f.pixel) {
      const m = pixelLine('Aa', 1);
      const c = document.createElement('canvas');
      c.width = m.w; c.height = m.h;
      const g = c.getContext('2d');
      g.fillStyle = '#1a2024';
      for (let i = 0; i < m.a.length; i++) if (m.a[i]) g.fillRect(i % m.w, Math.floor(i / m.w), 1, 1);
      c.style.height = f.pixel === 2 ? '24px' : '16px';
      sample.append(c);
    } else {
      sample.textContent = 'Aa';
      sample.style.fontFamily = f.css;
    }
    box.append(label);
  }
}

function buildSwatches() {
  for (const box of $$('.swatches')) {
    const field = box.dataset.field;
    const list = field === 'bg' ? BG_COLORS : TEXT_COLORS;
    box.innerHTML = '';
    for (const [hex, name] of list) {
      const l = document.createElement('label');
      l.title = name;
      l.innerHTML = `<input type="radio" name="z-${field}" value="${hex}" aria-label="${name}"><span style="--c:${hex}"></span>`;
      box.append(l);
    }
    const c = document.createElement('label');
    c.className = 'custom';
    c.title = 'Eigene Farbe';
    c.innerHTML = `<span></span><input type="color" data-field="${field}" aria-label="Eigene Farbe wählen">`;
    box.append(c);
  }
}

function buildPanelTabs() {
  const box = $('#panelTabs');
  box.innerHTML = '';
  panels.forEach((p, i) => {
    const l = document.createElement('label');
    l.style.flex = `${p.width} 1 0`;
    l.innerHTML = `<input type="radio" name="panel" value="${i}"><span title="${p.width} LEDs breit"><i></i>Panel ${i + 1}</span>`;
    box.append(l);
  });
}

// ---------- state -> form ----------
function setRadio(name, value) {
  for (const r of $$(`input[name="${name}"]`)) r.checked = String(r.value) === String(value);
}

function syncForm() {
  ensureZones();
  const z = zone();
  setRadio('layout', state.layout);
  $('#panelTabs').hidden = state.layout !== 'each';
  setRadio('panel', state.selected);
  preview.setSelected(state.layout === 'each' ? state.selected : null);

  setRadio('z-lines', z.lines);
  for (const name of ['text', 'text2']) {
    const el = $(`input[name="z-${name}"]`);
    if (el.value !== z[name]) el.value = z[name];
  }
  $('#line2Wrap').hidden = z.lines !== 2;
  $('#text1').placeholder = z.lines === 2 ? 'Erste Zeile' : 'Was soll leuchten?';

  setRadio('z-font', z.lines === 2 ? 'px1' : z.font);
  for (const r of $$('input[name="z-font"]')) r.disabled = z.lines === 2 && r.value !== 'px1';
  $('#fontHint').hidden = z.lines !== 2;
  const ttf = z.lines !== 2 && !FONTS[z.font]?.pixel;
  $('#smoothWrap').hidden = !ttf;
  $('input[name="z-smooth"]').checked = !!z.smooth;

  setRadio('z-effect', z.effect);
  setRadio('z-align', z.align);
  $('#alignWrap').hidden = z.effect === 'scroll';
  $('#speedWrap').hidden = z.effect !== 'scroll';
  $('#blinkWrap').hidden = z.effect !== 'blink';
  $('input[name="z-speed"]').value = z.speed;
  $('input[name="z-blinkHz"]').value = z.blinkHz;
  $('#speedOut').textContent = `${z.speed} Spalten pro Sekunde`;
  $('#blinkOut').textContent = `${fmt(z.blinkHz)} × pro Sekunde`;

  setRadio('z-colorMode', z.colorMode);
  $('#c1Wrap').hidden = z.colorMode === 'rainbow';
  $('#c2Wrap').hidden = z.colorMode !== 'gradient';
  $('#c1Label').textContent = z.colorMode === 'gradient' ? 'Anfangsfarbe des Verlaufs' : 'Textfarbe';
  for (const field of ['c1', 'c2', 'bg']) {
    setRadio(`z-${field}`, z[field]);
    const custom = $(`.swatches[data-field="${field}"] .custom`);
    const preset = $$(`input[name="z-${field}"]`).some((r) => r.checked);
    custom.classList.toggle('set', !preset);
    custom.style.setProperty('--c', z[field]);
    $('input[type=color]', custom).value = z[field];
    $('span', custom).style.boxShadow = preset ? '' : `0 0 0 2px var(--sheet), 0 0 0 4px var(--ink), 0 0 12px ${z[field]}`;
  }
  document.documentElement.style.setProperty('--signal', z.colorMode === 'rainbow' ? '#ff00b4' : z.c1);

  setRadio('bmode', bright.mode);
  $('#bright').value = bright.pct;
  $('#bright').disabled = bright.mode !== 'level';
  $('#brightOut').textContent = bright.mode === 'level' ? `${bright.pct} %` : bright.mode === 'auto' ? 'nach Umgebungslicht' : 'aus';
  preview.setBrightness(bright.mode === 'level' ? bright.pct / 100 : bright.mode === 'auto' ? 1 : 0);

  scheduleRender();
}

// ---------- form -> state ----------
const NUMERIC = new Set(['lines', 'speed', 'blinkHz']);

$('#controls').addEventListener('input', onInput);
$('#controls').addEventListener('change', onInput);
function onInput(e) {
  const t = e.target;
  if (t.type === 'radio' && !t.checked) return;
  if (t.type === 'color') {
    zone()[t.dataset.field] = t.value;
  } else if (t.name?.startsWith('z-')) {
    const key = t.name.slice(2);
    zone()[key] = t.type === 'checkbox' ? t.checked : NUMERIC.has(key) ? Number(t.value) : t.value;
    if (key === 'font' && zone().lines === 2) zone().lines = 1;
  } else if (t.name === 'layout') {
    if (t.value === 'each' && !state.eachInit) {
      state.zones = panels.map(() => clone(state.zones[0]));
      state.eachInit = true;
    }
    if (state.layout === 'each' && t.value !== 'each') state.zones[0] = clone(state.zones[state.selected]);
    state.layout = t.value;
  } else if (t.name === 'panel') {
    state.selected = Number(t.value);
  } else if (t.name === 'bmode' || t.id === 'bright') {
    if (t.name === 'bmode') bright.mode = t.value; else bright.pct = Number(t.value);
    store.set('brightness', bright);
    sendBrightness();
  } else return;
  store.set('draft', state);
  syncForm();
}

// ---------- rendering ----------
let renderTimer;
function scheduleRender() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(render, 40);
}

function render() {
  if (mode !== 'text') return;
  seq = buildSequence(state, panels, config.width, config.height);
  preview.setSequence(seq);
  const n = seq.frames.length;
  $('#summary').textContent = n === 1
    ? 'Ein Standbild, es bleibt stehen.'
    : `${n} Bilder, ein Durchlauf dauert ${fmt(seq.totalMs / 1000)} s.`;
  $('#warn').textContent = seq.warnings.join(' ');
  $('#transport').hidden = n < 2;
  updateDraftState();
  updateSendButton();
}

function updateDraftState() {
  if (mode !== 'text') return;
  const el = $('#draftState');
  if (!lastSent) el.innerHTML = 'Entwurf, noch nichts von hier gesendet.';
  else if (lastSent.sig === signature()) el.innerHTML = `<b>Das leuchtet gerade auf dem Display.</b> Gesendet um ${clock(lastSent.at)}.`;
  else el.innerHTML = `Entwurf mit Änderungen. Auf dem Display ist noch der Stand von ${clock(lastSent.at)}.`;
}

function updateSendButton() {
  const b = $('#send');
  b.disabled = sending || (mode === 'scenes' ? !sceneCanSend : !seq || seq.tooLong);
}

// ---------- transport ----------
$('#play').addEventListener('click', () => {
  preview.setPlaying(!preview.playing);
  updatePlayButton();
});
$('#prev').addEventListener('click', () => { preview.setPlaying(false); updatePlayButton(); preview.step(-1); });
$('#next').addEventListener('click', () => { preview.setPlaying(false); updatePlayButton(); preview.step(1); });
function updatePlayButton() {
  $('#play').setAttribute('aria-label', preview.playing ? 'Pause' : 'Abspielen');
  $('#playIcon').innerHTML = preview.playing ? '<path d="M5 3v10M11 3v10"/>' : '<path d="M5 3l8 5-8 5z"/>';
}

// ---------- sending ----------
$('#send').addEventListener('click', send);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
});

async function send() {
  if (sending) return;
  if (mode === 'scenes' ? !sceneCanSend : !seq || seq.tooLong) return;
  sending = true;
  const b = $('#send');
  b.setAttribute('aria-busy', 'true');
  updateSendButton();
  const started = Date.now();
  const label = $('#sendLabel');
  const tick = () => { label.textContent = `Wird gesendet … ${Math.round((Date.now() - started) / 1000)} s`; };
  tick();
  const timer = setInterval(tick, 1000);
  if (mode === 'scenes') {
    $('#warn').textContent = scenes.sendHint();
    try {
      await scenes.send();
      $('#warn').textContent = '';
    } catch (err) {
      $('#warn').textContent = `Senden fehlgeschlagen: ${err.message}. Läuft ko5g.server, und erreicht er das Display?`;
    } finally {
      clearInterval(timer);
      sending = false;
      b.removeAttribute('aria-busy');
      label.textContent = 'Auf Display senden';
      updateSendButton();
    }
    return;
  }
  $('#warn').textContent = seq.frames.length > 1000 ? 'Viele Bilder: Das Hochladen dauert etwas.' : '';
  const sent = seq;
  const sig = signature();
  const snapshot = clone(state);
  try {
    const z = state.zones[zoneIndex()];
    await api.upload([z.text, z.text2].filter(Boolean).join(' ') || 'Web', sent.frames);
    lastSent = { sig, at: Date.now() };
    store.set('lastSent', lastSent);
    addHistory(snapshot, sent, sig);
    $('#warn').textContent = '';
  } catch (err) {
    $('#warn').textContent = `Senden fehlgeschlagen: ${err.message}. Läuft ko5g.server, und erreicht er das Display?`;
  } finally {
    clearInterval(timer);
    sending = false;
    b.removeAttribute('aria-busy');
    label.textContent = 'Auf Display senden';
    updateSendButton();
    updateDraftState();
  }
}

// ---------- history ----------
function thumb(s) {
  const f = s.frames[Math.floor(s.frames.length / 3)];
  const c = document.createElement('canvas');
  c.width = s.W; c.height = s.H;
  const g = c.getContext('2d');
  const img = g.createImageData(s.W, s.H);
  for (let i = 0; i < s.W * s.H; i++) {
    img.data.set([f.rgb[i * 3], f.rgb[i * 3 + 1], f.rgb[i * 3 + 2], 255], i * 4);
  }
  g.putImageData(img, 0, 0);
  return c.toDataURL('image/png');
}

function addHistory(snapshot, s, sig) {
  const z = snapshot.zones[snapshot.layout === 'each' ? snapshot.selected : 0];
  history = history.filter((h) => h.sig !== sig);
  history.unshift({ sig, at: Date.now(), state: snapshot, img: thumb(s), title: [z.text, z.text2].filter(Boolean).join(' / ') || 'Ohne Text', frames: s.frames.length });
  history = history.slice(0, 8);
  store.set('history', history);
  renderHistory();
}

function renderHistory() {
  $('#historyWrap').hidden = history.length === 0 || mode !== 'text';
  const ol = $('#history');
  ol.innerHTML = '';
  for (const h of history) {
    const li = document.createElement('li');
    const b = document.createElement('button');
    b.type = 'button';
    b.innerHTML = `<img alt="" src="${h.img}"><small><span></span><span>${clock(h.at)}</span></small>`;
    $('small span', b).textContent = h.title;
    b.addEventListener('click', () => {
      Object.assign(state, clone(h.state));
      state.zones = state.zones.map((z) => ({ ...defaultZone(), ...z }));
      store.set('draft', state);
      syncForm();
      scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    });
    li.append(b);
    ol.append(li);
  }
}

// ---------- brightness & clock ----------
let brightTimer;
function sendBrightness() {
  clearTimeout(brightTimer);
  const out = $('#brightResult');
  out.classList.remove('err');
  out.textContent = '';
  brightTimer = setTimeout(async () => {
    const level = bright.mode === 'auto' ? 0 : bright.mode === 'off' ? 11 : 1 + (100 - bright.pct) / 10;
    try {
      await api.setBrightness(level);
      out.textContent = bright.mode === 'level' ? `${bright.pct} % ans Display geschickt.` : bright.mode === 'auto' ? 'Sensor-Steuerung ans Display geschickt.' : 'Ausschalten ans Display geschickt.';
    } catch (err) {
      out.classList.add('err');
      out.textContent = `Nicht übernommen: ${err.message}.`;
    }
  }, 450);
}

$('#clock').addEventListener('click', async () => {
  const out = $('#clockResult');
  out.classList.remove('err');
  out.textContent = 'Wird gestellt …';
  try {
    await api.setDatetime();
    out.textContent = `Gestellt auf ${new Date().toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'medium' })}.`;
  } catch (err) {
    out.classList.add('err');
    out.textContent = `Nicht gestellt: ${err.message}.`;
  }
});

// ---------- connection ----------
let retryTimer, failures = 0;
async function connect() {
  clearTimeout(retryTimer);
  const conn = $('#conn');
  try {
    const s = await api.getStatus();
    const c = s.config ?? {};
    const ps = (c.panels ?? []).map((p) => ({ x: p.x, width: p.width ?? p.w })).filter((p) => p.width > 0);
    if (c.width && c.height && ps.length) {
      const changed = JSON.stringify(ps) !== JSON.stringify(panels) || c.width !== config.width || c.height !== config.height;
      config = { width: c.width, height: c.height, panels: ps };
      panels = ps;
      if (changed) setupPanels();
    }
    failures = 0;
    conn.dataset.state = s.mock ? 'mock' : 'ok';
    $('#connText').textContent = s.mock
      ? 'Testmodus ohne Display'
      : `Verbunden, ${config.width} × ${config.height} LEDs auf ${panels.length} Panels`;
  } catch (err) {
    failures += 1;
    const delay = failures < 3 ? 3 : 20;
    conn.dataset.state = failures < 3 ? 'wait' : 'down';
    $('#connText').textContent = failures < 3
      ? 'Display antwortet gerade nicht, versuche es gleich noch einmal …'
      : `Display nicht erreichbar (${err.message}). Neuer Versuch in ${delay} s.`;
    retryTimer = setTimeout(connect, delay * 1000);
    return;
  }
}

function setupPanels() {
  preview.setPanels(panels, config.width, config.height);
  buildPanelTabs();
  if (mode === 'scenes') scenes.activate(); else syncForm();
}

// ---------- start ----------
buildFontTiles();
buildSwatches();
setupPanels();
updatePlayButton();
setMode(mode);
connect();
console.info(`Daylight UI: duration unit assumed ${UNIT_MS} ms, max ${MAX_FRAMES} frames.`);
