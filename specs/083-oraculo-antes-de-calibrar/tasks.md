# Tareas — Spec 083

- [x] T1 Búsqueda de factores en el oráculo. (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py` en verde.
- [x] T2 Enganche en la calibración, con su informe. (RF-1, RF-4, RF-5, RF-6)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py tests/test_ajuste_proyecto_guion.py` en verde.
- [x] T4 Cuadre robusto: casi en cero, factor quieto, intervalo y Broyden. (RF-7, RF-10, RF-11, RF-12, RF-13)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py tests/test_ajuste_cabecera.py` en verde.
- [x] T5 Transformadores sin pedirlos y arranque de la última calibración. (RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py tests/test_sistema_web.py` en verde.
- [x] T6 El registro de cada cliente sin «maestro_lib», y la Q con su precisión. (RF-14, RF-15)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py tests/test_demanda_medida.py` en verde.
- [x] T7 Motores de flujo sobre la misma red. (RF-16, RF-17, RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_motores_flujo.py -rs` en verde y sin omitidas.
- [x] T8 Las muestras del reparto probabilístico en el oráculo. (RF-20)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py tests/test_ajuste_proyecto_guion.py` en verde.
- [x] T9 Tiempos por etapa y variaciones apagadas una vez. (RF-21, RF-22)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py tests/test_ajuste_proyecto_guion.py` en verde.
- [x] T10 Oráculo para las muestras con los factores cuadrados, y su entrada guardada. (RF-23, RF-24)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py` en verde.
- [x] T11 Tope de tiempo de las muestras en DIgSILENT. (RF-25)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py` en verde.
- [x] T12 El ajuste heredado que cambia el consumo y lo escrito por la aplicación no son del operador. (RF-26, RF-27)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T13 El arranque del oráculo aunque un alimentador no cuadre, y ese nombrado. (RF-28)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py` en verde.
- [x] T14 Las variaciones del conversor activas al calibrar. (RF-29)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py` en verde.
- [x] T15 Las fijas que con sus pérdidas pasan de la medida se corrigen hasta un tope. (RF-30)
      Hecho cuando: `pytest -q tests/test_oraculo_calibracion.py` en verde.
- [ ] T3 [DIgSILENT] Pisco: flujos y minutos con el arranque del oráculo. (RF-1, RF-5, RF-20, RF-21, RF-22)
      Hecho cuando: el informe de la calibración por la web da su modelo, evaluaciones y factores.
