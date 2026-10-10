# Tareas — Spec 007

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Doble de PowerFactory: variaciones que se activan y desactivan,
      `GetActiveNetworkVariations`, y objetos creados en una etapa que salen de la red
      cuando su variación se desactiva, en `tests/fake_pf.py`. (apoyo de RF-11, RF-12, RF-17)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion.py tests/test_ajuste_cabecera_guion.py` sigue en verde.
- [x] T2. `medir_cabecera` y `potencia` a `tools/cargas_pf.py`; el ajuste las importa de
      allí. (apoyo de RF-13, RF-32)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde sin cambiar sus pruebas.
- [x] T3. `armar_plan(..., base=)`: base en el plan, nombre de variación por carga y de
      demandas, SED calibradas que cambia el libro. (RF-1, RF-10, RF-19, RF-21, RF-34)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py` en verde.
- [x] T4. Guion: activar la base, error si no existe, variaciones activas al empezar y al
      terminar. (RF-6, RF-7, RF-8, RF-34)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_007.py -k base` en verde.
- [x] T5. Guion: solo el alimentador activo para conectar, fila con otro alimentador
      anotada, distancia sin umbral. (RF-24 a RF-31)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_007.py -k activo` en verde.
- [x] T6. Guion (pruebas en `tests/test_cargas_pf_guion_007.py`): variación de demandas, flujo sin proyecto, una variación por carga
      desactivada al terminar, Δ por carga, carga no conectable sin variación,
      cancelación, solo la base al final; simular dice la variación de cada carga.
      (RF-9, RF-11 a RF-19, RF-32, RF-33, RF-35)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion.py` en verde, con las pruebas
      de la spec 004 que fijaban una variación para todo actualizadas.
- [x] T7. Guion: datos económicos en la etapa de cada carga y `ComTececo` por carga.
      (RF-22, RF-23)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_007.py -k tececo` en verde.
- [x] T8. Web: `cargas_plan` con `ajuste_job_id` (mismo proyecto, solo `ajuste_aplicar`
      terminado), endpoint. (RF-1, RF-4, RF-5)
      Hecho cuando: `pytest -q tests/test_cargas_pf_web.py` en verde.
- [x] T9. Interfaz: orden de pasos, recuadro de la base con «Quitar base», alimentador
      fijado al de la base, informe por carga. (RF-1 a RF-5, RF-18, RF-21, RF-23, RF-30,
      RF-33, RF-34)
      Hecho cuando: `pytest -q tests/test_cargas_pf_front.py`, `npx tsc --noEmit -p .` y
      `npm run build` en `frontend/` correctos.
- [x] T10. Validación: cada RF citado por al menos una prueba y en verde; suite completa.
      (Todos)
      Hecho cuando: `grep -rnoE "007:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-37.
- [ ] T11. Prueba real en DIgSILENT con SI213, a cargo del usuario: base del ajuste
      activa, una variación por carga, cada carga a su barra más cercana de SI213, solo
      la base activa al terminar, y los riesgos del plan.
