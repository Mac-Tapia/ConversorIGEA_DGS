# ConverterSmartGrid

Convierte la red de una distribuidora (TXT de CYMDIST, base Access o paquete VNR-GIS) en archivos DGS para DIgSILENT PowerFactory, y la calibra y estudia allí.

Este README es para quien desarrolla. Para instalar y usar el programa: [manual de instalación](docs/MANUAL_INSTALACION.md), [manual del operador](docs/MANUAL_OPERADOR.md) y [hoja de seguridad y privacidad](docs/SEGURIDAD_Y_PRIVACIDAD.md). El instalador se arma con `tools/construir_candidato.py`.

**Universal por diseño:** no está limitado a una empresa, a un número fijo de alimentadores ni a códigos como IN111/TA121. Cualquier export CYMDIST con otras denominaciones de NetworkID, tipos de línea o CRS regionales se puede cargar; los nombres y conteos salen de los TXT, no de listas fijas en el código.

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
python -m convertersmartgrid.web          # o: convertersmartgrid-web  /  convertersmartgrid web
```

Abre el navegador en `http://127.0.0.1:8765/`. Es una API **FastAPI** que sirve un
front **React + TypeScript** (`frontend/`) y usa el mismo motor `convertersmartgrid`, sin
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
6. **Cargar en DIgSILENT + flujo**, **Catálogo de parámetros** y **Sistema completo**
   (red unida, escenario año 0, datos que faltan): con el plan a la vista antes de
   aplicarlo.

### Cargas en DIgSILENT

Esta pestaña trabaja sobre un proyecto que **ya existe** en DIgSILENT, sin convertir
nada, y por eso se ve aunque no haya entradas cargadas (spec 008). Sigue el orden del
trabajo:

1. **1 · Proyecto de DIgSILENT**: leer los proyectos de la carpeta de importación,
   buscar por nombre o carpeta y elegir uno (spec 005).
2. **2 · Alimentadores y calibración**: al elegir el proyecto se marcan todos sus
   alimentadores. Con los libros de medición se busca la máxima de cabecera de cada uno,
   los clientes importantes (coincidentes con la máxima, por defecto, o en su máximo del
   mes) y las SED medidas en «3.1 Demandas en bloque» quedan como demanda fija, y el resto
   se escala por kVA con un reparto probabilístico, más cargado cuanto mayor la potencia,
   hasta que la cabecera dé la máxima; en DIgSILENT queda el P50 y el informe da sus bandas
   y la probabilidad de sobrecarga. La recalibración cuadra también la Q si la medida de
   cabecera es coherente con la red; si no, deja la Q real y lo dice. Todo en el escenario
   de «Sin proyecto» (specs 004, 006, 008, 014, 015, 035, 039 y 041). Solo se calibra un
   alimentador cuyo «Caso base» esté verificado frente al archivo original (spec 015), y
   un cambio manual del operador gana a la calibración (spec 014).
3. **3 · Integración de nuevas**: verificar que el flujo converge y, sobre esa red,
   integrar demandas en bloque, una carga nueva y cargas nuevas en bloque. Las cargas
   nuevas nacen solo en «Con proyecto», una variación por carga y sin duplicarlas al
   repetir (specs 007 y 014). Cada carga va en sus coordenadas UTM y se conecta en el
   punto más cercano de la red de media de su alimentador, partiendo el tramo, con su
   propia línea hasta su punto si queda lejos (spec 016, RF-77 y RF-78). Las tres son
   optativas; aplicar exige que el último flujo del proyecto haya convergido, y simular
   no escribe nada.
4. **4 · Obras y estudios**: obras de mejora, estudios con los módulos nativos de
   DIgSILENT, guiones del operador y transferencia de carga entre dos alimentadores,
   sobre «Sin proyecto» y «Con proyecto» (spec 011). Entre las obras: una terna más,
   el enlace con otro alimentador (trazado por la vía pública con OpenStreetMap si el
   perfil lo habilita) y la migración a otra tensión desde un nodo, que cierra el enlace
   que llega a la parte que pasa (spec 016). Cada obra va en su variación, con fecha de
   activación propia: DIgSILENT no aplica tres o más etapas de la misma fecha.
5. **4.4 · Informes**: el informe de estudio, con las obras en etapas (bancos,
   reguladores, conductor, refuerzo de la red con ternas y enlaces, migración), se arma
   con lo ya ejecutado desde la web; el de factibilidad y punto de diseño es un análisis
   aparte, de una carga nueva ingresada sola (spec 017).

El [manual de uso](docs/MANUAL_DE_USO.md) lo explica como un libro, con la arquitectura,
los flujos de trabajo y cada procedimiento paso a paso; las órdenes exactas, con los guiones
que hay detrás, están en `docs/MANUAL_COMANDOS.md` (7.ter).

### Perfil de empresa

Las convenciones de cada distribuidora no van en el código (constitución P13). Se copian
los ejemplos de `config/` y se rellenan en local, fuera de git:

- `config/perfil_empresa.json` (de `perfil_empresa.example.json`): la carpeta de
  DIgSILENT donde quedan los proyectos importados (spec 005).
- `config/demanda_medida_alias.json`: otros nombres de columna de los libros de medición.
- `config/line_type_aliases.json`: equivalencias de tipos de línea, revisadas a mano.
- Clave `vias` del perfil: el enrutador con que el enlace se traza por la vía pública
  (OSRM sobre OpenStreetMap en el perfil de Electro Dunas). Solo se envían las
  coordenadas de los dos extremos del enlace; sin la clave, el enlace va en recta y no
  sale nada del equipo (spec 016, RF-81 a RF-87).

La spec 002 llevará al perfil de empresa también el CRS de origen, el patrón de las SED
de medición y la escala del diagrama, que hoy todavía tienen un valor por defecto.

El Registro llega por WebSocket línea a línea, también la salida de los guiones de
PowerFactory mientras corren. Cada navegador trabaja en su **espacio de trabajo**
(en la raíz de ejecución, fuera del código: `copia_datos.py estado` la dice), que se reabre al volver.

**Primera vez**: instale los paquetes del front con `cd frontend && npm ci`; `run_gui.bat` lo compila si falta `frontend/dist` o está desfasado, sin salir a internet. Hace falta la versión de Node.js que declara `frontend/package.json`.

**Desarrollo del front** (recarga en caliente):

```bash
python -m convertersmartgrid.web --no-browser     # API en :8765
cd frontend && npm ci && npm run dev   # front en :5173, reenvía /api a :8765
```

**Seguridad** (spec 086): es un puesto local. Solo escucha en `127.0.0.1` y se niega a arrancar
fuera de esta máquina, porque no tiene usuarios ni TLS. Cada arranque crea un token que el lanzador
entrega al navegador, y los programas locales lo leen con `sesion_web.cabeceras_locales`. La web
rechaza un `Host` ajeno y un `Origin` ajeno. Con `npm run dev`, abra antes la dirección con `?acceso=`
del token en el puerto 8765: las cookies no distinguen puertos y Vite la reenvía.

Salidas a la red: están en `salidas_red.py`, cada una con su variable (`CSG_SALIDA_TESELAS=1`, por
ejemplo). En desarrollo siguen encendidas; con `CSG_EDICION=producto`, apagadas hasta que se activen.

### Colas de trabajo

Hay dos carriles, cada uno en serie: **motor** (leer, convertir, auditar) y
**PowerFactory** (import, flujo, cargas, red unida). PowerFactory admite un solo
proceso con el motor a la vez; serializarlo evita el fallo que eso produce, y separar
los carriles permite seguir convirtiendo mientras DIgSILENT importa la red unida.

La interfaz de escritorio Tkinter se retiró (spec 001, RF-16): todas sus funciones
están en la web, y `run_gui.bat` conserva el nombre por los accesos directos ya creados.

## Reglas del proyecto (se aplican a toda conversión)

Cada entrada —los tres TXT, la base Access `.mdb` o el paquete VNR-GIS— y cada vía
—interfaz web, CLI, red unida— convierte con las mismas reglas (`src/convertersmartgrid/reglas.py`):

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
convertersmartgrid convert --mdb 260924.mdb --feeder NA203 --feeder NA205 --unir NA203_NA205 --out-dir out
convertersmartgrid convert --red R.txt --loads C.txt --equipment E.txt --all --out-dir out   # hoja a medida, escala real
```

En la web: «Unir en un solo DGS…» con los alimentadores seleccionados. `--literal`
(CLI) convierte sin reglas, solo para comparar con la entrada.

**Cargas en DIgSILENT** (pestaña del mismo nombre, spec 004): trabaja sobre un proyecto
que **ya existe** en DIgSILENT, sin convertir ni cargar entradas en la web. Lea los
proyectos, elija uno y sus alimentadores (uno o varios, en el orden de aplicación) y
suba el libro de **demandas** (por SED un par: `Kw` y `Kvar`, `Kw` y `FP`, o `(kVA)` y
`FP`), el de **cargas nuevas** (`SED`, `kVA_instalado`, la demanda y `barra` o
`Lat`/`Lon` o `CoordX`/`CoordY`) o escriba **una carga nueva** en el formulario. Las
plantillas vacías se descargan en la misma pestaña. «Simular» dice qué coincide, qué
se omite y dónde se conectaría cada carga, sin escribir; «Aplicar» lo graba todo en una
**variación nueva** del proyecto y lanza el flujo de carga. Una SED que no está en el
alimentador se omite y se informa; cancelar termina el alimentador en curso.

**Demanda medida** (misma pestaña): escriba el código de alimentador y salen sus
medidores (libro medidor–alimentador); con la carpeta de medición de cabecera da, por
medidor, el kW máximo con su fecha y hora y el kVAR, kVA y FP de ese mismo registro.
Con el libro de suministros y el de clientes importantes del mes cruza cada cliente
(por suministro actual o, si no, el anterior) y da su SED, radial, EA, ERI y potencia.
Todo se descarga en Excel. Los alias de columna propios de una empresa van en
`config/demanda_medida_alias.json`.

## Instalación (otra máquina local)

Las dependencias Python del proyecto (conversor, web, VNR-GIS y pruebas) están en un
único `requirements.txt`. Lo opcional va aparte en `requirements-drivers.txt` —los
drivers de VNR-GIS (PostgreSQL, Oracle, OpenCV, PDF, RAR) y `leafmap` para la vista
previa del mapa—, para que un paquete que no se descargue no impida instalar el resto:

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-drivers.txt   # opcional, solo VNR-GIS
```

Alternativa con extras de `pyproject.toml`:

- Sin GPS/diagrama: `pip install -e .` y use `--no-geography` / desactive georreferenciación en la web.
- Solo producción (con geografía): `pip install -e ".[geo]"`.
- Desarrollo + tests: `pip install -e ".[geo,dev]"`.

El extra `dev` incluye ReportLab para generar PDF sintéticos de las pruebas de
lectura documental. No se necesita para leer los PDF del usuario ni se incluye
en el núcleo de producción. Instale los extras en el entorno de desarrollo
antes de la corrida: las pruebas de PDF no quedan verificadas si se omiten
por falta de esa dependencia.

También incluye Ruff para comprobar los nombres definidos. Esa prueba ejecuta
`python -m ruff` con el mismo intérprete que ejecuta pytest; un ejecutable Ruff
de otro entorno no sustituye esa dependencia de desarrollo.

Entradas de consola: `convertersmartgrid` (CLI) e `convertersmartgrid-web` (interfaz web). `run_gui.bat` nunca instala: si falta algo, lo dice (086:RF-39). `convertersmartgrid doctor` dice qué falta y qué función afecta. Tras actualizar el código, `pip install -e .` retira el antiguo `convertersmartgrid-gui` del entorno.

## Principio de arquitectura

La arquitectura completa (capas, flujo de conversión, los tres casos de estudio en
PowerFactory, carriles de trabajo de la web y su relación con cada spec) está en
[`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

El motor **no necesita un archivo DGS de referencia** para convertir. La compatibilidad de formato se describe en un perfil versionado (`src/convertersmartgrid/schemas/pf21_dgs_1_8_4.json`) que contiene únicamente nombres de tablas, campos y tipos DGS. No contiene nodos, FID, líneas, cargas, nombres ni datos eléctricos de un alimentador de ejemplo.

La fuente de verdad para cada conversión es:

- `RED_*.txt`: alimentadores, cabeceras, fuentes, nodos, secciones, configuración de línea, maniobras y nodos intermedios.
- `CARGA_*.txt`: ubicación de cargas y datos de cliente/carga.
- `BD_Equipo_*.txt`: parámetros eléctricos de tipos de línea/cable y otros catálogos CYMDIST.

## Estado del proyecto (diagnóstico)

| Ítem | Estado |
| ---- | ------ |
| Motor de conversión (dataset → model → DGS → validate) | Listo |
| CLI `list` / `convert` / `web` (TXT, Access y VNR-GIS) | Listo |
| Interfaz web (FastAPI + React) | Listo (`src/convertersmartgrid/web/` + `frontend/` + `run_gui.bat`) |
| Instalador sin internet (spec 086) | Candidato y guion listos; instalador compilado y máquina limpia pendientes (T37) |
| Interfaz de escritorio Tkinter | Retirada (spec 001, RF-16) |
| Empaquetado `pyproject.toml` | Listo |
| Dependencia `pyproj` (GPS) | En `requirements.txt` (+ extra `[geo]`) — opcional si convierte sin geografía |
| TXT de entrada en el repo | No incluidos — hay que suministrarlos |
| Base de datos SQL/Access | No aplica — `BD_Equipo` es TXT |
| Aceptación en PowerFactory | Requiere PF + importar el `.dgs` |
| Cargas, calibración, estudios y obras en PowerFactory | Implementado (specs 004 a 008, 011, 014, 015); falta la prueba en DIgSILENT de varias specs |
| Troncal, enlace, migración y cargas en un tramo (spec 016) | Cumplida: probada en DIgSILENT con IN111 + TA225 el 2026-10-16 («Con proyecto» converge con 9 cargas, enlace por la vía, migración y segunda terna) |
| Informes de estudio y factibilidad (spec 017) | Estudio probado con IN111 y TA225; factibilidad pendiente, con otro alimentador |
| Arquitectura por capas (spec 002) | En curso: su estado, en `specs/README.md` |
| Confiabilidad y capacidad (spec 012) | Implementada: falta su prueba en DIgSILENT |

El estado al día de cada spec está en `specs/README.md`.

## Estructura

```text
TXT CYMDIST
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
PYTHONPATH=src python -m convertersmartgrid.cli list \
  --red RED_030826.txt \
  --loads CARGA_030826.txt \
  --equipment BD_Equipo.txt
```

Convertir un alimentador (use el nombre corto que aparezca en `list`, el de su export):

```bash
PYTHONPATH=src python -m convertersmartgrid.cli convert \
  --red RED_export.txt \
  --loads CARGA_export.txt \
  --equipment BD_Equipo.txt \
  --feeder NOMBRE_ALIMENTADOR \
  --source-crs EPSG:XXXXX \
  --out-dir output
```

Convertir todos los alimentadores del lote cargado:

```bash
PYTHONPATH=src python -m convertersmartgrid.cli convert \
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

Se transforma `CoordX/CoordY` con `pyproj` desde el `--source-crs` **de su export** (cualquier EPSG) a WGS84. Elija el CRS de la empresa/región que entregó los TXT, o déjelo en el perfil de empresa (`crs_origen` en `config/perfil_empresa.json`, o un perfil de `config/perfiles/` con `--perfil`). Sin ninguno de los dos el conversor no supone un CRS: lo pide. Genera GPS en terminales, diagrama `IntGrf*` y sidecars `*_geography.json`.

## Pruebas

Instale deps de desarrollo: `pip install -r requirements.txt`.

Sin datos, pasan solo las sintéticas, y la suite «pasa» sin haber probado nada real. Con datos reales hacen falta `CSG_RED`, `CSG_LOADS` y `CSG_EQUIPMENT` (`CSG_TXT_DIR` no basta): la lista completa de variables, y la regla de darla por buena solo sin ninguna omitida, está en `CLAUDE.md`.

Aceptación en PowerFactory (API: import DGS + crear/activar escenario + flujo de carga con correcciones): `docs/POWERFACTORY_ACCEPTANCE.md` y `tools/powerfactory_acceptance.py` / `tools/run_powerfactory_gate.bat`. En la GUI: **Cargar DGS en DIgSILENT + flujo**.

## Resultado de ejemplo (IN111)

En un export concreto con `--source-crs EPSG:32718`, IN111 produjo del orden de ~1,936 `ElmTerm`, ~1,934 `ElmLne`, ~383 `ElmLod`, ~791 `StaSwitch` y cobertura geográfica 100 %. **Esos conteos no son fijos**: dependen del alimentador y de los TXT cargados. El número total de alimentadores también varía por export (puede ser más o menos que en un lote anterior). Artefactos de ejemplo en `output/IN111_CONVERTIDO/`.

## Licencia

El código se publica con licencia [MIT](LICENSE): se puede usar, modificar y reutilizar, también comercialmente, conservando el aviso de la licencia. Las dependencias y Leaflet (`src/convertersmartgrid/recursos/leaflet/LICENSE`) mantienen las suyas, y DIgSILENT PowerFactory necesita su propia licencia. Los datos de una distribuidora no forman parte del repositorio.
