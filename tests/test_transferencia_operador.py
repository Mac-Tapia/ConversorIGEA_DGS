"""Spec 098: la transferencia de carga que hizo el operador en DIgSILENT, en la calibración, el escaneo y las obras.

Caso real (2026-11-07, ``20261105-124711_CSG_TXT_CA101_CHN102``): el operador pasó parte de CA101 a CHN102 con dos tramos
nuevos y un punto abierto. La recalibración de julio, con medidas de antes de la transferencia, terminó con «pérdidas
activas negativas en CA101 (-1 271,2 kW)». Aquí, con ``fake_pf`` y la topología viva de sus ``ElmFeeder``: X cede su
última SED a Y por un tramo nuevo y abre el tramo que la unía. Las cifras se parecen a las de CA101: X medido en
6 600 kW antes de la transferencia, Y en 2 728 kW.
"""
from __future__ import annotations

import copy
import random

import fake_pf
import pytest
from apoyo import cargar_herramienta, contexto_nativo
from test_ajuste_cabecera_guion import _plan

from convertersmartgrid import transferencia_operador as to


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_transferencia_guion', tools_en_path=True)


@pytest.fixture(scope='module')
def tpf(guion):
    return guion.transferencia_pf


def _red(feeders=('F1', 'F2'), n=6, kw=None):
    """Red con sus SED etiquetadas por su alimentador, como las deja el DGS (``p:alimentador``)."""
    app = fake_pf.proyecto(alimentadores=feeders, cargas_por_alim=n, bt=True, flujo=True, escenario=True,
                           kva=lambda f, i: 3000.0)
    app.ldf.rp, app.ldf.rq = 0.002, 0.004
    kw = kw or {}
    for c in app.proyecto.GetContents('*.ElmLod', 1):
        f, _sed = c.loc_name.split('_')
        object.__setattr__(c, 'p:alimentador', f)
        c.plini = kw.get(c.loc_name, kw.get(f, 0.5))
    app.topologia_viva = True
    app.servicio_en_escenario = True
    app.escrituras.clear()
    return app


def _obj(app, clase, nombre):
    return next(o for o in app.proyecto.GetContents(f'*.{clase}', 1) if o.loc_name == nombre)


def _caso(app, nombre):
    return next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre)


def _transferir(app, abrir, de_barra, a_barra, nombre):
    """El operador, a mano en «Sin proyecto»: un tramo nuevo de ``de_barra`` a ``a_barra`` y ``abrir`` fuera de servicio."""
    red = app.proyecto.GetContents('*.ElmNet', 1)[0]
    ln = red.CreateObject('ElmLne', nombre)
    ln.typ_id, ln.nlnum, ln.outserv, ln.dline = _obj(app, 'ElmLne', abrir).typ_id, 1, 0, 0.3
    for lado, barra in ((0, de_barra), (1, a_barra)):
        cub = _obj(app, 'ElmTerm', barra).CreateObject('StaCubic', f'c{lado}_{nombre}')
        cub.obj_id, cub.obj_bus = ln, lado
        object.__setattr__(ln, f'bus{lado + 1}', cub)
    _obj(app, 'ElmLne', abrir).outserv = 1
    return ln


def _banco(app, barra, nombre):
    sh = _obj(app, 'ElmTerm', barra).CreateObject('ElmShnt', nombre)
    sh.qcapn, sh.ncapa, sh.outserv = 0.3, 1, 0
    cub = _obj(app, 'ElmTerm', barra).CreateObject('StaCubic', f'c_{nombre}')
    cub.obj_id = sh
    sh.bus1 = cub
    return sh


def _planes(objetivos, tramos):
    out = []
    for f, kw in objetivos.items():
        p = copy.deepcopy(_plan(kw=kw, kvar=kw * 0.3))
        p['feeder'] = f
        p['objetivo'].update(kw=kw, medidor=f'M_{f}', alimentador=f, fecha='2026-07-27 08:45:00')
        p['native_action_context'] = contexto_nativo('P', [f], 'ajuste')
        p['tramos_dgs'] = sorted(tramos)
        p['abiertos_dgs'] = {}
        p['fecha_importacion'] = '2026-11-05'
        out.append(p)
    return out


def _caso_ca101(guion):
    """X (6 SED de ~1,1 MW) cede su SED del final a Y, con su banco; las medidas son de antes de la transferencia."""
    kw = {'F1': 1.06, 'F1_S6': 1.3, 'F2': 0.455}
    app = _red(kw=kw)
    tramos = {o.loc_name for o in app.proyecto.GetContents('*.ElmLne', 1)}
    objetivos = {'F1': 6600.0, 'F2': 2728.0}
    primera = guion.ejecutar_proyecto(app, _planes(objetivos, tramos))          # crea los casos, sin transferencia
    assert all(rc == 0 for _i, rc in primera), primera
    import sys

    informe, rc = sys.modules['casos_pf'].preparar_con(                   # «Con proyecto», copia de «Sin proyecto»
        app, {'project': 'P', 'feeders': ['F1', 'F2'], 'caso_base_sin_verificar': {}})
    assert rc == 0, informe
    _caso(app, 'Sin proyecto').Activate()
    _banco(app, 'F1_B6', 'EBC_1')
    nuevo = _transferir(app, 'F1_L6', 'F2_B6', 'F1_B6', 'SEC_NUEVO_a')
    app.GetActiveScenario().Save()
    _caso(app, 'Caso base').Activate()
    return app, _planes(objetivos, tramos), nuevo


def test_sin_desactivar_da_las_perdidas_negativas_del_caso_real(guion, tpf, monkeypatch):
    """098:RF-3 — el control: con la transferencia puesta, X cuenta una SED que entra por Y y salen pérdidas
    negativas, como CA101 el 2026-11-07. Sin el cambio de la 098, la calibración termina así."""
    app, planes, _nuevo = _caso_ca101(guion)
    monkeypatch.setattr(tpf.RedDeLaFuente, 'preparar', lambda self, *a, **k: None)
    (x, _rcx), (_y, _rcy) = guion.ejecutar_proyecto(app, planes)
    assert not x['cuadrado'] and 'pérdidas activas negativas en F1' in (x['motivo'] or ''), x.get('motivo')


def test_se_calibra_con_los_alimentadores_completos_y_la_transferencia_vuelve(guion):
    """098:RF-1, 098:RF-2, 098:RF-3, 098:RF-5, 098:RF-6, 098:RF-7, 098:RF-10 — se abre el tramo nuevo y se cierra el
    que abrió el operador mientras se calibra: cada cabecera con todas sus SED por etiqueta, sin pérdidas negativas.
    Al terminar la transferencia está como la dejó, en «Sin proyecto» y en «Con proyecto», con la evidencia."""
    app, planes, nuevo = _caso_ca101(guion)
    vistos = []
    antes = app.ldf.Execute

    def flujo():
        vistos.append((int(_obj(app, 'ElmLne', 'F1_L6').outserv), int(nuevo.outserv)))
        return antes()

    app.ldf.Execute = flujo
    (x, rcx), (y, rcy) = guion.ejecutar_proyecto(app, planes)
    assert (rcx, rcy) == (0, 0), (x.get('motivo'), y.get('motivo'))
    assert x['cuadrado'] and y['cuadrado']
    assert x['perdidas']['kw'] > 0 and y['perdidas']['kw'] > 0
    assert (0, 1) in vistos, 'se calibró con la transferencia puesta'
    # Al terminar, como la dejó el operador, comprobado en el informe.
    t = x['transferencias_del_operador']
    assert t['zonas'] == [{**t['zonas'][0], 'desde': 'F1', 'hacia': 'F2', 'sed': ['F1_S6'], 'n_sed': 1, 'motivo': None}]
    assert {(c['nombre'], c['atributo']) for c in t['cambios']} == {('SEC_NUEVO_a', 'outserv'), ('F1_L6', 'outserv')}
    assert t['restituida'] and all(e['ok'] for e in t['evidencia'])
    assert y['transferencias_del_operador']['zonas'][0]['hacia'] == 'F2'
    assert any('098:RF-5' in a and 'Sin proyecto' in a for a in x['avisos'])
    assert any('Transferencia del operador de F1 a F2' in a and 'F1_S6' in a for a in x['avisos'])
    assert not any('098:RF-4' in a for a in x['avisos'])          # medida de julio, importado en noviembre: de antes
    for caso in ('Sin proyecto', 'Con proyecto'):
        _caso(app, caso).Activate()
        assert int(_obj(app, 'ElmLne', 'F1_L6').outserv) == 1 and int(nuevo.outserv) == 0, caso
        assert 'F1_S6' in {c.loc_name for c in _obj(app, 'ElmFeeder', 'F2').GetObjs('ElmLod')}, caso
    # La SED transferida escala con el factor de su alimentador de origen.
    s6 = _obj(app, 'ElmLod', 'F1_S6')
    assert s6.scale0 == pytest.approx(_obj(app, 'ElmLod', 'F1_S2').scale0)
    assert not list((tpf_fichero(guion, planes[0])).parent.glob('*_red_de_la_fuente.json'))


def tpf_fichero(guion, plan):
    return guion.transferencia_pf.fichero(plan)


def test_si_algo_revienta_la_transferencia_vuelve_igual(guion, monkeypatch):
    """098:RF-5 — una excepción a mitad de la calibración no deja la transferencia desactivada ni el registro."""
    app, planes, nuevo = _caso_ca101(guion)
    durante = {}

    def revienta(app_, planes_, **k):
        durante['estado'] = (int(_obj(app, 'ElmLne', 'F1_L6').outserv), int(nuevo.outserv))
        raise RuntimeError('DIgSILENT se cerró')

    monkeypatch.setattr(guion, '_ejecutar_proyecto', revienta)
    with pytest.raises(RuntimeError):
        guion.ejecutar_proyecto(app, planes)
    assert durante['estado'] == (0, 1)
    _caso(app, 'Sin proyecto').Activate()
    assert int(_obj(app, 'ElmLne', 'F1_L6').outserv) == 1 and int(nuevo.outserv) == 0
    assert not tpf_fichero(guion, planes[0]).exists()


def test_si_la_orden_muere_la_siguiente_la_restituye(guion, tpf):
    """098:RF-5 — lo anotado en disco antes de tocar se deshace al empezar la orden siguiente, y se dice."""
    app, planes, nuevo = _caso_ca101(guion)
    proyecto = app.proyecto
    _caso(app, 'Sin proyecto').Activate()
    red = tpf.RedDeLaFuente(app, planes[0])
    red.preparar(guion.Alimentadores(app, proyecto, ['F1', 'F2']), _caso(app, 'Sin proyecto'), ['F1', 'F2'])
    assert int(nuevo.outserv) == 1 and tpf.fichero(planes[0]).exists()      # la orden muere aquí
    _caso(app, 'Caso base').Activate()
    (x, rc), _ = guion.ejecutar_proyecto(app, planes)
    assert rc == 0, x.get('motivo')
    assert any('no terminó' in a and '098:RF-5' in a for a in x['avisos'])
    _caso(app, 'Sin proyecto').Activate()
    assert int(_obj(app, 'ElmLne', 'F1_L6').outserv) == 1 and int(nuevo.outserv) == 0
    assert not tpf.fichero(planes[0]).exists()


def test_si_no_se_puede_desactivar_se_calibra_como_esta(guion, tpf, monkeypatch):
    """098:RF-8 — un fallo al reconocer o desactivar la transferencia no impide calibrar: se dice y la red queda como
    la dejó el operador."""
    app, planes, nuevo = _caso_ca101(guion)

    def falla(self, *a, **k):
        raise RuntimeError('API ocupada')

    monkeypatch.setattr(tpf.RedDeLaFuente, 'preparar', falla)
    (x, _rc), _ = guion.ejecutar_proyecto(app, planes)
    assert any('098:RF-8' in a and 'API ocupada' in a for a in x['avisos'])
    _caso(app, 'Sin proyecto').Activate()
    assert int(_obj(app, 'ElmLne', 'F1_L6').outserv) == 1 and int(nuevo.outserv) == 0


def test_sin_transferencia_no_cambia_nada(guion):
    """098:RF-1 — un proyecto sin transferencias: ni un tramo tocado, ni aviso, ni registro."""
    app = _red(feeders=('A', 'B', 'C'))
    tramos = {o.loc_name for o in app.proyecto.GetContents('*.ElmLne', 1)}
    planes = _planes({'A': 1500.0, 'B': 1500.0, 'C': 1500.0}, tramos)
    guion.ejecutar_proyecto(app, planes)
    app.escrituras.clear()
    resultados = guion.ejecutar_proyecto(app, planes)
    assert all('transferencias_del_operador' not in i for i, _rc in resultados)
    assert not [e for e in app.escrituras if getattr(e[0], '_clase', '') in ('ElmLne', 'ElmCoup', 'StaSwitch')]


def test_tres_alimentadores_con_una_cadena_de_transferencias(guion):
    """098:RF-1, 098:RF-2, 098:RF-3, 098:RF-15 — A cede a B y B cede a C (con lo que recibió de A): cada zona vuelve a su
    alimentador mientras se calibra y todo queda como estaba. Tamaños sorteados."""
    rnd = random.Random(98)
    n = rnd.randint(5, 8)
    app = _red(feeders=('A', 'B', 'C'), n=n, kw={'A': 0.4, 'B': 0.35, 'C': 0.3})
    tramos = {o.loc_name for o in app.proyecto.GetContents('*.ElmLne', 1)}
    objetivos = {'A': 0.4 * n * 1000 * 1.01, 'B': 0.35 * n * 1000 * 1.01, 'C': 0.3 * n * 1000 * 1.01}
    planes = _planes(objetivos, tramos)
    guion.ejecutar_proyecto(app, planes)
    _caso(app, 'Sin proyecto').Activate()
    # A: su última SED pasa a B. B: sus dos últimas (y la de A colgada de ellas) pasan a C.
    t1 = _transferir(app, f'A_L{n}', f'B_B{n - 2}', f'A_B{n}', 'NUEVO_AB')
    t2 = _transferir(app, f'B_L{n - 1}', f'C_B{n}', f'B_B{n - 1}', 'NUEVO_BC')
    app.GetActiveScenario().Save()
    c = {x.loc_name for x in _obj(app, 'ElmFeeder', 'C').GetObjs('ElmLod')}
    assert {f'B_S{n - 1}', f'B_S{n}'} <= c
    _caso(app, 'Caso base').Activate()
    resultados = guion.ejecutar_proyecto(app, planes)
    assert all(rc == 0 for _i, rc in resultados), [i.get('motivo') for i, _ in resultados]
    zonas = {(z['desde'], z['hacia'], tuple(z['sed'])) for i, _ in resultados
             for z in i['transferencias_del_operador']['zonas']}
    assert (('B', 'C', (f'B_S{n - 1}', f'B_S{n}'))) in zonas and ('A', 'B', (f'A_S{n}',)) in zonas
    assert all(i['perdidas']['kw'] > 0 for i, _ in resultados)
    _caso(app, 'Sin proyecto').Activate()
    assert int(t1.outserv) == 0 and int(t2.outserv) == 0
    assert int(_obj(app, 'ElmLne', f'A_L{n}').outserv) == 1 and int(_obj(app, 'ElmLne', f'B_L{n - 1}').outserv) == 1


# =========================================================================== la parte pura
def _r(nombre, a, b, cerrada=True, en_fuente=True, cerrada_en_fuente=True, clase='ElmLne'):
    return to.Rama(nombre, clase, nombre, (a, b), cerrada, en_fuente, cerrada_en_fuente)


def _cadena(f, n):
    """Barras ``f0`` (cabecera) a ``fn`` en línea, una carga por barra etiquetada ``f``."""
    ramas = [_r(f'{f}L{i}', f'{f}{i - 1}', f'{f}{i}') for i in range(1, n + 1)]
    cargas = [to.CargaRed(f'{f}S{i}', f'{f}S{i}', f'{f}{i}', f, f, 100.0, 30.0) for i in range(1, n + 1)]
    return ramas, cargas


def test_dos_sentidos_a_la_vez():
    """098:RF-1, 098:RF-2, 098:RF-15 — X cede su final a Y e Y el suyo a X, en la misma red: dos zonas, cada una con lo suyo."""
    rx, cx = _cadena('X', 4)
    ry, cy = _cadena('Y', 4)
    ramas = [r if r.nombre not in ('XL4', 'YL4') else _r(r.nombre, *r.extremos, cerrada=False) for r in rx + ry]
    ramas += [_r('N1', 'Y3', 'X4', en_fuente=False), _r('N2', 'X3', 'Y4', en_fuente=False)]
    cargas = [c if c.nombre not in ('XS4', 'YS4') else to.CargaRed(c.clave, c.nombre, c.terminal, c.etiqueta,
                                                                    'Y' if c.etiqueta == 'X' else 'X', 100.0, 30.0)
              for c in cx + cy]
    topologia = {'X': {'X1', 'X2', 'X3', 'Y4'}, 'Y': {'Y1', 'Y2', 'Y3', 'X4'}}
    zonas = to.zonas_transferidas(cargas, ramas, topologia, cabeceras={'X0', 'Y0'})
    assert [(z.desde, z.hacia, [c.nombre for c in z.cargas], [r.nombre for r in z.abrir], [r.nombre for r in z.cerrar])
            for z in zonas] == [('X', 'Y', ['XS4'], ['N1'], ['XL4']), ('Y', 'X', ['YS4'], ['N2'], ['YL4'])]
    assert not any(z.supuesto or z.motivo for z in zonas)


def test_sin_estado_de_la_fuente_se_supone_y_un_enlace_abierto_de_la_fuente_no_se_cierra():
    """098:RF-2 — con los estados del DGS, un enlace que ya venía abierto no es el punto del operador; sin ellos, el
    camino más corto se supone y la zona lo dice."""
    rx, cx = _cadena('X', 3)
    ry, cy = _cadena('Y', 3)
    ramas = [r if r.nombre != 'XL3' else _r('XL3', 'X2', 'X3', cerrada=False) for r in rx + ry]
    ramas += [_r('N1', 'Y3', 'X3', en_fuente=False),
              _r('ENLACE', 'X3', 'X1', cerrada=False, cerrada_en_fuente=False, clase='ElmCoup')]
    cargas = cx[:2] + [to.CargaRed('XS3', 'XS3', 'X3', 'X', 'Y', 100.0, 30.0)] + cy
    topologia = {'X': {'X1', 'X2'}, 'Y': {'Y1', 'Y2', 'Y3', 'X3'}}
    (z,) = to.zonas_transferidas(cargas, ramas, topologia, cabeceras={'X0', 'Y0'})
    assert [r.nombre for r in z.cerrar] == ['XL3'] and not z.supuesto
    sin_estado = [to.Rama(r.clave, r.clase, r.nombre, r.extremos, r.cerrada, r.en_fuente, None) for r in ramas]
    (z2,) = to.zonas_transferidas(cargas, sin_estado, topologia, cabeceras={'X0', 'Y0'})
    assert len(z2.cerrar) == 1 and z2.supuesto and 'se supone' in to.texto_de_zona(z2)


def test_lo_que_no_se_puede_devolver_no_se_toca():
    """098:RF-8 — sin tramo nuevo que la una (transferencia por un enlace sin estado de la fuente) o unida a SED
    propias de quien la alimenta: no se toca y se dice por qué."""
    rx, cx = _cadena('X', 3)
    ry, cy = _cadena('Y', 3)
    ramas = [r if r.nombre != 'XL3' else _r('XL3', 'X2', 'X3', cerrada=False) for r in rx + ry]
    ramas.append(_r('TIE', 'Y3', 'X3', clase='ElmCoup', cerrada_en_fuente=None))          # cerrado, sin estado del DGS
    cargas = cx[:2] + [to.CargaRed('XS3', 'XS3', 'X3', 'X', 'Y', 100.0, 30.0)] + cy
    (z,) = to.zonas_transferidas(cargas, ramas, {'X': {'X1', 'X2'}, 'Y': {'Y1', 'Y2', 'Y3', 'X3'}},
                                 cabeceras={'X0', 'Y0'})
    assert z.motivo == to.MOTIVO_UNIDA_EN_LA_FUENTE and not z.abrir and '098:RF-8' in to.texto_de_zona(z)


def test_un_tramo_nuevo_hacia_sed_nuevas_no_es_de_la_transferencia():
    """098:RF-2 — de lo que no es de la fuente, solo se abre lo que lleva al alimentador que la alimenta."""
    rx, cx = _cadena('X', 3)
    ry, cy = _cadena('Y', 3)
    ramas = [r if r.nombre != 'XL3' else _r('XL3', 'X2', 'X3', cerrada=False) for r in rx + ry]
    ramas += [_r('N1', 'Y3', 'X3', en_fuente=False), _r('EXT', 'X3', 'NUEVA', en_fuente=False)]
    cargas = cx[:2] + [to.CargaRed('XS3', 'XS3', 'X3', 'X', 'Y'), to.CargaRed('SN', 'SN', 'NUEVA', None, 'Y')] + cy
    (z,) = to.zonas_transferidas(cargas, ramas, {'X': {'X1', 'X2'}, 'Y': {'Y1', 'Y2', 'Y3', 'X3', 'NUEVA'}},
                                 cabeceras={'X0', 'Y0'})
    assert [r.nombre for r in z.abrir] == ['N1']


def test_los_abiertos_del_dgs_por_su_cabecera():
    """098:RF-2, 098:RF-14 — de cada tabla, lo que el DGS deja abierto o fuera de servicio, sea cual sea el orden."""
    dgs = ['$$ElmCoup;FID(a:40);OP(a:1);loc_name(a:40);on_off(i)', '  1;C;ENLACE_1;0', '  2;C;SECC_2;1',
           '$$ElmLne;FID(a:40);OP(a:1);outserv(i);loc_name(a:40)', '  3;C;1;L_FUERA', '  4;C;0;L_BIEN',
           '$$ElmTerm;FID(a:40);OP(a:1);loc_name(a:40);outserv(i)', '  5;C;B1;1']
    assert to.maniobras_abiertas_del_dgs(dgs) == {'ElmCoup': ['ENLACE_1'], 'ElmLne': ['L_FUERA']}


def test_aviso_de_la_medida_posterior_a_la_importacion(tpf):
    """098:RF-4 — con la medida del mes de la importación o después, no se sabe si ya incluye la transferencia."""
    plan = {'objetivo': {'fecha': '2026-07-27 08:45:00'}}
    assert tpf.aviso_de_la_medida({**plan, 'fecha_importacion': '2026-11-05'}) is None      # CA101: de antes
    assert '098:RF-4' in tpf.aviso_de_la_medida({**plan, 'fecha_importacion': '2026-06-30'})
    assert tpf.aviso_de_la_medida({**plan, 'fecha_importacion': '2026-07-02'}) is not None   # el mismo mes: no se sabe
    assert tpf.aviso_de_la_medida(plan) is None


def test_el_escaneo_dice_lo_que_paso_con_la_transferencia(guion):
    """098:RF-9 — el banco y el tramo nuevo que están en Y por la transferencia desde X salen como tales, para que no
    parezca que el operador los puso en Y."""
    escaneo = cargar_herramienta('escanear_alimentador_pf.py', 'escaneo_transferencia', tools_en_path=True)
    app, planes, _nuevo = _caso_ca101(guion)
    plan = {'project': 'P', 'feeders': ['F1', 'F2'], 'tramos_dgs': planes[0]['tramos_dgs'], 'abiertos_dgs': {}}
    informe, rc = escaneo.ejecutar(app, plan)
    assert rc == 0, informe
    (z,) = informe['transferencias']
    assert (z['desde'], z['hacia'], z['sed'], z['bancos']) == ('F1', 'F2', ['F1_S6'], ['EBC_1'])
    f2 = informe['alimentadores']['F2']
    assert next(b for b in f2['bancos'] if b['banco'] == 'EBC_1')['transferido_desde'] == 'F1'
    assert next(t for t in f2['tramos_nuevos'] if t['tramo'] == 'SEC_NUEVO_a')['transferencia'] == {
        'desde': 'F1', 'hacia': 'F2'}
    assert any('Transferencia del operador de F1 a F2' in a for a in informe['avisos'])


def test_la_web_lleva_al_plan_la_red_de_la_fuente(tmp_path):
    """098:RF-14 — tramos, abiertos del DGS aceptado y fecha de la importación; sin DGS, nada."""
    import hashlib
    import time as _time
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    salida = tmp_path / 'runs' / 'r1' / 'salida'
    salida.mkdir(parents=True)
    dgs = salida / 'F1.dgs'
    dgs.write_text('$$ElmLne;FID(a:40);OP(a:1);loc_name(a:40);outserv(i)\n  1;C;L1;0\n  2;C;L2;1\n'
                   '$$ElmCoup;FID(a:40);OP(a:1);loc_name(a:40);on_off(i)\n  3;C;ENLACE;0\n', encoding='cp1252')
    cuando = _time.mktime((2026, 11, 5, 12, 47, 11, 0, 0, -1))
    ws = SimpleNamespace(root=tmp_path, pf_project_bindings={'P': {
        'source_run_id': 'r1', 'dgs_sha256': {'F1': hashlib.sha256(dgs.read_bytes()).hexdigest()}, 'accepted_at': cuando}})
    red = services._red_de_la_fuente_del_plan(ws, 'P')
    assert red == {'tramos_dgs': ['L1', 'L2'], 'abiertos_dgs': {'ElmCoup': ['ENLACE'], 'ElmLne': ['L2']},
                   'fecha_importacion': '2026-11-05'}
    assert services._red_de_la_fuente_del_plan(ws, 'OTRO') == {}


# =========================================================================== obras («Con proyecto», 042/087)
def _tramo(nombre, desde, hasta, u, maniobra=None, puente=False):
    t = {'nombre': nombre, 'desde': desde, 'hasta': hasta, 'largo_m': 0.0 if puente else 1000, 'u': {hasta: u},
         'corriente_a': 50}
    if maniobra:
        t['maniobra'] = {'clase': 'ElmCoup' if puente else 'StaSwitch', 'nombre': maniobra}
    if puente:
        t['puente'] = True
    return t


def test_la_escalera_solo_transfiere_donde_hay_maniobra():
    """098:RF-11 — de las barras de la troncal, solo las que tienen un seccionador en su tramo de entrada o un acoplador
    antes; el acoplador del camino separa desde su barra de llegada."""
    from convertersmartgrid import obras_integrales as oi

    camino = oi.con_maniobras([_tramo('T1', 'CAB', 'B1', 0.94), _tramo('T2', 'B1', 'B2', 0.94, 'SW2'),
                               _tramo('ACOPLE', 'B2', 'B2b', 0.94, 'ACOPLE', puente=True), _tramo('T3', 'B2b', 'B3', 0.94),
                               _tramo('R1', 'B3', 'RAMA', 0.93, 'SWR')])
    assert [t['nombre'] for t in camino] == ['T1', 'T2', 'T3', 'R1']
    assert camino[2]['maniobra_previa'] == {'clase': 'ElmCoup', 'nombre': 'ACOPLE'}
    troncal = {'T1', 'T2', 'T3'}
    assert oi.candidatos_de_transferencia(camino, troncal, 0.95) == ['B2', 'B2b']
    assert oi.nodo_de_traslado(camino, troncal, 'RAMA') == 'RAMA'


def test_sin_maniobra_no_se_propone_la_transferencia_y_se_avisa():
    """098:RF-13 — ninguna barra candidata con maniobra: ni transferencia ni traslado, con su aviso; los demás
    escalones siguen (las variantes que quedan son las que hay)."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid import obras_integrales as oi

    perfil = {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'semilla': 7, 'tolerancia_pu': 0.005,
                           'tolerancia_carga_pct': 1.0},
              'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    p = eo.parametros(perfil)
    tipos = [{'nombre': 'AA120_10', 'clase': 'TypLne', 'datos': {'uline': 10.0, 'sline': 0.36, 'cohl_': 1}}]
    camino = oi.con_maniobras([_tramo('T1', 'CAB', 'B1', 0.94), _tramo('R1', 'B1', 'RAMA', 0.93)])
    vecino = {'alimentador': 'V', 'distancia_m': 300, 'u_min': 0.99, 'carga_max_pct': 40.0, 'kv': 10.0, 'barra': 'X'}
    vs, avisos = oi.variantes('F1', 10.0, camino, {'T1'}, 'RAMA', {'B1': [vecino], 'RAMA': [vecino]}, tipos, p)
    assert vs == []
    assert sum('098:RF-13' in a for a in avisos) == 2


def test_la_migracion_abre_el_seccionador_del_tramo_y_se_restituye_solo_ese():
    """098:RF-12 — con un seccionador en el tramo de entrada, la migración lo abre por ``abrir`` (081:RF-80) en vez de
    sacar el tramo de servicio; al restituir se cierra ese y no otro con el mismo nombre."""
    from test_obras_pf_guion import CON, _activas, _calibrada, _linea
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_transferencia_098', tools_en_path=True)
    app, alims = _calibrada(random.Random(71), n_min=2, cargas_min=3)
    seccionadores = []
    for nombre in ('F1_L2', 'F1_L3'):
        cub = _linea(app, nombre).bus1
        sw = cub.CreateObject('StaSwitch', 'Switch')                  # el mismo nombre en los dos, como deja SplitLine
        sw.on_off = 1
        seccionadores.append(sw)
    informe, codigo = obras.aplicar(app, _plan_obras(alims, obras=[{'clase': 'migracion', 'alimentador': 'F1',
                                                                    'casos': [CON], 'nodo': 'F1_B2', 'kv_destino': 22.9}]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    _activas(app, CON)
    assert seccionadores[0].on_off == 0 and _linea(app, 'F1_L2').outserv == 0
    assert seccionadores[1].on_off == 1
    (entrada,) = fila['abiertos']
    assert entrada[:2] == ['StaSwitch', 'Switch'] and entrada[3] == seccionadores[0].GetFullName()
    assert obras.cerrar_lo_abierto(app, {'abiertos': [entrada], 'avisos': []}) == ['Switch']
    assert seccionadores[0].on_off == 1 and seccionadores[1].on_off == 1
