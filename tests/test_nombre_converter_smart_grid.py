"""El repositorio no menciona IGEA, el software de otra empresa (spec 058).

El proyecto se llamó «Conversor IGEA-DGS» hasta el 2026-11-01, con 511 ficheros que lo
nombraban. El usuario pidió dejarlo limpio con su nombre propio, ConverterSmartGrid; esta
prueba impide que el nombre vuelva a entrar por un fichero nuevo o una copia de un texto viejo.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: 058:RF-9: lo que se queda con el nombre anterior, cada cosa con su motivo.
EXCEPCIONES_FICHERO = (
    'specs/056-',   # explica por qué los mensajes no deben nombrar IGEA ni CYMDIST
    'specs/058-',   # explica el renombrado: cita los nombres anteriores
    'referencia/',  # datos de la distribuidora, fuera de git (principio 9)
    '.agents/coordination/',  # registro entre sesiones, sin versionar: cita la ruta real de la carpeta
    'tests/test_nombre_converter_smart_grid.py',
)
#: Una rama que existe en git (historia) y lo que el código reconoce para leer lo ya guardado.
EXCEPCIONES_LINEA = ('legado-058', 'feat/robustecimiento-igea')
PALABRA = re.compile(r'igea', re.IGNORECASE)


def _ficheros() -> list[str]:
    salida = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            cwd=RAIZ, check=True, capture_output=True).stdout
    return [f for f in salida.decode('utf-8').split('\0') if f]


def test_ningun_fichero_menciona_igea():
    """058:RF-1, 058:RF-2, 058:RF-3, 058:RF-7, 058:RF-8, 058:RF-9 — ni en el nombre ni dentro."""
    hallados = []
    for rel in _ficheros():
        if rel.startswith(EXCEPCIONES_FICHERO):
            continue
        if PALABRA.search(rel):
            hallados.append(f'{rel} (en el nombre)')
        ruta = RAIZ / rel
        if not ruta.is_file():
            continue
        datos = ruta.read_bytes()
        if b'\0' in datos[:8192]:
            continue    # binario: un PDF o una imagen no se reescriben aquí
        texto = datos.decode('utf-8', errors='replace')
        for n, linea in enumerate(texto.splitlines(), start=1):
            if PALABRA.search(linea) and not any(e in linea for e in EXCEPCIONES_LINEA):
                hallados.append(f'{rel}:{n}: {linea.strip()[:100]}')
    assert not hallados, 'menciones de IGEA (spec 058):\n' + '\n'.join(hallados[:40])


def test_el_paquete_y_los_comandos_tienen_el_nombre_nuevo():
    """058:RF-2 — paquete `convertersmartgrid` y sus dos comandos."""
    import tomllib

    datos = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    assert datos['project']['name'] == 'convertersmartgrid'
    assert {'convertersmartgrid', 'convertersmartgrid-web'} <= set(datos['project']['scripts'])
    assert (RAIZ / 'src' / 'convertersmartgrid' / '__init__.py').is_file()


def test_los_proyectos_nuevos_de_digsilent_llevan_la_sigla_csg():
    """058:RF-4 — `<sello>_CSG_<red>`, dentro de los 40 caracteres de DIgSILENT."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        'aceptacion', RAIZ / 'tools' / 'powerfactory_acceptance.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    corto = mod._generated_project_name('20261101-063543', 'W12882')
    largo = mod._generated_project_name('20261101-063543', 'SISTEMA_ELECTRICO_MUY_LARGO_DE_PRUEBA')
    assert corto == '20261101-063543_CSG_W12882'
    assert '_CSG_' in largo and len(largo) <= 40


def test_la_carpeta_por_defecto_es_convertersmartgrid():
    """058:RF-5 — sin carpeta en el perfil, «ConverterSmartGrid» (cambia 005:RF-3)."""
    from convertersmartgrid.carpeta_pf import NOMBRE_POR_DEFECTO

    assert NOMBRE_POR_DEFECTO == 'ConverterSmartGrid'


def test_lo_guardado_con_el_nombre_anterior_se_sigue_leyendo(tmp_path):
    """058:RF-6: el registro de vínculos y los vínculos escritos antes del cambio de nombre se
    leen; el 2026-11-01 la importación de NJA202 falló por el esquema anterior del registro."""
    import json

    from convertersmartgrid.powerfactory_binding import (
        BINDING_SCHEMA, PowerFactoryProjectBinding, _leer_registro,
    )
    from convertersmartgrid.util import PREFIJO_ESQUEMA_ANTERIOR, esquema_vigente

    anterior = PREFIJO_ESQUEMA_ANTERIOR + 'powerfactory-vinculos-v1'
    registro = tmp_path / 'vinculos_pf.json'
    registro.write_text(json.dumps({'schema': anterior, 'vinculos': {'P': {'project': 'P'}}}),
                        encoding='utf-8')
    assert _leer_registro(registro) == {'P': {'project': 'P'}}

    vinculo = PowerFactoryProjectBinding(
        project='P', folder='', source_run_id='r', source_mode='vnr', source_fingerprint='f',
        feeders=('A',), dgs_sha256={'A': 'x'}, native_inventory_sha256='h', native_reread={},
        schema_version=PREFIJO_ESQUEMA_ANTERIOR + 'powerfactory-project-binding-v1',
    )
    # Se acepta y su huella sigue valiendo: el esquema guardado no se reescribe.
    leido = PowerFactoryProjectBinding.from_dict(vinculo.as_dict())
    assert leido.binding_sha256 == vinculo.binding_sha256
    assert esquema_vigente(leido.schema_version) == BINDING_SCHEMA


def test_casos_y_biblioteca_de_antes_del_cambio_de_nombre():
    """058:RF-9: los casos marcados con el nombre anterior se reconocen (NA203 + NA205 y SM218,
    2026-11-01: «falta Con proyecto») y al volver a marcarlos queda solo la marca nueva."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import casos_pf
    from convertersmartgrid.util import NOMBRES_ANTERIORES_PF

    class Caso:
        loc_name = 'Con proyecto'
        desc = ['nota del operador', casos_pf.MARCA_ANTERIOR + 'con']

    caso = Caso()
    assert casos_pf.rol_de(caso) == 'con'
    casos_pf._marcar(caso, 'con')
    assert caso.desc == ['nota del operador', casos_pf.MARCA + 'con']
    assert NOMBRES_ANTERIORES_PF['CSG_Biblioteca_tipos'].endswith('_Biblioteca_tipos')
