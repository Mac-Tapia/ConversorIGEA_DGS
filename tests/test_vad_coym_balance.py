"""Spec 108 T8 (VAD-A7): COyM del Anexo 7 y balance de potencia y energía del 6.10, con las decisiones de 28.

Dos empresas sintéticas, sorteadas con su semilla; el registro real de ``config/vad`` y ``config/normativa``. Ningún
número del TdR se escribe en las pruebas: se leen del registro.
"""
from __future__ import annotations

import ast
import json
import random
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.aplicacion.vad import balance as bal
from convertersmartgrid.aplicacion.vad import coym

RAIZ = Path(__file__).resolve().parents[1]
VAD = RAIZ / 'config' / 'vad'
NORMATIVA = RAIZ / 'config' / 'normativa'
EMPRESAS = {'EMPRESA_A': 20261115, 'EMPRESA_B': 644573672}
VENTAS_MT = ('(21)', '(22)', '(23)', '(24)', '(25)', '(26)')
VENTAS_BT = tuple(f'({n})' for n in range(32, 47))


@pytest.fixture
def reg():
    return cargar_registro(VAD, NORMATIVA)


@pytest.fixture
def formato():
    return bal.formato_vi(VAD / 'anexo2_formatos.json')


def _registro_editado(tmp_path, cambio):
    """Copia del registro con ``cambio(nombre_fichero, datos)`` aplicado a cada JSON de config/vad y config/normativa."""
    vad, norm = tmp_path / 'vad', tmp_path / 'normativa'
    shutil.copytree(VAD, vad)
    shutil.copytree(NORMATIVA, norm)
    for f in [*vad.glob('*.json'), *norm.glob('*.json')]:
        datos = json.loads(f.read_text(encoding='utf-8'))
        if cambio(f.name, datos):
            f.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return cargar_registro(vad, norm)


def _regla_en(datos, clave):
    for r in [*(datos.get('reglas') or ()), *(r for n in datos.get('normas') or () for r in n.get('reglas') or ())]:
        if r['clave'] == clave:
            return r
    return None


def _sistema_sintetico(rng: random.Random) -> dict[str, dict[str, float]]:
    """Filas de dato del A-VI de un sistema de distribución que cierra: lo que entra = ventas + pérdidas."""
    out = {}
    for magnitud, escala in (('energia_mwh', 1000.0), ('potencia_kw', 200.0)):
        f = {k: 0.0 for k in ('(1)', '(2)', '(3)', '(5)', '(8)', '(9)', '(10)', '(15)')}
        for k in VENTAS_MT + VENTAS_BT:
            f[k] = round(rng.uniform(0, 1) * escala, 3)
        f['(18)'] = round(rng.uniform(0.01, 0.05) * escala * 6, 3)
        f['(19)'] = round(rng.uniform(0.0, 0.02) * escala * 6, 3)
        f['(29)'] = round(rng.uniform(0.02, 0.08) * escala * 15, 3)
        f['(30)'] = round(rng.uniform(0.0, 0.03) * escala * 15, 3)
        f['(13)'] = round(rng.uniform(0, 0.1) * escala, 3)
        f['(14)'] = round(rng.uniform(0, 0.05) * escala, 3)
        salida = sum(f[k] for k in VENTAS_MT + VENTAS_BT + ('(18)', '(19)', '(29)', '(30)'))
        f['(12)'] = salida - f['(13)'] + f['(14)']
        out[magnitud] = f
    return out


def _empresa(nombre: str) -> dict[str, dict[str, dict[str, float]]]:
    rng = random.Random(EMPRESAS[nombre])
    return {f'{nombre}-S{k}': _sistema_sintetico(rng) for k in range(1, 1 + rng.randint(2, 4))}


def _maxima(sis):
    p = sis['potencia_kw']
    return p['(1)'] + p['(5)'] + p['(12)'] + p['(13)'] - p['(14)']


# -------------------------------------------------------------------------------------------------- balance
@pytest.mark.parametrize('empresa', sorted(EMPRESAS))
def test_el_balance_real_cierra_en_cada_sistema_y_tension(reg, formato, empresa):
    """108:RF-8 — con dos empresas sintéticas el balance cierra (entrada = ventas + pérdidas) en cada sistema, en
    energía y en potencia, contra la máxima medida, y da las pérdidas de MT y BT con los decimales del registro."""
    sistemas = _empresa(empresa)
    medidas = {n: _maxima(s) for n, s in sistemas.items()}
    res = bal.balance_real(sistemas, reg, formato, maximas_medidas=medidas)
    assert res.conforme, res.motivos
    assert sorted(res.sistemas) == sorted(sistemas)
    assert res.cierra
    decimales = reg.regla('vad.perdidas_estandar.expresion').regla.valor['decimales']
    for nombre, b in res.sistemas.items():
        assert set(b.cierre_interno) == set(bal.MAGNITUDES), nombre
        assert all(c['cierra'] for c in b.cierre_interno.values())
        assert b.cierre_medida.get('cierra') is True and 'diferencia_kw' in b.cierre_medida
        for magnitud in bal.MAGNITUDES:
            f = b.filas.get(magnitud, {})
            assert set(b.porcentajes.get(magnitud, {})) == {'MT', 'BT', 'total'}
            assert b.porcentajes[magnitud]['MT'] == round(f['(17)'] / f['(16)'] * 100, decimales)
            assert b.porcentajes[magnitud]['BT'] == round(f['(28)'] / f['(27)'] * 100, decimales)
            entrada = sistemas[nombre][magnitud]
            assert f['(16)'] == pytest.approx(entrada['(12)'] + entrada['(13)'] - entrada['(14)'])
    assert res.total is not None
    assert res.total.filas['energia_mwh']['(16)'] == pytest.approx(
        sum(b.filas['energia_mwh']['(16)'] for b in res.sistemas.values()))


def test_un_balance_que_no_cierra_lo_dice_con_su_diferencia(reg, formato):
    """108:RF-8 — si lo que entra no es ventas + pérdidas, (47) muestra la diferencia y el balance no cierra."""
    sistemas = _empresa('EMPRESA_A')
    nombre = sorted(sistemas)[0]
    exceso = 0.02 * sistemas[nombre]['energia_mwh']['(12)']
    sistemas[nombre]['energia_mwh']['(12)'] += exceso
    res = bal.balance_real(sistemas, reg, formato, maximas_medidas={n: _maxima(s) for n, s in sistemas.items()})
    assert not res.cierra
    b = res.sistemas.get(nombre)
    assert b is not None and 'energia_mwh' in b.cierre_interno
    assert b.cierre_interno['energia_mwh']['diferencia'] == pytest.approx(exceso)
    assert b.cierre_interno['energia_mwh']['cierra'] is False


def test_la_tolerancia_por_defecto_es_el_error_admisible_de_la_clase(reg):
    """108:RF-8, 108:RF-9 — decisión de 28: sin clase en el perfil, la de MT por defecto (marcada); con clase, la suya;
    el perfil la sustituye solo con sustento. Las cifras salen del registro (RM 496-2005, Tabla N° 01)."""
    tabla = reg.regla('medida.error_admisible_por_clase').regla.valor
    defecto = reg.regla('medida.clase_por_defecto_mt').regla.valor
    t = bal.tolerancia_cierre(reg)
    assert t.relativa == pytest.approx(tabla[defecto] / 100)
    assert f'clase {defecto}' in t.origen and 'por defecto' in t.origen and 'RM 496-2005' in t.origen
    assert t.origen.startswith('tolerancia por defecto: error admisible de la clase')
    otra = sorted(set(tabla) - {defecto})[0]
    t2 = bal.tolerancia_cierre(reg, clase=otra)
    assert t2.relativa == pytest.approx(tabla[otra] / 100) and 'por defecto en MT' not in t2.origen
    with pytest.raises(VadError, match='sustento'):
        bal.tolerancia_cierre(reg, relativa=0.01)
    t3 = bal.tolerancia_cierre(reg, relativa=0.01, sustento='medición con clase 1 declarada')
    assert t3.relativa == 0.01 and 'perfil' in t3.origen
    with pytest.raises(VadError, match='clase'):
        bal.tolerancia_cierre(reg, clase='9X')


def test_el_cierre_contra_la_medida_muestra_siempre_la_diferencia(reg, formato):
    """108:RF-8 — dentro del error admisible cierra; fuera, no; y la diferencia se da en los dos casos."""
    sistemas = _empresa('EMPRESA_B')
    nombre = sorted(sistemas)[0]
    p = _maxima(sistemas[nombre])
    tol = bal.tolerancia_cierre(reg)
    for factor, cierra in ((1 + tol.relativa / 2, True), (1 + tol.relativa * 2, False)):
        res = bal.balance_real({nombre: sistemas[nombre]}, reg, formato, maximas_medidas={nombre: p * factor})
        b = res.sistemas.get(nombre)
        assert b is not None and b.cierre_medida, res.huecos
        assert b.cierre_medida['cierra'] is cierra
        assert b.cierre_medida['diferencia_kw'] == pytest.approx(p - p * factor)
        assert b.cierre_medida['tolerancia'] == tol.origen
    res = bal.balance_real({nombre: sistemas[nombre]}, reg, formato)
    assert any('medida' in h for h in res.huecos)


def test_el_adaptado_solo_cambia_las_perdidas(reg, formato):
    """108:RF-8 — el adaptado cambia solo las pérdidas; las no estándar (47) quedan a la vista; la demanda máxima de
    MT y de BT sale del adaptado; cambiar una venta se rechaza."""
    sistemas = _empresa('EMPRESA_A')
    nombre = sorted(sistemas)[0]
    real = sistemas[nombre]
    estandar = {nombre: {m: {k: real[m][k] * 0.8 for k in bal.FILAS_PERDIDAS} for m in bal.MAGNITUDES}}
    res = bal.balance_adaptado({nombre: real}, estandar, reg, formato)
    assert res.conforme, res.motivos
    b = res.sistemas.get(nombre)
    assert b is not None and 'potencia_kw' in b.filas
    rebaja = sum(real['potencia_kw'][k] for k in bal.FILAS_PERDIDAS) * 0.2
    assert b.filas['potencia_kw'].get('(47)') == pytest.approx(rebaja)
    assert b.demanda_maxima == {'MT': b.filas['potencia_kw']['(16)'], 'BT': b.filas['potencia_kw']['(27)']}
    with pytest.raises(VadError, match='solo cambia las pérdidas'):
        bal.balance_adaptado({nombre: real}, {nombre: {'energia_mwh': {'(21)': 1.0}}}, reg, formato)


def test_una_regla_sin_cita_deja_el_balance_no_conforme(tmp_path, formato):
    """108:RF-8, 108:RF-10 — un parámetro sin cita deja el resultado no_conforme."""
    def quitar(nombre, datos):
        r = _regla_en(datos, 'vad.perdidas_estandar.expresion')
        if r is not None:
            r['cita_literal'] = ''
            return True
        return False
    reg = _registro_editado(tmp_path, quitar)
    sistemas = _empresa('EMPRESA_B')
    res = bal.balance_real(sistemas, reg, formato, maximas_medidas={n: _maxima(s) for n, s in sistemas.items()})
    assert not res.conforme
    assert any('vad.perdidas_estandar.expresion' in m for m in res.motivos)


def test_el_cuadro_20_se_coteja_con_el_formato_a_vi(tmp_path, formato):
    """108:RF-8 — el Cuadro N° 20 del registro y el A-VI coinciden fila a fila; una fila cambiada lo rompe."""
    def cambiar(nombre, datos):
        r = _regla_en(datos, 'vad.balance.cuadro20')
        if r is not None:
            r['valor']['filas'][40] = 'BT5X'
            return True
        return False
    reg = _registro_editado(tmp_path, cambiar)
    res = bal.balance_real(_empresa('EMPRESA_A'), reg, formato)
    assert any('Cuadro N° 20' in m for m in res.motivos)


def test_los_factores_de_incremento_con_sus_topes_y_su_combinacion(reg):
    """108:RF-8 — decisión P-6: topes del registro siempre; sin combinación declarada, hueco; las dos cifras."""
    topes = reg.regla('vad.perdidas_estandar.factores_incremento').regla.valor
    div, asi = topes['divergencia_cargas_max'], topes['asimetria_fases_max']
    f = {'divergencia': bal.Factor(div / 2, 'medición'), 'asimetria': bal.Factor(asi / 2, 'medición')}
    sin = bal.factores_incremento(100.0, f, reg)
    assert sin.aplicado is None and sin.huecos
    assert sin.suma == pytest.approx(100 * (1 + div / 2 + asi / 2))
    assert sin.producto == pytest.approx(100 * (1 + div / 2) * (1 + asi / 2))
    assert bal.factores_incremento(100.0, f, reg, combinacion='producto').aplicado == pytest.approx(sin.producto)
    assert bal.factores_incremento(100.0, f, reg, combinacion='suma').aplicado == pytest.approx(sin.suma)
    with pytest.raises(VadError, match='tope'):
        bal.factores_incremento(100.0, {'divergencia': bal.Factor(div * 1.01, 'x')}, reg, combinacion='suma')
    with pytest.raises(VadError, match='tope'):
        bal.factores_incremento(100.0, {'asimetria': bal.Factor(asi * 1.01, 'x')}, reg, combinacion='suma')
    with pytest.raises(VadError, match='medición'):
        bal.factores_incremento(100.0, {'armonicos': bal.Factor(0.01, 'x')}, reg, combinacion='suma')


# ------------------------------------------------------------------------------------------------------ COyM
def _unitarios(reg, moneda='S/'):
    cuadro = coym.componentes_del_cuadro(reg)
    return {c: coym.CostoUnitario(c, 10.0 + k, f'S/ /{u[-1]}', moneda, 'estudio propio 2025')
            for k, (c, u) in enumerate(sorted(cuadro.items()))}


@pytest.mark.parametrize('empresa', sorted(EMPRESAS))
def test_el_coym_tecnico_es_cantidad_por_costo_unitario_por_sistema_y_etapa(reg, empresa):
    """108:RF-8 — Σ cantidad adaptada × costo unitario estándar, por sistema y etapa; los componentes y las unidades
    son los del cuadro del registro; un componente sin costo unitario es un hueco nombrado y no suma."""
    rng = random.Random(EMPRESAS[empresa])
    cuadro = coym.componentes_del_cuadro(reg)
    assert len(cuadro) == len(reg.regla('vad.anexo7.parametros_de_calculo').regla.valor['cuadro_costo_unitario_estandar'])
    unit = _unitarios(reg)
    assert unit, 'el cuadro del Anexo 7 sale vacío'
    falta = sorted(unit)[0]
    del unit[falta]
    cantidades = {}
    esperado = {}
    for s in range(2):
        filas = []
        for comp, unidades in sorted(cuadro.items()):
            etapa = rng.choice(coym.ETAPAS)
            c = coym.Cantidad(comp, round(rng.uniform(1, 50), 3), unidades[-1], etapa)
            filas.append(c)
            if comp in unit:
                clave = (f'{empresa}-{s}', etapa)
                esperado[clave] = esperado.get(clave, 0.0) + c.valor * unit[comp].valor
        cantidades[f'{empresa}-{s}'] = filas
    res = coym.coym_tecnico(cantidades, unit, reg)
    assert res.conforme, res.motivos
    for (sistema, etapa), monto in esperado.items():
        assert res.por_sistema.get(sistema, {}).get(etapa, {}).get('S/') == pytest.approx(monto)
    assert res.totales.get('S/') == pytest.approx(sum(esperado.values()))
    assert any(falta in h for h in res.huecos)
    assert res.reglas.get('vad.anexo7.parametros_de_calculo')


def test_el_coym_sin_fuente_con_otra_unidad_o_fuera_del_cuadro_no_es_conforme(reg):
    """108:RF-8, 108:RF-9 — sin fuente, con otra unidad o fuera del cuadro: no conforme; dos monedas no se suman."""
    unit = _unitarios(reg)
    assert len(unit) >= 2, 'el cuadro del Anexo 7 sale vacío'
    comp = sorted(unit)[0]
    malo = dict(unit)
    malo[comp] = coym.CostoUnitario(comp, 1.0, unit[comp].unidad, 'S/', '')
    assert not coym.coym_tecnico({}, malo, reg).conforme
    malo[comp] = coym.CostoUnitario(comp, 1.0, 'S/ /litro', 'S/', 'x')
    assert not coym.coym_tecnico({}, malo, reg).conforme
    assert not coym.coym_tecnico({}, {'Inventado': coym.CostoUnitario('Inventado', 1, 'S/ /km', 'S/', 'x')},
                                 reg).conforme
    cuadro = coym.componentes_del_cuadro(reg)
    a, b = sorted(cuadro)[:2]
    mix = {a: coym.CostoUnitario(a, 2.0, f'S/ /{cuadro[a][-1]}', 'S/', 'x'),
           b: coym.CostoUnitario(b, 3.0, f'USD/{cuadro[b][-1]}', 'USD', 'x')}
    res = coym.coym_tecnico({'s': [coym.Cantidad(a, 1.0, cuadro[a][-1], 'MT'),
                                   coym.Cantidad(b, 1.0, cuadro[b][-1], 'MT')]}, mix, reg)
    assert res.totales == {'S/': 2.0, 'USD': 3.0}


def test_las_cantidades_salen_de_la_red_dimensionada(reg):
    """108:RF-8 — km por nivel con conductor de la empresa modelo, SED y kVA; el componente de red lo declara el
    perfil y sin él no se adivina."""
    cuadro = coym.componentes_del_cuadro(reg)
    por_km = sorted(c for c, u in cuadro.items() if 'km' in u)
    assert len(por_km) >= 2, 'el cuadro del Anexo 7 no trae componentes por km'
    tr = lambda t, n, c: SimpleNamespace(tramo=t, alimentador='A1', nivel=n, conductor_modelo=c)  # noqa: E731
    dim = SimpleNamespace(
        modelo=SimpleNamespace(tramos=[SimpleNamespace(tramo='t1', longitud_m=1500.0),
                                       SimpleNamespace(tramo='t2', longitud_m=500.0),
                                       SimpleNamespace(tramo='t3', longitud_m=900.0)]),
        tramos=[tr('t1', 'MT', 'AAAC 35'), tr('t2', 'MT', None), tr('t3', 'BT', 'CAAI 16')],
        sed=[SimpleNamespace(alimentador='A1', kva_modelo=25.0), SimpleNamespace(alimentador='A1', kva_modelo=50.0),
             SimpleNamespace(alimentador='A1', kva_modelo=None)])
    out = coym.cantidades_de_dimensionamiento(dim, componente_red={'MT': por_km[0], 'BT': por_km[1]}, registro=reg)
    filas = {(c.componente, c.unidad): c.valor for c in out.get('A1', [])}
    assert filas.get((por_km[0], 'km')) == pytest.approx(1.5)
    assert filas.get((por_km[1], 'km')) == pytest.approx(0.9)
    assert sorted(v for (c, u), v in filas.items() if u in ('subestación', 'kVA')) == [2.0, 75.0]
    with pytest.raises(VadError, match='no declara'):
        coym.cantidades_de_dimensionamiento(dim, componente_red={'MT': por_km[0]}, registro=reg)


def test_los_costos_excluidos_y_los_sin_contrato(reg):
    """108:RF-8 — la lista cerrada del registro excluye; sin contrato no se toma el monto, sin desconocer la actividad."""
    excluido = reg.regla('vad.anexo7.costos_excluidos').regla.valor[0]
    partidas = [coym.Partida('poda', 'servicios contratados', 100.0, 'S/', 'libro', tercerizada=True, contrato='C-1'),
                coym.Partida('fee', excluido.upper(), 50.0, 'S/', 'libro'),
                coym.Partida('lectura', 'servicios contratados', 30.0, 'S/', 'libro', tercerizada=True)]
    res = coym.depurar_partidas(partidas, reg)
    assert [p.concepto for p in res.admitidas] == ['poda']
    assert [p.concepto for p, _ in res.excluidas] == ['fee']
    assert [p.concepto for p, _ in res.sin_monto] == ['lectura']
    assert res.total() == {'S/': 100.0}
    assert all('Anexo N° 7' in m for _, m in res.excluidas + res.sin_monto)


def test_el_tope_salarial_toma_el_real_si_la_encuesta_lo_excede(reg):
    """108:RF-8 — el costo anual por empleado de la encuesta no excede el real de la empresa de referencia."""
    res = coym.tope_salarial({'técnicos': (60000.0, 50000.0), 'jefes': (90000.0, 95000.0)}, reg)
    assert res.costo == {'jefes': 90000.0, 'técnicos': 50000.0}
    assert set(res.recortadas) == {'técnicos'} and res.avisos


def test_el_cct_con_tasa_diaria_efectiva_su_contraste_y_la_errata(reg):
    """108:RF-8 — decisión P-4: tasa diaria efectiva; la proporcional, contraste; la errata del num. 5.12."""
    inicio = date(2026, 11, 1)
    dias = coym.dias_del_periodo(inicio)
    rng = random.Random(7)
    saldos = [rng.uniform(-1000, 500) for _ in dias]
    tasa = reg.regla('vad.anexo7.capital_de_trabajo').regla.valor['tasa_interes']
    i_d = (1 + tasa) ** (1 / 365) - 1
    esperado = sum(max(0, -s) * i_d * (1 + i_d) ** (len(saldos) - 1 - k) for k, s in enumerate(saldos))
    res = coym.capital_de_trabajo(saldos, reg, inicio=inicio)
    assert res.conforme, res.motivos
    assert res.cct == pytest.approx(esperado, rel=1e-12)
    i_p = tasa / 365
    assert res.contraste == pytest.approx(sum(max(0, -s) * i_p * (1 + i_p) ** (len(saldos) - 1 - k)
                                              for k, s in enumerate(saldos)), rel=1e-12)
    assert any('numeral 12 del Anexo 7' in a and 'numeral 11' in a and '1215' in a and '7437' in a
               for a in res.avisos)
    with pytest.raises(VadError, match='sustento'):
        coym.capital_de_trabajo(saldos, reg, inicio=inicio, conversion='proporcional')
    prop = coym.capital_de_trabajo(saldos, reg, inicio=inicio, conversion='proporcional', sustento='perfil X')
    assert prop.cct == pytest.approx(res.contraste) and prop.contraste == pytest.approx(res.cct)
    with pytest.raises(VadError, match='saldos'):
        coym.capital_de_trabajo(saldos[:-1], reg, inicio=inicio)


def test_los_costos_compartidos_manda_el_tdr_con_aviso_y_el_hueco_a7_4(reg):
    """108:RF-8, 108:RF-9 — decisión de 28: manda el TdR, con el aviso frente al Manual vigente (las dos citas), el
    hueco A7-4 y la base del tope P-5."""
    v = reg.regla('vad.anexo7.costos_compartidos').regla.valor
    g, base = 1000.0, 2000.0
    res = coym.costos_compartidos(g, reg, avnr_periodo=base, vnr=30000.0, vida_util=30)
    tope = v['tope_sobre_inversion'] * base
    assert res.a_inversiones == pytest.approx(min(v['organos_de_gobierno_a_inversiones'] * g, tope))
    exceso = v['organos_de_gobierno_a_inversiones'] * g - tope
    assert exceso > 0
    # v3 (c3): el caso real. El exceso no lo asigna ninguna regla de este ámbito: hueco nombrado, sin asignar; la Nota 2
    # del Manual se cita como de otro ámbito, sin extenderla.
    assert res.al_servicio == pytest.approx(v['organos_de_gobierno_al_servicio'] * g)
    assert res.sin_asignar == pytest.approx(exceso)
    assert any('exceso' in h and 'hueco' in h and coym.REGLA_EXCESO in h for h in res.huecos)
    nota = reg.regla('manual_costos.formato_3_2.nota_2')
    gastos = reg.regla('manual_costos.costos_indirectos.imputacion').regla.valor['gastos']
    aviso = [a for a in res.avisos if 'Nota 2' in a]
    assert aviso and nota.regla.lineas in aviso[0] and nota.norma.acto in aviso[0]
    assert 'otro ámbito' in aviso[0] and 'no se extiende' in aviso[0] and all(x in aviso[0] for x in gastos)
    assert res.tope == pytest.approx(tope) and 'aVNR' in res.base_origen
    discrepancia = [a for a in res.avisos if 'Manual' in a and 'manda el TdR' in a]
    assert discrepancia and 'RCD 218-2020-OS/CD' in discrepancia[0] and 'RCD 249-2022-OS/CD' in discrepancia[0]
    assert 'no está en el Manual vigente' in discrepancia[0]
    assert 'inversión efectuada en el ejercicio' in discrepancia[0] and 'inversión analizada' in discrepancia[0]
    assert any('contraste' in a and 'VNR/vida útil' in a for a in res.avisos)
    assert any(h.startswith('A7-4') and '197-94' in h for h in res.huecos)
    sin = coym.costos_compartidos(g, reg)
    assert sin.a_inversiones is None and any('base del tope' in h for h in sin.huecos)
    with pytest.raises(VadError, match='sustento'):
        coym.costos_compartidos(g, reg, base_tope=5000.0)
    perfil = coym.costos_compartidos(g, reg, base_tope=5000.0, sustento_base='inversión anual del PIDE')
    assert 'perfil' in perfil.base_origen and perfil.base == 5000.0


def test_el_hueco_a7_4_cita_la_regla_de_reg_huecos_cuando_esta(tmp_path):
    """108:RF-9 — con la regla vad.anexo7.manual_costos de REG-HUECOS v4 (manda el TdR, sin «numeral 5.1»), el hueco
    A7-4 la cita y dice quién manda, lo mismo que el aviso de la discrepancia: los dos textos cuadran."""
    def anadir(nombre, datos):
        if nombre == 'anexo7_coym.json':
            datos['reglas'].append({'clave': 'vad.anexo7.manual_costos',
                                    'valor': {'cita_tdr': 'RM 197-94-EM/VME', 'texto_cita_tdr': 'no_hallado',
                                              'hueco': 'A7-4', 'manda': 'el TdR del VAD 2026-2030 (Anexo 7)'},
                                    'articulo_o_anexo': 'num. 4 (Formatos IV-1 y IV-4 «Costos Combinados» del Anexo N° 2)',
                                    'pagina': 'impresa 27, pdf 28', 'lineas': '1340-1344',
                                    'cita_literal': 'aprobado por Resolución Ministerial 197-94-EM/VME.'})
            return True
        return False
    reg = _registro_editado(tmp_path, anadir)
    res = coym.costos_compartidos(1000.0, reg, avnr_periodo=2000.0)
    a74 = [h for h in res.huecos if h.startswith('A7-4')]
    assert a74 and '1340-1344' in a74[0] and 'manda el TdR del VAD 2026-2030 (Anexo 7)' in a74[0]
    assert any('manda el TdR' in a for a in res.avisos)
    assert not any('numeral 5.1 del Manual vigente' in t for t in res.avisos + res.huecos)


def test_con_una_regla_citada_de_su_ambito_el_exceso_se_asignaria(reg, tmp_path):
    """108:RF-8, 108:RF-9 — c3 (v3): con una regla citada del ámbito del TdR (vad.anexo7.costos_compartidos.exceso, en
    una copia del registro) el código asigna el exceso al servicio y la cita; sin exceso no hay hueco; un destino que
    no es «servicio» se rechaza. La Nota 2 del Manual no la sustituye: hoy no existe esa regla y es hueco."""
    with pytest.raises(Exception):
        reg.regla(coym.REGLA_EXCESO)

    def anadir(destino):
        def cambio(nombre, datos):
            if nombre == 'anexo7_coym.json':
                datos['reglas'].append({'clave': coym.REGLA_EXCESO, 'valor': {'destino': destino},
                                        'articulo_o_anexo': 'regla sintética de la prueba', 'pagina': '1',
                                        'lineas': '1-2', 'cita_literal': 'cita sintética'})
                return True
            return False
        return cambio
    con = _registro_editado(tmp_path / 'a', anadir('servicio'))
    v = con.regla('vad.anexo7.costos_compartidos').regla.valor
    g, base = 1000.0, 2000.0
    res = coym.costos_compartidos(g, con, avnr_periodo=base)
    exceso = v['organos_de_gobierno_a_inversiones'] * g - v['tope_sobre_inversion'] * base
    assert exceso > 0
    assert res.al_servicio == pytest.approx(v['organos_de_gobierno_al_servicio'] * g + exceso)
    assert res.sin_asignar == 0.0 and not any('exceso' in h for h in res.huecos)
    assert any('exceso' in a and 'cita sintética' in a for a in res.avisos)
    assert coym.REGLA_EXCESO in res.reglas
    with pytest.raises(VadError, match='destino'):
        coym.costos_compartidos(g, _registro_editado(tmp_path / 'b', anadir('inversiones')), avnr_periodo=base)
    holgado = coym.costos_compartidos(g, reg, avnr_periodo=base * 100)
    assert holgado.sin_asignar == 0.0 and not any('exceso' in h for h in holgado.huecos)


def test_la_potencia_resultante_sale_de_la_regla_citada_del_a_vi(reg, formato, tmp_path):
    """108:RF-8, 108:RF-9 — c3 (v2): la potencia resultante del balance real son los términos de
    vad.balance.potencia_resultante, cada uno una fila del A-VI con su nombre y su cita literal (página y líneas)."""
    v = reg.regla('vad.balance.potencia_resultante')
    assert v.obligatoria and v.regla.pagina and v.regla.lineas
    nombres = {c.id: c.nombre for c in formato.filas}
    terminos = v.regla.valor['terminos']
    assert [t['fila'] for t in terminos] == ['(1)', '(5)', '(12)', '(13)', '(14)']
    for t, linea in zip(terminos, v.regla.lineas.split(';')):
        assert nombres[t['fila']] == t['nombre'] and t['fila'] in v.regla.cita_literal
        assert t['nombre'] in v.regla.cita_literal and linea.strip().isdigit()
    sistemas = _empresa('EMPRESA_A')
    nombre = sorted(sistemas)[0]
    p = sistemas[nombre]['potencia_kw']
    esperado = sum(t['signo'] * p[t['fila']] for t in terminos)
    res = bal.balance_real({nombre: sistemas[nombre]}, reg, formato, maximas_medidas={nombre: esperado})
    b = res.sistemas.get(nombre)
    assert b is not None and b.cierre_medida.get('resultante_kw') == pytest.approx(esperado)
    assert any('potencia resultante' in a and v.regla.lineas in a for a in res.avisos)

    def sin_consumo(nombre_f, datos):
        r = _regla_en(datos, 'vad.balance.potencia_resultante')
        if r is not None:
            r['valor']['terminos'] = [t for t in r['valor']['terminos'] if t['fila'] != '(14)']
            return True
        return False
    otro = bal.balance_real({nombre: sistemas[nombre]}, _registro_editado(tmp_path / 'a', sin_consumo), formato,
                            maximas_medidas={nombre: esperado})
    b2 = otro.sistemas.get(nombre)
    assert b2 is not None and b2.cierre_medida.get('resultante_kw') == pytest.approx(esperado + p['(14)'])

    def mal_nombre(nombre_f, datos):
        r = _regla_en(datos, 'vad.balance.potencia_resultante')
        if r is not None:
            r['valor']['terminos'][0]['nombre'] = 'Ingreso a AT'
            return True
        return False
    malo = bal.balance_real({nombre: sistemas[nombre]}, _registro_editado(tmp_path / 'b', mal_nombre), formato,
                            maximas_medidas={nombre: esperado})
    assert not malo.conforme and any('potencia_resultante' in m for m in malo.motivos)


def test_ninguna_cifra_del_tdr_esta_en_el_codigo(reg):
    """108:RF-13 — las cifras del Anexo 7 y del 6.9/6.10 (y la tabla de clases) viven en el registro, no en el
    código: ningún literal numérico de coym.py ni de balance.py es una de ellas."""
    cifras = set()
    for clave in ('vad.anexo7.costos_compartidos', 'vad.anexo7.capital_de_trabajo',
                  'vad.perdidas_estandar.factores_incremento'):
        cifras |= {x for x in reg.regla(clave).regla.valor.values() if isinstance(x, float)}
    cifras |= {float(x) for x in reg.regla('medida.error_admisible_por_clase').regla.valor.values()}
    assert len(cifras) >= 6
    for modulo in (coym, bal):
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding='utf-8'))
        literales = {n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant)
                     and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)}
        assert not (literales & cifras), (modulo.__name__, literales & cifras)
    assert 'def coym_tecnico' in Path(coym.__file__).read_text(encoding='utf-8')
