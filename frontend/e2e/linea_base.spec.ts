/**
 * 111:RF-16 — la línea base de la web: las pestañas y acciones de hoy siguen ahí.
 *
 * Las pestañas salen de `TABS` en `src/app/App.tsx` (nunca de una lista copiada aquí): una pestaña nueva entra sola y
 * una que se quite hace fallar el recorrido. En cada pestaña se apuntan sus acciones (botones, campos y listas con
 * nombre accesible). Si existe `linea_base_acciones.json`, toda acción fijada tiene que seguir; con
 * `CSG_E2E_FIJAR_LINEA_BASE=1` el recorrido escribe ese fichero con lo que ve (la primera vez, o al añadir acciones).
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { comprobar_sin_citas, expect, test, type Page } from './sin_red';

const AQUI = dirname(fileURLToPath(import.meta.url));
const FIJADAS = join(AQUI, 'linea_base_acciones.json');

type Pestana = { id: string; etiqueta: string; beta: boolean };

/** Las pestañas de `TABS`, leídas del código de la web. */
function pestanas(): Pestana[] {
  const app = readFileSync(join(AQUI, '..', 'src/app/App.tsx'), 'utf8');
  const bloque = app.match(/const TABS = \[([\s\S]*?)\] as const;/);
  if (!bloque) throw new Error('No se encuentra TABS en src/app/App.tsx');
  const filas = [...bloque[1].matchAll(/\{\s*id:\s*'([^']+)',\s*label:\s*'([^']+)'/g)];
  const betas = new Set([...app.matchAll(/t\.id !== '([^']+)' \|\| betaActiva/g)].map((m) => m[1]));
  return filas.map((m) => ({ id: m[1], etiqueta: m[2], beta: betas.has(m[1]) }));
}

async function acciones(pagina: Page): Promise<string[]> {
  const nombres = await pagina.locator('main button:visible, main select:visible, main input:visible, main a[href]:visible')
    .evaluateAll((els) => els.map((e) => {
      const el = e as HTMLElement;
      const n = el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || el.getAttribute('name') || '';
      return `${el.tagName.toLowerCase()}:${n.replace(/\s+/g, ' ').trim().slice(0, 80)}`;
    }));
  return [...new Set(nombres.filter((n) => !n.endsWith(':')))].sort();
}

test('111:RF-16 — todas las pestañas de la web siguen y conservan sus acciones', async ({ page }, info) => {
  const errores: string[] = [];
  page.on('pageerror', (e) => errores.push(String(e)));
  await page.goto(process.env.CSG_E2E_ENTRADA!, { waitUntil: 'networkidle' });
  const lista = page.getByRole('tablist');
  await expect(lista).toBeVisible();

  const vistas: Record<string, string[]> = {};
  for (const p of pestanas()) {
    const boton = lista.getByRole('tab', { name: p.etiqueta, exact: true });
    if (p.beta && (await boton.count()) === 0) {
      info.annotations.push({ type: 'beta apagada', description: p.id });
      continue;
    }
    await expect(boton, `falta la pestaña ${p.id}`).toBeVisible();
    // Un resumen en diálogo (p. ej. el de la carga del espacio sorteado) se cierra con Escape, como lo haría el operador.
    for (let i = 0; i < 3 && (await page.locator('dialog[open]').count()) > 0; i++) await page.keyboard.press('Escape');
    await expect(page.locator('dialog[open]')).toHaveCount(0);
    await boton.click();
    await expect(boton).toHaveAttribute('aria-selected', 'true');
    await page.waitForLoadState('networkidle');
    vistas[p.id] = await acciones(page);
    await comprobar_sin_citas(page, `pestaña ${p.id}`);
    expect(vistas[p.id].length, `la pestaña ${p.id} no ofrece ninguna acción`).toBeGreaterThan(0);
  }

  await info.attach('acciones.json', { body: JSON.stringify(vistas, null, 1), contentType: 'application/json' });
  if (process.env.CSG_E2E_FIJAR_LINEA_BASE === '1') {
    writeFileSync(FIJADAS, JSON.stringify(vistas, null, 1) + '\n', 'utf8');
  } else if (existsSync(FIJADAS)) {
    const fijadas: Record<string, string[]> = JSON.parse(readFileSync(FIJADAS, 'utf8'));
    for (const [id, antes] of Object.entries(fijadas)) {
      if (!(id in vistas)) continue;      // pestaña beta apagada en esta corrida: ya anotada
      const faltan = antes.filter((a) => !vistas[id].includes(a));
      expect(faltan, `acciones que ya no están en ${id}`).toEqual([]);
    }
    expect(Object.keys(fijadas).filter((id) => !(id in vistas) && !pestanas().find((p) => p.id === id)?.beta),
      'pestañas fijadas que ya no están').toEqual([]);
  }
  expect(errores, 'errores de la página').toEqual([]);
});
