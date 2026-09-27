# Manual de comandos — pruebas, conversión e importación en DigSILENT

Cada cosa que hace la interfaz gráfica se puede lanzar también desde la consola. Este
manual empareja las dos vías: **lo que pulsa en la ventana** y **el comando equivalente**,
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

Para poder ejecutar además las pruebas:

```bat
> python -m pip install -r requirements-dev.txt
```

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
| Lienzo / hoja | `--hoja AUTO` (defecto) o `A0`–`A4` | `AUTO` conserva 2,08 unidades/metro y dimensiona el lienzo con la red; A0–A4 son formatos explícitos de impresión |

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
| `{alimentador}_feeder_metadata.json` | Asignación auditable de cada carga/fuente a su alimentador; incluye SHA-256 del DGS |
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

En la ventana: botón **Cancelar**, habilitado mientras convierte. No empieza ningún
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
    --feeder-metadata output\produccion\IN111_feeder_metadata.json ^
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
| `--feeder-metadata` | Sidecar enlazado por SHA-256; crea/verifica `p:alimentador` y asigna cargas/fuentes sin ambigüedad |
| `--ensure-scenario` | Crea y activa un escenario de operación |
| `--run-load-flow` | Ejecuta el flujo de potencia (ComLdf) y exige convergencia |
| `--fix-until-converge` | Aplica correcciones si no converge a la primera |
| `--run-studies` | Suite de estudios (incluye cortocircuito ComShc si la licencia lo permite) |
| `--require-diagram` | Exige `ElmNet.pDiagram` + `IntGrf` |
| `--output-json` / `--output-txt` | Informes de aceptación |

La metadata explícita es obligatoria si se proporciona la bandera; si se omite, la
herramienta descubre el hermano `{stem}_feeder_metadata.json`. Antes de modificar Data
Extensions comprueba que el proyecto activo sea exactamente el recién importado.
PowerFactory 2024 expone `AddString` como `STRING_VEC`; la compuerta maneja esa
representación, relee las asignaciones y revierte lo ya escrito ante el primer fallo.

### 5.2.1 Ver la columna `Alimentador`

1. Abra **Network Model Manager → Generators, Loads, and Sources → General Load**.
2. En `Basic Data`, agregue **Alimentador** después de **Grid** si está disponible.
3. Si no aparece, use **Flexible Data → selección de variables → Data Extension → Alimentador** y arrastre la columna después de `Grid`. Esta es la vista garantizada por la documentación de DIgSILENT.
4. Repita en **Synchronous Machine** y **External Grid**.
5. Filtre por `NA203`/`NA205` y confronte los conteos del informe. Una fila `SE50033` en `General Load` es el `ElmLod` alojado dentro de la SED `ElmSubstat`; no sustituye el transformador `ElmTr2`.

Para una base Access cuya red y catálogo CYMEQ estén separados, la herramienta de
grupos admite ambas rutas:

```bat
> .venv\Scripts\python.exe tools\convertir_grupos_mdb.py ^
    --mdb red.mdb --equipment-db equipos.mdb ^
    --catalogo input\catalogo_parametros.xlsx ^
    --grupo NA203_NA205=NA203,NA205 --hoja AUTO --out-dir output\grupo
```

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

## 7.ter Crear SED nuevas desde la interfaz

Los botones 3, 4 y 5 de la fila «SED nuevas»:

* **3) Descargar plantilla de creación** — una fila por SED. Basta con `SED`, `CoordX`,
  `CoordY` y `kVA_instalado`. Trae además una hoja `nodos_validos` con los nodos del
  alimentador.
* **4) Cargar fichero y crear** — lee la plantilla, resuelve cada punto y aplica.
* **5) Crear una SED…** — el mismo camino con un formulario, para una sola.

Qué hace con las coordenadas: busca el **nodo más cercano**, usa esa distancia como
longitud de la derivación y elige el **conductor aéreo** por ampacidad con margen y
caída de tensión. En PowerFactory crea el nodo con su GPS, el tramo con su `TypLne`, la
`ElmSubstat` con sus barras MT y BT, el `TypTr2`/`ElmTr2`, el `ElmCoup` y el `ElmLod`.

Un punto a más de 2 km del nodo más cercano se rechaza: casi siempre es un error de
coordenadas o un CRS equivocado, no una derivación real.

**Sobre la elección automática de sección.** Medido con datos reales a 22,9 kV, una SED
de 15 a 630 kVA toma entre 0,4 y 16 A, y el conductor más pequeño de un catálogo real
ya es de 112 A. Ni la ampacidad ni la caída de tensión discriminan en ese rango: sale
siempre el menor. El campo `binding` del informe lo dice (`minimo`, `ampacidad`,
`caida` o `impuesto`). Lo que decide en la práctica es la normalización de la empresa,
y para eso está la columna `conductor`.

---

## 9. La red completa y el año 0 del PIDE

Todo lo de esta sección se puede lanzar desde la interfaz, fila **«Sistema»**, o desde
el terminal. La interfaz solo llama a estos mismos guiones, así que dan lo mismo.

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

rem Red unida y ano 0 del PIDE
.venv\Scripts\python.exe tools\build_system_grid.py --red R.txt --cargas C.txt --equipos E.txt --importar --run-load-flow
.venv\Scripts\python.exe tools\base_scenario.py --red R.txt --cargas C.txt --equipos E.txt --nombre PIDE_ANIO_0
.venv\Scripts\python.exe tools\base_scenario.py --red R.txt --cargas C.txt --equipos E.txt --solo-datos

rem Catalogo de parametros electricos -> input\catalogo_parametros.xlsx
.venv\Scripts\python.exe tools\build_input_catalog.py --red R.txt --cargas C.txt --equipos E.txt

rem Importar en DigSILENT
.venv\Scripts\python.exe tools\powerfactory_acceptance.py --import-dgs output\prod\IN111.dgs --manifest output\prod\IN111_geography.json --ensure-scenario --run-load-flow --fix-until-converge --run-studies
```

Documentos relacionados: `docs/POWERFACTORY_ACCEPTANCE.md` (detalle de la puerta de
aceptación) y `README.md` (instalación y arquitectura).
