// Interpreter for the ko5g-scene format (docs/scene-format.md).
// Must render pixel-identically to ko5g/scene.py: keep Python semantics for
// rounding (floor(v + 0.5)), floor division and modulo (result has the divisor's sign).
import { pixelLine } from './font5x8.js';

export class SceneError extends Error {}

const mod = (a, n) => ((a % n) + n) % n;
const fdiv = (a, b) => Math.floor(a / b);
const HEX = /^#[0-9a-fA-F]{6}$/;

export function value(v, t, dflt = 0) {
  if (v === undefined || v === null) return dflt;
  if (typeof v === 'number') return Math.floor(v + 0.5);
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (v && typeof v === 'object' && 'keys' in v) {
    const keys = v.keys;
    if (!keys || !keys.length) return dflt;
    const rep = v.repeat || 0;
    if (rep > 0) t = mod(t, rep);
    let r;
    if (t <= keys[0][0]) r = keys[0][1];
    else if (t >= keys[keys.length - 1][0]) r = keys[keys.length - 1][1];
    else {
      r = keys[keys.length - 1][1];
      for (let i = 0; i + 1 < keys.length; i++) {
        const [ta, va] = keys[i], [tb, vb] = keys[i + 1];
        if (ta <= t && t < tb) {
          const ease = v.ease ?? 'linear';
          let u = (t - ta) / (tb - ta);
          if (ease === 'step') r = va;
          else {
            if (ease === 'smooth') u = (1 - Math.cos(Math.PI * u)) / 2;
            r = va + (vb - va) * u;
          }
          break;
        }
      }
    }
    return Math.floor(r + 0.5);
  }
  throw new SceneError(`Ungültiger Wert: ${JSON.stringify(v)}`);
}

export class Renderer {
  constructor(doc, width = 288, height = 16, panels = null) {
    if (!doc || doc.format !== 'ko5g-scene' || doc.version !== 1) throw new SceneError('Keine ko5g-scene-Datei (format "ko5g-scene", version 1)');
    if (!Array.isArray(doc.scenes) || !doc.scenes.length) throw new SceneError('Die Datei enthält keine Szenen');
    this.doc = doc; this.W = width; this.H = height;
    this.panels = panels && panels.length ? panels : [{ x: 0, width }];
    this.palette = doc.colors ?? {};
    this.sprites = doc.sprites ?? {};
    this.colorCache = new Map();
  }

  color(c) {
    const key = c;
    if (this.colorCache.has(key)) return this.colorCache.get(key);
    if (typeof c === 'string' && Object.prototype.hasOwnProperty.call(this.palette, c)) c = this.palette[c];
    if (!(typeof c === 'string' && HEX.test(c))) throw new SceneError(`Unbekannte Farbe ${JSON.stringify(key)}`);
    const n = parseInt(c.slice(1), 16);
    const rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    this.colorCache.set(key, rgb);
    return rgb;
  }

  fps(scene) { return scene.fps ?? this.doc.fps ?? 20; }
  durationUnits(scene) { return Math.max(1, Math.floor(100 / this.fps(scene) + 0.5)); }

  frames(scene) {
    const n = Math.trunc(Number(scene.frames));
    if (!(n > 0)) throw new SceneError(`Szene "${scene.name ?? ''}" braucht frames > 0`);
    const out = [];
    for (let t = 0; t < n; t++) out.push(this.render(scene, t));
    return out;
  }

  /** One frame as Uint8Array(W*H*3), row-major RGB. */
  render(scene, t) {
    const { W, H } = this;
    const buf = new Uint8Array(W * H * 3);
    const bg = this.color(scene.background ?? '#000000');
    for (let i = 0; i < W * H; i++) buf.set(bg, i * 3);
    if (!Array.isArray(scene.layers)) throw new SceneError('Szene ohne layers');
    for (const layer of scene.layers) {
      if (!this.visible(layer, t)) continue;
      const clip = layer.clip ?? [0, 0, W, H];
      const wrap = !!layer.wrap;
      const put = (x, y, c) => {
        if (wrap) x = mod(x, W);
        if (clip[0] <= x && x < clip[2] && clip[1] <= y && y < clip[3] && x >= 0 && x < W && y >= 0 && y < H) {
          const o = (y * W + x) * 3;
          buf[o] = c[0]; buf[o + 1] = c[1]; buf[o + 2] = c[2];
        }
      };
      const fn = this[`_${layer.type}`];
      if (typeof fn !== 'function' || layer.type === 'region') throw new SceneError(`Unbekannter Layer-Typ ${JSON.stringify(layer.type)}`);
      fn.call(this, layer, t, put);
    }
    return buf;
  }

  visible(layer, t) {
    const f = layer.from ?? 0, to = layer.to;
    if (t < f || (to !== undefined && to !== null && t >= to)) return false;
    if ('blink' in layer) {
      const [on, off] = layer.blink;
      if (mod(t - f, on + off) >= on) return false;
    }
    return value(layer.visible, t, 1) !== 0;
  }

  _sprite(L, t, put) {
    const sp = this.sprites[L.sprite];
    if (!sp) throw new SceneError(`Unbekanntes Sprite ${JSON.stringify(L.sprite)}`);
    const frames = sp.frames;
    let idx;
    if ('cycle' in L) {
      const cy = L.cycle, seq = cy.seq;
      idx = seq[mod(fdiv(t + (cy.offset ?? 0), Math.max(1, cy.every ?? 1)), seq.length)];
    } else idx = value(L.frame, t, 0);
    const rows = frames[mod(idx, frames.length)];
    const cmap = { ...(sp.colors ?? {}), ...(L.colors ?? {}) };
    const x0 = value(L.x, t), y0 = value(L.y, t);
    const flip = value(L.flip, t) !== 0;
    const flash = value(L.flash, t) ? this.color(L.flash_color ?? '#ffffff') : null;
    const resolved = {};
    rows.forEach((row, y) => {
      const chars = [...row], w = chars.length;
      chars.forEach((ch, x) => {
        if (ch === '.' || ch === ' ') return;
        if (!(ch in resolved)) {
          if (!(ch in cmap)) throw new SceneError(`Sprite ${JSON.stringify(L.sprite)}: keine Farbe für ${JSON.stringify(ch)}`);
          resolved[ch] = this.color(cmap[ch]);
        }
        put(x0 + (flip ? w - 1 - x : x), y0 + y, flash ?? resolved[ch]);
      });
    });
  }

  region(L) {
    if ('panel' in L) {
      let i = Math.min(this.panels.length, Math.trunc(Number(L.panel))) - 1;
      if (i < 0) i += this.panels.length; // Python negative index
      const p = this.panels[i];
      if (!p) throw new SceneError(`Panel ${L.panel} gibt es nicht`);
      return [p.x, p.width];
    }
    if ('region' in L) return [L.region[0], L.region[1]];
    return [0, this.W];
  }

  _text(L, t, put) {
    const m = pixelLine(String(L.text), Math.trunc(Number(L.scale ?? 2)));
    const [x0, rw] = this.region(L);
    const align = L.align ?? 'center';
    let x = align === 'left' ? x0 : align === 'right' ? x0 + rw - m.w : x0 + fdiv(rw - m.w, 2);
    x += value(L.x, t);
    const y = fdiv(this.H - m.h, 2) + value(L.y, t);
    const c = this.color(L.color ?? '#ffffff');
    for (let ly = 0; ly < m.h; ly++) for (let lx = 0; lx < m.w; lx++) if (m.a[ly * m.w + lx]) put(x + lx, y + ly, c);
  }

  _rect(L, t, put) {
    const [x, y, w, h] = ['x', 'y', 'w', 'h'].map((k) => value(L[k], t));
    const c = this.color(L.color);
    for (let yy = y; yy < y + h; yy++) for (let xx = x; xx < x + w; xx++) put(xx, yy, c);
  }

  _bar(L, t, put) {
    const [x, y, w, h] = ['x', 'y', 'w', 'h'].map((k) => value(L[k], t));
    const v = Math.max(0, Math.min(100, value(L.value, t)));
    const filled = Math.floor((w * v) / 100);
    const c = this.color(L.color);
    const back = L.back ? this.color(L.back) : null;
    const rtl = (L.dir ?? 'ltr') === 'rtl';
    for (let i = 0; i < w; i++) {
      const on = rtl ? i >= w - filled : i < filled;
      const col = on ? c : back;
      if (!col) continue;
      for (let yy = y; yy < y + h; yy++) put(x + i, yy, col);
    }
  }

  _pattern(L, t, put) {
    const [x, y, w, h] = ['x', 'y', 'w', 'h'].map((k) => value(L[k], t));
    const rows = L.rows.map((r) => [...r]);
    const cmap = L.colors ?? {};
    const off = value(L.offset, t);
    const cache = {};
    for (let j = 0; j < h; j++) {
      const row = rows[mod(j, rows.length)], tw = row.length;
      for (let i = 0; i < w; i++) {
        const ch = row[mod(i + off, tw)];
        if (ch === '.' || ch === ' ') continue;
        if (!(ch in cache)) {
          if (!(ch in cmap)) throw new SceneError(`Muster: keine Farbe für ${JSON.stringify(ch)}`);
          cache[ch] = this.color(cmap[ch]);
        }
        put(x + i, y + j, cache[ch]);
      }
    }
  }

  _pixels(L, t, put) {
    const x0 = value(L.x, t), y0 = value(L.y, t);
    for (const [px, py, c] of L.points) put(x0 + px, y0 + py, this.color(c));
  }
}

/**
 * Render a whole file. Returns {scenes: [{name, frames: [Uint8Array], units, repeat}], mode}.
 */
export function renderDoc(doc, W, H, panels) {
  const r = new Renderer(doc, W, H, panels);
  const scenes = doc.scenes.map((sc, i) => ({
    name: sc.name ?? `Szene ${i + 1}`,
    frames: r.frames(sc),
    units: r.durationUnits(sc),
    repeat: Math.trunc(Number(sc.repeat ?? 1)) || 1,
  }));
  const mode = doc.mode || (scenes.length > 1 ? 'auto' : 'manual_spots');
  return { scenes, mode };
}
