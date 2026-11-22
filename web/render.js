// Turns the editor state into the exact RGB frames the display receives.
// The preview plays these same frames, so what you see is what gets uploaded.
import { pixelLine, GLYPH_H } from './font5x8.js';

// Device frame duration unit. Not verified on hardware: 3 units per frame gives a
// "decent" scroll speed, which fits 10 ms per unit. Adjust here once measured.
export const UNIT_MS = 10;
export const STATIC_UNITS = 100;
// Upload time is the limit, not storage (SD card holds ~66,000 frames; 65535 per spot).
export const MAX_FRAMES = 10000;

export const FONTS = {
  px2: { label: 'Pixel', pixel: 2 },
  px1: { label: 'Pixel klein', pixel: 1 },
  sans: { label: 'Grotesk', css: '"Helvetica Neue", Helvetica, Arial, sans-serif' },
  serif: { label: 'Serif', css: 'Georgia, "Times New Roman", serif' },
  mono: { label: 'Schreibmaschine', css: '"Courier New", Courier, monospace' },
};

export function defaultZone() {
  return {
    lines: 1, text: 'Hallo', text2: '', font: 'px2', smooth: false,
    align: 'center', effect: 'static', speed: 30, blinkHz: 1,
    colorMode: 'solid', c1: '#ff0000', c2: '#ffb000', bg: '#000000',
  };
}

export const hexToRgb = (h) => {
  const n = parseInt(h.replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

// --- text masks -------------------------------------------------------------------

let measureCtx;
function ttfLine(text, family, h, smooth) {
  measureCtx ??= document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const ctx = measureCtx;
  if (!text) return { w: 0, h, a: new Uint8Array(0) };
  let size = 48, asc, desc, m;
  for (; size > 5; size--) {
    ctx.font = `bold ${size}px ${family}`;
    m = ctx.measureText(text);
    const H = ctx.measureText('H');
    asc = Math.max(m.actualBoundingBoxAscent, H.actualBoundingBoxAscent);
    desc = Math.max(m.actualBoundingBoxDescent, 0);
    if (Math.ceil(asc + desc) <= h) break;
  }
  const left = Math.ceil(m.actualBoundingBoxLeft);
  const w = Math.max(1, left + Math.ceil(m.actualBoundingBoxRight));
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.font = `bold ${size}px ${family}`;
  g.fillStyle = '#fff';
  g.textBaseline = 'alphabetic';
  g.fillText(text, left, Math.round(asc + (h - asc - desc) / 2));
  const d = g.getImageData(0, 0, w, h).data;
  const a = new Uint8Array(w * h);
  for (let i = 0; i < a.length; i++) {
    const v = d[i * 4 + 3];
    a[i] = smooth ? v : v >= 110 ? 255 : 0;
  }
  return { w, h, a };
}

/** Lines of a zone as masks with their y offset inside the zone height h. */
function buildLines(zone, h) {
  if (zone.lines === 2) {
    return [
      { ...pixelLine(zone.text ?? '', 1), y: 0 },
      { ...pixelLine(zone.text2 ?? '', 1), y: GLYPH_H },
    ];
  }
  const f = FONTS[zone.font] ?? FONTS.px2;
  const text = (zone.text ?? '').replace(/\s*\n\s*/g, ' ');
  if (f.pixel) {
    const scale = Math.min(f.pixel, Math.floor(h / GLYPH_H));
    const m = pixelLine(text, scale);
    return [{ ...m, y: Math.floor((h - m.h) / 2) }];
  }
  return [{ ...ttfLine(text, f.css, h, zone.smooth), y: 0 }];
}

function columnColors(zone, tw) {
  const out = new Uint8Array(Math.max(tw, 1) * 3);
  const a = hexToRgb(zone.c1), b = hexToRgb(zone.c2);
  for (let x = 0; x < tw; x++) {
    const t = tw > 1 ? x / (tw - 1) : 0;
    let c;
    if (zone.colorMode === 'gradient') c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
    else if (zone.colorMode === 'rainbow') c = hsv(t * 330, 1, 1);
    else c = a;
    out.set(c, x * 3);
  }
  return out;
}

function hsv(hDeg, s, v) {
  const f = (n) => { const k = (n + hDeg / 60) % 6; return Math.round(255 * (v - v * s * Math.max(0, Math.min(k, 4 - k, 1)))); };
  return [f(5), f(3), f(1)];
}

// --- zones --------------------------------------------------------------------------

function prepareZone(zone, x0, w, h) {
  const lines = buildLines(zone, h);
  const tw = Math.max(0, ...lines.map((l) => l.w));
  const speed = Math.max(1, zone.speed);
  const p = { zone, x0, w, h, lines, tw, cols: columnColors(zone, tw), bg: hexToRgb(zone.bg) };
  if (zone.effect === 'scroll') {
    p.tickMs = 1000 / speed;
    p.cycleMs = ((w + tw) / speed) * 1000;
  } else if (zone.effect === 'blink') {
    p.tickMs = 500 / zone.blinkHz;
    p.cycleMs = 1000 / zone.blinkHz;
  }
  return p;
}

function drawZone(p, buf, W, t, cycleMs) {
  const { zone, x0, w, h, lines, tw, cols, bg } = p;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) buf.set(bg, (y * W + x0 + x) * 3);
  if (zone.effect === 'blink' && t % p.cycleMs >= p.cycleMs / 2) return;
  const scrollX = zone.effect === 'scroll' ? w - Math.floor(((t % cycleMs) * zone.speed) / 1000) : null;
  for (const l of lines) {
    let ox;
    if (scrollX !== null) ox = scrollX;
    else if (zone.align === 'left') ox = 0;
    else if (zone.align === 'right') ox = w - l.w;
    else ox = Math.floor((w - l.w) / 2);
    const colorScale = l.w > 1 && tw > 1 ? (tw - 1) / (l.w - 1) : 0;
    for (let y = 0; y < l.h; y++) {
      const dy = l.y + y;
      if (dy < 0 || dy >= h) continue;
      for (let x = 0; x < l.w; x++) {
        const a = l.a[y * l.w + x];
        if (!a) continue;
        const dx = ox + x;
        if (dx < 0 || dx >= w) continue;
        const ci = Math.round(x * colorScale) * 3;
        const o = (dy * W + x0 + dx) * 3;
        if (a === 255) { buf[o] = cols[ci]; buf[o + 1] = cols[ci + 1]; buf[o + 2] = cols[ci + 2]; }
        else {
          const k = a / 255;
          for (let i = 0; i < 3; i++) buf[o + i] = Math.round(bg[i] + (cols[ci + i] - bg[i]) * k);
        }
      }
    }
  }
}

/** Zones laid out on the panels for the chosen arrangement. */
export function zoneLayout(state, panels, W) {
  if (state.layout === 'span') return [{ x0: 0, w: W, zone: state.zones[0], panel: null }];
  return panels.map((p, i) => ({
    x0: p.x, w: p.width, panel: i,
    zone: state.layout === 'each' ? state.zones[i] ?? state.zones[0] : state.zones[0],
  }));
}

/**
 * Build the frame sequence.
 * Returns {W, H, frames: [{rgb: Uint8Array, units}], totalMs, warnings, tooLong}.
 */
export function buildSequence(state, panels, W, H) {
  const preps = zoneLayout(state, panels, W).map((z) => prepareZone(z.zone, z.x0, z.w, H));
  const warnings = [];
  preps.forEach((p, i) => {
    if (p.zone.effect !== 'scroll' && p.tw > p.w) {
      const where = state.layout === 'span' ? 'die Anzeige' : `Panel ${i + 1} (${p.w} px)`;
      warnings.push(`Der Text ist ${p.tw} px breit und passt nicht auf ${where}. Laufschrift zeigt ihn ganz.`);
    }
  });
  if (state.layout === 'same' && preps.length > 1 && preps[0].zone.effect !== 'scroll') {
    const tooWide = preps.filter((p) => p.tw > p.w);
    if (tooWide.length) warnings.splice(0, warnings.length, `Der Text ist ${preps[0].tw} px breit und passt nicht auf ${tooWide.map((p) => `${p.w} px`).join(' und ')}. Laufschrift zeigt ihn ganz.`);
  }

  const animated = preps.filter((p) => p.tickMs);
  let tickUnits = STATIC_UNITS, count = 1, cycleMs = 1;
  if (animated.length) {
    const tick = Math.min(...animated.map((p) => p.tickMs));
    tickUnits = Math.max(1, Math.round(tick / UNIT_MS));
    cycleMs = Math.max(...animated.map((p) => p.cycleMs));
    count = Math.max(2, Math.ceil(cycleMs / (tickUnits * UNIT_MS)));
  }
  const tooLong = count > MAX_FRAMES;
  if (tooLong) warnings.push(`Das wären ${count} Bilder, mehr als ${MAX_FRAMES.toLocaleString('de-DE')} dauern zu lange zum Hochladen. Kürzerer Text oder höheres Tempo hilft.`);

  const frames = [];
  const n = Math.min(count, MAX_FRAMES);
  for (let i = 0; i < n; i++) {
    const buf = new Uint8Array(W * H * 3);
    const t = i * tickUnits * UNIT_MS;
    for (const p of preps) drawZone(p, buf, W, t, p.zone.effect === 'scroll' ? cycleMs : p.cycleMs);
    const prev = frames[frames.length - 1];
    if (prev && prev.units + tickUnits <= 65535 && sameBytes(prev.rgb, buf)) prev.units += tickUnits;
    else frames.push({ rgb: buf, units: tickUnits });
  }
  const totalMs = frames.reduce((s, f) => s + f.units * UNIT_MS, 0);
  return { W, H, frames, totalMs, warnings, tooLong };
}

function sameBytes(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
