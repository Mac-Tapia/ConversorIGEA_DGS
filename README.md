# IGEA/CYMDIST → DIgSILENT DGS Universal Engine v2

Conversor modular para transformar los archivos TXT `RED`, `CARGA` y `BD_Equipo` exportados desde IGEA/CYMDIST en archivos DGS para DIgSILENT PowerFactory.

**Universal por diseño:** no está limitado a una empresa, a un número fijo de alimentadores ni a códigos como IN111/TA121. Cualquier export CYMDIST/IGEA con otras denominaciones de NetworkID, tipos de línea o CRS regionales se puede cargar; los nombres y conteos salen de los TXT, no de listas fijas en el código.

## Interfaz gráfica (recomendada)

Doble clic en `run_gui.bat`, o:

```bash
set PYTHONPATH=src
python -m igea_dgs.gui
```

En la ventana (flujo didáctico):

1. Elija los tres TXT: **RED**, **CARGA** y **BD_Equipo** — la GUI avisa cuando están listos.
2. Pulse **Cargar / listar alimentadores** — diálogo al terminar con el número de alimentadores.
3. Seleccione **uno**, **varios** (Ctrl/Mayús+clic) o **todos** (checkbox / botón).
4. Pulse **Convertir a DGS** — progreso N/M, diálogo al terminar y opción de abrir la carpeta.

Sin `pyproj` puede listar alimentadores y convertir **desactivando georreferenciación**. Con GPS/diagrama debe estar instalado vía `requirements.txt`.

## Instalación (otra máquina local)

**Producción / GUI** (paquete + `pyproj`):

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

**Desarrollo + tests:**

```bash
python -m pip install -r requirements-dev.txt
```

Alternativa con extras de `pyproject.toml`:

- Sin GPS/diagrama: `pip install -e .` y use `--no-geography` / desactive georreferenciación en la GUI.
- Solo producción (con geografía): `pip install -e ".[geo]"`.
- Desarrollo + tests: `pip install -e ".[geo,dev]"`.

Entradas de consola: `igea-dgs` y `igea-dgs-gui`. `run_gui.bat` instala solo `requirements.txt` (sin pytest) si faltan dependencias.

### Interfaz gráfica (pruebas y producción)

1. Elija RED, CARGA y BD_Equipo — la GUI avisa cuando los tres están listos.
2. Pulse **Cargar / listar alimentadores** — avisa al terminar con el conteo.
3. Convierta **uno** (clic), **varios** (Ctrl+clic / Mayús+clic / Seleccionar todos) o **todos** (checkbox).
4. Al terminar la conversión muestra resumen OK/fallidos y ofrece abrir la carpeta de salida.

## Principio de arquitectura

El motor **no necesita un archivo DGS de referencia** para convertir. La compatibilidad de formato se describe en un perfil versionado (`src/igea_dgs/schemas/pf21_dgs_1_8_4.json`) que contiene únicamente nombres de tablas, campos y tipos DGS. No contiene nodos, FID, líneas, cargas, nombres ni datos eléctricos de un alimentador de ejemplo.

La fuente de verdad para cada conversión es:

- `RED_*.txt`: alimentadores, cabeceras, fuentes, nodos, secciones, configuración de línea, maniobras y nodos intermedios.
- `CARGA_*.txt`: ubicación de cargas y datos de cliente/carga.
- `BD_Equipo_*.txt`: parámetros eléctricos de tipos de línea/cable y otros catálogos CYMDIST.

## Estado del proyecto (diagnóstico)

| Ítem | Estado |
| ---- | ------ |
| Motor de conversión (dataset → model → DGS → validate) | Listo |
| CLI `list` / `convert` / `gui` | Listo |
| Interfaz gráfica de archivos | Listo (`gui.py` + `run_gui.bat`) |
| Empaquetado `pyproject.toml` | Listo |
| Dependencia `pyproj` (GPS) | En `requirements.txt` (+ extra `[geo]`) — opcional si convierte sin geografía |
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
        ├── selector (cualquier NetworkID / nombre corto)
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

Convertir un alimentador (use el nombre corto que aparezca en `list`, el de su export):

```bash
PYTHONPATH=src python -m igea_dgs.cli convert \
  --red RED_export.txt \
  --loads CARGA_export.txt \
  --equipment BD_Equipo.txt \
  --feeder NOMBRE_ALIMENTADOR \
  --source-crs EPSG:XXXXX \
  --out-dir output
```

Convertir todos los alimentadores del lote cargado:

```bash
PYTHONPATH=src python -m igea_dgs.cli convert \
  --red RED_export.txt \
  --loads CARGA_export.txt \
  --equipment BD_Equipo.txt \
  --all \
  --source-crs EPSG:XXXXX \
  --out-dir output/all
```

## Tipos de línea y alimentadores

Todos los alimentadores presentes en los TXT cargados deben poder convertirse. Si un `LineCableID` no está en `BD_Equipo`:

1. Se aplica un alias JSON explícito (`--aliases` / GUI), si existe.
2. Si no, se elige automáticamente el ID **más cercano y único** del catálogo cargado.
3. Si no hay coincidencia única, se usa el `DEFAULT` del medio (aéreo/cable) **sin omitir la sección** ni bloquear el alimentador.

Topología rota (nodos faltantes, FID, cubículos, etc.) sigue siendo error fatal en modo estricto.

## Equivalencias externas (opcional)

JSON de aliases de **su** catálogo (plantilla en `config/line_type_aliases.example.json`):

```json
{
  "CODIGO_AUSENTE_EN_CATALOGO": "CODIGO_EXISTENTE_EN_BD_EQUIPO"
}
```

```bash
... convert --feeder NOMBRE_ALIMENTADOR --aliases aliases.json --out-dir output
```

Los destinos deben existir en el `BD_Equipo` cargado. Si un destino no está, el motor usará auto-mapeo o `DEFAULT`. No hay códigos de línea de una empresa embebidos en el motor.

## Georreferenciación

Se transforma `CoordX/CoordY` con `pyproj` desde el `--source-crs` **de su export** (cualquier EPSG) a WGS84. Elija el CRS de la empresa/región que entregó los TXT; el valor por defecto es solo un ejemplo editable. Genera GPS en terminales, diagrama `IntGrf*` y sidecars `*_geography.json`.

## Pruebas

Instale deps de desarrollo: `pip install -r requirements-dev.txt`.

Sin TXT, pasan las unitarias (schema, independencia, gráficos, resolución de tipos). Con TXT:

```bat
set IGEA_TXT_DIR=D:\ruta\a\carpeta_con_RED_CARGA_BD
set PYTHONPATH=src
pytest -q
```

También: `IGEA_RED`, `IGEA_LOADS`, `IGEA_EQUIPMENT` (rutas a cada archivo). Si faltan, las pruebas de integración hacen **skip** claro (no `FileNotFoundError`).

Aceptación en PowerFactory: `docs/POWERFACTORY_ACCEPTANCE.md` y `tools/powerfactory_acceptance.py`.

## Resultado de ejemplo (IN111)

En un export concreto con `--source-crs EPSG:32718`, IN111 produjo del orden de ~1,936 `ElmTerm`, ~1,934 `ElmLne`, ~383 `ElmLod`, ~791 `StaSwitch` y cobertura geográfica 100 %. **Esos conteos no son fijos**: dependen del alimentador y de los TXT cargados. El número total de alimentadores también varía por export (puede ser más o menos que en un lote anterior). Artefactos de ejemplo en `output/IN111_CONVERTIDO/`.
