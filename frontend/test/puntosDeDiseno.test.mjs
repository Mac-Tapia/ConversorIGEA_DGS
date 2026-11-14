import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const entrada = (rel) => fileURLToPath(new URL(rel, import.meta.url));

async function cargar(rel) {
  const salida = await build({
    entryPoints: [entrada(rel)], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

const logica = () => cargar('../src/features/powerfactory/puntosDeDiseno.ts');

// Como SECA001 de CA101 (2026-11-13): la web la tiene en un nodo y en DIgSILENT el enlace llega a otro.
const CAMBIADA = {
  sed: 'SE1', alimentador: 'AL1', variacion: 'Carga_SE1_AL1_1', estado: 'cambiada', error: null,
  guardado: { barra: 'N1' }, leido: { barra: 'N9', enlace: { nombre: 'LNE_SE1', km: 1.2 } },
  cambios: ['nodo de conexión N1 → N9'],
};
const IGUAL = { ...CAMBIADA, sed: 'SE2', estado: 'igual', cambios: [], leido: { barra: 'N1', enlace: null } };
const SOLO = { ...CAMBIADA, sed: 'SE0', estado: 'solo_en_digsilent', guardado: null,
  cambios: ['no está entre las cargas aplicadas desde esta web'] };
const SIN_LEER = { ...CAMBIADA, sed: 'SE3', estado: 'no_leida', leido: null, cambios: [], error: 'no se leyó en DIgSILENT' };

const trabajo = (project, created_at, status = 'done', kind = 'mapa_cargas_digsilent') => ({
  kind, status, created_at, result: { project, lectura: `ubicacion_cargas_${created_at}.json`, diferencias: [] },
});

test('017:RF-124: la lectura que vale es la última terminada de este proyecto', async () => {
  const { ultimaLectura } = await logica();
  const trabajos = [trabajo('PRY', 3), trabajo('OTRO', 9), trabajo('PRY', 5), trabajo('PRY', 7, 'failed'),
    trabajo('PRY', 8, 'done', 'cargas_aplicar')];
  assert.equal(ultimaLectura(trabajos, 'PRY').lectura, 'ubicacion_cargas_5.json');
  assert.equal(ultimaLectura(trabajos, ' PRY ').lectura, 'ubicacion_cargas_5.json');
  assert.equal(ultimaLectura(trabajos, 'NINGUNO'), null);
});

test('017:RF-124: «Usar este punto» solo con un nodo leído y algo que cambiar', async () => {
  const { sePuedeUsar } = await logica();
  assert.equal(sePuedeUsar(CAMBIADA), true);
  assert.equal(sePuedeUsar(SOLO), true);
  assert.equal(sePuedeUsar(IGUAL), false);
  assert.equal(sePuedeUsar(SIN_LEER), false);
  assert.equal(sePuedeUsar({ ...CAMBIADA, leido: { barra: null } }), false);
});

test('017:RF-124: cada fila dice qué cambió o por qué no se leyó, y las que piden decisión van primero', async () => {
  const { textoDiferencia, filasOrdenadas } = await logica();
  assert.equal(textoDiferencia(CAMBIADA), 'Cambiada en DIgSILENT: nodo de conexión N1 → N9');
  assert.equal(textoDiferencia(IGUAL), 'Igual que en DIgSILENT');
  assert.equal(textoDiferencia(SIN_LEER), 'No se pudo leer: no se leyó en DIgSILENT');
  assert.deepEqual(filasOrdenadas([IGUAL, SIN_LEER, CAMBIADA, SOLO]).map((d) => d.sed), ['SE0', 'SE1', 'SE3', 'SE2']);
});

test('017:RF-109: rótulo con SED y kW, y coordenadas UTM solo si el perfil da su CRS', async () => {
  const { rotuloCarga, textoCoordenadas } = await logica();
  assert.equal(rotuloCarga({ sed: 'SE1', kw: 1206, sola: true }),
    `SE1 · ${(1206).toLocaleString('es-PE', { maximumFractionDigits: 1 })} kW`);
  assert.match(rotuloCarga({ sed: 'SE1', kw: null, sola: false }), /^SE1 · en bloque$/);
  assert.equal(textoCoordenadas({ lat: -13.5, lon: -76.0, utm: null }), '-13.500000, -76.000000');
  assert.match(textoCoordenadas({ lat: -13.5, lon: -76.0, utm: [390000.04, 8505000.0] }), /^E .*390.* · N .*8.*505.*000$/);
  assert.equal(textoCoordenadas(null), '—');
});

test('017:RF-124: la consulta del mapa lleva el proyecto y cada alimentador, codificados', async () => {
  const { consultaMapa, mapaCargas } = await cargar('../src/api/mapaCargas.ts');
  assert.equal(consultaMapa('20261109 CA101&X', ['CA101', '', 'CHN102']),
    'project=20261109+CA101%26X&alimentador=CA101&alimentador=CHN102');
  assert.equal(mapaCargas.paginaUrl('w 1', 'P'), '/api/workspaces/w%201/mapa-cargas/pagina?project=P');
});
