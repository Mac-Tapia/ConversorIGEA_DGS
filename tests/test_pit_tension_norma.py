"""Spec 107 T7, tarjeta PIT-TEN — los límites de tensión del diagnóstico, por barra, desde la norma (107:RF-3, RF-4).

La red es sintética y el flujo se sustituye por tensiones fijadas en cada prueba: lo que se prueba es el criterio de
cada barra (RCD 217-2013, 12.2.1.a; NTCSE 5.1.2; NTCSER 4.1.2; RM 129-2009, art. 10 y Primera, por la remisión del
12.3.2 en la redacción de la RCD 018-2018), no el motor. El registro es el real de ``config/normativa``.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import openpyxl
import pytest

from convertersmartgrid.pit import diagnostico as dg
from convertersmartgrid.pit.ambito import AreaPit, PitError
from convertersmartgrid.pit.diagnostico import diagnosticar, limites_de_tension
from convertersmartgrid.pit.expediente import abrir, emitir
from convertersmartgrid.pit.red_area import RedArea, leer_libro_red
from convertersmartgrid.pit.red_pandapower import ResultadoFlujo
from convertersmartgrid.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
AREA = 'AD-T'
FUENTE_RM129 = 'RM 129-2009-MEM/DM, art. 10 y Primera Disposición Final (SPIJ H982706)'
TOMAS = {'tap_side': 'hv', 'tap_min': -10, 'tap_max': 10, 'tap_neutral': 0, 'tap_step_percent': 1.0}


def _barra(bid, kv, **datos):
    return {'id': bid, 'tipo': 'barra', 'kv': kv, 'titular': 'T', **datos}


def _trafo(tid, hv, lv, kv_hv, kv_lv, **tomas):
    return {'id': tid, 'tipo': 'trafo2', 'hv': hv, 'lv': lv, 'titular': 'T', 'sn_mva': 25.0, 'vn_hv_kv': kv_hv,
            'vn_lv_kv': kv_lv, 'vk_percent': 10.0, 'vkr_percent': 0.5, 'pfe_kw': 15.0, 'i0_percent': 0.1, **tomas}


def _caso(barras, trafos=(), *, area_demanda=8, limites=None):
    """Área, red y perfil sintéticos: la barra con ``rol='carga'`` recibe la demanda de la SET S1."""
    area = AreaPit(codigo=AREA, titulares=('T',), set=('S1',), set_alimentadores={'S1': ('A1',)},
                   tension_min_kv=30.0, compartidos={})
    red = RedArea(AREA, elementos={'barra': list(barras), 'trafo2': list(trafos)})
    pit = {'areas': [{'codigo': AREA, 'area_demanda': area_demanda}], 'limites': dict(limites or {})}
    return area, red, {'pit': pit}


FILAS = [{'alimentador': 'A1', 'anio_calendario': 2031, 'p_kw': 1000.0, 'q_kvar': 100.0}]


def _flujo(monkeypatch, base, n_1=None):
    """El flujo devuelve ``base`` en el caso base y ``n_1`` (o ``base``) en cada contingencia."""
    def falso(estudio, red, cargas, *, motor='abierto', fuera=()):
        v = base if not fuera else (n_1 if n_1 is not None else base)
        return {'resultado': ResultadoFlujo(motor, True, tuple(fuera), dict(v))}
    monkeypatch.setattr(dg, 'ejecutar', falso)


def _registro():
    return cargar_registro(NORMATIVA)


def _diagnostico(area, red, perfil, registro=None):
    registro = registro or _registro()
    tension = limites_de_tension(red, area, registro, perfil)
    limites = {'cargabilidad_max_pct': {'valor': 100.0, 'origen': 'perfil', 'regla': 'pit.limites.cargabilidad_max_pct'}}
    return diagnosticar(area, red, FILAS, [2031], limites, tension=tension), tension


def _de(caso, magnitud, elemento=None):
    return [v for v in caso if v['magnitud'] == magnitud and (elemento is None or v['elemento'] == elemento)]


# --------------------------------------------------------------------------- NTCSE y NTCSER con entrega

def test_mt_con_entrega_en_red_urbana_tiene_cinco_por_ciento(monkeypatch):
    """107:RF-3 — barra de MT con entrega en red urbana: ±5 % de la NTCSE (5.1.2), obligatoria, con su regla."""
    area, red, perfil = _caso([_barra('MT1', 22.9, rol='carga', set='S1', entrega='sí', tipo_red='urbana')])
    _flujo(monkeypatch, {'MT1': 0.94})
    diag, tension = _diagnostico(area, red, perfil)
    e = tension['barras']['MT1']
    assert (e['nivel'], e['criterio'], e['normal_pu']) == ('MT', 'ntcse', [0.95, 1.05])
    assert e['regla'] == 'calidad.tension.tolerancia_ntcse' and e['origen'] == 'registro' and e['cuenta']
    malas = _de(diag.anios[0].base.violaciones, 'tension_pu', 'MT1')
    assert len(malas) == 1 and malas[0]['limite'] == 0.95 and malas[0]['regla'] == 'calidad.tension.tolerancia_ntcse'
    assert 'calidad.tension.tolerancia_ntcse' in tension['reglas'] and diag.completo


def test_rural_siete_y_medio_solo_en_baja_tension(monkeypatch):
    """107:RF-3 — servicio rural: ±7,5 % en la red secundaria (BT) y ±5 % en MT (NTCSE 5.1.2, «redes secundarias»)."""
    area, red, perfil = _caso([_barra('MT1', 10.0, rol='carga', set='S1', entrega='si', tipo_red='rural'),
                               _barra('BT1', 0.38, entrega='si', tipo_red='rural')])
    _flujo(monkeypatch, {'MT1': 0.93, 'BT1': 0.93})
    diag, tension = _diagnostico(area, red, perfil)
    assert tension['barras']['BT1']['normal_pu'] == [0.925, 1.075] and tension['barras']['BT1']['nivel'] == 'BT'
    assert tension['barras']['MT1']['normal_pu'] == [0.95, 1.05]
    base = diag.anios[0].base
    assert not _de(base.violaciones, 'tension_pu', 'BT1') and _de(base.violaciones, 'tension_pu', 'MT1')


def test_ser_seis_por_ciento_en_mt_y_hueco_en_at(monkeypatch):
    """107:RF-3, RF-4 — SER: ±6 % en MT (NTCSER 4.1.2); en AT la NTCSER no da tolerancia y queda un hueco nombrado."""
    area, red, perfil = _caso([_barra('MT1', 22.9, rol='carga', set='S1', entrega=True, tipo_red='SER'),
                               _barra('AT1', 60.0, entrega=True, tipo_red='ser')])
    _flujo(monkeypatch, {'MT1': 0.945, 'AT1': 0.5})
    diag, tension = _diagnostico(area, red, perfil)
    e = tension['barras']['MT1']
    assert (e['criterio'], e['normal_pu'], e['regla']) == ('ntcser', [0.94, 1.06], 'calidad.tension.tolerancia_ntcser')
    assert not diag.anios[0].base.violaciones
    hueco = next(h for h in diag.huecos_tension if h.get('barra') == 'AT1')
    assert any('NTCSER' in f for f in hueco['falta']) and not diag.completo


# --------------------------------------------------------------------------- AT sin entrega: tomas del AT/MT

@pytest.mark.parametrize('caso', ('cumple', 'no_cumple', 'sin_tomas'))
def test_at_sin_entrega_se_comprueba_por_las_tomas(monkeypatch, caso):
    """107:RF-3, RF-4 — AT sin entrega: sin límite propio; el rango de tomas del AT/MT tiene que llevar su MT a ±5 %.
    Sin las tomas, un hueco nombrado del transformador, sin «cumple» ni violación."""
    tomas = {'cumple': TOMAS, 'no_cumple': {**TOMAS, 'tap_min': 0, 'tap_max': 0}, 'sin_tomas': {}}[caso]
    area, red, perfil = _caso([_barra('AT1', 60.0, entrega='no'),
                               _barra('MT1', 22.9, rol='carga', set='S1', entrega='no', tipo_red='urbana')],
                              [_trafo('T1', 'AT1', 'MT1', 60.0, 22.9, **tomas)])
    _flujo(monkeypatch, {'AT1': 0.80, 'MT1': 0.93})
    diag, tension = _diagnostico(area, red, perfil)
    assert tension['barras']['AT1']['criterio'] == 'regulacion_transformador'
    base = diag.anios[0].base
    assert not _de(base.violaciones, 'tension_pu')  # ni la AT ni la MT sin entrega tienen límite propio
    reg = _de(base.violaciones, 'regulacion_tension', 'T1')
    if caso == 'cumple':
        assert [r['cumple'] for r in base.regulacion] == [True] and not reg and diag.completo
    elif caso == 'no_cumple':
        assert [r['cumple'] for r in base.regulacion] == [False] and len(reg) == 1
        assert reg[0]['alcanzable'] == [0.93, 0.93] and reg[0]['limite'] == [0.95, 1.05]
    else:
        assert not base.regulacion and not reg
        hueco = next(h for h in diag.huecos_tension if h.get('elemento') == 'T1')
        assert {'tap_side', 'tap_min', 'tap_max'} <= set(hueco['falta']) and not diag.completo


# --------------------------------------------------------------------------- RM 129-2009: Área 15 y referencia

def test_mat_de_otra_area_es_aviso_visible_de_referencia(monkeypatch):
    """107:RF-3 — MAT sin entrega fuera del Área 15: la RM 129-2009 como referencia, un aviso con la barra, la cifra y
    la fuente, y no cuenta como violación."""
    area, red, perfil = _caso([_barra('MAT1', 220.0, entrega='no', tension_operacion_kv=225.0),
                               _barra('MT1', 22.9, rol='carga', set='S1', entrega='no', tipo_red='urbana')])
    _flujo(monkeypatch, {'MAT1': 1.09, 'MT1': 1.0})
    diag, tension = _diagnostico(area, red, perfil)
    e = tension['barras']['MAT1']
    assert e['criterio'] == 'referencia' and e['origen'] == 'registro_referencia' and not e['cuenta']
    base = diag.anios[0].base
    assert not _de(base.violaciones, 'tension_pu', 'MAT1')
    assert _de(base.referencias, 'tension_pu', 'MAT1')[0]['valor'] == 1.09
    ref = next(r for r in diag.referencias if r['barra'] == 'MAT1')
    assert ref['casos_fuera'] == 1 and ref['max_pu'] == 1.09 and ref['rango_normal_operacion_pu'] == [0.95, 1.05]
    aviso = next(a for a in diag.avisos if 'MAT1' in a)
    assert '1.0900' in aviso and FUENTE_RM129 in aviso and 'Área de Demanda 15' in aviso and '225 kV' in aviso


def _area15(monkeypatch, emergencia=None):
    """AT sin entrega del Área 15 a 0,93 p.u. de su tensión de operación, en el caso base y en el N-1 de T1."""
    area, red, perfil = _caso([_barra('AT1', 60.0, entrega='no', tension_operacion_kv=60.0),
                               _barra('MT1', 22.9, rol='carga', set='S1', entrega='no', tipo_red='urbana')],
                              [_trafo('T1', 'AT1', 'MT1', 60.0, 22.9, **TOMAS)], area_demanda=15)
    if emergencia is not None:
        perfil['pit']['emergencia_rm129'] = emergencia
    _flujo(monkeypatch, {'AT1': 0.93, 'MT1': 1.0})
    return area, red, perfil


def test_area15_la_rm129_obliga_y_el_n_1_va_por_defecto_con_el_rango_normal(monkeypatch):
    """107:RF-3 — AT sin entrega del Área 15: la RM 129-2009 obliga sobre la tensión de operación del COES; sin
    pit.emergencia_rm129, el N-1 también va con el rango normal (nota 2 del art. 10). Cambiada en PIT-TEN v2: en la v1
    el N-1 iba con el de emergencia."""
    diag, tension = _diagnostico(*_area15(monkeypatch))
    e = tension['barras']['AT1']
    assert e['criterio'] == 'area15' and e['cuenta'] and e['regla'] == 'pit.area15.criterios_desempeno'
    assert e['emergencia_pu'] == [0.95, 1.05] and e.get('n_1_con') == 'normal'
    anio = diag.anios[0]
    malas = _de(anio.base.violaciones, 'tension_pu', 'AT1')
    assert len(malas) == 1 and malas[0]['limite'] == 0.95 and malas[0]['criterio'] == 'area15'
    n_1 = [v for c in anio.contingencias for v in _de(c.violaciones, 'tension_pu', 'AT1')]
    assert n_1 and all(v['limite'] == 0.95 for v in n_1)
    assert not any('pit.emergencia_rm129' in a for a in diag.avisos)


def test_area15_el_n_1_usa_la_emergencia_solo_con_su_sustento(monkeypatch):
    """107:RF-3 — con pit.emergencia_rm129 y su sustento, el N-1 va con el rango de emergencia (0,90-1,05 p.u. hasta
    138 kV), y un aviso cita el sustento y la nota (2) del art. 10; el caso base sigue con el normal."""
    sustento = 'la pérdida de la línea L-X deja la SET radial: el estudio de estabilidad del anexo 4 lo demuestra'
    diag, tension = _diagnostico(*_area15(monkeypatch, {'aplica': True, 'sustento': sustento}))
    e = tension['barras']['AT1']
    assert e['emergencia_pu'] == [0.9, 1.05] and e.get('n_1_con') == 'emergencia'
    anio = diag.anios[0]
    assert _de(anio.base.violaciones, 'tension_pu', 'AT1')
    assert all(not _de(c.violaciones, 'tension_pu', 'AT1') for c in anio.contingencias)  # 0,93 ≥ 0,90 en N-1
    aviso = next((a for a in diag.avisos if 'pit.emergencia_rm129' in a), '')
    assert sustento in aviso and '(2) La condición de tensión en régimen de emergencia' in aviso
    assert 'pit.area15.criterios_desempeno_notas' in tension['reglas']


@pytest.mark.parametrize('campo', ({'aplica': True}, {'aplica': True, 'sustento': '  '}, {'aplica': 'sí'}))
def test_emergencia_rm129_sin_sustento_es_un_error_que_lo_nombra(campo):
    """107:RF-11 — «aplica» true sin sustento (o mal declarado) no se toma: el error nombra el campo."""
    area, red, perfil = _caso([_barra('AT1', 60.0, entrega='no', tension_operacion_kv=60.0)], area_demanda=15)
    perfil['pit']['emergencia_rm129'] = campo
    with pytest.raises(PitError, match='pit.emergencia_rm129'):
        limites_de_tension(red, area, _registro(), perfil)


def test_area15_sin_tension_de_operacion_es_hueco(monkeypatch):
    """107:RF-4 — en el Área 15, sin la tensión de operación del COES el límite es un hueco nombrado: ni violación ni
    «cumple», y nunca sobre la nominal."""
    area, red, perfil = _caso([_barra('AT1', 60.0, entrega='no'),
                               _barra('MT1', 22.9, rol='carga', set='S1', entrega='no', tipo_red='urbana')],
                              area_demanda=15)
    _flujo(monkeypatch, {'AT1': 0.5, 'MT1': 1.0})
    diag, tension = _diagnostico(area, red, perfil)
    assert 'normal_pu' not in tension['barras']['AT1']
    hueco = next(h for h in diag.huecos_tension if h.get('barra') == 'AT1')
    assert any('tension_operacion_kv' in f for f in hueco['falta']) and not diag.completo
    anio = diag.anios[0]
    assert not _de(anio.base.violaciones, 'tension_pu', 'AT1') and not _de(anio.base.referencias, 'tension_pu', 'AT1')


@pytest.mark.parametrize('estado, cuenta', (('modificada', True), ('no_verificada', False)))
def test_area15_obliga_o_avisa_segun_el_estado_de_su_norma(monkeypatch, tmp_path, estado, cuenta):
    """107:RF-3, RF-8 — la misma barra del Área 15 cuenta como violación con su norma vigente y pasa a aviso visible
    con la norma «no_verificada»: solo cambia el estado jurídico en el registro, no el código."""
    copia = tmp_path / 'normativa'
    shutil.copytree(NORMATIVA, copia)
    f = copia / 'rm_129_2009_mem_dm.json'
    datos = json.loads(f.read_text(encoding='utf-8'))
    datos['normas'][0]['estado_juridico'] = estado
    f.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    area, red, perfil = _caso([_barra('AT1', 60.0, entrega='no', tension_operacion_kv=60.0),
                               _barra('MT1', 22.9, rol='carga', set='S1', entrega='no', tipo_red='urbana')],
                              area_demanda=15)
    _flujo(monkeypatch, {'AT1': 1.08, 'MT1': 1.0})
    diag, _ = _diagnostico(area, red, perfil, cargar_registro(copia))
    base = diag.anios[0].base
    assert bool(_de(base.violaciones, 'tension_pu', 'AT1')) is cuenta
    assert bool(_de(base.referencias, 'tension_pu', 'AT1')) is not cuenta
    assert any('AT1' in a and FUENTE_RM129 in a for a in diag.avisos) is not cuenta


# --------------------------------------------------------------------------- huecos y respaldo del perfil

def test_barra_con_entrega_sin_tipo_de_red_es_hueco(monkeypatch):
    """107:RF-4 — sin el tipo de red no se sabe si rige la NTCSE o la NTCSER: hueco nombrado, sin valor supuesto."""
    area, red, perfil = _caso([_barra('MT1', 22.9, rol='carga', set='S1', entrega='si')])
    _flujo(monkeypatch, {'MT1': 0.5})
    diag, tension = _diagnostico(area, red, perfil)
    assert tension['barras']['MT1']['criterio'] == 'hueco'
    hueco = next(h for h in diag.huecos_tension if h.get('barra') == 'MT1')
    assert any(f.startswith('tipo_red') for f in hueco['falta'])
    assert not diag.anios[0].base.violaciones and not diag.completo


def test_el_perfil_sigue_como_respaldo_explicito(monkeypatch):
    """107:RF-3 (compatibilidad) — con pit.limites, la barra a la que le falta un dato usa el perfil, con su origen
    y un aviso que dice qué falta; sus violaciones cuentan."""
    area, red, perfil = _caso([_barra('MT1', 22.9, rol='carga', set='S1', entrega='si')],
                              limites={'tension_min_pu': 0.9, 'tension_max_pu': 1.1})
    _flujo(monkeypatch, {'MT1': 0.85})
    diag, tension = _diagnostico(area, red, perfil)
    e = tension['barras']['MT1']
    assert (e['criterio'], e['origen'], e['normal_pu']) == ('perfil', 'perfil', [0.9, 1.1])
    assert any('MT1' in a and 'pit.limites' in a for a in diag.avisos) and not diag.huecos_tension
    assert _de(diag.anios[0].base.violaciones, 'tension_pu', 'MT1')[0]['limite'] == 0.9


def test_tension_que_no_casa_con_ningun_nivel_es_hueco():
    """107:RF-4 — 150 kV no es MAT (500, 220 o 138 kV) ni AT (< 138 kV): no se clasifica por aproximación."""
    area, red, perfil = _caso([_barra('X1', 150.0, entrega='no')])
    tension = limites_de_tension(red, area, _registro(), perfil)
    assert any('150 kV' in f for h in tension['huecos'] if h.get('barra') == 'X1' for f in h['falta'])


# --------------------------------------------------------------------------- lector y expediente

def test_el_lector_toma_las_columnas_de_tension_si_estan(tmp_path):
    """107:RF-12 — entrega, tipo de red, tensión de operación y tomas se leen del libro cuando están."""
    claves = ['id', 'tipo', 'kv', 'titular', 'entrega', 'tipo_red', 'tension_operacion_kv', 'hv', 'lv', 'tap_side',
              'tap_min', 'tap_max', 'tap_neutral', 'tap_step_percent']
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Red'
    ws.append(claves)
    ws.append(['B1', 'barra', 60, 'T', 'no', None, 61.5, None, None, None, None, None, None, None])
    ws.append(['T1', 'trafo2', 60, 'T', None, None, None, 'B1', 'B2', 'hv', -8, 8, 0, 1.25])
    wb.save(tmp_path / 'red.xlsx')
    libro = leer_libro_red(tmp_path / 'red.xlsx', {})
    b1, t1 = {e['id']: e for e in libro}['B1'], {e['id']: e for e in libro}['T1']
    assert (b1.get('entrega'), b1.get('tension_operacion_kv')) == ('no', 61.5)
    assert (t1.get('tap_side'), t1.get('tap_min'), t1.get('tap_step_percent')) == ('hv', -8.0, 1.25)


def test_huecos_y_referencias_llegan_al_expediente(monkeypatch, tmp_path):
    """107:RF-4, RF-7 — el hueco de tensión es un pendiente del expediente y la referencia, un aviso en su resumen."""
    area, red, perfil = _caso([_barra('MAT1', 220.0, entrega='no', tension_operacion_kv=220.0),
                               _barra('MT1', 22.9, rol='carga', set='S1', entrega='si')])
    _flujo(monkeypatch, {'MAT1': 1.07, 'MT1': 1.0})
    registro = _registro()
    diag, _ = _diagnostico(area, red, perfil, registro)
    carpeta = abrir(tmp_path / 'espacio', AREA, '2031-2031', registro, fecha_apertura='2026-11-15')
    salidas = emitir(carpeta, registro, celdas=[], diagnostico=diag)
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    assert any(p['campo'] == 'diagnostico.tension.MT1' and 'tipo_red' in p['causa'] for p in resumen['pendientes'])
    assert any('MAT1' in a and FUENTE_RM129 in a for a in resumen['avisos_diagnostico'])
    reglas = {r['clave'] for r in json.loads(salidas['reglas'].read_text(encoding='utf-8'))}
    assert {'pit.area15.criterios_desempeno', 'pit.diagnostico.niveles_tension_rangos_kv'} <= reglas
    memoria = json.loads(salidas['memoria'].read_text(encoding='utf-8'))['diagnostico']
    assert memoria['criterios']['tension_por_barra']['MAT1']['criterio'] == 'referencia'
    assert memoria['resultados']['referencias_tension'][0]['barra'] == 'MAT1'
