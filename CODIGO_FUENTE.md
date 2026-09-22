# Índice del código fuente

- `src/igea_dgs/dataset.py`: parser de RED/CARGA/BD_Equipo y dataset reutilizable.
- `src/igea_dgs/model.py`: modelo eléctrico independiente por alimentador.
- `src/igea_dgs/geography.py`: UTM/CRS → WGS84, geometría de nodos y tramos, sidecar y validación geográfica.
- `src/igea_dgs/schema.py`: perfiles de tablas/campos DGS versionados.
- `src/igea_dgs/dgs.py`: escritor DGS, FID, cubículos, maniobras y capa gráfica.
- `src/igea_dgs/validate.py`: validación de esquema, estructura, conectividad, GPS y gráficos.
- `src/igea_dgs/batch.py`: conversión de uno, varios o todos los alimentadores.
- `src/igea_dgs/cli.py`: comandos estrictos y códigos de salida 0/2/3.
- `src/igea_dgs/domain/`: entidades eléctricas tipadas, fases, multiplicidad y longitudes.
- `src/igea_dgs/catalog/`: resolución exacta y fichas técnicas trazables.
- `src/igea_dgs/rules/`: reglas explícitas SED/TRAFOMIX.
- `src/igea_dgs/dgsio/`: construcción y lectura DGS estricta sin defaults físicos.
- `src/igea_dgs/validation/`: comparaciones independientes fuente-modelo-DGS-PowerFactory y KPIs.
- `src/igea_dgs/powerfactory/`: puerto, sesión, importador, adaptadores idempotentes y estudios protegidos.
- `src/igea_dgs/services/pipeline.py`: único orden de puertas G1–G6 para CLI/GUI nuevas.
- `src/igea_dgs/reporting/`: publicación atómica, hashes, manifiesto y sanitización.
- `src/igea_dgs/gui.py`: interfaz gráfica (selección de TXT, alimentadores, CRS y conversión).
- `src/igea_dgs/schemas/pf21_dgs_1_8_4.json`: perfil DGS genérico; no contiene datos de un alimentador de referencia.
- `run_gui.bat`: acceso directo Windows a la GUI.
- `pyproject.toml`: empaquetado instalable (`igea-dgs`, `igea-dgs-gui`).
- `tools/powerfactory_acceptance.py`: aceptación dentro de PowerFactory.
- `tests/`: pruebas automatizadas de la versión entregada.

La verificación automatizada no equivale a una corrida real en PowerFactory. `scripts/acceptance.ps1` registra un bloqueo verificable cuando faltan los tres TXT y nunca reutiliza `referencia/*.dgs` como entrada de construcción.
