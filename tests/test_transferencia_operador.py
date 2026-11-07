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
    assert e['elegida'] == f"{candidatas[0].nombre} + 2×450 kvar en A4"
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
    assert [x[:2] for x in llamadas[:3]] == [('mide', 'oraculo'), ('mide', 'traspaso'), ('mide', 'nivel')]
    assert llamadas[1][2] is False                       # el enlace existente ya lo juzgó el oráculo


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
    from test_obras_pf_guion import CON, PERFIL_ESCALERA, _actual_no_cumple, _calibrada_con_escenario, _obra_terna, _terna
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
