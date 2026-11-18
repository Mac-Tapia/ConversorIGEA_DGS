"""Spec 112: cohortes de evaluación por empresa y por tiempo (112:RF-6, RF-9).

Un modelo que se evalúa con alimentadores que ya vio en el ajuste no dice nada de una red nueva. La unidad de
partición es el componente conexo que une los alimentadores que comparten un cliente o un medidor: un cliente
transferido entre dos alimentadores arrastra a los dos a la misma partición. Por empresa se deja una fuera cada vez;
por tiempo se corta por fecha con una franja de un horizonte sin datos en ninguna parte. Cada cohorte se valida con
``evaluacion_modelos.particionar_registros``. Con una sola empresa —el caso real de hoy— no hay cohorte por empresa
y el informe lo dice. Todo con datos sintéticos sorteados, con un número de alimentadores que no está fijado.
"""
from __future__ import annotations

import importlib.util

import random
from datetime import datetime, timedelta

import pytest

INICIO = datetime(2027, 1, 4)


def _registros(semilla: int, empresas: tuple[str, ...], *, transferido: bool = True):
    from convertersmartgrid.aplicacion.benchmarks.cohortes import Registro
    r = random.Random(semilla)
    salida = []
    for e in empresas:
        alimentadores = [f'{e}-A{k}' for k in range(r.randint(5, 12))]
        for k, a in enumerate(alimentadores):
            clientes = [f'{a}-C{j}' for j in range(r.randint(1, 4))]
            if transferido and k == 1:
                # Un cliente transferido: aparece también en el alimentador anterior.
                clientes.append(f'{alimentadores[0]}-C0')
            for d in range(0, 120, 7):
                salida.append(Registro(id=f'{a}:{d}', empresa=e, alimentador=a, clientes=tuple(clientes),
                                       t=INICIO + timedelta(days=d)))
    return salida


def _particion_de(cohorte):
    return {rid: parte for parte in ('entrenamiento', 'seleccion', 'calibracion', 'prueba')
            for rid in getattr(cohorte.particiones, parte)}


def test_el_cliente_transferido_une_sus_alimentadores():
    """112:RF-6 — el componente conexo une a los alimentadores que comparten un cliente."""
    assert importlib.util.find_spec('convertersmartgrid.aplicacion.benchmarks.cohortes'), 'falta convertersmartgrid.aplicacion.benchmarks.cohortes'
    from convertersmartgrid.aplicacion.benchmarks.cohortes import componentes
    regs = _registros(1, ('E1',))
    comp = componentes(regs)
    por_alim = {r.alimentador: comp[r.id] for r in regs}
    assert por_alim['E1-A0'] == por_alim['E1-A1']
    assert len(set(por_alim.values())) == len(por_alim) - 1


@pytest.mark.parametrize('semilla', [3, 4, 5])
def test_una_empresa_fuera_cada_vez(semilla):
    """112:RF-6 — por empresa: la prueba es entera de la empresa retenida y ningún alimentador cae en dos partes."""
    assert importlib.util.find_spec('convertersmartgrid.aplicacion.benchmarks.cohortes'), 'falta convertersmartgrid.aplicacion.benchmarks.cohortes'
    from convertersmartgrid.aplicacion.benchmarks.cohortes import planificar
    regs = _registros(semilla, ('E1', 'E2', 'E3'))
    plan = planificar(regs, corte=INICIO + timedelta(days=70), horizonte=timedelta(days=14))
    por_empresa = [c for c in plan.cohortes if c.tipo == 'empresa']
    assert sorted(c.retenida for c in por_empresa) == ['E1', 'E2', 'E3']
    empresa_de = {r.id: r.empresa for r in regs}
    alim_de = {r.id: r.alimentador for r in regs}
    for c in por_empresa:
        parte = _particion_de(c)
        assert {empresa_de[i] for i in c.particiones.prueba} == {c.retenida}
        assert c.retenida not in {empresa_de[i] for p in ('entrenamiento', 'seleccion', 'calibracion')
                                  for i in getattr(c.particiones, p)}
        partes_por_alim = {}
        for rid, p in parte.items():
            partes_por_alim.setdefault(alim_de[rid], set()).add(p)
        assert all(len(v) == 1 for v in partes_por_alim.values())
        assert parte[f'{c.retenida}-A0:0'] == parte[f'{c.retenida}-A1:0'] == 'prueba'
        assert c.particiones.politica_hash
    assert not any('no está demostrada' in a for a in plan.avisos)


@pytest.mark.parametrize('semilla', [6, 7])
def test_por_tiempo_con_franja_de_separacion(semilla):
    """112:RF-6 — por tiempo: entrenamiento antes del corte, prueba tras la franja; la franja no está en ninguna parte."""
    assert importlib.util.find_spec('convertersmartgrid.aplicacion.benchmarks.cohortes'), 'falta convertersmartgrid.aplicacion.benchmarks.cohortes'
    from convertersmartgrid.aplicacion.benchmarks.cohortes import planificar
    regs = _registros(semilla, ('E1', 'E2'))
    corte, h = INICIO + timedelta(days=63), timedelta(days=21)
    plan = planificar(regs, corte=corte, horizonte=h)
    c = next(c for c in plan.cohortes if c.tipo == 'tiempo')
    t_de = {r.id: r.t for r in regs}
    alim_de = {r.id: r.alimentador for r in regs}
    parte = _particion_de(c)
    assert all(t_de[i] < corte for i, p in parte.items() if p != 'prueba')
    assert all(t_de[i] >= corte + h for i in c.particiones.prueba)
    assert not any(corte <= t_de[i] < corte + h for i in parte)
    # Tampoco por tiempo un alimentador cae en dos partes (RF-6).
    partes_por_alim = {}
    for rid, p in parte.items():
        partes_por_alim.setdefault(alim_de[rid], set()).add(p)
    assert all(len(v) == 1 for v in partes_por_alim.values())
    assert c.descartados > 0


def test_con_una_sola_empresa_lo_dice(tmp_path):
    """112:RF-9 — con una empresa no hay cohorte por empresa, y el aviso dice que la generalización no está demostrada."""
    assert importlib.util.find_spec('convertersmartgrid.aplicacion.benchmarks.cohortes'), 'falta convertersmartgrid.aplicacion.benchmarks.cohortes'
    from convertersmartgrid.aplicacion.benchmarks.cohortes import FRASE_UNA_EMPRESA, planificar
    regs = _registros(8, ('E1',))
    plan = planificar(regs, corte=INICIO + timedelta(days=70), horizonte=timedelta(days=14))
    assert not [c for c in plan.cohortes if c.tipo == 'empresa']
    assert [c for c in plan.cohortes if c.tipo == 'tiempo']
    assert FRASE_UNA_EMPRESA in plan.avisos
    assert FRASE_UNA_EMPRESA.startswith('La generalización entre empresas no está demostrada')


def test_las_empresas_se_nombran_por_seudonimo():
    """112:RF-6, RF-2 — la empresa de un origen es la huella de su perfil; en el benchmark, E1…En sin la huella."""
    assert importlib.util.find_spec('convertersmartgrid.aplicacion.benchmarks.cohortes'), 'falta convertersmartgrid.aplicacion.benchmarks.cohortes'
    from convertersmartgrid.aplicacion.benchmarks.cohortes import seudonimos_de_empresa
    huellas = ['f' * 64, '0' * 64, 'a' * 64]
    nombres = seudonimos_de_empresa(huellas)
    assert sorted(nombres.values()) == ['E1', 'E2', 'E3']
    assert seudonimos_de_empresa(list(reversed(huellas))) == nombres
    assert not set(nombres.values()) & set(huellas)


def test_un_cliente_en_dos_empresas_no_se_puede_separar():
    """112:RF-6 — si un componente cruza dos empresas, dejar una fuera es imposible sin mezclarlas: se dice."""
    assert importlib.util.find_spec('convertersmartgrid.aplicacion.benchmarks.cohortes'), 'falta convertersmartgrid.aplicacion.benchmarks.cohortes'
    from convertersmartgrid.aplicacion.benchmarks.cohortes import Registro, planificar
    regs = _registros(9, ('E1', 'E2'), transferido=False)
    regs.append(Registro(id='raro', empresa='E2', alimentador='E2-A0', clientes=('E1-A0-C0',), t=INICIO))
    with pytest.raises(ValueError, match='empresa'):
        planificar(regs, corte=INICIO + timedelta(days=70), horizonte=timedelta(days=14))
