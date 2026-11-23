"""Spec 112: benchmark de redes anonimizado (112:RF-1, RF-2, RF-3, RF-10).

El benchmark de redes es un trío TXT, el formato que el conversor ya lee (plan de la 112, decisiones): así
el benchmark prueba también el lector y las reglas. Solo lleva las secciones y columnas de una lista cerrada; los
identificadores pasan por el mapa de seudónimos y las columnas de texto libre se quedan fuera. Todo con exports
sintéticos sorteados (``ExportSpec``), en las dos disposiciones: ningún dato de la distribuidora entra en ``tests/``.
"""
from __future__ import annotations

import importlib.util

import hashlib
import re
import socket
from collections import Counter
from pathlib import Path

import pytest

from convertersmartgrid.adaptadores.dataset import CymdistDataset
from convertersmartgrid.dominio.model import extract_sed_code
from convertersmartgrid.dominio.perfil_empresa import PerfilEmpresa
from synthetic_export import ExportSpec, write_export

DISPOSICIONES = ('reducido', 'completo')


def _origen(tmp_path: Path, *, semilla: int, layout: str, naming: str = 'net', feeders: int = 4):
    spec = ExportSpec(feeders=feeders, sections_per_feeder=6, loads_per_feeder=3, switches_per_feeder=1,
                      sectionalizers_per_feeder=1, seed=semilla, layout=layout, naming=naming)
    return spec, write_export(spec, tmp_path / 'origen')


def _generar(trio, destino: Path, *, semilla: int = 31, perfil: PerfilEmpresa | None = None):
    from convertersmartgrid.dominio.benchmarks.redes import anonimizar_red
    return anonimizar_red(*trio, destino, semilla=semilla, perfil=perfil)


def _leer(carpeta: Path) -> CymdistDataset:
    return CymdistDataset.from_files(carpeta / 'RED.txt', carpeta / 'CARGA.txt', carpeta / 'BD_Equipo.txt')


def _bytes(carpeta: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(carpeta.iterdir())}


def _identificadores(ds: CymdistDataset) -> set[str]:
    ids = set(ds.feeders) | set(ds.nodes) | set(ds.sections)
    for (sid, dev), fila in ds.customer_loads.items():
        ids |= {dev, fila.get('CustomerNumber', '')}
    return {i for i in ids if i}


@pytest.mark.parametrize('layout', DISPOSICIONES)
@pytest.mark.parametrize('semilla,naming', [(101, 'net'), (202, 'dash')])
def test_el_trio_anonimizado_se_lee_y_conserva_la_red(tmp_path, layout, semilla, naming):
    """112:RF-3, RF-2 — el lector abre el benchmark en su disposición y conserva tramos, fases, longitudes y cargas."""
    spec, trio = _origen(tmp_path, semilla=semilla, layout=layout, naming=naming)
    _generar(trio, tmp_path / 'bench')
    original, bench = CymdistDataset.from_files(*trio), _leer(tmp_path / 'bench')

    assert len(bench.feeders) == len(original.feeders) == spec.total_feeders
    assert sorted(len(v) for v in bench.feeders.values()) == sorted(len(v) for v in original.feeders.values())
    assert len(bench.sections) == len(original.sections)
    assert len(bench.nodes) == len(original.nodes)
    assert len(bench.customer_loads) == len(original.customer_loads)
    assert len(bench.load_placements) == len(original.load_placements)
    assert len(bench.switch_settings) == len(original.switch_settings)
    assert len(bench.sectionalizer_settings) == len(original.sectionalizer_settings)
    assert len(bench.intermediate_nodes) == len(original.intermediate_nodes)
    assert Counter(s['Phase'] for s in bench.sections.values()) == \
        Counter(s['Phase'] for s in original.sections.values())
    assert sorted(float(c['Length']) for c in bench.line_configurations.values()) == \
        sorted(float(c['Length']) for c in original.line_configurations.values())
    assert sorted(float(c['Value1']) for c in bench.customer_loads.values()) == \
        sorted(float(c['Value1']) for c in original.customer_loads.values())
    # Ningún identificador original sobrevive en el benchmark (RF-2).
    texto = '\n'.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'bench').iterdir())
    for ident in _identificadores(original):
        assert not re.search(rf'(?<![\w-]){re.escape(ident)}(?![\w-])', texto), ident


@pytest.mark.parametrize('layout', DISPOSICIONES)
def test_la_topologia_cuadra_tramo_a_tramo(tmp_path, layout):
    """112:RF-3 — cada alimentador conserva su grafo: los grados de sus nudos y sus cabeceras."""
    _, trio = _origen(tmp_path, semilla=303, layout=layout)
    _generar(trio, tmp_path / 'bench')
    original, bench = CymdistDataset.from_files(*trio), _leer(tmp_path / 'bench')

    def firmas(ds):
        salida = []
        for red, tramos in ds.feeders.items():
            grados = Counter()
            for sid in tramos:
                grados[ds.sections[sid]['FromNodeID']] += 1
                grados[ds.sections[sid]['ToNodeID']] += 1
            cabecera = ds.sources[red]['NodeID']
            salida.append((len(tramos), tuple(sorted(grados.values())), grados.get(cabecera, 0)))
        return sorted(salida)

    assert firmas(bench) == firmas(original)
    assert set(bench.headnodes.values()) == set(bench.feeders)


@pytest.mark.parametrize('layout', DISPOSICIONES)
def test_bd_equipo_lleva_los_parametros_de_cada_tramo(tmp_path, layout):
    """112:RF-3 — el tipo de cada tramo, con otro nombre, trae las mismas impedancias y la misma ampacidad."""
    _, trio = _origen(tmp_path, semilla=404, layout=layout)
    _generar(trio, tmp_path / 'bench')
    original, bench = CymdistDataset.from_files(*trio), _leer(tmp_path / 'bench')

    def parametros(ds):
        tipos = {f['ID']: tuple(float(f[c]) for c in ('R1', 'R0', 'X1', 'X0', 'B1', 'B0', 'Amps'))
                 for t in ('LINE', 'CONCENTRIC NEUTRAL CABLE', 'CABLE') for f in ds.equipment_tables.get(t, ())}
        return Counter(tipos.get(c['LineCableID']) for c in ds.line_configurations.values())

    assert parametros(bench) == parametros(original)


def test_el_texto_libre_y_las_columnas_fuera_de_la_lista_no_salen(tmp_path):
    """112:RF-10 — descripciones, etiquetas y comentarios no entran; las columnas omitidas se anotan por nombre."""
    _, trio = _origen(tmp_path, semilla=505, layout='reducido')
    red = trio[0]
    lineas = red.read_text(encoding='utf-8').splitlines()
    # Un texto de la empresa en la etiqueta de un nudo, en la descripción de un alimentador y en el comentario.
    secreto = 'Informe de planificacion de la gerencia tecnica'
    i = lineas.index('[NODE]') + 2
    campos = lineas[i].split(',')
    campos[3] = secreto
    lineas[i] = ','.join(campos)
    j = next(k for k, l in enumerate(lineas) if l.startswith('FEEDER='))
    campos = lineas[j].split(',')
    campos[4] = secreto
    lineas[j] = ','.join(campos)
    lineas[2] = secreto
    red.write_text('\n'.join(lineas) + '\n', encoding='utf-8')

    informe = _generar(trio, tmp_path / 'bench')
    for p in (tmp_path / 'bench').iterdir():
        assert secreto not in p.read_text(encoding='utf-8'), p.name
    assert 'TagText' in informe.columnas_omitidas['RED.txt']['NODE']
    assert 'Description' in informe.columnas_omitidas['RED.txt']['SECTION']
    assert 'GENERAL' in informe.secciones_omitidas['RED.txt']
    # Las omitidas van por nombre, nunca por valor.
    assert secreto not in repr(informe)


def test_la_generacion_no_abre_la_red(tmp_path, monkeypatch):
    """112:RF-1 — el benchmark se crea en local: con los sockets prohibidos, se genera igual."""
    _, trio = _origen(tmp_path, semilla=606, layout='completo')

    class SinRed(socket.socket):
        def __init__(self, *a, **k):
            raise AssertionError('la generación del benchmark intentó abrir un socket')

    monkeypatch.setattr(socket, 'socket', SinRed)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: (_ for _ in ()).throw(AssertionError('red')))
    _generar(trio, tmp_path / 'bench')
    assert (tmp_path / 'bench' / 'RED.txt').exists()


@pytest.mark.parametrize('layout', DISPOSICIONES)
def test_misma_semilla_mismos_bytes(tmp_path, layout):
    """112:RF-2 — reproducible: la misma semilla y el mismo origen dan los mismos bytes; otra semilla, otros."""
    _, trio = _origen(tmp_path, semilla=707, layout=layout)
    _generar(trio, tmp_path / 'a', semilla=9)
    _generar(trio, tmp_path / 'b', semilla=9)
    _generar(trio, tmp_path / 'c', semilla=10)
    assert _bytes(tmp_path / 'a') == _bytes(tmp_path / 'b')
    assert _bytes(tmp_path / 'a')['RED.txt'] != _bytes(tmp_path / 'c')['RED.txt']


@pytest.mark.parametrize('layout', DISPOSICIONES)
def test_un_solo_alimentador(tmp_path, layout):
    """112:RF-3 — caso límite de la spec: una red con un solo alimentador."""
    _, trio = _origen(tmp_path, semilla=808, layout=layout, feeders=1)
    _generar(trio, tmp_path / 'bench')
    bench = _leer(tmp_path / 'bench')
    assert len(bench.feeders) == 1 and bench.sections


def _codigos_sed(ds: CymdistDataset) -> list[str]:
    return [extract_sed_code(f.get('CustomerNumber', ''), dev, sid) for (sid, dev), f in ds.customer_loads.items()]


@pytest.mark.parametrize('perfil', [
    PerfilEmpresa(nombre='uno', patron_sed_medicion=r'^SE1\d{3}$'),
    PerfilEmpresa(nombre='dos', patron_sed_medicion=None, crs_origen='EPSG:32719', escala_diagrama=7.5),
], ids=['con_medicion', 'sin_medicion'])
@pytest.mark.parametrize('layout', DISPOSICIONES)
def test_perfil_neutro_con_los_prefijos_traducidos(tmp_path, perfil, layout):
    """112:RF-3, RF-2 — las SED de medición siguen siéndolo con el perfil neutro; el perfil no delata a la empresa."""
    _, trio = _origen(tmp_path, semilla=909, layout=layout)
    informe = _generar(trio, tmp_path / 'bench', perfil=perfil)
    original, bench = CymdistDataset.from_files(*trio), _leer(tmp_path / 'bench')

    neutro = informe.perfil_neutro
    assert neutro.crs_origen is None and neutro.escala_diagrama is None
    assert neutro.nombre == 'benchmark'
    cod_o, cod_b = _codigos_sed(original), _codigos_sed(bench)
    # Una SED por código: las que compartían código lo siguen compartiendo.
    assert sorted(Counter(cod_o).values()) == sorted(Counter(cod_b).values())
    if perfil.patron_sed_medicion:
        medicion_o = sum(bool(re.search(perfil.patron_sed_medicion, c)) for c in cod_o)
        medicion_b = sum(bool(re.search(neutro.patron_sed_medicion, c)) for c in cod_b)
        assert medicion_o == medicion_b > 0
    else:
        assert neutro.patron_sed_medicion is None
    assert neutro.forma_alimentador and all(re.search(neutro.forma_alimentador, r) for r in bench.feeders)


# --------------------------------------------------------------------------- T4: reproducción del estudio (112:RF-3)

def _reproducir(trio, carpeta: Path, informe, perfil=None, tolerancia=None):
    from convertersmartgrid.adaptadores.benchmarks.reproduccion import reproducir_red
    return reproducir_red(trio, carpeta, mapa=informe.mapa, perfil=perfil, perfil_neutro=informe.perfil_neutro,
                          tolerancia=tolerancia)


@pytest.mark.parametrize('semilla,layout,perfil', [
    (1201, 'reducido', None),
    (1302, 'completo', PerfilEmpresa(nombre='uno', patron_sed_medicion=r'^SE1\d{3}$')),
], ids=['red_a_reducida', 'red_b_completa_con_medicion'])
def test_el_estudio_se_reproduce_en_dos_redes(tmp_path, semilla, layout, perfil):
    """112:RF-3 — tensiones, cargas, recuento y veredicto del oráculo iguales dentro de la tolerancia por defecto."""
    pytest.importorskip('pandapower')
    _, trio = _origen(tmp_path, semilla=semilla, layout=layout)
    informe = _generar(trio, tmp_path / 'bench', perfil=perfil)
    rep = _reproducir(trio, tmp_path / 'bench', informe, perfil=perfil)
    assert rep.reproduce, rep.motivos
    assert rep.tolerancia.v_pu == 0.005 and rep.tolerancia.corriente_rel == 0.01
    assert rep.tolerancia.fuente == 'por defecto'
    assert rep.metricas_original and set(rep.metricas_original) == set(rep.metricas_benchmark)
    # Las métricas van por seudónimo: ningún nombre original sale en el informe.
    originales = set(CymdistDataset.from_files(*trio).feeders)
    assert not originales & set(rep.metricas_original)
    assert all(m['convergio'] for m in rep.metricas_benchmark.values())


def test_si_no_reproduce_dice_que_magnitud_y_que_elemento(tmp_path):
    """112:RF-3 — un benchmark que no da el mismo estudio se rechaza nombrando la magnitud y el seudónimo."""
    pytest.importorskip('pandapower')
    from convertersmartgrid.adaptadores.benchmarks.reproduccion import ReproduccionFallida, exigir
    _, trio = _origen(tmp_path, semilla=1403, layout='reducido')
    informe = _generar(trio, tmp_path / 'bench')
    # Se estropea el benchmark: todas las cargas, al triple.
    carga = tmp_path / 'bench' / 'CARGA.txt'
    lineas = carga.read_text(encoding='utf-8').splitlines()
    cab = next(l for l in lineas if l.startswith('FORMAT_CUSTOMERLOADS=')).split('=', 1)[1].split(',')
    i = cab.index('Value1')
    nuevas, en_clientes = [], False
    for l in lineas:
        if l.startswith('['):
            en_clientes = l == '[CUSTOMER LOADS]'
        elif en_clientes and not l.startswith('FORMAT_'):
            c = l.split(',')
            c[i] = f'{float(c[i]) * 3:.6f}'
            l = ','.join(c)
        nuevas.append(l)
    carga.write_text('\n'.join(nuevas) + '\n', encoding='utf-8')

    rep = _reproducir(trio, tmp_path / 'bench', informe)
    assert not rep.reproduce
    assert any(m.magnitud in {'v_min_pu', 'carga_linea_max_pct', 'carga_trafo_max_pct'} for m in rep.motivos)
    assert all(m.elemento.startswith('BA') for m in rep.motivos)
    with pytest.raises(ReproduccionFallida, match='BA'):
        exigir(rep)


def test_reproduce_con_la_tolerancia_declarada_por_el_estudio(tmp_path):
    """112:RF-3 — la tolerancia del estudio, si la declara, sustituye a la de por defecto y dice de dónde sale."""
    from convertersmartgrid.adaptadores.benchmarks.reproduccion import Tolerancia, tolerancia_para
    assert tolerancia_para(None) == Tolerancia()
    t = tolerancia_para({'v_pu': 0.01, 'corriente_rel': 0.02, 'fuente': 'spec 011'})
    assert (t.v_pu, t.corriente_rel, t.fuente) == (0.01, 0.02, 'spec 011')
    with pytest.raises(ValueError):
        tolerancia_para({'v_pu': -1})


def test_el_estudio_se_reproduce_en_la_red_real(tmp_path):
    """112:RF-3 — con las tres variables ``CSG_*``, el benchmark de la red real reproduce su estudio (salida en tmp)."""
    import os
    pytest.importorskip('pandapower')
    rutas = [os.environ.get(k, '').strip() for k in ('CSG_RED', 'CSG_LOADS', 'CSG_EQUIPMENT')]
    if not all(rutas) or not all(Path(r).is_file() for r in rutas):
        pytest.skip('faltan CSG_RED, CSG_LOADS o CSG_EQUIPMENT: sin datos reales no se reproduce la red real')
    from convertersmartgrid.dominio.perfil_empresa import cargar_perfil
    perfil = cargar_perfil()
    trio = tuple(Path(r) for r in rutas)
    informe = _generar(trio, tmp_path / 'bench', perfil=perfil)
    rep = _reproducir(trio, tmp_path / 'bench', informe, perfil=perfil)
    assert rep.reproduce, [m.texto() for m in rep.motivos[:20]]
    assert len(rep.metricas_original) >= 2


# --------------------------------------------------------------------------- T7: manifiesto y emisión atómica (112:RF-1, RF-5)

SECRETA = 7_340_112_998_001_234_567


def _generar_todo(trio, destino: Path, raiz: Path, **kw):
    from convertersmartgrid.adaptadores.benchmarks import generar_benchmark
    return generar_benchmark(*trio, destino, semilla=SECRETA, raiz=raiz, **kw)


def test_manifiesto_con_todo_lo_que_pide_la_spec(tmp_path):
    """112:RF-5 — huella del origen, versión, semilla pública, transformaciones, omitidas, tolerancia, métricas y huellas."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.manifiesto'), 'falta convertersmartgrid.adaptadores.benchmarks.manifiesto'
    pytest.importorskip('pandapower')
    import json

    from convertersmartgrid.dominio.benchmarks.semilla import leer_secreta, semilla_publica
    _, trio = _origen(tmp_path, semilla=2101, layout='reducido')
    manifiesto = _generar_todo(trio, tmp_path / 'bench', tmp_path / 'local')
    leido = json.loads((tmp_path / 'bench' / 'manifiesto.json').read_text(encoding='utf-8'))
    assert leido == manifiesto
    assert len(manifiesto['origen']['huella']) == 64
    assert manifiesto['generador']['version']
    assert manifiesto['semilla_publica'] == semilla_publica(SECRETA)
    assert leer_secreta(manifiesto['origen']['huella'], raiz=tmp_path / 'local') == SECRETA
    assert manifiesto['transformaciones'] and manifiesto['columnas_omitidas']['RED.txt']['NODE']
    assert manifiesto['tolerancia']['fuente'] == 'por defecto' and manifiesto['tolerancia']['v_pu'] == 0.005
    assert set(manifiesto['metricas_referencia']['red']) == {'original', 'benchmark'}
    assert manifiesto['perfil_neutro']['nombre'] == 'benchmark'
    # Derivado de una red: solo para uso local (aclaración de RF-13 y RF-14); publicarlo lo rechaza la T13.
    assert manifiesto['uso_local'] is True
    for nombre, h in manifiesto['ficheros'].items():
        assert hashlib.sha256((tmp_path / 'bench' / nombre).read_bytes()).hexdigest() == h
    assert set(manifiesto['ficheros']) | {'manifiesto.json'} == {p.name for p in (tmp_path / 'bench').iterdir()}
    for p in (tmp_path / 'bench').iterdir():
        assert str(SECRETA) not in p.read_text(encoding='utf-8')


def test_manifiesto_dos_generaciones_mismas_huellas(tmp_path):
    """112:RF-5 — generar dos veces el mismo origen con la misma semilla da los mismos bytes, manifiesto incluido."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.manifiesto'), 'falta convertersmartgrid.adaptadores.benchmarks.manifiesto'
    pytest.importorskip('pandapower')
    _, trio = _origen(tmp_path, semilla=2202, layout='completo')
    a = _generar_todo(trio, tmp_path / 'a', tmp_path / 'local')
    b = _generar_todo(trio, tmp_path / 'b', tmp_path / 'local')
    assert a == b
    assert _bytes(tmp_path / 'a') == _bytes(tmp_path / 'b')


@pytest.mark.parametrize('fallo', ['fuga', 'reproduccion'])
def test_manifiesto_nada_a_medias_si_algo_falla(tmp_path, monkeypatch, fallo):
    """112:RF-1, RF-4, RF-5 — con una fuga o sin reproducir, el destino no aparece y no queda ninguna carpeta temporal."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.manifiesto'), 'falta convertersmartgrid.adaptadores.benchmarks.manifiesto'
    pytest.importorskip('pandapower')
    from convertersmartgrid.adaptadores.benchmarks import reidentificacion, reproduccion
    _, trio = _origen(tmp_path, semilla=2303, layout='reducido')
    if fallo == 'fuga':
        monkeypatch.setattr(reidentificacion, 'revisar', lambda *a, **k: [
            reidentificacion.Hallazgo('identificador', 'RED.txt', 3, 'un identificador del origen')])
        error = reidentificacion.FugaDetectada
    else:
        real = reproduccion.reproducir_red

        def peor(*a, **k):
            inf = real(*a, **k)
            inf.motivos.append(reproduccion.Motivo('v_min_pu', 'BA1', 0.98, 0.9, 0.005))
            return inf
        monkeypatch.setattr(reproduccion, 'reproducir_red', peor)
        error = reproduccion.ReproduccionFallida
    with pytest.raises(error):
        _generar_todo(trio, tmp_path / 'salida' / 'bench', tmp_path / 'local')
    assert not (tmp_path / 'salida' / 'bench').exists()
    salida = tmp_path / 'salida'
    assert not salida.exists() or not list(salida.iterdir()), 'queda una carpeta temporal a medias'


def test_manifiesto_no_pisa_un_benchmark_existente(tmp_path):
    """112:RF-5 — un benchmark ya emitido no se sobrescribe: su manifiesto es su contrato."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.manifiesto'), 'falta convertersmartgrid.adaptadores.benchmarks.manifiesto'
    _, trio = _origen(tmp_path, semilla=2404, layout='reducido')
    (tmp_path / 'bench').mkdir()
    with pytest.raises(FileExistsError):
        _generar_todo(trio, tmp_path / 'bench', tmp_path / 'local')


def test_manifiesto_origen_neutro_lejos_del_original(tmp_path):
    """112:RF-2, RF-4 — una red que ya está en el primer origen neutro se lleva a otro, a más de 100 km de su recuadro:
    el control de coordenadas no rechaza el benchmark limpio y la elección (de una lista fija) no delata el original."""
    from convertersmartgrid.dominio.benchmarks import seudonimos as Z
    assert hasattr(Z, 'origen_lejano'), 'falta seudonimos.origen_lejano'
    assert Z.origen_lejano(None, (0.0, 0.0, 1.0, 1.0)) == Z.ORIGENES_NEUTROS[0]
    ox, oy = Z.ORIGENES_NEUTROS[0]
    recuadro = (ox - 2000.0, oy - 1500.0, ox + 2500.0, oy + 1000.0)
    elegido = Z.origen_lejano(recuadro, (-3000.0, -3000.0, 3000.0, 3000.0))
    assert elegido != Z.ORIGENES_NEUTROS[0] and elegido in Z.ORIGENES_NEUTROS
    assert abs(elegido[1] - oy) > Z.DISTANCIA_MINIMA_M
    with pytest.raises(ValueError, match='ningún origen neutro'):
        Z.origen_lejano((0.0, 0.0, 1e8, 1e8), (-1.0, -1.0, 1.0, 1.0))
    puntos = [(ox + 10.0, oy + 20.0), (ox + 400.0, oy - 30.0), (ox - 50.0, oy + 90.0)]
    movidos = Z.transformar_coordenadas(puntos, semilla=5, origen=elegido)
    cx = sum(x for x, _ in movidos) / 3
    cy = sum(y for _, y in movidos) / 3
    assert abs(cx - elegido[0]) < 1e-6 and abs(cy - elegido[1]) < 1e-6
