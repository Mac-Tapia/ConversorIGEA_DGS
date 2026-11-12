import assert from 'node:assert/strict';
import test from 'node:test';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 006:RF-45 (2026-11-12): las gráficas son SVG con viewBox que se escalan al ancho de su caja; un texto de 12 unidades
// medía unos 26 px en una pantalla ancha, el doble que el título. Toda gráfica con etiquetas usa useLetraFija.
const SRC = fileURLToPath(new URL('../src/', import.meta.url));
const tsx = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? tsx(join(dir, e.name))
  : e.name.endsWith('.tsx') ? [join(dir, e.name)] : []));

test('006:RF-45 la letra de las etiquetas se compensa con la escala de la gráfica', () => {
  const css = readFileSync(join(SRC, 'shared', 'styles.css'), 'utf8');
  assert.match(css, /\.curva-texto\s*\{[^}]*font-size:\s*calc\([\d.]+px \* var\(--escala, 1\)\)/);
  const comun = readFileSync(join(SRC, 'shared', 'graficos.ts'), 'utf8');
  assert.match(comun, /export function useLetraFija/);
  assert.match(comun, /ResizeObserver/);
});

test('006:RF-45 toda gráfica con etiquetas usa useLetraFija en cada uno de sus svg', () => {
  const con = tsx(SRC).filter((f) => readFileSync(f, 'utf8').includes('curva-texto'));
  assert.ok(con.length >= 3, `se esperaban al menos 3 gráficas, hay ${con.length}`);
  for (const f of con) {
    const texto = readFileSync(f, 'utf8');
    const svgs = (texto.match(/<svg\b/g) ?? []).length;
    const ajustados = (texto.match(/style=\{estiloLetra\}/g) ?? []).length;
    assert.equal(ajustados, svgs, `${f}: ${svgs} svg y ${ajustados} con la letra fija`);
  }
});