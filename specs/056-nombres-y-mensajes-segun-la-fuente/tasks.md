# Tareas — Spec 056

- [x] T1. La fuente en el dataset y en el modelo, y los textos con sus palabras. (RF-3, RF-4, RF-5, RF-7)
      Hecho cuando: las pruebas que citan sus RF pasan y los TXT dan el mismo DGS que antes.
      Avance del 2026-11-02: el dataset y el modelo llevan su fuente, y la cabecera del DGS la dice (RF-3). CA101 y SM218 del TXT
      salen idénticos byte a byte al código anterior; una red de Access ya no lleva «CYMDIST» ni «IGEA». Faltan RF-4, RF-5 y los
      mensajes de aviso con las palabras de cada fuente.
      Avance del 2026-11-03: `model.palabras_de(fuente)` da las palabras de los avisos del modelo, de la validación y de la
      geografía (las del TXT, letra a letra las de antes; el DGS no lleva avisos y no cambia); la web solo nombra CYMDIST en
      la entrada de los TXT (RF-5). `tests/test_palabras_de_la_fuente.py` en verde. Falta RF-4 en el catálogo de datos de los
      estudios (`studies.py`: «[SUBSTATION] del BD_Equipo…», escrito para el TXT de una empresa), que necesita la fuente en el
      estudio.
      Hecho el 2026-11-03: `studies.estudios_de(fuente)` da el catálogo con las palabras de la fuente
      (`PALABRAS_ESTUDIOS`); el del TXT sigue siendo `ESTUDIOS`, sin las cifras de una empresa («24 subestaciones»,
      los kWh del export). Lo que un VNR-GIS no trae (energía, clientes, impedancia de las SET) se dice con sus palabras
      y bloquea como ausente; `auditar_datos` y `tools/base_scenario.py` usan la fuente del dataset. El DGS no cambia:
      el catálogo no lo escribe. La hoja de parámetros del libro del catálogo tampoco nombra una fuente.
      `pytest -q tests/test_palabras_de_la_fuente.py tests/test_codigo_operativo_y_conductores.py tests/test_fuente_en_el_dgs.py
      tests/test_estudios_pf.py` en verde, y `tests/test_studies.py tests/test_catalog.py` con los tres TXT reales, sin omitidas.
- [x] T2. El nombre del proyecto con su fuente, y la prueba de punta a punta. (RF-1, RF-2, RF-6)
      Hecho cuando: las pruebas que citan 056:RF-1, RF-2 y RF-6 pasan.
      Hecho el 2026-11-03: `<sello>_CSG_<TXT|MDB|VNR>_<red>`, con la fuente leída de la cabecera del DGS; un DGS sin ella da el
      nombre de antes y ningún guion reconoce proyectos por su nombre. Un VNR-GIS sintético convertido de punta a punta no
      deja IGEA, CYMDIST, TXT, BD_Equipo ni RED export en ninguna salida. `pytest -q tests/test_palabras_de_la_fuente.py`.
- [ ] T3. [DIgSILENT] NJA202 importado por la web sin esas palabras. (Todos)
      Hecho cuando: se cumple su criterio de finalización.
