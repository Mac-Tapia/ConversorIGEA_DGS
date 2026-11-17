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
      Hecho en <HASH-L4> (LOTE-4, ARQ-SUBSISTEMAS); pruebas: tests/test_arquitectura_generada.py.
