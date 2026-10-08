// Export a .drawio file to .vsdx with draw.io's own client-side VsdxExport (the code behind
// File > Export as > VSDX), running the draw.io webapp bundled in drawio-desktop in headless Chrome.
// The drawio CLI (-x) cannot write vsdx (it silently writes a PDF), hence this script.
//
// Setup (once):
//   npx @electron/asar@3.2.17 extract /opt/drawio/resources/app.asar /tmp/drawio-app/app
//   (cd /tmp/drawio-app && npm i puppeteer-core@23)
// Usage:
//   NODE_PATH=/tmp/drawio-app/node_modules node export_vsdx.js history/homelab-architecture.drawio history/homelab-architecture.vsdx
const http = require('http'), path = require('path');
const WEBAPP = process.env.DRAWIO_WEBAPP || '/tmp/drawio-app/app/drawio/src/main/webapp';
const MIME = {'.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json',
              '.svg': 'image/svg+xml', '.png': 'image/png', '.xml': 'application/xml', '.txt': 'text/plain'};
const server = http.createServer((req, res) => {
  const f = path.join(WEBAPP, decodeURIComponent(req.url.split('?')[0]));
  require('fs').readFile(f, (err, data) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, {'Content-Type': MIME[path.extname(f)] || 'application/octet-stream'}); res.end(data);
  });
}).listen(8123, '127.0.0.1');
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const [,, input, output] = process.argv;
(async () => {
  const browser = await puppeteer.launch({executablePath: '/usr/bin/google-chrome', headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage']});
  const page = await browser.newPage();
  page.on('pageerror', e => console.error('pageerror', e.message));
  await page.evaluateOnNewDocument(() => {
    let real;
    Object.defineProperty(window, 'EditorUi', { configurable: true,
      get() { return real; },
      set(fn) { real = new Proxy(fn, { apply(t, self, args) { window.__ui = self; return Reflect.apply(t, self, args); },
                                       construct(t, args, nt) { const o = Reflect.construct(t, args, nt); window.__ui = o; return o; } }); } });
  });
  await page.goto('http://127.0.0.1:8123/index.html?offline=1&stealth=1&lang=en&splash=0&gapi=0&db=0&od=0&gh=0&gl=0&tr=0&noExitBtn=1',
                  {waitUntil: 'load', timeout: 120000});
  await page.waitForFunction(() => window.__ui && window.__ui.editor && window.__ui.editor.graph && typeof App !== 'undefined', {timeout: 120000});
  await new Promise(r => setTimeout(r, 3000));
  const xml = fs.readFileSync(input, 'utf8');
  const name = require('path').basename(input);
  const b64 = await page.evaluate(async (xml, name) => {
    const ui = window.__ui;
    ui.openLocalFile(xml, name, true);
    await new Promise(r => setTimeout(r, 3000));
    if (typeof VsdxExport === 'undefined') await new Promise((res, rej) => mxscript('js/extensions.min.js', res, null, null, null, rej));
    return await new Promise((resolve, reject) => {
      ui.saveData = (fname, fmt, data, mime, base64) => resolve(data);
      const ok = new VsdxExport(ui).exportCurrentDiagrams(false);
      if (!ok) reject(new Error('VsdxExport returned false'));
      setTimeout(() => reject(new Error('timeout')), 60000);
    });
  }, xml, name);
  fs.writeFileSync(output, Buffer.from(b64, 'base64'));
  console.log('wrote', output, fs.statSync(output).size, 'bytes');
  await browser.close(); server.close();
})().catch(e => { console.error(e); process.exit(1); });
