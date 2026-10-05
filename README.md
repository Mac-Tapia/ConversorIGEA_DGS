# IGEA/CYMDIST → DIgSILENT DGS Universal Engine v2

Conversor modular para transformar los archivos TXT `RED`, `CARGA` y `BD_Equipo` exportados desde IGEA/CYMDIST en archivos DGS para DIgSILENT PowerFactory.

**Universal por diseño:** no está limitado a una empresa, a un número fijo de alimentadores ni a códigos como IN111/TA121. Cualquier export CYMDIST/IGEA con otras denominaciones de NetworkID, tipos de línea o CRS regionales se puede cargar; los nombres y conteos salen de los TXT, no de listas fijas en el código.

### Tres fuentes aisladas y aceptación auditable

La interfaz admite **tres TXT**, **MDB/Access** y **VNR-GIS**. Cada carga crea una
ejecución inmutable propia; nunca completa una modalidad con archivos de otra. La
tabla permite seleccionar uno, varios o todos los alimentadores. Si faltan nodos,
tramos o parámetros, trabaja sobre una copia reconstruida auditable: conserva primero
el valor original, completa por catálogo exacto/fabricante/global y deja cualquier
supuesto de ingeniería visible. Los archivos primarios nunca se mezclan ni se mutan.

Para ejecutar y documentar el flujo independiente hasta DGS/PowerFactory use
`python tools/accept_three_sources.py --help`. El procedimiento, los niveles de
evidencia y las referencias científicas están en
[`docs/runbooks/three-source-production-acceptance.md`](docs/runbooks/three-source-production-acceptance.md).
El ejecutor acepta `--feeder` repetido o `--all-feeders`, empresa, periodo, CRS y
política de reconstrucción; registra hashes antes/después, decisiones y clase de
convergencia. Una convergencia lograda reduciendo o desconectando carga exige revisión
del operador y no se declara lista para producción.

## Interfaz web (recomendada)

Doble clic en `run_gui.bat`, o:

```bash
set PYTHONPATH=src
python -m igea_dgs.web          # o: igea-dgs-web  /  igea-dgs web
```

Abre el navegador en `http://127.0.0.1:8765/`. Es una API **FastAPI** que sirve un
front **React + TypeScript** (`frontend/`) y usa el mismo motor `igea_dgs`, sin
reescribirlo.

1. **Entrada**: suelte los tres TXT juntos y cada uno va a su casilla por las tablas
   que trae dentro, no por el nombre. También se pueden subir de uno en uno, o indicar
   una ruta de este equipo (útil para la base `.mdb`, que pesa cientos de MB).
2. **Cargar / listar alimentadores**: inventario, integridad y cobertura del catálogo
   de conductores. Si el catálogo no cubre la red, lo avisa antes de convertir.
3. **Seleccione** con las casillas (Mayús+clic = rango), filtre y ordene.
4. **Convertir** uno, varios o todos: progreso en vivo, cancelable; lo ya convertido
   se conserva. La tabla recuerda qué alimentadores tienen su DGS entre lotes.
5. **Resultados**: descarga por fichero o en `.zip`, y el mapa de vista previa dentro
   de la página.
6. **Cargar en DigSILENT + flujo**, **Cargas de SED**, **SED nuevas**, **Catálogo de
   parámetros** y **Sistema completo** (red unida, escenario año 0, datos que faltan):
   lo mismo que la GUI de escritorio, con el plan a la vista antes de aplicarlo.

El Registro llega por WebSocket línea a línea, también la salida de los guiones de
PowerFactory mientras corren. Cada navegador trabaja en su **espacio de trabajo**
(`output/web/<id>/`), que se reabre al volver.

**Primera vez**: `run_gui.bat` compila el front si falta `frontend/dist`. Para eso
hace falta Node.js 20+ **solo una vez**; después, no.

**Desarrollo del front** (recarga en caliente):

```bash
python -m igea_dgs.web --no-browser     # API en :8765
cd frontend && npm install && npm run dev   # front en :5173, reenvía /api a :8765
```

**Seguridad**: por defecto escucha solo en `127.0.0.1`. Con `--host 0.0.0.0` se expone
en la red y se desactivan las rutas locales del servidor (solo subida de ficheros);
no hay autenticación todavía, así que no lo exponga fuera de una red de confianza.

### Colas de trabajo

Hay dos carriles, cada uno en serie: **motor** (leer, convertir, auditar) y
**PowerFactory** (import, flujo, cargas, red unida). PowerFactory admite un solo
proceso con el motor a la vez; serializarlo evita el fallo que eso produce, y separar
los carriles permite seguir convirtiendo mientras DigSILENT importa la red unida.

### Interfaz de escritorio (heredada)

La GUI Tkinter sigue disponible con `run_gui_escritorio.bat` o
`python -m igea_dgs.gui`. Sus funciones están todas en la web; se retirará cuando la
web se haya usado en producción.

## Reglas del proyecto (se aplican a toda conversión)

Cada entrada —los tres TXT o la base Access `.mdb`— y cada vía —interfaz web, CLI,
GUI de escritorio, red unida— convierte con las mismas reglas (`src/igea_dgs/reglas.py`):

| Regla | Qué hace |
|---|---|
| Hoja a medida | Por defecto el diagrama conserva la escala geográfica de referencia y el lienzo crece para cubrir la red completa, sin tope por tamaño. A0–A4 son opciones explícitas que reajustan la red al papel. |
| Coordenadas | Los nodos sin `CoordX/CoordY` se colocan por el grafo (interpolación por longitud de tramo); se marcan como inferidos y no cambian longitudes eléctricas. |
| Puentes `DEFAULT` | Los tramos `DEFAULT` de ≤ 10 m que CYMDIST crea para colgar un seccionador o una carga se funden: el seccionador pasa a `ElmCoup`, la SED queda en su barra. Un `DEFAULT` más largo es una línea real y se conserva. |
| Trafomix | La medición de MT registrada como SED `M…` no se modela (no es un transformador de distribución). |
| SED sobrecargadas | Una SED con más carga que kVA toma el menor tamaño normalizado que la cubre; queda listada en el manifiesto. |
| Catálogo | `input/catalogo_parametros.xlsx` completa los conductores que falten (mismo material y sección), da los transformadores de SED y sus filas `ficha`/`derivado` corrigen los valores. Una base sin tablas `CYMEQ*` toma de él todos los parámetros. |
| Completitud | Cada DGS se audita contra la entrada: tramos, cargas, kW, kvar y maniobras. Si algo se pierde, el alimentador no es «ok». |

**Uno, varios o todos**, cada uno en su DGS, o **varios en un solo DGS** (red unida:
cada alimentador con su fuente, enlaces como interruptores abiertos):

```bash
igea-dgs convert --mdb 260924.mdb --feeder NA203 --feeder NA205 --unir NA203_NA205 --out-dir out
igea-dgs convert --red R.txt --loads C.txt --equipment E.txt --all --out-dir out   # hoja a medida, escala real
```

En la web: «Unir en un solo DGS…» con los alimentadores seleccionados. `--literal`
(CLI) convierte sin reglas, solo para comparar con la entrada.

**Cargas de SED en bloque (Excel o CSV)**: descargue la plantilla del alimentador,
rellene por SED un par, el que tenga: `Kw` y `Kvar`, `Kw` y `FP` (cos φ), o `(kVA)` y `FP`.
La carga actual va aparte, en `Kw_actual`/`Kvar_actual`/`FP_actual`; la SED que se deja en
blanco no cambia, y una fila con dos pares que no coinciden es un error (`accion = omitir`
salta la fila). Súbala, revise el plan y aplíquelo. Se aplica sobre el
proyecto de PowerFactory que creó «Cargar en DigSILENT» (el del alimentador o el del DGS
unido que lo contiene); por eso hay que cargarlo antes.

Para uno, varios o todos los alimentadores use la pestaña **Cargas en DIgSILENT**:
crea un plan inmutable con hashes, muestra enrutamiento y valores antes/después, y
aplica cada alimentador con relectura, `ComLdf` y rollback aislado. La aceptación
genérica y la real se ejecutan con `python tools/accept_load_batch.py --help`; consulte
[`docs/runbooks/load-batch-production-acceptance.md`](docs/runbooks/load-batch-production-acceptance.md).

## Instalación (otra máquina local)

**Producción / interfaz web** (paquete + `pyproj` + FastAPI):

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt  # incluye TXT, MDB y VNR-GIS
```

**Desarrollo + tests:**

```bash
python -m pip install -r requirements-dev.txt
```

Alternativa con extras de `pyproject.toml`:

- Sin GPS/diagrama: `pip install -e .` y use `--no-geography` / desactive georreferenciación en la GUI.
- Solo producción (con geografía): `pip install -e ".[geo]"`.
- Desarrollo + tests: `pip install -e ".[geo,dev]"`.

Entradas de consola: `igea-dgs`, `igea-dgs-web` (interfaz web) e `igea-dgs-gui` (escritorio). `run_gui.bat` instala solo `requirements.txt` (sin pytest) si faltan dependencias.

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
| CLI `list` / `convert` / `gui` / `web` | Listo |
| Interfaz web (FastAPI + React) | Listo (`src/igea_dgs/web/` + `frontend/` + `run_gui.bat`) |
| Interfaz de escritorio Tkinter | Heredada (`gui.py` + `run_gui_escritorio.bat`) |
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

Aceptación en PowerFactory (API: import DGS + crear/activar escenario + flujo de carga con correcciones): `docs/POWERFACTORY_ACCEPTANCE.md` y `tools/powerfactory_acceptance.py` / `tools/run_powerfactory_gate.bat`. En la GUI: **Cargar DGS en DigSILENT + flujo**.

## Resultado de ejemplo (IN111)

En un export concreto con `--source-crs EPSG:32718`, IN111 produjo del orden de ~1,936 `ElmTerm`, ~1,934 `ElmLne`, ~383 `ElmLod`, ~791 `StaSwitch` y cobertura geográfica 100 %. **Esos conteos no son fijos**: dependen del alimentador y de los TXT cargados. El número total de alimentadores también varía por export (puede ser más o menos que en un lote anterior). Artefactos de ejemplo en `output/IN111_CONVERTIDO/`.
