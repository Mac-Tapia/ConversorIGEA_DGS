import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

/**
 * Plan Maestro V1, F-11 (spec 086): WCAG 2.2 AA de la web sin navegador. Teclado de las pestañas, de los grupos de
 * opciones y del separador del Registro; semántica ARIA de las pestañas; contraste de los tokens del tema claro y
 * del oscuro, y tamaño mínimo de los objetivos. Los recorridos en navegador con axe son los E2E (frontend/test/e2e).
 */
async function cargar() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { PestanasModulos, PanelPestana, idPestana, idPanel } from './src/app/Pestanas';
    export { indicePorTecla, alturaPorTecla, alturaAlPulsar, REGISTRO_MIN, REGISTRO_INICIAL } from './src/app/teclado';
    export { idPestana, idPanel };
    export const pestanas = (props) => renderToStaticMarkup(createElement(PestanasModulos, { onElegir: () => undefined, ...props }));
    export const panel = (props) => renderToStaticMarkup(createElement(PanelPestana, props, 'contenido'));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

const leer = (ruta) => readFileSync(new URL(ruta, import.meta.url), 'utf8');

test('F-11 las flechas recorren las pestañas con vuelta, Inicio y Fin van a los extremos y ↑ ↓ no se capturan', async () => {
  const { indicePorTecla } = await cargar();
  assert.equal(indicePorTecla(4, 0, 'ArrowRight'), 1);
  assert.equal(indicePorTecla(4, 3, 'ArrowRight'), 0, 'de la última vuelve a la primera');
  assert.equal(indicePorTecla(4, 0, 'ArrowLeft'), 3, 'de la primera va a la última');
  assert.equal(indicePorTecla(4, 2, 'Home'), 0);
  assert.equal(indicePorTecla(4, 1, 'End'), 3);
  assert.equal(indicePorTecla(4, 1, 'ArrowDown'), null, 'en horizontal la página sigue desplazándose');
  assert.equal(indicePorTecla(4, 1, 'Tab'), null);
  // Grupos de opciones: las cuatro flechas.
  assert.equal(indicePorTecla(3, 2, 'ArrowDown', true), 0);
  assert.equal(indicePorTecla(3, 0, 'ArrowUp', true), 2);
});

test('F-11 casos límite del teclado: sin elementos no hay destino y un índice fuera de rango parte del primero', async () => {
  const { indicePorTecla } = await cargar();
  assert.equal(indicePorTecla(0, 0, 'ArrowRight'), null);
  assert.equal(indicePorTecla(-1, 0, 'Home'), null);
  assert.equal(indicePorTecla(Number.NaN, 0, 'End'), null);
  assert.equal(indicePorTecla(3, 7, 'ArrowRight'), 1);
  assert.equal(indicePorTecla(3, -1, 'ArrowLeft'), 2);
  assert.equal(indicePorTecla(1, 0, 'ArrowRight'), 0, 'con una sola pestaña se queda en ella');
});

test('F-11 el separador del Registro se mueve con el teclado dentro de sus límites (2.1.1)', async () => {
  const { alturaPorTecla, REGISTRO_MIN } = await cargar();
  assert.equal(alturaPorTecla(220, 'ArrowUp', 600), 240, 'subir el borde agranda el Registro');
  assert.equal(alturaPorTecla(220, 'ArrowDown', 600), 200);
  assert.equal(alturaPorTecla(220, 'PageUp', 600), 320);
  assert.equal(alturaPorTecla(220, 'PageDown', 600), 120);
  assert.equal(alturaPorTecla(90, 'PageDown', 600), REGISTRO_MIN, 'no baja del mínimo');
  assert.equal(alturaPorTecla(590, 'PageUp', 600), 600, 'no pasa del tope');
  assert.equal(alturaPorTecla(220, 'Home', 600), REGISTRO_MIN);
  assert.equal(alturaPorTecla(220, 'End', 600), 600);
  assert.equal(alturaPorTecla(220, 'Enter', 600), null);
  // Una ventana muy baja: el tope nunca queda por debajo del mínimo.
  assert.equal(alturaPorTecla(80, 'End', 10), REGISTRO_MIN);
});

test('F-11 una pulsación sin arrastrar pliega el Registro y la siguiente lo devuelve (2.5.7)', async () => {
  const { alturaAlPulsar, REGISTRO_MIN, REGISTRO_INICIAL } = await cargar();
  assert.equal(alturaAlPulsar(300, null), REGISTRO_MIN);
  assert.equal(alturaAlPulsar(REGISTRO_MIN, 300), 300, 'vuelve a la altura de antes');
  assert.equal(alturaAlPulsar(REGISTRO_MIN, null), REGISTRO_INICIAL, 'sin altura previa, la inicial');
  assert.equal(alturaAlPulsar(REGISTRO_MIN, REGISTRO_MIN), REGISTRO_INICIAL);
});

test('F-11 las pestañas tienen nombre, un solo punto de tabulación y aria-controls solo hacia paneles que existen', async () => {
  const { pestanas, idPestana, idPanel } = await cargar();
  const lista = [{ id: 'a', etiqueta: 'Uno' }, { id: 'b', etiqueta: 'Dos', avisos: 2 }, { id: 'c', etiqueta: 'Tres' }];
  const html = pestanas({ pestanas: lista, actual: 'b', montadas: new Set(['a', 'b']) });
  assert.match(html, /role="tablist" aria-label="Módulos"/);
  assert.equal((html.match(/role="tab"/g) ?? []).length, 3);
  assert.equal((html.match(/tabindex="0"/g) ?? []).length, 1, 'solo la elegida está en el orden de tabulación');
  assert.equal((html.match(/tabindex="-1"/g) ?? []).length, 2);
  assert.equal((html.match(/aria-selected="true"/g) ?? []).length, 1);
  assert.match(html, new RegExp(`id="${idPestana('b')}" aria-selected="true" aria-controls="${idPanel('b')}" tabindex="0"`));
  assert.match(html, new RegExp(`aria-controls="${idPanel('a')}"`));
  assert.ok(!html.includes(`aria-controls="${idPanel('c')}"`), 'la que nunca se abrió no tiene panel: sin aria-controls');
  // 1.4.1: el aviso se lee como texto, no solo como color.
  assert.match(html, /2 avisos<\/span>/);
});

test('F-11 sin pestañas no se pinta ninguna y el panel queda enlazado con la suya', async () => {
  const { pestanas, panel, idPestana, idPanel } = await cargar();
  const vacia = pestanas({ pestanas: [], actual: '', montadas: new Set() });
  assert.ok(!vacia.includes('role="tab"'));
  const abierto = panel({ id: 'x', hidden: false });
  assert.match(abierto, new RegExp(`role="tabpanel" id="${idPanel('x')}" aria-labelledby="${idPestana('x')}"`));
  assert.ok(!abierto.includes('hidden'));
  assert.match(panel({ id: 'x', hidden: true }), /hidden=""/);
});

// ------------------------------------------------------------------ contraste (1.4.3 y 1.4.11)

function tokens(bloque) {
  return Object.fromEntries([...bloque.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{6})\b/gi)].map((m) => [m[1], m[2].toLowerCase()]));
}

function temas() {
  const css = leer('../src/shared/styles.css');
  const raiz = css.match(/:root\s*\{([\s\S]*?)\n\}/);
  const oscuro = css.match(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{([\s\S]*?)\n\s*\}/);
  assert.ok(raiz && oscuro, 'styles.css tiene el tema claro en :root y el oscuro en prefers-color-scheme');
  const claro = tokens(raiz[1]);
  return { claro, oscuro: { ...claro, ...tokens(oscuro[1]) } };
}

function luminancia(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

function contraste(a, b) {
  const [x, y] = [luminancia(a), luminancia(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

test('F-11 el cálculo de contraste da los valores de referencia de WCAG', () => {
  assert.equal(contraste('#000000', '#ffffff').toFixed(1), '21.0');
  assert.equal(contraste('#ffffff', '#ffffff').toFixed(1), '1.0');
  assert.equal(contraste('#767676', '#ffffff').toFixed(2), '4.54');
});

// Texto normal: 4,5:1 (1.4.3). Borde de un campo, estado de un interruptor y foco: 3:1 (1.4.11).
const TEXTO = [
  ['text', 'bg'], ['text', 'surface'], ['muted', 'bg'], ['muted', 'surface'], ['muted', 'surface-2'],
  ['primary', 'surface'], ['primary', 'bg'], ['primary', 'primary-soft'], ['primary-ink', 'primary'],
  ['pf-ink', 'pf'], ['pf', 'pf-soft'], ['error-ink', 'error'], ['ok', 'ok-soft'], ['warn', 'warn-soft'],
  ['error', 'error-soft'], ['info', 'info-soft'], ['ok', 'surface'], ['warn', 'surface'], ['error', 'surface'],
];
const CONTROL = [['border-control', 'surface'], ['border-control', 'surface-2'], ['border-control', 'bg'],
  ['primary', 'surface'], ['primary', 'surface-2']];

for (const tema of ['claro', 'oscuro']) {
  test(`F-11 contraste AA de los tokens del tema ${tema}`, () => {
    const t = temas()[tema];
    const malos = [];
    for (const [pares, minimo] of [[TEXTO, 4.5], [CONTROL, 3]]) {
      for (const [a, b] of pares) {
        assert.ok(t[a] && t[b], `falta el token --${!t[a] ? a : b} en el tema ${tema}`);
        const r = contraste(t[a], t[b]);
        if (r < minimo) malos.push(`--${a} sobre --${b}: ${r.toFixed(2)} < ${minimo}`);
      }
    }
    assert.deepEqual(malos, []);
  });
}

test('F-11 los botones de color usan su token de tinta, nunca un blanco fijo que en oscuro no contrasta', () => {
  const css = leer('../src/shared/styles.css');
  for (const clase of ['btn-primary', 'btn-pf', 'btn-danger', 'chip.on']) {
    const regla = css.match(new RegExp(`\\.${clase.replace('.', '\\.')} \\{([^}]*)\\}`));
    assert.ok(regla, clase);
    assert.match(regla[1], /color: var\(--[a-z]+-ink\)/, `${clase}: ${regla[1]}`);
  }
});

test('F-11 foco visible en todo lo que lo recibe y objetivos de al menos 24 px (2.4.7 y 2.5.8)', () => {
  const css = leer('../src/shared/styles.css');
  const foco = css.match(/([^{}]+)\{\s*outline: 2px solid var\(--primary\); outline-offset: 2px;\s*\}/);
  assert.ok(foco, 'hay una regla de foco común');
  for (const s of ['button', 'a', 'input', 'select', 'textarea', 'summary', '[role="tab"]', '[role="radio"]',
    '[role="separator"]', '[tabindex]']) {
    assert.ok(foco[1].includes(`${s}:focus-visible`), `sin foco visible: ${s}`);
  }
  for (const clase of ['icon-btn', 'toast-close', 'pill-boton', 'toggle', 'chip', 'btn-sm']) {
    const reglas = [...css.matchAll(new RegExp(`(?:^|\\n|,\\s*)\\.${clase}\\s*\\{([^}]*)\\}`, 'g'))].map((m) => m[1]).join(' ');
    assert.match(reglas, /min-height: 24px/, `.${clase} sin min-height de 24 px`);
  }
  assert.match(css, /\.splitter::before \{[^}]*top: -12px; bottom: -6px;/, 'la raya de 6 px se pulsa en 24 px');
});

test('F-11 la página enlaza el teclado, el salto al contenido y el estado de las capacidades con texto', () => {
  const app = leer('../src/app/App.tsx');
  assert.match(app, /useFlechasEnGrupos\(\);/);
  assert.match(app, /<a className="saltar" href="#contenido">/);
  assert.match(app, /<main className="content" id="contenido" tabIndex=\{-1\}>/);
  assert.match(app, /role="separator"[^>]*\n\s*tabIndex=\{0\} aria-valuemin=\{REGISTRO_MIN\}/);
  assert.match(app, /alturaPorTecla\(logHeight, e\.key, alturaMaxima\(\)\)/);
  assert.match(app, /alturaAlPulsar\(logHeight, antesDePlegar\.current\)/);
  assert.match(app, /<span className="sr-only">: \{estado\}<\/span>/);
  assert.ok(!/<Pill tone=\{caps\.\w+ \? 'ok' : 'muted'\}/.test(app), 'ninguna capacidad dice su estado solo con el color');
});

// ---------------------------------------------------------------- MEJ6-A11Y (111 T17): diálogo, notas y monitor

async function cargarMej6() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import * as ui from './src/shared/ui';
    import * as acerca from './src/app/AcercaDe';
    import * as monitor from './src/features/asistente/MonitorAgente';
    const { Modal } = ui;
    // Por el espacio de nombres: sobre el código anterior a MEJ6 falta lo nuevo y la prueba falla por aserción.
    export const enlazarDialogo = ui['enlazarDialogo'];
    export const bloquesMarkdown = acerca['bloquesMarkdown'];
    export const filasLegibles = monitor['filasLegibles'];
    export const sinRutas = monitor['sinRutas'];
    const NotasVersion = acerca['NotasVersion'];
    const DatosLegibles = monitor['DatosLegibles'];
    export const modal = (title) => renderToStaticMarkup(createElement(Modal, { title, onClose: () => undefined }, 'cuerpo'));
    export const dosModales = () => renderToStaticMarkup(createElement('div', null,
      createElement(Modal, { title: 'Uno', onClose: () => undefined }, 'a'),
      createElement(Modal, { title: 'Dos', onClose: () => undefined }, 'b')));
    export const notas = (texto) => renderToStaticMarkup(createElement(NotasVersion, { texto }));
    export const datos = (d) => renderToStaticMarkup(createElement(DatosLegibles, { datos: d }));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic', logLevel: 'silent' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

test('MEJ6 D1 (4.1.2) el diálogo se nombra con su título: aria-labelledby apunta al id del h2', async () => {
  const { modal, dosModales } = await cargarMej6();
  const html = modal('Nuevo espacio de trabajo');
  const ref = html.match(/<dialog[^>]*aria-labelledby="([^"]+)"/);
  assert.ok(ref, `el dialog no tiene aria-labelledby: ${html.slice(0, 160)}`);
  const h2 = html.match(/<h2[^>]*id="([^"]+)"[^>]*>([^<]*)<\/h2>/);
  assert.ok(h2, 'el h2 del título no tiene id');
  assert.equal(h2[1], ref[1], 'aria-labelledby y el id del h2 coinciden');
  assert.equal(h2[2], 'Nuevo espacio de trabajo');
  // Dos diálogos en la misma página no comparten id (useId).
  const ids = [...dosModales().matchAll(/<h2[^>]*id="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(ids.length, 2);
  assert.notEqual(ids[0], ids[1]);
});

test('MEJ6 D2 (2.4.3) al cerrar el diálogo el foco vuelve al elemento que lo abrió, si sigue en la página', async () => {
  const { enlazarDialogo } = await cargarMej6();
  assert.equal(typeof enlazarDialogo, 'function', 'Modal no tiene la función que guarda y devuelve el foco');
  const enfocados = [];
  const boton = { isConnected: true, focus: () => enfocados.push('boton') };
  const dialogo = { open: false, showModal() { this.open = true; } };
  const soltar = enlazarDialogo(dialogo, boton);
  assert.equal(dialogo.open, true, 'se abre como modal');
  assert.deepEqual(enfocados, [], 'al abrir no se toca el foco del que abre');
  soltar();
  assert.deepEqual(enfocados, ['boton'], 'el foco vuelve al botón que lo abrió');
  // Si el que lo abrió ya no está en la página, no se fuerza el foco sobre un nodo suelto.
  const suelto = { isConnected: false, focus: () => enfocados.push('suelto') };
  enlazarDialogo({ open: false, showModal() { this.open = true; } }, suelto)();
  assert.deepEqual(enfocados, ['boton']);
  // Ya abierto y sin elemento activo: ni se reabre ni falla.
  enlazarDialogo({ open: true, showModal() { throw new Error('ya abierto'); } }, null)();
});

test('MEJ6 D3 y M2 las notas de la versión: zona con nombre y alcanzable con Tab, Markdown con formato y escapado', async () => {
  const { notas, bloquesMarkdown } = await cargarMej6();
  assert.equal(typeof bloquesMarkdown, 'function', 'AcercaDe no da formato a las notas');
  const md = '# Notas de la versión\n\n## 1.0.0\n\n- Primera **línea** con `codigo`\n- Segunda\n\nTexto <b>sin</b> marcar.';
  const html = notas(md);
  assert.match(html, /<div[^>]*role="region"/, 'la zona desplazable es una región');
  assert.match(html, /aria-label="Notas de la versión"/);
  assert.match(html, /tabindex="0"/i, 'la zona desplazable entra en el orden del teclado (2.1.1)');
  assert.doesNotMatch(html, /<pre/, 'el Markdown no sale en crudo dentro de un pre');
  assert.doesNotMatch(html, /(^|>)#+ /, 'sin almohadillas a la vista');
  assert.match(html, /<h4[^>]*>1\.0\.0<\/h4>/);
  assert.match(html, /<ul[^>]*><li>Primera <strong>línea<\/strong> con <code>codigo<\/code><\/li><li>Segunda<\/li><\/ul>/);
  assert.doesNotMatch(html, /\*\*/);
  assert.match(html, /Texto &lt;b&gt;sin&lt;\/b&gt; marcar\./, 'el HTML del texto se escapa, nunca se interpreta');
  assert.doesNotMatch(html, /Notas de la versión<\/h4>/, 'el título que repite el de la sección no se duplica');
  assert.equal(bloquesMarkdown('').length, 0);
  assert.match(notas(''), /Sin notas\./);
});

test('MEJ6 M1 el monitor presenta los datos como lista en español, sin claves en inglés ni rutas absolutas', async () => {
  const { datos, filasLegibles, sinRutas } = await cargarMej6();
  assert.equal(typeof filasLegibles, 'function', 'el monitor no tiene la lista legible');
  const trabajo = {
    id: 'j1', kind: 'agente_proyecto', status: 'done', lane: 'engine', cancel_requested: false,
    created_at: 1763600000, finished_at: 1763600100, error: null,
    result: { informe: 'C:\\Usuarios\\alguien\\espacios\\w1\\salida\\informe.docx', rutas: ['/home/x/a.xlsx'] },
  };
  const filas = filasLegibles(trabajo);
  const etiquetas = filas.map((f) => f.etiqueta);
  for (const e of ['Estado', 'Carril', 'Cancelación solicitada', 'Creado', 'Terminado']) assert.ok(etiquetas.includes(e), e);
  assert.ok(!etiquetas.some((e) => /cancel_requested|finished_at|lane|created_at/.test(e)), etiquetas.join(', '));
  assert.equal(filas.find((f) => f.etiqueta === 'Estado').valor, 'Ejecución terminada');
  assert.equal(filas.find((f) => f.etiqueta === 'Cancelación solicitada').valor, 'No');
  assert.ok(!filas.some((f) => f.etiqueta === 'Error'), 'los vacíos no ocupan pantalla');
  assert.ok(!String(filas.find((f) => f.etiqueta === 'Terminado').valor).includes('1763600100'), 'fecha legible, no Unix');
  const html = datos(trabajo);
  assert.match(html, /<dl/);
  assert.match(html, /informe\.docx/);
  assert.doesNotMatch(html, /Usuarios|\/home\/x|C:\\/, 'ninguna ruta absoluta, ni en el detalle técnico');
  assert.match(html, /<details><summary>Detalle técnico<\/summary><pre>/);
  assert.deepEqual(sinRutas({ a: 'D:\\x\\y\\z.json', b: ['\\\\srv\\c\\d.txt', 'texto normal', 'a/b relativa'], c: 3 }),
    { a: 'z.json', b: ['d.txt', 'texto normal', 'a/b relativa'], c: 3 });
});

test('MEJ6 M1 el monitor ya no pinta JSON en crudo fuera del detalle técnico', () => {
  const t = leer('../src/features/asistente/MonitorAgente.tsx');
  assert.equal((t.match(/<pre>\{JSON\.stringify\((?!sinRutas\()/g) ?? []).length, 0, 'cada JSON pasa por DatosLegibles, sin rutas');
  assert.ok((t.match(/<DatosLegibles /g) ?? []).length >= 4, 'las cuatro vistas de datos usan la lista legible');
});
