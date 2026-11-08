# Harness integral: uso, evidencia y entrega coordinada

Fecha: 2026-11-08. Tarea HARNESS-20261108. Responsable: sesión «Mejorar precisión y
recall del LLM». Worktree `.worktrees/harness-integral-20261108`, rama
`codex/harness-integral-20261108`, base `5617251012f39193297e19b299d8a179a8fe1f61`.

## Estado comprobado

El usuario aprobó el diseño y pidió coordinación con la otra sesión. Se envió un
mensaje identificado como comunicación de agente mediante el chat de Codex
«Audita el proyecto para producción»; se observó el mensaje entregado. Esa sesión
confirmó recepción y reparto de archivos en `.agents/coordination/ACTIVE.md`.
Su actualización posterior liberó G2 y permitió pruebas CPU ligeras; mantiene
reservados GPU/PF/build e integración comercial. No se interpreta ese acuse como
aceptación de esta implementación.

Se implementaron el núcleo de métricas, configuración sellada, ejecución pareada,
validación de integridad, guarda runtime, adaptadores y CLI. La revisión
independiente ejecutó y confirmó 31 pruebas stdlib con Python 3.12, sin hallazgos
Critical/Important pendientes en las superficies nuevas. Incluyen una prueba CLI
en proceso hijo y restauración del informe previo ante fallo de relectura.
Las pruebas con proveedores/evaluadores dobles, incluso las que simulan metadata
`real` para probar una guarda, son exclusivamente contratos. No constituyen una
campaña de inferencia, entrenamiento, promoción ni aceptación eléctrica.

## CLI local

Desde la raíz del worktree, con Python 3.12:

```powershell
py -3.12 -I -B tools/evaluar_harness.py --help
py -3.12 -I -B tools/evaluar_harness.py sellar --config config.json --salida config_sellada.json
py -3.12 -I -B tools/evaluar_harness.py replay --config config_sellada.json --predicciones casos.json --salida diagnostico.json
py -3.12 -I -B tools/evaluar_harness.py verificar --informe diagnostico.json
py -3.12 -I -B tools/evaluar_harness.py ordenes --entrada evaluacion_ordenes.json --salida metricas_ordenes.json
py -3.12 -I -B tools/evaluar_harness.py importar --herramienta promptfoo --commit 2a6fdf9b2e1600ffa2a204e70e9fea7cb0c14cff --lock docs/superpowers/specs/2026-11-08-harness-integral-modelos-design-fuentes.json --entrada promptfoo.json --salida importacion.json
```

`sellar` rechaza mínimos omitidos, grupos/textos cruzados, ids repetidos y omisión
de suites obligatorias. Los mínimos positivos del formato son una validación
estructural: no acreditan suficiente potencia estadística ni corpus humano.
Las cuotas/políticas de dominio vigentes siguen siendo obligatorias.

`replay` exige ids/entradas/digests de las salidas guardadas, recalcula métricas
contra el gold sellado y conserva omisiones. Los evaluadores independientes de
dominio no se reconstruyen desde un JSON ni se sustituyen por sus propios scores;
si faltan, las suites correspondientes quedan incompletas. Esto es intencional.
No ejecuta comandos, imports o modelos indicados en archivos de configuración.

`ordenes` requiere casos individuales, entidades normalizadas y VP/FP/FN
coherentes con su resumen; conserva el F1 histórico junto a la convención nueva.
No puede inferir precision/recall a partir de un F1 agregado sin sus conteos.
El informe histórico `output/asistente_integral_20261106.json` inspeccionado contiene
resúmenes y no una lista `casos` suficiente para esta operación: no se inventó
una línea base con él ni se reejecutó el modelo para suplirlo.

`importar` acepta resultados auxiliares de las revisiones fijadas: `results` por
tarea en EleutherAI, EvaluateSummaryV3 de Promptfoo, y exportación explícita
`{"scores": resultado.scores}` de Ragas. Conserva la salida original y su huella.
No transforma accuracy de un benchmark en recall, juicio LLM en verdad experta,
ni importación histórica en inferencia actual. Se inspeccionaron los tipos
EvaluateSummaryV3 y EvaluationResult.scores en los commits fijados mediante sus
fuentes oficiales; no se instalaron ni ejecutaron esos paquetes.

Código 0 significa que la operación diagnóstica/publicación o verificación de
integridad terminó; nunca significa aceptación del modelo. Código 2 señala
entrada inválida, fallo de operación o cobertura incompleta de replay. El
resultado incluye su modo, bloqueos y `promocion_ejecutada=false` en la salida CLI.

## API de inferencia y evaluación independiente

```python
from convertersmartgrid.evaluacion_harness.ejecucion import ejecutar, validar_promocion

# La aplicación es responsable de adquirir y conservar el turno real con el
# coordinador vigente antes de invocar proveedores GPU o PowerFactory.
informe = ejecutar(config_sellada, proveedor_local, modo="runtime",
                   evaluadores=evaluadores_independientes,
                   cancelar=cancelacion_del_trabajo)
# Guarda adicional en el MISMO proceso; no escribe el registro.
validar_promocion(informe, config_sellada)
```

`proveedor_local(modelo, suite, entrada)` recibe solo identidad de modelo,
descriptor de suite sin casos/gold y copia de la entrada. Debe devolver
`prediccion` (objeto), `modelo_digest`, `config_hash` efectivos, `backend`,
`dispositivo` y `clase_evidencia`. Un digest o configuración distintos invalidan
el caso. El harness no interpreta el dispositivo solicitado como dispositivo
efectivo, y no carga ni entrena modelos por importar el paquete.

El mapa `evaluadores_independientes[tipo]` contiene callables Python explícitos
con firma `(gold, predicciones, parametros) -> resultado`. Se requieren para
pronóstico, gemelo, optimización, fundamentación, guardas, recarga, dominio y
verificación nativa. Deben devolver `metricas`, `aprobado` y su clase de evidencia;
para comparación estadística de dominio deben entregar `por_grupo` exclusivamente
como `{group_id: {metrica: valor}}`. Los escalares se rechazan incluso con un
contraste único; un MAE nunca se usa implícitamente como RMSE u otra métrica.
`parametros['_harness']` aporta los grupos,
rol y digest sin exponer el gold al proveedor.

`adaptadores.evaluar_temporal` delega al evaluador temporal vigente;
`adaptadores.evaluar_electrico` aplica la política existente y declara
`aceptacion_nativa=false`. Son envoltorios de evaluación directa: la aplicación
debe construir el callback de suite con su esquema de casos y evidencia real.
No se presenta esa conexión pendiente como activación automática.

Los contrastes sellan métrica, margen, dirección `mayor_mejor`/`menor_mejor`,
semilla, remuestras, confianza y mínimo de grupos. Estiman mejora de la media de
grupos con corrección Bonferroni de los contrastes declarados; no un intervalo
de un ratio global. Un grupo fallido/cancelado sigue bloqueando el contraste.
Las puertas admiten rutas como `clases.b.recall` o `tipos.sed.recall`.
Con gold de recuperación parcial, P@k/Recall@k/MRR quedan vacíos y se publican
las métricas sobre positivos conocidos bajo nombres diferentes.

La guarda exige informe íntegro, campaña runtime viva en el mismo proceso,
identidades coincidentes, todas las suites obligatorias aprobadas y mejora
según protocolo. Un nonce no autentica datos de terceros ni valida físicamente
una predicción: evita reutilizar un informe histórico como ejecución actual.
Después de esta guarda siguen siendo obligatorias las puertas, artefactos y
recarga del registro existente. El puente `integracion.registrar_resultado` puede
invocar la promoción existente solo con `activar=True` explícito y todas las
comprobaciones siguientes satisfechas.

## Puente ejecutable al entrenamiento y al registro

`integracion.crear_etapa(...)` devuelve un `TrainingStage` del proyecto que puede
ejecutar el `TrainingCoordinator` existente. Ejecuta evaluación, publica/reabre
el informe y registra el candidato automáticamente. La etapa usa nombres vigentes
(`qlora` para el LLM, `gru`, `pinn`, etc.), orden y exclusión de GPU del coordinador;
no cambia sus módulos ni ejecuta recursos al construirla. Cancelación conserva
el informe y devuelve estado bloqueado sin activar el candidato.

Antes de sellar una campaña que registre modelos, `config.integracion` debe
declarar `modelo`, `etapa`, `uses_gpu`, `registro_raiz` **absoluta** y
`activo_esperado` (puntero completo leído del registro, o `null` si no existe).
El mapa permitido impide publicar un LLM en el slot PINN; el puente comprueba
destino y activo esperado antes de escribir y antes de activar.

`config.modelos.candidato.artifacts` contiene los SHA-256 de todos los artefactos
evaluados, por nombre, antes de abrir prueba. El proveedor devuelve
`artifacts_hash=huella(artifacts)` efectivo. Los manifiestos, el snapshot privado
que se copia al registro y la recarga deben corresponder a esas mismas huellas.
No se acepta un fichero distinto presentado después de medir con su nuevo hash.

`declaracion` aporta `modelo`, `model_manifest`, `dataset_manifest`,
`decision_dominio`, `smoke_reload` y `artifacts`. La política sellada declara
`dominio_hash`. La decisión heredada debe incluir política, puertas y
`modelo_digest`, `config_hash`, `dataset_hash`, `artifacts_hash`; además debe
coincidir exactamente con `decision_original` emitida por el evaluador
independiente de la única suite `dominio` obligatoria de esa campaña. No basta
reutilizar un dict de aprobación de una evaluación anterior.

`revalidar()` debe devolver un mapa con `referencia` y `candidato`, cada uno con
digest y configuración efectivos, y huella de artefactos cuando estén declarados.
Se comprueba antes de registrar y antes de activar. `smoke_reload` declara
`ok`, `modelo_digest`, `config_hash` y `artifacts_hash` de la recarga independiente.
Si faltan puertas/recarga o la campaña es contract/replay, se conserva evidencia
como candidato rechazado y el activo sigue intacto. Los cambios contradictorios
de identidad/destino impiden la operación antes de registrar.

Esta conexión se probó con clases reales del coordinador/registro sobre rutas
temporales; sus proveedores y decisiones fueron dobles identificados. Incluso
el test de promoción usa un registro efímero, no modelos ni activos del usuario.
Se requiere admisión de **un escritor por slot** en la aplicación: comprobar el
puntero esperado no convierte el registro heredado en una operación CAS frente
a otros productores que ignoren esta admisión.

Los informes se publican por staging, fsync, reemplazo y relectura. Si falla la
relectura posterior se intenta restauración verificada de los bytes previos;
un fallo del propio rollback conserva un temporal recuperable y lo identifica.
Se requiere **un escritor por ruta**; la comprobación de cambio concurrente no
es una operación CAS y no acredita exclusión frente a escritores externos.

## Integración pendiente y límites

- No se editaron `aceptacion.py`, `model_registry.py`, `training_coordinator.py`,
  jobs ni otros archivos reservados por producción. La conexión se implementó
  mediante una etapa nueva que usa esas APIs; configurar sus productores/jobs
  heredados y su admisión queda a cargo del integrador. El catálogo generado por
  hook090 en este worktree ya fue autorizado expresamente, sin bypass del hook.
- Se contrastaron en lectura los contratos usados entre base `56172510` y corte
  comercial `bbb596ab8837ebbaca5a8e0a0b38f82a1bae329e`. De los cuatro módulos
  inspeccionados solo el registro tenía una función adicional de materialización;
  no se asumió que main fuese el corte comercial final. Revalidar al integrar.
- No se realizó campaña runtime de LLM/GPU, pronóstico entrenado, ni PowerFactory.
  No hay aumento de precisión/recall demostrado, ni promoción ni aceptación
  eléctrica/científica. Deben declararse datos, referencias, soporte y puertas
  de cada campaña antes de medir y obtener turno de los recursos reservados.
- La suite completa del producto y aceptación sobre el corte integrado siguen
  pendientes. Las 42 pruebas propias y revisión independiente verifican este
  núcleo y sus contratos; no cierran specs eléctricas ni la producción.

El fundamento académico y sus límites se conservan en el diseño: tesis de
maestría de König, doctorado de Stiasny, RAGAs (EACL), PowerFlowNet y JMLR.
Las fuentes justifican el método, no los resultados locales todavía ausentes.
