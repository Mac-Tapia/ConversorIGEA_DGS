"""106:RF-17 — durante la suite, ninguna raíz de datos que se deduce del checkout real cae en su output/.

Está en su propio módulo, y no junto a las otras de RF-16 y RF-17, para no pedir el turno de la máquina (106:RF-6):
estas pruebas no usan la tarjeta y no tienen por qué esperar a otra sesión de pytest que la tenga.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


# 106:RF-17 (ampliado el 2026-11-13) — ninguna raíz de datos que se deduce del checkout cae en su output/. En el árbol
# principal, raices_de_datos() daba output/web como raíz «heredada» (19,1 GB, 8 533 ficheros del usuario) y dos pruebas
# de copia_datos la copiaban a tmp hasta vencer su plazo; en un worktree limpio output/web no existe y pasaban, por eso
# ninguna puerta de worktree lo vio.
def _arboles_reales() -> list[Path]:
    """El árbol que se prueba y su checkout primario: los dos pueden tener el output/ del usuario."""
    from convertersmartgrid import runtime_paths

    return sorted({RAIZ.resolve(), runtime_paths._primario(RAIZ.resolve())})


@pytest.fixture
def output_del_arbol():
    """Un output/ con contenido en el árbol que se prueba, si no lo tiene: así la prueba vale también en un worktree
    limpio o en GitHub Actions. Si ya existe (el del usuario en el árbol principal) no se crea, ni se lee, ni se toca
    nada dentro: solo se borra lo que esta prueba creó."""
    import shutil

    salida = RAIZ / 'output'
    creadas = []
    for carpeta in (salida, salida / 'web', salida / 'pide_dataset'):
        if not carpeta.exists():
            carpeta.mkdir()
            creadas.append(carpeta)
    if salida / 'web' in creadas or salida in creadas:
        for nombre in ('_asistente', '_digital_twin'):
            (salida / 'web' / nombre).mkdir()
        (salida / 'web' / 'vinculos_pf.json').write_text('{}', encoding='utf-8')
        (salida / 'web' / 'a1b2c3d4e5f6').mkdir()
    if salida / 'pide_dataset' in creadas or salida in creadas:
        (salida / 'pide_dataset' / 'x').mkdir()
        (salida / 'pide_dataset' / 'x' / 'ejemplos_agente.json').write_text('[]', encoding='utf-8')
    try:
        yield salida
    finally:
        for carpeta in reversed(creadas):
            shutil.rmtree(carpeta, ignore_errors=True)


def test_ninguna_raiz_de_datos_cae_en_el_output_del_checkout(output_del_arbol, monkeypatch):
    """106:RF-17 — durante la suite, ni las raíces de la copia de datos, ni los espacios heredados de la web, ni el
    registro de vínculos heredado, ni los almacenes heredados del asistente y del gemelo, ni los ejemplos del PIDE caen
    en el output/ del checkout real (el que se prueba o su primario), aunque exista y tenga datos."""
    from convertersmartgrid import powerfactory_binding, runtime_paths
    from convertersmartgrid.asistente.ejemplos_pide import ultimo_ejemplos
    from convertersmartgrid.web import copia_datos
    from convertersmartgrid.web.workspace import WorkspaceStore

    # Sin las variables que fija el conftest para los almacenes: lo que se prueba es la ruta que se deduce del checkout.
    for variable in ('CSG_ASISTENTE_DATA', 'CSG_TWIN_DATA', 'CSG_WEB_DATA'):
        monkeypatch.delenv(variable, raising=False)
    arboles = _arboles_reales()
    halladas = []

    def anotar(origen: str, ruta) -> None:
        resuelta = Path(ruta).resolve()
        if any(resuelta.is_relative_to(arbol / 'output') for arbol in arboles):
            halladas.append(f'{origen}: {resuelta}')

    for arbol in (None, *arboles):
        for nombre, ruta in copia_datos.raices_de_datos(arbol).items():
            anotar(f'raices_de_datos({arbol}).{nombre}', ruta)
        for componente, variable in (('_asistente', 'CSG_ASISTENTE_DATA'), ('_digital_twin', 'CSG_TWIN_DATA')):
            anotar(f'raiz_componente({componente}, {arbol})', runtime_paths.raiz_componente(componente, variable, arbol))
    for ruta in powerfactory_binding.registros_heredados():
        anotar('registros_heredados', ruta)
    for ruta in WorkspaceStore().roots:
        anotar('WorkspaceStore().roots', ruta)
    ejemplos = ultimo_ejemplos(RAIZ)
    if ejemplos is not None:
        anotar('ultimo_ejemplos', ejemplos)
    assert not halladas, 'Raíces de datos en el output/ del checkout real durante la suite (106:RF-17):\n' + \
        '\n'.join(halladas)


def test_una_prueba_que_fija_su_checkout_conserva_su_output(tmp_path, monkeypatch):
    """106:RF-17 — lo que una prueba fije por su cuenta manda: un checkout simulado en tmp conserva su output/web."""
    from convertersmartgrid.web import copia_datos

    monkeypatch.delenv('CSG_WEB_DATA', raising=False)
    (tmp_path / 'output' / 'web' / 'a1b2c3d4e5f6').mkdir(parents=True)
    raices = copia_datos.raices_de_datos(tmp_path)
    assert raices['heredada'].resolve() == (tmp_path / 'output' / 'web').resolve()


# 106:RF-17 (ampliado de nuevo el 2026-11-13, a petición del auditor) — tampoco el config/ ni el input/ locales del
# checkout real: con el perfil_empresa.json de una distribuidora real, una prueba que lo leía pasaba en esta máquina y fallaba en
# otra (P13: sin perfil no se supone nada). Lo versionado (config/perfiles, config/fichas, pide_universal_2017.json…)
# es del programa y se sigue leyendo de él.
def test_ningun_fichero_local_de_config_ni_input_sale_del_checkout_real(monkeypatch):
    """106:RF-17 — durante la suite, el perfil activo, los alias, la carpeta de DIgSILENT, las salidas, el archivo de
    informes, la copia de datos, los módulos permitidos y el catálogo de input/ no se buscan en el config/ ni en el
    input/ del checkout real; config/perfiles, que está en git, sí."""
    from convertersmartgrid import archivo_informes, perfil_empresa, powerfactory_env, reglas, salidas_red
    from convertersmartgrid.runtime_paths import raiz_local
    from convertersmartgrid.web import copia_datos

    for variable in (perfil_empresa.VARIABLE_RUTA, salidas_red.VARIABLE_RUTA_GUARDADAS):
        monkeypatch.delenv(variable, raising=False)
    arboles = _arboles_reales()
    halladas = []

    def anotar(origen: str, ruta) -> None:
        if ruta is None:
            return
        resuelta = Path(ruta).resolve()
        if any(resuelta.is_relative_to(arbol / carpeta) for arbol in arboles for carpeta in ('config', 'input')):
            halladas.append(f'{origen}: {resuelta}')

    for arbol in (None, *arboles):
        anotar(f'raiz_local({arbol})/config', raiz_local(arbol) / 'config')
        anotar(f'raiz_local({arbol})/input', raiz_local(arbol) / 'input')
        raices = copia_datos.raices_de_datos(arbol)
        for nombre in ('config', 'perfil_empresa', 'input'):
            anotar(f'raices_de_datos({arbol}).{nombre}', raices.get(nombre))
    anotar('ruta_perfil_activo', perfil_empresa.ruta_perfil_activo())
    anotar('archivo_informes.ruta_config', archivo_informes.ruta_config())
    anotar('powerfactory_env.ruta_eleccion', powerfactory_env.ruta_eleccion())
    anotar('salidas_red.ruta_guardadas', salidas_red.ruta_guardadas())
    anotar('copia_datos.ruta_carpeta_recordada', copia_datos.ruta_carpeta_recordada())
    anotar('reglas.catalogo_del_proyecto', reglas.catalogo_del_proyecto())
    assert not halladas, 'Ficheros locales del checkout real durante la suite (106:RF-17):\n' + '\n'.join(halladas)
    # Lo versionado sigue siendo del programa.
    assert perfil_empresa.carpeta_perfiles().resolve() == (RAIZ / 'config' / 'perfiles').resolve()
    assert 'electro_dunas' in perfil_empresa.perfiles_disponibles()


def test_la_puerta_sigue_leyendo_su_suite_completa(tmp_path):
    """106:RF-17 — la herramienta de la puerta (no una prueba) lee el config/suite_completa.json de su checkout, sin
    pasar por raiz_local: la redirección de la suite no le quita sus variables."""
    import importlib.util
    import inspect
    import json
    import sys

    spec = importlib.util.spec_from_file_location('puerta_calidad_rf17', RAIZ / 'tools' / 'puerta_calidad.py')
    puerta = importlib.util.module_from_spec(spec)
    sys.modules['puerta_calidad_rf17'] = puerta
    try:
        spec.loader.exec_module(puerta)
    finally:
        sys.modules.pop('puerta_calidad_rf17', None)
    assert puerta.RAIZ.resolve() == RAIZ.resolve()
    assert inspect.signature(puerta.variables_de_la_suite).parameters['raiz'].default == puerta.RAIZ
    assert 'raiz_local' not in inspect.getsource(puerta.variables_de_la_suite)
    existe = tmp_path / 'dato'
    existe.mkdir()
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'suite_completa.json').write_text(
        json.dumps({'variables': {k: str(existe) for k in puerta.VARIABLES}}), encoding='utf-8')
    assert puerta.variables_de_la_suite(tmp_path, entorno={}) == {k: str(existe) for k in puerta.VARIABLES}
