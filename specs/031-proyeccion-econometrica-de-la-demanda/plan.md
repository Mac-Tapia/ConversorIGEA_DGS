# Plan 031 — Proyección para todos los años del PIDE

## Dónde

- `src/convertersmartgrid/proyeccion_anual.py`, nuevo: competición, métricas, elección, emisión y evaluación (RF-2 a RF-9, RF-12 a RF-14). Reutiliza `pronostico_demanda` (dataset, objetivos, métricas, modelos) y `proyeccion_mercado` (métodos anuales y errores contra lo ocurrido), sin duplicarlos.
- `tools/proyeccion_anual.py`, nueva: la orden, con su `--help` y el manual.
- `src/convertersmartgrid/web/services.py` y `web/app.py`: el PIDE pronostica primero y pasa la referencia con huella al plan (RF-1); las obras leen la proyección aceptada (RF-11).
- `tools/reentrenar_modelos.py` y `aprendizaje_continuo.py`: N-HiTS, TFT y PatchTST compiten dentro de la etapa `gru` del ciclo común (RF-2, RF-10).

## Decisiones

- La proyección es una capa aparte de la 089: extrapolar en silencio una curva de 28 días a años es lo que 072 prohíbe. Descartado.
- La regla de elección se escribe en la evaluación antes de medir (RF-4).
- La aceptación por orden del operador queda escrita y no oculta el horizonte sin validar (RF-6, RF-7).

## Pruebas

Sintéticas sorteadas: series con tendencia conocida; gana quien debe y, sin mejora, la referencia; `leer_proyeccion_anual` acepta el resultado; ninguna fila negativa; determinismo; el horizonte validado no se infla.
