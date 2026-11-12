# Tareas — Spec 089

- [x] T1. Datos vivos, equivalencia y lector de clientes. (RF-1 a RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_demanda.py` en verde.
- [x] T2. Limpieza y sentido de las series. (RF-18 a RF-28, RF-54)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde.
- [x] T3. Las tres clases y el apoyo. (RF-29 a RF-37, RF-55)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde.
- [x] T4. Métodos, backtest, exógenas y salida. (RF-38 a RF-53)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde.
- [ ] T5. Backtest real de 2026 con la herramienta. (RF-38 a RF-43)
      Hecho cuando: el informe está fuera de git y sus cifras, sin datos de la distribuidora, anotadas aquí.
- [x] T6. Modelos, conjunto y puerta. (RF-56 a RF-88)
      Hecho cuando: `tests/test_pronostico_demanda.py` en verde, en la GPU.
- [x] T8. Entrenamiento por alimentador en la GPU, sin rutas fijas. (RF-89, RF-90)
      Hecho cuando: `tests/test_entrenar_alimentadores_gpu.py` en verde y `--help` responde.
- [x] T9. Una ventana de entrenamiento por día en las redes. (RF-91)
      Hecho cuando: `tests/test_pronostico_demanda.py::test_las_redes_toman_una_ventana_por_dia` en verde, en la GPU.
- [ ] T7. Corrida larga real de todos los modelos.
      Hecho cuando: cada clase, magnitud y horizonte tiene su informe fuera de git, con la decisión y sus cifras anotadas aquí.
