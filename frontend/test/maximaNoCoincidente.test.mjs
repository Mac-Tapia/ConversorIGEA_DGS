import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 086:RF-126 (amplía 028:RF-27, RF-28): «Instante de la calibración» ofrece también la máxima de cada alimentador (no
// coincidente), con dos alimentadores, en una SET o en un sistema eléctrico; el valor por defecto de cada análisis no cambia
// y, elegida, la web dice la fecha y hora de cada uno y avisa, sin bloquear, de que no ocurrieron juntas.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const FUENTE = readFileSync(join(FRONT, 'src', 'features', 'powerfactory', 'DemandaMedida.tsx'), 'utf8');

const AMBITO = readFileSync(join(FRONT, 'src', 'features', 'powerfactory', 'ambitoMaxima.ts'), 'utf8');

test('086:RF-126, RF-140 la máxima de cada alimentador se elige en el ámbito, con SET y sistema; el instante no la repite', () => {
  assert.match(AMBITO, /\{ valor: 'alimentadores:propia', rotulo: 'Alimentadores: la máxima de cada uno \(no coincidente\)' \}/);
  assert.match(AMBITO, /\{ valor: 'set:propia',/);
  assert.match(AMBITO, /\{ valor: 'sistema:propia',/);
  assert.doesNotMatch(FUENTE, /<option value="propia">/, 'el instante repite la no coincidente del ámbito (RF-140)');
  assert.match(FUENTE, /\(instantes\.length > 1 \|\| \(deBarra && alimentadoresBuscados > 1\)\) && \(/,
    'por SET o por sistema el selector no sale');
});

test('086:RF-126 la máxima de cada uno pide sin barra, sin sistema y sin coincidente; el por defecto no cambia', () => {
  assert.match(FUENTE, /const comun = !instante && !propia;/);
  assert.match(FUENTE, /por_barra: porBarra && comun,/);
  assert.match(FUENTE, /sistema_60kv: tipoAnalisis === 'sistema' && comun,/);
  assert.match(FUENTE, /coincidente: !porBarra && comun && feeders\.length > 1,/);
  // El por defecto sigue siendo el del análisis: la coincidente, la barra de la SET o el sistema eléctrico (RF-140: en el
  // módulo del ámbito, que también da el de la no coincidente).
  assert.match(AMBITO, /a\.tipo === 'sistema' \? `Máxima coincidente del sistema eléctrico\$\{enMes\}`/);
  assert.match(AMBITO, /a\.tipo === 'set' \? `Máxima de la barra de su SET\$\{enMes\}`/);
  assert.match(AMBITO, /: `Máxima coincidente de los seleccionados\$\{enMes\}`;/);
  assert.match(FUENTE, /maxima\('', ambito\.noCoincidente\)\)\}>/, 'el por defecto del instante no sigue al ámbito');
});

test('086:RF-126 elegida, la web dice la fecha y hora de cada alimentador y avisa de que no ocurrieron juntas', () => {
  assert.match(FUENTE, /instantes\.map\(\(x\) => `\$\{x\.alimentador\} el \$\{x\.fecha\}`\)\.join\('; '\)/);
  assert.match(FUENTE, /Esos instantes no ocurrieron juntos/);
  assert.doesNotMatch(FUENTE, /alimentador\(es\)|instante\(s\)/);
});
