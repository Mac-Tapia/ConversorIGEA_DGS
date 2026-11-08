"""050:RF-2/8: composición de productores reales; imports literales, por familia solicitada."""
from __future__ import annotations


class ProductoresReales:
    """Adaptador de datos existentes: construirlo no entrena ni abre la GPU."""

    def lenguaje(self, instantanea, referencias, familias):
        from .asistente.dataset_entrenamiento import muestras_aprendizaje
        from .trabajadores_ml import leer_dataset_v2
        return muestras_aprendizaje(instantanea, referencias, list(familias), leer_dataset=leer_dataset_v2)

    def pinn(self, instantanea, referencias):
        from .digital_twin.productor_pinn import muestras_aprendizaje
        return muestras_aprendizaje(instantanea, referencias)

    def gru(self, instantanea, referencias, parametros):
        from .digital_twin.temporal_entrenamiento import muestras_aprendizaje
        return muestras_aprendizaje(instantanea, referencias, **dict(parametros))

    def qlora(self, instantanea, referencias):
        from .asistente.llm_destilacion import muestras_aprendizaje
        return muestras_aprendizaje(instantanea, referencias)

    def evolutivos(self, instantanea):
        from .digital_twin.evolutivo import casos_aprendizaje
        return [c['muestra'] for c in casos_aprendizaje(instantanea)]
