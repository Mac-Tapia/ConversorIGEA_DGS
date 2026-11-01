"""047:RF-14 — persistencia real de un alumno calibrado; exige candidato local y CUDA.

Ejecutar con IGEA_ALUMNO_CANDIDATO apuntando al directorio del alumno. Sin ese
artefacto el ensayo falla; no se sustituye por un doble ni se omite.
"""
import os
from pathlib import Path
import tempfile

from igea_dgs.asistente import transformer as tr
from igea_dgs.asistente.destilacion_integral import cargar_alumno
from igea_dgs.training_coordinator import BloqueoGPU


def test_formato_estandar_reabre_temperatura_y_prediccion(tmp_path, monkeypatch):
    """047:RF-14 — la temperatura aprendida no se pierde al usar guardar/cargar vigentes."""
    origen = Path(os.environ['IGEA_ALUMNO_CANDIDATO'])
    lock = Path(os.environ.get('IGEA_ML_GPU_LOCK') or str(Path(tempfile.gettempdir()) / 'igea-dgs-gpu.lock'))
    with BloqueoGPU(lock, 'ensayo-persistencia-calibracion'):
        modelo = cargar_alumno(origen)
        assert next(modelo.red.parameters()).device.type == 'cuda'
        assert modelo.temperatura != 1., 'el caso debe ejercer una calibración no trivial'
        esperado = modelo.predecir('convierte AB101 a dgs')
        temperatura = modelo.temperatura
        monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
        version = tr.guardar(modelo, {'origen': 'ensayo aislado; sin activación'})
        reabierto = tr.cargar(version)
        obtenido = reabierto.predecir('convierte AB101 a dgs')
        assert reabierto.temperatura == temperatura
        assert obtenido['tarea'] == esperado['tarea'] and obtenido['datos'] == esperado['datos']
        assert abs(obtenido['confianza'] - esperado['confianza']) < 1e-6
        assert tr.version_promovida() is None
