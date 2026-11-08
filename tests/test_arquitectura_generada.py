"""La arquitectura se cataloga sola: módulos, asistente, equipo y ganchos de git (spec 090)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from convertersmartgrid.asistente.equipo import ROLES_LECTURA, ROLES_REVISION, inventario_equipo
from convertersmartgrid.asistente.orquestador import ETAPAS, ETAPAS_CARGA
from convertersmartgrid.asistente.tareas import TAREAS
from convertersmartgrid.edicion import TAREAS_FUERA_DE_ALCANCE
from convertersmartgrid.web.jobs import LANES
from apoyo import cargar_herramienta

RAIZ = Path(__file__).resolve().parents[1]
GA = cargar_herramienta('generar_arquitectura.py')
CATALOGO = RAIZ / GA.SALIDA


class FuenteCon(GA.Fuente):
    """El repositorio real con ficheros de más o de menos, sin tocar el disco."""

    def __init__(self, extra=None, sin=()):
        super().__init__(RAIZ)
        self.extra, self.sin = dict(extra or {}), set(sin)

    def ficheros(self):
        return sorted((set(super().ficheros()) | set(self.extra)) - self.sin)

    def leer(self, ruta):
        return self.extra[ruta] if ruta in self.extra else super().leer(ruta)


@pytest.fixture(scope='module')
def texto():
    return GA.documento(GA.Fuente(RAIZ))


# ---------------------------------------------------------------------- catálogo y cifras
def test_catalogo_al_dia(texto):
    """090:RF-10 — lo escrito es lo que se generaría; si falla, --escribir lo arregla."""
    escrito = CATALOGO.read_bytes().decode('utf-8').replace('\r\n', '\n')
    assert escrito == texto, 'python tools/generar_arquitectura.py --escribir'


def test_catalogo_nombra_cada_fichero_versionado(texto):
    """090:RF-1 — ningún módulo, herramienta ni pieza de la interfaz se queda fuera."""
    filas = {m for m in re.findall(r'^\| `([^`]+)` \|', texto, re.M)}
    mapa = json.loads(GA.Fuente(RAIZ).leer(GA.MAPA))
    bases = {g['base'] + f for g in mapa['grupos'] for f in g['ficheros'] if f in filas}
    faltan = [f for f in GA.Fuente(RAIZ).ficheros() if f.startswith(GA.RAICES) and f not in bases and f not in filas]
    assert not faltan, faltan


def test_cada_fichero_toma_papel_y_capa_de_su_fuente(texto):
    """090:RF-2 — el papel es el del índice y la capa la de pyproject, sin otra copia."""
    fuente = FuenteCon({'CODIGO_FUENTE.md': fuente_indice_con('`src/convertersmartgrid/util.py`', 'Papel de prueba. Y más detalle', '777')})
    linea = next(x for x in GA.documento(fuente).splitlines() if x.startswith('| `util.py` |'))
    assert linea == '| `util.py` | Dom | 777 | Papel de prueba. |'


def fuente_indice_con(ruta, papel, spec):
    texto = GA.Fuente(RAIZ).leer('CODIGO_FUENTE.md')
    return re.sub(rf'^\| {re.escape(ruta)} \|.*$', f'| {ruta} | {papel} | {spec} |', texto, flags=re.M)


def test_fichero_nuevo_sin_subsistema_aparece_y_no_falla():
    """090:RF-3 — un módulo nuevo entra solo, con su docstring si el índice aún no lo trae."""
    nuevo = 'src/convertersmartgrid/modulo_de_prueba_090.py'
    texto = GA.documento(FuenteCon({nuevo: '"""Módulo de prueba."""\n'}))
    assert '### Sin subsistema asignado' in texto
    assert f'| `{nuevo}` | — | — | Módulo de prueba. |' in texto


def test_fichero_retirado_desaparece():
    """090:RF-4 — sale del catálogo aunque el mapa lo siga nombrando."""
    assert '| `vias.py` |' in GA.documento(FuenteCon())
    assert '| `vias.py` |' not in GA.documento(FuenteCon(sin={'src/convertersmartgrid/vias.py'}))


def test_cifras_con_capas_carriles_rutas_y_specs(texto):
    """090:RF-8 — las cifras salen del código, también la deuda de capas."""
    deuda = json.loads((RAIZ / 'docs/implementacion065/deuda_arquitectura.json').read_text(encoding='utf-8'))
    assert f"{len(deuda['excepciones'])} excepciones" in texto
    for carril in LANES:
        assert f'`{carril}`' in texto
    assert re.search(r'\d+ en `web/app\.py`', texto) and '`demanda`' in texto
    n_specs = sum(1 for _ in (RAIZ / 'specs').glob('[0-9][0-9][0-9]-*/spec.md'))
    assert f'{n_specs} specs con' in texto


def test_catalogo_determinista_sin_fechas(texto):
    """090:RF-9 — dos pasadas dan lo mismo, y no hay fecha ni revisión que lo cambie."""
    assert GA.documento(GA.Fuente(RAIZ)) == texto
    assert not re.search(r'\b20\d\d-\d\d-\d\d\b', texto.split('## Ficheros')[0])


def test_comprobar_dice_la_orden(tmp_path, capsys, monkeypatch):
    """090:RF-10 — desactualizado sale con 1 y nombra lo que lo arregla."""
    (tmp_path / 'docs').mkdir()
    (tmp_path / GA.SALIDA).write_text('viejo', encoding='utf-8')
    monkeypatch.setattr(GA, 'documento', lambda _f: 'nuevo\n')
    assert GA.main(['--comprobar', '--raiz', str(tmp_path)]) == 1
    assert '--escribir' in capsys.readouterr().out


# ---------------------------------------------------------------------- el asistente y su equipo
def test_tareas_iguales_al_codigo_real():
    """090:RF-5 — leídas sin importar, dicen lo mismo que el catálogo que corre."""
    leidas = GA.tareas(GA.Fuente(RAIZ).leer(GA.S + 'asistente/tareas.py'))
    assert [t['nombre'] for t in leidas] == list(TAREAS)
    for t in leidas:
        real = TAREAS[t['nombre']]
        assert (t['escribe'], t['modo'], t['funcion'], t['descripcion']) == (real.escribe, real.modo, real.funcion, real.descripcion)
        assert sorted(d['nombre'] for d in t['datos']) == sorted(d.nombre for d in real.datos), t['nombre']
        assert {d['nombre']: d['obligatorio'] for d in t['datos']} == {d.nombre: d.obligatorio for d in real.datos}, t['nombre']


def test_tareas_con_carril_y_edicion_como_el_inventario(texto):
    """090:RF-5 — el carril y la edición son los del gobierno del equipo y de edicion.py."""
    for h in inventario_equipo()['herramientas']:
        nombre = h['herramienta']
        producto = 'no' if nombre in TAREAS_FUERA_DE_ALCANCE else 'sí'
        assert re.search(rf"^\| `{nombre}` \| {h['modo']} \| {'sí' if h['escribe'] else 'no'} \| {h['carril']} \| {producto} \| `{h['funcion']}` \|", texto, re.M), nombre


def test_roles_iguales_al_inventario(texto):
    """090:RF-6 — todos los roles, y solo el operador ejecuta."""
    leidos = GA.roles(GA.Fuente(RAIZ).leer(GA.S + 'asistente/equipo.py'), GA.Fuente(RAIZ).leer(GA.S + 'asistente/revision_roles.py'))
    assert {r['rol'] for r in leidos} == {'operador', *ROLES_REVISION, *ROLES_LECTURA}
    inventario = {r['rol']: r['puede_ejecutar'] for r in inventario_equipo()['roles']}
    for r in leidos:
        assert r['ejecuta'] == inventario.get(r['rol'], False) and r['lee'] == (r['rol'] in ROLES_LECTURA) and r['encargo']
        assert f"| `{r['rol']}` | {'sí' if r['ejecuta'] else 'no'} |" in texto


def test_etapas_y_familias_iguales_al_codigo(texto):
    """090:RF-7 — las etapas de las dos cadenas, las familias y los umbrales."""
    orquestador = GA.Fuente(RAIZ).leer(GA.S + 'asistente/orquestador.py')
    for nombre, reales in (('ETAPAS', ETAPAS), ('ETAPAS_CARGA', ETAPAS_CARGA)):
        leidas = GA.etapas(orquestador, nombre)
        assert [(e['nombre'], e['tarea'], e['opcional'], e['proceso'], e['condicion']) for e in leidas] == \
               [(e.nombre, e.tarea, e.opcional, e.proceso, e.condicion) for e in reales]
    assert '### Etapas de una carga nueva' in texto and '`transformer`' in texto and 'confianza 0.85' in texto


def test_orden_de_familias_se_lee_del_contrato_puro():
    """090:RF-7/12; 002:RF-3: el catálogo usa el dueño canónico, sin importar el producto."""
    fuente = FuenteCon({
        GA.S + 'contratos_aprendizaje.py': 'ORDEN_MODELOS = ("familia_contrato",)\n',
        GA.S + 'training_coordinator.py': 'ORDEN_MODELOS = ("familia_obsoleta",)\n',
    })
    documento = GA.documento(fuente)
    assert 'Orden de entrenamiento: `familia_contrato`.' in documento
    assert 'familia_obsoleta' not in documento


# ---------------------------------------------------------------------- ganchos de punta a punta
def _git(repo, *args, env=None, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8', env=env, check=check)


@pytest.fixture
def repo(tmp_path):
    """Un repositorio con lo mínimo que lee el generador y los ganchos activos."""
    r = tmp_path / 'repo'
    for rel in (*GA.FUENTES, 'tools/generar_arquitectura.py', '.gitattributes'):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RAIZ / rel, r / rel)
    shutil.copytree(RAIZ / '.githooks', r / '.githooks')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['CSG_PYTHON'] = Path(sys.executable).as_posix()
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(r)], check=True, env=env)
    for k, v in (('user.email', 'prueba@ejemplo.invalid'), ('user.name', 'Prueba'), ('core.hooksPath', '.githooks'), ('core.autocrlf', 'false')):
        _git(r, 'config', k, v, env=env)
    _git(r, 'add', '-A', env=env)
    _git(r, 'commit', '-qm', 'base', env=env)
    return r, env


def test_gancho_commit_incluye_el_catalogo(repo):
    """090:RF-11 — un fichero nuevo entra en el catálogo de su mismo commit."""
    r, env = repo
    assert 'generar_arquitectura.py' in _git(r, 'show', f'HEAD:{GA.SALIDA}', env=env).stdout
    (r / 'tools/herramienta_nueva.py').write_text('"""Nueva."""\n', encoding='utf-8')
    _git(r, 'add', 'tools/herramienta_nueva.py', env=env)
    _git(r, 'commit', '-qm', 'nueva', env=env)
    assert 'tools/herramienta_nueva.py' in _git(r, 'show', f'HEAD:{GA.SALIDA}', env=env).stdout
    assert _git(r, 'status', '--porcelain', env=env).stdout == ''


def test_gancho_commit_con_rutas_lee_lo_que_entra(repo):
    """090:RF-12 — lo sin confirmar de otra sesión no entra, y nada queda a medio preparar."""
    r, env = repo
    (r / 'tools/mia.py').write_text('"""Mía."""\n', encoding='utf-8')
    (r / 'tools/ajena.py').write_text('"""Ajena."""\n', encoding='utf-8')
    _git(r, 'add', 'tools/mia.py', 'tools/ajena.py', env=env)
    _git(r, 'commit', '-qm', 'solo la mía', '--', 'tools/mia.py', env=env)
    catalogo = _git(r, 'show', f'HEAD:{GA.SALIDA}', env=env).stdout
    assert 'tools/mia.py' in catalogo and 'tools/ajena.py' not in catalogo
    estado = _git(r, 'status', '--porcelain', '--', GA.SALIDA, env=env).stdout
    assert not estado.startswith(('M', 'A')), estado


def test_gancho_fusion_sin_conflicto_regenera(repo):
    """090:RF-13 — dos ramas que añaden ficheros se funden solas, con los dos en el catálogo."""
    r, env = repo
    _git(r, 'checkout', '-qb', 'otra', env=env)
    (r / 'tools/de_otra.py').write_text('"""Otra."""\n', encoding='utf-8')
    _git(r, 'add', '-A', env=env)
    _git(r, 'commit', '-qm', 'otra', env=env)
    _git(r, 'checkout', '-q', 'main', env=env)
    (r / 'tools/de_main.py').write_text('"""Main."""\n', encoding='utf-8')
    _git(r, 'add', '-A', env=env)
    _git(r, 'commit', '-qm', 'main', env=env)
    _git(r, 'merge', '-q', '--no-edit', 'otra', env=env)
    catalogo = _git(r, 'show', f'HEAD:{GA.SALIDA}', env=env).stdout
    assert 'tools/de_otra.py' in catalogo and 'tools/de_main.py' in catalogo
    assert '<<<<' not in catalogo
    assert catalogo == GA.documento(GA.Fuente(r)).replace('\r\n', '\n')
    padres = _git(r, 'rev-list', '--parents', '-n', '1', 'HEAD', env=env).stdout.split()[1:]
    assert len(padres) == 2 and _git(r, 'log', '-1', '--format=%s', env=env).stdout.startswith('Merge branch')
    assert _git(r, 'status', '--porcelain', env=env).stdout == ''


def test_gancho_con_generador_roto_avisa_y_deja_pasar(repo):
    """090:RF-14 — un documento no para un commit: avisa, y lo detiene la suite."""
    r, env = repo
    (r / 'pyproject.toml').write_text('esto no es toml [', encoding='utf-8')
    _git(r, 'add', '-A', env=env)
    hecho = _git(r, 'commit', '-m', 'rompe', env=env)
    assert 'no se pudo regenerar' in hecho.stderr
    assert _git(r, 'log', '-1', '--format=%s', env=env).stdout.strip() == 'rompe'


# ---------------------------------------------------------------------- el documento que explica
def test_la_arquitectura_enlaza_el_catalogo_sin_sus_cifras():
    """090:RF-15 — las cifras que cambian viven en el catálogo generado."""
    texto = (RAIZ / 'docs/ARQUITECTURA.md').read_text(encoding='utf-8')
    assert '(ARQUITECTURA_CATALOGO.md)' in texto
    cuerpo = texto.split('## Correcciones a versiones anteriores')[0]
    assert not re.search(r'\b\d+ (módulos|rutas|funciones|excepciones)\b', cuerpo)


def test_las_citas_de_los_conjuntos_siguen_en_la_arquitectura():
    """090:RF-16 — ni la 076 ni la 077 se quedan con una frase que ya no está."""
    texto = (RAIZ / 'docs/ARQUITECTURA.md').read_text(encoding='utf-8')
    faltan = []

    def recorrer(nodo):
        if isinstance(nodo, dict):
            if nodo.get('fichero') == 'docs/ARQUITECTURA.md' and nodo.get('ancla') and nodo['ancla'] not in texto:
                faltan.append(nodo['ancla'])
            for v in nodo.values():
                recorrer(v)
        elif isinstance(nodo, list):
            for v in nodo:
                recorrer(v)

    docs = RAIZ / 'docs'
    for f in (*docs.glob('CONJUNTO_*077.json'), docs / 'asistente/preguntas_entregables_huecos.json'):
        recorrer(json.loads(f.read_text(encoding='utf-8')))
    for linea in (docs / 'asistente/preguntas_entregables.jsonl').read_text(encoding='utf-8').splitlines():
        if linea.strip():
            recorrer(json.loads(linea))
    assert not faltan, faltan
