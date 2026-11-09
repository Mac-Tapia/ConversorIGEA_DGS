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
- [ ] T5. Corrida real: proyección de un sistema con sus métricas por modelo y el ganador anotados aquí. (Todos)
      Hecho cuando: el informe está fuera de git y el resumen, sin datos de la distribuidora, anotado aquí.
