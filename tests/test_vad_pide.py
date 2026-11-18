"""Spec 108 T17 — incorporación del PIDE aprobado al VAD, contrato 072 → 108 (108:RF-17, RF-16).

El PIDE de prueba es sintético (niveles «N1» y «N2», moneda «XUS»); la fórmula, la tasa, el factor y los años salen
de un registro sintético o del registro real. Los valores esperados se calculan a mano.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from convertersmartgrid.dominio import registro_normativo as rn
from convertersmartgrid.dominio.perfil_empresa import PerfilEmpresa
from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.dominio import util
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.aplicacion.vad.estudio import cargar_estudio, crear_estudio
from convertersmartgrid.aplicacion.vad.pide_vad import CONTRATO, VadNivel, incorporar_pide, pide_desde_dict

RAIZ = Path(__file__).resolve().parents[1]
FORMULA = ('(aVNR0 + OyM0 + suma(n, aDVNR / (1 + i) ** (n - 1) + DOyM / 2)) / '
           '(POT0 + suma(n, DPOT / (1 + i) ** (n - 1)))')


def _registro(tmp_path, estado='vigente_comprobada', sin=(), anios=2):
    reglas = [{'clave': c, 'valor': v, 'cita_literal': f'«{c}»', 'lineas': '1'} for c, v in (
        ('vad.frc', 1.25), ('vad.vida_util_anios', 1), ('vad.tasa_actualizacion', 0.25), ('vad.pide.anios', anios),
        ('vad.formula.pide_ajustado', FORMULA)) if c not in sin]
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': estado, 'sha256': 'c' * 64,
        'vigencia_desde': '2001-01-01', 'reglas': reglas}]}
    ruta = tmp_path / 'reg' / 'tdr.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(ruta.parent)


def _pide(**cambios):
    datos = {'contrato': CONTRATO, 'id': 'pide-sintetico-1', 'estado': 'aprobado', 'acto_aprobacion': 'rcd-sintetica',
             'periodo': '2041-2045', 'moneda': 'XUS', 'huella': 'd' * 64,
             'niveles': {'N1': {'inversion': [40.0, 20.0], 'oym': [2.0, 4.0], 'demanda': [1.0, 2.5]}}}
    datos.update(cambios)
    return pide_desde_dict(datos)


BASE = {'N1': VadNivel(anualidad=100.0, oym=10.0, demanda=10.0)}
KW = {'ambito_fonafe': True, 'periodo': '2041-2045', 'moneda': 'XUS'}


def test_sin_pide_aprobado_avisa_y_no_incorpora_nada(tmp_path):
    """108:RF-17 — en el ámbito del FONAFE y sin PIDE aprobado, se avisa y no se incorpora nada."""
    reg = _registro(tmp_path)
    for pide in (None, _pide(estado='prepublicado')):
        r = incorporar_pide(reg, BASE, pide, **KW)
        assert not r.incorporado and not r.vad_ajustado and r.avisos
    assert 'no hay PIDE aprobado' in incorporar_pide(reg, BASE, None, **KW).avisos[0]
    assert 'prepublicado' in incorporar_pide(reg, BASE, _pide(estado='prepublicado'), **KW).avisos[0]


def test_ambito_sin_declarar_avisa_y_fuera_del_fonafe_no_incorpora(tmp_path):
    """108:RF-17 — el ámbito sin declarar no se supone: aviso y nada; fuera del FONAFE no se incorpora y no avisa."""
    reg = _registro(tmp_path)
    sin = incorporar_pide(reg, BASE, _pide(), ambito_fonafe=None, periodo='2041-2045', moneda='XUS')
    assert not sin.incorporado and 'FONAFE' in sin.avisos[0]
    fuera = incorporar_pide(reg, BASE, _pide(), ambito_fonafe=False, periodo='2041-2045', moneda='XUS')
    assert not fuera.incorporado and not fuera.avisos


def test_caso_calculado_a_mano(tmp_path):
    """108:RF-17, 108:RF-16 — con el PIDE aprobado, el VAD ajustado sale de la fórmula, la tasa y el factor del
    registro, y coincide con el cálculo a mano; guarda el PIDE usado y las huellas de las reglas."""
    r = incorporar_pide(_registro(tmp_path), BASE, _pide(), **KW)
    # FRC(25 %, 1 año) = 0,25 × 1,25 / 0,25 = 1,25; aΔVNR = inversión × 1,25 = [50, 25]; descuento (1,25)^(n-1) = [1, 1,25].
    numerador = 100 + 10 + (50 / 1 + 2 / 2) + (25 / 1.25 + 4 / 2)
    denominador = 10 + 1.0 / 1 + 2.5 / 1.25
    assert r.incorporado and r.vad_ajustado['N1'] == pytest.approx(numerador / denominador)
    assert r.pide == {'id': 'pide-sintetico-1', 'acto_aprobacion': 'rcd-sintetica', 'huella': 'd' * 64}
    assert set(r.reglas) == {'vad.frc', 'vad.vida_util_anios', 'vad.tasa_actualizacion', 'vad.pide.anios',
                             'vad.formula.pide_ajustado'}
    assert not r.avisos


def test_nivel_sin_inversion_queda_con_su_vad_base_y_se_dice(tmp_path):
    """108:RF-17 — un nivel del VAD que el PIDE no trae no se ajusta y se avisa."""
    base = dict(BASE, N2=VadNivel(50.0, 5.0, 5.0))
    r = incorporar_pide(_registro(tmp_path), base, _pide(), **KW)
    assert r.incorporado and set(r.vad_ajustado) == {'N1'} and 'N2' in r.avisos[0]


@pytest.mark.parametrize('cambio,texto', [({'periodo': '2046-2050'}, 'periodo'), ({'moneda': 'XPE'}, 'monedas')])
def test_otro_periodo_u_otra_moneda_no_se_incorporan(tmp_path, cambio, texto):
    """108:RF-17 — un PIDE de otro periodo o en otra moneda no se incorpora."""
    r = incorporar_pide(_registro(tmp_path), BASE, _pide(**cambio), **KW)
    assert not r.incorporado and texto in r.avisos[0]


def test_registro_incompleto_o_que_no_obliga_no_incorpora(tmp_path):
    """108:RF-17, 108:RF-10 — sin la fórmula registrada, con otro número de años o con el TdR sin comprobar no se
    incorpora nada."""
    sin_formula = incorporar_pide(_registro(tmp_path, sin=('vad.formula.pide_ajustado',)), BASE, _pide(), **KW)
    assert not sin_formula.incorporado and 'vad.formula.pide_ajustado' in sin_formula.avisos[0]
    tres = incorporar_pide(_registro(tmp_path, anios=3), BASE, _pide(), **KW)
    assert not tres.incorporado and 'pide 3' in tres.avisos[0]
    prepub = incorporar_pide(_registro(tmp_path, estado='prepublicada'), BASE, _pide(), **KW)
    assert not prepub.incorporado and 'no obligan' in prepub.avisos[0]


def test_niveles_que_sobran_o_demanda_cero(tmp_path):
    """108:RF-17 — un nivel del PIDE que el VAD no tiene, o un denominador 0, no se incorporan y se dice por qué."""
    reg = _registro(tmp_path)
    otro = _pide(niveles={'N9': {'inversion': [1, 1], 'oym': [1, 1], 'demanda': [1, 1]}})
    assert 'N9' in incorporar_pide(reg, BASE, otro, **KW).avisos[0]
    cero = _pide(niveles={'N1': {'inversion': [1, 1], 'oym': [1, 1], 'demanda': [0, 0]}})
    r = incorporar_pide(reg, {'N1': VadNivel(1.0, 1.0, 0.0)}, cero, **KW)
    assert not r.incorporado and 'cero' in r.avisos[0]


@pytest.mark.parametrize('cambio,texto', [
    ({'contrato': 'otro'}, 'contrato'), ({'acto_aprobacion': ''}, 'acto_aprobacion'),
    ({'periodo': '2041'}, 'AAAA-AAAA'), ({'huella': 'xyz'}, 'sha256'), ({'niveles': {}}, 'ningún nivel'),
    ({'niveles': {'N1': {'inversion': [1], 'oym': [1, 2], 'demanda': [1]}}}, 'distinto número'),
    ({'niveles': {'N1': {'inversion': [-1], 'oym': [1], 'demanda': [1]}}}, 'no negativo'),
    ({'niveles': {'N1': {'inversion': [], 'oym': [], 'demanda': []}}}, 'lista'),
])
def test_contrato_invalido_se_rechaza_con_mensaje(cambio, texto):
    """108:RF-17 — lo que la 072 entrega fuera del contrato se rechaza nombrando el campo."""
    with pytest.raises(VadError, match=texto):
        _pide(**cambio)


def test_con_el_registro_real(tmp_path):
    """108:RF-17 — con el registro real (la tasa del art. 79 de la LCE a la que remite el TdR, su vida útil, sus años y
    su fórmula) el VAD ajustado coincide con el cálculo a mano para los años que pide el registro, y el FRC calculado
    cuadra a 6 decimales con el que publica el TdR, sin aviso."""
    reg = cargar_registro(RAIZ / 'config' / 'vad', RAIZ / 'config' / 'normativa')
    anios = reg.regla('vad.pide.anios').regla.valor
    assert hasattr(rn, 'regla_remitida'), 'el registro no resuelve la remisión de vad.tasa_actualizacion'
    i = rn.regla_remitida(reg, 'vad.tasa_actualizacion').valor
    assert hasattr(util, 'frc'), 'el FRC no sale de la única fórmula del conversor (util.frc)'
    frc = util.frc(i, reg.regla('vad.vida_util_anios').regla.valor)
    assert round(frc, 6) == reg.regla('vad.frc').regla.valor
    pide = _pide(niveles={'N1': {'inversion': [100.0] * anios, 'oym': [4.0] * anios, 'demanda': [1.0] * anios}})
    r = incorporar_pide(reg, BASE, pide, **KW)
    descuento = [(1 + i) ** (n - 1) for n in range(1, anios + 1)]
    num = 100 + 10 + sum(100 * frc / d + 4 / 4 for d in descuento)
    den = 10 + sum(1 / d for d in descuento)
    assert r.incorporado and r.vad_ajustado['N1'] == pytest.approx(num / den) and not r.avisos


@pytest.mark.parametrize('nombre', ['Distribuidora Sintética Norte', 'Eléctrica Ficticia del Sur'])
def test_el_estudio_guarda_el_ambito_declarado(tmp_path, nombre):
    """108:RF-17, 108:RF-1 — el estudio guarda si la empresa está en el ámbito del FONAFE; sin declararlo queda None y
    la incorporación avisa; un valor que no es booleano se rechaza."""
    espacio = tmp_path / 'espacio'
    declarado = crear_estudio(espacio, PerfilEmpresa(nombre=nombre), grupo=2, periodo='2041-2045',
                              version_tdr='tdr-sintetico', ambito_fonafe=True)
    assert cargar_estudio(espacio, declarado.id).ambito_fonafe is True
    sin = crear_estudio(tmp_path / 'otro', PerfilEmpresa(nombre=nombre), grupo=2, periodo='2041-2045',
                        version_tdr='tdr-sintetico')
    assert sin.ambito_fonafe is None
    r = incorporar_pide(_registro(tmp_path), BASE, _pide(), ambito_fonafe=sin.ambito_fonafe, periodo=sin.periodo,
                        moneda='XUS')
    assert not r.incorporado and 'FONAFE' in r.avisos[0]
    with pytest.raises(VadError, match='ambito_fonafe'):
        crear_estudio(tmp_path / 'malo', PerfilEmpresa(nombre=nombre), grupo=2, periodo='2041-2045',
                      version_tdr='tdr-sintetico', ambito_fonafe='sí')
