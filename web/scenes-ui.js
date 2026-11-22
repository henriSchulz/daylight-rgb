// Library, import/export, editor and preview for ko5g-scene animations.
import { renderDoc, Renderer } from './scene.js';
import { UNIT_MS } from './render.js';
import * as api from './api.js';

const $ = (s, r = document) => r.querySelector(s);
const fmt = (n, d = 1) => n.toLocaleString('de-DE', { maximumFractionDigits: d });
const clock = (t) => new Date(t).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
const NAME_RE = /^[A-Za-z0-9_-]{1,64}$/;

const TEMPLATE = {
  format: 'ko5g-scene', version: 1, title: 'Neue Animation', fps: 20,
  colors: { sky: '#0050ff', sun: '#ffb000', ground: '#202840' },
  sprites: { ball: { frames: [['.##.', '####', '####', '.##.']], colors: { '#': 'sun' } } },
  scenes: [{
    name: 'Start', frames: 144, layers: [
      { type: 'pattern', x: 0, y: 15, w: 288, h: 1, rows: ['##..'], colors: { '#': 'ground' }, offset: { keys: [[0, 0], [144, 144]] } },
      { type: 'sprite', sprite: 'ball', x: { keys: [[0, -4], [144, 288]] }, y: { keys: [[0, 11], [12, 1], [24, 11]], ease: 'smooth', repeat: 24 } },
      { type: 'text', text: 'Hallo', panel: 1, color: 'sky' },
    ],
  }],
};

export function slug(s) {
  const t = String(s ?? '')
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/Ä/g, 'Ae').replace(/Ö/g, 'Oe').replace(/Ü/g, 'Ue').replace(/ß/g, 'ss')
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/\.scene\.json$|\.json$/i, '')
    .replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64);
  return t || 'animation';
}

function thumbURL(doc, W, H, panels) {
  const r = new Renderer(doc, W, H, panels);
  const sc = doc.scenes[0];
  const rgb = r.render(sc, Math.floor(Number(sc.frames) / 3));
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  const img = g.createImageData(W, H);
  for (let i = 0; i < W * H; i++) img.data.set([rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2], 255], i * 4);
  g.putImageData(img, 0, 0);
  return c.toDataURL('image/png');
}

/**
 * ctx: {preview, size() -> {W, H, panels}, setSummary(text, warn), setDraft(html), setCanSend(bool)}
 */
export function initScenes(ctx) {
  const el = {
    list: $('#sceneList'), empty: $('#sceneEmpty'), title: $('#sceneTitle'), meta: $('#sceneMeta'),
    rows: $('#sceneRows'), name: $('#sceneName'), save: $('#sceneSave'), exp: $('#sceneExport'),
    del: $('#sceneDelete'), result: $('#sceneResult'), editor: $('#sceneJson'), error: $('#sceneError'),
    file: $('#sceneFile'), add: $('#sceneNew'), panel: $('#scenesPanel'), libError: $('#libError'),
  };
  let lib = [];
  let loaded = false;
  // current document: name = library name it came from (null if not saved yet)
  let cur = null;
  let rendered = null;   // {scenes, mode, bounds, frames}
  let only = null;       // preview only this scene index (null = as the display plays it)
  let lastScene = -1;
  let lastSent = JSON.parse(localStorage.getItem('daylight.sceneSent') || 'null');

  const sig = () => (cur ? JSON.stringify(cur.doc) : '');

  // ---------- library ----------
  async function loadLibrary(selectName) {
    el.libError.textContent = '';
    try {
      const { scenes } = await api.listScenes();
      const { W, H, panels } = ctx.size();
      lib = await Promise.all(scenes.map(async (s) => {
        try {
          const { scene } = await api.getScene(s.name);
          return { ...s, doc: scene, thumb: thumbURL(scene, W, H, panels) };
        } catch (e) {
          return { ...s, doc: null, broken: e.message };
        }
      }));
    } catch (e) {
      lib = [];
      el.libError.textContent = `Bibliothek nicht geladen: ${e.message}.`;
    }
    renderList();
    const pick = selectName ?? cur?.name ?? lib.find((x) => x.doc)?.name;
    if (!cur && pick) select(pick);
    else if (selectName) select(selectName);
  }

  function renderList() {
    el.list.innerHTML = '';
    el.empty.hidden = lib.length > 0;
    for (const item of lib) {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'lib-item';
      if (cur?.name === item.name) b.setAttribute('aria-current', 'true');
      const secs = item.doc ? totalSeconds(item.doc) : 0;
      b.innerHTML = `${item.thumb ? `<img alt="" src="${item.thumb}">` : '<span class="lib-broken"></span>'}<span class="lib-title"></span><small></small>`;
      $('.lib-title', b).textContent = item.title || item.name;
      $('small', b).textContent = item.broken
        ? `Fehler: ${item.broken}`
        : `${item.scenes === 1 ? '1 Szene' : `${item.scenes} Szenen`}, ${fmt(secs)} s`;
      b.addEventListener('click', () => {
        if (cur?.dirty && cur.name !== item.name && !confirm('Die Änderungen an der aktuellen Animation sind nicht gespeichert. Trotzdem wechseln?')) return;
        select(item.name);
      });
      li.append(b);
      el.list.append(li);
    }
  }

  function totalSeconds(doc) {
    const fpsOf = (s) => s.fps ?? doc.fps ?? 20;
    const units = (s) => Math.max(1, Math.floor(100 / fpsOf(s) + 0.5));
    const auto = (doc.mode || (doc.scenes.length > 1 ? 'auto' : 'manual_spots')) === 'auto';
    const list = auto ? doc.scenes : doc.scenes.slice(0, 1);
    return list.reduce((s, sc) => s + sc.frames * units(sc) * UNIT_MS * (auto ? Number(sc.repeat ?? 1) || 1 : 1), 0) / 1000;
  }

  function select(name) {
    const item = lib.find((x) => x.name === name);
    if (!item?.doc) return;
    setDoc(structuredClone(item.doc), { name, dirty: false });
  }

  function setDoc(doc, { name = null, dirty = false, suggested } = {}) {
    cur = { doc, name, dirty };
    ai.modifyWrap.hidden = false;
    only = null;
    el.name.value = name ?? suggested ?? slug(doc.title);
    el.editor.value = JSON.stringify(doc, null, 2);
    el.error.textContent = '';
    renderList();
    renderCurrent();
  }

  // ---------- rendering ----------
  function renderCurrent() {
    if (!cur) {
      el.title.textContent = 'Keine Animation gewählt';
      el.meta.textContent = 'Wähle links eine aus, importiere eine Datei oder fang eine neue an.';
      el.rows.innerHTML = '';
      ctx.setSummary('Keine Animation gewählt.', '');
      ctx.setCanSend(false);
      return;
    }
    const { W, H, panels } = ctx.size();
    let r;
    try {
      r = renderDoc(cur.doc, W, H, panels);
    } catch (e) {
      el.error.textContent = `Kann nicht gezeichnet werden: ${e.message}`;
      ctx.setSummary('Die Animation enthält einen Fehler.', e.message);
      ctx.setCanSend(false);
      return;
    }
    el.error.textContent = '';
    const auto = r.mode === 'auto';
    const playIdx = only !== null ? [only] : auto ? r.scenes.map((_, i) => i) : [0];
    const frames = [], bounds = [];
    for (const i of playIdx) {
      const s = r.scenes[i];
      const reps = only === null && auto ? s.repeat : 1;
      for (let k = 0; k < reps; k++) {
        bounds.push({ start: frames.length, scene: i });
        for (const rgb of s.frames) frames.push({ rgb, units: s.units });
      }
    }
    const totalMs = frames.reduce((s, f) => s + f.units * UNIT_MS, 0);
    rendered = { ...r, bounds, frames };
    lastScene = -1;
    ctx.preview.setSequence({ W, H, frames, totalMs, warnings: [], tooLong: false });

    // details
    el.title.textContent = cur.doc.title || cur.name || 'Ohne Titel';
    const n = r.scenes.length;
    el.meta.textContent = n === 1
      ? 'Eine Szene, sie läuft auf dem Display in Schleife.'
      : auto
        ? `${n} Szenen, das Display spielt sie nacheinander ab.`
        : `${n} Szenen, das Display zeigt nur die erste in Schleife.`;
    el.rows.innerHTML = '';
    const addRow = (label, detail, idx) => {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-pressed', String(only === idx));
      b.innerHTML = '<span></span><small></small>';
      $('span', b).textContent = label;
      $('small', b).textContent = detail;
      b.addEventListener('click', () => { only = idx; renderCurrent(); });
      li.append(b);
      el.rows.append(li);
    };
    if (n > 1) addRow(auto ? 'Wie auf dem Display, alle nacheinander' : 'Wie auf dem Display', `${fmt(totalMs / 1000)} s`, null);
    r.scenes.forEach((s, i) => {
      const secs = (s.frames.length * s.units * UNIT_MS) / 1000;
      const fps = 100 / s.units;
      const rep = auto && s.repeat > 1 ? `, ${s.repeat}× hintereinander` : '';
      addRow(s.name, `${s.frames.length} Bilder, ${fmt(secs)} s bei ${fmt(fps)} Bildern pro Sekunde${rep}`, n > 1 ? i : null);
    });

    const allFrames = r.scenes.reduce((s, x) => s + x.frames.length, 0);
    ctx.setSummary(
      `${n === 1 ? 'Eine Szene' : `${n} Szenen`}, ${allFrames} Bilder, ein Durchlauf dauert ${fmt(totalSeconds(cur.doc))} s.`,
      only !== null && n > 1 ? 'Die Vorschau zeigt gerade nur eine Szene. Gesendet wird die ganze Datei.' : '',
    );
    ctx.setCanSend(true);
    updateButtons();
    updateDraft();
  }

  function updateButtons() {
    const saved = cur?.name && lib.some((x) => x.name === cur.name);
    el.del.hidden = !saved;
    el.save.textContent = saved && el.name.value === cur.name ? 'Änderungen speichern' : 'In Bibliothek speichern';
    el.save.disabled = !cur || (saved && !cur.dirty && el.name.value === cur.name);
  }

  function updateDraft(sceneIdx = lastScene) {
    if (!cur || !rendered) return;
    const parts = [];
    if (lastSent && lastSent.sig === sig()) parts.push(`<b>Das läuft gerade auf dem Display.</b> Gesendet um ${clock(lastSent.at)}.`);
    else parts.push(cur.dirty ? 'Animation mit ungespeicherten Änderungen.' : 'Vorschau, noch nicht von hier gesendet.');
    if (rendered.scenes.length > 1 && sceneIdx >= 0) parts.push(`Szene ${sceneIdx + 1}: ${escapeHtml(rendered.scenes[sceneIdx].name)}`);
    ctx.setDraft(parts.join(' '));
  }

  function onFrame(i) {
    if (!rendered) return;
    let s = rendered.bounds[0]?.scene ?? 0;
    for (const b of rendered.bounds) if (b.start <= i) s = b.scene;
    if (s !== lastScene) { lastScene = s; updateDraft(s); }
  }

  // ---------- editing ----------
  let editTimer;
  el.editor.addEventListener('input', () => {
    clearTimeout(editTimer);
    editTimer = setTimeout(() => {
      let doc;
      try { doc = JSON.parse(el.editor.value); } catch (e) {
        el.error.textContent = `JSON-Fehler: ${e.message}`;
        ctx.setCanSend(false);
        return;
      }
      if (!cur) cur = { doc, name: null, dirty: true };
      cur.doc = doc;
      cur.dirty = true;
      renderCurrent();
    }, 250);
  });
  el.editor.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      el.editor.setRangeText('  ', el.editor.selectionStart, el.editor.selectionEnd, 'end');
      el.editor.dispatchEvent(new Event('input'));
    }
  });
  el.name.addEventListener('input', updateButtons);

  el.add.addEventListener('click', () => {
    if (cur?.dirty && !confirm('Die Änderungen an der aktuellen Animation sind nicht gespeichert. Trotzdem neu anfangen?')) return;
    setDoc(structuredClone(TEMPLATE), { dirty: true });
    $('#sceneEditorBox').open = true;
    el.editor.focus();
  });

  async function importFile(file) {
    let doc;
    try {
      doc = JSON.parse(await file.text());
      renderDoc(doc, ctx.size().W, ctx.size().H, ctx.size().panels);
    } catch (e) {
      say(`„${file.name}“ lässt sich nicht öffnen: ${e.message}`, true);
      return;
    }
    if (cur?.dirty && !confirm('Die Änderungen an der aktuellen Animation sind nicht gespeichert. Trotzdem importieren?')) return;
    setDoc(doc, { dirty: true, suggested: slug(file.name) });
    say(`„${file.name}“ geladen. Speichern legt sie in der Bibliothek ab.`);
  }
  el.file.addEventListener('change', () => { if (el.file.files[0]) importFile(el.file.files[0]); el.file.value = ''; });
  el.panel.addEventListener('dragover', (e) => { e.preventDefault(); el.panel.classList.add('drop'); });
  el.panel.addEventListener('dragleave', (e) => { if (!el.panel.contains(e.relatedTarget)) el.panel.classList.remove('drop'); });
  el.panel.addEventListener('drop', (e) => {
    e.preventDefault();
    el.panel.classList.remove('drop');
    const f = e.dataTransfer.files[0];
    if (f) importFile(f);
  });

  el.exp.addEventListener('click', () => {
    if (!cur) return;
    const blob = new Blob([JSON.stringify(cur.doc, null, 2) + '\n'], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${slug(el.name.value || cur.doc.title)}.scene.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  el.save.addEventListener('click', async () => {
    if (!cur) return;
    const name = el.name.value.trim();
    if (!NAME_RE.test(name)) { say('Der Dateiname darf nur Buchstaben ohne Umlaute, Ziffern, - und _ enthalten (höchstens 64 Zeichen).', true); el.name.focus(); return; }
    if (name !== cur.name && lib.some((x) => x.name === name) && !confirm(`In der Bibliothek gibt es schon „${name}“. Überschreiben?`)) return;
    try {
      await api.saveScene(name, cur.doc);
      cur.name = name;
      cur.dirty = false;
      say(`Gespeichert als ${name}.`);
      await loadLibrary();
      updateButtons();
      updateDraft();
    } catch (e) { say(`Nicht gespeichert: ${e.message}.`, true); }
  });

  el.del.addEventListener('click', async () => {
    if (!cur?.name || !confirm(`„${cur.doc.title || cur.name}“ aus der Bibliothek löschen? Die Datei auf dem Server wird entfernt.`)) return;
    try {
      await api.deleteScene(cur.name);
      say(`${cur.name} gelöscht. Die Vorschau zeigt sie noch, bis du etwas anderes wählst.`);
      cur.name = null;
      cur.dirty = true;
      await loadLibrary();
      updateButtons();
    } catch (e) { say(`Nicht gelöscht: ${e.message}.`, true); }
  });

  // ---------- AI (Claude CLI on the server) ----------
  const EXAMPLES = [
    'Feuerwerk über einer nächtlichen Stadt',
    'Ein Fisch schwimmt durchs Aquarium, Blasen steigen auf',
    'Laufschrift „Guten Morgen“ mit aufgehender Sonne',
    'Zwei Pixel-Roboter spielen Tischtennis',
  ];
  const ai = { form: $('#aiForm'), prompt: $('#aiPrompt'), go: $('#aiGo'), result: $('#aiResult'), modify: $('#aiModify'), modifyWrap: $('#aiModifyWrap') };
  for (const ex of EXAMPLES) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = ex;
    b.addEventListener('click', () => { ai.prompt.value = ex; ai.prompt.focus(); });
    $('#aiExamples').append(b);
  }
  let generating = false;
  ai.prompt.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey) { e.preventDefault(); ai.form.requestSubmit(); }
  });
  ai.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = ai.prompt.value.trim();
    if (!prompt || generating) { if (!prompt) ai.prompt.focus(); return; }
    const modify = !ai.modifyWrap.hidden && ai.modify.checked && cur;
    if (!modify && cur?.dirty && !confirm('Die Änderungen an der aktuellen Animation sind nicht gespeichert. Trotzdem eine neue erzeugen?')) return;
    generating = true;
    ai.go.disabled = true;
    ai.go.setAttribute('aria-busy', 'true');
    ai.result.classList.remove('err');
    const t0 = Date.now();
    const tick = () => {
      const s = Math.round((Date.now() - t0) / 1000);
      ai.go.textContent = `${s} s …`;
      ai.result.textContent = s < 8 ? 'Claude entwirft die Animation …' : s < 40 ? 'Claude zeichnet Figuren und Bewegungen …' : 'Dauert etwas länger, Claude prüft und korrigiert die Animation …';
    };
    tick();
    const timer = setInterval(tick, 1000);
    try {
      const res = await api.generate(prompt, modify ? cur.doc : null);
      const keepName = modify ? cur.name : null;
      setDoc(res.scene, { name: keepName, dirty: true, suggested: slug(res.scene.title || prompt) });
      const tries = res.attempts > 1 ? `, ${res.attempts} Anläufe` : '';
      ai.result.textContent = `${modify ? 'Geändert' : 'Erzeugt'} in ${fmt(res.seconds, 0)} s${tries}. Oben läuft die Vorschau; senden oder speichern, wenn sie gefällt.`;
      ai.modify.checked = true;
    } catch (err) {
      ai.result.classList.add('err');
      ai.result.textContent = `Nicht erzeugt: ${err.message}.`;
    } finally {
      clearInterval(timer);
      generating = false;
      ai.go.disabled = false;
      ai.go.removeAttribute('aria-busy');
      ai.go.textContent = 'Erzeugen';
    }
  });

  function say(msg, err = false) {
    el.result.textContent = msg;
    el.result.classList.toggle('err', err);
  }

  return {
    activate() {
      // refresh the list every time the tab is shown: files may have been added elsewhere
      if (!loaded) {
        loaded = true;
        window.addEventListener('focus', () => { if (!el.panel.hidden) loadLibrary(); });
      }
      loadLibrary();
      renderCurrent();
    },
    onFrame,
    canSend: () => !!cur && !!rendered,
    async send() {
      const total = rendered.scenes.reduce((s, x) => s + x.frames.length, 0);
      await api.playScene(cur.doc, total);
      lastSent = { sig: sig(), at: Date.now() };
      localStorage.setItem('daylight.sceneSent', JSON.stringify(lastSent));
      updateDraft();
    },
    sendHint: () => (rendered && rendered.scenes.reduce((s, x) => s + x.frames.length, 0) > 1000 ? 'Viele Bilder: Das Hochladen dauert etwas.' : ''),
  };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}
