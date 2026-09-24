# Manual de comandos — pruebas, conversión e importación en DigSILENT

Cada cosa que hace la interfaz gráfica se puede lanzar también desde la consola. Este
manual empareja las dos vías: **lo que pulsa en la ventana** y **el comando equivalente**,
para poder automatizar, diagnosticar una incidencia o trabajar en una máquina sin pantalla.

Todos los comandos se ejecutan desde la raíz del proyecto (`D:\converter\ConversorIGEA_DGS`)
en **PowerShell** o **CMD** de Windows. El entorno virtual es `.venv`.

> Convención de este manual: `>` es el símbolo del sistema; no lo escriba.

---

## 0. Preparar el entorno (una sola vez por máquina)

```bat
> python -m venv .venv
> .venv\Scripts\activate
> python -m pip install -r requirements.txt
```

Para poder ejecutar además las pruebas:

```bat
> python -m pip install -r requirements-dev.txt
```

Comprobar que quedó bien instalado:

```bat
> .venv\Scripts\python.exe -c "import igea_dgs, pyproj; print(igea_dgs.__version__)"
2.1.0
```

Si aparece `ModuleNotFoundError: pyproj`, faltan las dependencias de georreferenciación:
repita `pip install -r requirements.txt`, o convierta con `--no-geography`.

---

## 1. Abrir la interfaz gráfica

| En la ventana | Comando |
| --- | --- |
| Doble clic en `run_gui.bat` | `> .venv\Scripts\python.exe -m igea_dgs.gui` |

`run_gui.bat` prefiere el `.venv`, instala las dependencias de producción si faltan y
abre la ventana. El comando directo no instala nada: asume el entorno ya preparado.

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

| En la ventana | Comando |
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

**Paso 1** tiene dos botones de opción: *Alternativa 1 — Tres ficheros TXT* y
*Alternativa 2 — Base de datos Access*. Al cambiar, el panel de campos se sustituye. En
la alternativa 2 solo la base de red es obligatoria; la base de equipos y el estudio son
opcionales.

---

## 4. Conversión a DGS

| En la ventana | Comando |
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

| Casilla en la ventana | Opción | Qué hace |
| --- | --- | --- |
| Georreferenciación (GPS + diagrama) | *(activa por defecto)* / `--no-geography` | GPS en terminales, diagrama `IntGrf` y sidecar `_geography.json` |
| Modo estricto | *(activo por defecto)* / `--non-strict` | En estricto, una topología rota bloquea el alimentador |
| Excel multi-hoja | `--export-xlsx` | Requiere `pip install "igea-dgs[xlsx]"` |
| TSV por tabla | `--export-tsv` | Una carpeta `{alimentador}_dgs_tables/` |
| Vista previa | `--preview` | Mapa HTML + GeoJSON. Exige georreferenciación |
| CRS origen | `--source-crs EPSG:XXXXX` | El de **su** export |
| Aliases de tipos | `--aliases ruta.json` | Equivalencias de códigos de conductor |

### 4.4 El CRS de origen: el punto que más caro sale equivocar

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

En la ventana: botón **Cancelar**, habilitado mientras convierte. Conserva lo ya
convertido y descarta entero el alimentador en curso.

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

| En la ventana | Comando |
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

## 8. Referencia rápida

```bat
rem Interfaz
.venv\Scripts\python.exe -m igea_dgs.gui

rem Pruebas
.venv\Scripts\python.exe -m pytest -q

rem Listar
.venv\Scripts\python.exe -m igea_dgs.cli list --red R.txt --loads C.txt --equipment E.txt

rem Convertir uno / todos
.venv\Scripts\python.exe -m igea_dgs.cli convert --red R.txt --loads C.txt --equipment E.txt --feeder IN111 --source-crs EPSG:32718 --out-dir output\prod
.venv\Scripts\python.exe -m igea_dgs.cli convert --red R.txt --loads C.txt --equipment E.txt --all --source-crs EPSG:32718 --out-dir output\prod

rem Importar en DigSILENT
.venv\Scripts\python.exe tools\powerfactory_acceptance.py --import-dgs output\prod\IN111.dgs --manifest output\prod\IN111_geography.json --ensure-scenario --run-load-flow --fix-until-converge --run-studies
```

Documentos relacionados: `docs/POWERFACTORY_ACCEPTANCE.md` (detalle de la puerta de
aceptación) y `README.md` (instalación y arquitectura).
