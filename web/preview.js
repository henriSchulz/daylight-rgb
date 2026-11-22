// Draws frames as a lit LED matrix, split into the physical panels.
import { UNIT_MS } from './render.js';

const OFF = '#1b2024';
const GAP = 0;   // panels sit flush against each other
const PAD = 3;   // slab padding, in LED pitches

export class LedPreview {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.glow = document.createElement('canvas');
    this.panels = [];
    this.seq = null;
    this.index = 0;
    this.brightness = 1;
    this.selected = null;
    this.playing = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.onPanelClick = null;
    this.onFrame = null;
    this.rects = [];
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
    canvas.addEventListener('click', (e) => this.click(e));
    canvas.addEventListener('pointermove', (e) => {
      canvas.style.cursor = this.onPanelClick && this.hit(e) !== null ? 'pointer' : '';
    });
    this.loop = this.loop.bind(this);
    requestAnimationFrame(this.loop);
  }

  setPanels(panels, W, H) {
    this.panels = panels; this.W = W; this.H = H;
    this.glow.width = W; this.glow.height = H;
    this.resize();
  }

  setSequence(seq) {
    const keepTime = this.seq && seq.frames.length > 1;
    this.seq = seq;
    if (!keepTime || this.index >= seq.frames.length) this.index = 0;
    this.elapsed = 0;
    this.draw();
  }

  setBrightness(f) { this.brightness = f; this.draw(); }
  setSelected(i) { this.selected = i; this.draw(); }
  setPlaying(on) { this.playing = on; this.last = null; }

  step(d) {
    if (!this.seq) return;
    const n = this.seq.frames.length;
    this.index = (this.index + d + n) % n;
    this.draw();
  }

  resize() {
    if (!this.W) return;
    const cw = this.canvas.parentElement.clientWidth;
    const n = this.panels.length;
    // always one row, like the real sign
    const pitch = cw / (this.W + GAP * (n - 1) + 2 * PAD);
    this.rects = [];
    let x = PAD * pitch;
    for (const p of this.panels) {
      this.rects.push({ x, y: PAD * pitch, p });
      x += (p.width + GAP) * pitch;
    }
    const h = (this.H + 2 * PAD) * pitch;
    this.pitch = pitch;
    const dpr = devicePixelRatio || 1;
    this.canvas.style.height = `${Math.round(h)}px`;
    this.canvas.width = Math.round(cw * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  }

  hit(e) {
    const r = this.canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top, p = this.pitch;
    const i = this.rects.findIndex((q) => x >= q.x - p && x <= q.x + (q.p.width + 1) * p && y >= q.y - p && y <= q.y + (this.H + 1) * p);
    return i < 0 ? null : i;
  }

  click(e) {
    const i = this.hit(e);
    if (i !== null && this.onPanelClick) this.onPanelClick(i);
  }

  loop(now) {
    requestAnimationFrame(this.loop);
    if (!this.seq || this.seq.frames.length < 2 || !this.playing) { this.last = now; return; }
    if (this.last == null) this.last = now;
    this.elapsed = (this.elapsed || 0) + (now - this.last);
    this.last = now;
    let changed = false;
    let dur = this.seq.frames[this.index].units * UNIT_MS;
    while (this.elapsed >= dur) {
      this.elapsed -= dur;
      this.index = (this.index + 1) % this.seq.frames.length;
      dur = this.seq.frames[this.index].units * UNIT_MS;
      changed = true;
      if (this.elapsed > 2000) this.elapsed = 0;
    }
    if (changed) this.draw();
  }

  draw() {
    const { ctx, seq, pitch, W, H } = this;
    if (!seq || !pitch) return;
    const cw = this.canvas.width / (devicePixelRatio || 1), ch = this.canvas.height / (devicePixelRatio || 1);
    ctx.clearRect(0, 0, cw, ch);
    const frame = seq.frames[this.index].rgb;
    const b = Math.sqrt(this.brightness); // perceived, not linear

    // one continuous matrix: the panels sit flush against each other
    const first = this.rects[0], last = this.rects[this.rects.length - 1];
    ctx.fillStyle = '#101417';
    ctx.beginPath();
    ctx.roundRect(first.x - pitch * 0.8, first.y - pitch * 0.8, last.x + last.p.width * pitch - first.x + pitch * 1.6, (H + 1.6) * pitch, pitch * 0.9);
    ctx.fill();

    // glow: the frame blurred underneath the dots
    const g = this.glow.getContext('2d');
    const img = g.createImageData(W, H);
    for (let i = 0, j = 0; i < W * H; i++, j += 3) {
      img.data[i * 4] = frame[j] * b; img.data[i * 4 + 1] = frame[j + 1] * b;
      img.data[i * 4 + 2] = frame[j + 2] * b; img.data[i * 4 + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    ctx.save();
    ctx.filter = `blur(${Math.max(2, pitch * 0.9)}px)`;
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = 0.6;
    ctx.imageSmoothingEnabled = true;
    for (const r of this.rects) ctx.drawImage(this.glow, r.p.x, 0, r.p.width, H, r.x, r.y, r.p.width * pitch, H * pitch);
    ctx.restore();

    // dots
    const rad = pitch * 0.38;
    const off = new Path2D();
    for (const r of this.rects) {
      for (let y = 0; y < H; y++) {
        const cy = r.y + (y + 0.5) * pitch;
        for (let x = 0; x < r.p.width; x++) {
          const j = (y * W + r.p.x + x) * 3;
          const R = frame[j] * b, G = frame[j + 1] * b, B = frame[j + 2] * b;
          const cx = r.x + (x + 0.5) * pitch;
          if (R + G + B < 18) { off.moveTo(cx + rad, cy); off.arc(cx, cy, rad, 0, Math.PI * 2); continue; }
          // lift the core a little toward white so saturated LEDs read as lit
          const m = Math.max(R, G, B) / 255;
          ctx.fillStyle = `rgb(${R + (255 - R) * 0.18 * m},${G + (255 - G) * 0.18 * m},${B + (255 - B) * 0.18 * m})`;
          ctx.beginPath();
          ctx.arc(cx, cy, rad, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    ctx.fillStyle = OFF;
    ctx.fill(off);

    // panel being edited ("Jedes Panel einzeln")
    const sel = this.rects[this.selected];
    if (sel) {
      ctx.strokeStyle = 'rgba(255,255,255,.6)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(sel.x - pitch * 0.15, sel.y - pitch * 0.5, (sel.p.width + 0.3) * pitch, (H + 1) * pitch, pitch * 0.5);
      ctx.stroke();
    }
    this.onFrame?.(this.index, seq.frames.length);
  }
}
