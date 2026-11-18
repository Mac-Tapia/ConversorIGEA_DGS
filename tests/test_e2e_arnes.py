"""Spec 111, T1: el arnés e2e del frontend existe, es solo de desarrollo y no sale a la red.

Estas pruebas no abren ningún navegador ni arrancan la web: leen el código del arnés. El recorrido en navegador real lo
corre ``npx playwright test -c e2e/playwright.config.ts`` desde ``frontend/`` (111:RF-16), fuera de la suite de Python.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / 'frontend'
E2E = FRONT / 'e2e'
HERRAMIENTAS_DEL_NAVEGADOR = ('@playwright/test', 'playwright', 'playwright-core', '@axe-core/playwright', 'axe-core')


def _texto(nombre: str) -> str:
    ruta = E2E / nombre
    assert ruta.is_file(), f'falta frontend/e2e/{nombre}'
    return ruta.read_text(encoding='utf-8')


def _componentes_de_la_entrega() -> set[str]:
    """Los paquetes del front que entran en la entrega del cliente, según ``tools/construir_candidato.py``."""
    spec = importlib.util.spec_from_file_location('construir_candidato_e2e', RAIZ / 'tools' / 'construir_candidato.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return {c['name'] for c in modulo._componentes_del_front(RAIZ)}


def test_111_rf16_un_solo_playwright_de_desarrollo_y_fuera_de_la_entrega():
    """111:RF-16 — Playwright y axe son herramientas de desarrollo: una sola declaración, la de T0c en las
    ``devDependencies`` de ``frontend/package.json`` con versión exacta (sin un paquete aparte en ``frontend/e2e``), nunca
    como dependencia de ejecución, marcadas ``dev`` en el lock y fuera de lo que se entrega al cliente."""
    assert not (E2E / 'package.json').exists(), 'frontend/e2e no es un paquete propio: usa la dependencia de la web'
    web = json.loads((FRONT / 'package.json').read_text(encoding='utf-8'))
    dev = web.get('devDependencies', {})
    for nombre in ('@playwright/test', '@axe-core/playwright'):
        assert re.fullmatch(r'\d+\.\d+\.\d+', dev.get(nombre, '')), f'{nombre}: dependencia de desarrollo con versión exacta'
        assert nombre not in web.get('dependencies', {}), f'{nombre} no es una dependencia de ejecución de la web'
    lock = json.loads((FRONT / 'package-lock.json').read_text(encoding='utf-8'))['packages']
    for nombre in HERRAMIENTAS_DEL_NAVEGADOR:
        fila = lock.get(f'node_modules/{nombre}')
        assert fila is None or fila.get('dev'), f'{nombre}: el lock no lo marca de desarrollo'
    entregados = _componentes_de_la_entrega()
    assert entregados, 'la entrega del front no lista ningún paquete: la comprobación dejó de servir'
    assert not entregados & set(HERRAMIENTAS_DEL_NAVEGADOR), f'en la entrega del cliente: {entregados & set(HERRAMIENTAS_DEL_NAVEGADOR)}'


def test_111_rf16_la_configuracion_arranca_la_web_de_prueba_y_corre_en_claro_y_oscuro():
    """111:RF-16 — la configuración prepara la web con ``preparar.mjs`` y corre cada recorrido en los dos modos."""
    config = _texto('playwright.config.ts')
    assert re.search(r"globalSetup:\s*['\"]\./preparar\.mjs['\"]", config), config
    assert "colorScheme: 'light'" in config and "colorScheme: 'dark'" in config
    assert re.search(r'workers:\s*1\b', config), 'una sola web de prueba: los recorridos van en serie'


def test_111_rf16_preparar_usa_un_espacio_sintetico_sorteado_y_dice_la_semilla():
    """111:RF-16 — la web de prueba carga un export sintético con semilla sorteada (o la dada) y la dice."""
    preparar = _texto('preparar.mjs')
    assert 'CSG_E2E_SEMILLA' in preparar and 'randomInt' in preparar
    assert re.search(r'console\.log\([^)]*semilla', preparar), 'la semilla tiene que salir en el registro'
    assert 'web_de_prueba.py' in preparar
    web = _texto('web_de_prueba.py')
    assert 'synthetic_export' in web and 'ExportSpec(' in web and 'seed=' in web
    assert 'EXIGIR_SEGURIDAD' in web, 'la web de prueba corre con la seguridad real'
    for var in ('CSG_RUNTIME_HOME', 'CSG_CACHE_HOME', 'CSG_WEB_SESIONES'):
        assert var in web, f'{var}: la web de prueba no toca el perfil del usuario'
    # 111:RF-16 (18-11): «Cargar perfil» escribía el de la prueba en config/perfil_empresa.json del checkout y la corrida
    # siguiente estudiaba con sus umbrales: el perfil de la empresa también va a la carpeta de la prueba.
    assert re.search(r'os\.environ\["CSG_PERFIL_EMPRESA"\]\s*=\s*str\(tmp\s*/', web), \
        'la web de prueba deja el perfil de la empresa en el checkout'
    assert "CUDA_VISIBLE_DEVICES" in web


def test_111_rf16_ningun_recorrido_sale_a_la_red():
    """111:RF-16 — cada recorrido usa ``sin_red.ts``: lo local sigue, las teselas se sirven en local y todo lo demás
    se aborta y hace fallar la prueba."""
    sin_red = _texto('sin_red.ts')
    assert 'context.route' in sin_red and '.fulfill(' in sin_red and '.abort(' in sin_red
    assert re.search(r'expect\(\s*abortadas', sin_red), 'una petición abortada tiene que hacer fallar la prueba'
    specs = sorted(E2E.glob('*.spec.ts'))
    assert specs, 'sin recorridos'
    for spec in specs:
        texto = spec.read_text(encoding='utf-8')
        assert re.search(r"from '\./sin_red'", texto), f'{spec.name} no usa sin_red.ts'
        assert "from '@playwright/test'" not in texto, f'{spec.name} salta la guarda de red'


def test_111_rf16_la_linea_base_lee_las_pestanas_de_la_web_y_no_una_lista_fija():
    """111:RF-16 — ``linea_base.spec.ts`` toma las pestañas de ``TABS`` en ``App.tsx``: una pestaña nueva entra sola
    y una que desaparece hace fallar el recorrido; las acciones vistas se comparan con las fijadas."""
    linea = _texto('linea_base.spec.ts')
    assert 'src/app/App.tsx' in linea and 'TABS' in linea
    assert '111:RF-16' in linea
    assert 'linea_base_acciones.json' in linea and 'CSG_E2E_FIJAR_LINEA_BASE' in linea
    etiquetas = re.findall(r"label: '([^']+)'", (FRONT / 'src/app/App.tsx').read_text(encoding='utf-8'))
    assert etiquetas and not any(e in linea for e in etiquetas), 'las pestañas no se copian a mano en el recorrido'


def test_111_rf16_la_web_de_prueba_no_arranca_nada_al_importarse():
    """111:RF-16: la conversión abre procesos «spawn» en Windows y cada hijo reimporta ``web_de_prueba.py``. Si el
    arranque (sesión, web y espacio) estuviera a nivel de módulo, el hijo crearía otra sesión y la del padre daría 401,
    y la conversión fallaría al arrancar. En el módulo solo hay importaciones, funciones y la guarda ``__main__``."""
    import ast

    arbol = ast.parse(_texto('web_de_prueba.py'))
    permitidos = (ast.Import, ast.ImportFrom, ast.FunctionDef)
    sueltos = [n.lineno for n in arbol.body[1:] if not isinstance(n, permitidos)
               and not (isinstance(n, ast.If) and "__name__" in ast.unparse(n.test))]
    assert not sueltos, f'web_de_prueba.py ejecuta código al importarse en las líneas {sueltos}'


def test_070_rf78_los_guiones_de_playwright_comprueban_que_no_hay_citas_a_la_vista():
    """070:RF-78 (070 T15) — los recorridos en navegador real llaman a ``comprobar_sin_citas``: la línea base en cada
    pestaña, y cada recorrido de ``test/e2e`` en cada estado (lo llama ``revisarAxe``, que todos usan)."""
    comun = (FRONT / 'test' / 'e2e' / 'comun.mjs').read_text(encoding='utf-8')
    assert 'export async function comprobar_sin_citas' in comun
    cuerpo_axe = comun.split('export async function revisarAxe', 1)[1].split('\n}\n', 1)[0]
    assert 'comprobar_sin_citas(' in cuerpo_axe
    for guion in sorted((FRONT / 'test' / 'e2e').glob('*.e2e.mjs')):
        texto = guion.read_text(encoding='utf-8')
        if ('test.skip(' in texto or 'test.fixme(' in texto) and 'revisarAxe' not in texto:  # pendiente a propósito
            continue
        assert 'revisarAxe(' in texto or 'comprobar_sin_citas(' in texto, guion.name
    assert 'comprobar_sin_citas(' in _texto('linea_base.spec.ts')
    assert 'export async function comprobar_sin_citas' in _texto('sin_red.ts')


# ---------------------------------------------------------------- frontend/test/e2e: web aislada y sin omisiones
E2E_PRUEBA = FRONT / 'test' / 'e2e'


def test_086_rf107_la_web_de_los_recorridos_guarda_sus_espacios_en_su_temporal():
    """086:RF-107 — la web de los recorridos fija su raíz de ejecución y la de los espacios en su carpeta temporal. Con
    solo LOCALAPPDATA, los espacios iban a <checkout>/../.convertersmartgrid-runtime/<huella>/data/web (runtime_paths),
    junto a los del operador; lo vio el recorrido del VAD (108 T30) el 17-11."""
    from convertersmartgrid.dominio.runtime_paths import raiz_datos_web, rutas_runtime

    config = (E2E_PRUEBA / 'playwright.config.mjs').read_text(encoding='utf-8')
    cuerpo = config.split('function servidor(', 1)[1]
    for var, sub in (('CSG_RUNTIME_HOME', 'runtime'), ('CSG_WEB_DATA', 'web'), ('CSG_WEB_SESIONES', 'sesiones')):
        assert re.search(rf"{var}: join\(carpetaDe, '{sub}'\)", cuerpo), f'{var} fuera de la carpeta temporal de la web'
    assert 'LOCALAPPDATA: carpetaDe' in cuerpo
    # Las dos variables siguen decidiendo de verdad: si dejaran de leerse, la configuración aislaría en vano.
    otra = RAIZ.parent / 'csg_e2e_prueba'
    assert rutas_runtime(environ={'CSG_RUNTIME_HOME': str(otra / 'runtime')}).runtime == (otra / 'runtime').resolve()
    import os
    previo = os.environ.get('CSG_WEB_DATA')
    os.environ['CSG_WEB_DATA'] = str(otra / 'web')
    try:
        assert raiz_datos_web() == otra / 'web', 'CSG_WEB_DATA ya no decide dónde van los espacios'
    finally:
        if previo is None:
            os.environ.pop('CSG_WEB_DATA', None)
        else:
            os.environ['CSG_WEB_DATA'] = previo


_GUION_REPORTERO = r"""
const { default: Rep } = await import(process.argv[1]);
const t = (titulo, desenlace, notas = []) => ({ outcome: () => desenlace, titlePath: () => ['', titulo],
  annotations: notas.map((type) => ({ type })) });
const correr = (casos, fin = 'passed') => {
  const r = new Rep();
  for (const [c, s] of casos) r.onTestEnd(c, { status: s });
  return r.onEnd({ status: fin }) ?? null;
};
console.log(JSON.stringify({
  todos_pasan: correr([[t('F01', 'expected'), 'passed']]),
  fixme: correr([[t('F01', 'expected'), 'passed'], [t('F02', 'skipped', ['fixme']), 'skipped']]),
  skip: correr([[t('F03', 'skipped', ['skip']), 'skipped']]),
  inestable: correr([[t('F04', 'flaky'), 'passed']]),
  interrumpida: correr([[t('F05', 'expected'), 'passed']], 'interrupted'),
}));
"""


def test_086_rf107_un_recorrido_omitido_inestable_o_en_fixme_hace_fallar_la_corrida():
    """086:RF-107 — sin_omitidas.mjs deja la corrida en fallo con un recorrido omitido (skip o fixme), inestable o
    interrumpido, y la deja pasar cuando todos pasan: se siembra cada caso en el reportero de verdad, con node."""
    import shutil
    import subprocess

    node = shutil.which('node')
    assert node, 'hace falta node para comprobar el reportero de los recorridos'
    r = subprocess.run([node, '--input-type=module', '-e', _GUION_REPORTERO, '--',
                        (E2E_PRUEBA / 'sin_omitidas.mjs').as_uri()],
                       capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res['todos_pasan'] is None, res
    for caso in ('fixme', 'skip', 'inestable', 'interrumpida'):
        assert res[caso] == {'status': 'failed'}, (caso, res)
    assert 'F02' in r.stderr and 'fixme' in r.stderr, 'el reportero dice qué recorrido no pasó y por qué'


def test_086_rf107_un_recorrido_que_no_puede_correr_no_se_recoge_con_su_motivo():
    """086:RF-107 — la configuración usa el reportero, y todo recorrido con test.skip o test.fixme queda en testIgnore
    con su motivo escrito encima; ninguno se recoge para salir omitido."""
    config = (E2E_PRUEBA / 'playwright.config.mjs').read_text(encoding='utf-8')
    assert "['./sin_omitidas.mjs']" in config, 'la configuración no usa sin_omitidas.mjs'
    # Los dos arneses de recorridos (test/e2e y el de la 111 en e2e/) llevan el mismo reportero.
    assert "['../test/e2e/sin_omitidas.mjs']" in _texto('playwright.config.ts'), 'el arnés de la 111 no usa sin_omitidas.mjs'
    for spec in sorted(E2E.glob('*.spec.ts')):
        texto = spec.read_text(encoding='utf-8')
        assert 'test.skip(' not in texto and 'test.fixme(' not in texto, f'{spec.name}: omitido en el arnés de la 111'
    ignorados = re.search(r'testIgnore:\s*\[([^\]]*)\]', config)
    patrones = [re.compile(p) for p in re.findall(r'/(.+?)/', ignorados.group(1))] if ignorados else []
    for guion in sorted(E2E_PRUEBA.glob('*.e2e.mjs')):
        texto = guion.read_text(encoding='utf-8')
        if 'test.skip(' in texto or 'test.fixme(' in texto:
            assert any(p.search(guion.name) for p in patrones), f'{guion.name} tiene skip o fixme y se recoge'
    if ignorados:
        antes = config[:ignorados.start()].rstrip().splitlines()[-1]
        assert antes.strip().startswith('//'), 'testIgnore sin su motivo escrito encima'


def test_111_rf16_el_recorrido_del_plano_cubre_la_t16_y_sustituye_al_f02_vacio():
    """111:RF-16, 086:RF-107 (111 T16) — `e2e/plano.spec.ts` recorre maniobra → estudio con el motor abierto → resultados
    sobre el plano y la comparación de dos casos, con el teclado, axe y las huellas de los vértices; F02 deja de ser un
    «test.fixme» vacío."""
    ruta = E2E / 'plano.spec.ts'
    assert ruta.is_file(), 'falta e2e/plano.spec.ts (111 T16)'
    texto = ruta.read_text(encoding='utf-8')
    for pieza in ('Cambiar estado', "name: 'Estudiar'", 'Caso A', 'Caso B', "name: 'Comparar'", 'huellaDeVertices',
                  'AxeBuilder', 'tabularHasta', "keyboard.press('Enter')", "from './sin_red'", 'CSG_E2E_SEMILLA'):
        assert pieza in texto, f'plano.spec.ts sin «{pieza}»'
    assert not (FRONT / 'test' / 'e2e' / 'f02_plano.e2e.mjs').exists(), 'el F02 vacío sigue en test/e2e'
