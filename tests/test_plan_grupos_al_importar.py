"""El plan reconoce un grupo ya convertido al importar y no inventa dudas (spec 078, RF-29 a RF-35).

Sin red real ni nombres de empresa: los grupos y los sistemas son de prueba.
"""
from __future__ import annotations

import copy

import pytest

from convertersmartgrid.asistente.interprete import Interpretacion
from convertersmartgrid.asistente.plan import resolver
from convertersmartgrid.asistente.tareas import TAREAS, TAREAS_HASTA_069

VOCAB = {'alimentadores': ['AL101', 'AL102'], 'proyecto': ['Proyecto demostracion'],
         'sistema': ['Zona', 'Otra'], 'set': ['SET_NORTE']}
GRUPOS = ['SISTEMA_ZONA', 'SISTEMA_ZONA_SET_NORTE', 'RED_UNIDA']


def _orden(texto, tarea='flujo', **datos):
    por_tipo = {t: [{'valor': v, 'confianza': .9} for v in vs] for t, vs in datos.items()}
    return Interpretacion(texto, tarea, .9, 'transformer', por_tipo)


@pytest.mark.parametrize('texto, marcado', [
    ('importa SISTEMA_ZONA en digsilent', []),
    ('importa SISTEMA_ZONA en digsilent', ['SISTEMA_ZONA']),
    ('Importa el sistema zona en PowerFactory', []),
    ('importa el sistema eléctrico Zona en digsilent', []),
    ('importa sistema-zona en digsilent', ['sistema-zona']),
])
def test_importar_un_grupo_convertido_no_pide_alimentadores(texto, marcado):
    """078:RF-29, 078:RF-30 — el grupo ya convertido es el destino, se escriba como se escriba."""
    datos = {'alimentadores': marcado} if marcado else {}
    plan = resolver(_orden(texto, **datos), VOCAB, grupos=GRUPOS)
    assert plan.listo and plan.datos['alimentadores'] == ['SISTEMA_ZONA']
    assert any('SISTEMA_ZONA' in r for r in plan.razonamiento)


def test_el_grupo_mas_largo_gana_sobre_el_que_contiene():
    """078:RF-30 — ``SISTEMA_ZONA_SET_NORTE`` no se confunde con ``SISTEMA_ZONA``."""
    plan = resolver(_orden('importa SISTEMA_ZONA_SET_NORTE en digsilent'), VOCAB, grupos=GRUPOS)
    assert plan.datos['alimentadores'] == ['SISTEMA_ZONA_SET_NORTE']


def test_un_grupo_con_errata_se_reconoce_por_parecido():
    """078:RF-30 — como los demás nombres del plan (026:RF-6)."""
    plan = resolver(_orden('importa SISTEMA_ZONAA en digsilent', alimentadores=['SISTEMA_ZONAA']), VOCAB, grupos=GRUPOS)
    assert plan.datos['alimentadores'] == ['SISTEMA_ZONA']


def test_el_grupo_no_deja_dudas_ni_pide_la_fuente():
    """078:RF-31 — ni «no es un alimentador» ni «contexto vinculado», también sin fuente cargada."""
    sin_fuente = {**VOCAB, 'alimentadores': []}
    plan = resolver(_orden('importa SISTEMA_ZONA en digsilent', alimentadores=['SISTEMA_ZONA']), sin_fuente, grupos=GRUPOS)
    assert plan.listo and not plan.dudas and not plan.faltan


@pytest.mark.parametrize('texto', ['importa el sistema Otra en digsilent', 'importa SISTEMA_OTRA en digsilent',
                                   'importa la set SET_SUR en digsilent'])
def test_sin_convertir_dice_que_se_convierta_y_no_pide_alimentadores(texto):
    """078:RF-32 — lo que falta es convertirlo, y lo dice con los grupos que sí hay."""
    plan = resolver(_orden(texto), VOCAB, grupos=GRUPOS)
    assert not plan.listo and not plan.dudas
    assert len(plan.faltan) == 1 and 'convert' in plan.faltan[0] and 'alimentadores' not in plan.faltan[0]
    assert 'SISTEMA_ZONA' in plan.faltan[0]


def test_una_orden_de_alimentadores_sigue_igual():
    """078:RF-29 — con alimentadores, y aunque se nombre su sistema, el plan no cambia."""
    plan = resolver(_orden('corre el flujo de AL101', alimentadores=['AL101']), VOCAB, grupos=GRUPOS)
    assert plan.datos['alimentadores'] == ['AL101'] and plan.listo
    con_sistema = resolver(_orden('importa AL102 del sistema Otra en digsilent'), VOCAB, grupos=GRUPOS)
    assert con_sistema.datos['alimentadores'] == ['AL102'] and con_sistema.listo
    sin_nada = resolver(_orden('corre el flujo'), VOCAB, grupos=GRUPOS)
    assert any(f.startswith('alimentadores:') for f in sin_nada.faltan)


def test_solo_la_tarea_de_importar_admite_grupo():
    """078:RF-29 — convertir un grupo no es lo mismo: esa orden sigue en sus alimentadores."""
    plan = resolver(_orden('convierte SISTEMA_ZONA', tarea='convertir', alimentadores=['SISTEMA_ZONA']), VOCAB, grupos=GRUPOS)
    assert plan.datos.get('alimentadores') != ['SISTEMA_ZONA']


def test_un_valor_que_contiene_el_nombre_no_es_una_duda():
    """078:RF-33 — «electrico Zona a DGS» dejaba la duda falsa «no es un sistema que la web conozca»."""
    plan = resolver(_orden('convierte el sistema electrico Zona a DGS', tarea='convertir_sistema',
                           sistema=['electrico Zona a DGS']), VOCAB)
    assert plan.datos['sistema'] == 'Zona' and not plan.dudas and plan.listo
    assert any('electrico Zona a DGS' in r and 'Zona' in r for r in plan.razonamiento)


def test_un_valor_que_no_existe_sigue_siendo_una_duda():
    """078:RF-34 — lo que no está en la web se dice."""
    plan = resolver(_orden('convierte el sistema Inexistente', tarea='convertir_sistema', sistema=['Inexistente']), VOCAB)
    assert 'sistema' not in plan.datos
    assert plan.dudas == ['«Inexistente» no es un sistema que la web conozca.']


def test_ni_el_catalogo_ni_el_vocabulario_cambian():
    """078:RF-35, 069:RF-13 — los grupos viven en el contraste: la prueba histórica no se mueve."""
    assert 'grupos' not in {d.tipo for t in TAREAS.values() for d in t.datos}
    assert TAREAS_HASTA_069['flujo'].descripcion == 'Flujo de potencia en DIgSILENT de los alimentadores.'
    antes = copy.deepcopy(VOCAB)
    resolver(_orden('importa SISTEMA_ZONA en digsilent'), VOCAB, grupos=GRUPOS)
    assert VOCAB == antes
    # Sin grupos, la firma de antes se comporta como antes.
    assert any(f.startswith('alimentadores:') for f in resolver(_orden('corre el flujo'), VOCAB).faltan)


def test_el_espacio_ofrece_solo_los_grupos_con_dgs(tmp_path):
    """078:RF-29, 078:RF-35 — un grupo fallido o sin fichero no se puede importar, y el vocabulario no los lleva."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    (tmp_path / 'BUENO.dgs').write_text('', encoding='utf-8')
    (tmp_path / 'FALLIDO.dgs').write_text('', encoding='utf-8')
    ws = SimpleNamespace(out_dir=tmp_path, groups={'BUENO': {'status': 'ok'}, 'FALLIDO': {'status': 'fail'},
                                                   'SIN_DGS': {'status': 'ok'}})
    assert services.asistente_grupos(ws) == ['BUENO']
