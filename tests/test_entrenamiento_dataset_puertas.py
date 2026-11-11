"""047:RF-42 — la puerta dice el valor medido y de cuántos ejemplos sale, o que la métrica falta."""
from __future__ import annotations

from convertersmartgrid.asistente.clasificador import _fallos_de_metricas
from convertersmartgrid.asistente.entrenamiento_dataset import puertas_dataset


def test_bajo_la_puerta_dice_su_valor_y_ejemplos_y_ausente_lo_dice_aparte():
    r = puertas_dataset('informes', {'ejemplos': 7, 'acierto_tipo': 0.71, 'acierto_subtipo': 0.95},
                        {'ejemplos': 3}, None, {'ok': True})
    assert 'prueba: acierto_tipo 0.710 bajo 0.9 con 7 ejemplo(s)' in r['fallos']
    assert any(f.startswith('reales: acierto_tipo ausente o inválido') for f in r['fallos'])
    assert not r['approved']
    assert _fallos_de_metricas({'acierto_tipo': 0.5}, None, 0.9)[0] == 'acierto_tipo 0.500 bajo 0.9'
