"""Spec 108 T12 — el estudio VAD es universal: ni el paquete ``vad/`` ni ``config/vad/`` ni sus pruebas llevan el
nombre, un código, un CRS o un periodo de una empresa (108:RF-13, P13).

Los términos de las empresas no se escriben aquí: salen de los perfiles que no se entregan, de las huellas de
``config/terminos_huellas.json`` y de la lista local, con ``tools/comprobar_entrega.py`` (086:RF-33). El CRS de una
empresa es el de su perfil (``crs_origen``): el código no lleva ninguno y las pruebas usan otros.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from apoyo import cargar_herramienta

CE = cargar_herramienta('comprobar_entrega.py')
RAIZ = CE.RAIZ
_CRS = re.compile(r'\b(?:EPSG|ESRI)\s*:\s*\d{4,6}\b', re.IGNORECASE)
#: Un periodo de fijación escrito en el código («2026-2030»): sale del registro (vad.grupo.N.periodo) o del estudio.
_PERIODO = re.compile(r'(?<![\w.-])(?:19|20)\d\d\s*[-–]\s*(?:19|20)\d\d(?![\w.-])')


def _ficheros(patron: str) -> list[Path]:
    return sorted(p for p in RAIZ.glob(patron) if p.is_file() and '__pycache__' not in p.parts)


def _rel(p: Path) -> str:
    return p.relative_to(RAIZ).as_posix()


@pytest.fixture(scope='module')
def manifiesto():
    return CE.leer_manifiesto()


@pytest.fixture(scope='module')
def terminos(manifiesto):
    return CE.cargar_terminos(RAIZ, manifiesto)


def _crs_de_las_empresas(manifiesto) -> set[str]:
    """Los CRS de los perfiles de empresa que no se entregan (los de las empresas de prueba)."""
    crs = set()
    for p in sorted((RAIZ / 'config' / 'perfiles').glob('*.json')):
        if CE.entra(f'config/perfiles/{p.name}', manifiesto):
            continue
        datos = json.loads(p.read_text(encoding='utf-8'))
        crs |= {m.group(0).replace(' ', '').upper() for m in _CRS.finditer(json.dumps(datos))}
    return crs


def test_108_rf13_sin_el_nombre_ni_un_codigo_de_una_empresa(terminos):
    """108:RF-13 — en vad/, config/vad/ y tests/test_vad_* no hay ningún nombre ni código de una empresa, tampoco en
    un comentario: el VAD vale para cualquier distribuidora."""
    ficheros = (_ficheros('src/convertersmartgrid/vad/*.py') + _ficheros('config/vad/*.json')
                + _ficheros('tests/test_vad_*.py'))
    assert len(ficheros) > 20, 'la comprobación recorrió de verdad el paquete, su registro y sus pruebas'
    malos = []
    for p in ficheros:
        malos += [f'{h.ruta}:{h.linea} ({h.categoria}, {h.clase})'
                  for h in CE.buscar_en_texto(_rel(p), p.read_text(encoding='utf-8'), terminos)]
    assert not malos, malos


def test_108_rf13_sin_un_crs_ni_un_periodo_escritos_en_el_codigo():
    """108:RF-13 — el código de vad/ no lleva ningún CRS (sale del perfil o de la entrada) ni ningún periodo de
    fijación (sale del registro o del estudio); config/vad/ no lleva ningún CRS."""
    malos = []
    for p in _ficheros('src/convertersmartgrid/vad/*.py'):
        for n, linea in enumerate(CE.lineas_de_codigo(p.name, p.read_text(encoding='utf-8')), 1):
            malos += [f'{_rel(p)}:{n} ({m.group(0)})' for m in _CRS.finditer(linea)]
            malos += [f'{_rel(p)}:{n} ({m.group(0)})' for m in _PERIODO.finditer(linea)]
    for p in _ficheros('config/vad/*.json'):
        malos += [f'{_rel(p)} ({m.group(0)})' for m in _CRS.finditer(p.read_text(encoding='utf-8'))]
    assert not malos, malos


def test_108_rf13_las_pruebas_no_usan_el_crs_de_una_empresa(manifiesto):
    """108:RF-13 — las pruebas del VAD usan CRS sintéticos o de otra zona, nunca el del perfil de una empresa."""
    de_empresas = _crs_de_las_empresas(manifiesto)
    assert de_empresas, 'hay perfiles de empresa fuera de la entrega con su CRS'
    malos = []
    for p in _ficheros('tests/test_vad_*.py'):
        for n, linea in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            malos += [f'{_rel(p)}:{n}' for m in _CRS.finditer(linea) if m.group(0).replace(' ', '').upper() in de_empresas]
    assert not malos, malos


def _registro_con_periodos(tmp_path, periodos):
    """Copia del registro real (config/vad y config/normativa) con los periodos de los grupos del TdR cambiados."""
    from convertersmartgrid.registro_normativo import cargar_registro
    destino = tmp_path / '-'.join(periodos)
    for carpeta in ('vad', 'normativa'):
        (destino / carpeta).mkdir(parents=True)
        for f in sorted((RAIZ / 'config' / carpeta).glob('*.json')):
            datos = json.loads(f.read_text(encoding='utf-8'))
            for norma in datos.get('normas') or ():
                for regla in norma.get('reglas') or ():
                    m = re.fullmatch(r'vad\.grupo\.(\d+)\.periodo', regla.get('clave', ''))
                    if m:
                        regla['valor'] = periodos[int(m.group(1)) - 1]
            (destino / carpeta / f.name).write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return cargar_registro(destino / 'vad', destino / 'normativa')


@pytest.mark.parametrize('periodos', (('2041-2045', '2042-2046'), ('2051-2055', '2052-2056')),
                         ids=('registro_a', 'registro_b'))
def test_108_rf13_el_periodo_del_aviso_de_costos_compartidos_sale_del_registro(tmp_path, periodos):
    """108:RF-13, 108:RF-9 — el aviso del Anexo 7 frente al Manual dice para qué periodos manda el TdR con los de los
    grupos que registra el acto (vad.grupo.N.periodo) y su vigencia del registro: con dos registros distintos, dos
    textos distintos, y ningún periodo fijo del código."""
    from convertersmartgrid.vad import coym
    registro = _registro_con_periodos(tmp_path, periodos)
    res = coym.costos_compartidos(1000.0, registro, avnr_periodo=2000.0)
    norma = registro.regla(coym.REGLA_COMPARTIDOS).norma
    aviso = next(a for a in res.avisos if 'manda el TdR' in a)
    esperado = f'para el VAD {periodos[0]} y {periodos[1]} ({norma.acto}, vigente desde {norma.vigencia_desde})'
    assert esperado in aviso, aviso
    assert '2026-2030' not in aviso
