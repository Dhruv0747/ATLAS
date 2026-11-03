// Offline Object/Target UI acceptance against the existing preview fixture. No Jetson, no camera.
// Run: python3 project_atlas/tests/vision_features_preview_server.py &  then: node project_atlas/tests/vision_features_ui_acceptance.cjs
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8770/v2/vision3d.html';
const results = []; const ok = (name, cond, detail = '') => results.push([cond ? 'PASS' : 'FAIL', name, detail]);

function feature(id, over = {}) {
  return Object.assign({ id, name: id, state: 'UNAVAILABLE', reason: 'fixture', start_available: false, report: null, metrics: null }, over);
}
const ids = ['face', 'gesture', 'body', 'target', 'object', 'mapping'];

async function cards(page) {
  return page.$$eval('#featureCards .feature-card', cs => cs.map(c => ({
    title: c.querySelector('h3').textContent, state: c.querySelector('strong').textContent,
    metrics: c.querySelector('pre').textContent, buttons: [...c.querySelectorAll('button')].map(b => [b.textContent, b.disabled]),
    download: !c.querySelector('a').hidden })));
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const requests = [];
  page.on('request', r => requests.push([r.method(), new URL(r.url()).pathname, r.postData() || '']));

  // S1: real fixture backend (inference disabled, nothing installed live).
  await page.goto(BASE); await page.waitForTimeout(1500);
  let c = await cards(page);
  ok('S1 six feature cards', c.length === 6, c.map(x => x.title).join(','));
  ok('S1 face/gesture NOT INSTALLED', c[0].state === 'NOT INSTALLED' && c[1].state === 'NOT INSTALLED');
  ok('S1 every button disabled while backend reports no start', c.every(x => x.buttons.every(b => b[1])));
  ok('S1 missing metrics shown as UNAVAILABLE, never zero', c.every(x => /FPS: UNAVAILABLE/.test(x.metrics) && !/FPS: 0/.test(x.metrics)));
  ok('S1 idle notice', /No feature test running/.test(await page.textContent('#featureNotice')));

  // Sample API data via interception (real UI code, fixture responses).
  let sample = null; let fail = false;
  await page.route('**/api/vision3d/features', async (route, req) => {
    if (fail) return route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"backend down"}' });
    if (req.method() === 'POST') return route.fulfill({ status: 409, contentType: 'application/json', body: '{"error":"fixture: start refused"}' });
    const s = typeof sample === 'function' ? sample() : sample;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(s) });
  });

  // S2: Object report READY, start available; backend wrongly offers start for face -> UI must still refuse.
  const report = { state: 'READY', frames: 5, detections_seen: 3, fps: 1.9, last_result: { peak_rss_kib: 204800, cpu_s: 0.04, stamp_ns_exact: '1793727000123456789', detections: [{ box: [1, 2, 30, 40], label: 'person', confidence: .9 }] } };
  sample = { active: null, latest: null, features: ids.map(id => feature(id, id === 'object' ? { state: 'READY', start_available: true, report, metrics: { cpu: 61.2, ram: 62.0, temperature: 62.4 } } : id === 'face' ? { start_available: true } : {})) };
  await page.reload(); await page.waitForTimeout(1500);
  c = await cards(page);
  const obj = c[4], face = c[0];
  ok('S2 Object Start enabled only when backend allows', obj.buttons[0][1] === false);
  ok('S2 Manual PASS enabled with READY evidence (>=2 frames, >=1 detection)', obj.buttons[2][1] === false);
  ok('S2 report download visible', obj.download);
  ok('S2 exact source timestamp shown as string', obj.metrics.includes('1793727000123456789'));
  ok('S2 face start stays disabled even if backend offers it', face.buttons.every(b => b[1]));
  ok('S2 metrics formatted', /Whole Jetson CPU: 61\.20%/.test(obj.metrics) && /Worker peak RSS: 200\.00 MiB/.test(obj.metrics));
  await page.click('#featureCards .feature-card:nth-child(5) button:has-text("Start Test")'); await page.waitForTimeout(400);
  ok('S2 refused start surfaces backend error', /start refused/.test(await page.textContent('#featureNotice')));

  // S3: running Target session with a matching RGB frame -> overlay; mismatched stamp -> no overlay.
  // The camera is simulated as the real viewer would deliver it: status ACTIVE and a stamped frame.
  const stamp = 1793727000.5;
  const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAIAAAAuKetIAAAAgUlEQVRoBdXBAQEAAAABIG72f4gdqsizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvyrMizIs+KPCvybIDOMtHBW64IAAAAAElFTkSuQmCC', 'base64');
  await page.route('**/api/vision3d/status', async route => {
    const res = await route.fetch(); const st = await res.json();
    st.streams = st.streams || {}; st.streams.rgb = Object.assign({}, st.streams.rgb || {}, { state: 'ACTIVE' });
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(st) });
  });
  await page.route('**/api/vision3d/frame?kind=rgb', route => route.fulfill({ status: 200, contentType: 'image/png',
    headers: { 'X-Source-Stamp': String(stamp) }, body: PNG }));
  const running = (st) => ({ active: 'target', latest: { width: 64, height: 48, stamp_ns: st * 1e9, received_at: Date.now() / 1000,
    detections: [{ box: [4, 4, 30, 30], label: 'person', confidence: .8, track_id: 7 }] },
    features: ids.map(id => feature(id, id === 'target' ? { state: 'RUNNING', report: Object.assign({}, report, { state: 'RUNNING' }) } : {})) });
  sample = () => running(stamp);
  await page.waitForTimeout(2200);
  ok('S3 overlay shown for matching fresh RGB frame', await page.isVisible('#featureOverlay'), await page.textContent('#featureOverlayStatus'));
  ok('S3 overlay states 2D only, distance UNAVAILABLE', /distance UNAVAILABLE/.test(await page.textContent('#featureOverlayStatus')));
  c = await cards(page);
  ok('S3 Stop enabled only for the active feature', c[3].buttons[1][1] === false && c[4].buttons[1][1] === true);
  ok('S3 Manual verdicts disabled while running', c[3].buttons[2][1] && c[3].buttons[3][1]);
  sample = () => running(stamp + 0.04);   // a result for a different frame than the one displayed
  await page.waitForTimeout(1300);
  ok('S3 mismatched frame -> overlay hidden', !(await page.isVisible('#featureOverlay')), await page.textContent('#featureOverlayStatus'));

  // S4: backend failure -> everything UNAVAILABLE, start disabled.
  fail = true; await page.waitForTimeout(3300);
  c = await cards(page);
  ok('S4 backend failure -> all UNAVAILABLE and start disabled', c.every(x => x.state === 'UNAVAILABLE' && x.buttons[0][1]));

  // Command boundary: only Vision Lab APIs and static assets were requested.
  const api = requests.filter(r => r[1].startsWith('/api/'));
  const allowed = /^\/api\/vision3d\//;
  const bad = api.filter(r => !allowed.test(r[1]));
  ok('No non-Vision-Lab API calls (no drive, servo, pan-tilt, nav, cmd_vel)', bad.length === 0, JSON.stringify([...new Set(bad.map(r => r.join(' ')))]));
  const posts = requests.filter(r => r[0] === 'POST');
  const failsafe = posts.filter(r => r[1] === '/api/vision3d/viewer' && r[2] === '{"action":"stop"}');   // pagehide/hidden camera stop
  const other = posts.filter(r => !failsafe.includes(r));
  ok('POSTs are only the operator-clicked start plus fail-safe camera-viewer stops', other.length === 1 && other[0][1] === '/api/vision3d/features' && /"action":"start","feature":"object"/.test(other[0][2]), JSON.stringify(other));
  ok('APIs touched', true, [...new Set(api.map(r => r[0] + ' ' + r[1]))].join(', '));

  await browser.close();
  for (const r of results) console.log(r[0], '|', r[1], r[2] ? '| ' + r[2] : '');
  console.log(results.filter(r => r[0] === 'PASS').length + '/' + results.length + ' PASS');
  process.exit(results.every(r => r[0] === 'PASS') ? 0 : 1);
})();
