"""Spec 002, RF-31 a RF-37 — perfil de empresa: el conversor no supone las convenciones
de ninguna distribuidora.

Hasta la spec 002 el CRS de Ica y la exclusión de las SED ``M…`` iban como valores por
defecto. En otra empresa la red salía desplazada o perdía SED reales sin aviso. Estas
pruebas convierten la misma red sintética con perfiles distintos y sin perfil.
"""
from __future__ import annotations

import io
import json
import tokenize
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

import pytest

from synthetic_export import ExportSpec, write_export
from igea_dgs.dataset import CymdistDataset
from igea_dgs.perfil_empresa import (
    SIN_PERFIL,
    VARIABLE_RUTA,
    PerfilEmpresa,
    PerfilError,
    cargar_perfil,
    perfil_con_nombre,
    perfiles_disponibles,
)
from igea_dgs.reglas import REGLAS_PROYECTO, reglas_de_perfil

RAIZ = Path(__file__).resolve().parents[1]

#: Dos empresas inventadas con convenciones distintas: otro CRS, otro patrón de SED de
#: medición (las del primer alimentador sintético, ``SE1…``) y otra escala.
EMPRESA_A = PerfilEmpresa(nombre='empresa_a', crs_origen='EPSG:32719',
                          patron_sed_medicion=r'^SE1\d+$', escala_diagrama=1.0)
EMPRESA_B = PerfilEmpresa(nombre='empresa_b', crs_origen='EPSG:32717')


def _convertir(tmp_path: Path, perfil: PerfilEmpresa, nombre: str, *, geografia: bool = True) -> tuple[dict, Path]:
    from igea_dgs.batch import convert_selection

    red, loads, equip = write_export(ExportSpec(feeders=2, naming='plain'), tmp_path / 'export')
    ds = CymdistDataset.from_files(red, loads, equip)
    out = tmp_path / nombre
    manifiesto = convert_selection(
        ds, None, out, all_feeders=True, include_geography=geografia,
        source_crs=perfil.crs_origen, reglas=reglas_de_perfil(perfil, REGLAS_PROYECTO),
        perfil=perfil,
    )
    return manifiesto, out


def _filas(dgs: Path, clase: str) -> list[dict]:
    from igea_dgs.validate import parse_dgs

    tabla = parse_dgs(dgs).get(clase) or {}
    return [dict(zip(tabla['fields'], fila)) for fila in tabla.get('rows') or []]


def _seds(dgs: Path) -> int:
    return len(_filas(dgs, 'ElmTr2'))


# --------------------------------------------------------------------------- RF-31
def test_el_perfil_activo_hereda_de_uno_con_nombre_y_lo_pisa(tmp_path):
    """002:RF-31 — CRS, patrón, escala y forma salen del perfil; el local pisa al heredado."""
    carpeta = tmp_path / 'perfiles'
    carpeta.mkdir()
    (carpeta / 'empresa_a.json').write_text(json.dumps({
        'crs_origen': 'EPSG:32719', 'patron_sed_medicion': '^X\\d+$',
        'escala_diagrama': 1.5, 'forma_alimentador': '^AL\\d+$'}), encoding='utf-8')
    activo = tmp_path / 'perfil_empresa.json'
    activo.write_text(json.dumps({'perfil': 'empresa_a', 'crs_origen': 'EPSG:32717',
                                  'patron_sed_medicion': None}), encoding='utf-8')

    perfil = cargar_perfil(activo, carpeta=carpeta)

    assert perfil == PerfilEmpresa(nombre='empresa_a', crs_origen='EPSG:32717',
                                   patron_sed_medicion=None, escala_diagrama=1.5,
                                   forma_alimentador='^AL\\d+$')


@pytest.mark.parametrize('datos, texto', [
    ({'patron_sed_medicion': '(sin cerrar'}, 'patron_sed_medicion'),
    ({'patron_libro_clientes': r'^clientes\d+$'}, 'patron_libro_clientes'),
    ({'escala_diagrama': 0}, 'escala_diagrama'),
    ({'escala_diagrama': 'mucha'}, 'escala_diagrama'),
    ({'crs_origen': ''}, 'crs_origen'),
    ({'perfil': 'no_existe'}, 'no_existe'),
])
def test_un_perfil_imposible_es_un_error_que_lo_nombra(tmp_path, datos, texto):
    """002:RF-31 — un valor imposible no se ignora: convertir con él daría otra red."""
    activo = tmp_path / 'perfil_empresa.json'
    activo.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(PerfilError, match=texto):
        cargar_perfil(activo, carpeta=tmp_path)


def test_la_escala_del_perfil_cambia_el_diagrama_y_no_la_red(tmp_path):
    """002:RF-31 — la escala del diagrama es del perfil; la red eléctrica no cambia."""
    pytest.importorskip('pyproj')
    _, a = _convertir(tmp_path / 'a', replace(EMPRESA_B, escala_diagrama=1.0), 'a')
    _, b = _convertir(tmp_path / 'b', replace(EMPRESA_B, escala_diagrama=4.0), 'b')
    assert _filas(a / 'AL01.dgs', 'ElmLne') == _filas(b / 'AL01.dgs', 'ElmLne')
    assert _filas(a / 'AL01.dgs', 'IntGrf') != _filas(b / 'AL01.dgs', 'IntGrf')


def test_la_forma_del_alimentador_solo_avisa(tmp_path):
    """002:RF-31 — un nombre fuera de la forma del perfil se avisa y se convierte igual."""
    perfil = replace(EMPRESA_B, forma_alimentador=r'^[A-Z]{2}\d{3}$')
    manifiesto, _ = _convertir(tmp_path, perfil, 'out')
    assert manifiesto['summary']['ok'] == 2
    assert any('no cumplen la forma' in w and 'AL01' in w for w in manifiesto['input_warnings'])


# --------------------------------------------------------------------------- RF-32
def test_sin_crs_no_se_supone_ninguno(tmp_path):
    """002:RF-32 — sin CRS en la entrada ni en el perfil, se pide antes de escribir nada."""
    from igea_dgs.batch import convert_selection
    from igea_dgs.geography import CrsOrigenFaltaError

    red, loads, equip = write_export(ExportSpec(feeders=1), tmp_path / 'export')
    ds = CymdistDataset.from_files(red, loads, equip)
    with pytest.raises(CrsOrigenFaltaError, match='crs_origen'):
        convert_selection(ds, None, tmp_path / 'out', all_feeders=True, include_geography=True)
    assert not list((tmp_path / 'out').glob('*.dgs'))


def test_sin_crs_se_convierte_sin_georreferenciacion(tmp_path):
    """002:RF-32 — sin CRS, la conversión sin georreferenciación sigue funcionando."""
    manifiesto, out = _convertir(tmp_path, SIN_PERFIL, 'out', geografia=False)
    assert manifiesto['summary']['ok'] == 2
    assert manifiesto['source_crs'] is None


def test_el_cli_pide_el_crs_y_dice_como(tmp_path):
    """002:RF-32 — el CLI sale con 1 y nombra --source-crs, --perfil y el perfil local."""
    from igea_dgs.cli import main

    red, loads, equip = write_export(ExportSpec(feeders=1), tmp_path / 'export')
    with pytest.raises(SystemExit) as exc:
        main(['convert', '--red', str(red), '--loads', str(loads), '--equipment', str(equip),
              '--all', '--out-dir', str(tmp_path / 'out')])
    mensaje = str(exc.value.code)
    assert '--source-crs' in mensaje and '--perfil' in mensaje and 'perfil_empresa.json' in mensaje


def test_el_cli_toma_el_crs_del_perfil_con_nombre(tmp_path):
    """002:RF-32 — con --perfil, el CRS sale del perfil y no hay que escribirlo."""
    pytest.importorskip('pyproj')
    from igea_dgs.cli import main

    red, loads, equip = write_export(ExportSpec(feeders=1), tmp_path / 'export')
    with redirect_stdout(io.StringIO()):
        codigo = main(['convert', '--red', str(red), '--loads', str(loads),
                       '--equipment', str(equip), '--all', '--out-dir', str(tmp_path / 'out'),
                       '--perfil', 'electro_dunas'])
    assert codigo == 0
    manifiesto = json.loads((tmp_path / 'out' / 'batch_manifest.json').read_text(encoding='utf-8'))
    assert manifiesto['source_crs'] == perfil_con_nombre('electro_dunas').crs_origen
    assert manifiesto['perfil_empresa']['nombre'] == 'electro_dunas'


def test_la_web_pide_el_crs_sin_perfil(tmp_path, monkeypatch):
    """002:RF-32 — la web no convierte con georreferenciación sin CRS: error de usuario."""
    pytest.importorskip('fastapi')
    from igea_dgs.web.services import UserError, crs_origen, crs_origen_exigido
    from igea_dgs.web.workspace import DEFAULT_OPTIONS, Workspace

    assert DEFAULT_OPTIONS['source_crs'] is None
    ws = Workspace(id='w', root=tmp_path / 'w')
    assert crs_origen(ws) is None
    with pytest.raises(UserError, match='crs_origen'):
        crs_origen_exigido(ws)

    activo = tmp_path / 'perfil_empresa.json'
    activo.write_text(json.dumps({'crs_origen': 'EPSG:32719'}), encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(activo))
    assert crs_origen_exigido(ws) == 'EPSG:32719'
    ws.options['source_crs'] = 'EPSG:32717'
    assert crs_origen_exigido(ws) == 'EPSG:32717', 'lo que elige el usuario manda sobre el perfil'


def test_la_web_sugiere_los_crs_de_los_perfiles_y_no_una_lista_fija(tmp_path, monkeypatch):
    """002:RF-32 — los CRS sugeridos salen de los perfiles, y /api/health dice el activo."""
    pytest.importorskip('fastapi')
    pytest.importorskip('httpx2')
    from fastapi.testclient import TestClient

    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as client:
        salud = client.get('/api/health').json()
    assert salud['perfil_empresa'] == {**SIN_PERFIL.valores(), 'error': None}
    assert salud['default_options']['source_crs'] is None
    sugeridos = {p['code']: p['label'] for p in salud['crs_presets']}
    for nombre in perfiles_disponibles():
        crs = perfil_con_nombre(nombre).crs_origen
        if crs:
            assert crs in sugeridos


# --------------------------------------------------------------------------- RF-33
def test_sin_patron_no_se_excluye_ninguna_sed_por_su_nombre():
    """002:RF-33 — una SED que se llame «M…» es una SED si el perfil no dice lo contrario."""
    from igea_dgs.trafomix import es_trafomix

    patron = perfil_con_nombre('electro_dunas').patron_sed_medicion
    assert es_trafomix('M41608', patron)
    assert not es_trafomix('M41608', SIN_PERFIL.patron_sed_medicion)
    assert reglas_de_perfil(SIN_PERFIL).patron_sed_medicion is None


def test_sin_patron_se_conservan_las_sed_que_otro_perfil_excluye(tmp_path):
    """002:RF-33 — mismas SED que la entrada sin patrón; con él, solo faltan las suyas."""
    _, sin = _convertir(tmp_path / 'sin', EMPRESA_B, 'out')
    _, con = _convertir(tmp_path / 'con', EMPRESA_A, 'out')
    assert _seds(sin / 'AL01.dgs') > 0
    assert _seds(con / 'AL01.dgs') == 0, 'el patrón de la empresa A es el de las SED de AL01'
    assert _seds(con / 'AL02.dgs') == _seds(sin / 'AL02.dgs')


# --------------------------------------------------------------------------- RF-34
#: Convenciones de Electro Dunas que no pueden volver al código como valores.
CONVENCIONES = ('EPSG:32718', '^M\\d', 'IN111', 'NA205')


def _literales(ruta: Path) -> list[tuple[int, str]]:
    """Cadenas del código que no son docstrings (un docstring explica, no decide)."""
    hallados = []
    previo = None
    with ruta.open('rb') as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.STRING:
                docstring = previo is None or previo.type in (tokenize.INDENT, tokenize.NEWLINE,
                                                               tokenize.DEDENT, tokenize.ENCODING)
                if not docstring:
                    hallados.append((tok.start[0], tok.string))
            if tok.type not in (tokenize.NL, tokenize.COMMENT):
                previo = tok
    return hallados


def test_el_codigo_no_trae_convenciones_de_una_empresa():
    """002:RF-34 — ningún literal de src/ ni tools/ lleva el CRS, el patrón o un alimentador de Electro Dunas."""
    hallados = [
        f'{ruta.relative_to(RAIZ)}:{linea}: {texto[:60]}'
        for carpeta in ('src', 'tools')
        for ruta in sorted((RAIZ / carpeta).rglob('*.py'))
        for linea, texto in _literales(ruta)
        if any(c in texto for c in CONVENCIONES)
    ]
    assert not hallados, hallados


# --------------------------------------------------------------------------- RF-35
def test_electro_dunas_es_un_perfil_mas():
    """002:RF-35 — el perfil de Electro Dunas está en config/perfiles, solo con convenciones."""
    assert 'electro_dunas' in perfiles_disponibles()
    perfil = perfil_con_nombre('electro_dunas')
    assert perfil.crs_origen and perfil.patron_sed_medicion and perfil.escala_diagrama
    assert perfil.patron_libro_clientes
    datos = json.loads((RAIZ / 'config' / 'perfiles' / 'electro_dunas.json').read_text(encoding='utf-8'))
    assert {k for k in datos if not k.startswith('_')} <= {
        'crs_origen', 'patron_sed_medicion', 'escala_diagrama', 'forma_alimentador',
        # 015:RF-54: el factor de potencia de las escaladas también es una convención.
        'patron_libro_clientes', 'informes', 'calibracion', 'estudios',
        # 016:RF-81: el enrutador de vías del enlace lo elige cada empresa.
        'vias',
        # 022:RF-3: la estructura zonal → SET → alimentadores, en un JSON aparte.
        'estructura'}
    assert perfiles_disponibles() == sorted(set(perfiles_disponibles())), 'la estructura no es un perfil'
    assert 'electro_dunas.estructura' not in perfiles_disponibles()


# --------------------------------------------------------------------------- RF-36
def test_dos_perfiles_sobre_la_misma_red_dan_dos_conversiones(tmp_path):
    """002:RF-36 — la misma red con dos perfiles: cada una con su CRS, sus SED y su escala."""
    pytest.importorskip('pyproj')
    man_a, a = _convertir(tmp_path / 'a', EMPRESA_A, 'out')
    man_b, b = _convertir(tmp_path / 'b', EMPRESA_B, 'out')
    assert man_a['summary']['ok'] == man_b['summary']['ok'] == 2
    assert (man_a['source_crs'], man_b['source_crs']) == ('EPSG:32719', 'EPSG:32717')
    gps = lambda d: [(f.get('GPSlat'), f.get('GPSlon')) for f in _filas(d, 'ElmTerm')]  # noqa: E731
    assert gps(a / 'AL02.dgs') != gps(b / 'AL02.dgs')
    assert _seds(a / 'AL01.dgs') < _seds(b / 'AL01.dgs')


# --------------------------------------------------------------------------- RF-37
def test_el_manifiesto_registra_el_perfil_y_sus_valores(tmp_path):
    """002:RF-37 — el manifiesto del lote dice con qué perfil y qué valores se convirtió."""
    manifiesto, out = _convertir(tmp_path, EMPRESA_A, 'out')
    escrito = json.loads((out / 'batch_manifest.json').read_text(encoding='utf-8'))
    assert manifiesto['perfil_empresa'] == escrito['perfil_empresa'] == EMPRESA_A.valores()


def test_la_red_unida_registra_el_perfil(tmp_path):
    """002:RF-37 — también el manifiesto de la red unida."""
    from igea_dgs.batch import convert_group

    red, loads, equip = write_export(ExportSpec(feeders=2, naming='plain'), tmp_path / 'export')
    ds = CymdistDataset.from_files(red, loads, equip)
    grupo = convert_group(ds, ['AL01', 'AL02'], tmp_path / 'out', name='UNIDA',
                          include_geography=False, perfil=EMPRESA_B,
                          reglas=reglas_de_perfil(EMPRESA_B))
    assert grupo['perfil_empresa'] == EMPRESA_B.valores()


@pytest.mark.parametrize('valor', [0, -0.5, 1.2, True, '0.98'])
def test_factor_de_potencia_imposible_lo_nombra(valor):
    """015:RF-57 — un factor de potencia fuera de (0, 1] es un error que dice el valor."""
    from igea_dgs.perfil_empresa import factor_potencia_cargas

    with pytest.raises(PerfilError, match='factor_potencia_cargas'):
        factor_potencia_cargas({'calibracion': {'factor_potencia_cargas': valor}})


def test_factor_de_potencia_del_perfil_de_electro_dunas():
    """015:RF-54 / 015:RF-55 — Electro Dunas fija 0,98 para las escaladas; sin la clave, nada."""
    from igea_dgs.perfil_empresa import factor_potencia_cargas

    raiz = Path(__file__).resolve().parents[1] / 'config' / 'perfiles'
    datos = json.loads((raiz / 'electro_dunas.json').read_text(encoding='utf-8'))
    assert factor_potencia_cargas(datos) == 0.98
    assert factor_potencia_cargas({}) is None


def test_fp_minimo_de_las_fijas_del_perfil():
    """015:RF-62 / 015:RF-57 — Electro Dunas fija 0,98 como mínimo de las fijas; un valor
    imposible se rechaza nombrando la clave."""
    from igea_dgs.perfil_empresa import factor_potencia_cargas

    raiz = Path(__file__).resolve().parents[1] / 'config' / 'perfiles'
    datos = json.loads((raiz / 'electro_dunas.json').read_text(encoding='utf-8'))
    assert factor_potencia_cargas(datos, 'factor_potencia_minimo_fijas') == 0.98
    with pytest.raises(PerfilError, match='factor_potencia_minimo_fijas'):
        factor_potencia_cargas({'calibracion': {'factor_potencia_minimo_fijas': 2}},
                               'factor_potencia_minimo_fijas')


# --------------------------------------------------------------------------- spec 020
def _electro_dunas():
    raiz = Path(__file__).resolve().parents[1] / 'config' / 'perfiles'
    return json.loads((raiz / 'electro_dunas.json').read_text(encoding='utf-8'))


def test_fichas_de_transformadores_del_perfil_de_electro_dunas():
    """020:RF-29 / 020:RF-30 — Electro Dunas trae las Tablas 6 y 7 de FONAFE 2017 (NTP
    370.400) por rango de tensión primaria, con Po, Pc, Io y uk por kVA, y el umbral del 80 %."""
    from igea_dgs.perfil_empresa import transformadores_sed

    t = transformadores_sed(_electro_dunas())
    assert t['umbral_carga_pct'] == 80 and t['avisos'] == []
    seis, siete = t['tablas']
    assert (seis['kv_min'], seis['kv_max'], siete['kv_min'], siete['kv_max']) == (0, 17.5, 17.5, 36)
    assert 'Tabla 6' in seis['norma'] and 'Tabla 7' in siete['norma'] and seis['codigo']
    assert seis['fichas'][630] == (1411, 8136, 1.15, 4)
    assert siete['fichas'][630] == (1486, 8144, 1.15, 4)
    assert siete['fichas'][500] == (1221, 6464, 1.87, 4)
    assert max(seis['fichas']) == max(siete['fichas']) == 630
    assert 200 in seis['fichas'] and 200 not in siete['fichas']


def test_sin_fichas_en_el_perfil_no_se_supone_ninguna():
    """020:RF-29 — sin la sección, ninguna tabla (la 020:RF-10 lo dice en la web)."""
    from igea_dgs.perfil_empresa import transformadores_sed

    assert transformadores_sed({}) is None
    assert transformadores_sed({'calibracion': {'factor_potencia_cargas': 0.98}}) is None


@pytest.mark.parametrize('fila', [[374, 1920, 2.99], [374, 0, 2.99, 4], [374, 1920, -1, 4],
                                  ['x', 1920, 2.99, 4], [374, 1920, True, 4], 'x'])
def test_una_fila_imposible_se_descarta_y_se_nombra(fila):
    """020:RF-31 — la fila incompleta o con un valor no positivo no se usa, y el aviso nombra
    la fila, la tabla y el perfil; las demás filas siguen valiendo."""
    from igea_dgs.perfil_empresa import transformadores_sed

    datos = {'perfil': 'otra', 'calibracion': {'transformadores_sed': {
        'umbral_carga_pct': 80, 'tablas': [{
            'norma': 'Norma X', 'codigo': 'NX', 'kv_min': 0, 'kv_max': 20,
            'fichas': {'50': [232, 1120, 3.57, 4], '100': fila}}]}}}
    t = transformadores_sed(datos)
    assert list(t['tablas'][0]['fichas']) == [50]
    assert len(t['avisos']) == 1
    assert '100' in t['avisos'][0] and 'Norma X' in t['avisos'][0] and 'otra' in t['avisos'][0]


@pytest.mark.parametrize('umbral', [0, -5, 150, 'x', None, True])
def test_umbral_de_carga_imposible_lo_nombra(umbral):
    """020:RF-30 — el umbral tiene que estar entre 0 (sin incluirlo) y 100."""
    from igea_dgs.perfil_empresa import transformadores_sed

    datos = {'calibracion': {'transformadores_sed': {'umbral_carga_pct': umbral, 'tablas': []}}}
    with pytest.raises(PerfilError, match='umbral_carga_pct'):
        transformadores_sed(datos)


def test_tabla_sin_rango_o_sin_filas_validas_se_descarta():
    """020:RF-31 — una tabla sin rango de tensión válido o sin ninguna fila válida no se usa."""
    from igea_dgs.perfil_empresa import transformadores_sed

    datos = {'calibracion': {'transformadores_sed': {'umbral_carga_pct': 80, 'tablas': [
        {'norma': 'A', 'codigo': 'A', 'kv_min': 20, 'kv_max': 10, 'fichas': {'50': [1, 1, 1, 1]}},
        {'norma': 'B', 'codigo': 'B', 'kv_min': 0, 'kv_max': 10, 'fichas': {'50': [0, 1, 1, 1]}},
    ]}}}
    t = transformadores_sed(datos)
    assert t['tablas'] == [] and any('A' in a for a in t['avisos']) and any('B' in a for a in t['avisos'])


def test_centrales_del_perfil_validadas():
    """021:RF-27 — la sección ``centrales_termicas``: tres medidores obligatorios y el nodo
    optativo; sin sección, ninguna central supuesta."""
    from igea_dgs.perfil_empresa import PerfilError, centrales_termicas

    assert centrales_termicas({}) == {}
    assert centrales_termicas({'centrales_termicas': {' A1 ': {
        'generacion': 'G', 'llegada': 'L', 'salida': 'S', 'nodo': ' N1 '}}}) == {
        'A1': {'generacion': 'G', 'llegada': 'L', 'salida': 'S', 'nodo': 'N1'}}
    with pytest.raises(PerfilError, match='salida'):
        centrales_termicas({'centrales_termicas': {'A1': {'generacion': 'G', 'llegada': 'L'}}})
