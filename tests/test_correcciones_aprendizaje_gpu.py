"""060:RF-6: prueba CUDA real de persistencia con una serie de contrato sintética.

No es una medición, campaña de aprendizaje aceptada ni resultado eléctrico nativo.
"""
import json
from pathlib import Path

import numpy as np


def test_gru_guarda_ajustes_pasos_historial_y_reabre(tmp_path):
    """060:RF-6: los pesos ajustados se reabren con toda su configuración real."""
    from convertersmartgrid.digital_twin.temporal_entrenamiento import entrenar_temporal,reabrir_temporal
    t=np.arange(30*96)
    serie=(100+10*np.sin(2*np.pi*t/96)).tolist()
    r=entrenar_temporal({'contrato':serie},tmp_path,semillas=(11,),
        procedencia={'origen':'sintético de contrato, no observación'},epocas=2)
    assert r['training_completed'] and not r['promovido']
    carpeta=Path(r['candidate_dir']);meta=json.loads((carpeta/'modelo.json').read_text(encoding='utf-8'))
    modelo=meta['modelos']['contrato']
    assert modelo['cfg']['ocultas']==32 and modelo['cfg']['paciencia']==8
    assert len(modelo['historial'])==modelo['validacion']['epocas']==2
    assert modelo['optimizer_updates']>0 and modelo['optimizador']['lr']==.01
    assert reabrir_temporal(carpeta)['smoke_reload']['ok']
