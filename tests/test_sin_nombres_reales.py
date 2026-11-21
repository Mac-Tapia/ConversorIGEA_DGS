"""086:RF-33 (aclaración MEJ7-NOMBRES): el repositorio público no lleva el nombre de ninguna distribuidora real.

Caso real (2026-11-20): más de cien ficheros seguidos por git, entre specs, planes, manuales, pruebas, comentarios del
código y la web, escribían el nombre de la distribuidora de prueba y el de otras con las que se trabajó. La lista local de
``tools/comprobar_entrega.py`` solo mira lo que se entrega, y el checklist de integración solo las líneas añadidas a
``src/``, ``tests/`` y ``specs/``: nada miraba el repositorio entero.

La lista negra vive aquí, como huellas: ``huella(nombre)`` de 076:RF-6 (minúsculas, sin tildes, solo letras y cifras),
la misma forma de ``config/terminos_huellas.json``. Así esta prueba no escribe ningún nombre. Un nombre nuevo se añade
con su huella, que da ``convertersmartgrid.dominio.huellas_terminos.huella``; sus formas juntas («Empresaa») también.

Excepciones, cada una con su motivo (las decide el integrador; ver el inventario de MEJ7-NOMBRES):

- E1, el perfil excluido de la entrega: sus ficheros en ``config/perfiles/`` y su identificador (el nombre del fichero
  sin extensión), que es la clave con la que lo nombran ``config/perfil_empresa.json`` de cada instalación, la variable
  ``CSG_PERFIL`` y las pruebas. Cambiarlo es una migración de las instalaciones, no una sustitución de texto.
- E2, ``config/normativa/``: reproduce resoluciones públicas de Osinergmin con su huella SHA-256, y el nombre de cada
  empresa es la clave con la que el producto toma sus valores (``valor['empresas'][empresa]``, 107:RF-7).
- E3, líneas concretas que son a su vez una lista negra (por la huella de la línea: si la línea cambia, la excepción
  caduca y esta prueba vuelve a fallar).
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.dominio.huellas_terminos import huella, normalizar

RAIZ = Path(__file__).resolve().parents[1]
CE = cargar_herramienta('comprobar_entrega.py')

#: Huellas (sal 086) de los nombres de distribuidoras reales, de sus formas juntas y de sus siglas. Sin el nombre en claro.
HUELLAS_NOMBRES = frozenset({
    '047075ed0151f2d4', '057a20b4c85c06e0', '0e9c75f588780064', '1370feed1b6bb7b3', '17955f099ef309ea',
    '18d1eede274e2f56', '209bc9213dc400bc', '20b789235d4dc99b', '262a89f79310cfbc', '2d038d5b38d97fc3',
    '3549d2661da631eb', '3b833f0e48fd55e8', '3fcef5d2b6df64cf', '4a2b9b82bd4f8536', '4af77e5d41606e44',
    '4b94a82090925982', '4c62ac323a3eac6b', '504c72ebf0590410', '53ebfb0c4357445e', '5cc0b3bda3b06791',
    '61ca863bf96be8d4', '6ce4485ddfc75013', '755d8708ea474ad9', '806cbb98ae98d490', '8602b61ef88fa80c',
    '9606a4270f7a5109', '9698703e4b646c23', '99d32a8fa06cc9b6', 'b2c28743067f3791', 'b4424a8ebcd5b04e',
    'bc05db4ffd9e0572', 'c3cc77a5a3af206d', 'd1e4d3c43373be32', 'd8c21c7f8eb56a31', 'd919ad937d30f5d5',
    'dcd7c91abd5b78fd', 'e04806134ca3e96c', 'f436e021b4abac61', 'f74bf7543c4a3d4b', 'f924a38d99e2f916',
})
#: Huellas de la primera palabra de cada nombre: solo desde ellas se forman ventanas (la búsqueda no hace una huella por
#: cada trozo de cada línea del repositorio).
HUELLAS_PRIMERAS = frozenset({
    '047075ed0151f2d4', '057a20b4c85c06e0', '0e7ac1847e99874d', '0e9c75f588780064', '1370feed1b6bb7b3',
    '18d1eede274e2f56', '20b789235d4dc99b', '262a89f79310cfbc', '3549d2661da631eb', '3b833f0e48fd55e8',
    '4a2b9b82bd4f8536', '4af77e5d41606e44', '4b94a82090925982', '504c72ebf0590410', '5cc0b3bda3b06791',
    '61ca863bf96be8d4', '755d8708ea474ad9', '806cbb98ae98d490', '9606a4270f7a5109', '99d32a8fa06cc9b6',
    'b4424a8ebcd5b04e', 'b9b2387d8afe7ffb', 'bc05db4ffd9e0572', 'd1e4d3c43373be32', 'd8c21c7f8eb56a31',
    'd919ad937d30f5d5', 'dcd7c91abd5b78fd', 'e04806134ca3e96c', 'f436e021b4abac61', 'f74bf7543c4a3d4b',
})
#: E2: datos públicos de Osinergmin en los que el nombre es una clave del producto.
PREFIJOS_EXCEPTUADOS = ('config/normativa/',)
#: E3: (fichero, huella sha256[:16] de la línea sin sangría) con su motivo.
LINEAS_EXCEPTUADAS = {
    # 009:RF-8: el patrón que impide a una herramienta fijar la ruta de los datos de la distribuidora es una lista negra.
    ('tests/test_inventario.py', 'cb922c97fbe487b7'),
    # Pruebas que impiden que un nombre o una palabra suya vuelva al código o a lo generado: también son listas negras.
    ('tests/test_asistente_corpus_ampliado.py', '7e10c192d41ec00b'),
    ('tests/test_cargas_duplicadas_cliente.py', '335f964f380d6cde'),
    ('tests/test_procedimientos.py', 'bacf18de748b1939'),
    ('tests/test_proyeccion_anual.py', '61a34b197942f80c'),
    ('tests/test_valle.py', 'a1d2b739a89d6b1c'),
}
_CAMELLO = re.compile(r'(?<=[a-z])(?=[A-Z])')
_TOKEN = re.compile(r'[a-z0-9]+')
_MAX_PALABRAS = 4


def _perfiles_excluidos(manifiesto) -> tuple[str, ...]:
    """E1: el identificador de cada perfil de ``config/perfiles`` que no se entrega (el de la empresa de prueba)."""
    return tuple(sorted({r.name.split('.')[0] for r in (RAIZ / 'config' / 'perfiles').glob('*.json')
                         if not CE.entra(f'config/perfiles/{r.name}', manifiesto)}))


def _palabras(linea: str) -> list[str]:
    """«BaseDatosEmpresaA» y «empresa_a» se parten como «base datos empresa a»: un identificador no esconde el nombre."""
    return _TOKEN.findall(normalizar(_CAMELLO.sub(' ', linea)))


def nombres_en_texto(texto: str, *, quitar: tuple[str, ...] = (), memoria: dict[str, str] | None = None,
                     nombres: frozenset[str] = HUELLAS_NOMBRES,
                     primeras: frozenset[str] = HUELLAS_PRIMERAS) -> list[tuple[int, str]]:
    """(línea, huella) de cada nombre vigilado; también el partido por un salto de línea. ``quitar``: identificadores E1."""
    memoria = {} if memoria is None else memoria

    def h(trozo: str) -> str:
        if trozo not in memoria:
            memoria[trozo] = huella(trozo)
        return memoria[trozo]

    flujo: list[tuple[int, str]] = []
    for n, linea in enumerate(texto.splitlines(), 1):
        for ident in quitar:
            linea = linea.replace(ident, ' ')
        flujo += [(n, p) for p in _palabras(linea)]
    salida = []
    for i, (n, primera) in enumerate(flujo):
        if h(primera) not in primeras:
            continue
        for largo in range(1, _MAX_PALABRAS + 1):
            ventana = flujo[i:i + largo]
            if len(ventana) < largo:
                break
            firma = h(' '.join(p for _, p in ventana))
            if firma in nombres:
                salida.append((n, firma))
    return salida


def _seguidos() -> list[str]:
    r = subprocess.run(['git', 'ls-files', '-z'], cwd=RAIZ, capture_output=True, check=True)
    return sorted(f for f in r.stdout.decode('utf-8').split('\0') if f)


def _texto(rel: str) -> str | None:
    ruta = RAIZ / rel
    try:
        crudo = ruta.read_bytes()
    except OSError:
        return None
    if b'\0' in crudo[:8192] or rel.lower().endswith('.pdf'):
        return None
    return crudo.decode('utf-8', errors='replace')


def _exceptuada(rel: str, linea: str) -> bool:
    return (rel, hashlib.sha256(linea.strip().encode('utf-8')).hexdigest()[:16]) in LINEAS_EXCEPTUADAS


@pytest.fixture(scope='module')
def barrido():
    """Hallazgos del repositorio entero, sin E2 ni los ficheros de E1, separados en (fuera de excepción, exceptuados)."""
    manifiesto = CE.leer_manifiesto()
    perfiles = _perfiles_excluidos(manifiesto)
    memoria: dict[str, str] = {}
    malos, exceptuados = [], []
    for rel in _seguidos():
        texto = _texto(rel)
        if texto is None:
            continue
        de_perfil = rel.startswith('config/perfiles/') and Path(rel).name.split('.')[0] in perfiles
        destino = exceptuados if de_perfil or rel.startswith(PREFIJOS_EXCEPTUADOS) else None
        lineas = texto.splitlines()
        for n, _ in nombres_en_texto(texto, quitar=perfiles, memoria=memoria):
            if destino is not None or _exceptuada(rel, lineas[n - 1]):
                exceptuados.append(f'{rel}:{n}')
            else:
                malos.append(f'{rel}:{n}')
    return sorted(set(malos)), sorted(set(exceptuados))


def test_ningun_fichero_seguido_nombra_una_distribuidora_real(barrido):
    """086:RF-33 — fuera de E1, E2 y E3, ningún fichero seguido por git escribe el nombre de una distribuidora real.

    El mensaje da fichero y línea, nunca el nombre."""
    malos, _ = barrido
    assert not malos, f'{len(malos)} líneas con el nombre de una distribuidora real (fichero:línea): {malos[:60]}'


def test_la_busqueda_ve_los_nombres_de_verdad(barrido):
    """086:RF-33 — la normativa pública (E2) sí los trae: si la búsqueda no los viera, la prueba anterior pasaría sola."""
    _, exceptuados = barrido
    assert any(e.startswith('config/normativa/') for e in exceptuados), 'la búsqueda no encontró ni los nombres de E2'


def test_un_nombre_partido_o_dentro_de_un_identificador_tambien_se_ve():
    """086:RF-33 — mayúsculas, guiones bajos, tildes y el salto de línea no esconden un nombre (con uno sintético)."""
    def buscar(texto: str, **kw) -> list[tuple[int, str]]:
        return nombres_en_texto(texto, nombres=frozenset({huella('compania ejemplo'), huella('companiaejemplo')}),
                                primeras=frozenset({huella('compania'), huella('companiaejemplo')}), **kw)

    assert buscar('la ruta D:/BaseDatosCompaniaEjemplo/x.txt') == [(1, huella('compania ejemplo'))]
    assert [n for n, _ in buscar('de la Compañía\n   Ejemplo, el perfil')] == [1]
    assert buscar('perfil compania_ejemplo') and buscar('COMPANIAEJEMPLO')
    assert buscar('la compania_x', quitar=('compania_x',)) == []
    assert buscar('una compania de otro ejemplo') == []
