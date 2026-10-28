import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const page = pathToFileURL(resolve('output/arquitectura/index.html')).href;
const profile = await mkdtemp(join(tmpdir(), 'igea-c4-browser-'));
const port = 12000 + Math.floor(Math.random() * 40000);
const child = spawn(chrome, [
  '--headless=new',
  '--disable-gpu',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  page,
], { stdio: 'ignore' });

const delay = milliseconds => new Promise(resolvePromise => setTimeout(resolvePromise, milliseconds));

async function findPage() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then(response => response.json());
      const target = targets.find(candidate => candidate.type === 'page');
      if (target) return target;
    } catch (_error) {
      // Chrome may still be starting.
    }
    await delay(100);
  }
  throw new Error('Chrome did not expose the architecture page.');
}

async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise((resolvePromise, reject) => {
    socket.addEventListener('open', resolvePromise, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let sequence = 0;
  const pending = new Map();
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve: accept, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else accept(message.result);
  });
  return {
    send(method, params = {}) {
      sequence += 1;
      return new Promise((accept, reject) => {
        pending.set(sequence, { resolve: accept, reject });
        socket.send(JSON.stringify({ id: sequence, method, params }));
      });
    },
    close() { socket.close(); },
  };
}

async function evaluate(client, expression) {
  const result = await client.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

let client;
try {
  const target = await findPage();
  client = await connect(target.webSocketDebuggerUrl);
  await client.send('Runtime.enable');
  await client.send('Log.enable');
  const browserErrors = [];
  // Protocol events are deliberately checked through an injected error recorder too,
  // because the page has no external logging dependency.

  let ready = false;
  for (let attempt = 0; attempt < 50 && !ready; attempt += 1) {
    ready = await evaluate(client, `Boolean(document.getElementById('flow-next'))`);
    if (!ready) await delay(100);
  }
  if (!ready) throw new Error('The interactive controls did not render.');

  const localAccess = await evaluate(client, `(() => {
    document.querySelector('.c4-access-index [data-node-id="twin"]').click();
    return {
      hidden: document.getElementById('c4-open').hidden,
      href: document.getElementById('c4-open').href,
    };
  })()`);
  if (localAccess.hidden || !localAccess.href.endsWith('/src/igea_dgs/digital_twin/oraculo.py')) {
    throw new Error(`Local direct access failed: ${JSON.stringify(localAccess)}`);
  }

  await evaluate(client, `(() => {
    window.__architectureErrors = [];
    window.addEventListener('error', event => window.__architectureErrors.push(event.message));
    const speed = document.getElementById('flow-speed');
    speed.value = '600';
    speed.dispatchEvent(new Event('input', { bubbles: true }));
    document.getElementById('flow-next').click();
  })()`);
  await delay(180);
  const manual = await evaluate(client, `(() => {
    const doc = document;
    return {
      activeEdges: doc.querySelectorAll('.c4-edge.is-active').length,
      activeNodes: doc.querySelectorAll('.c4-node.is-active').length,
      particleVisible: !doc.getElementById('c4-particle').hidden,
      stepLabel: doc.getElementById('flow-next').textContent,
    };
  })()`);
  await delay(650);
  const manualFinished = await evaluate(client, `document.getElementById('c4-particle').hidden`);

  await evaluate(client, `(() => {
    const doc = document;
    doc.querySelector('[data-view="conversion"]').click();
    const speed = doc.getElementById('flow-speed');
    speed.value = '600';
    speed.dispatchEvent(new Event('input', { bubbles: true }));
    doc.getElementById('flow-play').click();
  })()`);
  await delay(180);
  const automatic = await evaluate(client, `(() => {
    const doc = document;
    return {
      selectedView: doc.querySelector('[data-view].active')?.dataset.view,
      playLabel: doc.getElementById('flow-play').textContent,
      activeEdges: doc.querySelectorAll('.c4-edge.is-active').length,
      particleVisible: !doc.getElementById('c4-particle').hidden,
    };
  })()`);
  await delay(4500);
  const automaticFinished = await evaluate(client, `(() => ({
    playLabel: document.getElementById('flow-play').textContent,
    particleHidden: document.getElementById('c4-particle').hidden,
    message: document.getElementById('c4-detail-text').textContent,
  }))()`);

  await evaluate(client, `(() => {
    document.getElementById('flow-play').click();
    document.getElementById('flow-play').click();
    document.getElementById('flow-reset').click();
  })()`);
  const reset = await evaluate(client, `(() => ({
    playLabel: document.getElementById('flow-play').textContent,
    activeEdges: document.querySelectorAll('.c4-edge.is-active').length,
    activeNodes: document.querySelectorAll('.c4-node.is-active').length,
    particleHidden: document.getElementById('c4-particle').hidden,
  }))()`);

  await client.send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-reduced-motion', value: 'reduce' }],
  });
  await evaluate(client, `document.getElementById('flow-next').click()`);
  await delay(80);
  const reducedMotion = await evaluate(client, `document.getElementById('c4-particle').hidden`);

  await client.send('Emulation.setDeviceMetricsOverride', {
    width: 320, height: 900, deviceScaleFactor: 1, mobile: true,
  });
  const mobile = await evaluate(client, `(() => ({
    innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    rootWidth: document.getElementById('igea-c4-flow').scrollWidth,
    canvas: getComputedStyle(document.querySelector('.c4-canvas')).display,
    list: getComputedStyle(document.querySelector('.c4-mobile-flow')).display,
    firstStep: document.querySelector('.c4-mobile-flow button').textContent,
  }))()`);
  browserErrors.push(...await evaluate(client, `window.__architectureErrors || []`));

  if (manual.activeEdges !== 1 || manual.activeNodes !== 2 || !manual.particleVisible || !manualFinished) {
    throw new Error(`Manual flow verification failed: ${JSON.stringify(manual)}`);
  }
  if (automatic.selectedView !== 'conversion' || automatic.playLabel !== 'Pausar' || automatic.activeEdges !== 1 || !automatic.particleVisible) {
    throw new Error(`Automatic flow verification failed: ${JSON.stringify(automatic)}`);
  }
  if (automaticFinished.playLabel !== 'Reproducir' || !automaticFinished.particleHidden || !automaticFinished.message.includes('completado')) {
    throw new Error(`Finite playback verification failed: ${JSON.stringify(automaticFinished)}`);
  }
  if (reset.playLabel !== 'Reproducir' || reset.activeEdges !== 0 || reset.activeNodes !== 0 || !reset.particleHidden) {
    throw new Error(`Pause/reset verification failed: ${JSON.stringify(reset)}`);
  }
  if (!reducedMotion) throw new Error('Reduced-motion flow did not finish immediately.');
  if (mobile.canvas !== 'none' || mobile.list === 'none' || !mobile.firstStep.includes('->') || mobile.documentWidth > mobile.innerWidth || mobile.rootWidth > mobile.innerWidth) {
    throw new Error(`Mobile fallback verification failed: ${JSON.stringify(mobile)}`);
  }
  if (browserErrors.length) throw new Error(`Browser errors: ${JSON.stringify(browserErrors)}`);
  console.log(JSON.stringify({ localAccess, manual, automatic, automaticFinished, reset, reducedMotion, mobile, browserErrors }, null, 2));
} finally {
  client?.close();
  child.kill();
  await delay(200);
  await rm(profile, { recursive: true, force: true });
}
