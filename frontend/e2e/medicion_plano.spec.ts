/**
 * 111:RF-1 — medición de la línea base del plano: peso de la página y tiempo hasta el primer dibujo de la red unida con
 * TODOS los alimentadores del espacio sintético sorteado (`CSG_E2E_ALIMENTADORES` para una entrega grande).
 *
 * La página del plano (`pagina_plano.py`) avisa con `{tipo: 'listo'}` cuando termina su primer dibujo; abierta como
 * página principal, se envía el mensaje a sí misma y aquí se mide desde la petición hasta ese aviso. El resultado, con la
 * semilla y el número de alimentadores, queda en `resultados/medicion_plano.json`; `plan.md` (T2) anota la cifra, el
 * presupuesto y la decisión. El presupuesto vive en `PRESUPUESTO` y la prueba falla si la página lo supera.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from './sin_red';

const AQUI = dirname(fileURLToPath(import.meta.url));

/** Presupuesto de la página con todos los alimentadores (111 T2; ver plan.md, «Medición de la línea base»). */
const PRESUPUESTO = { primerDibujoMs: 12_000, pesoBytes: 2 * 1024 * 1024 };

test('111:RF-1 — la red unida con todos los alimentadores se dibuja dentro del presupuesto', async ({ page }, info) => {
  await page.goto(process.env.CSG_E2E_ENTRADA!, { waitUntil: 'networkidle' });
  const espacio = process.env.CSG_E2E_ESPACIO!;
  const base = process.env.CSG_E2E_BASE!;
  const r = await page.request.get(`${base}/api/workspaces/${encodeURIComponent(espacio)}/feeders`);
  expect(r.ok()).toBeTruthy();
  const alimentadores: string[] = (await r.json()).feeders.map((f: { feeder: string }) => f.feeder);
  expect(alimentadores.length).toBeGreaterThan(0);

  const q = new URLSearchParams();
  for (const a of alimentadores) q.append('alimentador', a);
  const url = `${base}/api/workspaces/${encodeURIComponent(espacio)}/plano/pagina?${q.toString()}`;

  // El servidor por separado: lo que tarda en generar la página (la misma petición, pedida antes del marco) y su peso,
  // leído de esa respuesta ya completa (sin carrera con un manejador asíncrono de «response»).
  const t0 = Date.now();
  const generada = await page.request.get(url);
  expect(generada.ok()).toBeTruthy();
  const pesoBytes = (await generada.body()).length;
  const servidorMs = Date.now() - t0;

  // Como en la pestaña «Plano de la red»: la página va en un <iframe sandbox="allow-scripts"> dentro de la web, que es el
  // único origen al que la página manda su «listo».
  // El primer dibujo incluye la petición del propio marco (otra vez al servidor) y el dibujo en el navegador.
  const { primerDibujoMs } = await page.evaluate(async (src) => {
    return await new Promise<{ primerDibujoMs: number }>((ok, mal) => {
      const marco = document.createElement('iframe');
      marco.setAttribute('sandbox', 'allow-scripts');
      marco.style.width = '1200px';
      marco.style.height = '800px';
      const inicio = performance.now();
      const reloj = setTimeout(() => mal(new Error('la página del plano no avisó «listo» en 120 s')), 120_000);
      window.addEventListener('message', (e) => {
        if (e.source === marco.contentWindow && e.data && e.data.tipo === 'listo') {
          clearTimeout(reloj);
          ok({ primerDibujoMs: Math.round(performance.now() - inicio) });
        }
      });
      marco.src = src;
      document.body.appendChild(marco);
    });
  }, url);

  const medicion = {
    semilla: Number(process.env.CSG_E2E_SEMILLA), alimentadores: alimentadores.length, pesoBytes,
    primerDibujoMs, servidorMs, presupuesto: PRESUPUESTO,
    navegador: info.project.name, fecha: new Date().toISOString(),
  };
  mkdirSync(join(AQUI, 'resultados'), { recursive: true });
  writeFileSync(join(AQUI, 'resultados', `medicion_plano_${info.project.name}.json`), JSON.stringify(medicion, null, 2));
  info.annotations.push({ type: 'medición', description: JSON.stringify(medicion) });
  console.log(`[medición] ${JSON.stringify(medicion)}`);

  expect(pesoBytes).toBeGreaterThan(0);
  expect(primerDibujoMs, 'primer dibujo de la red unida').toBeLessThanOrEqual(PRESUPUESTO.primerDibujoMs);
  expect(pesoBytes, 'peso de la página del plano').toBeLessThanOrEqual(PRESUPUESTO.pesoBytes);
});
