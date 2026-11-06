# Tareas — Spec 067

- [x] T1 Evidencia de los trabajos reales y revisión desde el botón. (RF-1 a RF-7)
  Hecho cuando: `pytest -q tests/test_asistente_operativo.py -k evidencia` en verde, sin registrar a mano.
- [x] T2 Aviso del modelo que respondió. (RF-8 a RF-11)
  Hecho cuando: `pytest -q tests/test_asistente_operativo.py -k aviso` en verde.
- [x] T3 Planes guardados por espacio. (RF-12 a RF-19)
  Hecho cuando: `pytest -q tests/test_asistente_operativo.py -k guardado` en verde.
- [x] T4 Puesta en uso gobernada por el registro. (RF-20 a RF-29)
  Hecho cuando: `pytest -q tests/test_asistente_operativo.py -k uso` en verde.
- [x] T5 Tareas de la escalera y de «Con proyecto». (RF-30 a RF-36)
  Hecho cuando: `pytest -q tests/test_asistente_operativo.py -k tarea` en verde.
- [x] T6 Lista de etapas del proyecto entero. (RF-37 a RF-40)
  Hecho cuando: `pytest -q tests/test_asistente_operativo.py -k lista` en verde.
- [x] T7 Reentrenar de verdad en la GPU, cuando esté libre, y comprobar que el candidato llega a una decisión del registro.
  Hecho cuando: el informe del trabajo dice su estado y el modelo en uso, y la decisión queda en `model_registry`.
  Hecho el 2026-11-02: candidato `702102bd1119` RECHAZADO (0,514 en 922 sintéticas, 2 de 3 humanas), el modelo en uso sigue `20261024-150042-37ce` y el clasificador queda BLOQUEADO_POR_DATOS.
- [x] T8 Recorrer la consola en el navegador con la web reiniciada.
  Hecho cuando: un plan guardado aparece tras reiniciar, la lista de etapas se ve antes del clic y un aviso de modelo se lee.
  Hecho el 2026-11-06: recorrido en el navegador (Playwright) sobre la web del 8765 arrancada el 2026-11-05 22:18
  con d6194dcf salvo 1fed4f78 (`pf_arnes.py` y `powerfactory_binding.py`, ajenos a la consola). El plan `738d3fe67ef9`
  del espacio `ece4d0559d2b4f40`, guardado el 2026-11-02, aparece tras el reinicio con «Confirmar» desactivado porque
  cambió el contexto (RF-13, RF-15, RF-19); «Ver las etapas» de Pisco 2026-07 enseña las 8 etapas, 6 que escriben y 2
  omitidas con su motivo, antes del botón «Confirmar estas 6 etapas», que no se pulsó (RF-37); y cada plan del espacio
  de prueba `1985f689071b42ee` trae el aviso del modelo de órdenes provisional como alerta (RF-11). Capturas en
  `output/evidencia_web_067_077/067_T8_*.png`, fuera de git. Sin DIgSILENT.
- [ ] T9 [DIgSILENT] La escalera y la optimización desde una orden, sobre un proyecto de prueba.
  Hecho cuando: el trabajo termina por la ruta de la web y su resultado queda como evidencia revisable.
