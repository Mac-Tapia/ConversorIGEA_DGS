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

test('086:RF-126 el selector ofrece la máxima de cada alimentador y sale también en una SET o en un sistema', () => {
  assert.match(FUENTE, /<option value="propia">Máxima de cada alimentador \(no coincidente\)<\/option>/,
    'falta la opción de la máxima de cada alimentador');
  assert.match(FUENTE, /\(instantes\.length > 1 \|\| \(deBarra && alimentadoresBuscados > 1\)\) && \(/,
    'por SET o por sistema el selector no sale');
});

test('086:RF-126 la máxima de cada uno pide sin barra, sin sistema y sin coincidente; el por defecto no cambia', () => {
  assert.match(FUENTE, /const comun = !instante && !propia;/);
  assert.match(FUENTE, /por_barra: porBarra && comun,/);
  assert.match(FUENTE, /sistema_60kv: tipoAnalisis === 'sistema' && comun,/);
  assert.match(FUENTE, /coincidente: !porBarra && comun && feeders\.length > 1,/);
  // El por defecto sigue siendo el del análisis: la coincidente, la barra de la SET o el sistema eléctrico.
  assert.match(FUENTE, /tipoAnalisis === 'sistema' \? 'Máxima coincidente del sistema eléctrico'/);
  assert.match(FUENTE, /tipoAnalisis === 'set' \? 'Máxima de la barra de su SET'/);
  assert.match(FUENTE, /: 'Máxima coincidente de los seleccionados'\}/);
});

test('086:RF-126 elegida, la web dice la fecha y hora de cada alimentador y avisa de que no ocurrieron juntas', () => {
  assert.match(FUENTE, /instantes\.map\(\(x\) => `\$\{x\.alimentador\} el \$\{x\.fecha\}`\)\.join\('; '\)/);
  assert.match(FUENTE, /Esos instantes no ocurrieron juntos/);
  assert.doesNotMatch(FUENTE, /alimentador\(es\)|instante\(s\)/);
});
