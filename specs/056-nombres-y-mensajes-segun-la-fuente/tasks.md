# Tareas — Spec 056

- [ ] T1. La fuente en el dataset y en el modelo, y los textos con sus palabras. (RF-3, RF-4, RF-5, RF-7)
      Hecho cuando: las pruebas que citan sus RF pasan y los TXT dan el mismo DGS que antes.
      Avance del 2026-11-02: el dataset y el modelo llevan su fuente, y la cabecera del DGS la dice (RF-3). CA101 y SM218 del TXT
      salen idénticos byte a byte al código anterior; una red de Access ya no lleva «CYMDIST» ni «IGEA». Faltan RF-4, RF-5 y los
      mensajes de aviso con las palabras de cada fuente.
      Avance del 2026-11-03: `model.palabras_de(fuente)` da las palabras de los avisos del modelo, de la validación y de la
      geografía (las del TXT, letra a letra las de antes; el DGS no lleva avisos y no cambia); la web solo nombra CYMDIST en
      la entrada de los TXT (RF-5). `tests/test_palabras_de_la_fuente.py` en verde. Falta RF-4 en el catálogo de datos de los
      estudios (`studies.py`: «[SUBSTATION] del BD_Equipo…», escrito para el TXT de una empresa), que necesita la fuente en el
      estudio.
- [x] T2. El nombre del proyecto con su fuente, y la prueba de punta a punta. (RF-1, RF-2, RF-6)
      Hecho cuando: las pruebas que citan 056:RF-1, RF-2 y RF-6 pasan.
      Hecho el 2026-11-03: `<sello>_CSG_<TXT|MDB|VNR>_<red>`, con la fuente leída de la cabecera del DGS; un DGS sin ella da el
      nombre de antes y ningún guion reconoce proyectos por su nombre. Un VNR-GIS sintético convertido de punta a punta no
      deja IGEA, CYMDIST, TXT, BD_Equipo ni RED export en ninguna salida. `pytest -q tests/test_palabras_de_la_fuente.py`.
- [ ] T3. [DIgSILENT] NJA202 importado por la web sin esas palabras. (Todos)
      Hecho cuando: se cumple su criterio de finalización.
