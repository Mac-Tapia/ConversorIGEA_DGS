# Índice del código fuente

- `src/igea_dgs/dataset.py`: parser de RED/CARGA/BD_Equipo y dataset reutilizable.
- `src/igea_dgs/model.py`: modelo eléctrico independiente por alimentador.
- `src/igea_dgs/geography.py`: UTM/CRS → WGS84, geometría de nodos y tramos, sidecar y validación geográfica.
- `src/igea_dgs/schema.py`: perfiles de tablas/campos DGS versionados.
- `src/igea_dgs/dgs.py`: escritor DGS, FID, cubículos, maniobras y capa gráfica.
- `src/igea_dgs/validate.py`: validación de esquema, estructura, conectividad, GPS y gráficos.
- `src/igea_dgs/batch.py`: conversión de uno, varios o todos los alimentadores.
- `src/igea_dgs/cli.py`: interfaz de línea de comandos (`list`, `convert`, `gui`).
- `src/igea_dgs/gui.py`: interfaz gráfica (selección de TXT, alimentadores, CRS y conversión).
- `src/igea_dgs/schemas/pf21_dgs_1_8_4.json`: perfil DGS genérico; no contiene datos de un alimentador de referencia.
- `run_gui.bat`: acceso directo Windows a la GUI.
- `pyproject.toml`: empaquetado instalable (`igea-dgs`, `igea-dgs-gui`).
- `tools/powerfactory_acceptance.py`: aceptación dentro de PowerFactory.
- `tests/`: pruebas automatizadas de la versión entregada.

El resultado reproducido para IN111 está en `output/IN111_CONVERTIDO/`.
