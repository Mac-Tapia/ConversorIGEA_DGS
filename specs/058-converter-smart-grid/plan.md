# Plan — Spec 058

Orden pensado para que el repositorio funcione al final de cada paso.

1. Punto de vuelta: un commit del trabajo pendiente antes de renombrar (lo autoriza el usuario),
   para que el renombrado sea un commit aparte y revisable.
2. Paquete y comandos (RF-2): `git mv src/igea_dgs src/convertersmartgrid`; `pyproject.toml`
   (nombre, comandos, datos del paquete); reemplazo de `igea_dgs` → `convertersmartgrid` e
   `igea-dgs` → `convertersmartgrid` en código, pruebas, guiones y frontend; `pip install -e .`.
3. Variables (RF-3): `IGEA_` → `CSG_` en código, pruebas, guiones, documentos y memoria.
4. Textos visibles (RF-1, RF-4, RF-5, RF-7): título de la web, cabecera del DGS, sigla de los
   proyectos (`_CSG_`), carpeta por defecto, skills (`.claude/skills/convertersmartgrid-*`),
   lanzador, README, CLAUDE.md, CODIGO_FUENTE.md, docs y specs. Las citas de RF-9 se marcan.
5. Prueba (RF-8, RF-9): `tests/test_nombre_converter_smart_grid.py` recorre `git ls-files` y falla si alguno
   menciona IGEA fuera de una lista corta de excepciones con su motivo.
6. Líneas base (RF-10): se regeneran solo por la cabecera; se comprueba que el resto del DGS es
   idéntico.
7. Carpeta principal (RF-6), lo último, con la web parada: renombrar la carpeta, rehacer `.venv`
   (sus rutas son absolutas), el acceso directo del escritorio y las rutas absolutas guardadas en
   `output/web/*/workspace.json`. La sesión de Claude Code se reabre en la carpeta nueva.

Alternativa descartada: dejar `igea_dgs` como alias de importación. Mantendría el nombre que el
usuario pidió quitar y dos nombres para lo mismo.
