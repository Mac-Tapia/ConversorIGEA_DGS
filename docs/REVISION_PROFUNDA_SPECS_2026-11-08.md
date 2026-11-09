# Revisión de las 99 SPEC y faltantes para terminar — 8 de noviembre de 2026

**El proyecto no tiene acreditado su cierre integral.** Hay implementación y verificaciones relevantes en ramas que todavía no están integradas en `main`. El total de casillas abiertas no mide ese avance. Esta revisión conserva esas diferencias y no cambia casillas ni estados de otras sesiones.

Responsable: Codex `/root`, tarea `REVISION-SPECS-20261108-56172510`. Se aplicaron constitución, protocolo global de coordinación, skill del proyecto `convertersmartgrid-spec` y verificación antes de declarar resultados. La instrucción posterior del usuario de comunicar cierres está registrada en [Conciliación de tareas](CONCILIACION_TAREAS_2026-11-08.md) y en `ACTIVE.md`. El integrador comercial confirmó lectura/aceptación y asignó P22 a conciliar cierres, P21 a HARNESS y P19 a la corrección de procedencia. Falta comprobar los cambios de estado que resulten; el acuse no equivale a tareas cerradas.

## Corte, alcance y límites

| Superficie | Revisión observada | Resultado de la inspección |
| --- | --- | --- |
| `main` | `5617251012f39193297e19b299d8a179a8fe1f61` | 99 SPEC, 3.219 RF, 1.093 tareas, 115 abiertas. Diff preexistente de `web/services.py`: 9 adiciones/1 borrado. |
| Cierre comercial | `09f6f3f3686819c230dbec0816d56b5f7ad75df2` | 99 SPEC, 3.226 RF, 114 abiertas; fuente separada, sin integrar por esta revisión. |
| HARNESS | `3de431093981ba850e29fb840a5e90085adaa503` | Entrega/HANDOFF disponibles; fuente `9e609f2c`, ocho módulos propuestos. Integración y campañas reales pendientes. |

Se recorrieron todos los `spec.md`, `plan.md` y `tasks.md` existentes, sus RF/tareas y referencias formales en código/pruebas, y se generó una fila por requisito. La inspección semántica y las reproducciones se concentraron en cierre, trazabilidad, arquitectura, aprendizaje, PIDE, aceptación nativa y regresiones observadas. **No se certificaron semánticamente los 3.219 RF ni se repitieron todos sus ensayos reales.** Las filas de las 99 SPEC distinguen el estado declarado de lo que esta revisión puede confirmar.

Las escrituras propias se limitan a estos informes, la entrada de coordinación y evidencia externa. No se modificaron implementación, estados de SPEC, instalaciones, modelos o datos de las distribuidoras. No se ejecutaron suite completa, GPU ni PowerFactory; se respetaron recursos y archivos del cierre comercial activo. Las pruebas de frontend construyen sus fixtures en temporales propios, sin publicar el frontend del operador.

Evidencia y reproductores: [directorio externo](D:/converter/auditorias/revision_specs_20261108_56172510_root). El detalle reproducible está en `inventario_main.json`, `inventario_rama_comercial.json`, `detalle_por_spec.md`, `requisitos_auditados.csv`, `trazabilidad_con_ejecucion/trazabilidad.json`, logs, XML y probes. Se conserva el criterio original de las 115 tareas en `tareas_abiertas_main.md`.

## Por qué sigue apareciendo 115

`main` no incorporó el trabajo comercial. En su rama el balance es **115 − 2 cierres + 1 alta = 114**: cerraron `016:T18` y `081:T20`; se añadió `065:T17`. La aritmética se comprobó leyendo ambas versiones de todas las tareas.

Además, tareas grandes acumulan implementación, datos, ejecución, reapertura y aceptación bajo una sola casilla. Por ejemplo, la rama ya documenta la migración VNR y frontend, la conexión de productores y consumidores del conjunto, recuperación de trabajos y ensayos de instalación. Las casillas siguen abiertas por sus residuos concretos. Presentarlas como si todo siguiera sin empezar sería incorrecto. Tampoco corresponde marcarlas completas por avances que cubren solo parte de su criterio.

Se indicó al integrador que concilie cada tarea, cierre las verificadas sin esperar a terminar el proyecto completo y devuelva por separado altas, cierres, avances parciales, bloqueos y diferidas. El registro comercial consigna `012:T13` y `049:T4` como diferidas por decisiones previas del usuario; siguen siendo distintas de cumplidas. No se convierte la muestra de una empresa en un requisito comercial universal: se releyó `alcance_universal_usuario_20261108.json`.

## Hallazgos que condicionan el cierre

### H01 — La procedencia de la captura se reescribe al recalcular evidencia nativa

Prioridad alta. Afecta a 065/086 y a la confianza en recibos de 044/045/048/049. En `tools/aceptacion_nativa.py`, `main()` asigna `commit`, `escrito` y `sha256` también para el subcomando `veredictos`; no comprueba las huellas anteriores antes de sustituirlas. `tests/apoyo.py::evidencia_nativa` comprueba esquema y archivos, pero no vincula el commit de captura con el candidato que ejecuta pytest.

**Reproducción nueva en main y rama comercial:** un directorio sintético externo contiene un manifiesto con revisión original y un testigo con SHA; se modifica el testigo y se ejecuta únicamente `veredictos`. Retorna 0, registra el SHA nuevo y reemplaza la revisión original por el HEAD actual. No hubo etapa nativa, PowerFactory ni manipulación de evidencia real. Esto demuestra pérdida de procedencia al recalcular; **no demuestra que una aceptación nativa completa pueda aprobarse con ese fixture**.

Evidencia: `probe_procedencia.py`, `procedencia_probe.json`, `procedencia_probe_branch.json`. Cierre pendiente: distinguir captura original y reevaluación, conservar sus identidades y detectar cambios antes de acreditar una captura sobre el candidato final. El integrador acusó lectura y asignó su corrección a P19; corrección/verificación todavía pendientes de entrega al corte de esta revisión.

### H02 — No hay una suite completa aprobada del candidato final

Prioridad alta, 025:T22, 058:T5, 065:T13/T17 y 086:T31. Se releyó el registro externo de G2 sobre `c6ec7fb8`: **8.209 pass, 36 fail, 9 skip, 0 error**, `state=rechazado`, fuentes y datos estables durante esa corrida. Existen correctivos posteriores y corridas enfocadas; no se trasladan sus resultados al candidato combinado por suma.

El registro actual de la rama mantiene `production_ready_core=false` y `project_complete=false`. Nueva validación completa y nativa del corte combinado continúa pendiente. El rechazo histórico no prueba que todos esos defectos persistan tras sus correctivos; impide afirmar un pase final sin volver a comprobar la combinación.

### H03 — La huella de main no cubre toda la entrega ni el ámbito ML

Prioridad alta, 065:RF-20/24 y 086. En `tools/trazabilidad_candidato.py` faltan locks/manifiestos opcionales, instalador, licencias entregadas y `tests_ml`. Se cambiaron ocho entradas en un sandbox externo: **ocho cambios no alteran la huella de main**. Con la función de la rama comercial, **los mismos ocho cambios sí alteran la huella**. La corrección existe fuera de main; no procede implementarla otra vez.

Además, `pyproject.toml` declara `testpaths=["tests"]` y el runner de main selecciona `tests`. La opción `--suite-completa` rechaza omisiones de ese ámbito; no ejecuta por ello `tests_ml`, npm, instalación ni aceptación física. La rama comercial ya contiene `tools/verificar_entrega_integral.py`; falta aceptación final de su combinación. Evidencia: `hash_probe_main.json`, `hash_probe_rama_comercial.json` y fuentes de ambos runners.

### H04 — El entorno de main está por debajo de su propia política de seguridad

Prioridad alta, 065:T7/T16 y 086. Lectura actual de metadata instalada y constraints: Pillow `12.3.0`, pypdf `6.21.2`, certifi `2026.7.22`; `config/entrega.json` exige `13.0.0`, `6.21.4` y `2026.10.18`. `pip check` retorna 0 y no detecta este desacuerdo: valida dependencias, no la política ni vulnerabilidades.

La rama comercial documenta entorno candidato y corrección de locks. Falta incorporar/verificar el entorno que realmente se entregue. No se atribuyen CVE actuales sin una nueva consulta de avisos: el hallazgo comprobado es la incompatibilidad con la política interna, no un escaneo de seguridad nuevo.

### H05 — Arquitectura pendiente aunque las guardas de deuda pasen

Prioridad de cierre integral, SPEC 002. Main conserva **37 excepciones** en `deuda_arquitectura.json`; la rama comercial, **34**. `test_capas.py` verifica que la deuda declarada no derive. T7 exige terminar sin excepciones de capa: pasar la guarda con deuda no satisface ese criterio.

VNR y frontend fueron trasladados en la rama comercial; T8 espera regresión real y T11 revisión visual según sus aclaraciones. T9 conserva compatibilidades pendientes; T12 exige referencias y línea base. El HANDOFF HARNESS pide además clasificar ocho módulos al integrarlo. No se cierra toda la 002 por haber completado una parte de las carpetas.

### H06 — Brechas distintas de trazabilidad

Main tiene **23 RF sin cita en pruebas**: 002 (6), 027 (8), 058 (1), 074 (1), 086 (4), 097 (3). Los identificadores exactos están debajo. Esto no demuestra que todo ese código falte: algunos comportamientos aparecen bajo otras SPEC y necesitan atribución semántica correcta.

La matriz estricta distingue además **72 RF sin función de prueba con aserción atribuida**: incluye esos 23 y otros 49 con citas en docstrings de módulo/comentarios o pruebas de frontend que requieren localizar su aserción. Ejemplo: 034 tiene 31 referencias a nivel de fichero, sin atribución de función en ese lector. No se presenta este número como 72 funciones inexistentes. Hay **640 RF sin vínculo explícito de implementación** en el índice formal, otra brecha de atribución, no prueba de inexistencia de 640 implementaciones.

`estado_specs --comprobar` y la matriz formal pasan porque sus contratos verifican estructura y citas válidas. El resultado de una función, la cobertura semántica del RF y la aceptación de ingeniería necesitan evidencia adicional.

### H07 — Aprendizaje e inferencia no tienen un cierre científico conjunto acreditado

043:T9, 045:T3, 047:T4/T7/T8, 050:T1b–T5b, 069:T7, 070:T11, 074:T5/T7/T8, 089:T5/T7 y 097:T3 conservan obligaciones reales. La rama 050 tiene conexión de productores/cola/estado/consumidores y negativas verificadas: faltantes antiguos de main sobre conexión ya no describen bien esa rama. Aún no hay evidencia del ciclo auténtico completo con evaluación conjunta, retención, publicación y reversión del conjunto.

La 046 documenta una corrida CUDA corta real del 2 de noviembre: los neuronales fueron rechazados y ganó la referencia en los diez objetivos. **Existe ejecución histórica; no hay por ello un ganador neuronal aceptado para el PIDE anual.** La 085 permite uso provisional explícito de un candidato rechazado: provisional no cambia a PROMOVIDO. Las SPEC de mecanismos cerradas no certifican automáticamente la precisión de los modelos actuales.

HARNESS tiene entrega disponible y pruebas de contrato; todavía requiere integración en consumidores/jobs y campañas reales. No equivale a mejora demostrada de precisión/recall. Tras acusar la orden de conciliación, el integrador comunicó una reproducción adicional sobre `3de43109`: referencia evaluada y activo esperado pueden tener digests distintos antes de promover. Asignó el correctivo de `integracion.py` y su prueba a P21, sin modificar la fuente del owner. Es evidencia de la revisión cruzada comunicada por el integrador; esta auditoría no repitió esa nueva reproducción. Su corrección y revisión quedan pendientes de entrega. No se pidió entrenar de nuevo en esta auditoría.

### H08 — Pronóstico → ganador → predicción → PIDE anual sigue sin acreditarse

072:T14 y 089:T5/T7. Main aún describe T14 como pendiente de su RF; la rama comercial ya añade seis RF y consumidor anual con contratos. Se releyó la inspección externa de registros canónicos: no acredita ganador Forecast aceptado ni predicción anual aplicada. Los PIDE históricos encontrados se hicieron por CAGR. Su alcance es de las raíces consultadas; no demuestra inexistencia global de todo artefacto en el equipo.

El cierre exige vincular proyección, datos, fechas, magnitud/horizonte, ganador/decisión y aplicación año a año desde las obras anteriores. El libro oficial y una obra real valorada de 072:T13, revisión humana del corpus de T9b y aceptación de entregables de T11 siguen pendientes. La consulta web de Osinergmin identificó la resolución 181-2026 que modifica la 152; no acreditó la descarga y huella de la base revisada. No se repite como hecho actual la antigua afirmación de que no está publicada.

### H09 — La convergencia y persistencia medidas no cierran el diseño eléctrico

004:T20 exige transformadores de cargas nuevas ≤80 %; 042/052/073/084/087/094/098/099 requieren ensayos concretos por web y relectura. La 048:T4 documenta persistencia y al mismo tiempo `converged_with_violations`; la tarea permanece correctamente abierta. En la evidencia histórica de 044 se rechazó un contraste por dominio equilibrado/desequilibrado: una prueba que confirma ese rechazo puede pasar sin aceptar la obra.

Se releyó `p05_aceptacion_nativa_rc6_20261108/NO_USAR_PARA_ACEPTACION.json`: ensayo descartado por parámetros sin respaldo y barra ajena al alcance; no cierra 044/045/048. Pendiente un diseño respaldado, fuente/caso/perfil exactos, cargas servidas, conservación antes/después y umbrales del perfil tras reabrir. Las 78 tareas marcadas `[DIgSILENT]` incluyen navegador, renombrado y hasta entrenamiento: **no son 78 flujos eléctricos independientes**.

### H10 — Instalación final y operación siguen pendientes en el alcance exigido

086:T9/T24–T34/T36/T40/T41 y 096:T3. Hay ensayos previos de instalación, actualización, rollback y datos conservados en la rama comercial; no se niega ese avance. Falta repetir lo exigido sobre el artefacto final, con Python entregado, uso nativo auténtico y complemento correspondiente. No se reutiliza una aceptación de paquete previo para uno reconstruido después.

Persisten comprobación visual, red realmente desconectada, interrupción/suspensión física según sus tareas, aceptación por un tercero, e integración final. No se renombra la raíz con sesiones activas. Publicación 086:T34 conserva la orden expresa del usuario como criterio final; no es una tarea que pueda cumplirse por más pruebas.

### H11 — Regresiones actuales y documentos de cierre desfasados

Se ejecutó `npm test` correctamente: **42 aprobadas, 1 fallida, 0 omitidas**. La expectativa de `042:RF-77` aún espera `temporal`, mientras el código devuelve `temporal, no llega al horizonte más corto`, coherente con la ampliación 098. Es una discrepancia contrato/prueba comprobada; no se prescribe volver al texto antiguo. La rama comercial ya actualizó su prueba.

La batería de estructura produjo **60 aprobadas, 1 fallida**: catálogo 090 esperaba 12.437 líneas de services y el árbol modificado tiene 12.445. El diff de services era preexistente; no se atribuye su autoría a esta revisión ni se sobrescribe. Tipos y contrato API pasaron.

`README.md` aún remite el instalador a T37 y dice que SQL/Access no aplica, pese a los contratos MDB/VNR. La finalización de 098 todavía menciona RF-1 a RF-45, aunque define hasta RF-49. El registro de HARNESS del cierre sigue esperando entrega y conserva cifras provisionales superadas por su HANDOFF. Son desajustes que dificultan ver el progreso y el cierre real.

## Resultado de las verificaciones nuevas

| Comprobación | Resultado | Límite |
| --- | --- | --- |
| `tools/estado_specs.py --comprobar` | exit 0 | Tabla canónica al día en main. |
| `tools/trazabilidad_candidato.py --comprobar` | 3.219 RF, 0 errores | Referencias formales válidas; semántica pendiente. |
| Pytest: trazabilidad de SPEC, capas y arquitectura generada | 60 pass, 1 fail | Falla deriva del catálogo descrita en H11. |
| `npm test` | 42 pass, 1 fail, 0 skip | Discrepancia de alcance temporal H11. |
| TypeScript `--noEmit --incremental false` | exit 0 | No es prueba visual ni de runtime. |
| `tools/generar_contrato_api.py --check` | exit 0 | Contrato API sin deriva. |
| `pip check` | exit 0 | No comprueba mínimos internos ni CVE. |
| Ocho mutaciones de huella en sandbox | main omite 8/8; rama detecta 8/8 | No se tocaron archivos reales. |
| Recalcular procedencia sintética | pérdida de revisión y regeneración de SHA en ambas ramas | No hubo etapa nativa ni aceptación de dominio. |

Cada corrida guardó comando, código de salida, tiempo, log y huella canónica antes/después. Durante esas corridas el hash fue `8112e8ba328761543cb92d23fe515aac35ed2c01ab8619f9c7c4bc8523dd345a`, estable. Las notas de coordinación escritas después cambian metadata incluida por ese selector: los resultados corresponden al corte registrado, no se convierten en freeze de liberación. H03 documenta las limitaciones del propio selector de main.

La primera invocación directa con `node --test` no suministró `npm_execpath` y falló fixtures que exigen npm. Se conservó como ensayo descartado; el resultado de frontend informado arriba procede de la ejecución posterior correcta `npm test`. Un error de impresión CP1252 del wrapper externo se corrigió sin tocar producto; los logs originales quedaron conservados.

## Condiciones concretas para terminar

| Prioridad / responsable | Falta demostrable | Criterio de salida |
| --- | --- | --- |
| Integrador y dueños de tareas | Conciliar avances y entrega HARNESS, revisar integración y procedencia H01 | Casillas cumplidas actualizadas con evidencia; residuos explícitos; corte único identificado. |
| Integrador / entorno | Adoptar correcciones ya existentes de huella, entorno, frontend y validación integral | Artefactos, dependencias y ámbitos obligatorios ligados al mismo candidato. |
| Responsable PowerFactory / ingeniería | Ensayos nativos por obligación, fuente y perfil, incluida obra eléctricamente admisible | Persistencia/reapertura/conservación y límites comprobados, sin usar recibos descartados. |
| Responsables de modelos y datos | Campañas 043/045/047/050/069/074/089/097 y cadena PIDE | Datasets/particiones/políticas sellados; evaluación y decisiones auténticas; modelos reales reabiertos; sin fuga ni extrapolar dominios. |
| Custodios / revisores humanos | Curvas y parámetros de protecciones si se incluye 049; corpus, costos oficiales, revisión de informes y tercero | Datos y decisiones humanas reales, o aplazamiento/alcance explícito. No sustituir por datos inventados. |
| Integrador comercial | Instalación final, operación, interrupciones y suite completa del corte final | Puertas aprobadas en su ámbito, sin omisiones obligatorias; artefacto e identidad coincidentes. |
| Dueño arquitectura | Terminar residuos de 002 | Criterios T7/T8/T9/T11/T12 cumplidos, sin confundir deuda permitida con migración completa. |
| Usuario e integrador | Publicación | Artefacto revisable listo y orden expresa para publicar. |

El cierre comercial del núcleo y el cierre de todos los módulos activos son alcances diferentes. Esta revisión no retira requisitos ni convierte una función pendiente en opcional. Las SPEC 003 retirada y 031 reservada se conservan con su motivo; no se cuentan como funcionalidad activa por completar.

## Fundamento académico consultado en la web

Las fuentes justifican el método, no certifican este repositorio ni fijan sus umbrales eléctricos:

- **Maestría, ingeniería de software:** Eriksson y Mosaddegh (2021), *Establishing Feedback in Continuous Delivery – Benefits and Approaches*, Lund. Distingue retroalimentación de proceso/producto y su comunicación entre equipos. Se consultó el resumen del [PDF institucional](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf). Aplicación: cierres y avances visibles por tarea, con evidencia de integración.
- **Maestría, modelos eléctricos:** Thorslund (2017), *Swedish Transmission Grid Model Based on Open Sources*, Chalmers. Contrasta un modelo de red con datos históricos; respalda comparar salidas con mediciones y declarar desviaciones. [Ficha institucional](https://odr.chalmers.se/items/e4ffcee9-9884-4a76-9f3f-af658429825c). Se consultaron metadatos/resumen, no todo el PDF.
- **Doctorado:** Viggiano (2023), *Data driven modelling of distribution system considering a high penetration of renewable energy sources for control applications*, Sheffield. Examina límites de datos, regresores, validación temporal e intervalos de predicción. [Repositorio institucional](https://etheses.whiterose.ac.uk/id/eprint/33810/). Aplicación: dominio/escenarios de los modelos, particiones, incertidumbre y límites del pronóstico. Se consultaron metadatos y resumen.
- **Artículo indexado:** Shahin, Ali Babar y Zhu (2017), *Continuous Integration, Delivery and Deployment: A Systematic Review on Approaches, Tools, Challenges and Practices*, IEEE Access 5, 3909–3943, DOI [10.1109/ACCESS.2017.2685629](https://doi.org/10.1109/ACCESS.2017.2685629). La [ficha institucional](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/) confirma revisión por pares y enlaces a Scopus. Aplicación: visibilidad de resultados y confiabilidad de integración/entrega; una prueba local no acredita el despliegue completo.
- **Artículo indexado de dominio:** Barzegkar-Ntovom et al. (2026), *Power Hardware-in-the-Loop validation of digital twin-enabled dynamic analysis and assessment of distribution networks*, Electric Power Systems Research 260, 113311, DOI [10.1016/j.epsr.2026.113311](https://doi.org/10.1016/j.epsr.2026.113311). La [ficha institucional](https://pureportal.strath.ac.uk/en/publications/power-hardware-in-the-loop-validation-of-digital-twin-enabled-dyn/) identifica revisión por pares y Scopus. Aplicación: separar modelo implementado de validación de su representación física. No se exige hardware-in-the-loop como requisito nuevo de este proyecto.

Consulta: 8 de noviembre de 2026. La [fuente oficial de Osinergmin](https://www.osinergmin.gob.pe/seccion/institucional/regulacion-tarifaria/informacion-tecnica/modulos-estandares) se usó solo para refrescar la referencia de 072:T13; no como evidencia de una base descargada/aceptada. Los umbrales concretos proceden de las SPEC y del perfil del caso.

## Matriz por SPEC

La tabla siguiente se genera de todas las SPEC y de las dos versiones de tareas leídas. **Cumplida es el estado declarado**: cuando no hay tarea abierta no se inventa otra, ni se concede una recertificación nativa/científica en esta revisión. El detalle externo añade archivos de implementación, ficheros/funciones de prueba, RF, criterios y referencias de evidencia.

<!-- GENERATED_SPEC_MATRIX -->

| SPEC | Estado main | RF / citados | Tareas abiertas main → rama comercial | Qué falta o límite de cierre |
| --- | --- | --- | --- | --- |
| [001](../specs/001-reorganizacion/spec.md) Reorganización: una responsabilidad, un sitio | cumplida | 35 / 35 | — | Sin casillas abiertas; conservar determinismo y línea base al integrar la migración 002. |
| [002](../specs/002-arquitectura-por-capas/spec.md) Arquitectura por capas y módulos enchufables | aprobada | 37 / 31 | T7, T8, T9, T11, T12 | Migración parcial: 37 deudas en main/34 en rama; T8/T11 implementadas en rama con residuos de regresión/visual. T7/T9/T12 siguen pendientes. |
| [003](../specs/003-integracion-web-retiro-gui/spec.md) Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`) | retirada | 0 / 0 | — | Retirada con motivo; conservar historia y datos privados. No es una función activa por terminar. |
| [004](../specs/004-cargas-en-powerfactory/spec.md) Cargas en un proyecto existente de DIgSILENT | implementada | 70 / 70 | T20 | Aplicación real de PE102: transformadores de CH_13/CH_22 con ficha y carga máxima ≤80 % en Con proyecto. |
| [005](../specs/005-carpeta-de-proyectos-pf/spec.md) Carpeta de proyectos importados en DIgSILENT | cumplida | 22 / 22 | — | Sin casillas abiertas en main. Rama añade RF-23 de identidad/carpeta; revisar ese delta al integrar, sin mover proyectos ajenos. |
| [006](../specs/006-ajuste-a-la-maxima-de-cabecera/spec.md) Ajuste de las demandas a la máxima de cabecera | cumplida | 44 / 44 | — | Sin casillas abiertas; el ajuste de cabecera sigue necesitando correspondencia temporal y de población en las campañas finales. |
| [007](../specs/007-cargas-nuevas-sobre-el-ajuste/spec.md) Cargas nuevas sobre el alimentador ajustado, una variación por carga | cumplida | 41 / 41 | — | Sin casillas abiertas; preservar variación por carga y Caso base al repetir pruebas finales. |
| [008](../specs/008-pestana-cargas-en-tres-pasos/spec.md) Pestaña «Cargas en DIgSILENT» en tres pasos | implementada | 28 / 28 | T7 | Aceptar los tres pasos de la web sobre un proyecto real de dos alimentadores. |
| [009](../specs/009-inventario-del-repositorio/spec.md) Inventario del repositorio: cada fichero con su módulo y su spec | cumplida | 15 / 15 | — | Sin casillas abiertas; incorporar nuevos módulos y rutas del corte combinado al inventario. |
| [010](../specs/010-trazado-gps-de-las-lineas/spec.md) Trazado GPS de las líneas | cumplida | 7 / 7 | — | Sin casillas abiertas; conservar procedencia CRS y distinguir coordenadas inferidas de originales. |
| [011](../specs/011-estudios-sobre-la-red-calibrada/spec.md) Estudios y obras de mejora sobre la red calibrada | implementada | 130 / 130 | T19 | Tres casos y obras de cada clase, con Sin proyecto intacto; migración de tensión con tipos compartidos y lectura real. |
| [012](../specs/012-confiabilidad-y-capacidad-de-la-red/spec.md) Confiabilidad y capacidad de la red calibrada | implementada | 72 / 72 | T13 | Índices/ENS, reconectador, banco, capacidad y PV con libro real. Comercial registra T13 diferida; no cumplida. |
| [013](../specs/013-mes-de-analisis-y-transferencia/spec.md) Mes de análisis y transferencia entre dos alimentadores | implementada | 32 / 32 | T7 | Transferencia real CA101/PE104 en instante común y descargable releído, con confirmación del operador. |
| [014](../specs/014-calibracion-en-sin-proyecto/spec.md) Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto» | cumplida | 34 / 34 | — | Sin casillas abiertas; conservación de los casos es dependencia de aceptación para 098 y obras. |
| [015](../specs/015-caso-base-verificado/spec.md) «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas | cumplida | 69 / 69 | — | Sin casillas abiertas; verificar identidad/fuente y huella real del Caso base en cada nueva campaña. |
| [016](../specs/016-troncal-y-enlace-entre-alimentadores/spec.md) Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo | implementada | 89 / 89 | T18 → — | T18: PN107, nodo y cable según distancia. Rama comercial la cerró con evidencia; falta trasladar el cierre a main mediante integración. |
| [017](../specs/017-informes-de-estudio-y-factibilidad/spec.md) Informes de estudio eléctrico y de factibilidad de suministro | implementada | 145 / 145 | T13, T14, T19 | T13/T14/T19: informes reales y dos alternativas medidas; aprobación del usuario de los DOCX todavía requerida. |
| [018](../specs/018-vinculo-compartido-entre-espacios/spec.md) Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo | cumplida | 15 / 15 | — | Sin casillas abiertas; vínculo compartido debe preservar identidad al instalar, renombrar y reabrir. |
| [019](../specs/019-arnes-de-powerfactory/spec.md) Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables | cumplida | 28 / 28 | — | Sin casillas abiertas; acceso nativo único/exclusivo sigue siendo condición de todas las campañas reales. |
| [020](../specs/020-sed-sobrecargadas/spec.md) SED fijas sobrecargadas: aviso y transformadores nuevos desde la web | cumplida | 35 / 35 | — | Sin casillas abiertas; no confundir normalización de tamaño con aceptación de carga ≤80 % de 004. |
| [021](../specs/021-maniobras-y-sed-en-el-diagrama/spec.md) Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración | cumplida | 70 / 70 | — | Sin casillas abiertas; maniobras, fases y central existentes deben conservarse en el contraste nativo. |
| [022](../specs/022-red-unida-por-zonal-y-set/spec.md) Red unida por zonal y SET | cumplida | 95 / 95 | — | Sin casillas abiertas; validar unión y poblaciones de alimentación en cada fuente/perfil de la entrega. |
| [023](../specs/023-vnrgis-copia-sql-server/spec.md) VNR-GIS desde la copia de SQL Server de cualquier concesionaria | cumplida | 10 / 10 | — | Sin casillas abiertas; la aceptación final VNR no se infiere de existencia de lector o SQL restaurado. |
| [024](../specs/024-pinn-gemelo-digital/spec.md) PINN como oráculo y gemelo digital de la red calibrada | cumplida | 80 / 80 | — | Sin casillas abiertas; físicas y modelos históricos no acreditan generalización o un modelo actual promovido. |
| [025](../specs/025-calibracion-por-anio/spec.md) Calibración por año de medición | aprobada | 85 / 85 | T21, T22 | PA217/TM105 reales y suite final sin omitidas; citas de RF-44 a RF-60 no sustituyen la corrida con datos. |
| [026](../specs/026-asistente-ordenes/spec.md) Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor | implementada | 32 / 32 | T12 | Órdenes reales por consola para todas las tareas nativas y recorrido hasta informes/PIDE con confirmaciones. |
| [027](../specs/027-cierre-agente-en-produccion/spec.md) Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación | aprobada | 69 / 61 | T11, T22, T14, T26, T29, T30, T31 | Siete casillas: ajuste condicionado, Codex como maestro por CLI, PIDE real, cuatro sistemas, LHS/top-k y episodios 30/10/10. Ocho RF sin cita. |
| [028](../specs/028-escaneo-del-alimentador/spec.md) Escaneo del alimentador antes de recalibrar | implementada | 42 / 42 | T6, T11 | Central térmica real de NA205 y recorrido web individual/unido con recalibración e informe; no inventar generador. |
| [029](../specs/029-crecimiento-por-alimentador/spec.md) Crecimiento de la demanda por alimentador desde la medición de cabecera | cumplida | 7 / 7 | — | Sin casillas abiertas; crecimiento real por alimentador no equivale a pronóstico multihorizonte neuronal. |
| [030](../specs/030-pide-por-anios-en-digsilent/spec.md) Los años del PIDE en casos y escenarios de DIgSILENT | cumplida | 15 / 15 | — | Sin casillas abiertas; PIDE histórico por tasa no cierra el consumidor anual de 072/089. |
| [031](../specs/031-proyeccion-econometrica-de-la-demanda/spec.md) Proyección econométrica de la demanda con variables exógenas | reservada | 0 / 0 | — | Reservada con motivo; no tratarla como algoritmo econométrico implementado ni como tarea activa pendiente. |
| [032](../specs/032-caso-base-original-fichas-en-sin-proyecto/spec.md) «Caso base» con los datos originales; fichas y potencias en «Sin proyecto» | cumplida | 29 / 29 | — | Sin casillas abiertas; conservar datos originales y escenarios separados durante relectura/instalación. |
| [033](../specs/033-trazabilidad-y-estado-de-las-specs/spec.md) Trazabilidad y estado de las specs | cumplida | 22 / 22 | — | Guardas documentales pasan; mejorar atribución por función/ejecución sin confundir citas a nivel de archivo con validación semántica. |
| [034](../specs/034-motor-base-y-contrato-de-fuentes/spec.md) Motor base de conversión y contrato universal de fuentes | cumplida | 33 / 33 | — | Sin casillas abiertas; 31 RF solo tienen atribución formal de fichero/comentario en la matriz estricta, pendiente localizar aserciones concretas. |
| [035](../specs/035-fijas-de-la-tabla-q-con-bancos-y-unidades/spec.md) Fijas de la tabla en el instante de la máxima, Q de cabecera con bancos y unidades de DIgSILENT | cumplida | 31 / 31 | — | Sin casillas abiertas; instante, signo Q, bancos y unidades deben coincidir en evidencia nativa de cada calibración. |
| [036](../specs/036-auditoria-raiz-y-arranque-fiable/spec.md) Auditoría de raíz y correcciones del arranque | cumplida | 3 / 3 | — | Sin casillas abiertas; arranque de desarrollo no acredita instalación limpia del candidato final. |
| [037](../specs/037-cargas-nuevas-en-estudios-web/spec.md) Caso «Cargas nuevas» en los estudios de la web | implementada | 8 / 8 | T4 | Tres casos/año, escenarios y cargas activas/exclusiones en trabajo web y relectura nativa. |
| [038](../specs/038-pertenencia-de-sed-y-notas-en-web/spec.md) Pertenencia de las SED en la fuente y notas de actualización | cumplida | 8 / 8 | — | Sin casillas abiertas; pertenencia de SED debe conservarse al importar nuevas fuentes/perfiles. |
| [039](../specs/039-fijas-maximo-del-mes-o-coincidentes/spec.md) Fijas del máximo del mes o coincidentes con la cabecera, elegidas y comparadas en la web | implementada | 22 / 22 | T8, T4 | Recalibración con fija a su máxima y comparación real de los dos criterios con NA203; tabla comprobada en navegador. |
| [040](../specs/040-cargas-del-bloque-sin-duplicados-y-ampliaciones/spec.md) Cargas del bloque sin duplicados, y ampliaciones de clientes existentes | cumplida | 12 / 12 | — | Sin casillas abiertas; 099 amplía identidad/deduplicación y mantiene aceptación real independiente. |
| [041](../specs/041-reparto-probabilistico-de-las-escaladas/spec.md) Reparto probabilístico de las SED escaladas | cumplida | 9 / 9 | — | Sin casillas abiertas; conservar incertidumbre/procedencia, sin presentar muestras probabilísticas como medida nativa. |
| [042](../specs/042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md) «Con proyecto»: escalera de obras carga a carga y SET nueva para las que no caben | implementada | 106 / 106 | T29, T42, T50, T48, T44, T37, T6 | Siete casillas nativas: otra empresa, elevador, alcance/tabla Pisco, déficit previo, migración 22,9 kV y SET Copara admisible. Regresión de texto reproducida. |
| [043](../specs/043-consolidacion-y-gobierno-de-modelos/spec.md) Consolidación y gobierno de modelos | aprobada | 15 / 15 | T9 | Reapertura CUDA de familias reales y campaña de siete familias con informe verify --fail-on-incomplete; contratos no cierran T9. |
| [044](../specs/044-evaluacion-causal-y-verificacion-completa/spec.md) Evaluación causal y verificación completa | cumplida | 9 / 9 | — | Cerrada documentalmente por contratos y rechazo nativo correcto; no significa obra aceptada. Revisar procedencia H01 y el dominio equilibrado/desequilibrado. |
| [045](../specs/045-gemelo-fisico-y-contratos-pinn-gnn/spec.md) Gemelo físico y contratos PINN/GNN | aprobada | 11 / 11 | T3, T4 | Ablaciones CUDA/dominio/PyG y contraste nativo con reapertura; mantener etiqueta física separada de diseño admisible. |
| [046](../specs/046-pronostico-causal-multihorizonte/spec.md) Pronóstico causal multihorizonte | cumplida | 25 / 25 | — | Corrida CUDA corta histórica documentada: ganaron referencias y no se promovieron neuronales. No es aceptación anual de 089/PIDE. |
| [047](../specs/047-asistente-estructurado-y-revision-por-roles/spec.md) Asistente estructurado y revisión por roles | aprobada | 41 / 41 | T4, T8, T7 | Evaluación real de 200 órdenes, revisión 12 casos sin falsas alarmas/perdidos/sin respuesta y QLoRA auténtico reabierto según puertas. |
| [048](../specs/048-optimizacion-mixta-evolutiva-y-pnl/spec.md) Optimización mixta evolutiva y PNL | implementada | 9 / 9 | T4 | Persistencia medida pero diseño con violaciones; falta obra respaldada eléctricamente admisible tras reabrir. H01 afecta custodia del recibo. |
| [049](../specs/049-protecciones-nativas-y-coordinacion/spec.md) Protecciones nativas y coordinación | implementada | 10 / 10 | T4 | Faltan curvas, ajustes, poder de corte, Scc/impedancia y criterios del perfil para aceptación real. Registro comercial la consigna diferida. |
| [050](../specs/050-aprendizaje-continuo-integrado/spec.md) Aprendizaje continuo integrado | aprobada | 10 / 10 | T1b, T2b, T3b, T4b, T5b | Cinco tareas reales b: instantánea/preparación/ciclo/modelos conjunto/segunda captura. Rama ya conectó productores, consumidores y estado; faltan campaña y aceptación. |
| [051](../specs/051-medicion-de-cabecera-en-libro-ancho/spec.md) Medición de cabecera en libro ancho: una columna por alimentador | implementada | 11 / 11 | T3 | Calibración por web de fuentes de otra empresa con cabecera dentro del 1 % según las magnitudes disponibles. |
| [052](../specs/052-optimizacion-con-proyecto-con-el-oraculo/spec.md) Optimización de «Con proyecto» con el oráculo y confirmación en DIgSILENT | implementada | 19 / 19 | T4 | Optimización real, tiempo <20 min y comparación oráculo/DIgSILENT con elegida y límites confirmados. |
| [053](../specs/053-catalogo-de-fichas-que-crece/spec.md) El catálogo de fichas crece con cada código nuevo | cumplida | 9 / 9 | — | Sin casillas abiertas; ampliación del catálogo debe conservar origen y no convertir inferencias en fichas verificadas. |
| [054](../specs/054-fases-reales-en-el-dgs/spec.md) Fases reales en el DGS: tramos y SED monofásicos y bifásicos | cumplida | 12 / 12 | — | Sin casillas abiertas; pruebas nativas monofásicas de 081 siguen siendo obligaciones distintas. |
| [055](../specs/055-estructura-de-la-fuente-sistemas-y-set/spec.md) Estructura de sistemas y SET desde la propia fuente, para cualquier empresa | implementada | 7 / 7 | T2 | Sistemas/SET por la fuente y conversión de otro perfil/empresa en web; criterio abreviado requiere consultar su plan. |
| [056](../specs/056-nombres-y-mensajes-segun-la-fuente/spec.md) Nombres y mensajes según la fuente: cada fuente con sus propias palabras | implementada | 7 / 7 | T3 | Vocabulario correcto de la fuente observado tras importar por web; criterio abreviado no es aceptación ejecutada. |
| [057](../specs/057-oraculo-corrige-antes-de-digsilent/spec.md) El «Caso base» llega convergido: el oráculo corrige antes de importar | cumplida | 6 / 6 | — | Sin casillas abiertas; convergencia previa del oráculo no acredita convergencia ni límites en PF por sí sola. |
| [058](../specs/058-converter-smart-grid/spec.md) ConverterSmartGrid: el proyecto sin el nombre de otra empresa | aprobada | 10 / 9 | T5, T6, T7 | Regenerar línea base solo por cabecera, suite final y nombre/espacios/acceso directo e importación. Renombrado físico no realizado. |
| [059](../specs/059-fuente-por-lo-que-se-carga/spec.md) La fuente es la del fichero que se carga, sin valor por defecto | cumplida | 8 / 8 | — | Sin casillas abiertas; mantener fuente identificada por archivos reales, sin default de una empresa de muestra. |
| [060](../specs/060-correcciones-del-aprendizaje/spec.md) Correcciones verificables del aprendizaje | cumplida | 8 / 8 | — | Sin casillas abiertas; corregir metodología de entrenamiento no acredita mejora predictiva de todas las familias. |
| [061](../specs/061-observacion-y-operacion-del-agente/spec.md) Observación y operación integrada del agente | cumplida | 10 / 10 | — | Sin casillas abiertas; observación y operación del agente no reemplazan aceptación punta a punta 027/070. |
| [062](../specs/062-retencion-diaria-de-ejecuciones/spec.md) Retención diaria de ejecuciones y temporales | cumplida | 8 / 8 | — | Sin casillas abiertas; retención debe proteger activos/referencias/originales; no se ejecutó limpieza en esta revisión. |
| [063](../specs/063-informe-de-factibilidad-en-un-paso/spec.md) Evaluación de conexión y operación comercial en un paso, para cualquier alimentador | cumplida | 57 / 57 | — | Sin casillas abiertas; sigue requerida revisión humana de los informes concretos de 017 y aceptación eléctrica del caso analizado. |
| [064](../specs/064-arnes-sin-atajos/spec.md) Arnés de DIgSILENT sin atajos: un turno para todos y estado restituido | cumplida | 10 / 10 | — | Sin casillas abiertas; no abrir otro motor para comprobar obras y respetar restitución del estado del operador. |
| [065](../specs/065-cierre-de-auditoria-integral/spec.md) Cierre verificable de la auditoría integral | aprobada | 26 / 26 | T12, T13 → T12, T13, T17 | Aceptaciones por proyecto/caso, regresión/instalación/arranque y T17 nueva en rama; H01/H03 requieren revisión en su mismo cierre. |
| [066](../specs/066-libro-de-cada-informe/spec.md) Cada informe con su libro Excel, según el perfil de la empresa | cumplida | 13 / 13 | — | Sin casillas abiertas; cada entregable debe conservar Excel y unidades/criterios del perfil correspondiente. |
| [067](../specs/067-asistente-operativo/spec.md) Asistente operativo: revisión, planes, modelos y tareas que funcionan desde la web | implementada | 40 / 40 | T9 | Orden que ejecuta escalera/optimización real sobre proyecto de prueba y evidencia de la ruta web. |
| [068](../specs/068-dataset-real-del-maestro/spec.md) Dataset real del maestro: órdenes del operador, etiquetas de plata y currículo con su estilo | cumplida | 42 / 42 | — | Sin casillas abiertas; fuentes reales y currículo no garantizan soporte humano suficiente en cada partición/categoría. |
| [069](../specs/069-interprete-con-codificador-preentrenado/spec.md) Intérprete de órdenes con codificador preentrenado y clase «ninguna» | aprobada | 32 / 32 | T7 | T7 exige candidato PROMOVIDO con prueba no usada para ajustar; registro de candidato rechazado no lo satisface. |
| [070](../specs/070-asistente-de-punta-a-punta/spec.md) El asistente opera el conversor de punta a punta | implementada | 77 / 77 | T9, T10, T11 | Recorridos escritos alimentador/SET/carga, navegador y promoción de candidato en prueba nueva. T11 está marcada nativa aunque su criterio es ML. |
| [071](../specs/071-puertas-de-los-modelos/spec.md) Puertas de los modelos antes de entrenar: PINN en su red, un puntero, sin autoentrenamiento y una guardia de GPU | aprobada | 8 / 8 | T5 | Medir antes/después tiempo y obra elegida sobre misma red; prueba estática de dominio no es ese contraste. |
| [072](../specs/072-pide-y-planeamiento-de-largo-plazo/spec.md) PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio | aprobada | 22 / 22 | T9b, T11, T13, T14 | Revisión humana, aceptación dos entregables, costos oficiales reales y PIDE anual. Rama añade RF/consumidor anual; cadena con ganador aún no acreditada. |
| [073](../specs/073-bancos-limitados-por-valle/spec.md) El número de bancos lo define la tensión en las ventanas de valle | implementada | 41 / 41 | T8, T12 | Valle con cabecera medida y máxima conservada, contraste oráculo/PF y columna En valle observada en navegador. |
| [074](../specs/074-piloto-madrl-en-obras/spec.md) Piloto MADRL en obras: medir antes de aprender | aprobada | 12 / 11 | T5, T7, T8 | Recaptura ntnum/fidelidad, GATv2 y MaskablePPO sobre redes reales, puerta en no vistos y confirmación nativa o archivo del piloto con medida. |
| [075](../specs/075-validacion-cruzada-de-las-ordenes/spec.md) Validación cruzada con las órdenes confirmadas, y Ollama no adivina cuando el modelo ve charla | cumplida | 46 / 46 | — | Sin casillas abiertas; mecanismo de partición validado no implica que intérprete actual pase todas las puertas de 069/070. |
| [076](../specs/076-preguntas-de-metodologia-por-entregable/spec.md) Preguntas de metodología y criterios por entregable, del flujo, de la arquitectura y de la web | cumplida | 34 / 34 | — | Sin casillas abiertas; referencias operativas deben revalidarse al mover archivos/líneas del frontend y servicios. |
| [077](../specs/077-asistente-lee-el-proyecto/spec.md) El asistente lee skills, documentos, código y API del proyecto, y un MCP local de solo lectura | cumplida | 74 / 74 | — | Sin casillas abiertas; lectura/RAG/MCP implementados no equivalen a evaluación/promotion del embedding nuevo de 097. |
| [078](../specs/078-senales-de-convergencia/spec.md) Las señales de convergencia dicen lo que devolvió DIgSILENT, y el asistente importa un grupo ya convertido | implementada | 35 / 35 | T6, T7 | Proyecto con fallo y proyecto válido por web; verificar estados/return_code veraces y orden de importación en navegador. |
| [079](../specs/079-afinado-del-interprete-de-ordenes/spec.md) Afinado real del intérprete de órdenes: las últimas capas del codificador junto con sus cabezas | cumplida | 64 / 64 | — | Sin casillas abiertas; afinado real histórico no constituye promoción del mejor candidato en examen nuevo. |
| [080](../specs/080-acceso-directo-a-paquetes-vnrgis/spec.md) Acceso directo a los paquetes VNR-GIS de cada distribuidora | cumplida | 52 / 52 | — | Sin casillas abiertas; conservar procedencia/CRS/perfil y no imponer paquetes específicos de muestra como requisito universal. |
| [081](../specs/081-regresiones-permanentes/spec.md) Los fallos reales no se repiten: comprobaciones permanentes, solución con los oráculos y mejora continua | implementada | 85 / 85 | T22, T20, T10, T11, T12, T13, T14, T16, T24, T31 → T22, T10, T11, T12, T13, T14, T16, T24, T31 | Diez casillas en main/nueve en rama; fases/servicio/base intacta/parcialidad/corte/catálogo/empresa/estadística/transferencia. T20 ya cerrada en rama. |
| [082](../specs/082-oraculo-completo-y-por-fases/spec.md) El oráculo calcula todo lo del modelo, y por fases | cumplida | 15 / 15 | — | Sin casillas abiertas; cálculo por fases del oráculo no autoriza extrapolar otro dominio de la PINN. |
| [083](../specs/083-oraculo-antes-de-calibrar/spec.md) El oráculo antes de calibrar y recalibrar | cumplida | 31 / 31 | — | Sin casillas abiertas; corrección anterior a calibrar se confirma en las campañas dependientes, no por inventario. |
| [084](../specs/084-seis-reglas-con-requisito/spec.md) Seis reglas del operador pasan de notas a requisitos con prueba | implementada | 30 / 30 | T8, T9 | SET fuera de trazado con flujos equilibrado/desequilibrado y iopt_net restituido; terna de cable con fabricante/fline persistido. |
| [085](../specs/085-ordenes-del-maestro-con-grupos-apartados/spec.md) Órdenes del maestro con grupos apartados, y la puerta de órdenes sin humanas suficientes | cumplida | 33 / 33 | — | Sin casillas abiertas; uso provisional por decisión expresa conserva RECHAZADO y confirmación, no se presenta como modelo aprobado. |
| [086](../specs/086-puesta-en-operacion-comercial/spec.md) Puesta en operación comercial: versión 1.0 instalable, segura y probada de punta a punta | aprobada | 53 / 49 | T9, T36, T40, T41, T24, T25, T26, T27, T28, T29, T30, T31, T32, T33, T34 | Quince casillas abiertas: aceptación de flujos/instalación/interrupción/sin red/tercero/suite/publicación. Actualizar cierres locales con recibos y residuos. |
| [087](../specs/087-seleccion-de-obras-con-metodos-y-medicion/spec.md) Selección de obras con el oráculo, métodos probabilísticos y medición de la mejora | implementada | 57 / 57 | T27, T12, T13, T14 | Confirmación conjunta Pisco, referencia frente a oráculo en mismo estado y otra empresa; medir tiempo/costo/norma, no solo proponer. |
| [088](../specs/088-q-de-cabecera-desde-el-factor-de-potencia/spec.md) Q negativa desde el factor de potencia | cumplida | 12 / 12 | — | Sin casillas abiertas; Q negativa debe conservar signo y instante al calibrar con factor de potencia. |
| [089](../specs/089-pronostico-de-demanda-en-un-modulo/spec.md) Pronóstico de demanda en un módulo: datos vivos, limpieza, tres clases y backtest por método | aprobada | 88 / 88 | T5, T7 | Backtest real 2026 y corrida larga de modelos por clase/magnitud/horizonte; decisiones y cifras fuera de datos privados. |
| [090](../specs/090-arquitectura-generada/spec.md) La arquitectura se cataloga sola: todos los módulos, el asistente y su equipo | cumplida | 16 / 16 | — | Catálogo declarado cumplido pero deriva reproducida por services modificado. Actualizarlo al revisar el corte dueño, sin sobrescribir ese cambio. |
| [091](../specs/091-flujo-calibracion-a-estudio/spec.md) De la calibración al estudio, en su orden y sin avisos que engañen | implementada | 33 / 33 | T7 | TM102: calibración/recalibración/estudio en navegador con habilitación/mensajes correctos y cifras reales. |
| [092](../specs/092-caso-base-de-una-red-reconstruida/spec.md) El «Caso base» de una red reconstruida se verifica con lo que hay en disco | implementada | 4 / 4 | T2 | Verificación real Caso base reconstruido, fuente coherente y sin SOURCE_RUN_MISMATCH; caso de muestra sujeto a identidad de campaña vigente. |
| [093](../specs/093-siglas-de-carga-como-nombre/spec.md) La sigla de la carga nombra la carga nueva y su variación | cumplida | 4 / 4 | — | Sin casillas abiertas; verificar nombre/variación de nueva carga al repetir aceptación del libro actual. |
| [094](../specs/094-perfil-de-tension-y-bancos/spec.md) Perfil de tensión en la calibración y bancos ubicados según el perfil | implementada | 18 / 18 | T5 | Perfil recalibrado dibujado en navegador y bancos del perfil aplicados y confirmados en PowerFactory. |
| [095](../specs/095-escaladas-proporcionales-a-su-kva/spec.md) Escaladas proporcionales a su potencia instalada | cumplida | 3 / 3 | — | Sin casillas abiertas; reparto por kVA no equivale a admisibilidad eléctrica de todas las SED. |
| [096](../specs/096-retomar-tras-suspender-el-equipo/spec.md) Tras suspender el equipo, la web vuelve sola al último trabajo pendiente | implementada | 7 / 7 | T3 | Suspender/despertar a mitad de recalibración y terminación automática real; pruebas de PID/recuperación CPU son parciales. |
| [097](../specs/097-vectores-multilingues-del-rag/spec.md) Vectores multilingües para la búsqueda del asistente | aprobada | 7 / 4 | T3 | Comparar candidatos GPU por MRR@10/Recall@10, confirmar una vez en sellado y conservar activo si falla; RF-5/6/7 aún sin cita en main. |
| [098](../specs/098-transferencia-del-operador-en-calibracion-y-obras/spec.md) La transferencia de carga del operador, en la calibración y en las obras | implementada | 49 / 49 | T6 | Transferencia del operador restituida/conservada, pérdidas no negativas, alternativas medidas por costo y receptores verificados. Finalización RF-45 desfasada frente a RF-49. |
| [099](../specs/099-cargas-del-libro-duplicadas-por-el-nombre-del-cliente/spec.md) Cargas del libro duplicadas por el nombre del cliente | implementada | 8 / 8 | T3 | Libro real: crear CH_23, excluir CH_20 y retirar su variación anterior con informe y relectura del proyecto. |

## RF sin cita exacta en pruebas

- 002: RF-1, RF-6, RF-18, RF-19, RF-21, RF-22.
- 027: RF-10, RF-21, RF-28, RF-40, RF-45, RF-52, RF-54, RF-55.
- 058: RF-10.
- 074: RF-10.
- 086: RF-45, RF-46, RF-52, RF-53.
- 097: RF-5, RF-6, RF-7.

El anexo externo `requisitos_auditados.csv` contiene las 3.219 filas y separa cita de archivo, función con aserción, ejecución observada y aceptación pendiente. `detalle_por_spec.md` conserva cada tarea abierta con su criterio original y los enlaces de código/pruebas por SPEC.
