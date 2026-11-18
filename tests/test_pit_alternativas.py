"""Spec 107 T8 — alternativas mutuamente excluyentes: inversión, COyM, pérdidas, confiabilidad y valor presente
(107:RF-5, 107:RF-8). Registro, costos y libro CAPEX sintéticos: ningún valor de una empresa ni de un periodo."""
from __future__ import annotations

import json

import openpyxl
import pytest

from datos_pit import perfil_a

from convertersmartgrid.aplicacion.costos_fuentes import Costo, FuenteCostos, TablaCostos
from convertersmartgrid.aplicacion.pide_economia import frc, van
from convertersmartgrid.adaptadores.pit.alternativas import evaluar
from convertersmartgrid.dominio.pit.ambito import areas_del_perfil, reunir
from convertersmartgrid.adaptadores.pit.diagnostico import agregar_demanda
from convertersmartgrid.aplicacion.pit.red_area import desde_ambito
from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.aplicacion.set_nueva import leer_modulos_pit

MONEDA = 'XTS'


def _registro(tmp_path, estado_tasa='no_verificada', perdidas=False):
    def regla(clave, valor):
        return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave}»', 'pagina': '1'}
    # 107:RF-20: un registro completo trae también el horizonte, las reglas citadas de la comparación y el umbral del N-1
    # (aquí 0 MW: el N-1 de todos los elementos con flujo, como antes).
    reglas_v = [regla('pit.vida_util_anios', 25), regla('pit.coym_pct', 3.0),
                regla('pit.horizonte_alternativas_anios', 10),
                regla('pit.criterio_alternativas', 'minimo_costo_total_inversion_coym_perdidas'),
                regla('pit.costo_total', 'valor_presente(inversion+operacion+mantenimiento+perdidas)'),
                regla('pit.coym_metodo', 'porcentaje_de_la_inversion'),
                regla('pit.tasa_actualizacion_fuente', 'art. 79 de la LCE'), regla('pit.n1_demanda_min_mw', 0.0)]
    if perdidas:
        reglas_v += [regla('pit.precio_perdidas', 40.0), regla('pit.horas_perdidas', 3000.0)]
    datos = {'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'SINT-V', 'titulo': 'Vigente', 'estado_juridico': 'vigente_comprobada', 'sha256': 'd' * 64,
         'vigencia_desde': '2001-01-01', 'reglas': reglas_v},
        {'acto': 'SINT-T', 'titulo': 'Tasa', 'estado_juridico': estado_tasa,
         **({'sha256': 'e' * 64, 'vigencia_desde': '2001-01-01'} if estado_tasa == 'vigente_comprobada' else {}),
         'reglas': [regla('pit.tasa_actualizacion', 0.11)]}]}
    carpeta = tmp_path / 'reg'
    carpeta.mkdir(exist_ok=True)
    (carpeta / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(carpeta)


def _tablas():
    fuente = FuenteCostos('Módulos sintéticos', 'transmision', 'SINT-001', 2001, MONEDA, 'https://ejemplo.invalid',
                          '2001-01-01', 'f' * 64)
    filas = {('TP-SINT', '', '', ''): Costo('TP-SINT', '', '', '', 'Transformador sintético', {'total': 900.0},
                                            fuente, unidad='u')}
    return {'transmision': TablaCostos(fuente, filas)}


def _caso(seed=19):
    caso = perfil_a(seed)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    red = desde_ambito(reunir(area, caso['elementos']))
    return caso, red, agregar_demanda(area, red, caso['proyeccion'])


def _paralelo(red, s, sufijo):
    t = next(e for e in red.de_tipo('trafo2') if e['set'] == s)
    return {**t, 'id': f'{t["id"]}-{sufijo}'}


def _libro_capex(tmp_path, kv_at, kv_mt):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'PIT'
    ws.append(['MÓDULOS', 'DESCRIPCIÓN', 'COSTO', 'MONEDA'])
    ws.append(['m1', f'Transformador {kv_at:g}/{kv_mt:g} kV de 30 MVA', 700.0, MONEDA])
    ruta = tmp_path / 'capex.xlsx'
    wb.save(ruta)
    return leer_modulos_pit(ruta, {'hoja': 'PIT', 'fila_cabecera_contiene': 'DESCRIPCIÓN',
                                   'columnas': {'descripcion': 'DESCRIPCIÓN', 'costo': 'COSTO', 'moneda': 'MONEDA'}})


def _alternativas(caso, red, tmp_path):
    s = caso['pistas']['sets']
    t0 = next(e for e in red.de_tipo('trafo2') if e['set'] == s[0])
    modulo = _libro_capex(tmp_path, t0['vn_hv_kv'], t0['vn_lv_kv'])[0]
    return [
        {'nombre': 'oficial', 'cambios': [{'accion': 'alta', 'elemento': _paralelo(red, s[0], 'b'),
                                           'costo': {'codigo': 'TP-SINT', 'cantidad': 1, 'unidad': 'u'}}]},
        {'nombre': 'sin_costo', 'cambios': [{'accion': 'alta', 'elemento': _paralelo(red, s[0], 'c'),
                                             'costo': {'codigo': 'NO-ESTA', 'cantidad': 1, 'unidad': 'u'}}]},
        {'nombre': 'capex', 'cambios': [{'accion': 'alta', 'elemento': _paralelo(red, s[0], 'd'),
                                         'modulo_pit': modulo}]},
    ]


def test_alternativa_sin_costo_queda_fuera_y_nunca_primera(tmp_path):
    """107:RF-5 — la que no tiene costo queda incompleta, con su motivo, fuera del orden; nunca con un 0."""
    caso, red, demanda = _caso()
    comp = evaluar(red, _alternativas(caso, red, tmp_path), demanda, caso['anios'], _registro(tmp_path), _tablas())
    res = {a.nombre: a for a in comp.alternativas}
    assert not res['sin_costo'].completa and 'NO-ESTA' in ' '.join(res['sin_costo'].motivos)
    assert comp.fuera_de_comparacion == ['sin_costo'] and 'sin_costo' not in comp.orden
    assert comp.orden[0] != 'sin_costo' and set(comp.orden) == {'oficial', 'capex'}
    assert not res['sin_costo'].valor_presente
    assert res['capex'].inversion_detalle['empresa'][0]['fuente'].endswith('(no oficial)')


def test_tasa_no_verificada_rotulada_como_referencia(tmp_path):
    """107:RF-8 — la tasa no verificada se usa como referencia y el resultado lo dice con su norma y su estado."""
    caso, red, demanda = _caso()
    comp = evaluar(red, _alternativas(caso, red, tmp_path), demanda, caso['anios'], _registro(tmp_path), _tablas())
    tasa = comp.reglas['pit.tasa_actualizacion']
    assert tasa['estado'] == 'no_verificada' and tasa['obligatoria'] is False
    assert any('pit.tasa_actualizacion' in a and 'referencia' in a for a in comp.avisos)
    assert comp.reglas['pit.vida_util_anios']['obligatoria'] is True


def test_misma_demanda_mismo_motor_y_valor_presente(tmp_path):
    """107:RF-5 — todas con la misma demanda (huella) y motor; VP = van de inversión, COyM y pérdidas valoradas."""
    caso, red, demanda = _caso()
    reg = _registro(tmp_path, 'vigente_comprobada', perdidas=True)
    comp = evaluar(red, _alternativas(caso, red, tmp_path), demanda, caso['anios'], reg, _tablas())
    assert comp.motor == 'abierto' and len(comp.demanda_huella) == 64 and not comp.avisos
    of = next(a for a in comp.alternativas if a.nombre == 'oficial')
    ci = of.inversion[MONEDA]
    assert ci == 900.0 and of.coym_anual[MONEDA] == pytest.approx(27.0)
    assert of.anualidad[MONEDA] == pytest.approx(ci * frc(0.11, 25))
    perd = [of.perdidas_valor[a] for a in caso['anios']]
    assert all(p > 0 for p in perd)
    flujos = [ci + perd[0]] + [27.0 + p for p in perd[1:]]
    assert of.valor_presente[MONEDA] == pytest.approx(van(flujos, 0.11))
    assert of.confiabilidad['motor'] == 'abierto' and of.confiabilidad['alcance'] == 'reducido'
    assert of.confiabilidad['p_sin_servir_peor_n_1_mw'] > 0
    # Las dos completas solo difieren en la inversión: la más barata va primero.
    assert comp.orden == ['capex', 'oficial']


def test_sin_reglas_en_el_registro_la_alternativa_queda_incompleta(tmp_path):
    """107:RF-8 — sin tasa ni vida útil en el registro no hay valor presente: se dice qué regla falta."""
    caso, red, demanda = _caso()
    vacio = tmp_path / 'vacio'
    vacio.mkdir()
    (vacio / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': []}), encoding='utf-8')
    comp = evaluar(red, _alternativas(caso, red, tmp_path)[:1], demanda, caso['anios'], cargar_registro(vacio),
                   _tablas())
    assert comp.orden == [] and 'falta la regla pit.tasa_actualizacion' in ' '.join(comp.alternativas[0].motivos)
