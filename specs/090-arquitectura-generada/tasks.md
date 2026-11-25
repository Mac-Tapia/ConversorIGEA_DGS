# Tareas — Spec 090

- [x] T1. `tools/generar_arquitectura.py` y `docs/architecture/subsistemas.json`: catálogo de ficheros y cifras. (RF-1 a RF-4, RF-8 a RF-10)
      Hecho cuando: `pytest -q tests/test_arquitectura_generada.py -k "catalogo or fichero or cifras or comprobar"` en verde.
- [x] T2. El asistente y su equipo en el catálogo, comparados con el código real. (RF-5 a RF-7)
      Hecho cuando: `pytest -q tests/test_arquitectura_generada.py -k "tareas or roles or etapas"` en verde.
- [x] T3. Ganchos de git y `.gitattributes`. (RF-11 a RF-14)
      Hecho cuando: `pytest -q tests/test_arquitectura_generada.py -k gancho` en verde.
- [x] T4. `docs/ARQUITECTURA.md` sin las cifras que cambian, con sus citas y su tabla de correcciones. (RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_arquitectura_generada.py tests/test_preguntas_entregables.py` en verde.
- [x] T5. `docs/ARQUITECTURA.md` al día con las specs 102 y 107 a 112, y cada paquete explicado. (RF-17)
      Hecho cuando: `pytest -q tests/test_arquitectura_generada.py tests/test_preguntas_entregables.py` en verde.
- [x] T6. Cada fichero con su subsistema: el VAD y el VNR, el PIT, la biblioteca normativa y las fuentes de la empresa, el
      gobierno de modelos, la web y las pestañas nuevas; el frontend por carpetas, sin las rutas de antes de `app/`, `shared/` y
      `features/`. (RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_arquitectura_generada.py` en verde, sin la sección
      «Sin subsistema asignado» en `docs/ARQUITECTURA_CATALOGO.md`.
      Hecho en ecad83ea (LOTE-4, ARQ-SUBSISTEMAS); pruebas: tests/test_arquitectura_generada.py.
- [x] T7. El C4 profesional al día y `tools/generar_c4.py` para sus cifras: un componente por grupo de subsistemas, con sus ficheros del catálogo, la biblioteca
      normativa como contenedor, el PIT y el VAD y VNR con sus componentes, sin «Módulos por asignar», los enlaces a ecad83ea y
      la página interactiva con los mismos componentes. (RF-19)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_arquitectura_c4_al_dia.py tests/test_interactive_architecture.py`
      en verde, con las PNG y el PDF del C4 regenerados desde la página.
      Hecho en la fila ARQ-C4 (f7, 17-11); pruebas: tests/test_arquitectura_c4_al_dia.py tests/test_interactive_architecture.py.
- [x] T8. El C4 completo y claro: motores abiertos, VNR de la Guía aparte del VNR-GIS y del VAD, los carriles del código
      dibujados, el pseudocódigo de cada flujo en `docs/architecture/pseudocodigo.md` y en la página, `docs/ARQUITECTURA.md` con
      los seis carriles, y las PNG y el PDF regenerados con `node frontend/scripts/exportar-c4.mjs`. (RF-20 a RF-26)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -rfs tests/test_arquitectura_c4_al_dia.py tests/test_interactive_architecture.py tests/test_arquitectura_generada.py tests/test_inventario.py tests/test_docs_vivos.py`
      en verde, y `node frontend/scripts/exportar-c4.mjs` termina con 0 y una página del PDF por vista.
      Hecho el 2026-11-25: 76 pruebas de `tests/test_arquitectura_c4_al_dia.py` y `tests/test_interactive_architecture.py` en verde, y la
      exportación con 10 PNG y el PDF de 21 páginas (portada, 10 vistas y 10 bloques).
