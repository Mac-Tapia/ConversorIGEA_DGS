"""Código operativo del alimentador (056:RF-7) y conductores reconstruidos al cargar (053:RF-9).

El 2026-11-01, con la copia VNR-GIS de Electro Oriente, la web listaba W12882 y L14243 (códigos
internos de VNR-GIS) en lugar de NJA202 y 0205, y dejaba 22 alimentadores «incompletos» porque
sus conductores venían sin impedancia y la reconstrucción esperaba a convertir.
"""

from __future__ import annotations

from types import SimpleNamespace

from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

from test_catalogo_crece import _catalogo
from test_vnr_sqlserver import _datos, _tablas


def test_el_alimentador_lleva_su_codigo_operativo():
    """056:RF-7: el modelo usa EtiquetaSalida; el código de VNR-GIS queda en los metadatos."""
    tablas = _tablas()
    tablas['mtSalida'][0]['EtiquetaSalida'] = 'NJA202'
    datos, _motor = _datos(tablas)
    modelo, _avisos = sv.modelo_canonico(datos)
    assert {s.feeder_id for s in modelo.sections} == {'NJA202'}
    assert {c.feeder_id for c in modelo.loads} == {'NJA202'}
    assert {f.feeder_id for f in modelo.sources} == {'NJA202'}
    assert modelo.metadata['codigo_vnr'] == {'NJA202': 'F1'}
    # Se puede pedir por cualquiera de los dos códigos.
    assert sv.modelo_canonico(datos, ['F1'])[0].sections
    assert sv.modelo_canonico(datos, ['NJA202'])[0].sections


def test_sin_etiqueta_o_repetida_conserva_el_codigo_y_se_anota():
    """056:RF-7: sin etiqueta, o con una que comparten dos salidas, no se adivina."""
    avisos: list[dict] = []
    codigos = sv.codigos_operativos([
        {'CodSalidaMT': 'A1', 'EtiquetaSalida': 'R5'},
        {'CodSalidaMT': 'A2', 'EtiquetaSalida': 'R5'},
        {'CodSalidaMT': 'A3', 'EtiquetaSalida': ''},
        {'CodSalidaMT': 'A4', 'EtiquetaSalida': 'NJA202 '},
    ], avisos)
    assert codigos == {'A1': 'A1', 'A2': 'A2', 'A3': 'A3', 'A4': 'NJA202'}
    assert {a['code'] for a in avisos} == {'ETIQUETA_REPETIDA', 'SALIDA_SIN_ETIQUETA'}


def test_conductor_sin_impedancia_se_reconstruye_al_cargar(tmp_path):
    """053:RF-9: el código que la fuente trae sin R ni X se completa con su ficha en la carga,
    sin duplicar la fila, y el alimentador sale listo con CONDUCTOR_RECONSTRUIDO."""
    from convertersmartgrid.reglas import con_impedancia, preparar_dataset
    from convertersmartgrid.web.readiness import revisar_conductores
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist

    tablas = _tablas()
    # Las normas del mismo material y sección que trae el catálogo de prueba.
    for t in tablas['mtTramo']:
        t['CodNorma'] = 'AA05003'
    datos, _motor = _datos(tablas)
    modelo, _avisos = sv.modelo_canonico(datos)
    puente = canonical_to_cymdist(modelo, source_path=tmp_path / 'copia')
    dataset = puente.dataset
    readiness = {k: dict(v) for k, v in puente.readiness.items()}
    assert any('MISSING_CONDUCTOR_PARAMETERS' in r['blocking_codes'] for r in readiness.values())

    informe = preparar_dataset(dataset, catalogo=_catalogo(tmp_path))
    filas = [f for f in dataset.equipment_tables.get('LINE', ()) if f['ID'] == 'AA05003D']
    assert len(filas) == 1 and con_impedancia(filas[0])
    cambiados = revisar_conductores(readiness, dataset,
                                    (d['codigo'] for d in informe.conductores_deducidos))
    assert cambiados == 1
    (fila,) = readiness.values()
    assert 'MISSING_CONDUCTOR_PARAMETERS' not in fila['blocking_codes']
    assert 'CONDUCTOR_RECONSTRUIDO' in fila['warning_codes']


def test_el_que_no_se_puede_completar_sigue_incompleto():
    """053:RF-9: si un código sigue sin impedancia, la falta se queda y se dice."""
    from convertersmartgrid.web.readiness import revisar_conductores

    dataset = SimpleNamespace(
        equipment_tables={'LINE': ({'ID': 'X1', 'R1': '', 'X1': ''},)},
        line_configurations={'s1': {'LineCableID': 'X1'}},
        feeders={'F': ('s1',)},
    )
    readiness = {'F': {'status': 'INVENTORY_ONLY',
                       'blocking_codes': ['MISSING_CONDUCTOR_PARAMETERS']}}
    assert revisar_conductores(readiness, dataset) == 0
    assert readiness['F']['blocking_codes'] == ['MISSING_CONDUCTOR_PARAMETERS']
