"""MEJ27-FIJAS (orden del usuario del 21-11): una fija imposible se diagnostica, se corrige o se libera; nunca para.

Datos sintéticos: códigos y curvas inventados. El caso que lo motivó (un cliente con su FM ×3,33 en el libro de un mes
sin cambio en su cabecera, y su alimentador parado antes del primer flujo) está fuera del repositorio.
"""
from __future__ import annotations

import math
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.aplicacion import demanda_medida as dm
from convertersmartgrid.dominio import ajuste_cabecera as ac


def _funcion(modulo, nombre):
    """La función, o una aserción que dice que falta (rojo por aserción sobre el árbol de antes)."""
    f = getattr(modulo, nombre, None)
    assert f is not None, f'falta {modulo.__name__}.{nombre}'
    return f


def _curva(dias, kw, desde=datetime(2026, 10, 1), q=0.25):
    """Una curva de 15 minutos de ``dias`` días; ``kw(i)`` da el kW del registro i."""
    return [(desde + timedelta(minutes=15 * i), kw(i), kw(i) * q) for i in range(96 * dias)]


def _diaria(i, base, amplitud):
    """Un ciclo diario suave, sin atípicos."""
    return base + amplitud * math.sin(2 * math.pi * (i % 96) / 96.0)


def _cambio_fm(factor=0.3, salto=1 / 0.3):
    return {'codigo': '900001', 'aviso': 'FM_CAMBIADO', 'fm_anterior': 30.0, 'fm_actual': 100.0,
            'medidor_anterior': 'MX-1', 'medidor_actual': 'MX-2', 'razon_fm': 1 / factor, 'salto_energia': salto,
            'dia_anterior': '2026-09-30', 'kwh_anterior': 2400.0, 'dia': '2026-10-01', 'kwh': 8000.0,
            'factor_propuesto': factor, 'mes': '2026-10'}


# =========================================================================== (a) factor del medidor
def test_039_rf24_a_fm_cambiado_con_cabecera_estable_se_corrige_solo():
    """039:RF-24 (a) — el cliente mide más que su cabecera porque su FM pasó de 30 a 100 sin cambio en la cabecera: el
    diagnóstico deduce el factor (0,3) y lo da por corrección automática, con la cabecera de los dos días."""
    diag = _funcion(ac, 'diagnostico_fija_imposible')
    estable = _funcion(ac, 'cabecera_estable')
    desde = datetime(2026, 9, 30)
    cabecera = _curva(2, lambda i: _diaria(i, 400.0, 30.0), desde=desde)
    cliente = _curva(2, lambda i: (200.0 if i < 96 else 200.0 / 0.3) + _diaria(i, 0.0, 10.0), desde=desde)
    e = estable(cabecera, _cambio_fm())
    assert e['estable'] is True and e['razon'] == pytest.approx(1.0)
    r = diag('900001', cliente, cabecera, cambio_fm=_cambio_fm())
    assert r['causa'] == 'FM_CAMBIADO' and r['accion'] == 'corregir_factor' and r['factor'] == pytest.approx(0.3), r
    assert r['registros'] > 0 and r['exceso_max_kw'] > 0
    assert 'corrección automática' in r['texto'] and '30' in r['texto'] and '100' in r['texto']
    # Sin el cambio de FM, el mismo cliente no se corrige: la hipótesis lo dice con su factor.
    sin = diag('900001', cliente, cabecera)
    assert sin['accion'] == 'liberar_fija' and sin['factor_que_cabria'] < 1.0 and 'hipótesis' in sin['texto']


def test_039_rf24_a_si_la_cabecera_salta_con_el_fm_no_es_el_medidor():
    """039:RF-24 (a) — si la cabecera salta en los mismos días como el cliente, el cambio es de carga y no se corrige."""
    diag = _funcion(ac, 'diagnostico_fija_imposible')
    desde = datetime(2026, 9, 30)
    cabecera = _curva(2, lambda i: (300.0 if i < 96 else 1000.0) + _diaria(i, 0.0, 10.0), desde=desde)
    cliente = _curva(2, lambda i: (100.0 if i < 96 else 1010.0), desde=desde)
    assert _funcion(ac, 'cabecera_estable')(cabecera, _cambio_fm())['estable'] is False
    r = diag('900001', cliente, cabecera, cambio_fm=_cambio_fm())
    assert r is not None and r['accion'] != 'corregir_factor', r


def test_039_rf24_a_fm_cambiado_se_detecta_con_el_registro_del_dia_siguiente(tmp_path):
    """039:RF-24 (a), 004:RF-111 — el libro de un mes trae el registro de las 00:00 del día siguiente: el salto se mide
    entre días completos de cada mes. Antes el «último día» del mes anterior era ese registro suelto y el aviso no
    salía (en un caso real, ×297 en vez de ×3,82)."""
    from test_demanda_medida import _libro

    def libro(path, mes, dias, fm, ea, siguiente):
        filas = [['SUMINISTRO', 'FECHA', 'HORA', 'EA', 'ERI', 'POT']]
        for d in dias:
            for k in range(24):
                filas.append(['900001', f'{d:02d}/{mes:02d}/2026', f'{k:02d}:00', ea, ea / 4, ea * 4])
        filas.append(['900001', siguiente, '00:00', ea, ea / 4, ea * 4])
        return _libro(path, {'Resumen': [['SUMINISTRO', 'EA_TOTAL', 'ERI_TOTAL', 'POT_MAX'],
                                         ['900001', ea * 24 * len(dias), ea * 6 * len(dias), ea * 4]],
                             'maestro_lib': [['numero_suministro', 'nombre_hoja_exportacion', 'fm',
                                              'numero_identificador'], ['900001', 'c900001', fm, 'MX']],
                             'c900001': filas})

    sep = libro(tmp_path / 'sep.xlsx', 9, (29, 30), 30.0, 10.0, '01/10/2026')
    octu = libro(tmp_path / 'oct.xlsx', 10, (1, 2), 100.0, 10.0 * 100 / 30, '03/10/2026')
    avisos = dm.fm_cambiados(octu, sep, '2026-10', '2026-09')
    assert len(avisos) == 1, 'el registro suelto del día siguiente tapa el salto del FM'
    (aviso,) = avisos
    assert (aviso['dia_anterior'], aviso['dia']) == ('2026-09-30', '2026-10-01'), aviso
    assert aviso['salto_energia'] == pytest.approx(100 / 30)


# =========================================================================== (b) registros aislados
def test_039_rf24_b_un_pico_aislado_se_excluye_como_dato_malo():
    """039:RF-24 (b) — un solo registro del cliente, atípico por Hampel, pasa de su cabecera: se excluye y se dice la
    mediana local que lo reemplaza; los que pasan muchos registros no son datos malos."""
    diag = _funcion(ac, 'diagnostico_fija_imposible')
    atipicos = _funcion(ac, 'registros_atipicos')
    cabecera = _curva(3, lambda i: _diaria(i, 500.0, 50.0))
    cliente = _curva(3, lambda i: 2000.0 if i == 130 else _diaria(i, 200.0, 20.0))
    raros = atipicos(cliente)
    assert list(raros) == [cliente[130][0]] and raros[cliente[130][0]] == pytest.approx(cliente[129][1], rel=0.05)
    r = diag('900001', cliente, cabecera)
    assert r['causa'] == 'REGISTROS_AISLADOS' and r['accion'] == 'excluir_registros', r
    (x,) = r['excluidos']
    assert x['de'] == 'cliente' and x['kw'] == 2000.0 and x['reemplazo_kw'] < 500.0
    assert 'Hampel' in r['texto']
    # Una curva plana no da atípicos por decimales.
    assert atipicos(_curva(1, lambda i: 100.0 + (i % 2) * 0.01)) == {}


def test_039_rf24_b_una_caida_aislada_de_la_cabecera_tambien_es_dato_malo():
    """039:RF-24 (b) — la cabecera cae a 5 kW en un registro (corte de su medidor): el cliente pasa ahí y se excluye."""
    cabecera = _curva(2, lambda i: 5.0 if i == 60 else _diaria(i, 500.0, 50.0))
    cliente = _curva(2, lambda i: _diaria(i, 200.0, 20.0))
    r = _funcion(ac, 'diagnostico_fija_imposible')('900001', cliente, cabecera)
    assert r['accion'] == 'excluir_registros' and r['excluidos'][0]['de'] == 'cabecera', r


# =========================================================================== (c) otro alimentador
def test_039_rf24_c_cabe_en_la_cabecera_de_otro_alimentador_se_propone():
    """039:RF-24 (c) — el cliente pasa siempre de su cabecera y cabe siempre en la del otro alimentador de la misma SET:
    se propone la reasignación con el margen mínimo, sin aplicarla."""
    diag = _funcion(ac, 'diagnostico_fija_imposible')
    cabecera = _curva(2, lambda i: _diaria(i, 150.0, 10.0))
    otra = _curva(2, lambda i: _diaria(i, 900.0, 50.0))
    cliente = _curva(2, lambda i: _diaria(i, 300.0, 30.0))
    r = diag('900001', cliente, cabecera, vecinas={'A2': otra, 'A3': cabecera})
    assert r['causa'] == 'OTRO_ALIMENTADOR' and r['alimentador'] == 'A2', r
    assert r['margen_min_kw'] > 0 and 'reasignarlo a A2' in r['texto']


# =========================================================================== (d) hipótesis con números
def test_039_rf24_d_sin_causa_cierta_dice_la_hipotesis_con_numeros():
    """039:RF-24 (d) — nada lo explica: la hipótesis más probable con el factor con que cabría y la fracción de la
    energía de la cabecera; nunca «no puede cuadrar» a secas."""
    cabecera = _curva(2, lambda i: _diaria(i, 300.0, 10.0))
    cliente = _curva(2, lambda i: _diaria(i, 330.0, 10.0))
    r = _funcion(ac, 'diagnostico_fija_imposible')('900001', cliente, cabecera)
    assert r['causa'] == 'HIPOTESIS' and r['accion'] == 'liberar_fija', r
    assert r['factor_que_cabria'] == pytest.approx(300.0 / 340.0, rel=0.05)
    assert r['fraccion_energia'] == pytest.approx(1.1, rel=0.02)
    assert 'hipótesis más probable' in r['texto'] and 'TC' in r['hipotesis'] and 'no puede cuadrar' not in r['texto']
    assert ac.diagnostico_fija_imposible('900001', _curva(1, lambda i: 10.0), cabecera) is None, 'si cabe, nada'


# =========================================================================== RF-25: liberar, no parar
def test_039_rf25_la_plausibilidad_libera_la_imposible_y_no_la_dudosa():
    """039:RF-25 — la fija que mide más que su cabecera se libera; la que solo deja casi nada a las escaladas, no."""
    objetivo = ac.Objetivo(2503.0, 800.0, 'M1', 'A1', '2026-10-15 15:15:00')
    f = ac.Fija('S1', 1806.5, 900.0, clientes=['900001'])
    evid = {'900001': {'supera_cabecera': {'registros': 5, 'exceso_max_kw': 162.0, 'fecha': '2026-10-21 13:15:00'},
                       'diagnostico': {'accion': 'liberar_fija', 'hipotesis': 'el FM no es el del libro'}}}
    r = ac.plausibilidad_fijas(objetivo, {'S1': f}, p_base_escaladas=6000.0, evidencia=evid)
    assert r.get('liberadas') == ['S1'] and r['fijas'][0]['liberar'], r
    assert 'el FM no es el del libro' in r['texto'] and 'calibra con el resto' in r['texto']
    assert r['fijas'][0]['motivos'][0]['diagnostico']['accion'] == 'liberar_fija'
    dudosa = ac.plausibilidad_fijas(objetivo, {'S1': f, 'S2': ac.Fija('S2', 518.0, 0.0, clientes=['900002'])},
                                    p_base_escaladas=6741.0 * 0.98)
    assert dudosa['estado'] == 'FIJA_A_REVISAR' and dudosa['liberadas'] == [], dudosa


# =========================================================================== la web: registrar y aplicar
def _ws(correcciones=None, curvas=None):
    return SimpleNamespace(lock=threading.RLock(), correcciones_medidor=list(correcciones or []),
                           curvas_cabecera={'J1': curvas or {}}, save=lambda: None)


def _parchear(monkeypatch, curva_cliente):
    from convertersmartgrid.presentacion.web import services

    monkeypatch.setattr(services, '_demanda_ruta', lambda *_a, **_k: Path('libro.xlsx'))
    monkeypatch.setattr(dm, 'curvas_de_clientes', lambda _libro, codigos, mes=None: ({'900001': curva_cliente}, []))
    return services


def _fila(**kw):
    fila = {'codigo': '900001', 'sed': 'S1', 'pot': 1000.0, 'ea': 600000.0, 'eri': 150000.0,
            'p_registro_kw': 1000.0 / 0.3 * 0.3, 'q_registro_kvar': 250.0, 'p_kw': 1000.0, 'q_kvar': 250.0,
            'fecha_registro': '01/10/2026 12:00', 'fm_cambiado': _cambio_fm(),
            'valores': {'coincidente': {'p_kw': 1000.0, 'q_kvar': 250.0}, 'maximo_mes': None}}
    fila.update(kw)
    return fila


def test_039_rf24_la_web_registra_la_correccion_automatica_con_su_evidencia(monkeypatch):
    """039:RF-24 (a), RF-23 — al preparar el plan, la corrección deducida se registra en el espacio con origen
    «automatico», su motivo y su evidencia, y la fila del cliente va por el factor; ya no queda evidencia de exceso."""
    cabecera = _curva(2, lambda i: _diaria(i, 500.0, 80.0))
    cliente = _curva(2, lambda i: 1000.0 + _diaria(i, 0.0, 20.0))
    services = _parchear(monkeypatch, cliente)
    ws = _ws(curvas={'M1': {'curva': cabecera, 'alimentador': 'A1'}})
    fila = _fila()
    ev = services._evidencia_fijas(ws, 'J1', '2026-10', [fila], 'M1')
    assert 'supera_cabecera' not in ev.get('900001', {}), ev
    assert len(ws.correcciones_medidor) == 1, 'la corrección deducida no se registra'
    (corr,) = ws.correcciones_medidor
    assert corr.get('origen') == 'automatico' and corr['factor'] == pytest.approx(0.3) and corr['desde'] == '2026-10'
    assert corr['evidencia']['fm_anterior'] == 30.0 and corr['evidencia']['fm_actual'] == 100.0
    assert corr['evidencia']['registros_sobre_la_cabecera'] > 0 and corr['motivo']
    assert fila['p_kw'] == pytest.approx(300.0) and fila['ea'] == pytest.approx(180000.0)
    assert fila['valores']['coincidente']['p_kw'] == pytest.approx(300.0)
    assert fila['correccion_medidor']['origen'] == 'automatico'
    # La del operador manda: con una (aquí la anulación con factor 1), no se deduce otra y queda el exceso.
    ws2 = _ws(correcciones=[{'codigo': '900001', 'factor': 1.0, 'desde': '2026-10', 'origen': 'operador'}],
              curvas={'M1': {'curva': cabecera, 'alimentador': 'A1'}})
    fila2 = _fila()
    ev2 = services._evidencia_fijas(ws2, 'J1', '2026-10', [fila2], 'M1')
    assert len(ws2.correcciones_medidor) == 1 and ev2['900001']['supera_cabecera']['registros'] > 0
    assert ev2['900001']['diagnostico']['accion'] == 'liberar_fija' and fila2['p_kw'] == 1000.0


def test_039_rf24_la_web_repara_el_registro_excluido_y_propone_la_reasignacion(monkeypatch):
    """039:RF-24 (b) y (c) — la fija que sale de un pico excluido va con la mediana local, dicho; la que cabe en otro
    alimentador del trabajo lleva la propuesta y su evidencia de exceso, para que el guion la libere."""
    cabecera = _curva(2, lambda i: _diaria(i, 500.0, 50.0))
    t_pico = datetime(2026, 10, 1, 12, 0)
    cliente = [(t, 2000.0 if t == t_pico else _diaria(i, 200.0, 20.0), 50.0) for i, (t, _k, _q)
               in enumerate(_curva(2, lambda i: 0.0))]
    services = _parchear(monkeypatch, cliente)
    ws = _ws(curvas={'M1': {'curva': cabecera, 'alimentador': 'A1'}})
    fila = _fila(fm_cambiado=None, p_registro_kw=2000.0, p_kw=2000.0)
    ev = services._evidencia_fijas(ws, 'J1', '2026-10', [fila], 'M1')
    assert (ev.get('900001') or {}).get('diagnostico', {}).get('accion') == 'excluir_registros', ev
    assert 'supera_cabecera' not in ev['900001']
    assert fila['registro_excluido']['kw'] == 2000.0 and fila['p_registro_kw'] < 500.0, fila
    assert not ws.correcciones_medidor

    cliente = _curva(2, lambda i: _diaria(i, 700.0, 30.0))
    services = _parchear(monkeypatch, cliente)
    ws = _ws(curvas={'M1': {'curva': cabecera, 'alimentador': 'A1'},
                     'M2': {'curva': _curva(2, lambda i: _diaria(i, 2000.0, 50.0)), 'alimentador': 'A2'}})
    fila = _fila(fm_cambiado=None)
    ev = services._evidencia_fijas(ws, 'J1', '2026-10', [fila], 'M1')
    assert ev['900001']['diagnostico']['accion'] == 'proponer_reasignacion'
    assert ev['900001']['supera_cabecera']['registros'] > 0 and fila['reasignacion_propuesta']['alimentador'] == 'A2'
