"""Spec 064: ningún guion conecta con DIgSILENT fuera del arnés (064:RF-1, 064:RF-2, 064:RF-3, 064:RF-8).

La prueba de 019:RF-5 solo buscaba ``GetApplicationExt(`` y dejaba pasar siete guiones que
conectaban con ``GetApplication()`` sin turno, dos de ellos lanzados por la web.
"""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: 064:RF-1: la aceptación nativa puede engancharse a un DIgSILENT abierto a mano y toma el
#: turno con ``tomar_turno``; el arnés es quien conecta.
PERMITIDOS = {'src/convertersmartgrid/pf_arnes.py', 'tools/powerfactory_acceptance.py'}


def _llamadas_directas(fuente: str) -> list[int]:
    """Líneas donde el código llama a ``GetApplication``/``GetApplicationExt`` o lo toma con
    ``getattr``; los comentarios, los docstrings y los textos de ayuda no cuentan."""
    lineas = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Attribute) and nodo.attr in ('GetApplication', 'GetApplicationExt'):
            lineas.append(nodo.lineno)
        elif (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
              and nodo.func.id == 'getattr' and len(nodo.args) >= 2
              and isinstance(nodo.args[1], ast.Constant)
              and str(nodo.args[1].value).startswith('GetApplication')):
            lineas.append(nodo.lineno)
    return sorted(lineas)


def test_ningun_guion_conecta_fuera_del_arnes():
    """064:RF-1, 064:RF-2 — solo ``pf_arnes.conectar`` (y la aceptación nativa) conectan."""
    fuera = []
    for carpeta in ('tools', 'src'):
        for p in sorted((RAIZ / carpeta).rglob('*.py')):
            rel = p.relative_to(RAIZ).as_posix()
            if rel in PERMITIDOS or '__pycache__' in rel:
                continue
            fuera += [f'{rel}:{n}' for n in
                      _llamadas_directas(p.read_text(encoding='utf-8', errors='replace'))]
    assert fuera == [], 'conectan con DIgSILENT sin el arnés: ' + ', '.join(fuera)


def test_la_deteccion_ve_las_tres_formas():
    """064:RF-2 — la llamada directa, la extendida y la tomada con ``getattr``."""
    fuente = ('import powerfactory as pf\n'
              'a = pf.GetApplication()\n'
              'b = pf.GetApplicationExt()\n'
              "c = getattr(pf, 'GetApplicationExt', None)\n"
              '# pf.GetApplication() en un comentario no cuenta\n'
              "d = 'GetApplication en un texto tampoco'\n")
    assert _llamadas_directas(fuente) == [2, 3, 4]


def test_la_web_lanza_la_red_del_sistema_con_el_entorno_de_digsilent(tmp_path, monkeypatch):
    """064:RF-3 — red del sistema, escenario base y datos que faltan llevan ``PF_PYTHON``:
    sin él, ``jobs.run_process`` no cerraba huérfanos ni ponía el límite de arranque."""
    from convertersmartgrid.web import services

    pf_dir = tmp_path / 'pf'
    pf_dir.mkdir()
    interprete = tmp_path / 'python312.exe'
    monkeypatch.setattr(services, '_require_pf', lambda: (pf_dir, interprete))
    monkeypatch.setattr(services, 'crs_origen_exigido', lambda ws: 'EPSG:4326')
    monkeypatch.setattr(services, 'script_inputs', lambda ws: ['--red', 'r.txt'])
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'Proyectos')

    class Ws:
        out_dir = tmp_path / 'salida'

    vistos = []

    class Ctx:
        def log(self, _texto):
            pass

        def run_process(self, cmd, env=None, cwd=None, **_kw):
            vistos.append((cmd, env))
            return 0

    for accion in ('grid', 'base', 'missing-data'):
        services.run_system(Ws(), Ctx(), accion)
    (red, env_red), (base, env_base), (datos, env_datos) = vistos
    assert red[0] == base[0] == str(interprete)
    assert env_red['PF_PYTHON'] == env_base['PF_PYTHON'] == str(pf_dir)
    # ``--solo-datos`` solo audita el export: no pide DIgSILENT ni su intérprete.
    assert '--solo-datos' in datos and (env_datos is None or 'PF_PYTHON' not in env_datos)


def test_el_servidor_atiende_la_operacion_de_la_set_nueva():
    """064:RF-8 — sin él, cada orden de la SET nueva cerraba el servidor y reconectaba."""
    from convertersmartgrid import pf_arnes

    assert 'set_nueva_operacion_pf.py' in pf_arnes.GUIONES_SERVIBLES
