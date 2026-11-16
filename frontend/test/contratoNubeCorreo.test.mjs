import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// 109 T14 y 110 T10: los clientes de la nube y del correo usan el contrato generado, sin formas escritas a mano.
const raiz = fileURLToPath(new URL('..', import.meta.url));
const leer = (rel) => readFileSync(`${raiz}${rel}`, 'utf8').replace(/\r\n/g, '\n');
const esquema = leer('src/api/esquema.ts');
const CLIENTES = { nube: 'src/api/nube.ts', correo: 'src/api/correo.ts' };

/** Los nombres de `components['schemas']` que trae el contrato generado. */
function modelos() {
  const inicio = esquema.indexOf('\n  schemas: {\n');
  assert.ok(inicio > 0, 'esquema.ts sin bloque de schemas');
  return new Set([...esquema.slice(inicio).matchAll(/^ {4}(\w+): \{/gm)].map((m) => m[1]));
}

/** Las rutas del contrato que llevan `/nube` o `/correo`. */
const rutas = (tema) => [...esquema.matchAll(/^ {2}"(\/[^"]+)": \{/gm)].map((m) => m[1])
  .filter((r) => r.includes(`/${tema}`));

for (const [tema, fichero] of Object.entries(CLIENTES)) {
  const cita = tema === 'nube' ? '109:RF-19' : '110:RF-1';

  test(`${cita} ${fichero} no lleva tipos provisionales ni interfaces que copien las respuestas`, () => {
    const fuente = leer(fichero);
    assert.doesNotMatch(fuente, /PROVISIONAL/i, `${fichero} aún dice PROVISIONAL`);
    const propias = [...fuente.matchAll(/^export interface (\w+)/gm)].map((m) => m[1]);
    assert.deepEqual(propias, [], `${fichero} escribe a mano: ${propias.join(', ')}`);
  });

  test(`${cita} cada tipo de ${fichero} sale de un modelo que existe en el contrato generado`, () => {
    const fuente = leer(fichero);
    const usados = [...new Set([...fuente.matchAll(/S\['(\w+)'\]/g)].map((m) => m[1]))];
    assert.ok(usados.length >= 5, `${fichero} usa pocos modelos del contrato (${usados.length})`);
    const hay = modelos();
    const faltan = usados.filter((m) => !hay.has(m));
    assert.deepEqual(faltan, [], `${fichero} cita modelos que el contrato no trae: ${faltan.join(', ')}`);
    assert.match(fuente, /import type \{ components \} from '\.\/esquema';/);
  });

  test(`${cita} cada ruta de ${tema} del contrato tiene su llamada en ${fichero}`, () => {
    const fuente = leer(fichero);
    const todas = rutas(tema);
    assert.ok(todas.length >= (tema === 'nube' ? 15 : 5), `pocas rutas de ${tema} en el contrato: ${todas.length}`);
    const sinLlamada = todas.filter((r) => {
      // El selector da su token a la página del propio selector, que lo pide sola: no es del cliente.
      if (r.endsWith('/selector/token')) return false;
      const cola = r.slice(r.indexOf(`/${tema}`) + tema.length + 1);
      const trozos = cola.split(/\{[^}]+\}/).map((t) => t.replace(/^\/+|\/+$/g, '')).filter(Boolean);
      return !trozos.every((t) => fuente.includes(t));
    });
    assert.deepEqual(sinLlamada, [], `rutas del contrato sin llamada en ${fichero}: ${sinLlamada.join(', ')}`);
  });
}
