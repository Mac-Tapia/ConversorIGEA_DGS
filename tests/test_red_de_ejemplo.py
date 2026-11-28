"""Spec 086, T41b: lo que dejó por corregir la revisión de una persona ajena (T41) en los documentos del cliente.

El revisor ajeno instaló el programa y siguió los manuales, pero no pudo convertir: el programa no trae datos de ninguna
empresa y él no tenía los de una. Tampoco encontró cómo instalar el complemento de IA (el diagnóstico remitía a un
apartado que el manual instalado no trae, porque se quita como «de quien construye») ni la plantilla del perfil, que
solo estaba dentro de la carpeta del Python del programa. Estas pruebas leen los documentos tal como se entregan
(``construir_candidato.copiar_documentos``) y siguen el manual al pie de la letra.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest

from apoyo import cargar_herramienta
from synthetic_export import ExportSpec, write_export

from convertersmartgrid import __version__
from convertersmartgrid.adaptadores.perfil_esquema import _hojas, esquema, validar_perfil
from convertersmartgrid.presentacion.cli import main as cli_main
from convertersmartgrid.presentacion.web import doctor as DR

CC = cargar_herramienta('construir_candidato.py')
CE = CC.CE
RAIZ = CE.RAIZ
EJEMPLO = RAIZ / 'ejemplos' / 'red_inventada'
#: La red de ejemplo es la del generador de las pruebas, con estos parámetros: dos alimentadores pequeños, sin semilla
#: (cada uno con 6 tramos, 3 cargas y un seccionador) y en la disposición reducida. Nada sale de un export real.
ESPEC = ExportSpec(feeders=2, sections_per_feeder=6, loads_per_feeder=3, naming='plain')
#: Nombre en el repositorio → lo que escribe ``write_export``.
FICHEROS = {'RED_ejemplo.txt': 'RED.txt', 'CARGA_ejemplo.txt': 'CARGA.txt', 'BD_Equipo_ejemplo.txt': 'BD_Equipo.txt'}
PLANTILLA = RAIZ / 'config' / 'perfiles' / 'plantilla.json'
MANUAL = RAIZ / 'docs' / 'MANUAL_OPERADOR.md'
GUIA = RAIZ / 'docs' / 'PERFIL_EMPRESA.md'
SECCION_IA = 'Instalar el complemento de IA'
SECCION_EJEMPLO = 'Probar con la red de ejemplo'


@pytest.fixture(scope='module')
def manifiesto():
    return CE.leer_manifiesto()


@pytest.fixture(scope='module')
def documentos(tmp_path_factory, manifiesto) -> Path:
    """«documentos/» como lo arma el candidato: lo que el operador encuentra en la carpeta del programa."""
    programa = tmp_path_factory.mktemp('programa')
    CC.copiar_documentos(RAIZ, programa / 'documentos', __version__, manifiesto)
    return programa / 'documentos'


def _seccion(texto: str, titulo: str) -> str:
    """El apartado ``## <titulo>`` hasta el siguiente ``## ``; vacío si no está."""
    hallado = re.search(rf'^## {re.escape(titulo)}\n(.*?)(?=^## |\Z)', texto, flags=re.M | re.S)
    return hallado.group(1) if hallado else ''


def test_la_red_de_ejemplo_es_la_inventada_del_generador(tmp_path, manifiesto):
    """086:RF-44 — la red de ejemplo es la del generador sintético, sin nada de una distribuidora (MEJ7-NOMBRES)."""
    generados = tmp_path / 'generada'
    write_export(ESPEC, generados)
    for nombre, generado in FICHEROS.items():
        assert (EJEMPLO / nombre).is_file(), nombre
        texto = (EJEMPLO / nombre).read_text(encoding='utf-8')
        assert texto == (generados / generado).read_text(encoding='utf-8'), \
            f'{nombre} ya no es la salida del generador: regenérelo con ExportSpec de esta prueba'
    terminos = CE.cargar_terminos(RAIZ, manifiesto, lista_local=None)
    for nombre in FICHEROS:
        rel = f'ejemplos/red_inventada/{nombre}'
        assert not CE.buscar_en_texto(rel, (EJEMPLO / nombre).read_text(encoding='utf-8'), terminos), rel


def test_la_red_y_la_plantilla_van_en_los_documentos(documentos):
    """086:RF-44 — la red de ejemplo y la plantilla del perfil quedan en «documentos/», junto a los manuales."""
    for nombre in FICHEROS:
        assert (documentos / nombre).is_file(), f'falta {nombre} en «documentos/»'
        assert (documentos / nombre).read_bytes() == (EJEMPLO / nombre).read_bytes(), nombre
    entregada = documentos / 'plantilla_perfil_empresa.json'
    assert entregada.is_file(), 'falta la plantilla del perfil en «documentos/»'
    assert json.loads(entregada.read_text(encoding='utf-8')) == json.loads(PLANTILLA.read_text(encoding='utf-8'))


def _orden_del_manual(texto: str) -> tuple[str, list[str]]:
    """La línea ``set "CSG=…"`` y la orden ``convert`` del apartado de la red de ejemplo, como las copia el operador."""
    seccion = _seccion(texto, SECCION_EJEMPLO)
    carpeta = re.search(r'^set "CSG=([^"]+)"$', seccion, flags=re.M)
    orden = re.search(r'^"%CSG%\\csg\.cmd" (convert .+)$', seccion, flags=re.M)
    assert carpeta and orden, f'el manual no trae la orden para convertir la red de ejemplo en «{SECCION_EJEMPLO}»'
    return carpeta.group(1), shlex.split(orden.group(1).replace('\\', '/'))


def test_la_red_de_ejemplo_se_convierte_siguiendo_el_manual(documentos, tmp_path, monkeypatch, capsys):
    """086:RF-44 — la orden del manual, tal cual, convierte la red de ejemplo de «documentos/» y deja sus DGS con GPS."""
    texto = MANUAL.read_text(encoding='utf-8')
    carpeta, argumentos = _orden_del_manual(texto)
    assert carpeta == r'%LOCALAPPDATA%\Programs\ConverterSmartGrid', 'la carpeta del programa del manual de instalación'
    # csg.cmd trabaja en la carpeta de datos (``cd /d``): una ruta relativa no encontraría los ficheros.
    rutas = [a for a in argumentos if '/' in a]
    assert rutas and all(a.startswith(('%CSG%/', '%USERPROFILE%/')) for a in rutas), rutas
    usuario = tmp_path / 'usuario'
    argumentos = [a.replace('%CSG%/documentos', str(documentos)).replace('%USERPROFILE%', str(usuario))
                  for a in argumentos]
    # Sin perfil de empresa: el revisor no tiene ninguno, y la orden no debe necesitarlo.
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(tmp_path / 'sin_perfil.json'))
    assert cli_main(argumentos) == 0, capsys.readouterr().out[-2000:]
    salida = Path(argumentos[argumentos.index('--out-dir') + 1])
    dgs = sorted(p.name for p in salida.glob('*.dgs'))
    assert dgs == ['AL01.dgs', 'AL02.dgs']
    for nombre in dgs:
        assert nombre in _seccion(texto, SECCION_EJEMPLO), f'el manual no dice que sale {nombre}'
        assert (salida / nombre).stat().st_size > 0
        assert (salida / nombre.replace('.dgs', '_geography.json')).is_file(), 'con el CRS del manual sale el GPS'
    manifiesto = json.loads((salida / 'batch_manifest.json').read_text(encoding='utf-8'))
    assert manifiesto, 'el manifiesto del lote'


def test_el_manual_explica_como_instalar_el_complemento_de_ia():
    """086:RF-44, 086:RF-37 — el operador encuentra en su manual cómo instalar el complemento, y el diagnóstico lo remite ahí."""
    texto = MANUAL.read_text(encoding='utf-8')
    seccion = _seccion(texto, SECCION_IA)
    assert seccion, f'MANUAL_OPERADOR.md no trae «{SECCION_IA}»'
    iss = (RAIZ / 'instalador' / 'ComplementoIA.iss').read_text(encoding='utf-8')
    base = re.search(r'^OutputBaseFilename=(.+)-\{#Version\}-setup$', iss, flags=re.M).group(1)
    for pieza in (f'{base}-<versión>-setup.exe', 'SHA256SUMS', 'misma versión', 'csg.cmd" doctor',
                  'ConverterSmartGrid - complemento de IA', 'cierre'):
        assert pieza in seccion, pieza
    assert f'«{SECCION_IA}»' in _seccion(texto, 'Qué hace y qué no'), 'el apartado de entrenar remite a la sección'
    arreglo = DR._ia(lambda _nombre: None).arreglo
    assert 'MANUAL_OPERADOR.md' in arreglo and f'«{SECCION_IA}»' in arreglo, arreglo


def test_la_plantilla_comenta_cada_clave_sin_valores_de_una_empresa():
    """086:RF-44, 086:RF-32 — cada clave de la plantilla lleva su comentario del esquema, y ninguna trae un valor (P13)."""
    datos = json.loads(PLANTILLA.read_text(encoding='utf-8'))
    esquema_hojas = dict(_hojas(esquema()))

    def hojas(d, prefijo=''):
        for clave, valor in d.items():
            if not clave.startswith('_'):
                yield from (hojas(valor, f'{prefijo}{clave}.') if isinstance(valor, dict) else [(f'{prefijo}{clave}', valor)])

    claves = list(hojas(datos))
    assert len(claves) >= 30
    for ruta, valor in claves:
        assert valor is None, f'{ruta} trae un valor: la plantilla no supone nada'
        comentario = datos.get(f'_comentario_{ruta}', '')
        assert esquema_hojas[ruta]['x-funcion'] in comentario, ruta
        assert comentario.startswith(esquema_hojas[ruta]['x-origen'].capitalize()), ruta
    r = validar_perfil(datos)
    assert r.errores == [] and r.desconocidas == []


def test_el_manual_y_la_guia_enlazan_la_plantilla_y_la_seccion():
    """086:RF-44 — el manual y la guía del perfil nombran la plantilla de «documentos/», y la guía, la sección del complemento."""
    manual = MANUAL.read_text(encoding='utf-8')
    guia = GUIA.read_text(encoding='utf-8')
    for texto in (manual, guia):
        assert 'documentos\\plantilla_perfil_empresa.json' in texto
    assert f'«{SECCION_IA}»' in guia and 'MANUAL_OPERADOR.md' in guia
