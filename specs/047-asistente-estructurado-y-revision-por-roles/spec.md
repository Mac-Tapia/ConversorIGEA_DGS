# Spec 047 — Asistente estructurado y revisión por roles

Estado: aprobada · Fecha: 2026-10-31

## Contexto y objetivo

El asistente ya tiene Transformer, clasificador, reglas, Ollama y BM25 con vectores opcionales. TradingAgents inspira roles separados, pero el sistema financiero no se incorpora ni demuestra capacidad eléctrica.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 043 y 044; conservar intérprete, resolución, herramientas y confirmaciones de 026–027.

## Requisitos funcionales (EARS)

- RF-1: CUANDO el modelo local interprete una orden, EL SISTEMA validará su salida contra el esquema de tareas y campos admitidos.
- RF-2: SI una entidad no corresponde al contexto vinculado, ENTONCES EL SISTEMA impedirá que esa entidad forme un plan ejecutable.
- RF-3: CUANDO se responda con documentos, EL SISTEMA conservará citas vinculadas a fragmentos de fuente verificables.
- RF-4: CUANDO se evalúe recuperación, EL SISTEMA comparará BM25, híbrido y reranker con el mismo conjunto sellado.
- RF-5: CUANDO se revise una propuesta, EL SISTEMA separará evidencia de fuentes, consistencia física, coste y riesgo en dictámenes trazables.
- RF-6: SI un dictamen carece de evidencia o contradice una restricción determinista, ENTONCES EL SISTEMA impedirá presentarlo como aprobación de ejecución.
- RF-7: MIENTRAS se revise por roles, EL SISTEMA limitará la discusión a dos rondas cancelables sin escrituras nativas.
- RF-8: CUANDO se decida ajustar el LLM, EL SISTEMA exigirá el incumplimiento medido de las puertas del conjunto real.
- RF-9: CUANDO se evalúe el asistente, EL SISTEMA aplicará las puertas de 027:RF-18 sobre órdenes reales independientes.
- RF-10: EL SISTEMA conservará las reglas de autorización y confirmación vigentes al incorporar los nuevos modelos.

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- JSON válido con tarea inexistente: T1, test_tarea_desconocida_rechaza.
- SED en otro alimentador pese al libro viejo: T1, test_entidad_respeta_fuente_activa.
- Reranker elimina coincidencia exacta de código: T2, test_codigo_exacto_se_conserva.
- Cuatro roles repiten la misma afirmación sin fuente: T3, test_critico_sin_evidencia_no_aprueba.
- Dataset sintético supera umbral de 200 reales: T4, test_qlora_sin_gold_real_bloquea.

## Fuera de alcance

Trading financiero; ejecución autónoma de maniobras por consenso LLM; datos empresariales en API externas; QLoRA obligatorio sin déficit demostrado.

## Criterios de finalización

Cada RF tiene una prueba con cita `047:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

[TradingAgents oficial](https://github.com/TauricResearch/TradingAgents) inspira revisión por roles, con licencia Apache-2.0; su paper/repo financiero no se presenta como evidencia eléctrica. [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs) y [retrieve/rerank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html) sustentan los contratos técnicos.

## Clarificaciones de diseño

El alcance y las políticas anteriores son propuesta en borrador. No se declara
aprobada esta spec ni se cambia el estado de specs anteriores por crear el plan.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

