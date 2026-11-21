# Tareas — Spec 002

Pendientes de aprobar el plan. Una tarea cada vez; cada una deja la suite en verde con
las tres variables `CSG_*` y la línea base de DGS idéntica (RF-20).

T1 y T5 se adelantaron el 2026-10-12 a petición del usuario («siempre debe ser universal;
Empresa A es un ejemplo de aplicación para pruebas»): no dependen de las capas. La
línea base con el perfil `electro_dunas` es idéntica a la de antes en TXT, red unida y
Access.

- [x] T1. Línea base de DGS con `tools/linea_base_dgs.py`, que guarda los SHA-256 en
      `output/linea_base_001.json` (fuera de git); añadirle la vía MDB y `workers=4`. (RF-20)
      Del 2026-10-28: la vía MDB en su propia línea base, `output/linea_base_001_mdb.json`,
      generada con `--mdb` sola; la herramienta rechaza TXT y MDB en una misma orden.
      Hecho cuando: `pytest -q tests/test_linea_base_001.py`, con las variables `CSG_*`, en verde.
- [x] T2. `tests/test_capas.py` y la tabla módulo → capa en `pyproject.toml`, con las
      excepciones medidas del plan. (RF-2 a RF-5)
      Hecho cuando: `pytest -q tests/test_capas.py` en verde y una violación nueva lo pone en rojo.
      Del 2026-11-03: lo cumplió la 065 con `tools/arquitectura.py` y el registro `docs/implementacion065/deuda_arquitectura.json`;
      `test_violacion_deliberada_en_modulos_arbitrarios` es la violación nueva que pone la prueba en rojo.
- [x] T3. Romper los 5 ciclos. (RF-4)
      Hecho cuando: la lista de ciclos permitidos de `test_capas.py` está vacía.
      Del 2026-11-03: eran 24 aristas en 8 grupos al medir de nuevo; `test_no_quedan_ciclos_entre_modulos` lo fija.
- [x] T4. Quitar las 12 importaciones de nombres privados. (RF-5)
      Hecho cuando: la lista de privados permitidos está vacía.
      Del 2026-11-03: eran 36 al medir de nuevo, no 12; pasan a nombres públicos y `test_no_quedan_nombres_privados_entre_modulos` lo fija.
- [x] T5. Perfil de empresa: CRS, patrón de SED de medición, escala y forma del
      alimentador; perfil de Empresa A; pedir el CRS si falta; manifiesto. (RF-31, RF-32, RF-33, RF-34, RF-35, RF-36, RF-37)
      Hecho cuando: `pytest -q tests/test_perfil_empresa.py` en verde y `git grep EPSG:32718 -- src tools`
      solo encuentra el perfil.
- [x] T6. Puertos, registro de módulos por entry points y lista de permitidos. (RF-7 a RF-15, RF-23 a RF-30)
      Hecho cuando: `pytest -q tests/test_modulos.py` en verde.
      Del 2026-11-03: `puertos.py`, `registro_modulos.py` y `escritores.py`. Tras integrar hay que ejecutar
      `pip install -e .`: hasta entonces la prueba de RF-28 falla y pide esa orden, como manda el requisito.
      La conversión aún crea sus lectores con `sources.adapter_for` y su DGS con `write_dgs`; el registro los declara
      y los carga, y el paso de la conversión al registro se hace con T7, cuando se muevan esos módulos.
Comparación del 2026-11-03: con T2, T3, T4 y T6 los DGS son idénticos a los de la revisión de partida `9dba2297`
(TXT con 1 y 4 procesos, red unida y Access). `output/linea_base_001*.json`, del 2026-11-02, ya no coincide en esa
misma revisión de partida por cambios ajenos a esta spec; `test_linea_base_001.py` falla hasta regenerarla.

Plan de lo abierto (2026-11-03): T7 a T9 mueven 250 módulos y tocan casi todas las pruebas, `tools/` y los
guiones de PowerFactory; van por capas, de abajo arriba, una por commit y con la línea base en cada una. T8 y T9
van después de T7. T11 reordena `frontend/src` y pide probar la web en el navegador real. T12 es el cierre.

- [x] T7. Mover los módulos a `dominio`, `puertos`, `aplicacion`, `adaptadores` y
      `presentacion`, con reexportaciones temporales. (RF-1)
      Hecho cuando: la tabla de `pyproject.toml` es la del plan y `test_capas.py` en verde sin excepciones de capa.
      Hecho en esta entrega (CAPAS-002, 4d): 355 módulos movidos a su paquete de capa por una transformación determinista (D:/csg/INTEGRA_54/capas_002/mover_a_capas.py); 444 módulos importan; test_capas en verde sin excepciones de capa.
- [x] T8. `vnr_etl` dentro de `convertersmartgrid.adaptadores.entrada.vnr`; `vnr-etl` sigue igual. (RF-6, RF-22)
      Hecho cuando: no queda `src/vnr_etl/` y `pytest -q tests/test_vnr_etl.py` en verde.
      Bloque P23 del 2026-11-08: implementación y consumidores trasladados, fachada única
      `src/vnr_etl.py` para los dos contratos de CLI, sin copia de implementación ni paquete paralelo.
      T8 conserva esta casilla abierta hasta la puerta de regresión real RF-20 del integrador;
      pruebas enfocadas, comparación sintética y revisión exacta en el HANDOFF externo indicado en el plan.
      RF y sus pruebas (una por RF; todas en el mapa `D:/csg/PM_IMPL/PISTA3/MARCAS-PISTA3/mapa_T_RF_pruebas.tsv`):
      RF-6: `tests/test_instalacion_programa.py::test_rueda_incluye_adaptador_vnr_y_ambos_launchers_sin_instalar` (línea 82).
      RF-22: `tests/test_vnr_etl.py::test_sqlite_probe_cli_real_codigo_y_json` (línea 175).
      Hecho el 2026-11-15 (MARCAS-PISTA3): en e182c823 no queda `src/vnr_etl/` (solo la fachada `src/vnr_etl.py` del CLI,
      RF-22), y la puerta de regresión real es la suite entera sobre el árbol de e182c823 con las 14 variables CSG_*: `D:/csg/INTEGRA_54/g107/integra_g12f13_82_183656.log` (línea 1202) «Puerta de calidad: 9582 pruebas, 0 fallidas, 0 omitidas.» Incluye `tests/test_vnr_etl.py` y `tests/test_linea_base_001.py`.
- [x] T9. Retirar las reexportaciones; `tools/` y las pruebas usan las rutas nuevas. (RF-21)
      Hecho cuando: `test_capas.py` no encuentra ningún módulo que solo reexporte.
      Compatibilidad pendiente: `src/vnr_etl.py` (CLI público conservado por contrato) y
      fachadas anteriores `convertersmartgrid.presentacion.web.sources` / `web.sources.vnr`.
      Hecho en esta entrega (CAPAS-002, 4d): sin reexportaciones (web.sources retirada); tools/ y las pruebas usan las rutas nuevas; vnr_etl queda como CLI público por contrato.
- [x] T10. Modelos Pydantic en las respuestas de la API y tipos del front generados. (RF-16, RF-17)
      Hecho cuando: `pytest -q tests/test_contrato_api.py` en verde.
      Del 2026-11-03: lo cumplió la 065. Quedan 7 de 133 rutas de `/api` sin modelo de respuesta; salen como tipo abierto.
- [x] T11. `frontend/src` en `api/`, `shared/`, `features/` y `app/`, con la regla de fronteras. (RF-18, RF-19)
      Hecho cuando: `npm run lint`, `npx tsc --noEmit -p .` y `npm run build` correctos.
      Implementación P23 frontend (2026-11-08): movidos los 47 archivos originales
      a api/shared/features/app, 49 finales por las extracciones compartidas;
      cero fachadas y excepciones. Lint con TypeScript AST ya instalado y
      negativas reales de imports, reexports, tipos, alias y dinámicos. API y
      tipos no dependen de features. El HTML de cinco renders React antes/después
      es idéntico; 470 declaraciones/sentencias y 3160 aperturas JSX conservadas.
      Evidencia externa `paralelo_p23_frontend_20261108/HANDOFF.md`.
      Los criterios automáticos se verifican con lint/test/typecheck/build;
      T11 conserva pendiente la revisión visual en navegador pedida arriba,
      que no está disponible. No equivale a cierre de T7/T8/T9/T12 ni de 002.
      RF y sus pruebas: RF-18 `frontend/test/fronteras.test.mjs` («002:RF-18 capas permitidas componen sin depender de otro
      feature», línea 20) y RF-19 la misma prueba («002:RF-19 frontera ilícita … falla incluso desde CLI», línea 35).
      Hecho el 2026-11-15 (MARCAS-PISTA3 v3; el auditor 0d la pasa de REAL a MARCAR: su «Hecho cuando:» es lint, tsc y build,
      sin navegador): sobre e182c823, `D:/csg/PM_IMPL/PISTA3/MARCAS-PISTA3/verde_002T11_lint_tsc_build.log` da rc_lint=0
      («Fronteras verificadas: api/shared/features/app, sin dependencias ilícitas.»), rc_tsc=0 y rc_build=0, y
      `verde_002T11_fronteras_test.log` 32 de 32.
- [x] T12. Validación: `grep -rnoE "002:RF-[0-9]+" tests frontend | sort -u` lista RF-1 a RF-37;
      línea base idéntica; `CODIGO_FUENTE.md` con las rutas nuevas.
      Hecho cuando: `grep -rnoE "002:RF-[0-9]+" tests frontend | sort -u` lista RF-1 a RF-37 y la línea base de la 001 sigue idéntica.
      Hecho el 2026-11-17 con CAPAS-002 v5 sobre 2c0b2823: el grep lista RF-1 a RF-38. La línea base se generó con el código de
      antes (árbol 18a8f86c), con el catálogo del proyecto que fija la prueba: 96 DGS de alimentador y la red unida por TXT,
      y 101 por Access. Con los módulos ya en su capa, `pytest tests/test_linea_base_001.py` da 3 passed, sin omitidas
      (D:/csg/INTEGRA_54/capas_002/linea_base_v5_0c02a607.log y linea_base_v5_SHA256SUMS.txt). `test_inventario` exige cada
      ruta nueva en `CODIGO_FUENTE.md`.
- [x] T13. Tope de rutas sin modelo de respuesta: `tools/rutas_sin_modelo.py` y `docs/architecture/rutas_sin_modelo.json`,
      con una lista que solo baja, al día con el código y con el motivo de cada ruta. (RF-38 y su aclaración)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q -rfs tests/test_contrato_api.py -k rf38` en verde y
      `python tools/rutas_sin_modelo.py --help` sale con 0.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_contrato_api.py -k rf38.
- [x] T14. Los guiones de `tools/` que nombran las pruebas y la aplicación existen: `tests/test_guiones_de_tools_existen.py`
      lee, sin ejecutar nada, cada `cargar_herramienta('x.py')`, `spec_from_file_location(… 'tools' / 'x.py')`, `_script`,
      `guion_pf`/`_guion_pf` y las listas del arnés, y exige el fichero; un sembrado prueba que no es ciego. (RF-39)
      Hecho cuando: falla por aserción sobre b0f95bdc (CAPAS-002 v5 superada: 81 cargas de pruebas y 25 guiones de la
      aplicación sin fichero) y pasa sobre 8d42bc30, con `test_capas`, `test_inventario` y `test_trazabilidad_specs` en verde.
      Hecho en la fila RUTAS-TOOLS (f7, 17-11); evidencias en D:/csg/PM_IMPL/RUTAS_TOOLS.
