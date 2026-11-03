"""Spec 081: ningún elemento con más fases que su barra, en cualquier fuente; nada se rechaza."""
from __future__ import annotations

from dataclasses import replace

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.comprobacion_fases import (
    MAS_FASES, NO_LLEGAN, Barra, Elemento, comprobar, comprobar_modelo, reconstruir_bancos, ubicar_nuevo,
)
from convertersmartgrid.model import CapacitorBank, Coupler, FeederModel, Line, Load, Sed
from convertersmartgrid.reglas import SIN_REGLAS, aplicar_reglas


def _linea(i, a, b, fase):
    return Line(i, a, b, fase, 'T', 'T', 1.0, True)


def _modelo(lineas, *, cargas=(), seds=(), bancos=(), acopladores=()):
    return FeederModel(name='F', network_id='F', nominal_kv=10.0, source_node='H', nodes={}, lines=list(lineas),
                       loads=list(cargas), devices=[], line_types={}, seds=list(seds), capacitors=list(bancos),
                       couplers=list(acopladores))


def _banco(nodo, fases):
    return CapacitorBank('B1', nodo, 'F', 'F', fases, 150.0, 2, 300.0, 10.0, True)


def _sed(codigo, nodo, fase):
    carga = Load(codigo, codigo, '', '', nodo, .01, 0., 1., 10., 0., fase, sed_code=codigo)
    return carga, Sed(codigo, codigo, nodo, 10.0, codigo, codigo, (codigo, codigo))


@pytest.mark.parametrize('clase', ['acoplador', 'banco', 'carga', 'transformador', 'tramo', 'regulador'])
def test_toda_clase_con_mas_fases_que_su_barra(clase):
    """081:RF-1, 081:RF-3 — es la clase entera de fallos y no un caso: cualquier elemento, con su barra y sus fases."""
    barras = {'B': Barra('B', 2, 'AB'), 'C': Barra('C', 3, 'ABC')}
    informe = comprobar([Elemento(clase, 'E', ('C', 'B'), 3, 'ABC'), Elemento(clase, 'BIEN', ('B',), 2, 'AB')], barras)
    assert [h.tipo for h in informe.hallazgos] == [MAS_FASES]
    h = informe.hallazgos[0]
    assert (h.clase, h.nombre, h.barra) == (clase, 'E', 'B') and '3 fases' in h.linea() and 'lleva 2' in h.linea()
    assert informe.conteo == {clase: 1} and informe.as_dict()['total'] == 1 and f'1 {clase}' in informe.resumen()


def test_fases_que_no_llegan_desde_la_cabecera():
    """081:RF-2, 081:RF-6 — el fallo real: una SED de fase C en un ramal que solo lleva AB, sobre el modelo común."""
    carga, sed = _sed('S1', 'N2', 'C')
    bien, sed_bien = _sed('S2', 'N2', 'A')
    m = _modelo([_linea('T0', 'H', 'N1', 'ABC'), _linea('R1', 'N1', 'N2', 'AB')], cargas=[carga, bien], seds=[sed, sed_bien])
    informe = comprobar_modelo(m)
    assert [(h.tipo, h.clase, h.nombre) for h in informe.hallazgos] == [(NO_LLEGAN, 'transformador', 'S1')]
    assert 'le llegan AB' in informe.hallazgos[0].linea()


def test_acoplador_entre_barras_sin_fases_comunes():
    """081:RF-1 — el acoplador toma las comunes de sus barras (054:RF-3): sin ninguna común, se dice."""
    def acoplador(a, b):
        return Coupler('A1', a, b, 1, 'swt', '', '', 'S', '')

    m = _modelo([_linea('T0', 'H', 'N1', 'ABC'), _linea('R1', 'N1', 'N2', 'A'), _linea('R2', 'N1', 'N3', 'B')],
                acopladores=[acoplador('N2', 'N3')])
    assert [(h.clase, h.nombre) for h in comprobar_modelo(m).hallazgos] == [('acoplador', 'A1')]
    bien = _modelo([_linea('T0', 'H', 'N1', 'ABC'), _linea('R1', 'N1', 'N2', 'A')], acopladores=[acoplador('N1', 'N2')])
    assert comprobar_modelo(bien).hallazgos == []


def test_el_banco_de_la_fuente_toma_las_fases_de_su_barra():
    """081:RF-5 — el DGS no mira los bancos al decidir la barra: este salía trifásico y DIgSILENT no calculaba nada."""
    m = _modelo([_linea('T0', 'H', 'N1', 'ABC'), _linea('R1', 'N1', 'N2', 'AB')], bancos=[_banco('N2', 'ABC')])
    assert [h.clase for h in comprobar_modelo(m).hallazgos] == ['banco']
    informe = aplicar_reglas(m, replace(SIN_REGLAS, reconstruir_fases=True))
    banco = m.capacitors[0]
    assert banco.phases == 'AB' and banco.total_kvar == 300.0 and banco.steps == 2
    assert 'FASE_RECONSTRUIDA' in informe['fases_reconstruidas'][0] and 'ABC → AB' in informe['fases_reconstruidas'][0]
    assert any('FASE_RECONSTRUIDA' in a for a in m.warnings)
    assert comprobar_modelo(m).hallazgos == []
    from convertersmartgrid.dgs import _capacitor_technology

    assert _capacitor_technology(banco.phases)[0] == 3         # el DGS le da la tecnología de dos fases
    # Una vez reconstruido, repetir no cambia nada.
    assert reconstruir_bancos(m) == []
    # Con otra fase de las mismas: la que su barra lleva.
    otro = _modelo([_linea('T0', 'H', 'N1', 'ABC'), _linea('R1', 'N1', 'N2', 'AB')], bancos=[_banco('N2', 'C')])
    reconstruir_bancos(otro)
    assert otro.capacitors[0].phases == 'A'


def test_lo_que_cuadra_no_cambia_nada():
    """081:RF-7 — sin hallazgos, el modelo y el informe de reglas quedan como estaban (el DGS no se entera)."""
    carga, sed = _sed('S1', 'N1', 'ABC')
    m = _modelo([_linea('T0', 'H', 'N1', 'ABC')], cargas=[carga], seds=[sed], bancos=[_banco('N1', 'ABC')])
    antes = list(m.capacitors)
    informe = aplicar_reglas(m, replace(SIN_REGLAS, reconstruir_fases=True))
    assert informe == {} and m.capacitors == antes and m.warnings == [] and comprobar_modelo(m).hallazgos == []


def test_el_preflight_lo_dice_y_la_importacion_sigue(tmp_path, monkeypatch):
    """081:RF-4, 081:RF-3 — lo que no cuadra no impide importar: va al Registro y al informe, por elemento."""
    from types import SimpleNamespace

    from convertersmartgrid import oraculo, preflight_contract
    from convertersmartgrid.web import services

    carga, sed = _sed('S1', 'N2', 'C')
    m = _modelo([_linea('T0', 'H', 'N1', 'ABC'), _linea('R1', 'N1', 'N2', 'AB')], cargas=[carga], seds=[sed])
    bueno = SimpleNamespace(disponible=True, convergio=True, errores=[], resumen=lambda: 'converge',
                            as_dict=lambda: {'convergio': True})
    monkeypatch.setattr(oraculo, 'disponible', lambda: True)
    monkeypatch.setattr(oraculo, 'validar', lambda _m: bueno)
    monkeypatch.setattr(preflight_contract, 'load_contract',
                        lambda _d: {'model': m, 'members': [m], 'model_sha256': 'x'})
    logs: list[str] = []
    ctx = SimpleNamespace(check_cancel=lambda: None, progress=lambda *a: None, log=logs.append)
    ws = SimpleNamespace(out_dir=tmp_path, groups={})
    r = services.pandapower_preflight(ws, ['F'], ctx)
    assert r['import_continued'] is True and r['no_convergen'] == {}
    assert r['feeders'][0]['fases']['conteo'] == {'transformador': 1}
    assert any('S1' in x for x in logs)


def test_elemento_nuevo_a_la_barra_compatible_mas_cercana():
    """081:RF-8 — un banco trifásico no se pone en una barra de dos fases: va a la que los lleva más cerca."""
    pedida = Barra('B2', 2)
    u = ubicar_nuevo('banco', 'BC1', 3, pedida, [(Barra('LEJOS', 3), 900.0), (Barra('MONO', 1), 5.0), (Barra('CERCA', 3), 40.0)])
    assert u.barra == 'CERCA' and u.reubicado and u.n == 3 and 'BC1' in u.nota and '40 m' in u.nota
    # En su barra, ni se mueve ni se anota.
    assert ubicar_nuevo('banco', 'BC1', 3, Barra('B3', 3)) == ubicar_nuevo('banco', 'BC1', 3, Barra('B3', 3))
    assert not ubicar_nuevo('banco', 'BC1', 3, Barra('B3', 3)).nota


def test_elemento_nuevo_sin_barra_compatible_no_se_rechaza():
    """081:RF-9 — queda en su barra con las fases de esa barra, y se dice; nada se rechaza."""
    u = ubicar_nuevo('banco', 'BC1', 3, Barra('B2', 2), [(Barra('MONO', 1), 5.0)])
    assert (u.barra, u.n, u.adaptado, u.reubicado) == ('B2', 2, True, False) and 'queda en B2' in u.nota


class _Terminal:
    def __init__(self, nombre, phtech, gps=(0.0, 0.0)):
        self.loc_name, self.phtech, self.uknom = nombre, phtech, 10.0
        self.GPSlat, self.GPSlon = gps


def test_obra_de_banco_va_a_una_barra_que_lo_lleve():
    """081:RF-8 — la obra de un banco nuevo, en el guion: nunca sobre una barra de dos fases si hay otra."""
    import sys
    from pathlib import Path

    from types import SimpleNamespace

    tools = str(Path(__file__).resolve().parents[1] / 'tools')
    sys.path.insert(0, tools)
    try:
        obras = cargar_herramienta('obras_pf.py', 'obras_pf_081', tools_en_path=True)
    finally:
        sys.path.remove(tools)
    pedida, cerca, lejos = _Terminal('B2', 4), _Terminal('B3', 0, (0.001, 0.0)), _Terminal('B4', 0, (0.5, 0.0))
    ctx = SimpleNamespace(obra=SimpleNamespace(barra='B2'), fila={}, elm=SimpleNamespace(GetObjs=lambda _c: [pedida, cerca, lejos]))
    assert obras._barra_con_tres_fases(ctx, pedida) is cerca and 'B3' in ctx.fila['avisos'][0]
    # Trifásica: se queda, sin aviso.
    otro = SimpleNamespace(obra=SimpleNamespace(barra='B3'), fila={}, elm=ctx.elm)
    assert obras._barra_con_tres_fases(otro, cerca) is cerca and otro.fila == {}
