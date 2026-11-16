# Tareas 031

- [x] T1. Competición, métricas y elección por magnitud y clase. (RF-2, RF-3, RF-4, RF-8, RF-13, RF-14)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k "competicion or eleccion"` en verde.
      Hecho el 2026-11-08: 10 pruebas en verde.
- [x] T6. Formato 01 construido con la medición de cabecera, con sus meses por año. (RF-15, RF-8)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k formato` en verde.
      Hecho el 2026-11-08: 8 pruebas en verde.
- [x] T2. Emisión de todos los años con banda, reparto por carga y evaluación que lee 072. (RF-5, RF-6, RF-7, RF-9, RF-12, RF-16)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k "emision or contrato"` en verde.
      Hecho el 2026-11-08: 16 pruebas en verde.
- [x] T3. El PIDE pronostica primero y las obras leen la proyección aceptada. (RF-1, RF-11)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k "pide or obras"` en verde.
      Hecho el 2026-11-08: 7 pruebas en verde. Residuo: con proyección aceptada el PIDE recibe una tasa equivalente por alimentador; el valor de cada año exige las identidades `.ElmLod` del modo anual.
- [ ] T4. Los modelos neuronales compiten en el ciclo común y el ganador publicado ancla el año base. (RF-2, RF-10)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual.py -k ciclo` en verde.
      Bloqueada por alcance (2026-11-14, T0b de e6): el plan la pone en `tools/reentrenar_modelos.py` y `aprendizaje_continuo.py`, fuera de los ficheros de F-06 (`D:/csg/PM_IMPL/PLAN_MAESTRO_ESTRATEGICO/INFORME.md`, §3, Tanda 0). Siguiente acción: e6 le da dueño cuando el pronóstico de la 089 (Tanda 1) esté integrado.
- [ ] T5. Corrida real: proyección de un sistema con sus métricas por modelo y el ganador anotados aquí. (Todos)
      Hecho cuando: el informe está fuera de git y el resumen, sin datos de la distribuidora, anotado aquí.
      Bloqueada por datos y carril (2026-11-14, T0b de e6): la corrida real necesita los libros de la empresa, el registro de PBI y población del INEI y el BCRP de su región y el turno de GPU; el encargo prohíbe descargas, datos reales pesados y GPU (`D:/csg/PM_IMPL/ENCARGOS_E6.md`, «Prohibiciones»). Siguiente acción: el operador carga el registro y e6 la pone en el corredor.
- [x] T7. Lanzador del PIDE en la GPU en un paso, sin ganador fijo ni series inventadas. (RF-17, RF-18)
      Hecho cuando: `tests/test_lanzar_pronostico_pide_gpu.py` en verde y `--help` responde.
- [ ] T8. PBI y población como exógenas anuales, con su fuente, su huella y su fecha de publicación, en la competición y en la emisión. (RF-19, RF-20, RF-21, RF-22, RF-23)
      Hecho cuando: `pytest -q tests/test_proyeccion_anual_exogenas.py` en verde, con la prueba de que una cifra publicada después del origen se rechaza.
