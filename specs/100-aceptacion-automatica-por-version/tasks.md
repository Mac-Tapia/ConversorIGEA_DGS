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
- [x] T7. `tools/aceptacion_version.py` toma un candado de su carpeta de salida y sale con 3 si otra viva la tiene. (RF-14)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py -k rf14` en verde, con su rojo por aserción sobre cf484bd4.
      Hecho el 2026-11-26 (agente cal-borrado, entregado por parche a d8): rojo y verde en D:/csg/PM_IMPL/CAL_BORRADO.
- [x] T8. `tools/sistema_web.py` no empieza si otro `sistema_web.py` vivo tiene el mismo espacio. (RF-15)
      Hecho cuando: `pytest -q tests/test_sistema_web.py -k rf15` en verde, con su rojo por aserción sobre cf484bd4.
      Hecho el 2026-11-26 (agente cal-borrado): rojo y verde en D:/csg/PM_IMPL/CAL_BORRADO.
- [x] T9. La web pasa a la importación los proyectos de sus trabajos pendientes (`--conservar`) y la retirada de versiones anteriores no los borra. (RF-16)
      Hecho cuando: `pytest -q tests/test_carpeta_pf.py -k rf16` en verde, con su rojo por aserción sobre cf484bd4.
      Hecho el 2026-11-26 (agente cal-borrado): rojo y verde en D:/csg/PM_IMPL/CAL_BORRADO.
- [x] T10. La calibración con un proyecto que ya no está deja el error claro en cada informe, también con los bancos que faltan. (RF-17)
      Hecho cuando: `pytest -q tests/test_ajuste_proyecto_guion.py -k rf17` en verde, con su rojo sobre cf484bd4 (el `AttributeError` del 25-11).
      Hecho el 2026-11-26 (agente cal-borrado): rojo y verde en D:/csg/PM_IMPL/CAL_BORRADO.
- [x] T11. Sello de la versión aceptada, la orden `--sellar` para un informe ya corrido, la matriz validada con el sello de su versión y los espacios de la aceptación anotados. (RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24)
      Hecho cuando: `pytest -q tests/test_aceptacion_version.py tests/test_matriz_estudios.py` en verde, con el rojo por aserción de las pruebas nuevas sobre 1ec36ff5.
      Hecho el 2026-11-28 (rama `agente/validar-y-ciclo`, entregado por parche): rojo por aserción sobre 1ec36ff5 y verde en D:/csg/PM_IMPL/validar_y_ciclo.
