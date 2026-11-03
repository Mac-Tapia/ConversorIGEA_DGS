# Gobierno operativo del equipo LLM — M9

Responsable: implementador_equipo_llm. Proyecto: ConversorIGEA_DGS.
Candidato: `codex/mejoras-auditoria-integral`, base `f5c9c89d`.
Contrato: 065:RF-22/23; conserva 027:RF-19/20, 047:RF-5/6/7/10 y 061.
Las evidencias de esta entrega están fuera del checkout, en
`D:/converter/auditorias/ConversorIGEA_DGS_20261102/implementacion065/equipo_llm/`.

## Implementación y conexión

`asistente/equipo.py` fija tarea, datos, espacio, fuente, modo y vínculo del proyecto
al proponer el plan. La confirmación solo se aplica a esa firma. El rol operador
ejecuta la herramienta concreta; fuentes/física/coste/riesgo revisan, sin permisos
de ejecución. Desconocidos, cambios de contexto, métodos, rutas y cuerpos fuera
del plan se rechazan antes del HTTP. Los archivos aportados por ruta se sellan y
releen mediante SHA-256: otro libro con el mismo nombre exige propuesta nueva.
Un modelo presente no añade permisos.

`web/services.py` crea el gobierno al proponer y corregir, lo usa al ejecutar y
revoca la propuesta anterior tras corregirla. La rama proceso tiene la misma
admisión. `asistente/orquestador.py` recibe la fábrica de gobierno por etapa desde
el servicio real del agente, incluidas las etapas de proceso. Se conservan las
rutas y la cola existentes; no hay un segundo motor nativo.

El ejecutor limita el destino a la API local, impide redirecciones de requests y
comprueba el espacio efectivo. La exclusión del equipo admite una acción por
espacio en el proceso; JobManager/pf_arnes conservan la exclusión eléctrica. El
diario local registra propietario, entradas/huella, alcance, carril, decisión,
pasos autorizados y salidas/huella. Una escritura inicial fallida del diario
impide ejecutar. Una pérdida posterior de persistencia se informa como fallo.

`asistente/revision_roles.py` ejecuta cuatro dictámenes separados, hasta dos rondas,
con cancelación entre intervenciones y presupuesto temporal. Se releen SHA-256 y
contexto de las citas. Una contradicción con las restricciones deterministas,
evidencia ausente/alterada o una incertidumbre pendiente impide dictamen favorable.
El adaptador usa exclusivamente ClienteOllama local, formato estructurado y salida
limitada a 512 tokens por intervención, sin herramientas de ejecución.

`web/equipo_api.py` monta inventario global, permisos del espacio y revisión de un
plan guardado como trabajo. El servidor selecciona informes previamente custodiados
por observacion, del mismo proyecto/fuente, y fragmentos verificables. El cliente
no aporta rutas, permisos ni restricciones. Sin evidencia contextual se abstiene
sin cargar LLM. La aprobación es documental, conserva `autoriza_ejecucion=false`
y no acredita física, mejora del modelo ni aceptación nativa.

`frontend/src/components/EquipoAsistente.tsx` y `equipoAsistente.ts` muestran roles,
herramientas, permiso efectivo del plan y dictámenes. La revisión se sigue por los
eventos de trabajos existentes, sin sondeo periódico. El integrador monta el router
y el componente en las superficies compartidas que posee.

## Verificación y evidencia real

Pruebas nuevas: `test_asistente_equipo.py`, `test_asistente_revision_roles.py`,
`test_asistente_equipo_web.py` y `frontend/test/equipoAsistente.test.mjs`.
Las primeras negativas fallaron por módulos inexistentes; las negativas adicionales
reprodujeron llamadas indebidas a otro espacio/destino y ausencia del hook por etapa.
Se conservan resultados intermedios `contratos.xml`, `integracion.xml` y
`regresion2.xml`; no se cuentan como una suite final aprobada.

Las pruebas HTTP/cola usan FastAPI real y almacenamiento propio. Los motores y el
transporte LLM están sustituidos explícitamente en contratos: no acreditan cálculo
eléctrico, entrenamiento ni calidad de los revisores. La comprobación frontend
`npm run typecheck` y los dos contratos del cliente pasaron durante el desarrollo.

Verificación enfocada final del 2026-11-02: **83 aprobadas, cero fallos/omisiones**
en los ocho archivos de pruebas de equipo/revisión/web/tareas/esquema/orquestador/
monitor, en 15,48 s, con `-B -p no:cacheprovider` y temporales externos.
Informe: `cierre.xml`. Incluye rechazo de llamadas directas sin paso y proxies de
entorno desactivados. Cinco E2E verificaron además el contrato JobRespuesta del
router (`contrato_router.xml`). Dos contratos frontend y comprobación TypeScript
también aprobados. Esta es regresión enfocada, no la suite completa ni aceptación
científica. La integración general debe verificar de nuevo el candidato completo.

`inventario_real.json` registra 241 JSON/JSONL reales reabiertos con SHA-256 y cero
ilegibles. Se leyeron las carpetas de asistente, aceptación de 200 propuestas,
alumno generativo, destilación y monitor del output principal, sin copiar pesos.
Los GET a `127.0.0.1:8765` de health/modelos/aceptacion/registro devolvieron 200;
sus respuestas están conservadas en `api_*.json`. Ese proceso corresponde al main
ya abierto: esta sonda no demuestra despliegue del candidato. No se reinició el
servidor, entrenaron modelos ni se ejecutó PowerFactory.

La evidencia releída conserva Qwen3:8b: 188/200 tareas (0,94), F1 0,9393939394;
puertas 0,98 y 0,95 incumplidas. Hay cinco eventos humanos, tres órdenes únicas,
y 2/3 tareas correctas en su evaluación. `integral=false`, aceptación eléctrica
ausente. La API de modelos conserva Transformer RECHAZADO, QLoRA ERROR_ENTORNO y
`complete=false`; los restantes estados sin terminal no se convierten en promociones.

## Pendientes que no cierra este cambio

| Spec | Evidencia/implementación observada | Falta exigida por su contrato |
| --- | --- | --- |
| 043 | registro/coordinador y GET real con estados y bloqueos | reapertura correcta en CUDA y campaña integral: T9 abierta; T1/T3/T4 cerradas el 2026-11-03 |
| 044 | contratos de experimentos/evaluación disponibles | verificación completa por alternativa y reapertura nativa, no solo convergencia |
| 045 | episode/buffer/oraculo y adaptador_pyg existentes | contratos_fisicos/benchmark_fisico y pruebas previstas ausentes; ablación/domain gate y contraste nativo siguen pendientes |
| 046 | series_causales.py y su prueba existentes | pronostico/adaptador_neuralforecast/evaluacion_temporal y pruebas previstas ausentes; benchmark causal real y promoción por horizonte pendientes |
| 047 | esquema existente; gobierno, revisores y conexión añadidos | comparación rol único/equipo con casos sellados y coste/latencia; reranker/QLoRA y destilación generativa completa no demostrados |
| 048 | evolutivos existentes | problema mixto/adaptadores pymoo-PNL/benchmark y pruebas previstas ausentes; >=20 semillas, verificación top-k completa y persistencia nativa pendientes |
| 049 | catálogo de estudios existente | módulo/guion/contratos de protecciones y pruebas previstas ausentes; licencia/curvas/selectividad/reapertura reales pendientes |
| 050 | coordinador ordena familias separadas | instantánea común, replay causal, retención, evaluación conjunta y activación/reversión de conjunto no demostradas; pruebas previstas ausentes |

Esta tabla proviene de las specs/planes/tareas actuales y de existencia de archivos;
no es una evaluación científica nueva. El cambio no cierra casillas de 043–050 ni
declara producción o aceptación eléctrica por disponer de controles y pruebas verdes.

## Fundamento consultado en la web el 2026-11-02

- Chan-Zheng, C. (2017). *MAES: A Multi-Agent Systems Framework for Embedded Systems*.
  Tesis de maestría, TU Delft. La coordinación requiere contratos de interacción y
  tiene un coste medible; no basta enumerar agentes.
  https://repository.tudelft.nl/file/File_74edee35-0523-4bd3-92a3-04f9723a9b86
- Amrit, C. (2008). *Improving coordination in software development through social
  and technical network analysis*. Tesis doctoral, University of Twente. Fundamenta
  vincular responsables, dependencias técnicas y evidencia observable.
  https://research.utwente.nl/en/publications/improving-coordination-in-software-development-through-social-and-2/
- Kreuzberger, D., Kühl, N. y Hirschl, S. (2023). *Machine Learning Operations
  (MLOps): Overview, Definition, and Architecture*. IEEE Access, 11, 31866–31879.
  Artículo revisado en revista indexada; distingue roles, componentes y ciclo de
  operación. https://doi.org/10.1109/ACCESS.2023.3262138
  Texto primario abierto: https://epub.uni-bayreuth.de/id/eprint/7577/1/Machine_Learning_Operations_MLOps_Overview_Definition_and_Architecture.pdf
- Ollama. *Structured Outputs*, documentación oficial consultada para el contrato
  JSON del adaptador local. https://docs.ollama.com/capabilities/structured-outputs

Estas fuentes justifican decisiones metodológicas; no certifican esta implementación,
la independencia de cuatro llamadas al mismo LLM ni su competencia eléctrica.
