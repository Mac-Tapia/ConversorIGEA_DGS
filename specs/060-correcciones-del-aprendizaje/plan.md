# Plan — Spec 060

1. Corregir `digital_twin/oraculo.py`: validación previa a cargar/ajustar, calibración por familias apartada de selección, IDs por partición y comprobación de genealogía antes de warm-start. RF-1–RF-3.
2. Corregir preparación en `asistente/llm_destilacion.py` y `tools/llm_destilar.py`: copia verificada de política dentro del corpus, parámetro explícito del constructor y origen registrado. Regenerar corpus en destino nuevo. RF-4.
3. Corregir `digital_twin/temporal_entrenamiento.py` usando fechas del lector existente; diagnóstico de celdas y persistencia completa de `GemeloGRU`. No rellenar mediciones ni filtrar fallos para fabricar un entrenamiento. RF-5–RF-6.
4. Ampliar consulta de estados existente en `web/services.py` con evidencia heredada explícita, sin cargar Torch ni migrar punteros mediante una consulta. RF-7.
5. Pruebas de regresión por cada cambio y auditoría real del corpus/fuentes. No entrenar sobre un sellado inválido. Registrar por separado campañas y bloqueos de recursos/datos.
6. Selección temporal explícita de hojas e intervalo en el trabajador existente, registrada antes de ajustar. La campaña de comprobación se fija en enero2025 para el medidor de la hojaL-TM105, sin inferir una pertenencia a un proyecto PowerFactory ni seleccionar la ventana por su error de prueba. El resultado será candidato y se reabrirá aparte; no se promueve automáticamente. RF-8.

Se conservan APIs y módulos existentes; la alternativa de crear otro entrenador o registro paralelo se descarta porque duplicaría identidad, promoción y custodia. Pruebas de contratos no sustituyen inferencia, entrenamiento ni aceptación eléctrica real.
