# Plan de implementación — Spec 013

> **Para Codex:** ejecutar este plan con `superpowers:executing-plans` y aplicar TDD en
> cada tarea. No comenzar una tarea de PowerFactory si la anterior no dejó en verde las
> pruebas puras y web que forman su contrato.

**Objetivo:** indexar los libros mensuales de clientes, obligar a elegir un periodo común
para cabeceras y clientes, y verificar la transferencia entre dos alimentadores en estados
temporales coincidentes, conservando la evidencia de SED, cabeceras y cobertura.

**Arquitectura:** el perfil de empresa interpreta el nombre; un catálogo puro y auditable
resuelve mes, duplicados y asignaciones manuales; un trabajo en cola crea una instantánea
de libros y series de cabecera; máximas, curvas, cruce, ajuste y transferencia consumen esa
misma instantánea. La transferencia calcula primero la frontera temporal exacta en Python y
PowerFactory comprueba todos sus candidatos no dominados dentro de variaciones temporales
reversibles. Si falta un candidato o una restauración, el resultado queda parcial y no es
aceptable.

**Tecnología:** Python 3.12, FastAPI/Pydantic, `python-calamine`, `openpyxl`, React 19,
TypeScript 5.8, SVG, pytest y DIgSILENT PowerFactory 2024.

**Especificación:** `specs/013-mes-de-analisis-y-transferencia/spec.md`.

## Restricciones que rigen todo el plan

- No codificar `MMAA` ni `clientesImportantes` fuera de
  `config/perfiles/electro_dunas.json` (P13).
- No abrir los siete libros normales para determinar el mes: el nombre manda cuando casa
  con el patrón; solo un nombre no resuelto obliga a inspeccionar el libro.
- El selector empieza vacío. Servidor y navegador rechazan máxima, cruce, ajuste y
  transferencia sin un periodo expresamente elegido.
- La opción `todo` exige además un `mes_clientes` expresamente elegido; nunca se infiere de
  la máxima anual.
- Todo resultado derivado conserva `periodo_job_id`, huella de entradas, periodo, libro de
  clientes y pares alimentador-medidor. Si cualquiera cambia, se prepara otro índice.
- No interpolar timestamps. Una reducción distinta de la dominancia aprobada, un límite de
  candidatos o una comprobación nativa incompleta produce `aceptable=false`.
- Los libros reales se prueban solo si `IGEA_DEMANDA_DIR` apunta a la carpeta raíz de la
  distribuidora. Ningún dato real se copia al repositorio.
- Los cambios ajenos que ya existen en el árbol de trabajo no se reescriben ni se incluyen
  accidentalmente en los commits de esta spec.

## Fundamento científico aplicado

La implementación traduce a contratos verificables la distinción entre demanda coincidente
y suma de máximas individuales, el uso conjunto de mediciones de cabecera y perfiles de
clientes, y la reconfiguración bajo carga variable:

- Erickson, tesis de maestría, sustenta que la máxima coincidente no es la suma de máximas
  individuales: <https://trace.tennessee.edu/handle/20.500.14382/37180>.
- Singh, tesis de maestría, sustenta conservar y utilizar las series temporales de
  alimentadores: <https://repository.lib.ncsu.edu/items/a3fd70d6-6f1a-43cf-a853-bb07191b8e75>.
- Chang, tesis doctoral, y Carmona et al., artículo IEEE, sustentan reconciliar consumo de
  clientes con mediciones agregadas de cabecera:
  <https://ethesys.lis.nsysu.edu.tw/ETD-db/ETD-search-c/view_etd?URN=etd-0628102-172036> y
  <https://doi.org/10.1109/ISGTEUROPE.2010.5638995>.
- Ding, tesis doctoral, Mahdavi et al. y Azizivahed et al. sustentan verificar la
  reconfiguración con demanda variable y por intervalos:
  <http://rave.ohiolink.edu/etdc/view?acc_num=case1417291114>,
  <https://doi.org/10.1109/TII.2022.3141412> y
  <https://doi.org/10.1016/j.energy.2018.01.111>.

Estas fuentes justifican conservar la dimensión temporal. Las reglas concretas sobre
patrones, selector vacío, dominancia y cierre `fail-closed` son decisiones auditables de la
aplicación aprobadas en la spec, no afirmaciones textuales de los autores.

## Contratos de datos nuevos

```python
@dataclass(frozen=True)
class LibroClientesMes:
    path: str
    nombre: str
    mes: str | None                 # YYYY-MM
    origen_mes: Literal['nombre', 'contenido', 'manual', 'sin_mes']
    mtime_ns: int
    size: int
    activo: bool
    avisos: tuple[str, ...] = ()

@dataclass(frozen=True)
class PeriodoRef:
    job_id: str
    huella: str
    periodo: str                    # YYYY-MM o 'todo'
    mes_clientes: str
    libro_clientes: str
    pares: tuple[tuple[str, str], ...]  # alimentador, medidor

@dataclass(frozen=True)
class InstanteTransferencia:
    fecha: datetime
    objetivos: dict[str, tuple[float, float]]  # alimentador -> (kW, kVAR)
```

`huella` se calcula con rutas resueltas, tamaños, `mtime_ns`, perfil y asignaciones
manuales. No pretende sustituir un hash de custodia del contenido; sirve para invalidar un
índice cuando cambia una entrada visible.

## Mapa de cobertura

| Tarea | Requisitos |
|---|---|
| 1 | RF-1 a RF-5 |
| 2 | RF-1, RF-2, RF-4 a RF-6 |
| 3 | RF-7 a RF-10 |
| 4 | RF-11 a RF-17 |
| 5 | RF-1 a RF-17, interfaz |
| 6 | RF-18 a RF-21 |
| 7 | RF-22, trazabilidad hacia PowerFactory |
| 8 | RF-23 a RF-29, cálculo puro y fichero |
| 9 | RF-22 a RF-29, verificación PowerFactory |
| 10 | RF-23 a RF-29, API e interfaz |
| 11 | aceptación integral y evidencia |

---

### Tarea 1: perfil de empresa y catálogo mensual puro

**Archivos**

- Modificar: `src/igea_dgs/perfil_empresa.py`
- Modificar: `config/perfiles/electro_dunas.json`
- Modificar: `src/igea_dgs/demanda_medida.py`
- Modificar: `tests/test_perfil_empresa.py`
- Modificar: `tests/test_demanda_medida.py`

**Justificación científica:** Chang y Carmona et al. vinculan datos de clientes y cabecera;
el catálogo impide vincularlos a meses distintos sin evidencia.

1. Escribir pruebas fallidas `013:RF-1` a `013:RF-5` para:

   - aceptar carpeta y extensiones `.xls`, `.xlsx`, `.xlsb`, `.xlsm`;
   - resolver `0126clientesImportantes.xlsb` como `2026-01` y
     `0726clientesImportantes.xlsx` como `2026-07` usando el patrón del perfil;
   - no abrir el contenido cuando el nombre resuelve el mes;
   - inspeccionar fechas internas solo si falta patrón o no casa el nombre;
   - aceptar el contenido solo si todas las fechas válidas señalan un único mes;
   - dejar `sin_mes` ante cero o varios meses, sin usar `mtime` como fecha de negocio;
   - dar prioridad a la asignación manual explícita;
   - elegir, entre duplicados, el mayor `(mtime_ns, nombre)` y avisar ambos nombres.

   El patrón de Electro Dunas tendrá grupos nombrados `mes` y `anio`, por ejemplo
   `^(?P<mes>0[1-9]|1[0-2])(?P<anio>\\d{2})clientesImportantes\\.(xlsb|xlsx)$`.

2. Ejecutar RED:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_perfil_empresa.py tests/test_demanda_medida.py -q
   ```

3. Añadir `patron_libro_clientes` a `CLAVES`, `PerfilEmpresa` y la validación de regex.
   Implementar en `demanda_medida.py`:

   ```python
   def mes_de_nombre(nombre: str, patron: str | None) -> str | None: ...
   def meses_de_contenido(path: Path, alias: dict[str, str]) -> set[str]: ...
   def catalogar_libros_clientes(
       carpeta: Path, patron: str | None, asignaciones: dict[str, str],
       alias: dict[str, str],
   ) -> list[LibroClientesMes]: ...
   ```

   La inspección interna reconoce celdas fecha y columnas normalizadas `FECHA`, `MES` o
   `PERIODO`; una cadena ambigua no se convierte por conjetura. Registrar el origen de cada
   mes y todos los duplicados descartados.

4. Ejecutar GREEN y hacer commit solo de estos archivos:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_perfil_empresa.py tests/test_demanda_medida.py -q
   git add src/igea_dgs/perfil_empresa.py config/perfiles/electro_dunas.json src/igea_dgs/demanda_medida.py tests/test_perfil_empresa.py tests/test_demanda_medida.py
   git commit -m "feat: indexar libros mensuales de clientes"
   ```

### Tarea 2: persistencia de carpeta, instantánea y asignación manual

**Archivos**

- Modificar: `src/igea_dgs/web/workspace.py`
- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Modificar: `tests/test_demanda_medida_web.py`

**Justificación científica:** la trazabilidad exigida por el uso conjunto de perfiles y
medición agregada (Chang; Carmona et al.) requiere saber exactamente qué libro produjo el
cruce.

1. Escribir pruebas fallidas `013:RF-1`, `013:RF-2`, `013:RF-4`, `013:RF-5` y
   `013:RF-6` que demuestren:

   - `POST /demanda/clientes/path` acepta directorio o libro;
   - la carga web acepta varios libros de clientes sin cambiar la pluralidad de cabecera;
   - `PATCH /demanda/clientes/mes` conserva `{ruta_relativa: YYYY-MM}`;
   - quitar/reemplazar la fuente invalida catálogo, asignaciones inexistentes y cachés;
   - un reescaneo detecta libro agregado o retirado;
   - si tamaño o `mtime_ns` cambia mientras se escanea, la respuesta conserva la
     instantánea inicial, avisa la carrera y exige actualizar antes de usarla.

2. Ejecutar RED:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_demanda_medida_web.py -q
   ```

3. Guardar en `Workspace.demanda['clientes']` la fuente y asignaciones manuales; añadir
   caché acotada al último índice temporal. La ruta pública solo expone nombre, mes,
   origen, estado activo y avisos, nunca rutas absolutas. La lectura del contenido ocurre
   en trabajo en cola, no dentro del `PUT`/`PATCH`.

4. Ejecutar GREEN y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_demanda_medida_web.py -q
   git add src/igea_dgs/web/workspace.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py tests/test_demanda_medida_web.py
   git commit -m "feat: conservar carpeta y meses de clientes"
   ```

### Tarea 3: trabajo de índice temporal y periodos comunes

**Archivos**

- Crear: `src/igea_dgs/periodo_analisis.py`
- Modificar: `src/igea_dgs/demanda_medida.py`
- Modificar: `src/igea_dgs/web/workspace.py`
- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Crear: `tests/test_periodo_analisis.py`
- Modificar: `tests/test_demanda_medida_web.py`

**Justificación científica:** Singh y Erickson sustentan preservar la serie y calcular
coincidencia temporal, no reducir anticipadamente cada alimentador a una punta aislada.

1. Escribir pruebas fallidas `013:RF-7` a `013:RF-10` para una función pura:

   ```python
   def meses_comunes(
       series: dict[str, list[Registro]], catalogo: list[LibroClientesMes]
   ) -> list[str]: ...
   ```

   Debe devolver la intersección ordenada de meses con libro activo y al menos un registro
   válido para cada par seleccionado. Probar alimentador sin mes, último mes incompleto,
   varios medidores y orden de entrada aleatorio.

2. Escribir pruebas web fallidas para `POST /demanda/periodos/buscar`:

   - recibe pares `{alimentador, medidor}` y crea un job `demanda_periodos`;
   - respuesta: `job_id`, `huella`, catálogo, meses comunes, cobertura por par y avisos;
   - guarda las series completas solo en la caché acotada del workspace;
   - cambiar pares deja el selector sin valor y obliga a crear otro índice;
   - máxima/cruce sin `periodo_job_id` y `periodo` devuelve 422.

3. Ejecutar RED:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_periodo_analisis.py tests/test_demanda_medida_web.py -q
   ```

4. Implementar lectura única de cabeceras, catálogo y huella. El resultado del job no
   transporta las series por WebSocket. La caché se reemplaza al terminar un índice nuevo
   y se rechaza si la huella actual difiere.

5. Ejecutar GREEN y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_periodo_analisis.py tests/test_demanda_medida_web.py -q
   git add src/igea_dgs/periodo_analisis.py src/igea_dgs/demanda_medida.py src/igea_dgs/web/workspace.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py tests/test_periodo_analisis.py tests/test_demanda_medida_web.py
   git commit -m "feat: calcular periodos comunes de demanda"
   ```

### Tarea 4: máxima, cruce y procedencia dentro del periodo

**Archivos**

- Modificar: `src/igea_dgs/demanda_medida.py`
- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Modificar: `tests/test_demanda_medida.py`
- Modificar: `tests/test_demanda_medida_web.py`

**Justificación científica:** Singh respalda el análisis por intervalos; Chang y Carmona
et al. respaldan reconciliar el libro de clientes con la medición del mismo periodo.

1. Escribir pruebas fallidas `013:RF-11` a `013:RF-17`:

   - `maxima_de_registros(..., periodo='2026-07')` ignora enero-junio;
   - el resultado incluye máxima mensual, máxima de todo el periodo y mes anual;
   - el aviso RF-15 no bloquea ni cambia julio;
   - cruce de julio solo abre `0726clientesImportantes.xlsx` e informa libro/mes/origen;
   - falta de libro produce cruce vacío y modo kVA, con aviso explícito;
   - `periodo='todo'` sin `mes_clientes` falla; con abril usa abril y conserva el aviso;
   - huella, job o pares obsoletos fallan cerrados.

2. Ejecutar RED:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_demanda_medida.py tests/test_demanda_medida_web.py -q
   ```

3. Extender las peticiones de máxima y cruce con `periodo_job_id`, `periodo` y
   `mes_clientes`. Construir una sola `PeriodoRef` del lado del servidor y devolverla en
   ambos resultados. No aceptar rutas o nombres de libro enviados libremente por el
   navegador.

4. Ejecutar GREEN y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_demanda_medida.py tests/test_demanda_medida_web.py -q
   git add src/igea_dgs/demanda_medida.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py tests/test_demanda_medida.py tests/test_demanda_medida_web.py
   git commit -m "feat: acotar maxima y clientes al periodo"
   ```

### Tarea 5: carpeta, catálogo y selector explícito en el paso 2

**Archivos**

- Modificar: `frontend/src/types.ts`
- Modificar: `frontend/src/api.ts`
- Modificar: `frontend/src/components/DemandaMedida.tsx`
- Modificar: `frontend/src/components/AjusteCabecera.tsx`
- Modificar: `frontend/src/styles.css`
- Modificar: `tests/test_demanda_medida_web.py`
- Crear: `docs/acceptance/013-mes-clientes.md`

**Justificación científica:** la UI hace visible el emparejamiento temporal que exigen las
fuentes de perfilado y medición; no automatiza una decisión operativa que Erickson muestra
que depende de coincidencia.

1. Añadir pruebas API de comportamiento `013:RF-1` a `013:RF-17`: opciones devueltas,
   selección vacía, bloqueo antes de elegir, asignación manual y modo `todo`. No añadir
   pruebas que solo busquen cadenas en el fuente TSX.

2. Ejecutar RED y comprobar también el error de tipos previsto:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_demanda_medida_web.py -q
   Set-Location frontend
   npm run typecheck
   Set-Location ..
   ```

3. Implementar:

   - control de carpeta/libros y tabla `nombre | mes | origen | activo | aviso`;
   - acción de asignar mes a los `sin_mes`;
   - botón «Actualizar índice»;
   - selector controlado cuyo estado inicial es `''`, opciones `YYYY-MM` y `todo`;
   - selector adicional obligatorio del mes de clientes solo en `todo`;
   - reinicio del periodo al cambiar alimentadores, medidores o fuente;
   - botones de máxima, cruce y ajuste deshabilitados sin `PeriodoRef` vigente;
   - avisos RF-13, RF-15 y RF-17 junto al dato que afectan.

4. Crear el guion de aceptación de navegador con casos observables y espacio para
   captura: carpeta, siete libros, selector vacío, julio, `todo`, asignación manual y
   cambio de alimentador. Es evidencia complementaria; no sustituye las pruebas del API.

5. Ejecutar GREEN/build y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_demanda_medida_web.py -q
   Set-Location frontend
   npm run build
   Set-Location ..
   git add frontend/src/types.ts frontend/src/api.ts frontend/src/components/DemandaMedida.tsx frontend/src/components/AjusteCabecera.tsx frontend/src/styles.css tests/test_demanda_medida_web.py docs/acceptance/013-mes-clientes.md
   git commit -m "feat: elegir mes comun en demanda medida"
   ```

### Tarea 6: curvas sincronizadas de varios alimentadores

**Archivos**

- Modificar: `src/igea_dgs/demanda_medida.py`
- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Modificar: `frontend/src/types.ts`
- Modificar: `frontend/src/api.ts`
- Modificar: `frontend/src/components/CurvaCabecera.tsx`
- Modificar: `frontend/src/styles.css`
- Modificar: `tests/test_demanda_medida.py`
- Modificar: `tests/test_demanda_medida_web.py`
- Modificar: `docs/acceptance/013-mes-clientes.md`

**Justificación científica:** Singh y Erickson requieren observar perfiles sobre un eje
temporal común para distinguir simultaneidad y diversidad.

1. Escribir pruebas fallidas `013:RF-18` a `013:RF-21` para un endpoint de curvas que:

   - devuelve una serie por par seleccionado, todas con el mismo `inicio`/`fin`;
   - recorta inicialmente al mes elegido;
   - marca la máxima mensual de cada serie;
   - conserva huecos como huecos, sin interpolación;
   - reduce cada serie con el mismo conjunto de intervalos y conserva sus extremos.

2. Ejecutar RED. Implementar `GET .../demanda/cabecera/{job_id}/curvas` y ampliar el SVG
   actual con leyenda, colores accesibles, una polilínea por alimentador y marcador por
   máxima. El zoom conserva un eje común; «Ver mes» restaura el periodo seleccionado.

3. Ejecutar pruebas, build y aceptación de navegador; adjuntar captura de ambas curvas
   solo después de confirmar los datos mostrados en la respuesta del endpoint.

4. Commit:

   ```powershell
   git add src/igea_dgs/demanda_medida.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py frontend/src/types.ts frontend/src/api.ts frontend/src/components/CurvaCabecera.tsx frontend/src/styles.css tests/test_demanda_medida.py tests/test_demanda_medida_web.py docs/acceptance/013-mes-clientes.md
   git commit -m "feat: comparar curvas en un eje temporal"
   ```

### Tarea 7: encadenar el periodo al ajuste y la transferencia

**Archivos**

- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Modificar: `frontend/src/components/CargasTab.tsx`
- Modificar: `frontend/src/components/TransferenciaPF.tsx`
- Modificar: `frontend/src/api.ts`
- Modificar: `tests/test_ajuste_cabecera_web.py`
- Modificar: `tests/test_estudios_pf_web.py`

**Justificación científica:** Ding y Mahdavi et al. tratan reconfiguración bajo estados de
carga definidos; por eso una transferencia no puede desligarse del índice temporal que la
originó.

1. Escribir pruebas fallidas `013:RF-22` que comprueben que `ajuste_plan` recibe y guarda
   `PeriodoRef`, y que transferencia exige el id de un `ajuste_aplicar` terminado para el
   mismo proyecto, dos alimentadores y la misma huella.

2. Probar rechazo por trabajo simulado/no aplicado, ajuste de otro proyecto, un solo
   alimentador, tres alimentadores, periodo obsoleto y máxima independiente enviada por el
   cliente.

3. Implementar la cadena servidor → `CargasTab` → `TransferenciaPF` pasando
   `ajuste_job_id`. La petición de transferencia no lleva objetivos kW/kVAR arbitrarios:
   el servidor recupera las series y la procedencia del trabajo aplicado.

4. Ejecutar GREEN, build y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_ajuste_cabecera_web.py tests/test_estudios_pf_web.py -q
   Set-Location frontend
   npm run build
   Set-Location ..
   git add src/igea_dgs/web/services.py src/igea_dgs/web/app.py frontend/src/components/CargasTab.tsx frontend/src/components/TransferenciaPF.tsx frontend/src/api.ts tests/test_ajuste_cabecera_web.py tests/test_estudios_pf_web.py
   git commit -m "feat: enlazar transferencia con el periodo aplicado"
   ```

### Tarea 8: candidatos temporales, dominancia y libro de evidencia

**Archivos**

- Modificar: `src/igea_dgs/periodo_analisis.py`
- Modificar: `src/igea_dgs/transferencia_pf.py`
- Modificar: `tests/test_periodo_analisis.py`
- Modificar: `tests/test_transferencia_pf.py`

**Justificación científica:** Erickson impide sumar puntas no coincidentes; Azizivahed et
al. y Mahdavi et al. respaldan evaluar reconfiguración bajo múltiples estados variables.

1. Escribir pruebas fallidas `013:RF-22`, `013:RF-27`, `013:RF-28` y `013:RF-29` para:

   ```python
   def instantes_comunes(series, alimentadores, periodo) -> list[InstanteTransferencia]: ...
   def frontera_no_dominada(instantes, donante, receptor) -> FronteraTemporal: ...
   ```

   Casos obligatorios: timestamps iguales exactos; segundos/zona distintos no coinciden;
   registro sin kW se excluye; kVAR ausente impide descartar por dominancia; empate
   determinista; cada descarte conserva `dominado_por`; sin comunes bloquea; ningún `cap`
   silencioso.

2. Escribir pruebas fallidas `013:RF-23` a `013:RF-26` para ampliar `Punto`, `Paso` y
   `SentidoTransferencia` con SED acumuladas, kW/kVA, instante, cabeceras antes/después y
   cobertura. Sustituir el descargable CSV por XLSX con hojas:

   - `Pasos`;
   - `SED transferidas`;
   - `Cobertura temporal`.

   Reabrir el XLSX con `openpyxl` en la prueba y comparar celdas con el resultado JSON.

3. Ejecutar RED:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_periodo_analisis.py tests/test_transferencia_pf.py -q
   ```

4. Implementar la frontera exacta. Un instante domina a otro solo si sus cuatro
   componentes `(P_d, |Q_d|, P_r, |Q_r|)` son no menores y al menos uno es mayor; si
   cualquiera de los cuatro Q falta, ese par no permite descarte. No redondear antes de
   comparar.

5. Ejecutar GREEN y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_periodo_analisis.py tests/test_transferencia_pf.py -q
   git add src/igea_dgs/periodo_analisis.py src/igea_dgs/transferencia_pf.py tests/test_periodo_analisis.py tests/test_transferencia_pf.py
   git commit -m "feat: construir frontera temporal de transferencia"
   ```

### Tarea 9: verificar cada candidato en PowerFactory y restaurar el modelo

**Archivos**

- Modificar: `tools/transferencia_pf.py`
- Modificar: `tools/cargas_pf.py`
- Modificar: `tests/fake_pf.py`
- Modificar: `tests/test_transferencia_pf_guion.py`

**Justificación científica:** Ding, Mahdavi et al. y Azizivahed et al. justifican que la
capacidad de reconfiguración se determine con flujo de carga en los estados variables, no
solo por aritmética de puntas.

1. Escribir pruebas fallidas `013:RF-22` a `013:RF-29` con `fake_pf` para demostrar:

   - cada candidato lleva objetivos P/Q de ambos alimentadores del mismo timestamp;
   - ambos se cuadran y releen antes de maniobrar;
   - cada sentido/enlace parte del mismo estado base restaurado;
   - `Red.colgado` devuelve por carga `loc_name`, kW, kVAR y kVA;
   - el paso viable más lejano conserva SED acumuladas y cabeceras antes/después;
   - se evalúan todos los no dominados aunque uno falle, siempre que la restauración de ese
     candidato quede verificada; una restauración fallida detiene el trabajo;
   - candidato no convergido, no cuadrado o no relecturable deja `aceptable=false`;
   - cancelación, excepción y término normal restauran cargas, escalas, escenario, caso,
     variación y opciones de `ComLdf`.

2. Ejecutar RED:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_transferencia_pf_guion.py -q
   ```

3. Extraer de `tools/cargas_pf.py` una lectura reusable de cabecera sin cambiar su
   semántica. En `tools/transferencia_pf.py` implementar:

   ```python
   def ajustar_instante(app, alimentadores, objetivos, tolerancia, cancelado) -> dict: ...
   def verificar_candidato(app, instante, sentidos, enlaces, ...) -> dict: ...
   ```

   El ajuste temporal usa como base el ajuste mensual aplicado, escala P y Q por separado,
   ejecuta `ComLdf` y exige tolerancia y relectura en ambas cabeceras. Crear una variación
   temporal identificable por candidato y eliminarla al restaurar. No grabar el proyecto.

4. La selección final por sentido/enlace toma el mínimo de las máximas transferencias
   viables entre todos los candidatos verificados. Si falta alguno, puede mostrarse el
   detalle observado, pero `aceptable=false`, `capacidad_comprobada=null` y se lista la
   evidencia faltante.

5. Ejecutar GREEN y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_transferencia_pf_guion.py -q
   git add tools/transferencia_pf.py tools/cargas_pf.py tests/fake_pf.py tests/test_transferencia_pf_guion.py
   git commit -m "feat: verificar transferencia por instante comun"
   ```

### Tarea 10: orquestación, resultados y UI de transferencia

**Archivos**

- Modificar: `src/igea_dgs/web/services.py`
- Modificar: `src/igea_dgs/web/app.py`
- Modificar: `frontend/src/types.ts`
- Modificar: `frontend/src/api.ts`
- Modificar: `frontend/src/components/TransferenciaPF.tsx`
- Modificar: `frontend/src/styles.css`
- Modificar: `tests/test_estudios_pf_web.py`
- Modificar: `docs/acceptance/013-mes-clientes.md`

**Justificación científica:** la evidencia de estado, sentido y resultado operacionaliza
la evaluación multitemporal descrita por Ding, Mahdavi et al. y Azizivahed et al.

1. Escribir pruebas web fallidas `013:RF-23` a `013:RF-29` para comprobar:

   - el plan enviado al guion contiene todos los no dominados y su cobertura;
   - progreso informa `candidato i/n`, sentido y enlace;
   - JSON y XLSX sobreviven a un resultado parcial sin llamarlo capacidad comprobada;
   - descarga usa `.xlsx` y reabre el archivo generado;
   - el servidor rechaza un informe cuya huella/periodo no coincide con el plan.

2. Implementar en la UI: periodo, instante crítico, cobertura, criterio, kW/kVA por
   sentido/enlace, cabeceras antes/después, tabla de SED y estado visible
   `comprobada | parcial/no aceptable`. No mostrar `0` cuando el valor es desconocido.

3. Añadir al guion de aceptación los dos sentidos CA101 ↔ PE104, apertura del XLSX y
   comparación de una SED y una cabecera con la respuesta JSON.

4. Ejecutar GREEN/build y commit:

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_estudios_pf_web.py -q
   Set-Location frontend
   npm run build
   Set-Location ..
   git add src/igea_dgs/web/services.py src/igea_dgs/web/app.py frontend/src/types.ts frontend/src/api.ts frontend/src/components/TransferenciaPF.tsx frontend/src/styles.css tests/test_estudios_pf_web.py docs/acceptance/013-mes-clientes.md
   git commit -m "feat: informar transferencia temporal comprobada"
   ```

### Tarea 11: verificación integral y aceptación nativa

**Archivos**

- Modificar si la evidencia lo exige: `docs/acceptance/013-mes-clientes.md`
- Crear por ejecución: `docs/acceptance/evidence/013/<fecha>/...`

**Justificación científica:** las fuentes respaldan el método; la aceptación nativa
demuestra que el método quedó materializado en el motor y datos concretos, sin confundir
pruebas sintéticas con resultado operacional.

1. Verificar trazabilidad de todos los RF:

   ```powershell
   rg -o "013:RF-[0-9]+" tests | Sort-Object -Unique
   ```

   Deben aparecer RF-1 a RF-29. Una prueba puede cubrir varios RF si afirma su conducta,
   pero una mera cadena sin aserción relevante no cuenta.

2. Ejecutar suite y frontend desde árbol limpio de artefactos temporales:

   ```powershell
   .venv\Scripts\python.exe -m pytest -q
   Set-Location frontend
   npm run typecheck
   npm run build
   Set-Location ..
   ```

3. Ejecutar prueba real de libros solo con datos externos configurados:

   ```powershell
   $env:IGEA_DEMANDA_DIR = 'D:\converter\ConversorIGEA_DGS\referencia'
   .venv\Scripts\python.exe -m pytest tests/test_demanda_medida.py -k real -q
   ```

   Confirmar en evidencia los siete archivos enero-julio, ambos formatos y que el libro
   de julio seleccionado es `0726clientesImportantes.xlsx`. Si la ruta real no coincide,
   resolverla primero y registrar la ruta usada; no adaptar la prueba para que omita datos.

4. Aceptación de navegador:

   - abrir el paso 2 y comprobar selector vacío;
   - elegir julio y comparar tabla/curvas con el JSON del API;
   - comprobar avisos de máxima anual distinta sin cambio automático;
   - cambiar a `todo`, exigir mes de clientes y revisar procedencia;
   - capturar catálogo, curvas comunes y resultado de transferencia.

5. Aceptación PowerFactory 2024 con CA101 y PE104:

   - registrar proyecto, caso, variación base, huella, periodo y candidatos;
   - para cada candidato no dominado, conservar objetivos y relectura P/Q de ambas
     cabeceras, convergencia, sentido/enlace y máximo viable;
   - verificar que instante de ambas cabeceras es idéntico;
   - reabrir/consultar el estado nativo tras terminar y demostrar restauración de las
     variaciones temporales;
   - descargar y reabrir el XLSX; comparar SED, kW/kVA y cabeceras con el informe JSON;
   - si falta un candidato o falla la restauración, documentar `NO ACEPTABLE` y no cerrar
     RF-22 a RF-29.

6. Guardar comandos, versiones, logs, capturas y hashes SHA-256 de JSON/XLSX en la carpeta
   de evidencia. Actualizar el guion con `PASS`, `FAIL` o `BLOCKED` por compuerta.

7. Revisar que cada commit de la spec contiene solo archivos intencionados y que los
   cambios locales previos siguen intactos:

   ```powershell
   git status --short
   git log --oneline --decorate -12
   ```

8. Commit final solo de evidencia/documentación. No hacer `push` sin petición expresa:

   ```powershell
   git add docs/acceptance/013-mes-clientes.md docs/acceptance/evidence/013
   git commit -m "test: documentar aceptacion de la spec 013"
   ```

## Riesgos y respuestas verificables

| Riesgo | Respuesta | Prueba/compuerta |
|---|---|---|
| Nombre no resuelto o fechas internas ambiguas | `sin_mes`; nunca inferir por `mtime` | Tareas 1 y 2 |
| La carpeta cambia durante un job | instantánea y huella; aviso y reindexación | Tarea 2 |
| Timestamps no alineados o zonas distintas | igualdad exacta normalizada; sin interpolación | Tarea 8 |
| Falta kVAR y se elimina un caso crítico | no aplicar dominancia a ese par | Tarea 8 |
| Demasiados candidatos | progreso y ejecución completa; cualquier cap es parcial | Tareas 8 a 10 |
| Estado PF queda contaminado | snapshot, `finally`, relectura y aceptación nativa | Tarea 9 y 11 |
| Un candidato PF falla | conservar detalle pero anular capacidad comprobada | Tareas 9 y 10 |
| UI parece correcta pero backend usa otro libro | `PeriodoRef`, huella y comparación JSON/XLSX | Tareas 4, 10 y 11 |

## Criterio para declarar terminado

La implementación no se declara terminada solo porque pytest y el build estén en verde.
Queda terminada cuando RF-1 a RF-29 tienen prueba de conducta, los siete libros reales se
indexan con su mes correcto, la UI conserva una selección explícita, y la aceptación nativa
CA101/PE104 demuestra —con relectura y restauración— que todos los candidatos necesarios se
simularon usando el mismo instante para ambos alimentadores. Cualquier omisión se reporta
como parcial o bloqueada, nunca como transferencia comprobada.
