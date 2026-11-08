# Tareas 100

- [ ] T1. La matriz de casos y su validación, sin convenciones de una empresa. (RF-1, RF-4)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py -k matriz` en verde.
- [ ] T2. `tools/aceptacion_version.py`: recorrido en serie, relanzado desde donde quedó e informe por caso. (RF-2, RF-3, RF-5)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py -k recorrido` en verde.
- [ ] T3. Veredicto de la versión y paso de los fallos a comprobación permanente. (RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py -k veredicto` en verde.
- [ ] T4. [DIgSILENT] Primera corrida completa de la matriz sobre una versión candidata, en proyectos de prueba. (Todos)
      Hecho cuando: el informe de la versión da todos los casos aceptados.
