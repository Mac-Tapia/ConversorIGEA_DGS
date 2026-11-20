# Tareas 100

- [x] T1. La matriz de casos y su validación, sin convenciones de una empresa. (RF-1, RF-4)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py -k matriz` en verde.
      Hecho en 016498fc (LOTE-1); pruebas: tests/test_aceptacion_version.py -k matriz.
- [x] T2. `tools/aceptacion_version.py`: recorrido en serie, relanzado desde donde quedó e informe por caso. (RF-2, RF-3, RF-5)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py -k recorrido` en verde.
      Hecho en 016498fc (LOTE-1); pruebas: tests/test_aceptacion_version.py -k recorrido.
- [x] T3. Veredicto de la versión y paso de los fallos a comprobación permanente. (RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py -k veredicto` en verde.
      Código de T1 a T3 (2026-11-16, f7): `config/aceptacion/matriz.json`, `tools/aceptacion_version.py` y `tests/test_aceptacion_version.py`; los fallos dejan su borrador en `docs/regresiones/pendientes/`.
      Hecho en 016498fc (LOTE-1); pruebas: tests/test_aceptacion_version.py -k veredicto.
- [ ] T4. [DIgSILENT] Primera corrida completa de la matriz sobre una versión candidata, en proyectos de prueba. (Todos)
      Hecho cuando: el informe de la versión da todos los casos aceptados.
- [x] T5. La matriz estudio × motor en el dominio, su ruta `GET /api/estudios/matriz` y el recurso del estado de las specs para el programa instalado. (RF-8, RF-9, RF-10, RF-11, RF-13)
      Hecho cuando: `pytest -q tests/test_matriz_estudios.py` en verde, con su rojo sobre faf67626 (el módulo no existe).
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T6. La marca «Sin validar» o el apagado «No disponible» en la web, en cada estudio con el motor de su botón. (RF-12)
      Hecho cuando: `node --test test/matrizEstudios.test.mjs` y `tsc` en verde, con su rojo sobre faf67626.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
