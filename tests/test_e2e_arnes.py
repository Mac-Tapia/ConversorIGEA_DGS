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
