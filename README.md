# IGEA/CYMDIST → DIgSILENT DGS Universal Engine v2

Conversor modular para transformar los archivos TXT `RED`, `CARGA` y `BD_Equipo` exportados desde IGEA/CYMDIST en archivos DGS para DIgSILENT PowerFactory.

## Interfaz gráfica (recomendada)

Doble clic en `run_gui.bat`, o:

```bash
set PYTHONPATH=src
python -m igea_dgs.gui
```

En la ventana:

1. Elija los tres TXT: **RED**, **CARGA** y **BD_Equipo** (catálogo de equipos; no es una base SQL).
2. Elija carpeta de salida y, si aplica, un JSON de aliases de tipos.
3. Pulse **Cargar / listar alimentadores**, seleccione uno o varios (o «Convertir todos»).
4. Configure CRS (por defecto `EPSG:32718` → WGS84) y pulse **Convertir a DGS**.

Sin `pyproj` puede listar alimentadores y convertir **desactivando georreferenciación**. Con GPS/diagrama: `pip install pyproj`.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

Entradas de consola tras instalar: `igea-dgs` y `igea-dgs-gui`.

## Principio de arquitectura

El motor **no necesita un archivo DGS de referencia** para convertir. La compatibilidad de formato se describe en un perfil versionado (`src/igea_dgs/schemas/pf21_dgs_1_8_4.json`) que contiene únicamente nombres de tablas, campos y tipos DGS. No contiene nodos, FID, líneas, cargas, nombres ni datos eléctricos de un alimentador de ejemplo.

La fuente de verdad para cada conversión es:

- `RED_*.txt`: alimentadores, cabeceras, fuentes, nodos, secciones, configuración de línea, maniobras y nodos intermedios.
- `CARGA_*.txt`: ubicación de cargas y datos de cliente/carga.
- `BD_Equipo_*.txt`: parámetros eléctricos de tipos de línea/cable y otros catálogos CYMDIST.

## Estado del proyecto (diagnóstico)

| Ítem | Estado |
|------|--------|
| Motor de conversión (dataset → model → DGS → validate) | Listo |
| CLI `list` / `convert` / `gui` | Listo |
| Interfaz gráfica de archivos | Listo (`gui.py` + `run_gui.bat`) |
| Empaquetado `pyproject.toml` | Listo |
| Dependencia `pyproj` (GPS) | Requerida solo con geografía |
| TXT de entrada en el repo | No incluidos — hay que suministrarlos |
| Base de datos SQL/Access | No aplica — `BD_Equipo` es TXT |
| Aceptación en PowerFactory | Requiere PF + importar el `.dgs` |

## Estructura

```text
TXT IGEA/CYMDIST
   │
   ├── RED
   ├── CARGA
   └── BD_Equipo
        │
        ▼
CymdistDataset (una sola lectura)
        │
        ├── selector IN111
        ├── selector TA121
        ├── varios selectores
        └── --all
        │
        ▼
FeederModel aislado
        │
        ▼
DGS Writer + perfil versionado
        │
        ▼
Validador estricto
```

## Comandos CLI

Listar alimentadores:

```bash
PYTHONPATH=src python -m igea_dgs.cli list \
  --red RED_030826.txt \
  --loads CARGA_030826.txt \
  --equipment BD_Equipo.txt
```

Convertir un alimentador:

```bash
PYTHONPATH=src python -m igea_dgs.cli convert \
  --red RED_030826.txt \
  --loads CARGA_030826.txt \
  --equipment BD_Equipo.txt \
  --feeder IN111 \
  --out-dir output
```

Convertir todos:

```bash
PYTHONPATH=src python -m igea_dgs.cli convert \
  --red RED_030826.txt \
  --loads CARGA_030826.txt \
  --equipment BD_Equipo.txt \
  --all \
  --out-dir output/all
```

## Modo estricto

Es el modo predeterminado. Un alimentador no se genera si falta tipo en `BD_Equipo`, hay nodos/configuraciones incompletas, FID duplicados, punteros colgantes, cubículos incorrectos, etc. Los tipos faltantes no se sustituyen por `DEFAULT`.

## Equivalencias externas

JSON externo aprobado por Ingeniería:

```json
{
  "CODIGO_ORIGEN": "CODIGO_APROBADO"
}
```

```bash
... convert --feeder ALIMENTADOR --aliases aliases.json --out-dir output
```

## Georreferenciación

Por defecto se transforma `CoordX/CoordY` con `pyproj` desde `--source-crs` (p. ej. `EPSG:32718`) a WGS84. Genera GPS en terminales, diagrama `IntGrf*` y sidecars `*_geography.json`.

## Pruebas

```bash
PYTHONPATH=src pytest -q
```

Aceptación en PowerFactory: `docs/POWERFACTORY_ACCEPTANCE.md` y `tools/powerfactory_acceptance.py`.

## Resultado reproducido IN111

Con los TXT suministrados y `--source-crs EPSG:32718`: 1,936 `ElmTerm`, 1,934 `ElmLne`, 383 `ElmLod`, 791 `StaSwitch`, cobertura geográfica 100 %. Artefactos en `output/IN111_CONVERTIDO/`.
