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


def _red(feeders=('F1', 'F2'), n=6, kw=None, kva=None):
    """Red con sus SED etiquetadas por su alimentador, como las deja el DGS (``p:alimentador``)."""
    app = fake_pf.proyecto(alimentadores=feeders, cargas_por_alim=n, bt=True, flujo=True, escenario=True,
                           kva=kva or (lambda f, i: 3000.0))
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
    """098:RF-14 — rutas, tramos y abiertos del DGS aceptado, y la fecha de la importación por el sello; sin DGS, nada."""
    import hashlib
    import time as _time
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    salida = tmp_path / 'runs' / 'r1' / 'salida'
    salida.mkdir(parents=True)
    dgs = salida / 'F1.dgs'
    dgs.write_text('$$ElmLne;FID(a:40);OP(a:1);loc_name(a:40);outserv(i)\n  1;C;L1;0\n  2;C;L2;1\n'
                   '$$ElmCoup;FID(a:40);OP(a:1);loc_name(a:40);on_off(i)\n  3;C;ENLACE;0\n', encoding='cp1252')
    # Verificado otra vez el 2026-11-07: ``accepted_at`` cambia; la fecha es la del sello de la importación.
    verificado = _time.mktime((2026, 11, 7, 9, 0, 0, 0, 0, -1))
    vinculo = {'source_run_id': 'r1', 'dgs_sha256': {'F1': hashlib.sha256(dgs.read_bytes()).hexdigest()},
               'accepted_at': verificado}
    ws = SimpleNamespace(root=tmp_path, pf_project_bindings={'20261105-124711_CSG_TXT_X_Y': vinculo, 'SIN_SELLO': vinculo})
    red = services._red_de_la_fuente_del_plan(ws, '20261105-124711_CSG_TXT_X_Y')
    assert red == {'dgs_fuente': [str(dgs)], 'tramos_dgs': ['L1', 'L2'],
                   'abiertos_dgs': {'ElmCoup': ['ENLACE'], 'ElmLne': ['L2']}, 'fecha_importacion': '2026-11-05'}
    import os
    os.utime(dgs, (_time.mktime((2026, 11, 4, 8, 0, 0, 0, 0, -1)),) * 2)
    assert services._red_de_la_fuente_del_plan(ws, 'SIN_SELLO')['fecha_importacion'] == '2026-11-04'   # la del DGS
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


# =========================================================================== la configuración real de CA101 y CHN102
def _dgs_de(app, ruta):
    """El DGS «aceptado» de la red tal como está, con sus cubículos: lo que la web pasa en ``dgs_fuente`` (098:RF-16).

    Como el del conversor, sin maniobras abiertas."""
    fid = {}

    def f(o):
        return fid.setdefault(id(o), str(len(fid) + 1))

    filas = ['$$General;ID(a:40);Descr(a:40);Val(a:40)', '  1;Version;6.0',
             '$$ElmTerm;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p)']
    filas += [f'  {f(t)};C;{t.loc_name};1' for t in app.proyecto.GetContents('*.ElmTerm', 1)]
    for clase in ('ElmLne', 'ElmCoup', 'ElmTr2'):
        filas.append(f'$${clase};FID(a:40);OP(a:1);loc_name(a:40);fold_id(p)')
        filas += [f'  {f(o)};C;{o.loc_name};1' for o in app.proyecto.GetContents(f'*.{clase}', 1)]
    filas.append('$$StaCubic;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);obj_bus(i);obj_id(p)')
    for c in app.proyecto.GetContents('*.StaCubic', 1):
        o = getattr(c, 'obj_id', None)
        if o is not None and o._clase in ('ElmLne', 'ElmCoup', 'ElmTr2'):
            lado = getattr(c, 'obj_bus', None)
            if lado is None:
                lado = 0 if getattr(o, 'bushv', None) is c else 1
            filas.append(f'  {f(c)};C;{c.loc_name};{f(c.cterm)};{lado};{f(o)}')
    ruta.write_text('\n'.join(filas) + '\n', encoding='cp1252')
    return ruta


def _barra_nueva(app, nombre):
    red = app.proyecto.GetContents('*.ElmNet', 1)[0]
    b = red.CreateObject('ElmTerm', nombre)
    b.uknom = 10.0
    return b


def _mover_extremo(app, elemento, lado, barra):
    """Lo que hace ``SplitLine``: el cubículo de un extremo pasa a otra barra."""
    viejo = getattr(elemento, f'bus{lado + 1}')
    viejo.Delete()
    cub = barra.CreateObject('StaCubic', f'c{lado}_{elemento.loc_name}')
    cub.obj_id, cub.obj_bus = elemento, lado
    object.__setattr__(elemento, f'bus{lado + 1}', cub)


def _rama(app, clase, nombre, a, b, **attrs):
    red = app.proyecto.GetContents('*.ElmNet', 1)[0]
    o = red.CreateObject(clase, nombre)
    for k, v in attrs.items():
        setattr(o, k, v)
    for lado, barra in ((0, a), (1, b)):
        cub = barra.CreateObject('StaCubic', f'c{lado}_{nombre}')
        cub.obj_id, cub.obj_bus = o, lado
        object.__setattr__(o, f'bus{lado + 1}', cub)
    return o


def _caso_ca101_real(guion, tmp_path):
    """Como en DIgSILENT el 2026-11-07 (sondas de solo lectura de la sesión de T6):

    1. ``X_L3`` partido: va de ``X_B3`` a «Terminal» y la mitad nueva ``X_L3_a`` de «Terminal» a ``X_B2``, con un banco
       en «Terminal». Sin cambio de topología: no hay que abrir nada.
    2. ``X_L5`` partido: de ``X_B4`` a «Terminal(2)»; el acoplador nuevo «Breaker/Switch», ABIERTO, a «Terminal(3)»; y la
       línea nueva ``X_L5_c`` a ``X_B5``. Es el punto que separa la zona de X.
    3. El acoplador nuevo «Breaker/Switch(1)», CERRADO, entre ``Y_B6`` y ``X_B6``, dos barras del DGS que el DGS no une
       (la conversión quita las maniobras abiertas): por él Y alimenta la zona.
    """
    # Las escaladas se reparten por kVA (095): la zona, con transformadores menores, lleva una parte como la de CA101.
    app = _red(kw={'F1': 1.1, 'F1_S5': 0.3, 'F1_S6': 0.3, 'F2': 0.455},
               kva=lambda f, i: 600.0 if (f, i) in (('F1', 5), ('F1', 6)) else 3000.0)
    objetivos = {'F1': 6600.0, 'F2': 2728.0}
    dgs = _dgs_de(app, tmp_path / 'aceptado.dgs')
    planes = _planes(objetivos, set())
    for p in planes:
        p.update(dgs_fuente=[str(dgs)], tramos_dgs=[], abiertos_dgs={})
    primera = guion.ejecutar_proyecto(app, planes)
    assert all(rc == 0 for _i, rc in primera), primera
    import sys

    informe, rc = sys.modules['casos_pf'].preparar_con(
        app, {'project': 'P', 'feeders': ['F1', 'F2'], 'caso_base_sin_verificar': {}})
    assert rc == 0, informe
    _caso(app, 'Sin proyecto').Activate()
    tipo = _obj(app, 'ElmLne', 'F1_L1').typ_id
    terminal = _barra_nueva(app, 'Terminal')
    _mover_extremo(app, _obj(app, 'ElmLne', 'F1_L3'), 0, terminal)
    a = _rama(app, 'ElmLne', 'F1_L3_a', terminal, _obj(app, 'ElmTerm', 'F1_B2'), typ_id=tipo, nlnum=1, outserv=0, dline=0.5)
    _banco(app, 'Terminal', 'EBC_2')
    t2, t3 = _barra_nueva(app, 'Terminal(2)'), _barra_nueva(app, 'Terminal(3)')
    _mover_extremo(app, _obj(app, 'ElmLne', 'F1_L5'), 1, t2)
    abierto = _rama(app, 'ElmCoup', 'Breaker/Switch', t2, t3, on_off=0, outserv=0)
    c = _rama(app, 'ElmLne', 'F1_L5_c', t3, _obj(app, 'ElmTerm', 'F1_B5'), typ_id=tipo, nlnum=1, outserv=0, dline=0.5)
    enlace = _rama(app, 'ElmCoup', 'Breaker/Switch(1)', _obj(app, 'ElmTerm', 'F2_B6'), _obj(app, 'ElmTerm', 'F1_B6'),
                   on_off=1, outserv=0)
    app.GetActiveScenario().Save()
    en_f2 = {x.loc_name for x in _obj(app, 'ElmFeeder', 'F2').GetObjs('ElmLod')}
    assert {'F1_S5', 'F1_S6'} <= en_f2 and 'F1_S4' not in en_f2
    _caso(app, 'Caso base').Activate()
    return app, planes, {'a': a, 'abierto': abierto, 'c': c, 'enlace': enlace}


def _como_lo_dejo(app, el):
    _caso(app, 'Sin proyecto').Activate()
    return (int(el['abierto'].on_off), int(el['enlace'].on_off), int(el['a'].outserv), int(el['c'].outserv))


def test_la_configuracion_real_da_perdidas_negativas_sin_la_098(guion, tpf, tmp_path, monkeypatch):
    """098:RF-3, 098:RF-17 — el control: con la transferencia de CA101 y CHN102 puesta, pérdidas negativas en X."""
    app, planes, _el = _caso_ca101_real(guion, tmp_path)
    monkeypatch.setattr(tpf.RedDeLaFuente, 'preparar', lambda self, *a, **k: None)
    (x, _rc), _ = guion.ejecutar_proyecto(app, planes)
    assert not x['cuadrado'] and 'pérdidas activas negativas en F1' in (x['motivo'] or '')


def test_dos_particiones_y_dos_acopladores_nuevos_como_en_ca101(guion, tmp_path):
    """098:RF-16, 098:RF-17, 098:RF-18, 098:RF-19, 098:RF-3, 098:RF-5 — frente al DGS aceptado: las dos particiones son
    la red de la fuente, el acoplador abierto dentro de una es el punto del operador (se cierra) y el nuevo cerrado entre
    barras del DGS es su enlace (se abre). Se cuadra sin pérdidas negativas y todo vuelve a como lo dejó."""
    app, planes, el = _caso_ca101_real(guion, tmp_path)
    antes = _como_lo_dejo(app, el)
    assert antes == (0, 1, 0, 0)
    _caso(app, 'Caso base').Activate()
    (x, rcx), (y, rcy) = guion.ejecutar_proyecto(app, planes)
    assert (rcx, rcy) == (0, 0), (x.get('motivo'), y.get('motivo'))
    assert x['perdidas']['kw'] > 0 and y['perdidas']['kw'] > 0
    t = x['transferencias_del_operador']
    (z,) = t['zonas']
    assert (z['desde'], z['hacia'], z['sed'], z['motivo']) == ('F1', 'F2', ['F1_S5', 'F1_S6'], None)
    assert z['abrir'] == [{'clase': 'ElmCoup', 'nombre': 'Breaker/Switch(1)'}]
    assert z['cerrar'] == [{'clase': 'ElmCoup', 'nombre': 'Breaker/Switch'}] and not z['supuesto']
    particiones = {p['rama']: p for p in t['frente_a_la_fuente']['particiones']}
    assert set(particiones) == {'F1_L3', 'F1_L5'} and particiones['F1_L5']['abierto'] == ['Breaker/Switch']
    assert t['frente_a_la_fuente']['nuevas'] == ['Breaker/Switch(1)']
    assert {c['nombre'] for c in t['cambios']} == {'Breaker/Switch', 'Breaker/Switch(1)'}
    assert t['restituida'] and all(e['ok'] for e in t['evidencia'])
    assert _como_lo_dejo(app, el) == antes
    _caso(app, 'Con proyecto').Activate()
    assert int(el['abierto'].on_off) == 0 and int(el['enlace'].on_off) == 1


def test_el_registro_distingue_acopladores_de_nombre_parecido(guion, tpf, tmp_path):
    """098:RF-19, 098:RF-5 — si la orden muere con la transferencia desactivada, la siguiente restituye cada acoplador por
    su nombre completo: «Breaker/Switch» y «Breaker/Switch(1)» no se confunden."""
    app, planes, el = _caso_ca101_real(guion, tmp_path)
    _caso(app, 'Sin proyecto').Activate()
    red = tpf.RedDeLaFuente(app, planes[0])
    red.preparar(guion.Alimentadores(app, app.proyecto, ['F1', 'F2']), _caso(app, 'Sin proyecto'), ['F1', 'F2'])
    assert (int(el['abierto'].on_off), int(el['enlace'].on_off)) == (1, 0)
    rutas = {e['nombre']: e['ruta'] for e in tpf._leer(tpf.fichero(planes[0]))}
    assert rutas == {'Breaker/Switch': el['abierto'].GetFullName(), 'Breaker/Switch(1)': el['enlace'].GetFullName()}
    _caso(app, 'Caso base').Activate()
    (x, rc), _ = guion.ejecutar_proyecto(app, planes)
    assert rc == 0, x.get('motivo')
    assert _como_lo_dejo(app, el) == (0, 1, 0, 0)
    assert not tpf.fichero(planes[0]).exists()


def test_frente_a_la_fuente_puro():
    """098:RF-16, 098:RF-17, 098:RF-18 — la partición con todo cerrado es de la fuente; un elemento nuevo fuera de ella
    no lo es; el DGS se lee por sus cubículos."""
    dgs = ['$$ElmTerm;FID(a:40);OP(a:1);loc_name(a:40)', '  1;C;A', '  2;C;B', '  3;C;C',
           '$$ElmLne;FID(a:40);OP(a:1);loc_name(a:40)', '  10;C;L1',
           '$$StaCubic;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);obj_bus(i);obj_id(p)', '  20;C;c0;1;0;10',
           '  21;C;c1;2;1;10']
    fuente = to.red_del_dgs(dgs)
    assert fuente.ramas == {('ElmLne', 'L1'): ('A', 'B')} and fuente.barras == {'A', 'B', 'C'}

    def r(nombre, clase, a, b, cerrada=True):
        return to.Rama(nombre, clase, nombre, (a, b), cerrada, barras=(a, b))

    ramas, frente = to.frente_a_la_fuente([r('L1', 'ElmLne', 'A', 'T'), r('L1_a', 'ElmLne', 'T', 'B'),
                                           r('NUEVO', 'ElmCoup', 'B', 'C')], fuente)
    por = {x.nombre: x for x in ramas}
    assert por['L1'].en_fuente and por['L1_a'].en_fuente and not por['L1_a'].fuera_de_la_fuente
    assert por['NUEVO'].en_fuente is False and por['NUEVO'].fuera_de_la_fuente
    assert frente == {'particiones': [{'rama': 'L1', 'clase': 'ElmLne', 'cadena': ['L1_a'], 'abierto': []}],
                      'nuevas': ['NUEVO']}


# =========================================================================== 098:RF-20 a RF-27: transferir por el enlace que ya existe
def test_una_barra_sin_gps_toma_las_de_la_mas_cercana_por_la_red():
    """098:RF-20 — CA101 + CHN102 (2026-11-07): sin coordenadas en 12333, 11969 y la barra nueva, la búsqueda de vecinos
    salía vacía; ahora toma las de la barra con GPS más cercana por la red, y sin ninguna dice que no hay."""
    obras = cargar_herramienta('obras_pf.py', 'obras_gps_098', tools_en_path=True)
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=4, bt=True, flujo=True)
    for n in ('F1_B2', 'F1_B3'):
        b = _obj(app, 'ElmTerm', n)
        b.GPSlat, b.GPSlon = 0.0, 0.0
    punto, desde = obras._gps_por_la_red(_obj(app, 'ElmTerm', 'F1_B3'), {})
    assert desde in ('F1_B1', 'F1_B4') and punto == obras.gps_de(_obj(app, 'ElmTerm', desde))
    for b in app.proyecto.GetContents('*.ElmTerm', 1):
        b.GPSlat, b.GPSlon = 0.0, 0.0
    assert obras._gps_por_la_red(_obj(app, 'ElmTerm', 'F1_B3'), {}) == (None, None)


PREFIJO_098 = 'Red:\\P\\'


def _gid(n, c):
    return f'{c}:{PREFIJO_098}{n}.{c}'


def _grafo_dos():
    """X: S1–A1–A2–A3–A4, con la carga nueva en A4; Y: S2–B1–B2; el acoplador ENL, abierto, entre A3 y B2.

    Con la nueva, A4 queda a 0,926 p.u.; abrir A2–A3 y cerrar ENL la sube a 0,936 (no basta); 900 kvar en A4, solos,
    a 0,948 (no basta); la transferencia con esos 900 kvar, a 0,955 (cumple), y los 1 800 kvar solos también, más caros.
    """
    nodos = {_gid('S1', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0, 'q_mvar': 0, 'fuente': True, 'v_pu': 1.0},
             _gid('S2', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0, 'q_mvar': 0, 'fuente': True, 'v_pu': 1.0}}
    for n in ('A1', 'A2', 'A3', 'A4'):
        nodos[_gid(n, 'ElmTerm')] = {'kv': 10.0, 'p_mw': 0.3, 'q_mvar': 0.1, 'fuente': False}
    nodos[_gid('A4', 'ElmTerm')].update(p_mw=1.5, q_mvar=0.46)
    for n in ('B1', 'B2'):
        nodos[_gid(n, 'ElmTerm')] = {'kv': 10.0, 'p_mw': 0.2, 'q_mvar': 0.05, 'fuente': False}
    ramas = [{'id': _gid(f'L{a}{b}', 'ElmLne'), 'desde': _gid(a, 'ElmTerm'), 'hasta': _gid(b, 'ElmTerm'),
              'r_ohm': r, 'x_ohm': r * 0.8, 'inom_ka': 0.3, 'largo_km': 2.0, 'cerrada': True}
             for a, b, r in (('S1', 'A1', 0.7), ('A1', 'A2', 0.7), ('A2', 'A3', 0.7), ('A3', 'A4', 0.7),
                             ('S2', 'B1', 0.9), ('B1', 'B2', 0.9))]
    ramas.append({'id': _gid('ENL', 'ElmCoup'), 'clase': 'ElmCoup', 'desde': _gid('A3', 'ElmTerm'),
                  'hasta': _gid('B2', 'ElmTerm'), 'r_ohm': 0.01, 'x_ohm': 0.01, 'inom_ka': 0.5, 'cerrada': False})
    return {'nodos': nodos, 'ramas': ramas}


def _p_098():
    from convertersmartgrid.escalera_optima import Parametros

    return Parametros(cumplimiento=0.95, sorteos=4, semilla=7, tolerancia_pu=0.001, tolerancia_carga_pct=1.0,
                      max_variantes=40, tasa=0.12, vida=20, tension_min_pu=0.95, tension_max_pu=1.05,
                      cargabilidad_max_pct=100.0)


def _enlace_x():
    """Lo que da ``--escalera-datos``: el enlace ENL con Y y las maniobras de la cabecera hasta A3, en orden."""
    return {'enlace': 'ENL', 'clase': 'ElmCoup', 'ruta': 'ENL.ElmCoup', 'cerrado': False, 'vecino': 'Y', 'barra': 'A3',
            'u_min': 0.99, 'carga_max_pct': 30.0,
            'puntos': [{'rama': r, 'barra': b, 'maniobra': {'clase': 'StaSwitch', 'nombre': f'SW_{r}', 'ruta': f'X\\{r}\\SW'}}
                       for r, b in (('LS1A1', 'A1'), ('LA1A2', 'A2'), ('LA2A3', 'A3'))]}


def _bancos_x():
    from convertersmartgrid.escalera_optima import Variante

    return [Variante(f'{n}×450 kvar en A4', ('bancos',), [{'clase': 'condensador', 'alimentador': 'X', 'barra': 'A4',
                                                          'q_kvar': 450.0 * n, 'escalones': n}], {'bancos': n})
            for n in (1, 2, 3, 4)]


def _costo(v, perdidas_kw):
    return 1000.0 * v.cantidades.get('bancos', 0) + 0.1 * (perdidas_kw or 0.0)


def test_transferencias_por_el_enlace_de_la_mas_cercana_a_la_cabecera():
    """098:RF-21, 098:RF-22 — sin línea nueva ni km: de la maniobra más cercana al enlace hacia la cabecera; abre la
    maniobra y cierra el enlace; un vecino sin margen no recibe."""
    from convertersmartgrid import obras_integrales as oi

    vs, avisos = oi.variantes_por_enlace('X', [_enlace_x()], _p_098())
    assert [v.obras[0]['maniobra'] for v in vs] == ['SW_LA2A3', 'SW_LA1A2', 'SW_LS1A1'] and not avisos
    o = vs[0].obras[0]
    assert (o['clase'], o['tramo'], o['enlace'], o['vecino'], o['enlace_cerrado']) == ('maniobra', 'LA2A3', 'ENL', 'Y', False)
    assert all(v.cantidades == {} and v.escalones == ('transferencia',) for v in vs)
    sin_margen, av = oi.variantes_por_enlace('X', [{**_enlace_x(), 'u_min': 0.951}], _p_098())
    assert sin_margen == [] and any('087:RF-32' in a for a in av)


def test_la_transferencia_sola_no_basta_y_con_bancos_si(monkeypatch):
    """098:RF-25, 098:RF-23, 098:RF-24 — el oráculo descarta la maniobra que no sirve, sobre la topología de la mejor
    vuelve a probar los bancos y elige «transferencia + bancos», más barata que los bancos solos; su costo y su
    tensión salen en la tabla."""
    pytest.importorskip('scipy')
    from convertersmartgrid import obras_integrales as oi
    from convertersmartgrid import optimizacion_oraculo as oo

    p = _p_098()
    nueva = {'variacion': 'C1', 'nodo': _gid('A4', 'ElmTerm'), 'p_mw': 1.2, 'q_mvar': 0.36, 'alimentador': 'X',
             'barra': 'A4'}
    ora = oo.Oraculo(_grafo_dos(), [nueva])
    candidatas, _av = oi.variantes_por_enlace('X', [_enlace_x()], p)
    a = oo.Alimentador('X', _bancos_x(), _costo, None)
    extra, resumen = oo.transferencias_con_oraculo(ora, a, candidatas, 1, p, confirmar=1)
    assert resumen['generadas'] == 3 and resumen['pasan'] == [candidatas[0].nombre]
    assert len(resumen['descartadas']) == 2 and all(x['motivo'] for x in resumen['descartadas'])
    assert resumen['combinadas'] == 4 and resumen['flujos'] == 2 * (1 + 3)       # sin obra y cada candidata, con su base
    e = oo.elegir_para_k(ora, [oo.Alimentador('X', _bancos_x() + extra, _costo, None)], 1, p,
                         evaluaciones_bayes=0, permutaciones=0, pareto=False)['X']
    # 098:RF-45: los bancos solos que cumplen van antes que la transferencia (con bancos o sin ellos).
    assert e['elegida'] == '3×450 kvar en A4' or e['elegida'] == f"{candidatas[0].nombre} + 2×450 kvar en A4"
    fila = next(t for t in e['tabla'] if t['nombre'] == e['elegida'])
    solos = next(t for t in e['tabla'] if t['nombre'] == '4×450 kvar en A4')
    assert fila['cumple'] and solos['cumple'] and fila['costo_anual'] < solos['costo_anual']
    assert fila['v_min'] is not None and fila['v_min'] >= p.tension_min_pu - 0.05
    sola = next(t for t in e['tabla'] if t['nombre'] == candidatas[0].nombre)
    assert not sola['cumple']                                                     # sola no basta


def test_el_oraculo_filtra_y_solo_las_mejores_van_a_digsilent():
    """098:RF-26 — de una cadena de maniobras, el oráculo juzga cada una con un flujo; a DIgSILENT van solo las que
    da por buenas y una tanda más (087:RF-39), no todas."""
    pytest.importorskip('scipy')
    from convertersmartgrid import obras_integrales as oi
    from convertersmartgrid import optimizacion_oraculo as oo

    p = _p_098()
    nueva = {'variacion': 'C1', 'nodo': _gid('A4', 'ElmTerm'), 'p_mw': 1.2, 'q_mvar': 0.36, 'alimentador': 'X',
             'barra': 'A4'}
    ora = oo.Oraculo(_grafo_dos(), [nueva])
    candidatas, _av = oi.variantes_por_enlace('X', [_enlace_x()], p)
    a = oo.Alimentador('X', _bancos_x(), _costo, None)
    antes = ora.evaluaciones
    extra, resumen = oo.transferencias_con_oraculo(ora, a, candidatas, 1, p, confirmar=2)
    assert ora.evaluaciones - antes == 0                       # en el oráculo rápido, aparte
    assert resumen['flujos'] == 2 * (1 + 3) and len(resumen['pasan']) == 2
    todas = _bancos_x() + extra
    e = oo.elegir_para_k(ora, [oo.Alimentador('X', todas, _costo, None)], 1, p,
                         evaluaciones_bayes=0, permutaciones=0, pareto=False)['X']
    a_digsilent = oo.a_confirmar(e, 1)
    buenas = sum(1 for t in e['tabla'] if t['cumple'])
    assert len(a_digsilent) == buenas + 1 < len(todas)
    assert a_digsilent[0].nombre == e['elegida']


def _red_con_enlace():
    """Dos alimentadores del doble con un acoplador ENL, abierto, entre la última barra de cada uno, y un seccionador en
    los dos últimos tramos de F1; los ``ElmFeeder`` siguen la topología de ahora."""
    from test_obras_pf_guion import _calibrada_con_escenario

    app, alims = _calibrada_con_escenario(random.Random(98))
    n = len([b for b in _obj(app, 'ElmFeeder', 'F1').GetObjs('ElmTerm') if b.loc_name.startswith('F1_B')]) - 1
    seccionadores = []
    for i in (n - 1, n):
        sw = _obj(app, 'ElmLne', f'F1_L{i}').bus1.CreateObject('StaSwitch', 'Switch')
        sw.on_off = 1
        seccionadores.append(sw)
    enl = _rama(app, 'ElmCoup', 'ENL', _obj(app, 'ElmTerm', f'F1_B{n}'), _obj(app, 'ElmTerm', f'F2_B{n}'),
                on_off=0, outserv=0)
    app.topologia_viva = True
    app.servicio_en_escenario = True             # abrir y cerrar es dato del escenario de «Con proyecto»
    return app, alims, n, seccionadores, enl


def test_la_lectura_da_el_enlace_existente_con_sus_maniobras():
    """098:RF-21, 098:RF-22, 098:RF-27 — ``--escalera-datos`` da el enlace con el vecino, abierto, y las maniobras del camino de la
    cabecera a su barra, en orden, con su nombre completo."""
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_enlace_098', tools_en_path=True)
    app, alims, n, seccionadores, _enl = _red_con_enlace()
    informe, codigo = obras.datos_escalera(app, _plan_obras(alims, barras={'F1': [f'F1_B{n}']}))
    assert codigo == 0, informe
    (e,) = [x for x in informe['alimentadores']['F1']['enlaces'] if x['enlace'] == 'ENL']
    assert (e['vecino'], e['cerrado'], e['barra']) == ('F2', False, f'F1_B{n}')
    assert [x['maniobra']['ruta'] for x in e['puntos']] == [s.GetFullName() for s in seccionadores]


def test_un_enlace_entre_tensiones_distintas_no_se_propone():
    """098:RF-42 — tras pasar CHN102 a 22,9 kV, «Breaker/Switch» unía 10 kV con 22,9 kV: la lectura lo descarta y lo
    dice; con la misma tensión, el enlace sigue."""
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_enlace_tensiones_098', tools_en_path=True)
    app, alims, n, _seccionadores, _enl = _red_con_enlace()
    _obj(app, 'ElmTerm', f'F2_B{n}').uknom = 22.9
    _obj(app, 'ElmTerm', f'F1_B{n}').uknom = 10.0
    informe, codigo = obras.datos_escalera(app, _plan_obras(alims, barras={'F1': [f'F1_B{n}']}))
    assert codigo == 0, informe
    assert not [x for x in informe['alimentadores']['F1']['enlaces'] if x['enlace'] == 'ENL']
    assert any('ENL' in a and '22.9 kV' in a and '098:RF-42' in a for a in informe['avisos'])
    _obj(app, 'ElmTerm', f'F2_B{n}').uknom = 10.0
    informe, _c = obras.datos_escalera(app, _plan_obras(alims, barras={'F1': [f'F1_B{n}']}))
    assert [x for x in informe['alimentadores']['F1']['enlaces'] if x['enlace'] == 'ENL']


def test_la_obra_abre_la_maniobra_cierra_el_enlace_y_dice_que_pasa(tmp_path):
    """098:RF-21, 098:RF-24, 098:RF-19 — sin línea nueva: se cierra el enlace y se abre el seccionador, los dos anotados;
    el informe dice qué SED pasaron, con cuántos kW, y las tensiones y cargas antes y después; al quedar inactiva todo
    vuelve a como estaba."""
    from test_obras_pf_guion import CON
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_maniobra_098', tools_en_path=True)
    app, alims, n, seccionadores, enl = _red_con_enlace()
    obra = {'clase': 'maniobra', 'alimentador': 'F1', 'vecino': 'F2', 'casos': [CON], 'tramo': f'F1_L{n}',
            'maniobra': 'Switch', 'maniobra_clase': 'StaSwitch', 'maniobra_ruta': seccionadores[1].GetFullName(),
            'enlace': 'ENL', 'enlace_clase': 'ElmCoup', 'enlace_ruta': enl.GetFullName(), 'enlace_cerrado': False}
    plan = _plan_obras(alims, obras=[obra], aperturas_fichero=str(tmp_path / 'aperturas.json'))
    informe, codigo = obras.aplicar(app, plan)
    assert codigo == 0, informe
    (fila,) = informe['obras']
    t = fila['transferencia']
    assert t['sed'] == [f'F1_S{n}'] and t['kw'] > 0 and t['vecino'] == 'F2' and not t['enlace_cerrado_antes']
    assert set(t['antes']) == set(t['despues']) == {'F1', 'F2'}
    assert any('098:RF-24' in a for a in fila['avisos'])
    _caso(app, CON).Activate()
    assert (seccionadores[1].on_off, seccionadores[0].on_off, enl.on_off) == (0, 1, 1)
    # La obra queda aplicada: su anotación sale del registro (081:RF-81) y la fila guarda qué abrió y qué cerró.
    assert fila['abiertos'][0][3] == seccionadores[1].GetFullName() and fila['cerrados'][0][:2] == ['ElmCoup', 'ENL']
    obras.cerrar_lo_abierto(app, fila, plan)
    assert (seccionadores[1].on_off, enl.on_off) == (1, 0)
    assert obras.leer_aperturas(tmp_path / 'aperturas.json') == []


def test_la_orden_que_muere_reabre_el_enlace_que_cerro(tmp_path):
    """098:RF-21, 081:RF-82 — lo que una obra cerró se vuelve a abrir al empezar la orden siguiente."""
    from test_obras_pf_guion import CON
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_muere_098', tools_en_path=True)
    app, alims, n, seccionadores, enl = _red_con_enlace()
    obra = {'clase': 'maniobra', 'alimentador': 'F1', 'vecino': 'F2', 'casos': [CON], 'tramo': f'F1_L{n}',
            'maniobra': 'Switch', 'maniobra_clase': 'StaSwitch', 'maniobra_ruta': seccionadores[1].GetFullName(),
            'enlace': 'ENL', 'enlace_clase': 'ElmCoup', 'enlace_ruta': enl.GetFullName()}
    plan = _plan_obras(alims, obras=[obra], aperturas_fichero=str(tmp_path / 'aperturas.json'), evaluando=True)
    informe, codigo = obras.aplicar(app, plan)
    assert codigo == 0, informe
    casos = obras.casos_del_proyecto(app, None)
    obras.restituir_pendientes(app, plan, casos, {})
    _caso(app, CON).Activate()
    assert (seccionadores[1].on_off, enl.on_off) == (1, 0)


def test_transferir_se_prueba_antes_que_el_nivel(monkeypatch, tmp_path):
    """098:RF-23, 098:RF-26 — con el oráculo, la transferencia (y la de un enlace nuevo) se mide antes del paso a 22,9 kV;
    las del enlace existente ya las juzgó el oráculo y no se repiten; si no cumple, entonces el nivel."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.web import services

    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas',
                        lambda ws, project: [{'sed': 'A', 'alimentador': 'F1', 'kw': 100.0, 'variacion': 'Carga_A'}])
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    v = eo.Variante('bancos', ('bancos',), [{'clase': 'condensador'}], {})
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {
        'alimentadores': {'F1': {'orden': [v], 'tabla': [{'nombre': 'bancos', 'cumple': False}], 'ya_cumple': False}},
        'tanda': 3})
    llamadas = []

    def escalera(ws, ctx, project, feeders, *, aplicar=False, traspaso=False, sin_oraculo=False, con_enlaces=True, **k):
        etapa = 'traspaso' if traspaso else 'nivel' if sin_oraculo else 'oraculo'
        llamadas.append(('aplica' if aplicar else 'mide', etapa, con_enlaces))
        return {'alimentadores': [{'alimentador': 'F1', 'elegida': 'nivel' if etapa == 'nivel' and not aplicar else None,
                                   'tabla': []}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)
    monkeypatch.setattr(services, 'confirmar_conjunto', lambda *a, **k: {'cumple': True})

    class _C:
        def __init__(self):
            self.textos = []

        def log(self, t):
            self.textos.append(t)

        def check_cancel(self):
            pass

    services.escalera_por_alimentador(object(), _C(), 'P', ['F1'])
    # 098:RF-45: bancos, sección y terna, cada uno en su turno; después la transferencia; después el nivel.
    assert [x[:2] for x in llamadas[:5]] == [('mide', 'oraculo')] * 3 + [('mide', 'traspaso'), ('mide', 'nivel')]
    assert llamadas[3][2] is False                       # el enlace existente ya lo juzgó el oráculo


def test_al_evaluar_la_transferencia_se_mide_y_todo_vuelve(monkeypatch, tmp_path):
    """098:RF-21, 098:RF-25 — la escalera mide la transferencia por el enlace existente con los dos alimentadores y,
    al borrar la variante evaluada, el enlace vuelve a abrirse y el seccionador a cerrarse (081:RF-81)."""
    from test_obras_pf_guion import CON, PERFIL_ESCALERA, _actual_no_cumple
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_evaluar_098', tools_en_path=True)
    app, _alims, n, seccionadores, enl = _red_con_enlace()
    _actual_no_cumple(monkeypatch)
    obra = {'clase': 'maniobra', 'alimentador': 'F1', 'vecino': 'F2', 'casos': [CON], 'tramo': f'F1_L{n}',
            'maniobra': 'Switch', 'maniobra_clase': 'StaSwitch', 'maniobra_ruta': seccionadores[1].GetFullName(),
            'enlace': 'ENL', 'enlace_clase': 'ElmCoup', 'enlace_ruta': enl.GetFullName()}
    plan = _plan_obras(['F1', 'F2'], variantes=[{'nombre': 'transferir', 'obras': [obra], 'costo_base': 0.0}],
                       sorteos=[], barras_cargas=[], parametros=PERFIL_ESCALERA,
                       aperturas_fichero=str(tmp_path / 'aperturas.json'))
    informe, codigo = obras.evaluar(app, plan)
    assert codigo == 0, informe
    assert [v['nombre'] for v in informe['variantes']] == ['transferir']
    _caso(app, CON).Activate()
    assert (seccionadores[1].on_off, enl.on_off) == (1, 0)
    assert obras.leer_aperturas(tmp_path / 'aperturas.json') == []


# =========================================================================== 098:RF-28 a RF-30 (T6 de «Con proyecto», 2026-11-07)
def test_la_variante_que_no_queda_aplicada_no_se_cuenta_como_no_cumple(monkeypatch):
    """098:RF-28 — CA101 (job 11469a95f83e): «cambio a 22.9 kV» dio las tensiones de sin obra: su flujo no convergía,
    la obra quedaba inactiva y se medía sin ella. Ahora se marca «no aplicada» con su causa."""
    from test_obras_pf_guion import (
        CON,
        PERFIL_ESCALERA,
        _actual_no_cumple,
        _calibrada_con_escenario,
        _obra_terna,
        _terna,
    )
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_no_aplicada_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(28))
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', _terna)
    _actual_no_cumple(monkeypatch)
    f = alims[0]
    antes = app.ldf.Execute

    def no_converge_con_la_obra():
        if any(str(v.loc_name).startswith('Obra_') for v in app.variaciones_activas):
            app.ldf_valido = False
            return 1
        return antes()

    app.ldf.Execute = no_converge_con_la_obra
    plan = _plan_obras(alims, variantes=[{'nombre': 'terna', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0}],
                       sorteos=[], barras_cargas=[], parametros=PERFIL_ESCALERA)
    informe, codigo = obras.evaluar(app, plan)
    assert codigo == 0, informe
    (fila,) = informe['variantes']
    assert fila['no_aplicada'].startswith('no aplicada') and 'inactiva' in fila['no_aplicada']
    assert not fila['maxima'] and fila['error'] == fila['no_aplicada'] and 'u_cargas' not in fila


def test_sin_cambio_alguno_es_no_aplicada():
    """098:RF-28 — la comprobación permanente: mismas tensiones y cargas que sin obra."""
    obras = cargar_herramienta('obras_pf.py', 'obras_sin_cambio_098', tools_en_path=True)
    a = {'converge': True, 'u': {'B1': 0.95, 'B2': 0.93}, 'carga': {'L1': 50.0}}
    assert obras.sin_cambio(a, {**a})
    assert not obras.sin_cambio(a, {**a, 'u': {'B1': 0.95, 'B2': 0.9301}})
    assert not obras.sin_cambio(a, {**a, 'carga': {'L1': 49.0}})
    assert not obras.sin_cambio(a, {'converge': False})


def test_la_lectura_da_las_barras_bajas_de_cada_alimentador():
    """098:RF-29 — ``--escalera-datos`` dice qué barras de media quedan bajo el límite, de la más baja a la menos."""
    from test_obras_pf_guion import _calibrada_con_escenario
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_bajas_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(29))
    informe, codigo = obras.datos_escalera(app, _plan_obras(alims, barras={alims[1]: []}, tension_min_pu=0.9999))
    assert codigo == 0, informe
    bajas = informe['alimentadores'][alims[1]]['bajas']
    assert bajas and [b['u'] for b in bajas] == sorted(b['u'] for b in bajas) and all(b['u'] < 0.9999 for b in bajas)


def test_el_alimentador_sin_cargas_que_viola_limites_lleva_su_escalera(monkeypatch, tmp_path):
    """098:RF-29 — CHN102 (2026-11-07) en 0,73 p.u. sin cargas nuevas no se trataba: ahora, antes que los demás, sube su
    escalera con sus barras bajas, primero transfiriendo y después desde los bancos, y lo elegido se aplica."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.web import services

    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas',
                        lambda ws, project: [{'sed': 'A', 'alimentador': 'F1', 'kw': 100.0, 'variacion': 'Carga_A'}])
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {})
    monkeypatch.setattr(services, '_bajas_sin_cargas', lambda ws, ctx, project, feeders, opciones: {'F2': ['F2_B3', 'F2_B2']})
    monkeypatch.setattr(services, 'confirmar_conjunto', lambda *a, **k: {'cumple': True})
    llamadas = []

    def escalera(ws, ctx, project, feeders, *, aplicar=False, traspaso=False, previas=None, cargas_activas=None, **k):
        f = feeders[0]
        llamadas.append((f, 'aplica' if aplicar else 'mide', 'traspaso' if traspaso else 'escalera', bool(previas)))
        elegida = 'bancos 2×300 kvar' if f == 'F2' and not traspaso else 'bancos' if f == 'F1' else None
        return {'alimentadores': [{'alimentador': f, 'elegida': elegida, 'tabla': []}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)

    class _C:
        def __init__(self):
            self.textos = []

        def log(self, t):
            self.textos.append(t)

        def check_cancel(self):
            pass

    ctx = _C()
    r = services.escalera_por_alimentador(object(), ctx, 'P', ['F1', 'F2'])
    de_f2 = [x for x in llamadas if x[0] == 'F2']
    assert de_f2 == [('F2', 'mide', 'traspaso', True), ('F2', 'mide', 'escalera', True), ('F2', 'aplica', 'escalera', True)]
    assert llamadas.index(de_f2[0]) < next(i for i, x in enumerate(llamadas) if x[0] == 'F1')
    f2 = r['por_alimentador']['F2']
    assert f2['sin_cargas_nuevas'] and f2['cumple'] and f2['barras_bajas'] == ['F2_B3', 'F2_B2']
    assert any('098:RF-29' in t for t in ctx.textos)
    assert eo is not None


def test_el_oraculo_se_corrige_con_lo_que_midio_digsilent():
    """098:RF-30 — CA101 + CHN102: el oráculo equilibrado daba 0,888 donde DIgSILENT medía 0,829. Con la tensión de
    DIgSILENT en el grafo, cada barra se lleva a lo medido y una obra mueve la caída en la misma proporción."""
    pytest.importorskip('scipy')
    from convertersmartgrid import optimizacion_oraculo as oo

    nueva = {'variacion': 'C1', 'nodo': _gid('A4', 'ElmTerm'), 'p_mw': 1.2, 'q_mvar': 0.36, 'alimentador': 'X', 'barra': 'A4'}
    crudo = oo.Oraculo(_grafo_dos(), [nueva])
    sin = crudo.medir([], 1)
    g = _grafo_dos()
    medido = {}
    for n, d in g['nodos'].items():
        corto = n.rsplit('\\', 1)[-1].rsplit('.', 1)[0]
        if corto in sin.u and not d.get('fuente'):
            medido[corto] = d['u_medida'] = 1.0 - 1.5 * (1.0 - sin.u[corto])      # DIgSILENT: 50 % más caída
    ora = oo.Oraculo(g, [nueva])
    con = ora.medir([], 1)
    assert all(con.u[b] == pytest.approx(medido[b], abs=1e-9) for b in medido)
    assert ora.desvio['barras'] == len(medido) and ora.desvio['max_pu'] > 0
    banco = [{'clase': 'condensador', 'barra': 'A4', 'q_kvar': 900.0}]
    sube_crudo = crudo.medir(banco, 1).u['A4'] - sin.u['A4']
    sube = ora.medir(banco, 1).u['A4'] - con.u['A4']
    assert sube == pytest.approx(1.5 * sube_crudo, rel=1e-6)
    assert ora.medir([], 1).v_min == pytest.approx(min(medido.values()), abs=1e-9)


# =========================================================================== 098:RF-31 a RF-35 (T6 de «Con proyecto», segunda corrida)
def _perfil_eo(**esc):
    return {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0,
                         'max_variantes': 400, 'secciones_normalizadas': ['AA05003D', 'AA12003D', 'AA24003D'], **esc},
            'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
            'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}


def _tipo_eo(codigo, mm2):
    return {'nombre': f'{codigo}_10kV_FICHA', 'clase': 'TypLne', 'origen': 'proyecto',
            'datos': {'uline': 10.0, 'sline': mm2 * 2.2 / 1000, 'cohl_': 1, 'rline': 30.0 / mm2, 'xline': 0.4}}


def test_las_obras_de_linea_de_dos_caminos_van_juntas():
    """098:RF-31 — CA101 (2026-11-07): la cola de CH_23 y la rama de CH_10 y CH_18, cada una con su camino; ahora hay
    variantes que juntan la obra de línea de los dos, con y sin bancos, y el tramo común va una vez, con el conductor
    mayor; la de 50 mm² no se propone para la caída (098:RF-33)."""
    from convertersmartgrid import escalera_optima as eo

    comun = [{'nombre': f'T{i}', 'largo_m': 1000.0, 'corriente_a': 80.0, 'inom_a': 110.0} for i in range(3)]
    cola = comun + [{'nombre': f'C{i}', 'largo_m': 1500.0, 'corriente_a': 40.0, 'inom_a': 110.0} for i in range(3)]
    rama = comun + [{'nombre': f'R{i}', 'largo_m': 1200.0, 'corriente_a': 50.0, 'inom_a': 110.0} for i in range(2)]
    cargas = [{'barra': 'COLA', 'existe': True, 'camino': cola}, {'barra': 'RAMA', 'existe': True, 'camino': rama}]
    tipos = [_tipo_eo('AA05003D', 50), _tipo_eo('AA12003D', 120), _tipo_eo('AA24003D', 240)]
    vs, _av = eo.variantes('X', 10.0, comun, cargas, tipos, eo.parametros(_perfil_eo()), banco_kvar=300.0)
    juntas = [v for v in vs if v.caminos == 2]
    assert juntas and all(v.nombre.endswith('en 2 caminos') for v in juntas)
    ambas = next(v for v in juntas if not v.escalones.count('bancos') and {o['clase'] for o in v.obras} == {'seccion'}
                 and len(v.obras) == 1 and v.obras[0]['tipo']['nombre'].startswith('AA24003D'))
    tramos = ambas.obras[0]['tramos']
    assert sorted(tramos) == sorted({t['nombre'] for t in cola + rama}) and len(tramos) == len(set(tramos))
    assert ambas.cantidades['seccion'] == pytest.approx((3 * 1000 + 3 * 1500 + 2 * 1200) / 1000)
    mixta = next(v for v in juntas if {o['clase'] for o in v.obras} == {'seccion', 'terna'} and 'bancos' not in v.escalones)
    assert mixta
    assert any('bancos' in v.escalones for v in juntas)
    assert not any('AA05003D' in str(o.get('tipo')) for v in juntas for o in v.obras)


def test_con_el_oraculo_gana_la_combinacion_de_los_dos_caminos():
    """098:RF-31, 098:RF-33 — con dos ramas bajo el límite, ninguna obra de un solo camino cumple y la que junta los
    dos sí: el oráculo la elige y solo esa (y las cercanas de una tanda) va a DIgSILENT."""
    pytest.importorskip('scipy')
    from convertersmartgrid import optimizacion_oraculo as oo
    from convertersmartgrid.escalera_optima import Variante

    nodos = {_gid('S', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0, 'q_mvar': 0, 'fuente': True, 'v_pu': 1.0},
             _gid('M', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0.2, 'q_mvar': 0.05, 'fuente': False},
             _gid('A', 'ElmTerm'): {'kv': 10.0, 'p_mw': 1.3, 'q_mvar': 0.3, 'fuente': False},
             _gid('B', 'ElmTerm'): {'kv': 10.0, 'p_mw': 1.3, 'q_mvar': 0.3, 'fuente': False}}
    # Sin obra, A y B a 0,937 p.u.; la sección de una rama arregla solo la suya; la de las dos, las dos.
    ramas = [{'id': _gid(n, 'ElmLne'), 'desde': _gid(a, 'ElmTerm'), 'hasta': _gid(b, 'ElmTerm'), 'r_ohm': r,
              'x_ohm': r * 0.75, 'inom_ka': 0.3, 'largo_km': 3.0, 'cerrada': True}
             for n, a, b, r in (('LSM', 'S', 'M', 0.4), ('LMA', 'M', 'A', 3.0), ('LMB', 'M', 'B', 3.0))]
    p = _p_098()
    nuevas = [{'variacion': 'NA', 'nodo': _gid('A', 'ElmTerm'), 'p_mw': 1.0, 'q_mvar': 0.2, 'alimentador': 'X', 'barra': 'A'},
              {'variacion': 'NB', 'nodo': _gid('B', 'ElmTerm'), 'p_mw': 1.0, 'q_mvar': 0.2, 'alimentador': 'X', 'barra': 'B'}]
    ora = oo.Oraculo({'nodos': nodos, 'ramas': ramas}, nuevas, tipos={'G': {'rline': 0.12, 'xline': 0.3, 'sline': 0.5}})

    def sec(tramos):
        return {'clase': 'seccion', 'tramos': tramos, 'tipo': {'nombre': 'G'}}
    vs = [Variante('sección en la rama A', ('seccion',), [sec(['LMA'])], {'seccion': 3.0}),
          Variante('sección en la rama B', ('seccion',), [sec(['LMB'])], {'seccion': 3.0}),
          Variante('sección en 2 caminos', ('seccion',), [sec(['LMA', 'LMB'])], {'seccion': 6.0}, caminos=2)]
    a = oo.Alimentador('X', vs, lambda v, perd: 1000.0 * v.cantidades.get('seccion', 0), None)
    e = oo.elegir_para_k(ora, [a], 2, p, evaluaciones_bayes=0, permutaciones=0, pareto=False)['X']
    assert e['elegida'] == 'sección en 2 caminos'
    assert [t['cumple'] for t in e['tabla'] if t['nombre'] != e['elegida']] == [False, False]
    assert oo.a_confirmar(e, 1)[0].nombre == 'sección en 2 caminos'


def test_lo_medido_con_la_misma_red_se_reutiliza_y_lo_dudoso_se_mide():
    """098:RF-32 — con la misma huella se reutiliza y se dice; con otra (otra ronda, otras cargas activas), sin
    huella comprobable o con un resultado sospechoso, se vuelve a medir."""
    from convertersmartgrid.web import services

    class _C:
        def __init__(self):
            self.textos = []

        def log(self, t):
            self.textos.append(t)

    plan = {'project': 'P', 'feeders': ['X'], 'estado_con_proyecto': ['Carga_A', 'Obra_tension_Y'], 'huella_red': 'h1',
            'apartar_cargas_de': [],
            'apartar_variaciones': [], 'barras_cargas': ['A'], 'sorteos': [{'factores': {'X': 0.9}}], 'parametros': {},
            'variantes': [{'nombre': 'sec', 'obras': [{'clase': 'seccion'}]}, {'nombre': 'ter', 'obras': [{'clase': 'terna'}]},
                          {'nombre': 'mal', 'obras': [{'clase': 'condensador'}]}]}
    memo = {}
    ev = {'variantes': [{'nombre': 'sec', 'maxima': False, 'u_cargas': {'A': 0.93}},
                        {'nombre': 'ter', 'maxima': True, 'fraccion': 1.0, 'u_cargas': {'A': 0.96}},
                        {'nombre': 'mal', 'maxima': False, 'no_aplicada': 'no aplicada: …', 'error': 'no aplicada: …'}]}
    services._guardar_medidas(plan, ev, memo)
    ctx = _C()
    ya, nuevas = services._medidas_ya_hechas(ctx, 'X', dict(plan), memo)
    assert set(ya) == {'sec', 'ter'} and [v['nombre'] for v in nuevas] == ['mal']
    assert any('reutilizadas' in t and 'de nuevo' in t and '098:RF-32' in t for t in ctx.textos)
    otra_ronda = {**plan, 'estado_con_proyecto': ['Carga_A', 'Carga_B', 'Obra_tension_Y']}
    ya, nuevas = services._medidas_ya_hechas(_C(), 'X', otra_ronda, memo)
    assert ya == {} and len(nuevas) == 3
    sin_estado = {**plan, 'estado_con_proyecto': None}
    ctx = _C()
    ya, nuevas = services._medidas_ya_hechas(ctx, 'X', sin_estado, memo)
    assert ya == {} and len(nuevas) == 3 and any('no se puede comprobar' in t for t in ctx.textos)
    # P1: las mismas variaciones por nombre con otro contenido (una carga nueva con otros kW) es otra red.
    otro_contenido = {**plan, 'huella_red': 'h2'}
    ya, nuevas = services._medidas_ya_hechas(_C(), 'X', otro_contenido, memo)
    assert ya == {} and len(nuevas) == 3
    ya, nuevas = services._medidas_ya_hechas(_C(), 'X', {**plan, 'huella_red': None}, memo)
    assert ya == {} and len(nuevas) == 3


def test_el_regulador_activa_el_ajuste_de_tomas_y_vuelve_al_borrar_la_variante(monkeypatch):
    """098:RF-34 — CHN102 (2026-11-07): con ``iopt_at = 0`` el regulador no cambiaba nada. La obra activa el ajuste de
    tomas del flujo del caso, lo anota y, al borrar la variante evaluada, el flujo vuelve a como estaba; y una variante
    con regulador igual a la misma sin él es «no aplicada»."""
    from test_obras_pf_guion import (
        CON,
        PERFIL_ESCALERA,
        _actual_no_cumple,
        _calibrada_con_escenario,
        _obra_terna,
        _terna,
    )
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_regulador_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(34))
    f = alims[0]
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', _terna)

    def regulador(ctx):
        obras._activar_en_el_flujo(ctx, 'iopt_at', 'las tomas')
        _terna(ctx)                       # la red del doble cambia con cualquier obra activa: aquí, la misma que la terna
    monkeypatch.setitem(obras.CONSTRUCTORES, 'regulador', regulador)
    _actual_no_cumple(monkeypatch)
    app.ldf.iopt_at = 0
    reg = {'clase': 'regulador', 'alimentador': f, 'casos': [CON], 'tramo': f'{f}_L1', 'consigna_pu': 1.0,
           'rango_pct': 10.0, 'pasos': 16, 'tipo': {'nombre': 'VR', 'clase': 'TypVoltreg'}}
    vistos = []
    medir = obras.medida_para_criterio

    def registrar(app_, alims_, feeders, **k):
        vistos.append(int(getattr(app.ldf, 'iopt_at', 0)))
        return medir(app_, alims_, feeders, **k)

    monkeypatch.setattr(obras, 'medida_para_criterio', registrar)
    from convertersmartgrid import obras_pf as op

    def plan_regulador(pl):           # sin tipo de regulador en el doble: se planifica como la terna de su tramo
        pl.elemento(pl.obra.tramo, 'ElmLne', 'regulador al principio del tramo')
    monkeypatch.setitem(op._PLANES, 'regulador', plan_regulador)
    plan = _plan_obras(alims, variantes=[{'nombre': 'terna', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0},
                                         {'nombre': 'terna + regulador', 'obras': [_obra_terna(f, [CON]), reg],
                                          'costo_base': 2.0}],
                       sorteos=[], barras_cargas=[], parametros=PERFIL_ESCALERA)
    informe, codigo = obras.evaluar(app, plan)
    assert codigo == 0, informe
    filas = {v['nombre']: v for v in informe['variantes']}
    assert 1 in vistos, 'con el regulador se midió con el ajuste de tomas'
    assert int(app.ldf.iopt_at) == 0, 'al borrar la variante, el flujo vuelve a como estaba'
    assert 'regulador no cambia' in (filas['terna + regulador'].get('no_aplicada') or ''), (filas['terna'].get('no_aplicada'), filas['terna'].get('error'), informe['avisos'][:3])


def _fila_eo(nombre, escalones, costo, horizonte=None, obras=()):
    return {'nombre': nombre, 'maxima': True, 'fraccion': 1.0, 'escalones': escalones, 'valle': None,
            'costo': {'costo_anual': costo, 'inversion': costo * 8}, 'horizonte': horizonte, 'motivos': [],
            'obras': list(obras), 'u_min_mt': 0.951}


def test_la_seccion_y_la_terna_tienen_costo_sin_libro_capex():
    """098:RF-35 — CHN102 (2026-11-07): sin libro CAPEX, el paso a 22,9 kV tenía costo y la sección no; ahora la
    sección se costea con el km del cambio de nivel y la terna con ese km por su factor (1,5, del perfil si lo da)."""
    from convertersmartgrid import escalera_optima as eo

    p = eo.parametros(_perfil_eo())
    costos = eo.costos_de_alternativas({}, p)
    nivel = costos['cambio_tension']['costo_unitario']
    assert costos['cambio_seccion']['costo_unitario'] == nivel
    assert costos['nueva_terna']['costo_unitario'] == pytest.approx(1.5 * nivel)
    assert '098:RF-35' in costos['nueva_terna']['origen'] and 'por 1.5' in costos['nueva_terna']['origen']
    p2 = eo.parametros(_perfil_eo(factor_terna_sin_capex=2.0))
    assert eo.costos_de_alternativas({}, p2)['nueva_terna']['costo_unitario'] == pytest.approx(2.0 * nivel)


def test_la_de_corto_plazo_tiene_que_llegar_al_anio_del_periodo():
    """098:RF-37 — usuario (2026-11-07): «el corto plazo debe ser solo para 4 años, considerando como año 0 el del
    análisis». Una que cumple hoy y no llega al año 4 no es la de corto plazo; la más barata que llega, sí. CA101: la
    terna con la sección de 240 mm² cumplía hoy y fallaba en el año 7."""
    from convertersmartgrid import escalera_optima as eo

    p = eo.parametros(_perfil_eo())
    terna = _fila_eo('terna en 62 tramos + 240 mm² en 9 tramos en 3 caminos', ('terna', 'seccion'), 500.0,
                     {'definitiva': False, 'aguanta_anios': 0, 'mas_corto': 4,
                      'motivos': ['S_U__HHUU_BUGANVILLA a 0.938 p.u.']})
    bancos = _fila_eo('3×300 kvar + terna en 62 tramos', ('bancos', 'terna'), 800.0,
                      {'definitiva': True, 'aguanta_anios': 4})
    d = eo.elegir([terna, bancos], p)
    assert d['elegida'] == bancos['nombre']
    motivo = next(t for t in d['tabla'] if t['nombre'] == terna['nombre'])['motivo']
    assert 'no llega al año del periodo' in motivo and 'BUGANVILLA' in motivo
    # Si ninguna llega, la más barata que cumple hoy, y se dice.
    d = eo.elegir([terna], p)
    assert d['elegida'] == terna['nombre'] and '098:RF-37' in d['aviso_periodo']
    # Sin medirlo (sin tasa), la de siempre.
    assert eo.elegir([{**terna, 'horizonte': None}, {**bancos, 'horizonte': None}], p)['elegida'] == terna['nombre']


def test_el_periodo_de_corto_plazo_sale_del_perfil():
    """098:RF-37 — del perfil (la clave del corto plazo, o el primer año del PIDE); si no, 4; y es el año que se mide."""
    from convertersmartgrid import escalera_optima as eo

    assert eo.periodo_de_corto_plazo({}) == 4
    assert eo.periodo_de_corto_plazo({'planificacion': {'anios_horizonte': [5, 10, 15]}}) == 5
    assert eo.periodo_de_corto_plazo({'escalera': {'periodo_corto_plazo_anios': 3},
                                      'planificacion': {'anios_horizonte': [5]}}) == 3
    p = eo.parametros({**_perfil_eo(), 'planificacion': {**_perfil_eo()['planificacion'], 'anios_horizonte': [5, 10]}})
    h = eo.plan_de_corto_plazo('F1', 0.03, p)
    assert h['anios'] == [5] and h['periodo'] == 5 and h['factores']['5']['F1'] == pytest.approx(1.03 ** 5)


def test_el_anio_en_que_vuelve_a_fallar_lo_busca_el_oraculo_y_lo_confirma_digsilent(tmp_path, monkeypatch):
    """098:RF-39, RF-40 — el oráculo busca el primer año que falla desde el siguiente al periodo; DIgSILENT mide solo
    ese año y el anterior; si no lo confirma, lo busca DIgSILENT. Va al informe con el año, la barra y la tensión, y no
    se busca ninguna obra de ese año."""
    from types import SimpleNamespace

    from convertersmartgrid import perfil_empresa
    from convertersmartgrid.web import services

    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: _perfil_eo())
    monkeypatch.setattr(services, 'carpeta_de', lambda *_a: '')
    monkeypatch.setattr(services, 'native_action_context', lambda *_a: {})
    falla_desde = 9

    class Ora:
        nuevas = [{}, {}]
        evaluaciones = 0

        def medir(self, obras, k, factor, alimentador):
            self.evaluaciones += 1
            anio = round(__import__('math').log(factor) / __import__('math').log(1.03))
            u = 0.96 if anio < falla_desde else 0.94
            return SimpleNamespace(para_criterio=lambda: {'converge': True, 'u': {'COLA': u}, 'carga': {}})
    planes = []

    def guion(ws_, ctx_, script, plan, **k):
        planes.append(plan)
        anios = list(plan.get('anios') or [])
        vistos = {str(a): {'cumple': a < falla_desde,
                           'motivos': [] if a < falla_desde else ['COLA a 0.940 p.u.']} for a in anios}
        return 0, {'anios': vistos, 'medidos': len(vistos)}, None
    monkeypatch.setattr(services, '_guion_pf', guion)
    ws = _ws_con_obras(tmp_path, [])
    services._guardar_alternativas_escalera(ws, 'P', 'F1', [{'nombre': 'bancos', 'elegida': True}])
    memo = {'oraculo_prep': {'ora': Ora()}}
    r = services._anio_de_problemas(ws, _Registro(), 'P', 'F1', [{'clase': 'condensador'}], memo, {}, 'bancos')
    assert r['anio'] == falla_desde and r['barra'] == 'COLA' and r['u'] == pytest.approx(0.94)
    assert [p_.get('anios') for p_ in planes] == [[falla_desde - 1, falla_desde]], 'DIgSILENT, solo esos dos años'
    assert not any('variantes' in p_ for p_ in planes), 'ninguna obra futura se busca ni se mide'
    guardada = services.alternativas_de_la_escalera(ws, 'P')['F1'][0]
    assert guardada['vuelve_a_fallar']['anio'] == falla_desde
    from convertersmartgrid.informes import filas_alternativas_escalera
    cabecera, filas = filas_alternativas_escalera({'F1': [{**guardada, 'numero': 1, 'costo_anual': 1.0,
                                                           'plazo': 'corto plazo'}]})
    texto = filas[0][cabecera.index('Plazo')]
    assert f'vuelve a tener problemas en el año {falla_desde}' in texto and 'COLA a 0.940' in texto and 'PIDE' in texto
    # Si DIgSILENT no lo confirma, lo busca él.
    falla_desde_digsilent = 12

    def guion2(ws_, ctx_, script, plan, **k):
        planes.append(plan)
        if plan.get('buscar'):
            return 0, {'anios': {str(falla_desde_digsilent): {'cumple': False, 'motivos': ['COLA a 0.930 p.u.']}},
                       'primer_anio': falla_desde_digsilent, 'medidos': 4}, None
        return 0, {'anios': {str(a): {'cumple': True, 'motivos': []} for a in plan.get('anios') or []}, 'medidos': 2}, None
    monkeypatch.setattr(services, '_guion_pf', guion2)
    r = services._anio_de_problemas(ws, _Registro(), 'P', 'F1', [{'clase': 'condensador'}], {'oraculo_prep': {'ora': Ora()}},
                                    {}, 'bancos')
    assert r['anio'] == falla_desde_digsilent and planes[-1]['desde'] == 5 and planes[-1]['buscar'] == 30


def test_el_guion_busca_el_primer_anio_que_falla_por_biseccion(tmp_path, monkeypatch):
    """098:RF-39 — sin oráculo, DIgSILENT por bisección desde el año siguiente al periodo: pocos flujos."""
    from convertersmartgrid import escalera_optima as eo

    vistos = []

    def cumple(anio):
        vistos.append(anio)
        return anio < 11
    assert eo.primer_anio_que_falla(cumple, 5, 30) == 11 and len(vistos) <= 6
    assert eo.primer_anio_que_falla(lambda a: True, 5, 30) is None


class _Registro:
    def __init__(self):
        self.textos = []

    def log(self, t):
        self.textos.append(t)

    def check_cancel(self):
        pass


def _ws_con_obras(tmp_path, registros):
    from types import SimpleNamespace

    return SimpleNamespace(out_dir=tmp_path, obras_aplicadas=list(registros), obras=[], lock=__import__('threading').Lock(),
                           save=lambda: None)


def test_solo_se_compara_y_se_retira_lo_que_aplico_la_escalera(tmp_path, monkeypatch):
    """098:RF-36 — 040:RF-8, 014:RF-3: lo que el operador aplicó no se compara ni se retira; lo aplicado sin origen se
    compara (y «rehacer obras» lo retira) solo si la escalera aplicó esa misma obra: su elegida guardada con lo aplicado
    o el plan con que aplicó su elegida, con una obra igual (M1: CHN102, «Obra_tension_CHN102» y la elegida «cambio a
    22.9 kV…»); sin esa evidencia, se avisa y no se toca."""
    from convertersmartgrid.web import services

    ws = _ws_con_obras(tmp_path, [
        {'project': 'P', 'variacion': 'Obra_tension_F1', 'obra': {'alimentador': 'F1', 'clase': 'tension'}},
        {'project': 'P', 'variacion': 'Obra_seccion_F1', 'obra': {'alimentador': 'F1', 'clase': 'seccion'},
         'origen': 'operador'},
        {'project': 'P', 'variacion': 'Obra_terna_F2', 'obra': {'alimentador': 'F2', 'clase': 'terna'}},
        {'project': 'P', 'variacion': 'Obra_condensador_F3', 'obra': {'alimentador': 'F3', 'clase': 'condensador'},
         'origen': 'escalera', 'eleccion': {'nombre': 'bancos 1×300 kvar', 'huella': 'h', 'regla': 'r',
                                             'escalones': ['bancos'], 'cantidades': {'bancos': 1.0}}}])
    services._guardar_alternativas_escalera(ws, 'P', 'F1 · sin cargas nuevas, fuera de límites', [
        {'nombre': 'cambio a 22.9 kV con su fuente (29.30 km, 50 SED)', 'escalones': ['nivel'], 'elegida': True}])
    services._guardar_alternativas_escalera(ws, 'P', 'F2', [{'nombre': 'bancos', 'escalones': ['bancos'], 'elegida': True}])
    # Como CHN102: el plan con que la escalera aplicó su elegida, con la obra del registro.
    ws.plans_dir = tmp_path / 'planes'
    ws.plans_dir.mkdir()
    (ws.plans_dir / 'escalera_evaluar_x.json').write_text(__import__('json').dumps({
        'project': 'P', 'aplicando_elegida': True, 'variantes': [
            {'nombre': 'cambio a 22.9 kV con su fuente (29.30 km, 50 SED)',
             'obras': [{'alimentador': 'F1', 'clase': 'tension'}]}]}), encoding='utf-8')
    ctx = _Registro()
    comparar = services._obras_a_comparar(ws, ctx, 'P', ['F1', 'F2', 'F3'])
    assert set(comparar) == {'F1', 'F3'}
    assert comparar['F1']['variaciones'] == ['Obra_tension_F1'] and comparar['F1']['nombre'].startswith('cambio a 22.9 kV')
    assert comparar['F3']['cantidades'] == {'bancos': 1.0} and comparar['F3']['escalones'] == ['bancos']
    assert any('Obra_terna_F2' in t and 'no se compara ni se retira' in t for t in ctx.textos)
    planes = []
    monkeypatch.setattr(services, 'carpeta_de', lambda *_a: '')
    monkeypatch.setattr(services, 'native_action_context', lambda *_a: {})
    monkeypatch.setattr(services, '_guion_pf', lambda ws_, ctx_, guion, plan, **k: (
        planes.append(plan), (0, {'retiradas': list(plan['variaciones'])}, None))[1])
    services._retirar_obras(ws, ctx, 'P', ['F1', 'F2'], 2026, sin_origen=True)
    assert planes[-1]['variaciones'] == ['Obra_tension_F1'], 'sin evidencia (F2) ni del operador, nunca'
    assert any('Obra_terna_F2 no se retira' in t for t in ctx.textos)
    assert {a['variacion'] for a in ws.obras_aplicadas} == {'Obra_seccion_F1', 'Obra_terna_F2', 'Obra_condensador_F3'}


def test_una_elegida_no_aplicada_no_es_evidencia_y_la_seccion_del_operador_no_se_toca(tmp_path):
    """098:RF-36 (M1) — una sección aplicada sin origen y una elegida guardada por una evaluación que no aplicó nada, con
    escalón «seccion»: no es evidencia, no se compara ni se retira; con la elegida aplicada de otra sección (otros
    tramos), tampoco; con la misma, sí."""
    from convertersmartgrid.web import services

    sec = {'alimentador': 'F1', 'clase': 'seccion', 'tramos': ['L1', 'L2'], 'tipo': {'nombre': 'AA24003D'}}
    ws = _ws_con_obras(tmp_path, [{'project': 'P', 'variacion': 'Obra_seccion_F1', 'obra': sec}])
    services._guardar_alternativas_escalera(ws, 'P', 'F1', [{'nombre': 'sección AA24003D', 'escalones': ['seccion'],
                                                             'elegida': True}])
    ctx = _Registro()
    assert services._obras_a_comparar(ws, ctx, 'P', ['F1']) == {}
    assert any('no se compara ni se retira' in t for t in ctx.textos)
    services._marcar_aplicada(ws, 'P', 'F1', 'sección AA24003D', ['Obra_seccion_F1_7'], [{**sec, 'tramos': ['L3']}])
    assert services._obras_a_comparar(ws, _Registro(), 'P', ['F1']) == {}
    services._marcar_aplicada(ws, 'P', 'F1', 'sección AA24003D', ['Obra_seccion_F1_7'], [dict(sec)])
    assert set(services._obras_a_comparar(ws, _Registro(), 'P', ['F1'])) == {'F1'}


def test_retirar_obras_borra_solo_las_nombradas(monkeypatch):
    """098:RF-36, 042:RF-60 — el guion real borra solo las variaciones nombradas de los alimentadores pedidos: la obra
    del operador y una «Obra_x_F1» sin registro se quedan; sin nombres no borra nada."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario

    obras = cargar_herramienta('obras_pf.py', 'obras_retirar_nombres_098', tools_en_path=True)
    app, _alims = _calibrada_con_escenario(random.Random(41))
    _caso(app, CON).Activate()
    for nombre in ('Obra_tension_F1', 'Obra_seccion_F1', 'Obra_x_F1'):
        fake_pf.variacion_del_operador(app, nombre, [])
    plan = {'project': 'P', 'feeders': ['F1']}
    informe, codigo = obras.retirar_obras(app, plan)
    assert codigo == 0 and informe['retiradas'] == [] and any('nombres exactos' in a for a in informe['avisos'])
    informe, codigo = obras.retirar_obras(app, {**plan, 'variaciones': ['Obra_tension_F1', 'Obra_terna_F2']})
    assert codigo == 0 and informe['retiradas'] == ['Obra_tension_F1']
    quedan = {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)}
    assert {'Obra_seccion_F1', 'Obra_x_F1'} <= quedan and 'Obra_tension_F1' not in quedan
    assert any('Obra_terna_F2' in a for a in informe['avisos'])


def test_la_vieja_se_cambia_solo_si_la_nueva_cumple_y_cuesta_menos():
    """098:RF-36 — con la fila de la vieja medida en esta corrida: se conserva si nada cambió, si sin ella ya cumple (y se
    dice que sobra), si su medida es dudosa, si ninguna cumple, si vuelve a ganar o si la nueva no cuesta menos; se
    cambia si cuesta menos o si la vieja ya no cumple. ``ok`` solo si lo que queda cumple (M2)."""
    from convertersmartgrid.web import services

    vieja = {'nombre': 'cambio a 22.9 kV', 'variaciones': ['Obra_tension_F1']}
    cumple = {'factible': True, 'costo_anual': 1200.0, 'dudosa': None}
    nueva = {'nombre': '1×300 kvar + sección', 'costo_anual': 700.0, 'factible': True}

    def fila(elegida, v=cumple, tabla=(nueva,), **k):
        return {'elegida': elegida, 'tabla': list(tabla), 'vieja': v, **k}
    d = services._decidir_sustitucion
    assert d(fila(None, conserva='x'), vieja)[::2] == (False, True)
    cambia, motivo, ok = d(fila(None, ya_cumple=True), vieja)
    assert not cambia and ok and 'sobra' in motivo
    cambia, motivo, ok = d(fila(nueva['nombre'], {'dudosa': 'su medida tuvo un error'}), vieja)
    assert not cambia and 'dudosa' in motivo and ok
    assert d(fila(None), vieja)[::2] == (False, True)
    no_cumple = {'factible': False, 'motivo': 'no cumple con la máxima', 'costo_anual': 500.0, 'dudosa': None}
    cambia, motivo, ok = d(fila(None, no_cumple), vieja)
    assert not cambia and not ok and 'tampoco' in motivo, 'la vieja que no cumple no resuelve: sigue la obra integral'
    assert d(fila('cambio a 22.9 kV'), vieja)[0] is False
    assert d(fila(nueva['nombre']), vieja)[0] is True
    assert d(fila(nueva['nombre'], tabla=({**nueva, 'costo_anual': 1300.0},)), vieja)[0] is False
    cambia, motivo, ok = d(fila(nueva['nombre'], no_cumple), vieja)
    assert cambia and ok and 'ya no cumple' in motivo


def test_sustituir_aplica_la_nueva_y_si_no_queda_la_vieja_sigue(tmp_path):
    """098:RF-36 — el servicio no borra nada: pide al guion la sustitución con la vieja; si la nueva no queda, la vieja
    sigue, activa, y no se recrea; si queda, la sustituye. Sin cambio, ni se llama."""
    from convertersmartgrid.web import services

    ws = _ws_con_obras(tmp_path, [])
    vieja = {'nombre': 'cambio a 22.9 kV', 'variaciones': ['Obra_tension_F1'], 'operacion': [{'variacion': 'Obra_tension_F1',
                                                                                             'abiertos': []}]}
    fila = {'elegida': 'bancos', 'tabla': [{'nombre': 'bancos', 'costo_anual': 100.0, 'factible': True}],
            'vieja': {'factible': True, 'costo_anual': 1200.0, 'dudosa': None}}
    pedidas = []

    def aplicar(hecha):
        def nueva(sust):
            pedidas.append(sust)
            return {'alimentadores': [{'sustitucion': hecha}]}
        return nueva
    ctx = _Registro()
    r = services._sustituir(ws, ctx, 'P', 'F1', vieja, fila, aplicar({'hecha': False, 'motivo': 'no converge'}), 2026)
    assert r['repuesta'] and r['ok'] and r['sustituta'] is None
    assert pedidas[-1] == {'variaciones': ['Obra_tension_F1'], 'operacion': vieja['operacion'], 'alimentador': 'F1'}
    r = services._sustituir(ws, ctx, 'P', 'F1', vieja, fila, aplicar({'hecha': True, 'retiradas': ['Obra_tension_F1']}), 2026)
    assert r['sustituta'] == 'bancos' and r['ok']
    n = len(pedidas)
    r = services._sustituir(ws, ctx, 'P', 'F1', vieja, {**fila, 'elegida': None}, aplicar({'hecha': True}), 2026)
    assert len(pedidas) == n and r['sustituta'] is None


def _con_obra_vieja(obras, tmp_path, semilla):
    """Un proyecto del doble con la obra vieja de la escalera aplicada en «Con proyecto» (una terna en L1)."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario, _obra_terna
    from test_obras_pf_guion import _plan as _plan_obras

    app, alims = _calibrada_con_escenario(random.Random(semilla))
    app.atributos_en_variacion = app.servicio_en_escenario = True
    f = alims[0]
    plan = _plan_obras(alims, obras=[_obra_terna(f, [CON])], aperturas_fichero=str(tmp_path / 'aperturas.json'))
    informe, _codigo = obras.aplicar(app, plan)
    (fila,) = informe['obras']
    assert fila['variacion'] and not fila['error'], fila
    return app, alims, f, fila['variacion'], plan


def _activa(app, nombre):
    from test_obras_pf_guion import CON

    _caso(app, CON).Activate()
    return nombre in {v.loc_name for v in app.GetActiveNetworkVariations() or []}


def _existe(app, nombre):
    return nombre in {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)}


def test_el_guion_sustituye_primero_la_nueva_y_despues_borra_la_vieja(tmp_path):
    """098:RF-36 — con la guion real: la nueva queda activa y la vieja se borra entera; el diario sale del registro."""
    from test_obras_pf_guion import CON, _obra_terna

    obras = cargar_herramienta('obras_pf.py', 'obras_sustituir_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 51)
    informe, codigo = obras.sustituir(app, {**plan, 'obras': [_obra_terna(f, [CON], ('L2',))],
                                            'sustituir': {'variaciones': [vieja], 'operacion': [], 'alimentador': f}})
    assert informe['sustitucion']['hecha'] and informe['sustitucion']['retiradas'] == [vieja], informe.get('avisos')
    (nueva,) = [o['variacion'] for o in informe['obras']]
    assert not _existe(app, vieja) and _activa(app, nueva)
    assert not [e for e in obras.leer_aperturas(tmp_path / 'aperturas.json') if e.get('accion') == 'sustitucion']


@pytest.mark.parametrize('como', ['no_queda', 'parcial', 'excepcion'])
def test_si_la_nueva_falla_se_deshace_y_la_vieja_sigue_activa_y_entera(tmp_path, monkeypatch, como):
    """098:RF-36 — la nueva no queda (su constructor falla), queda a medias (la segunda de dos falla) o la orden se corta
    con una excepción: lo creado de la nueva se borra y la vieja, que nunca se borró, vuelve a estar activa."""
    from test_obras_pf_guion import CON, _obra_terna, _terna

    obras = cargar_herramienta('obras_pf.py', f'obras_sustituir_falla_{como}', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 52)
    antes = {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)}
    llamadas = []

    def terna(ctx):
        llamadas.append(1)
        if como == 'no_queda' or (como == 'parcial' and len(llamadas) == 2):
            raise RuntimeError('DIgSILENT no la deja crear')
        _terna(ctx)
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', terna)
    nuevas = [_obra_terna(f, [CON], ('L2',))] + ([_obra_terna(f, [CON], ('L3',))] if como == 'parcial' else [])
    plan_s = {**plan, 'obras': nuevas, 'sustituir': {'variaciones': [vieja], 'operacion': [], 'alimentador': f}}
    if como == 'excepcion':
        real = obras.aplicar

        def se_corta(app_, plan_, **k):
            real(app_, plan_, **k)
            raise KeyboardInterrupt('cancelada')
        monkeypatch.setattr(obras, 'aplicar', se_corta)
        with pytest.raises(KeyboardInterrupt):
            obras.sustituir(app, plan_s)
    else:
        informe, codigo = obras.sustituir(app, plan_s)
        assert codigo == 2 and not informe['sustitucion']['hecha']
        assert all(o['error'].startswith('deshecha') for o in informe['obras'])
    assert _existe(app, vieja) and _activa(app, vieja), 'la vieja sigue, activa'
    assert {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)} == antes, 'nada de la nueva queda'
    assert not [e for e in obras.leer_aperturas(tmp_path / 'aperturas.json') if e.get('accion') == 'sustitucion']


def test_el_retiro_incompleto_de_la_vieja_se_dice(tmp_path):
    """098:RF-36 (M4c) — si una variación de la vieja no se deja borrar, la nueva queda, la que no se borró sigue
    desactivada y el informe la nombra, con código de error."""
    from test_obras_pf_guion import CON, _obra_terna

    obras = cargar_herramienta('obras_pf.py', 'obras_sustituir_incompleto_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 53)
    var = next(v for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1) if v.loc_name == vieja)
    object.__setattr__(var, 'Delete', lambda *_a: 1)
    informe, codigo = obras.sustituir(app, {**plan, 'obras': [_obra_terna(f, [CON], ('L2',))],
                                            'sustituir': {'variaciones': [vieja], 'operacion': [], 'alimentador': f}})
    assert codigo == 2 and informe['sustitucion']['sin_borrar'] == [vieja]
    assert any(vieja in a and 'no se borró entera' in a for a in informe['avisos'])
    assert _existe(app, vieja) and not _activa(app, vieja)


@pytest.mark.parametrize('paso', ['operacion_deshecha', 'nueva_verificada'])
def test_la_sustitucion_cortada_se_completa_o_se_deshace_al_empezar_la_siguiente(tmp_path, paso):
    """098:RF-36 (M4d) — el proceso murió a mitad: con la nueva sin comprobar, la siguiente orden la borra y la vieja
    vuelve a estar activa; con la nueva ya comprobada, borra la vieja."""
    from test_obras_pf_guion import CON, _obra_terna

    obras = cargar_herramienta('obras_pf.py', f'obras_sustitucion_cortada_{paso}', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 54)
    antes = sorted(v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1))
    casos = obras.casos_del_proyecto(app, None)
    # Lo que hizo la orden antes de morir: vieja apartada, nueva creada, el diario en su paso.
    _caso(app, CON).Activate()
    next(v for v in app.GetActiveNetworkVariations() if v.loc_name == vieja).Deactivate()
    hecho, _rc = obras.aplicar(app, {**plan, 'obras': [_obra_terna(f, [CON], ('L2',))]})
    nueva = hecho['obras'][0]['variacion']
    obras._diario(plan, {'accion': 'sustitucion', 'id': 'x1', 'proyecto': 'P', 'caso': CON, 'paso': paso,
                         'viejas': [vieja], 'antes': antes, 'operacion': [], 'apartadas': [vieja], 'creadas': [nueva],
                         'feeders': [f]})
    informe = {'avisos': []}
    obras.restituir_pendientes(app, plan, casos, informe)
    if paso == 'nueva_verificada':
        assert not _existe(app, vieja) and _activa(app, nueva)
    else:
        assert _existe(app, vieja) and _activa(app, vieja) and not _existe(app, nueva)
    assert any('098:RF-36' in a for a in informe['avisos'])
    assert not [e for e in obras.leer_aperturas(tmp_path / 'aperturas.json') if e.get('accion') == 'sustitucion']


def test_la_medida_cortada_con_la_vieja_apartada_la_devuelve(tmp_path):
    """098:RF-36 (M4d) — la evaluación anota la obra que aparta; si muere con ella fuera, la siguiente orden la activa."""
    from test_obras_pf_guion import CON

    obras = cargar_herramienta('obras_pf.py', 'obras_apartada_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 55)
    casos = obras.casos_del_proyecto(app, None)
    obras.anotar_apartadas(plan, casos['con'], [vieja])
    _caso(app, CON).Activate()
    next(v for v in app.GetActiveNetworkVariations() if v.loc_name == vieja).Deactivate()
    informe = {'avisos': []}
    obras.restituir_pendientes(app, plan, casos, informe)
    assert _activa(app, vieja) and any(vieja in a for a in informe['avisos'])
    assert obras.leer_aperturas(tmp_path / 'aperturas.json') == []


def test_la_obra_de_la_escalera_se_mide_fuera_y_se_conserva_si_nada_cambio(tmp_path, monkeypatch):
    """098:RF-36 (M6) — la vieja va fuera de la lectura y de la medida (por su nombre) y se mide como una variante más;
    la huella que se guarda al aplicar es la del paso de evaluar de la elegida: con ella, la siguiente corrida conserva
    sin medir; con otra, mide. La vieja que no cumple sale con su fila (M2)."""
    from test_casos_por_anio import ANIO, _escalera_falsa

    def evaluar(nombre):
        cumple = nombre.startswith('sección')
        return {'nombre': nombre, 'maxima': cumple, 'fraccion': 1.0 if cumple else None, 'perdidas_kw': 10.0,
                'motivos': [] if cumple else ['no converge'], 'u_cargas': {'F1_B4': 0.96 if cumple else 0.93}}

    services, ws, ctx, planes, _aplicadas, _apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'bancos': 9000, 'nueva_terna': 40000, 'cambio_seccion': 30000})
    falso = services._guion_pf
    monkeypatch.setattr(services, '_guion_pf', lambda ws_, ctx_, script, plan, *, nombre, args=(), **k: (
        lambda r: (r[0], {**r[1], 'huella_red': 'h1'} if '--escalera-datos' in args else r[1], r[2]))(
        falso(ws_, ctx_, script, plan, nombre=nombre, args=args, **k)))
    elecciones = []
    ejecutar = services.obras_ejecutar
    monkeypatch.setattr(services, 'obras_ejecutar', lambda *a, **k: (elecciones.append(k.get('eleccion')),
                                                                     ejecutar(*a, **k))[1])
    from convertersmartgrid import escalera_optima as eo

    r1 = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=False, por_alternativas=True)
    f1 = r1['alimentadores'][0]
    services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=True, solo={'F1': f1['elegida']},
                            huellas={'F1': f1['huella_eleccion']})
    guardada = elecciones[-1]
    assert guardada['huella'] == f1['huella_eleccion'] and guardada['regla'] == eo.REGLA_DE_PLAZOS
    assert guardada['cantidades'] and guardada['escalones']
    vieja = {'nombre': guardada['nombre'], 'huella': guardada['huella'], 'regla': guardada['regla'],
             'variaciones': ['Obra_seccion_F1'], 'obras': [{'clase': 'seccion'}], 'cantidades': guardada['cantidades'],
             'escalones': guardada['escalones']}
    n = len([1 for a, _p in planes if '--evaluar' in a])
    r2 = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=False, por_alternativas=True,
                                 apartar_obras={'F1': ['Obra_seccion_F1']}, conservar={'F1': vieja})
    assert r2['alimentadores'][0]['conserva'] == guardada['nombre']
    assert len([1 for a, _p in planes if '--evaluar' in a]) == n, 'conservada sin medir'
    assert [p for a, p in planes if '--escalera-datos' in a][-1]['apartar_obras'] == ['Obra_seccion_F1']
    r3 = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=False, por_alternativas=True,
                                 apartar_obras={'F1': ['Obra_seccion_F1']},
                                 conservar={'F1': {**vieja, 'nombre': 'bancos viejos', 'huella': 'otra'}})
    f3 = r3['alimentadores'][0]
    assert not f3.get('conserva') and f3['vieja']['factible'] is False and not f3['vieja']['dudosa']
    medidas = [p for a, p in planes if '--evaluar' in a]
    assert all(p['apartar_obras'] == ['Obra_seccion_F1'] for p in medidas[n:])
    assert any(v['nombre'] == 'obra aplicada: bancos viejos' for p in medidas[n:] for v in p['variantes'])


def test_la_vieja_dudosa_no_se_sustituye(tmp_path, monkeypatch):
    """098:RF-36 — si la medida de la vieja sale con error, no se sustituye por ello: se conserva y se dice."""
    from test_casos_por_anio import ANIO, _escalera_falsa

    def evaluar(nombre):
        if nombre.startswith('obra aplicada'):
            return {'nombre': nombre, 'maxima': False, 'error': 'DIgSILENT no la dejó crear', 'u_cargas': {}}
        cumple = nombre.startswith('sección')
        return {'nombre': nombre, 'maxima': cumple, 'fraccion': 1.0 if cumple else None, 'perdidas_kw': 10.0,
                'motivos': [], 'u_cargas': {'F1_B4': 0.96}}

    services, ws, ctx, _planes, _aplicadas, _apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'bancos': 9000, 'nueva_terna': 40000, 'cambio_seccion': 30000})
    vieja = {'nombre': 'bancos viejos', 'variaciones': ['Obra_condensador_F1'], 'obras': [{'clase': 'condensador'}],
             'cantidades': {'bancos': 1.0}, 'escalones': ['bancos']}
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=False, conservar={'F1': vieja},
                                apartar_obras={'F1': vieja['variaciones']})
    f1 = r['alimentadores'][0]
    assert f1['vieja']['dudosa'] == 'su medida tuvo un error'
    cambia, motivo, _ok = services._decidir_sustitucion(f1, vieja)
    assert not cambia and 'dudosa' in motivo


def test_dos_reguladores_comparten_el_ajuste_de_tomas(tmp_path):
    """098:RF-34 — al retirar una obra con regulador, el ajuste de tomas no se apaga mientras otra variación activa tenga
    el suyo; se dice."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario

    obras = cargar_herramienta('obras_pf.py', 'obras_dos_reguladores_098', tools_en_path=True)
    app, _alims = _calibrada_con_escenario(random.Random(42))
    casos = obras.casos_del_proyecto(app, None)
    _caso(app, CON).Activate()
    otra = fake_pf.variacion_del_operador(app, 'Obra_regulador_F2', [])
    etapa = otra.GetContents('*.IntSstage')[0]
    etapa.CreateObject('ElmVoltreg', 'Regulador_F2_L1')
    app.ldf.iopt_at = 1
    avisos: list[str] = []
    valores = [{'clase': 'ComLdf', 'caso': CON, 'atributo': 'iopt_at', 'valor': 0}]
    assert obras.restituir_valores(app, casos, valores, avisos) == 0
    assert int(app.ldf.iopt_at) == 1 and any('Obra_regulador_F2' in a for a in avisos)
    otra.Deactivate()
    avisos.clear()
    assert obras.restituir_valores(app, casos, valores, avisos) == 1 and int(app.ldf.iopt_at) == 0


def test_el_ajuste_de_tomas_vuelve_al_retirar_la_ultima_obra_con_regulador(tmp_path):
    """098:RF-34 (M5) — el ajuste de tomas de antes de la primera obra con regulador se guarda por proyecto y caso; al
    retirar la primera, sigue (la otra lo necesita) y se dice; al retirar la segunda, que lo encontró ya activo y no
    anotó nada, vuelve a como estaba."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario

    obras = cargar_herramienta('obras_pf.py', 'obras_segundo_retiro_098', tools_en_path=True)
    app, _alims = _calibrada_con_escenario(random.Random(45))
    casos = obras.casos_del_proyecto(app, None)
    _caso(app, CON).Activate()
    plan = {'project': 'P', 'feeders': ['F1'], 'aperturas_fichero': str(tmp_path / 'aperturas.json')}
    app.ldf.iopt_at = 0
    ctx = obras.Contexto(app, app.proyecto, None, {'variacion': 'Obra_regulador_F1', 'avisos': []}, None, None, plan=plan)
    ctx.casos = {'con': casos['con']}
    obras._activar_en_el_flujo(ctx, 'iopt_at', 'las tomas')
    assert int(app.ldf.iopt_at) == 1
    for nombre in ('Obra_regulador_F1', 'Obra_regulador_F1_2'):
        v = fake_pf.variacion_del_operador(app, nombre, [])
        v.GetContents('*.IntSstage')[0].CreateObject('ElmVoltreg', f'Regulador_{nombre}')
    informe, _c = obras.retirar_obras(app, {**plan, 'variaciones': ['Obra_regulador_F1']})
    assert informe['retiradas'] == ['Obra_regulador_F1'] and int(app.ldf.iopt_at) == 1
    assert any('Obra_regulador_F1_2' in a and 'sigue activo' in a for a in informe['avisos'])
    informe, _c = obras.retirar_obras(app, {**plan, 'variaciones': ['Obra_regulador_F1_2']})
    assert informe['retiradas'] == ['Obra_regulador_F1_2'] and int(app.ldf.iopt_at) == 0
    assert not [e for e in obras.leer_aperturas(tmp_path / 'aperturas.json') if e.get('accion') == 'original']


def test_la_huella_de_la_red_ve_el_contenido_el_tipo_y_la_operacion():
    """098:RF-32 — con la misma red, la misma huella; cambia con lo que graba una etapa, con la sección del tipo (aunque
    se llame igual) y con lo que se abre en el escenario; si no se puede leer, ``None``."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario

    obras = cargar_herramienta('obras_pf.py', 'obras_huella_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(43))
    _caso(app, CON).Activate()
    red = obras.Alimentadores(app, app.proyecto, alims)
    v = fake_pf.variacion_del_operador(app, 'Carga_Q_F1_1', [])
    carga = v.GetContents('*.IntSstage')[0].CreateObject('ElmLod', 'Q')
    carga.plini = 100.0
    h0 = obras.huella_de_la_red(app, red, alims)
    assert h0 and obras.huella_de_la_red(app, red, alims) == h0
    carga.plini = 150.0
    h1 = obras.huella_de_la_red(app, red, alims)
    assert h1 != h0
    linea = app.GetCalcRelevantObjects('*.ElmLne')[0]
    linea.typ_id.sline = float(getattr(linea.typ_id, 'sline', 0.2) or 0.2) * 2
    h2 = obras.huella_de_la_red(app, red, alims)
    assert h2 != h1
    tramo = next(iter(app.GetCalcRelevantObjects('*.ElmLne')), None)
    tramo.outserv = 1
    assert obras.huella_de_la_red(app, red, alims) != h2

    class Rota:
        def GetActiveNetworkVariations(self):
            raise RuntimeError('sin caso activo')
    assert obras.huella_de_la_red(Rota(), red, alims) is None


def test_el_alcance_de_cada_una_que_cumple_aunque_sea_de_la_misma_clase(monkeypatch):
    """098:RF-35 (H1) — dos variantes de la misma clase que cumplen llevan las dos su alcance: la de largo plazo es la más
    barata que aguanta, y sin medirlas no se sabe cuál es."""
    from test_obras_pf_guion import CON, PERFIL_ESCALERA, _actual_no_cumple, _calibrada_con_escenario, _obra_terna, _terna
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_alcance_clase_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(44))
    f = alims[0]
    _actual_no_cumple(monkeypatch)
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', _terna)
    variantes = [{'nombre': f'terna {i}', 'obras': [_obra_terna(f, [CON], (f'L{i}',))], 'costo_base': float(i),
                  'escalones': ['terna']} for i in (1, 2)]
    plan = _plan_obras(alims, variantes=variantes, sorteos=[], barras_cargas=[], parametros=PERFIL_ESCALERA,
                       alternativas=3, horizonte={'tasa': 0.03})
    informe, codigo = obras.evaluar(app, plan)
    assert codigo == 0, informe
    filas = [v for v in informe['variantes'] if v.get('maxima')]
    assert len(filas) == 2 and all(v.get('horizonte') for v in filas)
    assert all(v['horizonte'].get('probados') for v in filas)


def test_la_largo_plazo_queda_para_el_pide_partiendo_de_la_de_corto_plazo():
    """098:RF-37 — en el estudio no se plantea la obra de los años futuros; :func:`largo_plazo` queda para la ruta del
    PIDE: «2×300 kvar» contiene a «1×300 kvar» y la definitiva parte de la de corto plazo."""
    from convertersmartgrid import escalera_optima as eo

    b1 = {'clase': 'condensador', 'barra': 'B4', 'q_kvar': 300.0}
    b2 = {**b1, 'q_kvar': 600.0}
    s1 = {'clase': 'seccion', 'tipo': {'nombre': 'AA24003D'}, 'tramos': ['T1']}
    s2 = {**s1, 'tramos': ['T1', 'T2']}
    assert eo.contiene({'obras': [b2, s2]}, {'obras': [b1]}) and not eo.contiene({'obras': [b1]}, {'obras': [b2]})
    corto = _fila_eo('1×300 kvar', ('bancos',), 100.0, {'definitiva': True, 'aguanta_anios': 4, 'probados': [4]}, [b1])
    otra = _fila_eo('2×300 kvar + sección', ('bancos', 'seccion'), 900.0, {'definitiva': True, 'aguanta_anios': 4},
                    [b2, s2])
    d = eo.elegir([corto, otra], eo.parametros(_perfil_eo()))
    assert d['elegida'] == corto['nombre'] and 'largo_plazo' not in d
    assert all(a['plazo'] in ('corto plazo', None) for a in d['alternativas'])
    assert eo.largo_plazo([corto, otra], corto)['misma'], 'la ruta del PIDE la sigue teniendo'


@pytest.mark.parametrize('valor', [0, -1, 'x'])
def test_el_factor_de_la_terna_tiene_que_ser_positivo(valor):
    """098:RF-35 — un factor de 0 o negativo dejaba la terna gratis: se rechaza con el nombre del dato."""
    from convertersmartgrid import escalera_optima as eo

    with pytest.raises(eo.EscaleraError, match='factor_terna_sin_capex'):
        eo.parametros(_perfil_eo(factor_terna_sin_capex=valor))


def test_la_obra_retirada_deshace_lo_que_abrio_y_el_ajuste_del_flujo(tmp_path, monkeypatch):
    """098:RF-36, 098:RF-34 — la obra aplicada abre un tramo y activa el ajuste de tomas de «Con proyecto»; al retirarla,
    su variación se borra y el tramo y el flujo vuelven a como estaban, con lo que guardó la web de la obra aplicada."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario, _obra_terna, _terna
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_retirar_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(36))
    f = alims[0]
    app.atributos_en_variacion = app.servicio_en_escenario = True   # la obra graba en su variación

    def abre_y_regula(ctx):
        _terna(ctx)
        obras.abrir(ctx, 'ElmLne', ctx.objeto('ElmLne', f'{f}_L2'))
        obras._activar_en_el_flujo(ctx, 'iopt_at', 'las tomas')
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', abre_y_regula)
    app.ldf.iopt_at = 0
    plan = _plan_obras(alims, obras=[_obra_terna(f, [CON])], aperturas_fichero=str(tmp_path / 'aperturas.json'))
    informe, codigo = obras.aplicar(app, plan)
    assert codigo == 0, informe
    (fila,) = informe['obras']
    _caso(app, CON).Activate()
    assert int(app.ldf.iopt_at) == 1 and fila['valores'][0]['atributo'] == 'iopt_at'
    registro = obras.leer_aperturas(tmp_path / 'aperturas.json')
    # La obra aplicada sale del registro (081:RF-81); queda el ajuste del flujo de antes de ella (098:RF-34).
    assert [(e['accion'], e['atributo'], e['valor']) for e in registro] == [('original', 'iopt_at', 0)]
    operacion = {k: fila[k] for k in ('abiertos', 'valores') if fila.get(k)} | {'variacion': fila['variacion']}
    informe, codigo = obras.retirar_obras(app, {**plan, 'feeders': [f], 'operacion_de_obras': [operacion],
                                               'variaciones': [fila['variacion']]})
    assert codigo == 0, informe
    assert informe['retiradas'] == [fila['variacion']] and informe['operacion_restituida'] == [fila['variacion']]
    _caso(app, CON).Activate()
    assert int(app.ldf.iopt_at) == 0
    tramo = obras._con_nombre(app, 'ElmLne', f'{f}_L2')[0]
    assert int(getattr(tramo, 'outserv', 0) or 0) == 0


def test_el_ajuste_del_flujo_va_al_caso_de_la_obra_y_deja_fijas_las_otras_tomas(tmp_path):
    """098:RF-34 — la obra se construye con activo el primero de sus casos («Sin proyecto»): el ajuste de tomas se
    activa en el flujo de cada caso de la obra, no en el activo; midiendo, los transformadores con toma automática
    quedan fijos; todo anotado en disco y, al restituir, como estaba, con el caso por su nombre completo; si el caso ya
    no está, se dice."""
    from test_obras_pf_guion import _calibrada_con_escenario

    obras = cargar_herramienta('obras_pf.py', 'obras_flujo_098', tools_en_path=True)

    app, _alims = _calibrada_con_escenario(random.Random(37))
    casos = obras.casos_del_proyecto(app, None)
    ldf_con = casos['con'].CreateObject('ComLdf', 'Flujo de «Con proyecto»')
    ldf_con.iopt_at = 0
    app.ldf.iopt_at = 0
    trafo = app.GetCalcRelevantObjects('*.ElmTr2')[0]
    trafo.ntrcn = 1
    casos['sin'].Activate()
    plan = {'project': 'P', 'aperturas_fichero': str(tmp_path / 'aperturas.json'), 'evaluando': True}
    fila = {'variacion': 'Obra_regulador_F1', 'avisos': []}
    ctx = obras.Contexto(app, app.proyecto, None, fila, None, None, plan=plan)
    ctx.casos = {'con': casos['con']}
    obras._activar_en_el_flujo(ctx, 'iopt_at', 'las tomas')
    assert int(ldf_con.iopt_at) == 1 and int(app.ldf.iopt_at) == 0, 'el de «Con proyecto», no el del caso activo'
    assert int(trafo.ntrcn) == 0 and any('toma fija' in a for a in fila['avisos'])
    registro = obras.leer_aperturas(tmp_path / 'aperturas.json')
    assert {(e['clase'], e['atributo'], e['valor'], e['accion']) for e in registro} == {
        ('ComLdf', 'iopt_at', 0, 'valor'), ('ElmTr2', 'ntrcn', 1, 'valor')}
    assert next(e for e in registro if e['clase'] == 'ComLdf')['caso_ruta'] == casos['con'].GetFullName()
    avisos = obras.restituir_el_flujo(app, casos, [fila], plan)
    assert avisos == [] and int(ldf_con.iopt_at) == 0 and int(trafo.ntrcn) == 1
    assert obras.leer_aperturas(tmp_path / 'aperturas.json') == []
    assert app.GetActiveStudyCase() is casos['sin'], 'vuelve al caso que estaba activo'
    # Sin el caso donde se cambió, no se toca otro: se dice.
    fila2 = {'valores': [{'clase': 'ComLdf', 'caso': 'Otro caso', 'caso_ruta': 'X', 'atributo': 'iopt_at', 'valor': 0}]}
    assert any('No está el caso «Otro caso»' in a for a in obras.restituir_el_flujo(app, casos, [fila2]))
    # Aplicada (sin evaluar), las otras tomas no se tocan: se dicen.
    ldf_con.iopt_at = 0
    fila3 = {'variacion': 'Obra_regulador_F1', 'avisos': []}
    ctx3 = obras.Contexto(app, app.proyecto, None, fila3, None, None, plan={**plan, 'evaluando': False})
    ctx3.casos = {'con': casos['con']}
    obras._activar_en_el_flujo(ctx3, 'iopt_at', 'las tomas')
    assert int(trafo.ntrcn) == 1 and any('también regulan' in a for a in fila3['avisos'])


def test_si_la_evaluacion_se_corta_al_crear_la_obra_se_restituye_lo_anotado(tmp_path, monkeypatch):
    """098:RF-34, 081:RF-81 — ``aplicar`` falla a mitad (tras abrir y activar el flujo): ``con_variante`` lo deshace
    igual, con lo anotado en disco, antes de que el error suba."""
    from test_obras_pf_guion import CON, PERFIL_ESCALERA, _actual_no_cumple, _calibrada_con_escenario, _obra_terna, _terna
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_corte_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(38))
    f = alims[0]
    _actual_no_cumple(monkeypatch)

    def abre_y_regula(ctx):
        _terna(ctx)
        obras.abrir(ctx, 'ElmLne', ctx.objeto('ElmLne', f'{f}_L2'))
        obras._activar_en_el_flujo(ctx, 'iopt_at', 'las tomas')
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', abre_y_regula)
    app.ldf.iopt_at = 0
    real = obras.aplicar

    def aplicar_que_se_corta(app_, plan_, **k):
        if plan_.get('evaluando'):
            real(app_, plan_, **k)
            raise RuntimeError('la orden se cortó')
        return real(app_, plan_, **k)
    monkeypatch.setattr(obras, 'aplicar', aplicar_que_se_corta)
    plan = _plan_obras(alims, variantes=[{'nombre': 'terna', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0}],
                       sorteos=[], barras_cargas=[], parametros=PERFIL_ESCALERA,
                       aperturas_fichero=str(tmp_path / 'aperturas.json'))
    with pytest.raises(RuntimeError, match='se cortó'):
        obras.evaluar(app, plan)
    _caso(app, CON).Activate()
    assert int(app.ldf.iopt_at) == 0
    assert int(getattr(obras._con_nombre(app, 'ElmLne', f'{f}_L2')[0], 'outserv', 0) or 0) == 0
    assert obras.leer_aperturas(tmp_path / 'aperturas.json') == []


def test_las_ya_medidas_no_se_miden_pero_cuentan_para_parar(monkeypatch):
    """098:RF-32 (H4) — la web pasa la lista entera y las ya medidas: el guion no las crea de nuevo, pero la primera
    que ya cumplía cuenta para parar (073:RF-18); sin esto se medía la siguiente."""
    from test_obras_pf_guion import CON, PERFIL_ESCALERA, _actual_no_cumple, _calibrada_con_escenario, _obra_terna, _terna
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_ya_medidas_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(39))
    f = alims[0]
    _actual_no_cumple(monkeypatch)
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', _terna)
    creadas = []
    real = obras.aplicar
    monkeypatch.setattr(obras, 'aplicar', lambda app_, plan_, **k: (creadas.append(len(plan_.get('obras') or [])),
                                                                    real(app_, plan_, **k))[1])
    ya = {'nombre': 'a', 'maxima': True, 'fraccion': 1.0, 'motivos': [], 'u_cargas': {'X': 0.96}, 'error': None,
          'perdidas_kw': 1.0}
    plan = _plan_obras(alims, variantes=[{'nombre': 'a', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0},
                                         {'nombre': 'b', 'obras': [_obra_terna(f, [CON], ('L2',))], 'costo_base': 2.0}],
                       sorteos=[], barras_cargas=[], parametros=PERFIL_ESCALERA, basta_una=True, ya_medidas=[ya])
    informe, codigo = obras.evaluar(app, plan)
    assert codigo == 0, informe
    assert informe['basta_una'] == 'a' and creadas == []
    assert [v['nombre'] for v in informe['variantes']] == ['a'] and informe['variantes'][0]['reutilizada']


def test_la_escalera_de_la_web_reutiliza_sin_abrir_digsilent_y_pasa_la_lista_entera(tmp_path, monkeypatch):
    """098:RF-32 (H4, H6) — de punta a punta en ``obras_escalera`` con la misma huella: la segunda vez, sabido todo, no
    se llama al guion de evaluar y las variantes salen en el orden del plan; con una sin saber, el guion recibe la
    lista entera y las ya medidas."""
    from test_casos_por_anio import ANIO, _escalera_falsa

    def evaluar(nombre):
        cumple = nombre.startswith('sección')
        return {'nombre': nombre, 'maxima': cumple, 'fraccion': 1.0 if cumple else None, 'perdidas_kw': 10.0,
                'motivos': [] if cumple else ['no converge'], 'u_cargas': {'F1_B4': 0.96 if cumple else 0.93}}

    services, ws, ctx, planes, _aplicadas, _apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'bancos': 9000, 'nueva_terna': 40000, 'cambio_seccion': 30000})
    falso = services._guion_pf

    def con_huella(ws_, ctx_, script, plan, *, nombre, args=(), **k):
        rc, inf, rep = falso(ws_, ctx_, script, plan, nombre=nombre, args=args, **k)
        return rc, ({**inf, 'huella_red': 'h1'} if '--escalera-datos' in args else inf), rep
    monkeypatch.setattr(services, '_guion_pf', con_huella)
    memo: dict = {}
    r1 = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=False, memo=memo)
    evaluaciones = [p for a, p in planes if '--evaluar' in a]
    assert len(evaluaciones) == 1 and 'ya_medidas' not in evaluaciones[0]
    r2 = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=False, memo=memo)
    assert len([p for a, p in planes if '--evaluar' in a]) == 1, 'todo sabido: DIgSILENT no se abre'
    assert [t['nombre'] for t in r2['alimentadores'][0]['tabla']] == [t['nombre'] for t in r1['alimentadores'][0]['tabla']]
    assert r2['alimentadores'][0]['elegida'] == r1['alimentadores'][0]['elegida']
    guardadas = memo['medidas_por_variante']
    guardadas.pop(next(iter(guardadas)))
    services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO, aplicar=False, memo=memo)
    ultima = [p for a, p in planes if '--evaluar' in a][-1]
    assert len(ultima['variantes']) == len(evaluaciones[0]['variantes'])
    assert len(ultima['ya_medidas']) == len(evaluaciones[0]['variantes']) - 1


def test_las_obras_de_varios_caminos_no_comparten_tramo_y_el_comun_lleva_el_mayor():
    """098:RF-31, 042:RF-30 — en las de varios caminos, cada tramo va en una sola obra (ni sección y terna a la vez) y el
    tramo común lleva la mayor capacidad de los caminos que pasan por él."""
    from convertersmartgrid import escalera_optima as eo

    comun = [{'nombre': f'T{i}', 'largo_m': 1000.0, 'corriente_a': 80.0, 'inom_a': 110.0} for i in range(3)]
    cola = comun + [{'nombre': f'C{i}', 'largo_m': 1500.0, 'corriente_a': 40.0, 'inom_a': 110.0} for i in range(3)]
    rama = comun + [{'nombre': f'R{i}', 'largo_m': 1200.0, 'corriente_a': 50.0, 'inom_a': 110.0} for i in range(2)]
    cargas = [{'barra': 'COLA', 'existe': True, 'camino': cola}, {'barra': 'RAMA', 'existe': True, 'camino': rama}]
    tipos = [_tipo_eo('AA05003D', 50), _tipo_eo('AA12003D', 120), _tipo_eo('AA24003D', 240)]
    vs, _av = eo.variantes('X', 10.0, comun, cargas, tipos, eo.parametros(_perfil_eo()), banco_kvar=300.0)
    juntas = [v for v in vs if v.caminos]
    assert juntas
    for v in juntas:
        de_linea = [o for o in v.obras if o['clase'] in ('seccion', 'terna')]
        tramos = [t for o in de_linea for t in (o.get('tramos') or [])]
        assert len(tramos) == len(set(tramos)), f'{v.nombre}: un tramo en dos obras'
    # Terna en un camino y sección en el otro: el común va con la sección (240 mm², 528 A > 2 × 110 A de la terna).
    mixtas = [v for v in juntas if {o['clase'] for o in v.obras} == {'seccion', 'terna'} and 'bancos' not in v.escalones]
    assert mixtas
    for v in mixtas:
        sec = {t for o in v.obras if o['clase'] == 'seccion' for t in o['tramos']}
        assert {'T0', 'T1', 'T2'} <= sec


def test_la_terna_de_dos_ramas_separadas_se_construye_en_sus_tramos(monkeypatch):
    """098:RF-31 (P5) — una terna de una obra de varios caminos lleva tramos que no son contiguos: el constructor real
    suma el circuito en cada uno y no toca el de en medio."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario, _obra_terna
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_terna_ramas_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(40))
    f = alims[0]
    app.atributos_en_variacion = app.servicio_en_escenario = True   # la obra graba en su variación
    plan = _plan_obras(alims, obras=[_obra_terna(f, [CON], ('L1', 'L3'))])
    informe, codigo = obras.aplicar(app, plan)
    assert codigo == 0, informe
    (fila,) = informe['obras']
    assert not fila.get('error'), fila
    _caso(app, CON).Activate()
    n = {t: int(getattr(obras._con_nombre(app, 'ElmLne', f'{f}_{t}')[0], 'nlnum', 1) or 1) for t in ('L1', 'L2', 'L3')}
    assert n == {'L1': 2, 'L2': 1, 'L3': 2}


# =========================================================================== 098:RF-36, cuarta revisión (T14)
def _linea_de(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == nombre)


def test_tras_comprobar_la_nueva_solo_se_va_hacia_delante(tmp_path):
    """098:RF-36 (C) — una pila vieja de dos variaciones y un ``Delete`` que falla en la segunda: la nueva se queda, la
    primera se borra, la segunda queda desactivada y se dice; nunca se deshace la nueva."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario, _obra_terna
    from test_obras_pf_guion import _plan as _plan_obras

    obras = cargar_herramienta('obras_pf.py', 'obras_hacia_delante_098', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(61))
    app.atributos_en_variacion = app.servicio_en_escenario = True
    f = alims[0]
    plan = _plan_obras(alims, obras=[_obra_terna(f, [CON]), _obra_terna(f, [CON], ('L3',))],
                       aperturas_fichero=str(tmp_path / 'aperturas.json'))
    viejas = [o['variacion'] for o in obras.aplicar(app, plan)[0]['obras']]
    assert len(viejas) == 2 and all(viejas)
    segunda = next(v for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1) if v.loc_name == viejas[1])

    def falla(*_a):
        raise RuntimeError('DIgSILENT no deja borrarla')
    object.__setattr__(segunda, 'Delete', falla)
    informe, codigo = obras.sustituir(app, {**plan, 'obras': [_obra_terna(f, [CON], ('L2',))],
                                            'sustituir': {'variaciones': viejas, 'operacion': [], 'alimentador': f}})
    assert codigo == 2 and informe['sustitucion']['hecha']
    assert informe['sustitucion']['retiradas'] == [viejas[0]] and informe['sustitucion']['sin_borrar'] == [viejas[1]]
    (nueva,) = informe['sustitucion']['nuevas']
    assert _activa(app, nueva) and not _existe(app, viejas[0]) and _existe(app, viejas[1]) and not _activa(app, viejas[1])


def test_la_operacion_de_la_vieja_se_deshace_y_se_guarda_en_el_escenario(tmp_path):
    """098:RF-36 (D) — la vieja abrió un tramo: al sustituirla, el tramo vuelve a servicio y el escenario de «Con
    proyecto» se guarda con ello."""
    from test_obras_pf_guion import CON, _obra_terna

    obras = cargar_herramienta('obras_pf.py', 'obras_operacion_vieja_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 62)
    _caso(app, CON).Activate()
    tramo = _linea_de(app, f'{f}_L3')
    tramo.outserv = 1                                                   # lo que abrió la vieja
    escenario = app.GetActiveScenario()
    antes = escenario.guardados
    operacion = [{'variacion': vieja, 'abiertos': [['ElmLne', f'{f}_L3', CON]]}]
    informe, _codigo = obras.sustituir(app, {**plan, 'obras': [_obra_terna(f, [CON], ('L2',))],
                                             'sustituir': {'variaciones': [vieja], 'operacion': operacion,
                                                           'alimentador': f}})
    assert informe['sustitucion']['hecha']
    _caso(app, CON).Activate()
    assert int(tramo.outserv) == 0 and escenario.guardados > antes


def test_si_la_orden_se_corta_dentro_de_aplicar_lo_que_abrio_la_nueva_vuelve(tmp_path, monkeypatch):
    """098:RF-36 (D, E) — la nueva abre un tramo y la orden se corta: se borra solo lo que la nueva creó (por su nombre,
    anotado al crearse; una «Obra_» del operador creada entre medias se queda) y el tramo vuelve a servicio."""
    from test_obras_pf_guion import CON, _obra_terna, _terna

    obras = cargar_herramienta('obras_pf.py', 'obras_corte_aplicar_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 63)

    def abre_y_se_corta(ctx):
        _terna(ctx)
        fake_pf.variacion_del_operador(app, f'Obra_manual_{f}', [])         # el operador, entre medias
        obras.abrir(ctx, 'ElmLne', ctx.objeto('ElmLne', f'{f}_L3'))
        raise KeyboardInterrupt('cancelada')
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', abre_y_se_corta)
    with pytest.raises(KeyboardInterrupt):
        obras.sustituir(app, {**plan, 'obras': [_obra_terna(f, [CON], ('L2',))],
                              'sustituir': {'variaciones': [vieja], 'operacion': [], 'alimentador': f}})
    _caso(app, CON).Activate()
    assert int(_linea_de(app, f'{f}_L3').outserv) == 0
    assert _activa(app, vieja) and _existe(app, f'Obra_manual_{f}')
    assert not [n for n in (v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1))
                if n.startswith('Obra_terna_') and n != vieja]


def test_la_sustitucion_muerta_en_nueva_creada_deshace_su_operacion(tmp_path):
    """098:RF-36 (D) — muerta tras crear la nueva, con su operación en el diario: la orden siguiente la deshace (el tramo
    que abrió vuelve), borra lo creado y devuelve la vieja."""
    from test_obras_pf_guion import CON, _obra_terna

    obras = cargar_herramienta('obras_pf.py', 'obras_muerta_creada_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 64)
    casos = obras.casos_del_proyecto(app, None)
    _caso(app, CON).Activate()
    next(v for v in app.GetActiveNetworkVariations() if v.loc_name == vieja).Deactivate()
    nueva = obras.aplicar(app, {**plan, 'obras': [_obra_terna(f, [CON], ('L2',))]})[0]['obras'][0]['variacion']
    _caso(app, CON).Activate()
    _linea_de(app, f'{f}_L3').outserv = 1
    obras._diario(plan, {'accion': 'sustitucion', 'id': 'x2', 'proyecto': 'P', 'caso': CON, 'paso': 'nueva_creada',
                         'viejas': [vieja], 'operacion': [], 'apartadas': [vieja], 'creadas': [nueva], 'feeders': [f],
                         'operacion_nueva': [{'variacion': nueva, 'abiertos': [['ElmLne', f'{f}_L3', CON]]}]})
    obras.restituir_pendientes(app, plan, casos, {'avisos': []})
    _caso(app, CON).Activate()
    assert int(_linea_de(app, f'{f}_L3').outserv) == 0 and _activa(app, vieja) and not _existe(app, nueva)


def test_solo_se_borran_variaciones_de_obra_de_la_orden(tmp_path):
    """098:RF-36 (E) — lo creado y lo viejo se borran solo si son ``Obra_*`` de los alimentadores de la orden."""
    from test_obras_pf_guion import CON

    obras = cargar_herramienta('obras_pf.py', 'obras_guarda_borrar_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 65)
    casos = obras.casos_del_proyecto(app, None)
    _caso(app, CON).Activate()
    for nombre in ('Carga_Q_F1_1', 'Obra_terna_F2'):
        fake_pf.variacion_del_operador(app, nombre, [])
    assert obras._borrar_creadas(app, casos, ['Carga_Q_F1_1', 'Obra_terna_F2'], [f]) == []
    assert obras._borrar_variaciones(app, casos, ['Carga_Q_F1_1', 'Obra_terna_F2'], [f]) == ([], [])
    assert _existe(app, 'Carga_Q_F1_1') and _existe(app, 'Obra_terna_F2')


def test_el_ajuste_de_tomas_de_una_obra_antigua_y_al_rehacer(tmp_path):
    """098:RF-34 (F) — una obra de antes de guardar el valor original lo devuelve con el suyo (con la guarda de los
    reguladores); al rehacer la operación de la vieja, el valor original se guarda otra vez."""
    from test_obras_pf_guion import CON, _calibrada_con_escenario

    obras = cargar_herramienta('obras_pf.py', 'obras_iopt_antiguo_098', tools_en_path=True)
    app, _alims = _calibrada_con_escenario(random.Random(66))
    casos = obras.casos_del_proyecto(app, None)
    _caso(app, CON).Activate()
    plan = {'project': 'P', 'aperturas_fichero': str(tmp_path / 'aperturas.json')}
    app.ldf.iopt_at = 1
    fila = {'variacion': 'Obra_regulador_F1', 'valores': [{'clase': 'ComLdf', 'caso': CON, 'atributo': 'iopt_at',
                                                           'valor': 0, 'nuevo': 1}]}
    obras.deshacer_operacion(app, plan, casos, [fila], [])
    assert int(app.ldf.iopt_at) == 0
    obras.rehacer_operacion(app, plan, casos, [fila])
    assert int(app.ldf.iopt_at) == 1
    (original,) = [e for e in obras.leer_aperturas(tmp_path / 'aperturas.json') if e.get('accion') == 'original']
    assert original['valor'] == 0
    obras.deshacer_operacion(app, plan, casos, [fila], [])
    assert int(app.ldf.iopt_at) == 0


def test_lo_especial_de_la_corrida_no_es_un_resto(tmp_path):
    """098:RF-36 (G) — el ``restituir_pendientes`` de la variante cortada no devuelve la obra apartada de la medida en
    curso; el de la orden siguiente, sí."""
    from test_obras_pf_guion import CON

    obras = cargar_herramienta('obras_pf.py', 'obras_solo_aperturas_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 67)
    casos = obras.casos_del_proyecto(app, None)
    obras.anotar_apartadas(plan, casos['con'], [vieja])
    _caso(app, CON).Activate()
    next(v for v in app.GetActiveNetworkVariations() if v.loc_name == vieja).Deactivate()
    obras.restituir_pendientes(app, {**plan, 'solo_aperturas': True}, casos, {'avisos': []})
    assert not _activa(app, vieja)
    obras.restituir_pendientes(app, plan, casos, {'avisos': []})
    assert _activa(app, vieja)
    fuente = __import__('inspect').getsource(obras.evaluar)
    assert "restituir_pendientes(app, {**plan, 'solo_aperturas': True}, casos, {})" in fuente


def test_la_vieja_con_operacion_se_mide_sin_su_operacion(tmp_path, monkeypatch):
    """098:RF-36 (H) — la vieja abrió un tramo: medida «sin ella», el tramo está en servicio; al terminar, la vieja vuelve
    activa y el tramo, abierto como lo dejó."""
    from test_obras_pf_guion import CON, PERFIL_ESCALERA, _actual_no_cumple, _obra_terna, _terna

    obras = cargar_herramienta('obras_pf.py', 'obras_vieja_con_operacion_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 68)
    _actual_no_cumple(monkeypatch)
    monkeypatch.setitem(obras.CONSTRUCTORES, 'terna', _terna)
    _caso(app, CON).Activate()
    tramo = _linea_de(app, f'{f}_L3')
    tramo.outserv = 1
    vistos = []
    medir = obras.medida_para_criterio

    def registrar(app_, alims_, feeders, **k):
        if app_.GetActiveStudyCase().loc_name == CON:
            vistos.append((int(tramo.outserv), _activa(app_, vieja)))
            _caso(app_, CON).Activate()
        return medir(app_, alims_, feeders, **k)
    monkeypatch.setattr(obras, 'medida_para_criterio', registrar)
    plan_e = {**plan, 'variantes': [{'nombre': 'otra', 'obras': [_obra_terna(f, [CON], ('L2',))], 'costo_base': 1.0}],
              'sorteos': [], 'barras_cargas': [], 'parametros': PERFIL_ESCALERA, 'apartar_obras': [vieja],
              'operacion_apartadas': [{'variacion': vieja, 'abiertos': [['ElmLne', f'{f}_L3', CON]]}]}
    informe, codigo = obras.evaluar(app, plan_e)
    assert codigo == 0, informe
    assert vistos and all(v == (0, False) for v in vistos), vistos
    assert _activa(app, vieja) and int(tramo.outserv) == 1
    assert not [e for e in obras.leer_aperturas(tmp_path / 'aperturas.json') if e.get('accion') == 'apartada']


def test_si_no_se_puede_quitar_lo_nuevo_la_vieja_no_se_reactiva(tmp_path):
    """098:RF-36 (I) — si lo creado de la nueva no se deja desactivar, la vieja no se reactiva encima; se dice."""
    from test_obras_pf_guion import CON

    obras = cargar_herramienta('obras_pf.py', 'obras_no_se_quita_098', tools_en_path=True)
    app, alims, f, vieja, plan = _con_obra_vieja(obras, tmp_path, 69)
    casos = obras.casos_del_proyecto(app, None)
    _caso(app, CON).Activate()
    next(v for v in app.GetActiveNetworkVariations() if v.loc_name == vieja).Deactivate()
    nueva = fake_pf.variacion_del_operador(app, f'Obra_terna_{f}_9', [])

    def falla(*_a):
        raise RuntimeError('no se deja')
    object.__setattr__(nueva, 'Deactivate', falla)
    avisos: list[str] = []
    obras.deshacer_sustitucion(app, plan, casos, [nueva.loc_name], [vieja], [], [], True, avisos, [f])
    assert not _activa(app, vieja) and any('no se reactiva encima' in a for a in avisos)


def test_la_sustitucion_fallida_no_deja_obras_pendientes_y_el_diario_recompone(tmp_path, monkeypatch):
    """098:RF-36 (I) — si la nueva se deshace, sus obras no quedan en el espacio como del operador; si una sustitución se
    completó en la orden siguiente, lo aplicado del espacio se pone al día con su diario."""
    from convertersmartgrid.web import services

    ws = _ws_con_obras(tmp_path, [{'project': 'P', 'variacion': 'Obra_tension_F1', 'obra': {'alimentador': 'F1'},
                                   'origen': 'escalera'}])
    ws.plans_dir = tmp_path / 'planes'
    obra = {'clase': 'condensador', 'alimentador': 'F1', 'casos': ['Con proyecto'], 'barra': 'F1_B1', 'q_kvar': 300.0,
            'escalones': 1}
    ws.obras = [{**obra, 'id': 'o1'}]
    monkeypatch.setattr(services, 'carpeta_de', lambda *_a: '')
    monkeypatch.setattr(services, 'native_action_context', lambda ws_, p, feeders, a: {'feeders': list(feeders)})
    monkeypatch.setattr(services, '_gemelo', lambda *a, **k: None)
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (2, {'obras': [{'obra': 1, 'variacion': 'Obra_x_F1',
                                                                               'error': 'deshecha: no converge'}],
                                                                    'sustitucion': {'hecha': False}}, tmp_path / 'r.json'))
    services.obras_ejecutar(ws, _Registro(), 'P', ['F1'], ['o1'], '', simular=False, origen='escalera',
                            sustituir={'variaciones': ['Obra_tension_F1'], 'operacion': [], 'alimentador': 'F1'})
    assert ws.obras == [] and [a['variacion'] for a in ws.obras_aplicadas] == ['Obra_tension_F1']
    hechas = services._recomponer_por_diario(ws, 'P', {'especiales_recuperadas': [
        {'accion': 'sustitucion', 'paso': 'nueva_verificada', 'viejas': ['Obra_tension_F1'], 'proyecto': 'P',
         'nuevas': [{'variacion': 'Obra_condensador_F1', 'obra': obra}], 'eleccion': {'nombre': 'bancos'}}]})
    assert hechas == ['Obra_condensador_F1']
    (a,) = ws.obras_aplicadas
    assert a['variacion'] == 'Obra_condensador_F1' and a['origen'] == 'escalera' and a['eleccion'] == {'nombre': 'bancos'}


# =========================================================================== 098:RF-43 (otro corte de la transferencia)
def test_el_que_recibe_la_transferencia_prueba_otro_corte_de_la_misma():
    """098:RF-43 — CHN102 (2026-11-07) recibía la cola de CA101 y quedaba en 0,703 p.u.: su escalera empieza por mover el
    corte de la misma transferencia (devolver parte a CA101 por el punto que abrió el operador, abriendo otra maniobra
    de la zona), aunque CA101 no tenga margen ahora: se miden los dos (098:RF-25). Primero la que devuelve más."""
    from convertersmartgrid import obras_integrales as oi

    devolver = {**_enlace_x(), 'u_min': 0.90, 'devuelve_zona': True}
    vs, avisos = oi.variantes_por_enlace('X', [devolver], _p_098())
    assert vs and not avisos and all(v.nombre.startswith('otro corte de la transferencia') for v in vs)
    assert [v.obras[0]['maniobra'] for v in vs] == ['SW_LS1A1', 'SW_LA1A2', 'SW_LA2A3']
    otro, av = oi.variantes_por_enlace('X', [{**_enlace_x(), 'u_min': 0.90}], _p_098())
    assert not otro and av, 'un vecino cualquiera sin margen sigue sin recibir (087:RF-32)'


def test_la_lectura_marca_el_corte_del_operador_en_los_enlaces(monkeypatch):
    """098:RF-43 — el enlace abierto que devolvería la zona del operador a su alimentador se marca, con su potencia."""
    import sys
    import types

    from convertersmartgrid.transferencia_operador import CargaRed, Rama, Zona

    obras = cargar_herramienta('obras_pf.py', 'obras_corte_operador_098', tools_en_path=True)
    zona = Zona('CA101', 'CHN102', [CargaRed('k1', 'S1', 't1', 'CA101', 'CHN102', 900.0),
                                    CargaRed('k2', 'S2', 't2', 'CA101', 'CHN102', 830.0)],
                cerrar=[Rama('R\\ENL', 'ElmCoup', 'Breaker/Switch', ('a', 'b'), False)])
    falso = types.ModuleType('transferencia_operador_pf')
    falso.leer_transferencias = lambda app, alims, plan, interesan=None: ([zona], {}, {})
    monkeypatch.setitem(sys.modules, 'transferencia_operador_pf', falso)
    enlaces = {'CHN102': [{'enlace': 'Breaker/Switch', 'ruta': 'R\\ENL', 'vecino': 'CA101', 'cerrado': False},
                          {'enlace': 'OTRO', 'ruta': 'R\\OTRO', 'vecino': 'CA101', 'cerrado': False}]}
    obras.marcar_cortes_del_operador(None, None, {'dgs_fuente': ['x.dgs']}, enlaces, [])
    marcado, otro = enlaces['CHN102']
    assert marcado['devuelve_zona'] and marcado['zona_kw'] == 1730.0 and not otro.get('devuelve_zona')


# =========================================================================== 098:RF-44 (la transferencia, alternativa)
def test_en_con_proyecto_la_transferencia_se_deshace_para_medirla_como_alternativa(guion, tpf):
    """098:RF-44 — en «Con proyecto» lo que hizo el operador se deshace para que la escalera del que cede lo mida como
    una alternativa más; «Sin proyecto» no se toca; la zona dice su enlace y su corte."""
    import sys

    app, planes, nuevo = _caso_ca101(guion)
    con = _caso(app, 'Con proyecto')
    con.Activate()
    _obj(app, 'ElmLne', 'F1_L6').outserv = 1                      # el operador, también en «Con proyecto»
    nuevo.outserv = 0
    app.GetActiveScenario().Save()
    alims = sys.modules['cargas_pf'].Alimentadores(app, app.proyecto, ['F1', 'F2'])
    informe = tpf.deshacer_en_con_proyecto(app, alims, con, planes[0])
    (z,) = informe['zonas']
    assert (z['desde'], z['hacia']) == ('F1', 'F2') and z['enlace'] == [nuevo.loc_name] and z['corte'] == ['F1_L6']
    con.Activate()
    assert int(_obj(app, 'ElmLne', 'F1_L6').outserv) == 0 and int(nuevo.outserv) == 1
    _caso(app, 'Sin proyecto').Activate()
    assert int(_obj(app, 'ElmLne', 'F1_L6').outserv) == 1 and int(nuevo.outserv) == 0, '«Sin proyecto», como lo dejó'


def _zona_operador():
    return {'desde': 'CA101', 'hacia': 'CHN102', 'n_sed': 50, 'kw': 1730.0, 'enlace': ['Breaker/Switch(1)'],
            'corte': ['SW_LA2A3']}


def _tabla_con(transfer_cumple: bool, otro_corte_cumple: bool = False, bancos_cumplen: bool = False):
    """Las filas de la escalera de CA101: la del operador, otro corte y unos bancos más caros."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.web import services

    vs = services.marcar_la_del_operador(
        [eo.Variante(f'transferencia a CHN102 por Breaker/Switch(1) abriendo {m}', ('transferencia',),
                     [{'clase': 'maniobra', 'maniobra': m, 'alimentador': 'CA101'}], {}) for m in ('SW_LA2A3', 'SW_LA1A2')],
        _zona_operador())
    p = eo.parametros(_perfil_eo())
    filas = [_fila_eo(vs[0].nombre, ('transferencia',), 10.0, {'definitiva': True, 'aguanta_anios': 4}),
             _fila_eo(vs[1].nombre, ('transferencia',), 11.0, {'definitiva': True, 'aguanta_anios': 4}),
             _fila_eo('2×300 kvar', ('bancos',), 300.0, {'definitiva': True, 'aguanta_anios': 4}),
             _fila_eo('cambio a 22.9 kV', ('nivel',), 900.0, {'definitiva': True, 'aguanta_anios': 4})]
    filas[2].update(maxima=bancos_cumplen, motivos=[] if bancos_cumplen else ['CH_23 a 0.874 p.u.'])
    filas[0].update(maxima=transfer_cumple, u_cargas={'CH_23': 0.95 if transfer_cumple else 0.861},
                    motivos=[] if transfer_cumple else ['CHN102_X a 0.703 p.u.'])
    filas[1].update(maxima=otro_corte_cumple, motivos=[] if otro_corte_cumple else ['CH_23 a 0.93 p.u.'])
    return eo.elegir(filas, p), vs


def test_los_bancos_que_bastan_van_antes_que_la_transferencia_del_operador():
    """098:RF-45 — el escalón de los bancos va antes que el de la transferencia: si los bancos bastan, no se transfiere."""
    d, _vs = _tabla_con(True, bancos_cumplen=True)
    assert d['elegida'] == '2×300 kvar'


def test_la_transferencia_del_operador_que_resuelve_y_no_rompe_al_que_recibe_se_elige():
    """098:RF-44 — medida en los dos alimentadores (098:RF-25), cumple y es la más barata: se elige; su fila lo dice."""
    from convertersmartgrid.web import services

    d, vs = _tabla_con(True)
    assert d['elegida'] == vs[0].nombre and vs[0].nombre.startswith('la transferencia del operador')
    fila = services.fila_de_la_transferencia_del_operador(d['tabla'], _zona_operador())
    assert 'se elige' in fila['texto'] and 'CH_23 0.950' in fila['texto'] and '1,730 kW' in fila['texto']


def test_la_que_no_resuelve_se_mide_se_informa_y_se_trabaja_sin_ella():
    """098:RF-44 — no cumple (deja a CHN102 en 0,703 p.u.): se elige otra y la fila dice por qué, con las cifras."""
    from convertersmartgrid.web import services

    d, vs = _tabla_con(False)
    assert d['elegida'] == 'cambio a 22.9 kV'
    fila = services.fila_de_la_transferencia_del_operador(d['tabla'], _zona_operador())
    assert 'no se elige' in fila['texto'] and '0.703' in fila['texto'] and 'sin ella' in fila['texto']


def test_otro_punto_de_corte_que_resuelve_se_elige():
    """098:RF-44 — la del operador no resuelve y otro corte de la misma, sí: se elige ese."""
    d, vs = _tabla_con(False, otro_corte_cumple=True)
    assert d['elegida'] == vs[1].nombre and not vs[1].nombre.startswith('la transferencia del operador')


# =========================================================================== 098:RF-45 (orden fijo de los escalones)
def test_el_orden_fijo_de_los_escalones():
    """098:RF-45 — bancos, sección, terna, transferencia, nivel, regulador; una combinación, en el de su obra mayor."""
    from convertersmartgrid import escalera_optima as eo

    orden = [('bancos',), ('seccion', 'bancos'), ('terna', 'bancos'), ('transferencia', 'bancos'), ('nivel',),
             ('regulador',)]
    assert [eo.escalon(e) for e in orden] == [0, 1, 2, 3, 4, 5]
    assert eo.escalon(('terna', 'seccion')) == 2 and eo.escalon(('traslado',)) == 3 and eo.escalon(()) == -1
    vs = [{'nombre': n, 'escalones': e, 'costo_base': c} for n, e, c in
          (('nivel', ('nivel',), 10.0), ('terna', ('terna',), 50.0), ('banco', ('bancos',), 900.0),
           ('seccion', ('seccion',), 20.0), ('transferencia', ('transferencia',), 1.0))]
    assert [v['nombre'] for v in eo.por_costo(vs)] == ['banco', 'seccion', 'terna', 'transferencia', 'nivel']


def _escalera_por_escalones(monkeypatch, tmp_path, cumple_en):
    """La escalera de F1 con el oráculo y DIgSILENT sustituidos: cumple solo en el escalón ``cumple_en`` (o ninguno)."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.web import services

    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas',
                        lambda ws, project: [{'sed': 'A', 'alimentador': 'F1', 'kw': 100.0, 'variacion': 'Carga_A'}])
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    orden = [eo.Variante(n, e, [{'clase': 'x'}], {}) for n, e in
             (('bancos', ('bancos',)), ('sección', ('seccion',)), ('terna', ('terna',)), ('regulador', ('regulador',)))]
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {
        'alimentadores': {'F1': {'orden': orden, 'tabla': [{'nombre': v.nombre, 'cumple': False} for v in orden],
                                 'ya_cumple': False}}, 'tanda': 3})
    llamadas = []

    def escalera(ws, ctx, project, feeders, *, aplicar=False, traspaso=False, sin_oraculo=False, escalones=None,
                 variantes_de=None, **k):
        llamadas.append(('aplica' if aplicar else 'mide', escalones, traspaso,
                         [v.nombre for v in (variantes_de or {}).get('F1') or []]))
        bien = not aplicar and escalones is not None and escalones[1] == cumple_en
        return {'alimentadores': [{'alimentador': 'F1', 'elegida': f'la del escalón {cumple_en}' if bien else None,
                                   'tabla': [{'nombre': 'x', 'factible': bien}], 'aplicada': ['Obra_x'] if aplicar else []}]}
    monkeypatch.setattr(services, 'obras_escalera', escalera)
    monkeypatch.setattr(services, 'confirmar_conjunto', lambda *a, **k: {'cumple': True})
    monkeypatch.setattr(services, '_anio_de_problemas', lambda *a, **k: {})
    ctx = _Registro()
    r = services.escalera_por_alimentador(object(), ctx, 'P', ['F1'])
    return llamadas, r, ctx


def test_se_para_en_el_primer_escalon_que_cumple(monkeypatch, tmp_path):
    """098:RF-45 — la sección cumple: se miden bancos y sección (cada uno con sus candidatas del oráculo) y se para; la
    terna, la transferencia y el nivel no se miden."""
    llamadas, r, ctx = _escalera_por_escalones(monkeypatch, tmp_path, 1)
    medidas = [x for x in llamadas if x[0] == 'mide']
    assert [x[1] for x in medidas] == [(-1, 0), (1, 1)]
    assert medidas[0][3] == ['bancos'] and medidas[1][3] == ['sección']
    assert [x[0] for x in llamadas].count('aplica') == 1
    reg = r['por_alimentador']['F1']['escalones']
    assert [(x['escalon'], x['resuelve']) for x in reg] == [('bancos', False), ('seccion', True)]
    assert any('escalón seccion' in t and 'se para aquí' in t for t in ctx.textos)


def test_no_se_llega_a_la_obra_integral_sin_los_cuatro_escalones(monkeypatch, tmp_path):
    """098:RF-45 — ninguno cumple: bancos, sección, terna y transferencia, después nivel y regulador, cada uno medido; el
    corte de 087:RF-40 ya no existe."""
    llamadas, r, ctx = _escalera_por_escalones(monkeypatch, tmp_path, None)
    medidas = [x for x in llamadas if x[0] == 'mide']
    assert [x[1] for x in medidas] == [(-1, 0), (1, 1), (2, 2), (3, 3), (4, 5)]
    assert medidas[3][2] is True, 'el escalón de la transferencia mide las de traspaso'
    assert medidas[4][3] == ['regulador'], 'el regulador, en su turno, con su candidata del oráculo'
    assert not any('087:RF-40' in t for t in ctx.textos)
    assert not r['por_alimentador']['F1']['cumple']
