// Client for ko5g/server.py (served from the same origin, default http://localhost:8080).
// Open the page with ?mock to try the whole flow without a display.
// Open with ?api=http://host:port to talk to a server on another origin.
const params = new URLSearchParams(location.search);
export const MOCK = params.has('mock');
const BASE = (params.get('api') ?? '').replace(/\/$/, '');

export const FALLBACK_CONFIG = {
  width: 288, height: 16,
  panels: [{ x: 0, width: 128, port: 1 }, { x: 128, width: 64, port: 2 }, { x: 192, width: 96, port: 3 }],
};

async function call(path, body, timeoutMs = 8000, method) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(BASE + path, body === undefined
      ? { method: method ?? 'GET', signal: ctl.signal }
      : { method: method ?? 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctl.signal });
    let data;
    try { data = await res.json(); } catch { data = null; }
    if (!res.ok || !data || data.ok === false) {
      throw new Error(data?.error || `Server antwortet mit ${res.status} ${res.statusText}`);
    }
    return data;
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('Keine Antwort in der erwarteten Zeit');
    if (e instanceof TypeError) throw new Error('Server nicht erreichbar');
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

export async function getStatus() {
  if (MOCK) { await wait(300); return { ok: true, config: FALLBACK_CONFIG, composition: { spot_count: 1, mode: 'manual_spots' }, mock: true }; }
  return call('/api/status', undefined, 6000);
}

function toBase64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

/** Upload one spot made of the given frames. Replaces the whole composition on the display. */
export async function upload(name, frames) {
  const body = {
    mode: 'manual_spots',
    spots: [{ name: name.slice(0, 30) || 'Web', frames: frames.map((f) => ({ rgb: toBase64(f.rgb), duration: f.units })) }],
  };
  if (MOCK) { await wait(600 + frames.length * 8); return { ok: true, composition: { spot_count: 1, frames_per_spot: [frames.length] } }; }
  // server merges and RLE-compresses; measured ~30 ms per frame, timeout with 2x margin
  return call('/api/upload', body, 20000 + frames.length * 60);
}

export async function setBrightness(level) {
  if (MOCK) { await wait(200); return { ok: true }; }
  return call('/api/brightness', { level });
}

export async function setDatetime() {
  if (MOCK) { await wait(200); return { ok: true }; }
  return call('/api/datetime', {});
}

// ---------- scene library (ko5g-scene files in scenes/ on the server) ----------
const mockScenes = new Map();
const enc = encodeURIComponent;

export async function listScenes() {
  if (MOCK) return { scenes: [...mockScenes].map(([name, doc]) => ({ name, title: doc.title, scenes: doc.scenes.length, frames: doc.scenes.reduce((s, x) => s + x.frames, 0) })) };
  return call('/api/scenes');
}
export async function getScene(name) {
  if (MOCK) return { scene: structuredClone(mockScenes.get(name)) };
  return call(`/api/scenes/${enc(name)}`);
}
export async function saveScene(name, doc) {
  if (MOCK) { mockScenes.set(name, structuredClone(doc)); return { ok: true }; }
  return call(`/api/scenes/${enc(name)}`, doc, 15000);
}
export async function deleteScene(name) {
  if (MOCK) { mockScenes.delete(name); return { ok: true }; }
  return call(`/api/scenes/${enc(name)}`, undefined, 15000, 'DELETE');
}
/** Let Claude (CLI on the server) write a scene. Only allowed from the computer running the server. */
export async function generate(prompt, scene) {
  if (MOCK) {
    await wait(1500);
    return { scene: { format: 'ko5g-scene', version: 1, title: prompt.slice(0, 40), fps: 20, scenes: [{ name: 'KI-Test', frames: 120, layers: [
      { type: 'text', text: prompt.slice(0, 20), color: '#00ffb0', x: { keys: [[0, 160], [120, -160]] } }] }] }, attempts: 1, cost_usd: 0, seconds: 1.5, frames: 120 };
  }
  return call('/api/generate', scene ? { prompt, scene } : { prompt }, 600000);
}

/** Server renders with the Python reference interpreter and uploads. */
export async function playScene(doc, totalFrames) {
  if (MOCK) { await wait(600 + totalFrames * 4); return { ok: true }; }
  return call('/api/scene/play', doc, 20000 + totalFrames * 60);
}
