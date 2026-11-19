// 102:RF-31 (auditoría del 18-11, H06): un solo punto de entrada para los dos arneses de navegador. Corre los dos
// aunque el primero falle, para que la corrida diga el estado de los dos, y sale en rojo si falla cualquiera. Cada arnés
// conserva su reportero sin_omitidas: un recorrido omitido, en «fixme», inestable o sin correr ya deja el suyo en rojo.
//   npm run e2e:todo
// CSG_E2E_PLAYWRIGHT (solo pruebas): un guion de Node que hace de Playwright, para comprobar este agregado sin navegador.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const FRONT = fileURLToPath(new URL('../../', import.meta.url));
const ARNESES = [
  ['recorridos de la web (test/e2e)', 'test/e2e/playwright.config.mjs'],
  ['plano de la red (e2e)', 'e2e/playwright.config.ts'],
];

function correr(config) {
  const falso = process.env.CSG_E2E_PLAYWRIGHT;
  const [orden, argumentos] = falso
    ? [process.execPath, [falso, 'test', '-c', config]]
    : ['npx', ['playwright', 'test', '-c', config]];
  const r = spawnSync(orden, argumentos, { cwd: FRONT, stdio: 'inherit', shell: !falso && process.platform === 'win32' });
  return r.status ?? 1;
}

const resultados = ARNESES.map(([nombre, config]) => {
  console.log(`\n=== e2e: ${nombre} (${config}) ===`);
  return [nombre, correr(config)];
});
console.log('\n=== e2e: resumen ===');
for (const [nombre, rc] of resultados) console.log(`${rc === 0 ? 'bien ' : 'FALLO'} ${nombre} (código ${rc})`);
process.exit(resultados.every(([, rc]) => rc === 0) ? 0 : 1);
