# Plan de implementación — Spec062

Ejecución directa, sin delegación. Aplica las reglas SDD del proyecto y la metodología
de writing-plans: pruebas del contrato antes del código, comprobación y cierre con evidencia.

1. Crear `web/retencion.py`: política diaria persistida, referencias cruzadas y
   clasificación restrictiva de `runs/<run_id>`, `tmp` y `entradas/_auto`. Validar rutas
   absolutas antes de borrar; rechazar enlaces en todo el árbol; no borrar carpetas
   desconocidas. Conservar informes, pesos y ejecuciones con archivos recientes. RF-1/2/4/5/6/7.
2. Añadir exclusión de mantenimiento a `JobManager`: admisión y limpieza comparten
   un cerrojo; si hay trabajos, aplazar. No cancelar procesos. RF-3.
3. Integrar revisión en lifespan mediante `asyncio.to_thread` y parada cooperativa;
   consulta cada60 segundos del vencimiento, pero limpieza una vez cada24h. Persistir
   próxima fecha tras reiniciar; cualquier error aparece en el resumen. RF-1/3/7.
4. Incorporar estado al monitor existente y a su vista sin intervalos nuevos. RF-8.
5. Probar sobre directorios temporales reales, incluyendo enlaces duros, referencias
   entre espacios, errores, reanudación, exclusión concurrente y consulta HTTP.
   Documentar política, registrar fuentes en índice y ejecutar regresiones/build.

No se modifica `source_runs.py`: su custodia sigue vigente mientras una ejecución
esté referenciada. No se utiliza `git clean` ni se borra toda `output` por antigüedad.
