"""El oráculo calcula todo lo del modelo, y por fases (spec 082).

Medido contra DIgSILENT el 2026-11-03: el flujo equilibrado y sin bancos daba 0,802 p.u. en TI01 de
Electro Sur Este, donde DIgSILENT tiene 0,790, y 0,804 p.u. en C+æ02 de Luz del Sur, donde tiene 0,934,
y a C+æ02 le quitaba así el 57 % de su demanda sin motivo.
"""

from __future__ import annotations

import dataclasses
import random

import pytest

pytest.importorskip('pandapower')

from convertersmartgrid import oraculo  # noqa: E402
from convertersmartgrid.model import CapacitorBank, Coupler, DatosRegulador, SwitchingDevice, build_feeder_model  # noqa: E402
from synthetic_export import ExportSpec, load_export  # noqa: E402
from test_oraculo_unido import _red  # noqa: E402

LAYOUTS = ('reducido', 'completo')


def _modelo(tmp_path, layout='reducido', seed=7):
    spec = ExportSpec(feeders=2, sections_per_feeder=6, loads_per_feeder=4, layout=layout, seed=seed)
    ds = load_export(spec, tmp_path / f'{layout}_{seed}')
    return build_feeder_model(ds, ds.feeder_ids()[0], strict=True)


def _trifasico(modelo):
    # El export sintético sortea tramos de menos fases; estas pruebas parten de una red toda ABC.
    modelo.lines = [dataclasses.replace(ln, phase='ABC') for ln in modelo.lines]
    modelo.loads = [dataclasses.replace(c, phase='ABC') for c in modelo.loads]
    return modelo


def _escalar(modelo, f):
    modelo.loads = [dataclasses.replace(c, p_mw=c.p_mw * f, q_mvar=c.q_mvar * f) for c in modelo.loads]


def _en_fase(modelo, fase='A'):
    modelo.loads = [dataclasses.replace(c, phase=fase) for c in modelo.loads]


def _banco(modelo, kvar, *, en_servicio=True, fases='ABC'):
    return CapacitorBank('B1', modelo.loads[0].node_id, '', '', fases, kvar, 1, kvar,
                         float(modelo.nominal_kv), en_servicio)


def _cuadra(informe):
    return all(n['modelo'] == n['red'] for n in informe.recuento.values())


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('por_fases', (False, True))
def test_todas_las_clases_entran_en_la_red(tmp_path, layout, por_fases):
    """082:RF-3, 082:RF-12, 082:RF-13 — sea cual sea la red y su disposición, cada clase del modelo
    está en la red calculada; un elemento que falte no pasaría esta cuenta."""
    modelo = _modelo(tmp_path, layout, seed=random.randrange(10_000))
    modelo.capacitors = [_banco(modelo, 150.0)]
    _en_fase(modelo)
    _net, _barra, informe = oraculo.red_pandapower(modelo, por_fases=por_fases)
    assert set(informe.recuento) == {'tramos', 'sed', 'cargas', 'bancos', 'maniobras', 'acopladores'}
    assert _cuadra(informe), informe.recuento
    assert not [h for h in informe.errores if h.codigo == 'omitido_en_la_red']


@pytest.mark.parametrize('cambio', ('tipo_ausente', 'impedancia_nula', 'impedancia_negativa'))
def test_un_tramo_imposible_se_calcula_como_conexion_y_sigue_el_error(tmp_path, cambio):
    """082:RF-1 — antes un solo tramo así dejaba sin calcular el alimentador entero."""
    modelo = _modelo(tmp_path)
    clave = next(ln.type_key for ln in modelo.lines if ln.length_m > 0)
    if cambio == 'tipo_ausente':
        del modelo.line_types[clave]
    else:
        modelo.line_types[clave] = dataclasses.replace(
            modelo.line_types[clave], r1_ohm_km=0.0 if cambio == 'impedancia_nula' else -1.0,
            x1_ohm_km=0.0 if cambio == 'impedancia_nula' else 0.3)
    informe = oraculo.validar(modelo)
    assert informe.convergio and informe.v_min_pu is not None
    assert cambio in {h.codigo for h in informe.errores}
    assert informe.veredicto == 'errores'
    assert _cuadra(informe), informe.recuento


def test_un_nodo_sin_definir_entra_sin_alimentar_y_se_dice(tmp_path):
    """082:RF-2 — antes la carga se saltaba en silencio y su demanda desaparecía."""
    modelo = _modelo(tmp_path)
    modelo.loads.append(dataclasses.replace(modelo.loads[0], device_number='NUEVA', node_id='NO_EXISTE'))
    informe = oraculo.validar(modelo)
    assert {'nodo_sin_definir'} <= {h.codigo for h in informe.avisos}
    assert 'carga_sin_alimentar' in {h.codigo for h in informe.errores}
    assert _cuadra(informe), informe.recuento


def test_una_maniobra_fuera_de_su_tramo_sigue_cortandolo(tmp_path):
    """082:RF-2 — abierta, y apuntando a otro nodo, antes se ignoraba y el tramo seguía cerrado."""
    modelo = _modelo(tmp_path)
    tramo = next(ln for ln in modelo.lines if ln.length_m >= oraculo._LARGO_CONEXION_M)
    modelo.devices = [SwitchingDevice('SW', tramo.section_id, '', 0, 'OTRO_NODO', 'E', 'E1', 'ABC', 0, 0, 0)]
    net, _barra, informe = oraculo.red_pandapower(modelo)
    assert 'maniobra_fuera_de_extremo' in {h.codigo for h in informe.avisos}
    assert len(net.switch) >= 1 and not net.switch[net.switch.element.notna()].closed.all()
    assert informe.recuento['maniobras'] == {'modelo': 1, 'red': 1}


def test_una_maniobra_de_un_tramo_que_no_existe_se_anota(tmp_path):
    """082:RF-2 — no tiene dónde actuar: se dice, y no cuenta como una omisión callada."""
    modelo = _modelo(tmp_path)
    modelo.devices = [SwitchingDevice('SW', 'NO_EXISTE', '', 0, 'N', 'E', 'E1', 'ABC', 1, 0, 0)]
    _net, _barra, informe = oraculo.red_pandapower(modelo)
    assert 'maniobra_sin_tramo' in {h.codigo for h in informe.avisos}
    assert 'omitido_en_la_red' not in {h.codigo for h in informe.hallazgos}


def _q_de_la_fuente(modelo):
    import pandapower

    net, _barra, _informe = oraculo.red_pandapower(modelo)
    oraculo._ejecutar(pandapower, net)
    return float(net.res_ext_grid.q_mvar.sum())


def test_un_banco_entrega_su_potencia_y_fuera_de_servicio_no(tmp_path):
    """082:RF-4 — C+æ02 de Luz del Sur: sin sus 3 bancos el oráculo erraba 10 puntos."""
    modelo = _trifasico(_modelo(tmp_path))
    sin_banco = _q_de_la_fuente(modelo)
    modelo.capacitors = [_banco(modelo, 300.0, en_servicio=False)]
    assert _q_de_la_fuente(modelo) == pytest.approx(sin_banco)
    modelo.capacitors = [_banco(modelo, 300.0)]
    assert _q_de_la_fuente(modelo) == pytest.approx(sin_banco - 0.3, abs=0.03)
    assert oraculo.validar(modelo).recuento['bancos'] == {'modelo': 1, 'red': 1}


def test_un_banco_sin_potencia_se_anota(tmp_path):
    """082:RF-4 — el DGS tampoco lo escribe: se dice, sin inventar su potencia."""
    modelo = _modelo(tmp_path)
    modelo.capacitors = [dataclasses.replace(_banco(modelo, 1.0), kvar_per_step=None, total_kvar=None)]
    informe = oraculo.validar(modelo)
    assert 'banco_sin_potencia' in {h.codigo for h in informe.avisos}
    assert 'omitido_en_la_red' not in {h.codigo for h in informe.hallazgos}


@pytest.mark.parametrize('layout', LAYOUTS)
def test_con_monofasicos_el_veredicto_es_del_desequilibrado(tmp_path, layout):
    """082:RF-5, 082:RF-7, 082:RF-8 — toda la carga en una fase cae más que repartida entre tres, se
    mide solo en las fases que hay y queda lo que daría el equilibrado."""
    # Tramos largos: con la caída en el transformador, igual por fase, no se distinguirían.
    modelo = _trifasico(_modelo(tmp_path, layout))
    modelo.lines = [dataclasses.replace(ln, length_m=5000.0) for ln in modelo.lines]
    _escalar(modelo, 3.0)
    equilibrada = oraculo.validar(modelo)
    assert equilibrada.flujo == 'equilibrado' and not equilibrada.equilibrado
    assert not equilibrada.v_min_fase
    _en_fase(modelo)
    informe = oraculo.validar(modelo)
    assert informe.flujo == 'desequilibrado'
    assert informe.v_min_fase['A'] < equilibrada.v_min_pu
    assert informe.v_min_pu == min(informe.v_min_fase.values())
    assert informe.equilibrado['v_min_pu'] == pytest.approx(equilibrada.v_min_pu, abs=1e-4)


@pytest.mark.parametrize('fase', ('A', 'B', 'C', 'AB', 'BC', 'AC'))
def test_cada_sed_conserva_su_transformador_y_su_demanda(tmp_path, fase):
    """082:RF-6 — monofásica o bifásica: todas las SED con su trafo y la potencia de la fuente."""
    modelo = _modelo(tmp_path)
    _en_fase(modelo, fase)
    informe = oraculo.validar(modelo)
    assert informe.convergio, informe.resumen()
    assert informe.transformadores == len(modelo.seds)
    assert informe.p_carga_mw == pytest.approx(sum(c.p_mw for c in modelo.loads))
    assert informe.p_fuente_mw > informe.p_carga_mw * 0.99


def test_una_convergencia_sin_tensiones_no_es_convergencia(tmp_path):
    """082:RF-9 — ``runpp_3ph`` dice «convergió» con todo en nan: TI01 y C+æ02 con toda su demanda."""
    modelo = _modelo(tmp_path)
    _en_fase(modelo)
    _escalar(modelo, 10_000.0)
    informe = oraculo.validar(modelo)
    assert not informe.convergio
    assert 'no_converge' in {h.codigo for h in informe.errores}


def test_la_correccion_mide_con_el_mismo_flujo_del_veredicto(tmp_path):
    """082:RF-11 — el factor elegido deja sin errores el flujo por fases, y es determinista."""
    modelo = _modelo(tmp_path)
    _en_fase(modelo)
    _escalar(modelo, 10_000.0)
    otro = dataclasses.replace(modelo, loads=list(modelo.loads), warnings=[])
    resultado = oraculo.corregir_para_converger(modelo)
    assert resultado.convergio and resultado.factor
    final = oraculo.validar(modelo)
    assert final.flujo == 'desequilibrado' and final.convergio and not final.errores
    assert oraculo.corregir_para_converger(otro).factor == resultado.factor


def test_la_red_unida_calcula_sus_islas_por_fases():
    """082:RF-10 — con cargas monofásicas, cada isla de la red unida con el flujo desequilibrado."""
    red = _red()
    red.loads = [dataclasses.replace(c, phase='A') for c in red.loads]
    resultado = oraculo.validar_unida(red)
    assert resultado.general.flujo == 'desequilibrado'
    assert resultado.convergio
    assert all(i.convergio and i.v_min_pu is not None and i.p_mw for i in resultado.islas)
    assert resultado.general.p_fuente_mw > resultado.general.p_carga_mw * 0.99


def test_con_todo_trifasico_los_dos_flujos_dicen_lo_mismo(tmp_path):
    """082:RF-14 — la vara del contraste: sin fases, el flujo por fases queda a menos de 0,5 puntos del
    equilibrado. El contraste con DIgSILENT es la tarea [DIgSILENT] T4, que aquí no se puede hacer."""
    import pandapower

    modelo = _trifasico(_modelo(tmp_path))
    equilibrada = oraculo.validar(modelo)
    net, _barra, _informe = oraculo.red_pandapower(modelo, por_fases=True)
    oraculo._ejecutar(pandapower, net)
    assert float(oraculo._tensiones(net).min()) == pytest.approx(equilibrada.v_min_pu, abs=0.005)


def _con_regulador(modelo, corriente):
    """El primer tramo de verdad pasa a ser un regulador entre sus dos barras."""
    tramo = next(ln for ln in modelo.lines if ln.length_m >= oraculo._LARGO_CONEXION_M)
    modelo.lines = [ln for ln in modelo.lines if ln.section_id != tramo.section_id]
    modelo.devices = [d for d in modelo.devices if d.section_id != tramo.section_id]
    datos = DatosRegulador(2, corriente, float(modelo.nominal_kv))
    modelo.couplers = [Coupler('BR1', tramo.from_node, tramo.to_node, 1, 'regulador', 'E', 'E1', tramo.section_id,
                               'ABC', regulador=datos)]
    return modelo


@pytest.mark.parametrize('por_fases', (False, True))
def test_un_regulador_tiene_impedancia_y_no_cuenta_como_tramo(tmp_path, por_fases):
    """082:RF-15 — sus 3 consumían 0,23 Mvar en DIgSILENT y el oráculo los daba por interruptor. X = uk·Un/In."""
    modelo = _con_regulador(_trifasico(_modelo(tmp_path)), 100.0)
    net, _barra, informe = oraculo.red_pandapower(modelo, por_fases=por_fases)
    linea = net.line[net.line.name == 'BR1']
    assert len(linea) == 1 and not (net.switch.name == 'BR1').any()
    x_esperada = 0.003 * float(modelo.nominal_kv) * 1000 / 3 ** 0.5 / 100.0
    assert float(linea.x_ohm_per_km.iloc[0]) == pytest.approx(x_esperada)
    assert informe.lineas == len(net.line) - 1
    assert _cuadra(informe), informe.recuento
    assert oraculo.validar(modelo).convergio


def test_un_regulador_abierto_corta_y_sin_corriente_es_interruptor(tmp_path):
    """082:RF-15 — abierto no lleva corriente; sin corriente en la fuente no hay de dónde sacar su X."""
    modelo = _con_regulador(_trifasico(_modelo(tmp_path)), 100.0)
    modelo.couplers = [dataclasses.replace(modelo.couplers[0], on_off=0)]
    net, _barra, _informe = oraculo.red_pandapower(modelo)
    assert not bool(net.line[net.line.name == 'BR1'].in_service.iloc[0])
    sin_dato = _con_regulador(_trifasico(_modelo(tmp_path / 'b')), None)
    net, _barra, informe = oraculo.red_pandapower(sin_dato)
    assert (net.switch.name == 'BR1').any() and _cuadra(informe)
