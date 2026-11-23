/**
 * 111:RF-16 — guarda de red de todos los recorridos: nada sale de la máquina.
 *
 * - Lo local (127.0.0.1, localhost, data:, blob:, about:) sigue.
 * - Las teselas de fondo (las de `preview.py`: OpenStreetMap y el satélite) se responden con un PNG de 256×256 hecho
 *   aquí; se apuntan para que una prueba sepa que se pidieron.
 * - Todo lo demás se aborta, se apunta y hace fallar la prueba al terminar.
 * Cada recorrido importa `test` y `expect` de este fichero, nunca de '@playwright/test'.
 */
import { test as base, expect } from '@playwright/test';
import { deflateSync } from 'node:zlib';

const TESELAS = [/^[abc]\.tile\.openstreetmap\.org$/, /^server\.arcgisonline\.com$/];
const LOCALES = new Set(['127.0.0.1', 'localhost', '[::1]', '']);

function crc32(datos: Buffer): number {
  let c = ~0;
  for (const b of datos) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

function trozo(tipo: string, datos: Buffer): Buffer {
  const largo = Buffer.alloc(4);
  largo.writeUInt32BE(datos.length);
  const cuerpo = Buffer.concat([Buffer.from(tipo, 'ascii'), datos]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(cuerpo));
  return Buffer.concat([largo, cuerpo, crc]);
}

/** Un PNG gris de 256×256: la tesela local (ningún byte de un servidor de mapas). */
function png256(): Buffer {
  const fila = Buffer.concat([Buffer.from([0]), Buffer.alloc(256 * 3, 0xc8)]);
  const cabecera = Buffer.alloc(13);
  cabecera.writeUInt32BE(256, 0);
  cabecera.writeUInt32BE(256, 4);
  cabecera.set([8, 2, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), trozo('IHDR', cabecera),
    trozo('IDAT', deflateSync(Buffer.concat(Array(256).fill(fila)))), trozo('IEND', Buffer.alloc(0))]);
}

const PNG = png256();

type Red = { teselas: string[]; abortadas: string[] };

export const test = base.extend<{ red: Red }>({
  red: [async ({ context }, usar) => {
    const teselas: string[] = [];
    const abortadas: string[] = [];
    await context.route('**/*', async (ruta) => {
      const url = new URL(ruta.request().url());
      if (['data:', 'blob:', 'about:'].includes(url.protocol) || LOCALES.has(url.hostname)) {
        await ruta.continue();
      } else if (TESELAS.some((h) => h.test(url.hostname))) {
        teselas.push(url.hostname + url.pathname);
        await ruta.fulfill({ status: 200, contentType: 'image/png', body: PNG });
      } else {
        abortadas.push(url.href.slice(0, 160));
        await ruta.abort();
      }
    });
    await usar({ teselas, abortadas });
    expect(abortadas, 'peticiones fuera de la máquina').toEqual([]);
  }, { auto: true }],
});

export { expect };
export type { Page } from '@playwright/test';

/**
 * 111:RF-16 — la red en reposo según las peticiones que la página y sus marcos hacen de verdad.
 *
 * `waitForLoadState('networkidle')` espera además al «networkidle» propio de cada marco, y el del plano es un `<iframe
 * sandbox>` sin origen propio que Chromium lleva en otro proceso: a veces su evento no le llega a Playwright aunque no
 * quede ninguna petición en vuelo, y la espera dura hasta el tope de la prueba (Actions 45046057235 y 3 de 10
 * repeticiones locales del 2026-11-22, siempre en «Plano de la red», con cero peticiones abiertas). Aquí se cuentan las
 * peticiones con los eventos de la página: 500 ms sin ninguna abierta, como «networkidle»; si una no termina, la prueba
 * falla diciendo cuál.
 */
export function vigilarRed(pagina: import('@playwright/test').Page): () => Promise<void> {
  const enVuelo = new Map<import('@playwright/test').Request, string>();
  let cambio = Date.now();
  pagina.on('request', (r) => { enVuelo.set(r, r.url().slice(0, 120)); cambio = Date.now(); });
  const sale = (r: import('@playwright/test').Request) => { enVuelo.delete(r); cambio = Date.now(); };
  pagina.on('requestfinished', sale);
  pagina.on('requestfailed', sale);
  return async () => {
    await expect.poll(() => (enVuelo.size === 0 && Date.now() - cambio >= 500 ? 'en reposo' : [...enVuelo.values()]),
      { message: 'peticiones que no terminan', timeout: 30_000, intervals: [100] }).toBe('en reposo');
  };
}

/** 070:RF-78 — el mismo patrón de `test/e2e/comun.mjs` (CITA_EN_PANTALLA): nada a la vista cita requisitos o tareas. */
const CITA_EN_PANTALLA = /RF-\d|\b\d{3}:RF|\(spec \d{3}\b|(?:\b\d{3}[ :]|\btarea\s)T\d+\b/g;

export async function comprobar_sin_citas(page: import('@playwright/test').Page, donde: string): Promise<void> {
  // Las fuentes citadas por el asistente (data-cita-de-fuente) son texto literal del corpus: se excluyen solo ellas.
  const texto = await page.evaluate(() => {
    let visible = document.body.innerText;
    for (const n of document.querySelectorAll<HTMLElement>('[data-cita-de-fuente]')) visible = visible.replace(n.innerText, '');
    return visible;
  });
  const citas = [...new Set(texto.match(CITA_EN_PANTALLA) ?? [])];
  expect(citas, `citas internas a la vista en ${donde}`).toEqual([]);
}
