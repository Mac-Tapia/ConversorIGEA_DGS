# Tareas — Spec 069

- [x] T1 Modelo: codificador, cabezas, contrato, carga y errores. (RF-1 a RF-9, RF-30 a RF-32)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k modelo` en verde.
- [x] T2 Clase `ninguna` en el corpus y en el intérprete. (RF-10 a RF-16)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k ninguna` en verde.
- [x] T3 Puerta de rechazo en la decisión y el informe. (RF-17 a RF-22)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k rechazo` en verde.
- [x] T4 Calibración de temperatura y umbral. (RF-23 a RF-27)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k calibra` en verde.
- [x] T5 Herramientas y frases de operador de las tareas flojas. (RF-28, RF-29)
  Hecho cuando: `pytest -q tests/test_interprete_codificador.py -k integral` en verde.
- [ ] T6 Ejecución real única con `tools/asistente_entrenar.py --integral`.
  Hecho cuando: el informe da candidato, estado del registro y puntero antes y después, por familia y con rechazo.
