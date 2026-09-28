# Diseño de actualización masiva de cargas CSV/XLSX

## Objetivo

Permitir que un operador actualice en una sola operación las cargas de uno o varios
alimentadores desde CSV o Excel, con vista previa, identificación inequívoca de cada
`ElmLod`, aplicación controlada mediante la API de PowerFactory, validación del flujo de
carga y restauración automática del alimentador ante cualquier fallo.

## Alcance aprobado

- La interfaz principal sigue siendo React + FastAPI.
- Se conservan las plantillas CSV/XLSX y el módulo actual de cargas de SED.
- Un libro Excel puede contener una hoja por alimentador.
- Un CSV puede contener varios alimentadores mediante una columna obligatoria
  `Alimentador`.
- La operación se ejecuta asíncronamente desde la interfaz.
- El procesamiento de lectura, normalización y conciliación puede usar varios hilos; la
  escritura en PowerFactory permanece serializada en una sola sesión porque su estado de
  proyecto y caso de estudio es compartido.
- La atomicidad es por alimentador. Si un alimentador falla, se restaura por completo;
  los alimentadores ya confirmados conservan sus cambios y el lote informa el resultado
  individual de cada uno.
- La creación de SED inexistentes continúa perteneciendo al módulo `SED nuevas`; una
  actualización masiva nunca inventa cargas ni topología.

## Estado actual verificado

El repositorio ya contiene:

- Generación y lectura de plantillas en `src/igea_dgs/loads.py`.
- Validación de columnas, unidades, duplicados, acciones y SED desconocidas.
- Construcción de un plan sin modificar PowerFactory.
- Endpoints FastAPI de plantilla, plan y aplicación.
- Pantalla React de vista previa y confirmación.
- Aplicador externo `tools/apply_sed_loads.py` para la versión de Python exigida por
  PowerFactory.

La verificación del 27 de septiembre de 2026 obtuvo 34 pruebas Python aprobadas y 5
pruebas React aprobadas. La lectura directa de `referencia/PA217.xlsx` encontró 170
filas, 111 cargas derivadas, 59 filas sin datos, 2 duplicados, 169 coincidencias, una
SED desconocida y 84 SED no mencionadas. El plan se bloqueó correctamente por los dos
duplicados.

Las brechas que este diseño corrige son: aplicación de una sola hoja a la vez,
identificación basada solo en `loc_name`, ausencia de preflight completo, posibilidad de
escritura parcial, falta de rollback, verificación incompleta de P/Q/FP y retorno exitoso
aunque el flujo no converja.

## Contrato de entrada

### Formatos

Excel `.xlsx`:

- Una hoja por alimentador.
- El nombre de la hoja es el nombre canónico del alimentador.
- Las hojas auxiliares se admiten solo si no parecen tablas de cargas; se registran como
  ignoradas.

CSV `.csv`:

- Codificación UTF-8 con o sin BOM.
- Delimitador `;`, `,` o tabulador detectado de forma determinista.
- La columna `Alimentador` es obligatoria cuando el lote contiene más de un alimentador.

Columnas canónicas:

- `Alimentador`
- `SED`
- `kW`
- `kvar`
- `kVA`
- `FP`
- `accion`
- `observaciones`

Se mantienen los alias actualmente soportados, pero la plantilla generada utiliza
siempre esos nombres canónicos.

### Acciones

- `actualizar` o vacío: aplica una carga válida distinta de la condición sin datos.
- `omitir`: no modifica la carga y registra la decisión del operador.
- `poner_cero`: establece explícitamente P=0 y Q=0.

### Regla aprobada de cuatro ceros

Una fila se clasifica como `SIN_DATOS` cuando:

```text
kW = 0
kvar = 0
kVA = 0
FP = 0
```

La misma clasificación se aplica cuando los cuatro campos están vacíos. Una fila
`SIN_DATOS` deja la carga existente sin cambios. Solamente `accion=poner_cero` autoriza
llevar la carga a cero.

### Resolución de potencia

1. Con `poner_cero`, P y Q son cero y los demás campos son informativos.
2. Si `kW` o `kvar` contienen un valor distinto de cero, esos valores mandan; el campo
   faltante vale cero y se recalculan kVA y FP.
3. Si P y Q no están informados y `kVA > 0` con `0 < FP <= 1`, se deriva:
   `kW = kVA·FP` y `kvar = kVA·sqrt(1-FP²)`.
4. Si se informan ambos pares P/Q y kVA/FP, una diferencia superior al 1 % bloquea la
   fila; el conversor no elige silenciosamente uno de los pares.
5. kW, kvar y kVA negativos, FP fuera de `[0, 1]`, valores no numéricos, infinitos o
   fórmulas sin resultado calculado son errores bloqueantes.

## Identidad y conciliación

La identidad lógica es la tupla:

```text
(Alimentador, NetworkID, SED)
```

El operador solo escribe Alimentador y SED. `NetworkID`, terminal, subestación, FID y
proyecto PowerFactory se incorporan desde el modelo y los metadatos custodiados por el
workspace.

Antes de producir un plan aplicable se comprueba:

1. El alimentador existe en el dataset TXT/MDB cargado.
2. La SED pertenece eléctricamente a ese alimentador.
3. Existe exactamente una asignación `ElmLod` en los metadatos DGS.
4. El proyecto PowerFactory corresponde al DGS importado por ese workspace.
5. El hash del DGS y la revisión del modelo no cambiaron desde la creación del plan.

Una coincidencia por `loc_name` sin concordancia de alimentador y NetworkID no es
suficiente. Cero coincidencias produce `NO_ENCONTRADA`; más de una produce `AMBIGUA`.
Ambas situaciones bloquean ese alimentador.

## Arquitectura

### Dominio y lectura

`src/igea_dgs/loads.py` conserva las reglas de columnas y cálculo. Se amplía con la
acción `poner_cero`, la regla de cuatro ceros, la detección de fórmulas sin caché y la
comprobación de coherencia P/Q frente a kVA/FP.

`src/igea_dgs/load_batch.py` será responsable de:

- consolidar todas las hojas o grupos CSV;
- resolver el alimentador canónico;
- construir un `BulkLoadUpdatePlan` con planes por alimentador;
- calcular hashes de entrada, DGS y modelo;
- producir el resumen y la auditoría serializable.

El módulo no importa `powerfactory` ni modifica archivos DGS.

### Preflight y aplicación PowerFactory

`tools/apply_sed_loads.py` se dividirá internamente en cuatro fases observables:

1. `connect`: una sola conexión API para el lote.
2. `preflight`: activar el proyecto exacto, caso de estudio y escenario; localizar todas
   las cargas mediante identidad compuesta; capturar el estado anterior sin escribir.
3. `apply_and_verify`: escribir según `mode_inp` e `i_sym`, releer P, Q, FP y fases, y
   ejecutar `ComLdf`.
4. `rollback`: ante cualquier error o no convergencia, restaurar todas las cargas
   modificadas del alimentador, ejecutar de nuevo `ComLdf` y documentar el resultado.

No se escribe la primera carga de un alimentador hasta que su preflight completo tenga
cero faltantes y cero ambigüedades. Las tolerancias de relectura son
`1e-6 + 1e-4·abs(valor_esperado)` en MW/Mvar y `1e-6` para FP.

El resultado de un alimentador solo es `PASS` cuando:

```text
requested = matched = written = verified
not_found = 0
ambiguous = 0
write_errors = 0
verification_errors = 0
ComLdf.return_code = 0
IsLdfValid = true
```

Una no convergencia devuelve código distinto de cero. Un rollback fallido se eleva como
error crítico y nunca se presenta como una actualización exitosa.

### API y ejecución asíncrona

FastAPI incorpora operaciones masivas:

- `GET /api/workspaces/{wid}/load-template?feeder=...&format=xlsx|csv`
- `POST /api/workspaces/{wid}/load-batch-plan`
- `POST /api/workspaces/{wid}/load-batch-plans/{token}/dry-run`
- `POST /api/workspaces/{wid}/load-batch-plans/{token}/apply`

La lectura y conciliación se ejecutan como trabajo de CPU/IO fuera del hilo de solicitud.
El dry-run y la aplicación usan la lane exclusiva `powerfactory`, de modo que nunca hay
dos procesos modificando simultáneamente el mismo estado de PowerFactory.

El token del plan referencia un JSON inmutable con hashes, revisión, alimentadores,
valores anteriores esperados y cambios solicitados. Un cambio de entradas, DGS,
proyecto o revisión invalida el token.

### Interfaz React

La pestaña `Cargas de SED` permitirá:

- seleccionar uno, varios o todos los alimentadores;
- descargar una plantilla consolidada;
- subir CSV/XLSX mediante arrastrar y soltar;
- ver resultados agrupados por alimentador y estado;
- filtrar diferencias, errores, desconocidas y filas sin datos;
- ejecutar `Simular en DigSILENT` antes de habilitar `Aplicar`;
- seguir el progreso por alimentador;
- descargar auditoría CSV/JSON y el informe de convergencia.

La tabla no se limita a 500 filas. La API pagina el detalle mientras el resumen conserva
los totales completos.

## Auditoría y artefactos

Cada lote crea un directorio propio, sin sobrescribir ejecuciones anteriores:

```text
output/load_updates/<timestamp>_<batch_id>/
  input_manifest.json
  plan.json
  preview.csv
  result.json
  result.csv
  rollback.json
  logs.jsonl
```

Por fila se conservan: alimentador, NetworkID, SED, proyecto, terminal, P/Q/FP anterior,
P/Q/FP solicitado, P/Q/FP verificado, acción, estado, motivo y marcas de tiempo. El
manifiesto registra SHA-256 del archivo cargado, DGS y metadatos usados.

## Manejo de errores

- Una fila sintácticamente inválida bloquea su alimentador antes de PowerFactory.
- Un alimentador ausente o una hoja repetida bloquea ese alimentador.
- Una SED desconocida nunca se crea desde este módulo.
- Un plan vencido o con hashes distintos debe regenerarse.
- La desconexión de PowerFactory no se reintenta después de iniciar escrituras; se
  intenta rollback y se informa el estado real conocido.
- Cancelar antes de escribir termina limpiamente. Cancelar durante un alimentador
  solicita rollback antes de finalizar el trabajo.
- La aplicación continúa con el siguiente alimentador solamente después de confirmar
  `PASS` o rollback satisfactorio del actual.

## Estrategia de pruebas

### Unitarias

- Regla de cuatro ceros y `poner_cero`.
- Prioridad y coherencia de P/Q frente a kVA/FP.
- CSV multialimentador y Excel multihoja.
- Duplicados dentro y entre hojas.
- Fórmulas sin valor calculado.
- Alimentador, NetworkID o SED desconocidos.
- Serialización determinista y hashes.

### API y React

- Plantilla consolidada de selección múltiple.
- Plan paginado con totales completos.
- Token invalidado por cambio de entrada o DGS.
- Dry-run obligatorio antes de aplicar.
- Progreso, cancelación, errores y descarga de auditoría.

### PowerFactory simulado

- Coincidencia inequívoca por identidad compuesta.
- Modos PC, PQ, SC, SP y QC.
- Cargas equilibradas y desequilibradas.
- Fallo antes de escribir, fallo intermedio, no convergencia y rollback.
- El proceso devuelve error si el flujo no converge o el rollback no puede verificarse.

### Aceptación real

1. Importar AL209 desde `260924.mdb` mediante el conversor actual.
2. Generar y simular un lote con cargas de AL209.
3. Aplicar cambios controlados, verificar valores y `ComLdf`, y restaurar los originales.
4. Repetir el ciclo para IN111 desde los TXT `260927_Carga`, `260927_Red` y
   `260927_Equipo`.
5. Ejecutar un lote combinado AL209 + IN111 en una sola sesión de PowerFactory.
6. Conservar informes antes/después y demostrar que una prueba deliberadamente fallida
   restaura el alimentador.

Las pruebas reales deben utilizar copias o proyectos dedicados del conversor. Nunca se
modifica el archivo MDB/TXT de origen ni un proyecto operativo ajeno.

## Criterios de aceptación

- El mismo lote CSV/XLSX produce el mismo plan y hashes.
- Todos los alimentadores y filas aparecen en el resumen; ninguno se ignora en silencio.
- Las filas con kW=kvar=kVA=FP=0 permanecen sin cambios salvo `poner_cero`.
- No existe escritura parcial dentro de un alimentador.
- Toda carga aplicada conserva la relación correcta Alimentador–NetworkID–SED.
- El dry-run tiene cero faltantes y cero ambiguos antes de habilitar la aplicación.
- Cada alimentador aplicado converge o queda restaurado y marcado como fallido.
- La interfaz permanece responsiva y muestra avance y resultado por alimentador.
- AL209 MDB e IN111 TXT completan la aceptación real con evidencia JSON/CSV.

## Fuera de alcance

- Crear nuevas SED o modificar la topología.
- Reconfigurar interruptores para forzar convergencia.
- Corregir automáticamente códigos de SED parecidos.
- Cambiar parámetros de transformadores, líneas o catálogos.
- Ejecutar escrituras PowerFactory concurrentes.

## Fundamentación

- DIgSILENT describe la necesidad de construir una topología conectada y asociar datos
  de carga/generación para ejecutar estudios de flujo:
  <https://www.digsilent.de/index.php/en/paper-reader-pf-en/gis-integration.html?_cmsscb=1&cid=17686&file=files%2Fcontent%2FWhitepaper%2FPF%2FPF_Paper_GIS-Integration.pdf>
- Una tesis de maestría sobre intercambio y validación de modelos en PowerFactory señala
  que el flujo requiere conocer la topología y las condiciones iniciales:
  <https://kth.diva-portal.org/smash/get/diva2%3A1046364/FULLTEXT01.pdf>
- La tesis doctoral de Kennedy O. Oyoo desarrolla validación basada en reglas para datos
  heterogéneos de activos del sector eléctrico:
  <https://research.ualr.edu/etd/1096/>
- Bai et al. muestran que cuantificar y validar las cargas individuales de subestaciones
  es un requisito central para validar modelos de redes con cargas inciertas:
  <https://doi.org/10.1049/iet-gtd.2015.0734>
- La revisión de Dalavi, Golshan y Hatziargyriou trata la calidad de datos y la
  identificación topológica como condiciones críticas de los modelos de distribución:
  <https://doi.org/10.1016/j.epsr.2024.110538>

La decisión de usar preflight, identidad compuesta, auditoría y rollback es una
inferencia de ingeniería aplicada a esas exigencias de calidad y validación; no se
atribuye literalmente a una sola fuente.
