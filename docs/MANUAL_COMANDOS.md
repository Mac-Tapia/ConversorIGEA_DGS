# Manual de comandos — pruebas, conversión e importación en DigSILENT

Cada cosa que hace la interfaz gráfica se puede lanzar también desde la consola. Este
manual empareja las dos vías: **lo que pulsa en la interfaz web** y **el comando equivalente**,
para poder automatizar, diagnosticar una incidencia o trabajar en una máquina sin pantalla.

Todos los comandos se ejecutan desde la raíz del proyecto (`D:\converter\ConversorIGEA_DGS`)
en **PowerShell** o **CMD** de Windows. El entorno virtual es `.venv`.

> Convención de este manual: `>` es el símbolo del sistema; no lo escriba.

---

## 0. Preparar el entorno (una sola vez por máquina)

### El entorno es Python 3.12. Ni más, ni menos.

`powerfactory.pyd`, la API de PowerFactory 2024, es una extensión binaria compilada
contra **CPython 3.12**. No carga en 3.11 ni en 3.13, y cuando falla lo hace con
`DLL load failed while importing powerfactory`, un mensaje que no menciona la versión de
Python y manda a buscar un problema de DLL que no existe.

Por eso `pyproject.toml` declara `requires-python = ">=3.12,<3.13"`: **el tope superior
es parte de la restricción**, no una formalidad. Un `>=3.12` abierto deja instalar 3.14 y
rompe la integración con DIgSILENT, que es la razón de ser del proyecto.

```bat
> py -3.12 -m venv .venv
> .venv\Scripts\activate
> python -m pip install -r requirements.txt
```

Ese único fichero trae todo: conversor, web, VNR-GIS y las herramientas de prueba.

Comprobar que quedó bien instalado:

```bat
> .venv\Scripts\python.exe -c "import igea_dgs, pyproj; print(igea_dgs.__version__)"
2.1.0
```

Y, lo que de verdad importa, que el entorno puede hablar con DIgSILENT **en su propio
proceso**:

```bat
> .venv\Scripts\python.exe -c "import sys; sys.path.insert(0, r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12'); import powerfactory; print('API disponible')"
API disponible
```

Si eso funciona, el conversor no necesita saltar a otro intérprete para cada llamada a
la API, y desaparece toda una familia de fallos.

Las pruebas de `tests/test_python_version.py` lo verifican y fallan si el entorno se
desvía: la versión del intérprete, el tope de `pyproject.toml`, el `.python-version`, y
que el `.venv` de la raíz —si existe— sea el correcto y no uno olvidado.

Si aparece `ModuleNotFoundError: pyproj`, faltan las dependencias de georreferenciación:
repita `pip install -r requirements.txt`, o convierta con `--no-geography`.

---

## 1. Abrir la interfaz gráfica

| En la interfaz | Comando |
| --- | --- |
| Doble clic en `run_gui.bat` | `> .venv\Scripts\igea-dgs.exe web` (o `igea-dgs-web`) |

`run_gui.bat` prefiere el `.venv`, instala las dependencias de producción si faltan,
recompila el front si su código es más reciente que la compilación y abre el navegador
en `http://127.0.0.1:8765/`. El comando directo no instala nada: asume el entorno ya
preparado. La interfaz de escritorio Tkinter (`igea_dgs.gui`) se retiró (spec 001, RF-16).

### Las órdenes del CLI

| Orden | Para qué | Sección |
| --- | --- | --- |
| `igea-dgs list` | Listar alimentadores e inventario de la entrada (TXT, `.mdb` o VNR-GIS). | 3 |
| `igea-dgs convert` | Convertir uno, varios (`--feeder` repetido) o todos (`--all`). | 4 |
| `igea-dgs web` | Arrancar la interfaz web y abrir el navegador. | 1 |
| `vnr-etl` | Módulo VNR-GIS: descubrir, validar y exportar paquetes (`docs/VNR_GIS_PRODUCTION.md`). | — |

`igea-dgs` equivale a `python -m igea_dgs.cli`; los ejemplos usan una u otra forma.

---

## 2. Pruebas

Verifican que la instalación está sana antes de convertir nada en producción. **La
interfaz no tiene botón de pruebas**: esto es solo de consola.

### 2.1 Pruebas rápidas, sin datos de la distribuidora

```bat
> .venv\Scripts\python.exe -m pytest -q
```

Las pruebas que necesitan TXT reales se marcan `skipped`; el resto debe pasar. Es la
comprobación mínima tras instalar o actualizar.

### 2.2 Suite completa, con sus TXT

```bat
> set IGEA_RED=referencia\RED_030826(1).txt
> set IGEA_LOADS=referencia\CARGA_030826(1).txt
> set IGEA_EQUIPMENT=referencia\BD_Equipo_V261124 (1)(1).txt
> .venv\Scripts\python.exe -m pytest -q
```

En PowerShell:

```powershell
> $env:IGEA_RED='referencia\RED_030826(1).txt'
> $env:IGEA_LOADS='referencia\CARGA_030826(1).txt'
> $env:IGEA_EQUIPMENT='referencia\BD_Equipo_V261124 (1)(1).txt'
> .venv\Scripts\python.exe -m pytest -q
```

Nota: los nombres con paréntesis **deben ir entre comillas** si los escribe sueltos.
La variable `IGEA_TXT_DIR` que menciona el README no resuelve estos nombres; use las
tres variables individuales.

### 2.3 Solo un grupo concreto

```bat
rem Presupuesto de rendimiento (evita que vuelva el coste cuadrático)
> .venv\Scripts\python.exe -m pytest tests\test_performance_budget.py -v

rem Unidades del CRS de origen (defecto de escala silenciosa)
> .venv\Scripts\python.exe -m pytest tests\test_source_crs_units.py -v

rem Atomicidad, cancelación y alimentadores solo-cabecera
> .venv\Scripts\python.exe -m pytest tests\test_batch_robustness.py -v

rem Vínculo de la interfaz con el motor
> .venv\Scripts\python.exe -m pytest tests\test_gui_wiring.py -v
```

### 2.4 Cómo leer el resultado

| Salida | Significado |
| --- | --- |
| `N passed` | Todo correcto |
| `N skipped` | Faltan los TXT o `pyproj`; no es un fallo |
| `N failed` | **No convierta en producción** hasta resolverlo |

---

## 3. Listar alimentadores e inventario

| En la interfaz | Comando |
| --- | --- |
| **Cargar / listar alimentadores** | `igea_dgs.cli list` |

```bat
> .venv\Scripts\python.exe -m igea_dgs.cli list ^
    --red "referencia\RED_030826(1).txt" ^
    --loads "referencia\CARGA_030826(1).txt" ^
    --equipment "referencia\BD_Equipo_V261124 (1)(1).txt" ^
    --inventory-json output\inventario.json
```

Imprime el inventario del export (nodos, tramos, cargas, maniobras, alimentadores) y
escribe el JSON si indica `--inventory-json`.

**Código de salida:** `0` sin errores de integridad, `2` con errores. Útil para encadenar.

---

## 3.bis Las dos alternativas de entrada

El conversor acepta la red por **dos vías**. Son excluyentes: se elige una.

| | Alternativa 1 — TXT | Alternativa 2 — base Access |
| --- | --- | --- |
| Qué se indica | `--red` `--loads` `--equipment` | `--mdb` (+ `--equipment-mdb` si el catálogo está aparte) |
| Requisitos | Ninguno especial | Windows, driver «Microsoft Access Driver» de 64 bits, `pip install "igea-dgs[access]"` |
| Ventaja | Portable; no necesita CYMDIST ni licencia; funciona en Linux | Evita el paso manual de exportar; **conserva el conductor real** allí donde el export TXT escribe `DEFAULT`; permite elegir el año del escenario de carga |
| Escenario de carga | El que trajera el export | `--load-year 2026`; por defecto el más reciente, igual que el TXT |

En un export real de 96 alimentadores, el TXT trae `DEFAULT` en el **59 %** de los tramos
mientras la base conserva el código real en todos menos el 5,4 %: **20.694 tramos
recuperan su conductor** leyendo la base en lugar del TXT.

### Leer desde la base

```bat
> .venv\Scripts\python.exe -m igea_dgs.cli list --mdb "D:\Ruta\BaseDatos.mdb"

> .venv\Scripts\python.exe -m igea_dgs.cli convert ^
    --mdb "D:\Ruta\BaseDatos.mdb" ^
    --all --source-crs EPSG:32718 --out-dir output\produccion
```

Si el catálogo de equipos vive en otra base —ocurre: hay bases de red con
`CYMEQOVERHEADLINE` vacía— indíquelo, o el motor lo dirá:

```bat
> ... --mdb "D:\Ruta\202603.mdb" --equipment-mdb "D:\Ruta\BaseDatos.mdb"
```

### El estudio o proyecto, opcional

Un `.zxst` de CYMDIST no contiene la red, pero sí **qué alimentadores forman parte del
estudio**. Con `--study` se convierte exactamente ese conjunto:

```bat
> .venv\Scripts\python.exe -m igea_dgs.cli convert ^
    --mdb "D:\Ruta\BaseDatos.mdb" ^
    --study "D:\Ruta\estudios\base2026.zxst" ^
    --all --source-crs EPSG:32718 --out-dir output\produccion
```

Imprime `Estudio «base2026»: 96 alimentadores.` y limita la lectura a esas redes.
Funciona también con la entrada por TXT, donde actúa como filtro de selección.

### En la interfaz

El panel **1 · Entrada de datos** tiene tres pestañas: *Tres TXT de IGEA/CYMDIST*,
*Base Access (.mdb)* y *VNR-GIS*. Al cambiar, el panel de casillas se sustituye. Con la
base Access solo la base de red es obligatoria; la base de equipos y el estudio son
opcionales.

---

## 4. Conversión a DGS

| En la interfaz | Comando |
| --- | --- |
| **Convertir a DGS** (uno) | `convert --feeder NOMBRE` |
| **Convertir a DGS** (varios) | `convert --feeder A --feeder B` |
| Casilla **Convertir todos** | `convert --all` |

### 4.1 Un alimentador

```bat
> .venv\Scripts\python.exe -m igea_dgs.cli convert ^
    --red "referencia\RED_030826(1).txt" ^
    --loads "referencia\CARGA_030826(1).txt" ^
    --equipment "referencia\BD_Equipo_V261124 (1)(1).txt" ^
    --feeder IN111 ^
    --source-crs EPSG:32718 ^
    --out-dir output\produccion
```

### 4.2 Todos

```bat
> .venv\Scripts\python.exe -m igea_dgs.cli convert ^
    --red "referencia\RED_030826(1).txt" ^
    --loads "referencia\CARGA_030826(1).txt" ^
    --equipment "referencia\BD_Equipo_V261124 (1)(1).txt" ^
    --all ^
    --source-crs EPSG:32718 ^
    --out-dir output\produccion
```

### 4.3 Opciones, y su casilla equivalente

| Casilla en la interfaz | Opción | Qué hace |
| --- | --- | --- |
| Georreferenciación (GPS + diagrama) | *(activa por defecto)* / `--no-geography` | GPS en terminales, diagrama `IntGrf` y sidecar `_geography.json` |
| Modo estricto | *(activo por defecto)* / `--non-strict` | En estricto, una topología rota bloquea el alimentador |
| Excel multi-hoja | `--export-xlsx` | Requiere `pip install "igea-dgs[xlsx]"` |
| TSV por tabla | `--export-tsv` | Una carpeta `{alimentador}_dgs_tables/` |
| Vista previa | `--preview` | Mapa HTML + GeoJSON. Exige georreferenciación |
| CRS origen | `--source-crs EPSG:XXXXX` | El de **su** export. Sin él, el del perfil de empresa; sin perfil, se pide |
| Perfil de empresa | `--perfil NOMBRE` | Uno de `config/perfiles/` (CRS, SED de medición, escala). Sin él, `config/perfil_empresa.json` |
| Aliases de tipos | `--aliases ruta.json` | Equivalencias de códigos de conductor |

### 4.4 El CRS de origen: el punto que más caro sale equivocar

El conversor no supone ningún CRS (spec 002): lo toma de `--source-crs`, si no del perfil
de empresa (`crs_origen` en `config/perfil_empresa.json`, o el de `--perfil NOMBRE`), y si
ninguno lo da se niega a georreferenciar y dice cómo elegirlo. Para Electro Dunas, el
caso de prueba, basta con `config/perfil_empresa.json` = `{"perfil": "electro_dunas"}`.

`--source-crs` debe ser un sistema **proyectado en metros** (un UTM regional, por
ejemplo). Las longitudes eléctricas se miden sobre `CoordX/CoordY` y se escriben como
metros: un CRS en grados (`EPSG:4326`) daría longitudes ~100.000 veces menores y un
modelo eléctricamente falso.

El motor lo rechaza antes de escribir nada:

```
Error de conversión: CRS de origen 'EPSG:4326' usa unidades 'degree', no metros. …
```

Si no necesita GPS ni diagrama, convierta con `--no-geography` y el CRS deja de importar.

### 4.5 Qué se genera

Por cada alimentador, en `--out-dir`:

| Fichero | Contenido |
| --- | --- |
| `{alimentador}.dgs` | El modelo para PowerFactory |
| `{alimentador}_validation.json` / `.txt` | Informe de validación estricta |
| `{alimentador}_geography.json` | Coordenadas WGS84 (con georreferenciación) |
| `{alimentador}_geography_validation.txt` | Cobertura GPS |
| `batch_manifest.json` | Resumen del lote: qué se convirtió y con qué opciones |
| `dataset_inventory.json` | Inventario del export |

**Código de salida:** `0` si no falló ningún alimentador, `2` si falló alguno.

### 4.6 Garantías de integridad

- **Nada se publica a medias.** Cada alimentador se escribe en una carpeta temporal
  `.igea-stage-…` y solo se mueve a su sitio cuando está completo y validado. Un corte
  de luz o un cierre no pueden dejar un `.dgs` truncado que parezca válido.
- **Si un alimentador falla, no deja fichero** y el resultado bueno anterior se conserva.
- **El manifiesto se escribe siempre**, incluso si el lote se interrumpe.
- Si dos `NetworkID` distintos comparten nombre corto, solo los que chocan reciben un
  sufijo (`NA999__a1b2c3d4`); los demás conservan su nombre. El manifiesto lo registra
  en `disambiguated_output_names`.

### 4.7 Cancelar

En la interfaz: botón **Cancelar**, habilitado mientras convierte. No empieza ningún
alimentador más; el que está en marcha (o los que están en marcha, con `--workers`)
termina y se conserva junto con lo ya convertido. Ningún DGS queda a medias.

En consola: `Ctrl+C`. El manifiesto se escribe igualmente con lo procesado hasta ese
momento.

---

## 4.bis Caso de aceptación por alimentador: PA217

Ejemplo completo con un alimentador concreto por las **dos vías**, útil como
comprobación rápida tras instalar o actualizar.

```bat
rem Alternativa 1 — TXT
> .venv\Scripts\python.exe -m igea_dgs.cli convert ^
    --red "referencia\RED_030826(1).txt" ^
    --loads "referencia\CARGA_030826(1).txt" ^
    --equipment "referencia\BD_Equipo_V261124 (1)(1).txt" ^
    --feeder PA217 --source-crs EPSG:32718 --out-dir output\pa217_txt

rem Alternativa 2 — base Access
> .venv\Scripts\python.exe -m igea_dgs.cli convert ^
    --mdb "D:\BaseDatosElectroDunas\BaseDatos.mdb" ^
    --feeder PA217 --source-crs EPSG:32718 --out-dir output\pa217_mdb
```

Resultado esperado por ambas vías (`NET_2030_179_PA217`, 22,9 kV):

| | Valor |
| --- | --- |
| Tramos → `ElmLne` | 1.324 |
| Cargas → `ElmLod` | 253 |
| Barras → `ElmTerm` | 1.830 |
| Maniobras → `StaSwitch` | 525 |
| SED → `ElmSubstat` / `ElmTr2` | 253 / 253 |
| Cubículos → `StaCubic` | 3.914 |
| Gráficos → `IntGrf` | 2.396 |
| Cobertura GPS | 100 % nodos y líneas |
| `errors_total` | 0 |

**Las dos vías dan la misma estructura pero no el mismo fichero**, y es correcto: de
los 1.324 tramos, el TXT trae `DEFAULT` en **784 (59,2 %)** mientras la base solo en
**79 (6,0 %)**. Leyendo la base, **705 tramos recuperan su conductor real** y con él sus
R/X/ampacidad verdaderos. Las fases coinciden exactamente (1.316 ABC + 8 AB).

Las pruebas automáticas de este caso están en `tests/test_feeder_pa217.py` (21 pruebas,
parametrizadas sobre las dos alternativas).

---

## 5. Importación en DigSILENT PowerFactory

| En la interfaz | Comando |
| --- | --- |
| **Cargar DGS en DigSILENT + flujo** | `tools\powerfactory_acceptance.py` |

### 5.1 Requisitos

- PowerFactory **instalado y licenciado** en la máquina.
- La API Python de PowerFactory accesible. Si no está en la ruta por defecto
  (`C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12`), indíquela:

```bat
> set PF_PYTHON=C:\Ruta\A\DIgSILENT\PowerFactory 2024\Python\3.12
> set PYTHONPATH=%PF_PYTHON%;%PYTHONPATH%
```

- Es preferible tener PowerFactory **abierto** antes de lanzar el comando.

### 5.2 El comando que ejecuta la interfaz

Es exactamente éste, un alimentador por llamada:

```bat
> .venv\Scripts\python.exe tools\powerfactory_acceptance.py ^
    --import-dgs output\produccion\IN111.dgs ^
    --manifest output\produccion\IN111_geography.json ^
    --ensure-scenario ^
    --run-load-flow ^
    --fix-until-converge ^
    --run-studies ^
    --output-json output\produccion\IN111_powerfactory_acceptance.json ^
    --output-txt output\produccion\IN111_powerfactory_acceptance.txt
```

Qué hace cada opción:

| Opción | Efecto |
| --- | --- |
| `--import-dgs` | Importa el `.dgs` en PowerFactory (ComImport) |
| `--manifest` | Sidecar de geografía, para verificar GPS y diagrama |
| `--ensure-scenario` | Crea y activa un escenario de operación |
| `--run-load-flow` | Ejecuta el flujo de potencia (ComLdf) y exige convergencia |
| `--fix-until-converge` | Aplica correcciones si no converge a la primera |
| `--run-studies` | Suite de estudios (incluye cortocircuito ComShc si la licencia lo permite) |
| `--require-diagram` | Exige `ElmNet.pDiagram` + `IntGrf` |
| `--output-json` / `--output-txt` | Informes de aceptación |

#### Verificar el «Caso base» de un proyecto existente (spec 015)

Cuando el proyecto ya fue importado y contiene correcciones manuales que deben
conservarse, use su ruta exacta con `--existing-project`. Esta opción es mutuamente
exclusiva con `--import-dgs`; `--source-dgs` y el sidecar demuestran la procedencia sin
volver a ejecutar `ComImport`. Exige `--manifest`, la geografía del archivo original: sin
ella no se puede verificar el «Caso base» (015:RF-1). No admite `--run-load-flow`,
`--fix-until-converge` ni `--run-studies`: la convergencia se prueba al importar el DGS,
y antes con el oráculo y las cargas del archivo (015:RF-8, RF-39, RF-41).

```bat
> .venv\Scripts\python.exe tools\powerfactory_acceptance.py ^
    --existing-project "20261013-121930_IGEA_CA101" ^
    --pf-carpeta "sistemaeletricoELD" ^
    --source-dgs output\produccion\CA101.dgs ^
    --manifest output\produccion\CA101_geography.json ^
    --feeder-metadata output\produccion\CA101_feeder_metadata.json ^
    --source-run-id RUN_ID --source-mode mdb --source-fingerprint SHA256 ^
    --require-diagram
```

Si el proyecto tiene el caso «Caso base» de la spec 011, se verifica ese. El informe trae
`caso_base` con el resultado de cada comprobación: GPS de barras y trazado de líneas
frente al archivo original, conectividad, diagrama y capacidades. Bloquean todas;
una capacidad distinta de la del archivo solo se avisa, y el grupo de conexión y la
tensión de baja de los transformadores se corrigen con el valor del archivo antes del
flujo, copiando el tipo si lo comparten transformadores que estaban bien. Lo mismo hace
el botón «Verificar el Caso base» del paso 1.1 de la pestaña de cargas.

La aceptación relee también los `ElmShnt` presentes únicamente en el proyecto. Si no
hay capacidad de origen, aplica el catálogo 10 kV/300 kVAr o 22,9 kV/450 kVAr, informa
nodo y cubículo, y mantiene cualquier diferencia como aviso no bloqueante.

### 5.3 Atajo con el `.bat`

```bat
> tools\run_powerfactory_gate.bat output\produccion\IN111.dgs output\produccion\IN111_geography.json
```

Configura `PF_PYTHON`/`PYTHONPATH` solo y ejecuta la puerta con
`--require-diagram --run-load-flow --fix-until-converge --ensure-scenario`
(sin `--run-studies`).

### 5.4 Códigos de salida

| Código | Significado | Qué hacer |
| --- | --- | --- |
| `0` | Importado y aceptado | — |
| `3` | **API de PowerFactory no disponible** | Abra PowerFactory, o revise `PF_PYTHON` / `PYTHONPATH` |
| otro | Fallo de importación, convergencia o estudios | Lea el `_powerfactory_acceptance.txt` |

### 5.5 Advertencia sobre `--fix-until-converge`

Si un caso no converge, esta opción **modifica el caso** (por ejemplo, poniendo cargas
fuera de servicio o escalándolas) hasta lograr convergencia. Eso demuestra que el
modelo es importable y operable, **no** que el caso original converja. Para una
aceptación defendible, ejecute primero sin esa opción y registre por separado:

```bat
rem 1) El caso original, tal cual
> .venv\Scripts\python.exe tools\powerfactory_acceptance.py ^
    --import-dgs output\produccion\IN111.dgs --ensure-scenario --run-load-flow ^
    --output-json output\produccion\IN111_original.json

rem 2) Solo si el anterior falla, con correcciones, y como resultado aparte
> .venv\Scripts\python.exe tools\powerfactory_acceptance.py ^
    --import-dgs output\produccion\IN111.dgs --ensure-scenario --run-load-flow ^
    --fix-until-converge --output-json output\produccion\IN111_corregido.json
```

---

## 6. Cadena completa en un solo guion

Pruebas → conversión → importación, parando en el primer fallo. Guarde como
`ejecutar_todo.bat` en la raíz del proyecto:

```bat
@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "RED=referencia\RED_030826(1).txt"
set "CARGA=referencia\CARGA_030826(1).txt"
set "EQUIPO=referencia\BD_Equipo_V261124 (1)(1).txt"
set "SALIDA=output\produccion"
set "CRS=EPSG:32718"
set "ALIM=IN111"

echo === 1/3 Pruebas ===
set "IGEA_RED=%RED%"
set "IGEA_LOADS=%CARGA%"
set "IGEA_EQUIPMENT=%EQUIPO%"
"%PY%" -m pytest -q || (echo Pruebas fallidas: se detiene. & exit /b 1)

echo === 2/3 Conversion ===
"%PY%" -m igea_dgs.cli convert --red "%RED%" --loads "%CARGA%" --equipment "%EQUIPO%" ^
    --feeder %ALIM% --source-crs %CRS% --out-dir "%SALIDA%" || (echo Conversion fallida. & exit /b 2)

echo === 3/3 Importacion en DigSILENT ===
if not defined PF_PYTHON set "PF_PYTHON=C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12"
if exist "%PF_PYTHON%\powerfactory.pyd" set "PYTHONPATH=%PF_PYTHON%;%PYTHONPATH%"
"%PY%" tools\powerfactory_acceptance.py ^
    --import-dgs "%SALIDA%\%ALIM%.dgs" ^
    --manifest "%SALIDA%\%ALIM%_geography.json" ^
    --ensure-scenario --run-load-flow --fix-until-converge --run-studies ^
    --output-json "%SALIDA%\%ALIM%_powerfactory_acceptance.json" ^
    --output-txt "%SALIDA%\%ALIM%_powerfactory_acceptance.txt"
set ERR=%ERRORLEVEL%

if %ERR%==0 (echo LISTO: %ALIM% convertido e importado.) else (echo Importacion fallida, codigo %ERR%.)
endlocal & exit /b %ERR%
```

Para procesar todos los alimentadores, cambie `--feeder %ALIM%` por `--all` en el paso 2
y recorra los `.dgs` generados en el paso 3:

```bat
for %%F in ("%SALIDA%\*.dgs") do (
  "%PY%" tools\powerfactory_acceptance.py --import-dgs "%%F" --ensure-scenario ^
      --run-load-flow --fix-until-converge --run-studies
)
```

---

## 7. Problemas frecuentes

| Síntoma | Causa | Solución |
| --- | --- | --- |
| `ModuleNotFoundError: igea_dgs` | Entorno sin instalar | `pip install -r requirements.txt` desde la raíz |
| `ModuleNotFoundError: pyproj` | Falta la dependencia de GPS | `pip install -r requirements.txt`, o use `--no-geography` |
| `CRS de origen … no metros` | CRS en grados o pies | Indique el UTM de su export (§4.4) |
| `Archivos de entrada no encontrados` | Ruta mal escrita | Comillas si el nombre lleva espacios o paréntesis |
| Código `3` en la importación | API de PowerFactory no visible | Abra PF; configure `PF_PYTHON` (§5.1) |
| Nombres con sufijo `__a1b2c3d4` | Dos `NetworkID` con el mismo nombre corto | Es correcto: evita que un alimentador pise al otro (§4.6) |
| Carpetas `.igea-stage-…` sobrantes | El proceso murió a la fuerza | Se pueden borrar; ningún resultado publicado se pierde |
| `topology: source_only` en el manifiesto | Cabecera sin tramos MT en el export | El DGS solo tiene la barra de cabecera. **No lo use para flujo ni estudios** |

---

## 7.bis Catálogo de parámetros eléctricos (carpeta `input/`)

El catálogo de equipos que viene en el TXT es lo único que fija la impedancia de cada
tramo, y nadie lo contrasta con la ficha del conductor que de verdad está colgado.
Cuando una fila está mal, el error se propaga en silencio a todos los tramos de ese
tipo, en todos los alimentadores.

### Generarlo

Desde la interfaz: **«Parámetros → Generar catálogo y auditar»**. Sin selección analiza
todos los alimentadores; con alimentadores marcados, solo esos.

Desde la línea de órdenes:

```bat
.venv\Scripts\python.exe toolsuild_input_catalog.py --red R.txt --cargas C.txt --equipos E.txt
.venv\Scripts\python.exe toolsuild_input_catalog.py --mdb BaseDatos.mdb
```

Sale `input\catalogo_parametros.xlsx` con siete hojas:

| Hoja | Qué lleva |
|---|---|
| `conductores_aereos` | Cada tipo aéreo en uso: R, X, B, ampacidad del modelo frente a los de ficha, con tramos y km |
| `cables_subterraneos` | Lo mismo para los cables |
| `transformadores_sed` | Una fila por potencia de SED: uk, Pk, Po, io, tomas, y los máximos reglamentarios |
| `condensadores` | Formato para bancos de condensadores (vacía si la red no tiene) |
| `reguladores` | Formato para reguladores de tensión |
| `parametros_por_elemento` | **Qué ficha hay que pedir para cada dato y qué estudio se estropea sin ella** |
| `hallazgos` | Las diferencias encontradas, con su cuenta hecha y su fuente |

### El flujo de corrección

```
TXT / MDB  ──►  modelo  ──►  [catálogo de fichas]  ──►  modelo corregido  ──►  DGS
                  │                                          │
          identidad intacta                        características al día
```

**Lo que se conserva, siempre**: el código del tipo, el material y la sección. Si el
export dice que el tramo va con `AA12003D` —un AAAC de 120 mm²—, sigue yendo con
`AA12003D`. Igual con `NK12003D`, cable de cobre de 120 mm². Eso es el inventario de lo
que está instalado y la herramienta no opina sobre él.

**Lo que se actualiza**: resistencia, reactancia, susceptancia y ampacidad, cuando la
ficha del fabricante para esa misma designación dice otra cosa.

**Por qué en ese sentido**: cuando `AA01003D` declara 10 mm² pero lleva la resistencia
de un conductor de 31 mm², o la sección está mal o el número está mal. La designación
viene del inventario de activos; la impedancia es un campo calculado del catálogo de
CYMDIST, que es justo donde aparecen las filas copiadas. Se conserva la designación y
se corrige el número.

### Completarlo y aplicarlo

1. Ponga el valor de la ficha de su proveedor en la columna `*_ficha_*` que toque
   (`R1_ficha_ohm_km`, `X1_ficha_ohm_km`, `B1_ficha_uS_km`, `ampacidad_ficha_A`…).
2. Escriba `ficha` en la columna `estado` de esa fila.
3. Aplíquelo, por cualquiera de estas tres vías:

```bat
rem Ver qué cambiaría, sin escribir nada
.venv\Scripts\python.exe toolspply_catalog_to_model.py --red R.txt --cargas C.txt --equipos E.txt

rem Convertir a DGS con las características corregidas
.venv\Scripts\python.exe toolspply_catalog_to_model.py --red R.txt --cargas C.txt --equipos E.txt ^
    --out-dir output\corregido --escribir-dgs --informe-json output\cambios.json

rem O directamente en la conversión normal
.venv\Scripts\python.exe -m igea_dgs.cli convert --red R.txt --loads C.txt --equipment E.txt ^
    --all --catalogo --source-crs EPSG:32718 --out-dir output\prod
```

Desde la interfaz: **«Aplicar catálogo corregido»**, con UN alimentador seleccionado.

El manifiesto del lote registra en `catalog_applied` y `catalog_changes` qué se corrigió
en cada alimentador: un DGS con impedancias distintas a las del TXT tiene que decir de
dónde salieron.

### Dos salvaguardas que conviene conocer

**Una fila `por_confirmar` no corrige nada**, aunque tenga un número escrito. Impide que
un valor provisional entre en el modelo como si viniera de fabricante. El TXT de origen
nunca se toca.

**La homopolar copiada sigue a la directa.** El catálogo CYMDIST guarda R0 y X0 como
copia exacta de R1 y X1. Si se corrigiera solo la directa, saldría R0 < R1, que con
retorno por tierra es imposible. Mientras no haya valor de ficha para la homopolar, la
copia se arrastra y el informe lo declara en la fuente del cambio.

### Lo que cambia en el export real

Con el catálogo generado sin teclear nada, sobre los 96 alimentadores:

| Tipo | Modelo | Ficha | Variación | Red afectada |
|---|---|---|---|---|
| `AA03502D` | 1,0891 | 0,9651 Ω/km | −11,4 % | 272,4 km |
| `AA02502D` | 1,0891 | 1,35104 Ω/km | +24,1 % | 218,1 km |
| `AA05002D` | 0,5834 | 0,6755 Ω/km | +15,8 % | 185,0 km |
| `AA01603D` | 1,0891 | 2,111 Ω/km | +93,8 % | 23,1 km |
| `AA01003D` | 1,0891 | 3,37759 Ω/km | +210,1 % | 4,0 km |

Trece características en trece tipos, 1.039,8 km de red, 56 alimentadores. **No son
cosméticos**: las pérdidas y la caída de tensión de esos tramos cambian en la misma
proporción, así que el script no aplica nada sin enseñarlo antes y marca aparte todo
cambio de más del 25 %.

### Cómo leer la columna `estado`

| Estado | Significa |
|---|---|
| `ficha` | Leído de una ficha de fabricante o de una norma, con la referencia puesta |
| `derivado` | Calculado a partir de un dato de ficha con una fórmula explícita |
| `referencia` | Valor típico de norma; sirve para detectar disparates, no para dar por buena una cifra |
| `por_confirmar` | Sin fuente pública fiable. La casilla es para que la llene el ingeniero |

---

## 7.ter Cargas en DIgSILENT: calibrar, integrar y estudiar (pestaña en cuatro pasos)

La pestaña **«Cargas en DIgSILENT»** trabaja sobre un proyecto que **ya existe** en
DIgSILENT, sin convertir nada: por eso se ve aunque no haya entradas cargadas (spec 008).
Sustituye a las antiguas filas «Cargas de SED» y «SED nuevas», retiradas por la spec 004.

El proyecto se trabaja en tres casos de estudio (specs 011, 014 y 015):

- **«Caso base»**: la red física, verificada frente al archivo original (GPS, trazado,
  conectividad, diagrama, capacidades, grupo y tensión de los transformadores) con
  `tools/powerfactory_acceptance.py` (sección 5.2). Después no se toca.
- **«Sin proyecto»**: copia del «Caso base». Aquí se calibra a la máxima, con la demanda y
  la escala en su escenario de operación y sin variación de la aplicación, y aquí hace el
  operador sus cambios manuales: si chocan con la calibración, **gana lo manual**.
- **«Con proyecto»**: copia de «Sin proyecto» con su escenario. Solo aquí nacen las cargas
  nuevas, cada una en su **variación**, que se puede activar, comparar o borrar; repetir
  la inserción no las duplica.

Un alimentador sin «Caso base» verificado no se calibra; los demás sí, y se dice cuál
queda fuera. Una modificación manual del proyecto es un aviso, nunca un bloqueo.

| Paso | En la pestaña | Lo que hace por debajo |
| --- | --- | --- |
| **1 · Proyecto de DIgSILENT** | «Leer proyectos», buscar por nombre o carpeta y elegir | `tools/pf_proyectos.py` lee la carpeta de importación (spec 005) |
| **2 · Alimentadores y calibración** | Marcar alimentadores (todos al elegir el proyecto) | Los marcados sirven a la calibración y a la integración |
| 2.1 Libros de medición | Medidor por alimentador, medición de cabecera, suministros, clientes importantes | Se validan en la web (spec 004, RF-22 a RF-45) |
| 2.2 Máxima de cabecera | «Buscar medidores» y «Buscar la máxima», para todos los marcados en un trabajo | `igea_dgs.demanda_medida` |
| 2.3 Clientes importantes | «Cruzar clientes»: su demanda queda fija | Cruce por «Suministro Act» y «Suministro» |
| 2.4 Escalar y ajustar | «Simular» o «Ajustar en DIgSILENT» | `tools/ajuste_cabecera_pf.py`, un alimentador tras otro, en el escenario de «Sin proyecto»; las cargas nuevas quedan fuera de la medida (specs 006, 008, 014 y 015) |
| **3 · Integración de nuevas** | | |
| 3.0 Convergencia | «Verificar la convergencia en DIgSILENT» | `tools/verificar_pf.py`: flujo con lo activo y cabecera de cada alimentador; no escribe |
| 3.1 Demandas en bloque | Libro de demandas (plantilla Excel o CSV) | `tools/cargas_pf.py` |
| 3.2 Una carga nueva | Formulario: kW, FP y coordenadas; se conecta a la barra de media más cercana y la SED queda con su GPS. Las mismas reglas que el libro | `tools/cargas_pf.py` |
| 3.3 Cargas nuevas en bloque | Libro de cargas nuevas | `tools/cargas_pf.py`, en «Con proyecto», una variación por carga (specs 007 y 014) |
| **4 · Obras y estudios** | | Sobre «Sin proyecto» y «Con proyecto», preparados por `tools/casos_pf.py` (spec 011) |
| 4.1 Obras de mejora | Formulario y obras guardadas; «Simular» o «Aplicar» | `tools/obras_pf.py` |
| 4.2 Estudios y guiones | Estudio, caso y límites; guiones DPL y Python del operador | `tools/estudios_pf.py` |
| 4.3 Transferencia | Dos alimentadores y su enlace | `tools/transferencia_pf.py` |

Las tres partes del paso 3 son optativas: se usa cualquier combinación y se revisan
juntas. En cada alimentador se aplican en ese orden: demandas, carga del formulario y
cargas del libro. **Aplicar** solo se activa si el último flujo del proyecto —la
verificación, el ajuste o la última integración— convergió; **Simular** está disponible
siempre y no escribe nada.

Los tres guiones se ejecutan con el intérprete de PowerFactory y reciben un plan JSON
que prepara la web (`output/web/<espacio>/planes/`):

```bat
> python tools\verificar_pf.py --plan plan.json --output-json informe.json
> python tools\ajuste_cabecera_pf.py --plan plan.json --output-json informe.json [--simular] [--cancel-file cancelar.flag]
> python tools\cargas_pf.py --plan plan.json --output-json informe.json [--simular] [--cancel-file cancelar.flag]
> python tools\cargas_pf.py --plan plan.json --deshacer informe_aplicacion.json --output-json deshecho.json [--simular]
> python tools\casos_pf.py --plan plan.json --output-json informe.json
> python tools\estudios_pf.py --plan plan.json --output-json informe.json
> python tools\estudios_pf.py --guion --plan plan.json --output-json informe.json
> python tools\obras_pf.py --bibliotecas --plan plan.json --output-json informe.json
> python tools\obras_pf.py --plan plan.json --output-json informe.json [--simular] [--cancel-file cancelar.flag]
> python tools\transferencia_pf.py --plan plan.json --output-json informe.json [--fichero transferencias.csv] [--cancel-file cancelar.flag]
```

Un solo proceso a la vez tiene el motor de DIgSILENT en la máquina (spec 019): si otro lo
tiene, el guion espera hasta 10 minutos diciendo quién, y con DIgSILENT abierto a mano
avisa y no se lanza. La web manda estos guiones a un proceso que mantiene DIgSILENT
abierto entre órdenes, sin volver a activar el proyecto, y que se cierra a los 2 minutos
sin órdenes (`IGEA_PF_SERVIDOR=0` lo apaga):

```bat
> python tools\pf_servidor.py [--inactividad 120]
> python tools\pf_cliente.py verificar_pf.py --plan plan.json --output-json informe.json
```

Un guion suelto que encuentra ese proceso sin órdenes le pide que se cierre y entra sin
esperar los 2 minutos; su salida va línea a línea aunque se redirija a un fichero, y la
API de DIgSILENT se busca en la instalación si no está en la ruta (spec 019, RF-14 a RF-16).

Un sistema eléctrico entero, con la web abierta (spec 022, RF-56):

```bat
> python tools\sistema_web.py --espacio <id> --zonal Pisco --demanda-dir referencia --periodo 2026-07 [--transformadores] [--tension-pu 1.05] [--alimentadores COD …] [--reconstruir TM106 TM101]
```

Con `--deshacer`, `cargas_pf.py` borra lo que creó una aplicación anterior según su
informe (`runs/<id>/salida/cargas_pf_aplicacion_<token>.json`): las variaciones de sus
cargas nuevas, sus símbolos del diagrama y los tipos de transformador que creó y ya no
usa nadie (spec 007, RF-38). Con `--simular` solo lo lista.

Con `--guion`, `estudios_pf.py` trabaja con los guiones DPL y Python del operador (spec
011, RF-27 a RF-30): si el plan no trae `guion`, lista los de «Sin proyecto», «Con
proyecto» y la carpeta de guiones del proyecto, con sus parámetros de entrada; si lo
trae (`{"nombre": ..., "origen": "caso"|"proyecto"}`), lo ejecuta en el `caso` del
plan con los `parametros` que escribió el operador, y el informe da su código de salida
y lo que escribió en la ventana de salida. Un guion que termina con error sale con `2`.

Con `--bibliotecas`, `obras_pf.py` solo lee lo que ofrece el formulario de las obras de
mejora (spec 011, RF-88 a RF-94): de cada alimentador del plan, su tensión, barras,
tramos con su tipo y ternas, y SED con su tipo de transformador; y los tipos de línea,
transformador, regulador y reconectador de la biblioteca del proyecto, de la global de
DIgSILENT y, si el plan trae `otro_proyecto`, de ese proyecto, que se lee sin activarlo.
`clases` limita la lista a unas clases. No escribe nada en ningún proyecto.

Sin `--bibliotecas`, `obras_pf.py` aplica las `obras` del plan (con `--simular`, solo dice
por obra su variación, los elementos que cambiaría y los tipos que copiaría). Necesita
los tres casos de `casos_pf.py`. Cada obra va en su propia variación, activa solo en los
casos que eligió el operador y nunca en el «Caso base»; los tipos que necesita se copian
a la biblioteca del proyecto sin tocar los originales. En cada caso donde queda activa se
ejecuta un flujo de carga: si no converge, la obra se desactiva en ese caso, se conserva
en el proyecto y el informe trae el diagnóstico del ajuste. Al final se comprueba que en
«Sin proyecto» los alimentadores sin obras siguen con la misma cabecera y tensión mínima.
Se cancela entre obras. Hoy se aplican el banco de condensadores (fijo, o regulando por
escalones si trae `consigna_pu`), el reconectador (interruptor con protección y reenganche
y su relé, al principio del tramo) y el regulador de tensión (intercalado al principio
del tramo con una barra nueva; `pasos` son a cada lado de la toma central), el cambio de
sección y la terna más. Sin `tramos`, la sección y la terna van a la troncal del
alimentador, que el guion calcula con el estudio de troncal (`ComBbone`) del caso y borra
después de leerla; la sección avisa de los tramos indicados que no son de ella. El cambio
de tensión (`kv_destino`) migra el alimentador entero desde su cabecera: barras de media y
de cabecera a la tensión nueva, una copia de cada tipo de línea, de SED (cambia solo la
alta) y de regulador, y los condensadores de media; la fuente queda en su barra con su
consigna en p.u. Se rechaza si otro alimentador sale de la misma barra de cabecera. Si el flujo de carga del caso no ajusta los escalones
de los condensadores (`iopt_asht`) o las tomas (`iopt_at`), el informe lo avisa.

`transferencia_pf.py` calcula cuánta carga puede pasar un alimentador a otro por su
punto de enlace, en los dos sentidos y en los casos del plan (`casos`): cierra el enlace
y abre, uno tras otro desde el enlace hacia la cabecera del que cede, cada seccionador
de la troncal y cada barra, con un flujo de carga en cada paso. Da por sentido y enlace
el seccionador y el nodo viables más lejanos con su carga, y qué limita en el primer
paso que no lo es. Solo cuentan como puntos de maniobra los seccionadores (los que el DGS
escribe con `aUsage='dct'`); en un proyecto convertido antes, `seccionadores` del plan da
sus números de equipo. En la configuración del seccionador viable más lejano da además
la capacidad del enlace (hasta dónde puede subir la carga transferida sin pasar un límite
del que recibe) y el margen sobre lo que ya transfiere: con `ComTransfer` si la licencia lo
tiene, o por flujos sucesivos, y el informe dice con cuál. Las maniobras y el punto
escalado se hacen en una variación temporal, con el escenario apagado, y al terminar todo
vuelve a como estaba.

Si un guion falla por un error inesperado, deja igualmente el informe con el tipo y el
mensaje del error, que la web muestra; la traza completa va al Registro (spec 008, RF-17).

**Códigos de salida:** `0` correcto, `1` error inesperado, `2` sin cuadrar, sin converger
o con fallos parciales, `3` sin API de DIgSILENT.

---

### Paso 5 · Planificación PIDE y gemelo digital (spec 024)

Con el proyecto del paso 1 y los alimentadores marcados en el paso 2 (cualquier proyecto
importado y calibrado, de uno o de varios alimentadores):

1. **Planificar.** Diagnostica «Sin proyecto» en DIgSILENT para el año 00 y los años del
   horizonte (04, 08, 12, 16 y 20), con la demanda escalada por la tasa del perfil; arma las
   obras por rubro, las evalúa (art. 14: anualidad del CI + COyM + CP; flujo privado con el
   pliego tarifario) y las prioriza (art. 15). Con «Aplicar solas las obras que funcionan»,
   los bancos y las ternas se simulan y, si funcionan, se aplican en «Con proyecto», cada uno
   en su variación (para deshacerlo, desactívela o bórrela en DIgSILENT). El resto queda
   propuesto con su motivo. Descarga: los formatos 01 a 15 de la norma en un Excel.
2. **Decidir.** Cada obra admite «aceptada», «rechazada» o «modificada»: el gemelo aprende
   de esa decisión.
3. **Aprender.** Simula escenarios (demanda y un tramo fuera de servicio) en una copia del
   proyecto que se borra al terminar, los guarda como episodios y reentrena la PINN si hay
   suficientes nuevos (en la GPU si la hay; `pip install -r requirements.txt` y el extra `ml`).

Además, cada acción de DIgSILENT desde la web (cargas, ajuste, verificación, obras,
estudios, transferencia, guiones) deja su episodio en el búfer local
(`output/web/_digital_twin`), que se consulta con `tools/digital_twin_buffer.py`.
La lectura de cada episodio tiene su propio límite, 5 minutos por defecto
(`gemelo.lectura_s` en el perfil): si DIgSILENT no responde a tiempo, el episodio va a
cuarentena con su motivo y la acción del operador sigue. `gemelo.captura: false` en el
perfil (o `IGEA_TWIN_CAPTURA=0`) apaga la captura.

Lo que el perfil de empresa necesita (`planificacion` en `config/perfiles/<empresa>.json`):
la tasa de crecimiento de la demanda (`crecimiento_demanda_anual`; sin ella solo se
diagnostica el año 00), el factor de carga y el precio de compra de energía (`factor_carga`,
`precio_compra_kwh`; sin ellos la evaluación privada se omite y se avisa), las tarifas, las
tasas, la vida útil y los nombres de hoja y columnas del libro CAPEX. Los límites de cada
sistema salen de su norma (NTCSE o NTCSER) en `estudios` y `normas`.

## 8. La red completa y el año 0 del PIDE

Todo lo de esta sección se puede lanzar desde la interfaz, pestaña **«Sistema completo»**,
o desde el terminal. La interfaz solo llama a estos mismos guiones, así que dan lo mismo.

### Por qué una sola grid

Hasta la versión anterior cada alimentador iba a su propio DGS y a su propio proyecto:
96 redes que no se ven entre sí. Con eso no se puede ni formular la pregunta de si un
alimentador puede respaldar a otro, ni dónde conviene el punto de apertura, porque el
respaldo y la reconfiguración ocurren **entre** alimentadores. En el export real hay 40
nodos compartidos —los puntos de enlace de la media tensión— que ningún modelo por
separado contiene.

La red unida conserva de cada alimentador **su tensión** (conviven 10 kV y 22,9 kV) y
**su fuente**, tomada del `SOURCE` de su TXT. Los enlaces entre alimentadores quedan
como **interruptores normalmente abiertos**, que es como opera la red: cada alimentador
sigue siendo su propia área radial y el enlace queda explícito y cerrable.

```bat
rem Solo el DGS de la red unida
.venv\Scripts\python.exe tools\build_system_grid.py --red R.txt --cargas C.txt --equipos E.txt

rem DGS, importación en DigSILENT y flujo de potencia
.venv\Scripts\python.exe tools\build_system_grid.py --red R.txt --cargas C.txt --equipos E.txt ^
    --importar --run-load-flow
```

### El escenario base (año 0)

Es la foto de la red tal como está, y el punto contra el que se mide todo lo demás: sin
un año 0 defendible, los años 4, 8, 12, 16 y 20 no miden nada.

```bat
rem Construye, importa, crea el caso ANIO_0_BASE, converge y ejecuta los estudios
.venv\Scripts\python.exe tools\base_scenario.py --red R.txt --cargas C.txt --equipos E.txt ^
    --nombre PIDE_ANIO_0

rem Solo la lista de datos que faltan. NO toca DigSILENT y tarda segundos.
.venv\Scripts\python.exe tools\base_scenario.py --red R.txt --cargas C.txt --equipos E.txt --solo-datos

rem Incluir los estudios que resuelven la red muchas veces, con 600 s cada uno
.venv\Scripts\python.exe tools\base_scenario.py ... --pesados --limite-segundos 600
```

### «Se ejecuta» no es «es defendible»

Es la distinción que ordena el informe, y conviene entenderla antes de leerlo.
`ComRel3` corre sin problema con todas las tasas de falla a cero y devuelve
SAIDI = SAIFI = ENS = 0. **No falla: miente.** Un número limpio y sin sentido en un
expediente que va a Osinergmin es peor que un error, porque nadie lo cuestiona.

Por eso cada estudio sale marcado de una de estas formas:

| Marca | Significa |
|---|---|
| `OK` | Se ejecutó y sus entradas son reales |
| `SIN DATOS` | Se ejecutó, pero le falta un dato y el resultado no significa nada |
| `SIN TIEMPO` | Agotó su presupuesto. Es un resultado: no cabe en un ciclo de planificación |
| `NO CORRE` | Es pesado y no se pidió `--pesados`, o la clase no existe en esta versión |

Con el export actual, **8 de 16 estudios** dan un resultado defendible. La lista de lo
que falta sale ordenada por cuántos estudios desbloquea cada dato; encabezan los
precios unitarios, que la empresa ya tiene en su VNR.

### Cada estudio en su propio proceso

`Execute()` de la API es bloqueante y no se puede interrumpir desde el mismo hilo. Un
análisis de contingencias sobre 53.000 barras puede irse a horas, y una ejecución así
se quedó colgada más de una hora llevándose por delante todo lo que faltaba. Ahora cada
estudio corre aislado con `--limite-segundos`: un cuelgue cuesta ese estudio y no el
informe.

Esto tiene una consecuencia que conviene recordar: **PowerFactory solo admite un
proceso con el motor a la vez**. Si aparece «PowerFactory no respondió», casi siempre
es que otro guion lo tiene tomado. Para liberarlo:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*run_one_study*' } | Stop-Process -Force
```

Y **no envuelva estos comandos en un `timeout` del intérprete de órdenes**: si corta el
proceso mientras habla con PowerFactory, el motor queda tomado un rato. Los guiones ya
traen sus propios límites.

---

## 9. Referencia rápida

```bat
rem Interfaz web
run_gui.bat
.venv\Scripts\igea-dgs.exe web

rem Pruebas
.venv\Scripts\python.exe -m pytest -q

rem Listar
.venv\Scripts\igea-dgs.exe list --red R.txt --loads C.txt --equipment E.txt

rem Convertir uno / todos
.venv\Scripts\igea-dgs.exe convert --red R.txt --loads C.txt --equipment E.txt --feeder ALIMENTADOR --source-crs EPSG:XXXXX --out-dir output\prod
.venv\Scripts\igea-dgs.exe convert --red R.txt --loads C.txt --equipment E.txt --all --source-crs EPSG:XXXXX --out-dir output\prod

rem Red unida y ano 0 del PIDE
.venv\Scripts\python.exe tools\build_system_grid.py --red R.txt --cargas C.txt --equipos E.txt --importar --run-load-flow
.venv\Scripts\python.exe tools\base_scenario.py --red R.txt --cargas C.txt --equipos E.txt --nombre PIDE_ANIO_0
.venv\Scripts\python.exe tools\base_scenario.py --red R.txt --cargas C.txt --equipos E.txt --solo-datos

rem Catalogo de parametros electricos -> input\catalogo_parametros.xlsx
.venv\Scripts\python.exe tools\build_input_catalog.py --red R.txt --cargas C.txt --equipos E.txt

rem Importar en DigSILENT
.venv\Scripts\python.exe tools\powerfactory_acceptance.py --import-dgs output\prod\ALIMENTADOR.dgs --manifest output\prod\ALIMENTADOR_geography.json --ensure-scenario --run-load-flow --fix-until-converge --run-studies
```

---

## 10. Herramientas de `tools/`

Todas aceptan `--help`, que no necesita DIgSILENT ni datos (spec 009). Las marcadas «PF»
se ejecutan con el intérprete de PowerFactory (Python 3.12 con `powerfactory.pyd`). El
índice de `CODIGO_FUENTE.md` dice qué spec rige cada una.

| Herramienta | Para qué | PF |
| --- | --- | --- |
| `accept_three_sources.py` | Aceptación universal TXT/MDB/VNR-GIS hasta ajuste y estudio nativos (`docs/runbooks/universal-native-load-acceptance.md`). | opcional |
| `accept_digital_twin_in111_ta225.py` | Aceptación nativa del caso dorado del gemelo digital: dos lecturas en procesos nuevos, hechos del JSON `--esperado` (`tests/fixtures/digital_twin/in111_ta225_topology_episode.json` para IN111–TA225) y su episodio en el búfer. Solo lee; no entrena ningún modelo (spec 024, T8). | PF |
| `ajuste_cabecera_pf.py` | Ajusta un alimentador a su máxima de cabecera (sección 7.ter). | PF |
| `apply_catalog_to_model.py` | Corrige impedancias y ampacidades del modelo con el catálogo de fichas (sección 7.bis). | |
| `base_scenario.py` | Escenario base (año 0): construye, hace converger y diagnostica (sección 8). | PF |
| `build_input_catalog.py` | Tabla de parámetros eléctricos en `input/` y auditoría (sección 7.bis). | |
| `build_system_grid.py` | Todos los alimentadores en una sola red, importada en PowerFactory (sección 8). | PF |
| `cargas_pf.py` | Demandas y cargas nuevas en un proyecto existente (sección 7.ter). | PF |
| `casos_pf.py` | Deja los casos «Caso base», «Sin proyecto» y «Con proyecto» sobre la red calibrada, cada uno con su escenario (spec 011; sección 7.ter). | PF |
| `asistente_entrenar.py` | Entrena el Transformer de órdenes y el clasificador de informes del asistente en su propio proceso, en la GPU, con el vocabulario del espacio (`--vocabulario`); solo promueve si pasa las puertas; `--evaluar` mide los modelos en uso. La web lo lanza con «Reentrenar» o la orden «reentrena el asistente» (spec 026, T3 y T7). | |
| `asistente_medir_ollama.py` | Mide los modelos locales de Ollama (`--modelos qwen2.5:3b llama3.1:8b`) como intérpretes de órdenes y guarda el que más acierta en menos de `--tiempo-max` segundos (spec 026, T4). | |
| `digital_twin_auditar.py` | Audita el dataset del gemelo y del asistente antes de entrenar: redes distintas, no finitos, tensiones fuera de rango, parámetros frente a etiquetas y órdenes reales (spec 027, T0). | |
| `digital_twin_buffer.py` | Búfer de episodios del gemelo digital: `list` con filtros, `show`, `validate`, `register` y `rebuild-index`, sin DIgSILENT (spec 024, T7). | |
| `digital_twin_entrenar.py` | Entrena el oráculo PINN/GNN del gemelo en su propio proceso, solo en la GPU (CUDA): sin ella se detiene con su motivo; `--forzar` entrena aunque no haya episodios nuevos; `--evaluar` no entrena y dice cuánto se apartan de DIgSILENT el modelo y la física por partición. La web lo lanza tras «Aprender» (spec 024, T11 y T17). | |
| `digital_twin_snapshot_pf.py` | Lectura de solo lectura tras una acción: reabre el proyecto, activa el caso y devuelve flujo, islas, frontera y huellas del trazado; la web la lanza sola tras cada acción (spec 024, T5). | PF |
| `escenarios_pf.py` | Escenarios del gemelo digital en una copia del proyecto que se borra al terminar: demanda escalada y tramos abiertos, con el grafo eléctrico para la PINN. La web lo lanza desde `POST /api/workspaces/{id}/digital-twin/aprender`, que después entrena si toca (spec 024, T10 y T11). | PF |
| `estudios_pf.py` | Un estudio de la spec 011 en «Sin proyecto» o «Con proyecto», sin aplicar las propuestas de los optimizadores (sección 7.ter). | PF |
| `obras_pf.py` | Obras de mejora de la spec 011: con `--bibliotecas`, alimentadores y tipos de las tres bibliotecas para el formulario; sin él, simula o aplica las obras en sus casos (sección 7.ter). | PF |
| `transferencia_pf.py` | Transferencia de carga entre dos alimentadores por su enlace, en los dos sentidos, sin dejar nada en el proyecto (spec 011; sección 7.ter). | PF |
| `transformador_set_pf.py` | Cargabilidad del devanado del transformador de la SET en el proyecto de transmisión (AD08), sin y con proyecto: a la carga de la barra de la SET se le suma el Δ de cabecera de los flujos guardados de 4.2; `--listar` da las cargas de barra y los casos. Nada se guarda (spec 017, T10; paso 4.4.2). | PF |
| `build_interactive_architecture.py` | Genera la página de la arquitectura C4 interactiva desde `docs/architecture/`. | |
| `check_pf_license.py` | Qué módulos de PowerFactory permite la licencia. | PF |
| `compare_schema.py` | Cabeceras de un DGS de otra versión de PF frente a un perfil de esquema. | |
| `construir_dataset_pide.py` | Corpus PIDE universal de una empresa: `--raiz`, `--destino`, `--empresa`, `--contrato` (solo lee el expediente). | |
| `convertir_grupos_mdb.py` | Varios alimentadores de una base en un DGS, importado y con flujo. | PF |
| `fidelidad_seleccion.py` | Que una selección pase entera del TXT al modelo y al DGS. | |
| `linea_base_dgs.py` | Línea base de DGS antes de una reorganización, y comparación después. | |
| `pide_pf.py` | Cada año del horizonte del PIDE en DIgSILENT con la demanda escalada y el diagnóstico de la norma; no deja nada en el proyecto (spec 024, T13). La web lo lanza desde `POST /api/workspaces/{id}/pide`, que además propone, prioriza y aplica solas las obras que se construyen sin diseño. | PF |
| `pf_proyectos.py` | Proyectos de la carpeta de importación y sus alimentadores (paso 1 de 7.ter). | PF |
| `powerfactory_acceptance.py` | Puerta de aceptación: importa un DGS y lo valida (sección 5). | PF |
| `prueba_representacion.py` | Red, cargas y SED del TXT en una sola hoja de PowerFactory. | PF |
| `run_one_study.py` | Trabajador de un estudio en su propio proceso (sección 8). | PF |
| `run_powerfactory_gate.bat` | Atajo de `powerfactory_acceptance.py` con el intérprete de PF (sección 5.3). | PF |
| `show_pf_diagram.py` | Abre en DIgSILENT el diagrama de un alimentador (`--feeder`). | PF |
| `sistema_web.py` | Un sistema eléctrico de punta a punta por la web abierta: convierte por sistema, importa, busca la máxima por barra de SET y calibra el sistema entero; retoma lo hecho (spec 022, RF-56). | Web + PF |
| `suggest_line_type_aliases.py` | Propone alias para tipos de línea sin ficha en el catálogo. | |
| `verify_architecture_links.py` | Comprueba los enlaces del espacio Structurizr (`docs/architecture/workspace.dsl`); necesita internet. | |
| `verificar_pf.py` | Convergencia del proyecto con lo activo (paso 3.0 de 7.ter). | PF |

Documentos relacionados: `docs/POWERFACTORY_ACCEPTANCE.md` (detalle de la puerta de
aceptación), `README.md` (instalación y arquitectura) y `CODIGO_FUENTE.md` (índice).
