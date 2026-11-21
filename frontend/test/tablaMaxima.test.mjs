import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 004:RF-112 a RF-116, 028:RF-43 y RF-44: la tabla «Buscar la máxima» con cada dato en su columna; en el coincidente,
// el instante común en las columnas principales y la máxima propia y el pico solo como referencia. Datos ficticios.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const PF = join(FRONT, 'src', 'features', 'powerfactory');
const FUENTE = readFileSync(join(PF, 'DemandaMedida.tsx'), 'utf8');

async function cargar() {
  assert.ok(existsSync(join(PF, 'tablaMaxima.ts')), 'falta tablaMaxima.ts');
  const salida = await build({
    stdin: { contents: `export * from './src/features/powerfactory/tablaMaxima';`, resolveDir: FRONT, loader: 'ts' },
    bundle: true, format: 'cjs', platform: 'node', write: false,
  });
  const require = createRequire(import.meta.url);
  const m = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(m, m.exports, require);
  return m.exports;
}

const fila = (alimentador, fecha, kw, extra = {}) => ({
  alimentador, medidor: `M-${alimentador}`, libro: 'l.xlsx', hojas: ['h'], fecha, kw, kvar: kw * 0.3, kva: null, fp: null,
  kva_calculado: false, fp_calculado: false, registros: 96, columnas: {}, avisos: [], error: null,
  ventana: { inicio: '2026-07-01 18:15:00', fin: fecha, registros: 4, minutos: 15 },
  sostenida: { fecha: '2026-07-02 20:00:00', kw: kw + 50, sostenida: true, registros: 4, minutos: 15 },
  pico: { fecha: '2026-07-03 03:15:00', kw: kw + 400, minutos: 15 }, ...extra,
});

test('028:RF-44 coincidente: un instante común, la propia de referencia y lo que se carga es la fila', async () => {
  const m = await cargar();
  const comun = '2026-07-01 19:00:00';
  const res = { ambito: 'coincidente', instante: comun, coincidente: { fecha: comun, total_kw: 300 },
    resultados: [fila('A1', comun, 100), fila('A2', comun, 200)] };
  const modo = m.modoDeLaTabla(res, 'alimentadores');
  assert.equal(modo.instanteComun, comun);
  assert.equal(modo.deOtroAmbito, false);
  assert.equal(modo.tituloFecha, 'Fecha y hora (instante común)');
  assert.equal(m.conPropiaDeReferencia(modo), true);
  for (const r of res.resultados) {
    assert.equal(m.fueraDelInstante(r, modo), false);
    assert.deepEqual(m.cargaDeLaFila(r), { fecha: comun, kw: r.kw, kvar: r.kvar });
    assert.notEqual(m.cargaDeLaFila(r).kw, r.sostenida.kw, 'la propia no sustituye a lo que se carga');
  }
});

test('028:RF-44 no coincidente: cada alimentador su máxima sostenida, sin columna de propia', async () => {
  const m = await cargar();
  const res = { ambito: 'propia', resultados: [fila('A1', '2026-07-01 19:00:00', 100), fila('A2', '2026-07-05 12:00:00', 90)] };
  const modo = m.modoDeLaTabla(res, 'sistema');
  assert.equal(modo.instanteComun, null);
  assert.equal(modo.deOtroAmbito, false, 'la no coincidente se elige con cualquier ámbito');
  assert.equal(m.conPropiaDeReferencia(modo), false);
  assert.equal(modo.tituloFecha, 'Fecha y hora (máx. 1 h)');
  assert.equal(m.cargaDeLaFila(res.resultados[1]).fecha, '2026-07-05 12:00:00');
});

test('028:RF-43 sistema: el instante del sistema, y la tabla de otro ámbito se dice', async () => {
  const m = await cargar();
  const t = '2026-07-15 21:00:00';
  const res = { ambito: 'sistema', por_barra: true, sistema_60kv: { fecha: t, total_kw: 900 },
    resultados: [fila('A1', t, 100), fila('A2', '2026-07-03 10:00:00', 80)] };
  const modo = m.modoDeLaTabla(res, 'sistema');
  assert.equal(modo.instanteComun, t);
  assert.equal(m.fueraDelInstante(res.resultados[0], modo), false);
  assert.equal(m.fueraDelInstante(res.resultados[1], modo), true, 'sin medida en el instante: se señala');
  assert.equal(m.modoDeLaTabla(res, 'alimentadores').deOtroAmbito, true);
  assert.equal(m.modoDeLaTabla({ ambito: 'coincidente', coincidente: { fecha: t } }, 'sistema').deOtroAmbito, true);
  // Un resultado guardado antes de 028:RF-43 se deduce de sus campos.
  assert.equal(m.ambitoDe({ por_barra: true, sistema_60kv: { fecha: t } }), 'sistema');
  assert.equal(m.ambitoDe({ por_barra: true }), 'set');
});

test('004:RF-114 factor de carga con tres decimales y la hora de la ventana', async () => {
  const m = await cargar();
  assert.equal(m.fmtFactor(0.61234), '0.612');
  assert.equal(m.fmtFactor(null), '—');
  assert.equal(m.horaDeLaVentana(fila('A1', '2026-07-01 19:00:00', 1)), '18:15–19:00');
  assert.equal(m.horaDeLaVentana({ ...fila('A1', 'x', 1), ventana: { inicio: 'x', fin: 'x', registros: 1, minutos: 60 } }), '');
});

test('004:RF-116 cada dato en su columna: sin «Periodo:» en la fecha ni el aviso de tensión en la celda', () => {
  assert.doesNotMatch(FUENTE, /Periodo: \{fmtNum\(r\.maxima_periodo\.kw/, 'la referencia del periodo sigue dentro de la fecha');
  assert.doesNotMatch(FUENTE, /\{r\.tension_aviso && <div className="muted small">/, 'el aviso de tensión invade la columna');
  for (const col of ['Pico 15 min (kW)', 'Fecha del pico', 'Promedio (kW)', 'F. carga', 'Máx. propia (kW)', 'Máx. del periodo']) {
    assert.ok(FUENTE.includes(`>${col}</th>`), `falta la columna ${col}`);
  }
  assert.match(FUENTE, /className="aviso-icono"/);
  assert.match(FUENTE, /Instante común: /);
  assert.doesNotMatch(FUENTE, /registro\(s\)|alimentador\(es\)/);
});
