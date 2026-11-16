"""Spec 107, RF-15 — el unifilar del PIT por alternativa y año, con el flujo de cada línea (F-212), en DXF y, si hay
convertidor, en DWG.

ezdxf hace de lector independiente: abre el DXF escrito y busca el marco A3, una hoja por alternativa y año, y las
barras, los transformadores y las líneas con su flujo. El convertidor a DWG es un doble (un .bat que llama a Python),
nunca el ODA File Converter real; su ruta sale del perfil o del PATH. Datos sintéticos sorteados con semilla.
"""
from __future__ import annotations

import random
import re
import sys
import tomllib
from pathlib import Path

import ezdxf
import pytest

from convertersmartgrid.pit import unifilar as U
from convertersmartgrid.pit.red_area import RedArea
from convertersmartgrid.pit.red_pandapower import ResultadoFlujo, calcular

RAIZ = Path(__file__).resolve().parents[1]


def _caso(seed: int, *, completa: bool = True) -> dict:
    """Fuente → línea → barra AT → transformador → barra MT con carga; y una línea nueva a otra SET."""
    rng = random.Random(seed)
    kv_at, kv_mt = rng.choice((60.0, 66.0, 69.0)), rng.choice((10.0, 13.8, 22.9))
    area = f'AD-{rng.randint(10, 99)}'
    s1, s2 = f'S{rng.randint(100, 499)}', f'S{rng.randint(500, 999)}'
    t = {'titular': f'TIT-{rng.randint(1, 50)}'}
    linea_extra = {'material': rng.choice(('AAAC', 'ACSR', 'Cu')), 'seccion_mm2': rng.choice((120, 185, 240))} \
        if completa else {}
    trafo_extra = {'tap_min': -rng.randint(5, 10), 'tap_max': rng.randint(5, 10)} if completa else {}

    def linea(i, a, b):
        return {'id': i, 'tipo': 'linea', 'desde': a, 'hasta': b, 'longitud_km': round(rng.uniform(4, 25), 2),
                'r_ohm_per_km': 0.12, 'x_ohm_per_km': 0.4, 'c_nf_per_km': 9.5, 'max_i_ka': 0.5, **linea_extra, **t}

    def trafo(i, hv, lv):
        return {'id': i, 'tipo': 'trafo2', 'hv': hv, 'lv': lv, 'sn_mva': rng.choice((15.0, 25.0, 30.0)),
                'vn_hv_kv': kv_at, 'vn_lv_kv': kv_mt, 'vk_percent': round(rng.uniform(8, 11), 2),
                'vkr_percent': 0.4, 'pfe_kw': 15.0, 'i0_percent': 0.1, **trafo_extra, **t}

    red = RedArea(area, elementos={
        'barra': [{'id': 'B-F', 'tipo': 'barra', 'kv': kv_at, **t},
                  {'id': f'B-{s1}-AT', 'tipo': 'barra', 'kv': kv_at, 'set': s1, **t},
                  {'id': f'B-{s1}-MT', 'tipo': 'barra', 'kv': kv_mt, 'set': s1, 'rol': 'carga', **t},
                  {'id': f'B-{s2}-AT', 'tipo': 'barra', 'kv': kv_at, 'set': s2, **t},
                  {'id': f'B-{s2}-MT', 'tipo': 'barra', 'kv': kv_mt, 'set': s2, 'rol': 'carga', **t}],
        'red_externa': [{'id': 'RE', 'tipo': 'red_externa', 'barra': 'B-F', 'vm_pu': 1.0, **t}],
        'linea': [linea(f'L-{s1}', 'B-F', f'B-{s1}-AT'), linea(f'L-{s2}', f'B-{s1}-AT', f'B-{s2}-AT')],
        'trafo2': [trafo(f'T-{s1}', f'B-{s1}-AT', f'B-{s1}-MT'), trafo(f'T-{s2}', f'B-{s2}-AT', f'B-{s2}-MT')]})
    inicio = rng.randint(2031, 2040)
    nuevos = {f'L-{s2}': inicio + rng.randint(0, 2), f'T-{s2}': inicio + rng.randint(3, 4)}
    cargas = {f'B-{s1}-MT': (round(rng.uniform(4, 9), 2), round(rng.uniform(1, 3), 2)),
              f'B-{s2}-MT': (round(rng.uniform(4, 9), 2), round(rng.uniform(1, 3), 2))}
    ids = ['B-F', f'B-{s1}-AT', f'B-{s1}-MT', f'B-{s2}-AT', f'B-{s2}-MT']
    flujo = ResultadoFlujo('abierto', True, tensiones_pu={b: round(rng.uniform(0.95, 1.02), 4) for b in ids})
    flujo.flujos = {e: (round(rng.uniform(5, 20), 3), round(rng.uniform(1, 6), 3))
                    for e in (f'L-{s1}', f'L-{s2}', f'T-{s1}', f'T-{s2}')}
    return {'red': red, 'flujo': flujo, 'cargas': cargas, 'ingresos': nuevos, 'inicio': inicio, 'area': area,
            'kv': {'B-F': kv_at, f'B-{s1}-AT': kv_at, f'B-{s1}-MT': kv_mt, f'B-{s2}-AT': kv_at, f'B-{s2}-MT': kv_mt}}


def _hojas(caso, alternativas=('ALT-A', 'ALT-B'), anios=None):
    anios = anios or (caso['inicio'], caso['inicio'] + 4)
    return [U.Hoja(a, n, caso['red'], caso['flujo'], caso['cargas'], caso['ingresos'])
            for a in alternativas for n in anios]


def _sin_convertidor(_nombre):
    return None


def _generar(tmp_path, caso, **kw):
    kw.setdefault('buscar', _sin_convertidor)
    return U.generar(tmp_path, kw.pop('hojas', None) or _hojas(caso), area=caso['area'], sistema='SIS-1', **kw)


def _leer(tmp_path, res):
    dxf = [f for f in res.ficheros if f.endswith('.dxf')]
    assert len(dxf) == 1, f'el unifilar no entregó su DXF: {res.ficheros}'
    assert (tmp_path / dxf[0]).stat().st_size > 0
    return ezdxf.readfile(tmp_path / dxf[0])


def _textos(lay, capa):
    return [e.dxf.text for e in lay.query(f'TEXT[layer=="{capa}"]')]


def _doble(tmp_path: Path, modo: str, nombre: str = 'convertidor_doble') -> Path:
    """Un convertidor de mentira con la misma línea de órdenes que el ODA File Converter."""
    carpeta = tmp_path / f'doble_{modo}'
    carpeta.mkdir()
    guion = carpeta / 'doble.py'
    guion.write_text(
        'import sys\nfrom pathlib import Path\n'
        'entrada, salida, modo = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[-1]\n'
        'if modo == "falla":\n    sys.exit(3)\n'
        'for dxf in entrada.glob("*.dxf"):\n'
        '    (salida / (dxf.stem + ".dwg")).write_bytes(b"" if modo == "vacio" else b"AC1032" + dxf.read_bytes()[:64])\n',
        encoding='utf-8')
    bat = carpeta / f'{nombre}.bat'
    bat.write_text(f'@"{sys.executable}" "{guion}" %1 %2 %3 %4 %5 %6 %7 {modo}\r\n', encoding='utf-8')
    return bat


# --------------------------------------------------------------------------- dependencia


def test_ezdxf_es_dependencia_obligatoria_con_version_y_huella():
    """107:RF-15 — el DXF es la entrega garantizada: ezdxf se importa, está fijada en las dependencias obligatorias,
    en requirements.txt y en el lock del núcleo con la huella de su rueda."""
    assert ezdxf.__version__ == '1.4.5'
    proyecto = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert 'ezdxf==1.4.5' in proyecto['dependencies']
    assert re.search(r'^ezdxf==1\.4\.5$', (RAIZ / 'requirements.txt').read_text(encoding='utf-8'), re.M)
    lock = (RAIZ / 'requirements-nucleo.lock').read_text(encoding='utf-8')
    for paquete in ('ezdxf', 'fonttools', 'pyparsing'):
        assert re.search(rf'^{paquete}==\S+ \\\n    --hash=sha256:[0-9a-f]{{64}}$', lock, re.M), paquete
    assert 'xlrd==2.0.2' in proyecto['optional-dependencies']['normativa']


# --------------------------------------------------------------------------- DXF


def test_una_hoja_a3_por_alternativa_y_anio_con_marco_y_rotulo(tmp_path):
    """107:RF-15 — una hoja (espacio papel) A3 por alternativa y año, con su marco y el rótulo del F-212."""
    caso = _caso(11)
    hojas = _hojas(caso)
    res = _generar(tmp_path, caso, hojas=hojas)
    doc = _leer(tmp_path, res)
    esperadas = {U.nombre_de_hoja(h.alternativa, h.anio) for h in hojas}
    assert set(doc.layout_names()) - {'Model'} == esperadas
    assert {h['hoja'] for h in res.manifiesto()['hojas']} == esperadas
    for h in hojas:
        lay = doc.layouts.get(U.nombre_de_hoja(h.alternativa, h.anio))
        assert (lay.dxf_layout.dxf.paper_width, lay.dxf_layout.dxf.paper_height) == U.A3_MM
        marcos = list(lay.query(f'LWPOLYLINE[layer=="{U.CAPAS["marco"]}"]'))
        assert len(marcos) == 1 and marcos[0].closed
        xs, ys = zip(*[(p[0], p[1]) for p in marcos[0].get_points()])
        assert 0 < min(xs) and max(xs) < U.A3_MM[0] and 0 < min(ys) and max(ys) < U.A3_MM[1]
        rotulo = _textos(lay, U.CAPAS['rotulo'])
        assert any('F-212' in t for t in rotulo) and 'DIAGRAMA UNIFILAR DE ALTERNATIVAS' in rotulo
        assert f'ÁREA DE DEMANDA: {caso["area"]}' in rotulo and f'ALTERNATIVA : {h.alternativa}' in rotulo
        assert f'AÑO : {h.anio}' in rotulo


def test_barras_transformadores_y_lineas_con_su_flujo(tmp_path):
    """107:RF-15 — cada línea y transformador con P y Q del flujo; las barras con su tensión nominal y calculada; las
    cargas con P y Q (F-212, art. 37 de la 217-2013)."""
    caso = _caso(23)
    res = _generar(tmp_path, caso)
    doc = _leer(tmp_path, res)
    lay = doc.layouts.get(U.nombre_de_hoja('ALT-A', caso['inicio']))
    red, flujo = caso['red'], caso['flujo']
    lineas, trafos, barras = (_textos(lay, U.CAPAS[c]) for c in ('linea', 'trafo', 'barra'))
    for e in red.de_tipo('linea'):
        p, q = flujo.flujos[e['id']]
        assert e['id'] in lineas and f'P = {p:.2f} MW  Q = {q:.2f} Mvar' in lineas
        assert f'{e["longitud_km"]:.2f} km' in lineas and f'{e["material"]} {e["seccion_mm2"]:.0f} mm2' in lineas
    for e in red.de_tipo('trafo2'):
        p, q = flujo.flujos[e['id']]
        assert e['id'] in trafos and f'P = {p:.2f} MW  Q = {q:.2f} Mvar' in trafos
        assert f'{e["sn_mva"]:.1f} MVA' in trafos and f'Vcc = {e["vk_percent"]:.2f} %' in trafos
        assert f'{e["vn_hv_kv"]:.1f}/{e["vn_lv_kv"]:.1f} kV' in trafos
        assert f'Taps: {e["tap_min"]} a {e["tap_max"]}' in trafos
    assert list(lay.query(f'CIRCLE[layer=="{U.CAPAS["trafo"]}"]'))
    for b, v in flujo.tensiones_pu.items():
        assert b in barras and f'Vn = {caso["kv"][b]:.1f} kV' in barras
        assert f'V calc. = {v * caso["kv"][b]:.2f} kV ({v:.4f} pu)' in barras
    cargas = _textos(lay, U.CAPAS['carga'])
    for b, (p, q) in caso['cargas'].items():
        assert f'Carga {b}: P = {p:.2f} MW  Q = {q:.2f} Mvar' in cargas


def test_convencion_de_colores_del_anio_de_ingreso(tmp_path):
    """107:RF-15 — el F-212 indica el año en que se incorpora cada elemento nuevo «de preferencia» con una convención de
    colores (217-2013, art. 37, pdf pág. 64): lo nuevo, con el color de su año y su rótulo; lo existente, con otro;
    y la leyenda dice qué color es cada año."""
    caso = _caso(37)
    res = _generar(tmp_path, caso)
    lay = _leer(tmp_path, res).layouts.get(U.nombre_de_hoja('ALT-B', caso['inicio'] + 4))
    color = {}
    for e in lay.query('TEXT'):
        color.setdefault(e.dxf.text, e.dxf.color)
    leyenda = {e.dxf.text: e.dxf.color for e in lay.query(f'TEXT[layer=="{U.CAPAS["leyenda"]}"]')}
    existente = color[caso['red'].de_tipo('linea')[0]['id']]
    assert leyenda.get('Existente') == existente
    for eid, anio in caso['ingresos'].items():
        assert color[eid] != existente, eid
        assert leyenda.get(f'Ingresa en {anio}') == color[eid]
        assert f'Ingresa en {anio}' in color
    if len(set(caso['ingresos'].values())) > 1:
        assert len({color[e] for e in caso['ingresos']}) == len(set(caso['ingresos'].values()))


def test_anios_del_f212():
    """107:RF-15 — el año 10 para cada alternativa; para la seleccionada, los años 1, 5, 10, 15, 20, 25 y 30."""
    inicio = random.Random(5).randint(2031, 2050)
    assert U.anios_f212(inicio, seleccionada=False) == (inicio + 9,)
    assert U.anios_f212(inicio, seleccionada=True) == tuple(inicio + n - 1 for n in (1, 5, 10, 15, 20, 25, 30))


def test_ingresos_de_las_altas_de_alternativa_y_de_programa():
    """107:RF-15 — el año de ingreso sale de los cambios (de alternativas o del programa); sin año, se avisa."""
    cambios = [{'accion': 'alta', 'elemento': {'id': 'L-9', 'tipo': 'linea'}, 'anio': 2033},
               {'accion': 'reemplazo', 'elemento': 'T-9', 'anio': '2035'},
               {'accion': 'baja', 'elemento': 'T-1', 'anio': 2035},
               {'accion': 'alta', 'elemento': 'C-1'}]
    ingresos, avisos = U.ingresos_de(cambios)
    assert ingresos == {'L-9': 2033, 'T-9': 2035}
    assert len(avisos) == 1 and 'C-1' in avisos[0]


def test_lo_que_falta_se_rotula_sin_dato_y_se_avisa(tmp_path):
    """107:RF-15 — sin material, sección ni taps, y sin flujo, nada se inventa: «sin dato» y su aviso."""
    caso = _caso(41, completa=False)
    sin_flujo = ResultadoFlujo('abierto', False, mensaje='no converge en la prueba')
    hojas = [U.Hoja('ALT-A', caso['inicio'], caso['red'], caso['flujo'], caso['cargas'], {}),
             U.Hoja('ALT-A', caso['inicio'] + 1, caso['red'], sin_flujo, caso['cargas'], {})]
    res = _generar(tmp_path, caso, hojas=hojas)
    doc = _leer(tmp_path, res)
    lay = doc.layouts.get(U.nombre_de_hoja('ALT-A', caso['inicio']))
    assert 'sin dato sin dato' in _textos(lay, U.CAPAS['linea'])
    assert 'Taps: sin dato' in _textos(lay, U.CAPAS['trafo'])
    avisos = ' | '.join(res.avisos)
    for e in caso['red'].de_tipo('linea'):
        assert f'la línea {e["id"]} no trae material, seccion_mm2' in avisos
    for e in caso['red'].de_tipo('trafo2'):
        assert f'el transformador {e["id"]} no trae sus taps' in avisos
    assert 'no converge en la prueba' in avisos
    lay2 = doc.layouts.get(U.nombre_de_hoja('ALT-A', caso['inicio'] + 1))
    assert 'P y Q: sin dato' in _textos(lay2, U.CAPAS['linea'])


def test_flujo_de_cada_linea_y_transformador_del_motor_abierto():
    """107:RF-15 — el motor abierto da P y Q en el extremo de envío de cada línea y transformador, que es lo que pinta
    el unifilar."""
    caso = _caso(53)
    red = caso['red']
    r = calcular(red, caso['cargas'])
    assert r.converge
    ids = {e['id'] for t in ('linea', 'trafo2') for e in red.de_tipo(t)}
    assert set(r.flujos) == ids
    total = sum(p for p, _q in caso['cargas'].values())
    primera = red.de_tipo('linea')[0]['id']
    assert r.flujos[primera][0] >= total  # la cabecera lleva la demanda y las pérdidas
    assert r.flujos[primera][0] == pytest.approx(total + r.perdidas_mw, rel=1e-3)


# --------------------------------------------------------------------------- DWG


def test_dwg_con_el_convertidor_del_perfil(tmp_path):
    """107:RF-15 — con el convertidor que declara el perfil (un doble), sale el DWG con contenido y los dos ficheros
    van al manifiesto y a la relación de sustento con su descripción y su uso."""
    caso = _caso(61)
    bat = _doble(tmp_path, 'ok')
    exp = tmp_path / 'expediente'
    res = _generar(exp, caso, perfil={'pit': {'convertidor_dwg': str(bat)}})
    dwg = [f for f in res.ficheros if f.endswith('.dwg')]
    assert res.dwg and len(dwg) == 1 and (exp / dwg[0]).stat().st_size > 0
    assert set(res.sustento) == set(res.ficheros) and len(res.ficheros) == 2
    assert all(d['descripcion'].strip() and d['uso'].strip() for d in res.sustento.values())
    assert not any('DWG no se generó' in a for a in res.avisos)
    assert sorted(p.relative_to(exp).as_posix() for p in exp.rglob('*') if p.is_file()) == sorted(res.ficheros)


def test_dwg_con_el_convertidor_del_path(tmp_path, monkeypatch):
    """107:RF-15 — sin perfil, el convertidor se busca en el PATH por su nombre, nunca en una ruta fija."""
    caso = _caso(67)
    bat = _doble(tmp_path, 'ok', nombre=U.CONVERTIDOR_EN_PATH)
    monkeypatch.setenv('PATH', str(bat.parent))
    exp = tmp_path / 'expediente'
    res = U.generar(exp, _hojas(caso), area=caso['area'], sistema='SIS-1', perfil={})
    assert res.dwg and any(f.endswith('.dwg') for f in res.ficheros)


@pytest.mark.parametrize('modo', ['ausente', 'falla', 'vacio', 'perfil_inexistente'])
def test_sin_convertidor_o_si_falla_la_entrega_queda_con_el_dxf(tmp_path, modo):
    """107:RF-15 — con el doble ausente, con el que falla y con el que deja un DWG vacío, la entrega queda completa con
    el DXF, el aviso que dice cómo obtener el DWG va al manifiesto y no queda ningún DWG."""
    caso = _caso(71)
    exp = tmp_path / 'expediente'
    perfil = {}
    if modo in ('falla', 'vacio'):
        perfil = {'pit': {'convertidor_dwg': str(_doble(tmp_path, modo))}}
    elif modo == 'perfil_inexistente':
        perfil = {'pit': {'convertidor_dwg': str(tmp_path / 'no_esta' / 'ODAFileConverter.exe')}}
    res = _generar(exp, caso, perfil=perfil)
    _leer(exp, res)
    assert not res.dwg and len(res.ficheros) == 1 and res.ficheros[0].endswith('.dxf')
    aviso = [a for a in res.manifiesto()['avisos'] if 'DWG no se generó' in a]
    assert len(aviso) == 1 and 'pit.convertidor_dwg' in aviso[0] and 'PATH' in aviso[0]
    assert not list(exp.rglob('*.dwg')) and not list(exp.rglob('*.DWG'))
    assert sorted(p.relative_to(exp).as_posix() for p in exp.rglob('*') if p.is_file()) == res.ficheros


def test_reemitir_sin_convertidor_no_deja_el_dwg_anterior(tmp_path):
    """107:RF-15 — un DWG de una emisión anterior no se queda junto a un DXF nuevo que no le corresponde."""
    caso = _caso(73)
    exp = tmp_path / 'expediente'
    primera = _generar(exp, caso, perfil={'pit': {'convertidor_dwg': str(_doble(tmp_path, 'ok'))}})
    assert primera.dwg
    segunda = _generar(exp, caso)
    assert not segunda.dwg and not list(exp.rglob('*.dwg'))


def test_la_ruta_del_convertidor_sale_del_perfil_o_del_path_y_no_del_codigo(tmp_path):
    """107:RF-15 — el convertidor se detecta y nunca se distribuye: su ruta sale del perfil o del PATH (por su
    nombre), ninguna ruta de la máquina está en el código y ningún ejecutable del convertidor va en el paquete."""
    fuente = (RAIZ / 'src' / 'convertersmartgrid' / 'pit' / 'unifilar.py').read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]', fuente)
    assert 'Program Files' not in fuente and 'ODA\\' not in fuente
    pedidos = []
    assert U.convertidor_dwg({}, buscar=lambda n: pedidos.append(n))[0] is None
    assert pedidos == [U.CONVERTIDOR_EN_PATH]
    exe = tmp_path / 'convertidor.exe'
    exe.write_bytes(b'doble')
    assert U.convertidor_dwg({'pit': {'convertidor_dwg': str(exe)}}, buscar=_sin_convertidor) == (str(exe), 'perfil')
    assert U.convertidor_dwg({}, buscar=lambda n: str(exe)) == (str(exe), 'PATH')
    paquete = RAIZ / 'src' / 'convertersmartgrid'
    assert not [p for p in paquete.rglob('*') if p.suffix.lower() in ('.exe', '.dll') and 'oda' in p.name.lower()]
