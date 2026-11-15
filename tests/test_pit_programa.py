"""Spec 107 T9 — programa por año, titular y área, con bajas y reemplazos (107:RF-6)."""
from __future__ import annotations

import pytest

from datos_pit import perfil_a, perfil_b

from convertersmartgrid.pit.ambito import PitError, areas_del_perfil
from convertersmartgrid.pit.programa import programar


def _cambios(caso):
    """Una alta por SET y un reemplazo del transformador de la primera, en años del horizonte sorteado."""
    p = caso['pistas']
    tit = p.get('titular_de_set') or {s: p['titulares'][0] for s in p['sets']}
    anios = caso['anios']
    cambios = [{'accion': 'alta', 'elemento': f'CN-{s}', 'tipo': 'celda', 'anio': anios[i % len(anios)],
                'titular': tit[s], 'instalacion': s} for i, s in enumerate(p['sets'])]
    s0 = p['sets'][-1]
    cambios.append({'accion': 'reemplazo', 'elemento': f'TN-{s0}', 'reemplaza': f'T-{s0}', 'tipo': 'trafo2',
                    'anio': anios[-1], 'titular': tit[s0], 'instalacion': s0})
    return cambios


def test_perfil_a_un_titular():
    """107:RF-6 — con un titular, un solo programa; cada fila con año, titular y área, y el reemplazo en baja y alta."""
    caso = perfil_a(7)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    prog = programar(area, _cambios(caso))
    assert list(prog.por_titular()) == caso['pistas']['titulares']
    assert all(f.area == caso['area'] and f.anio in caso['anios'] for f in prog.filas)
    s0 = caso['pistas']['sets'][-1]
    baja = next(f for f in prog.filas if f.elemento == f'T-{s0}')
    alta = next(f for f in prog.filas if f.elemento == f'TN-{s0}')
    assert (baja.accion, alta.accion, alta.reemplaza, baja.anio) == ('baja', 'alta', f'T-{s0}', alta.anio)
    assert [f.anio for f in prog.filas] == sorted(f.anio for f in prog.filas)


@pytest.mark.parametrize('seed', (7, 40))
def test_perfil_b_un_programa_por_titular(seed):
    """107:RF-6 — con varios titulares, un programa por titular que suma el del área."""
    caso = perfil_b(seed)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    prog = programar(area, _cambios(caso))
    por = prog.por_titular()
    usados = set(caso['pistas']['titular_de_set'].values())
    assert set(por) == usados and len(por) >= 2
    assert sum(len(v) for v in por.values()) == len(prog.filas)
    assert prog.como_dict()['por_titular'].keys() == por.keys()


def test_titular_de_otra_area_o_sin_anio():
    """107:RF-6 — un titular que no es del área, o un elemento sin año, no se programa: error que lo nombra."""
    caso = perfil_a(7)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    with pytest.raises(PitError, match='no es del área'):
        programar(area, [{'accion': 'alta', 'elemento': 'X', 'anio': caso['anios'][0], 'titular': 'OTRO'}])
    with pytest.raises(PitError, match='anio'):
        programar(area, [{'accion': 'alta', 'elemento': 'X', 'titular': caso['pistas']['titulares'][0]}])


# --- Modificación del plan vigente (107:RF-17, T25) ------------------------------------------------------------------

def _vigente_y_nuevo(caso):
    """El programa vigente y uno nuevo que elimina una alta, cambia el año de otra y agrega una tercera."""
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    cambios = _cambios(caso)
    vigente = programar(area, cambios)
    anios = caso['anios']
    quitada, movida = cambios[0], cambios[1] if len(cambios) > 2 else cambios[-1]
    nuevos = [c for c in cambios if c is not quitada and c is not movida]
    nuevos.append({**movida, 'anio': anios[-1] if movida['anio'] != anios[-1] else anios[0]})
    s = caso['pistas']['sets'][0]
    tit = (caso['pistas'].get('titular_de_set') or {}).get(s) or caso['pistas']['titulares'][0]
    nuevos.append({'accion': 'alta', 'elemento': f'CX-{s}', 'tipo': 'celda', 'anio': anios[0], 'titular': tit,
                   'instalacion': s})
    return area, vigente, programar(area, nuevos), quitada, movida, f'CX-{s}'


@pytest.mark.parametrize('fabrica', (perfil_a, perfil_b), ids=('A', 'B'))
def test_modificacion_lista_lo_que_se_elimina_cambia_o_agrega(fabrica):
    """107:RF-17 — entre el programa vigente y el nuevo: lo eliminado, lo cambiado (con lo de antes y lo de ahora) y lo
    agregado, cada uno con su razón."""
    from convertersmartgrid.pit.programa import comparar_programas

    caso = fabrica(44)
    _, vigente, nuevo, quitada, movida, agregada = _vigente_y_nuevo(caso)
    razones = {quitada['elemento']: 'la demanda ya no lo exige', movida['elemento']: 'se adelanta por la demanda',
               agregada: 'nueva salida de la SET'}
    cambios = comparar_programas(vigente, nuevo, razones)
    por = {(c.elemento, c.cambio): c for c in cambios}
    assert set(por) == {(quitada['elemento'], 'elimina'), (movida['elemento'], 'cambia'), (agregada, 'agrega')}
    assert por[(movida['elemento'], 'cambia')].antes['anio'] != por[(movida['elemento'], 'cambia')].despues['anio']
    assert por[(quitada['elemento'], 'elimina')].despues is None and por[(agregada, 'agrega')].antes is None
    assert all(c.razon == razones[c.elemento] for c in cambios)
    assert comparar_programas(vigente, vigente, {}) == []


def test_modificacion_sin_razon_o_de_otra_area_es_un_error():
    """107:RF-17 — un cambio sin su razón no se lista callado, y dos programas de áreas distintas no se comparan."""
    import dataclasses

    from convertersmartgrid.pit.programa import comparar_programas

    caso = perfil_a(44)
    _, vigente, nuevo, quitada, movida, agregada = _vigente_y_nuevo(caso)
    with pytest.raises(PitError, match=agregada):
        comparar_programas(vigente, nuevo, {quitada['elemento']: 'x', movida['elemento']: 'y'})
    with pytest.raises(PitError, match='área'):
        comparar_programas(vigente, dataclasses.replace(nuevo, area='OTRA'), {})
