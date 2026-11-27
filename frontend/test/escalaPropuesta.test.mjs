// 039:RF-27: el alimentador que mide más que la barra de su SET lleva un aviso con su botón de corrección.
// LL202, 27-11: 9 296 kW con la barra de Llipata en 3 139 kW; su hoja estaba en décimas de kW.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const pantalla = readFileSync(fileURLToPath(new URL('../src/features/powerfactory/DemandaMedida.tsx', import.meta.url)), 'utf8');

test('039:RF-27 la fila de la máxima muestra la escala propuesta y la registra con un botón', () => {
  assert.match(pantalla, /\{r\.escala_propuesta\?\.factor && <EscalaPropuesta wsId=\{ws\.id\} r=\{r\}/);
  assert.match(pantalla, /api\.demandaCorreccionCabecera\(wsId, \{ medidor: r\.medidor, factor: e\.factor!/);
  assert.match(pantalla, /Corregir ×\{e\.factor\}\{e\.absoluto \? ' y valor absoluto' : ''\}/);
});
