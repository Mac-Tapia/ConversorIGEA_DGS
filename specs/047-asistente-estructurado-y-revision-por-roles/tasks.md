# Tareas — Spec 047

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Esquema de salida y entidades del contexto activo. (RF-1, RF-2, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_salida_estructurada.py tests/test_asistente_interprete.py tests/test_asistente_ollama.py tests/test_asistente_tareas.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.
      Evidencia: esas pruebas, sin omitidas, 2026-11-03 (ver «T1, T3 y T4, 2026-11-03» abajo). El esquema ya viajó a Ollama real en las 200 propuestas de T6.

- [x] T2. Recuperación híbrida con reranker contrastado. (RF-3, RF-4, RF-21 a RF-37)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_reranker.py tests/test_asistente_indice.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.
      Evidencia: `docs/EVALUACION_RAG_047.json` (mmarco adoptado, MRR@10 0,786) y `docs/EVALUACION_ABSTENCION_047.json` (sellado: reranker cumple; híbrido 0,925 y BM25 0,950 de abstención). Cierre por la regla aceptada por el usuario el 2026-11-02 (plan, T2).

- [x] T3. Revisión por roles acotada y trazable. (RF-5, RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_revision_roles.py tests/test_asistente_tareas.py tests/test_asistente_web.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.
      Falta: la comparación rol único frente a equipo con un LLM real (`tools/asistente_comparar_revision.py --modelo <modelo> --salida <informe.json>`). Pide Ollama y su GPU.

- [ ] T4. Evaluación real y ajuste condicionado. (RF-8, RF-9, RF-59)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_ajuste_condicionado.py tests/test_asistente_qlora.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan.
      Falta: carga cuantizada y un paso en CUDA con la revisión fijada, con su VRAM y la reapertura del adaptador real; exigir `decidir_ajuste` en `tools/asistente_qlora.py`, junto con T7; y la evaluación final con 200 órdenes reales (desde la T12, mientras falten humanas, con las 200 revisadas por el maestro de RF-64: `aceptar_agente.py preparar --revisadas-maestro` y `evaluar` en GPU).

- [x] T5. Destilación reproducible del maestro de sesión y ensayo del alumno. (RF-11, RF-12, RF-13, RF-14, RF-15)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_destilacion_integral.py tests/test_evaluacion_modelos.py` pasa, se ejecuta entrenamiento CUDA real con comparación supervisado/destilado, reapertura en proceso nuevo y ensayo del intérprete/plan; se informa por separado cualquier bloqueo de promoción por datos humanos.

- [x] T6. Auditar, materializar y evaluar 200 propuestas únicas, sin fuga y con puertas por alcance. (RF-13, RF-16, RF-17, RF-18)
      Hecho cuando: pruebas de `tests/test_aceptacion_agente.py` y regresiones de órdenes fijas/intérprete pasan; se ejecutan selección local de configuración y evaluación sellada de las 200 propuestas, con informe de métricas/errores/bloqueos y sin escrituras nativas.

- [ ] T8. Que la revisión distinga una propuesta sana de una con defecto antes de autorizar nada. (RF-5, RF-6, RF-38, RF-39, RF-40, RF-41, RF-43, RF-44, RF-45, RF-46, RF-47)
      Hecho cuando: `tools/asistente_comparar_revision.py` sobre sus 12 casos da 0 falsas alarmas sin perder defectos, con el
      informe en `docs/asistente/`, sin ajustar nada mirando esos casos (si hace falta, con un conjunto nuevo declarado antes de medir).
      Código, 2026-11-03 (rama `feat/027-047t8`): causa hallada en el código y en el encargo, sin leer el contenido de los
      12 casos y sin Ollama. (1) El encargo solo decía cuándo bloquear («ante evidencia insuficiente usa bloqueada») y
      prohibía aprobar la física («no apruebes física por consenso textual»), que solo se revisa por texto; el de riesgo
      pedía imaginar que la propuesta «falla». Ninguna regla decía cuándo es favorable. (2) La decisión era el primer
      campo del esquema y, sin razonar (`think: false`), el modelo la escribía antes de comparar nada. (3) Un dictamen
      «bloqueada» sin contradicción ni incertidumbre contaba como defecto hallado: los «6 de 6» no lo acreditan.
      (4) El proyecto y el fichero de cada caso se llamaban como el caso («sano-…», «defecto-…») y viajaban al LLM con
      la ruta y la huella. (5) El informe no guardaba los dictámenes. Corregido con RF-38 a RF-41: regla de decisión
      común, decisión al final del esquema, bloqueo sin hallazgo como dictamen no válido (cuenta como sin respuesta, no
      como detección), al LLM solo la propuesta y los fragmentos, nombres opacos, dictámenes en el informe. Mismo
      conjunto, misma huella `102bdfbf…1ca6d`: no se cambió ni se declaró otro, porque la corrección no mira los casos.
      Pruebas: `tests/test_asistente_revision_roles.py` 26 aprobadas (las 5 nuevas fallaban antes del cambio).
      Medido el 2026-11-03 con esos 12 casos: no pasa (ver «T8, 2026-11-03» abajo), y esos casos ya orientaron el diagnóstico.
      Conjunto nuevo, 2026-11-19: `docs/REVISION_ROLES_CASOS_047b.json`, 12 casos sintéticos del maestro (6 sanos y 6 con un
      defecto cada uno: física por cortocircuito, coste por suma incompleta y por anualidad, riesgo por carga crítica sin
      respaldo y por maniobra en un nodo sin equipo, fuentes de otro alimentador), nombres opacos, escrito sin mirar los
      dictámenes del 03-11 y declarado antes de medir con huella sha256
      `54f2a035bc7c173d87830a5faaf2e5fdca79851df448abb854efff60e2f4e910` (2026-11-19), la misma en el fichero y en la
      herramienta. `--conjunto` elige el conjunto, su huella va al informe y uno con otra huella o sin declarar no se mide
      (RF-43). Pruebas: `tests/test_revision_conjunto_047b.py`, con un cliente LLM falso.
      Bloqueada por la medida en su turno de GPU con el conjunto 047b (huella `54f2a035…f2e4e910`). Siguiente acción:
      `tools/asistente_comparar_revision.py --modelo qwen3:8b --conjunto docs/REVISION_ROLES_CASOS_047b.json --salida docs/asistente/COMPARACION_REVISION_047_T8b.json`
      (pide la GPU). Se cierra con 0 falsas alarmas, 0 perdidos y 0 sin respuesta en los dos modos.
      Medida del 047b, 2026-11-21 (bloque de GPU, `qwen3:8b`, tope 512, huella `54f2a035…f2e4e910`): **no pasa**. Rol
      único 5 de 6 defectos, 1 perdido, 2 falsas alarmas, 1 sin respuesta; equipo 4 de 6, 1 perdido, 2 falsas alarmas,
      4 sin respuesta (7 intervenciones). Diagnóstico por clases de error, leyendo los dictámenes del informe (MEJ24):
      (1) todas las «sin respuesta» son «favorable» con listas pendientes, que RF-40 anula: el encargo no decía que con
      algo pendiente la decisión no puede ser favorable; (2) las restricciones deterministas viajaban en la propuesta y
      el modelo las tomaba por datos sin evidencia; (3) el modelo apuntaba como contradicción lo que coincide («9 500»
      frente a 9500, «no hay contradicción») y como incertidumbre la acción o un campo suelto; (4) en la segunda ronda
      del equipo los cuatro roles copiaban las dudas de los otros; (5) el perdido, en los dos modos, era de fuentes con
      la evidencia de otro alimentador: el encargo pedía «el mismo valor», no «el mismo elemento»; (6) la media de
      salida (unos 90 a 160 tokens) no llega al tope, pero el informe no decía cuántas intervenciones llegaron a él.
      Corrección, en el encargo y no en la puerta (RF-44 a RF-47): regla explícita de «nunca favorable con algo
      pendiente», restricciones deterministas fuera del mensaje al LLM (el código las sigue aplicando), regla de mismo
      valor con otro formato y de lo confirmado fuera de las listas, segunda ronda sin copiar, fuentes del mismo
      elemento y coste total; tope por omisión 1024, con el tope, la intervención más larga, las que llegan al tope y lo
      que devolvió el modelo en cada dictamen no válido en el informe. RF-40 y la puerta no cambian. Pruebas, con dobles
      y sin LLM: `tests/test_asistente_revision_roles.py` y `tests/test_revision_conjunto_047c.py`.
      Conjunto nuevo, 2026-11-21: el 047b ya orientó este diagnóstico, así que la medida se hace con
      `docs/REVISION_ROLES_CASOS_047c.json`, 12 casos sintéticos del maestro (6 sanos y 6 con un error cada uno: física
      por sobretensión en valle y por sobrecarga tras una transferencia, coste por precio unitario por cantidad, riesgo
      por pérdida de coordinación de un fusible, fuentes por la evidencia de otro transformador y por un número de
      usuarios distinto), sin repetir propuestas ni evidencias del 047 ni del 047b, nombres opacos, con las mismas reglas
      de declaración que el 047b y declarado antes de medir con huella sha256
      `04f19184a45fed27966a880bd0f89a23d819db6836da22f13e3ab79ecd618d88` (2026-11-21), la misma en el fichero y en la
      herramienta. Lo escribió quien corrigió el encargo: es una limitación declarada; por eso reparte los errores de
      otra forma y trae clases que el encargo no nombra (sobretensión, coordinación de protecciones).
      Siguiente acción (cola de GPU de d8, con Ollama y `qwen3:8b`):
      `tools/asistente_comparar_revision.py --modelo qwen3:8b --conjunto docs/REVISION_ROLES_CASOS_047c.json --tokens 1024 --salida docs/asistente/COMPARACION_REVISION_047_T8c.json`.
      Se cierra con 0 falsas alarmas, 0 perdidos y 0 sin respuesta en los dos modos; si no, se diagnostica de nuevo y
      la medida siguiente usa otro conjunto declarado antes.
      Medida del 047c, 2026-11-21 (bloque de GPU, `qwen3:8b`, tope 1024, huella `04f19184…ecd618d88`): **no pasa**.
      Rol único 6 de 6, 0 perdidos, 5 falsas alarmas, 0 sin respuesta; equipo 5 de 6, 0 perdidos, 2 falsas alarmas,
      5 sin respuesta. Ninguna intervención llegó al tope (243 tokens la más larga). Causa, en los dictámenes: el
      modelo apunta como contradicción comprobaciones cuyos dos valores coinciden. Sigue en la T10 (RF-48 a RF-51).

## Evidencia de ejecución

- [ ] T7. Destilar el LLM generativo con fuentes reales y verificar su ejecución local. (RF-8, RF-9, RF-11, RF-14, RF-15, RF-19, RF-20)
      Hecho cuando: las pruebas de `tests/test_llm_destilacion.py` pasan, el corpus conserva fuentes reales y particiones sin fuga, se completa ajuste QLoRA CUDA con pérdida solo de respuesta, se comparan base/checkpoints por selección, se reabre/exporta la versión exacta y se evalúan las 200 propuestas nuevas más casos humanos separados; la integración conserva confirmaciones y solo activa una versión aprobada.

- [x] T7a. Volver a sellar el corpus reubicado con el prompt vigente, a través de su custodia. (RF-57, RF-58)
      Hecho cuando: `tests/test_resellado_custodia_llm.py` pasa y `tools/llm_destilar.py sellar --custodia <manifiesto>
      --destino <nuevo>` resella o dice qué fuente rechaza y por qué.
      Evidencia, 2026-11-21 (MEJ29): `resellar_con_custodia` en `asistente/llm_destilacion.py` lee la custodia con
      `leer_custodia`, resuelve cada fuente por su resolución con su sha256 y sus bytes, escribe la ruta resuelta, rehace
      `record_id` y `dataset_hash` y sella con `sellar_particiones`; el rastro va en `resellado` y los pares de
      `record_id`, custodiados, en `resellado_record_ids.json`. Las seis pruebas nuevas fallaban por aserción con el
      manifiesto reutilizado tal cual. Ensayo de solo lectura sobre el corpus reubicado del 065: 11 de 11 fuentes casan
      por sha256. El sellado v6 real lo corre la cola de GPU (paso `sellar_v6`); no cierra la T7.

- [x] T7b. Elegir y abrir la prueba con las tareas del sellado, y decir las que el sellado no cubre. (RF-60, RF-61)
      Hecho cuando: `tests/test_elegir_tareas_selladas_llm.py` pasa y `tools/llm_destilar.py elegir --informe … --dataset
      <corpus sellado> --destino …` elige con las tareas del manifiesto.
      Evidencia, 2026-11-21 (MEJ29b): `tareas_selladas` y `no_cubiertas_por_el_sellado` en `asistente/llm_destilacion.py`;
      `elegir_version_llm` pide el manifiesto (`--dataset` en la orden) y `evaluar_version_llm` comprueba las tareas de la
      elección antes de abrir la prueba. Las seis pruebas nuevas fallaban por aserción con el esbozo. Ensayo sobre el
      informe real de selección del v6, escrito fuera del repo: elige `csg-alumno:t7-v6` con 27 tareas selladas y declara
      40 tareas no cubiertas. La elección y la prueba reales las corre la cola de GPU; no cierra la T7.

- [x] T7d. Corpus v7 de órdenes con las 67 tareas del contrato vigente, sellado antes de entrenar. (RF-69, RF-70, RF-71, RF-72, RF-73, RF-74)
      Hecho cuando: `tests/test_corpus_contrato_llm.py` pasa y `tools/llm_destilar.py preparar-contrato --base <v6>
      --destino <fuente_v7>` seguido de `sellar --dataset <fuente_v7> --destino <corpus_v7>` deja un corpus que cubre las
      67 tareas en las cuatro particiones, sin nombres reales y con el prompt `llm_destilado_v2`.
      Evidencia, 2026-11-21 (MEJ34): `asistente/corpus_contrato_llm.py` parte de los contextos del v6 (sin abrir sus
      particiones), seudonimiza los valores, copia las 11 fuentes a su custodia por sha256 y redacta con las columnas del
      maestro (`CURRICULO_CONTRATO` para las 38 tareas posteriores a la 069). Corpus real sellado fuera del repositorio,
      en la carpeta de la tarjeta MEJ34: 3.280/201/134/402 (48, 3, 2 y 6 por tarea), 67 tareas en cada
      partición, 344 filas con ruta sintética declarada, 43 órdenes humanas reservadas, 0 nombres con el detector de la
      entrega, prompt `0cd40aa4…`, `dataset_hash` `b5490ab6…`; preparación en 27 s de CPU, sin GPU ni llamadas a modelos.
      Rojo: las doce pruebas nuevas fallan por aserción (ocho `AssertionError`, cuatro `DID NOT RAISE`) con el esbozo
      del v6 con `TAREAS_HASTA_069`, sin seudónimos, sin custodia propia, sin orígenes ni apartadas; verde con sus vecinas.

- [ ] T7c. Reentrenar en GPU el alumno con el corpus v7 y medirlo en su selección y su prueba sellada. (RF-8, RF-9, RF-19, RF-20, RF-59, RF-69)
      Hecho cuando: `tools/asistente_qlora.py entrenar` termina sobre el corpus v7 sellado con `--experimento-autorizado
      047-T7`, se exporta y publica la versión, `llm_destilar.py evaluar --parte seleccion`, `elegir --dataset <corpus v7>` (RF-60) y `evaluar --parte
      prueba` dan sus informes con el perfil `llm_destilado_v2` y las 67 familias, y la decisión de uso sale de esas
      cifras (no del plan). Las órdenes exactas están en el traspaso de la tarjeta MEJ34.

T6: 200 propuestas únicas, 27 tareas, 54 familias; auditoría sin solapamiento de
texto/grupo con entrenamiento. Evaluación local Llama3.1:8b: 157/200 tareas,
F1 0,864646; humanas 2/3 por separado. Uso asistido **rechazado por calidad**,
sin activación ni escrituras nativas. El cierre de la tarea de evaluación no
acredita aceptación del agente. [Informe y pendientes](../../docs/ACEPTACION_INTEGRAL_AGENTE_2026-10-31.md).

Continuación T6: selección Qwen3:8b de una etapa (22/27) frente a dos etapas
(21/27), sin pensamiento, digest fijado. Evaluación completa de 200 propuestas:
188 tareas correctas (0,94), F1 0,9393939394; humanas 2/3 por separado. Continúa
RECHAZADO por las puertas de calidad. Informe `evaluacion_qwen3/resultado.json`
publicado y releído mediante HTTP local real, sin activar pesos ni escrituras nativas.
Regresión de los archivos existentes del asistente y sus contratos: 183 aprobadas,
cero fallos/errores/omisiones (`asistente_regresion_completa.xml`). No cierra T1–T4.

T5: seis entrenamientos CUDA, semilla elegida por selección, recarga en proceso nuevo,
prueba separada y diagnóstico híbrido de las 27 tareas. Candidato bloqueado, sin
promoción. [Metodología y evidencia](../../docs/DESTILACION_AGENTE_2026-10-31.md).
Las tareas T1–T4 conservan pendientes reales; no se cierran por este entrenamiento.

T7, 2026-11-01: corpus real sellado de 1.734/54/54/200 registros; auditoría
contra 11 archivos y 96 contextos, tres órdenes humanas reservadas. Validación
final: 54 aprobadas, incluidas trazabilidad y procedencia con archivos reales.
Regresión adicional del intérprete/esquema/tareas/web/aceptación: 70 aprobadas,
sin fallos/errores/omisiones y con almacenamiento de prueba aislado.
La base NF4 se exportó, convirtió, cuantizó e importó sin activarla; su selección
anterior de 54 casos obtuvo 7 tareas correctas y F1 0,1. El primer ajuste generativo
completo solicitado falló con error Windows 1455 antes de acreditar pasos o pesos.
El segundo intento con el código revisado fue rechazado antes de cargar Torch por
memoria comprometible de 2,00 GiB frente al mínimo de 8 GiB. Registro y API web
releídos: QLoRA `ERROR_ENTORNO`, sin activo y `complete=false`.
No se cierran entrenamiento, aceptación ni integración por estos resultados.
[Evidencia, comandos y continuación](../../docs/DESTILACION_LLM_REAL_2026-11-01.md).
La sincronización del ciclo entre familias queda exigida por la nueva spec 050,
sin atribuirla a la mera existencia del coordinador.

Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

T2, 2026-11-02, Fase 1 (código y pruebas sintéticas, reranker falso inyectado, sin GPU ni modelos cargados): `tests/test_asistente_reranker.py` falló antes del cambio (30 de 40) y pasa después; `test_asistente_indice`, `test_asistente_embeddings`, `test_asistente_web`, `test_capas`, `test_inventario` y `test_trazabilidad_specs` en verde, por fichero. `tools/asistente_evaluar_rag.py --solo-conjunto`: 76 preguntas sintéticas del maestro (66 con respuesta, 6 de ellas de código, y 10 sin respuesta), ninguna sin ancla, SHA-256 `88245a0755bac8813968dee64a03a22778168d8a6aec9d21e813f73a0ff5c36a`. **T2 sigue abierta:** falta la Fase 2, medición real en CUDA con `tools/asistente_evaluar_rag.py`; sin su informe ningún reranker entra en producción (RF-27) y no se acredita mejora alguna. El conjunto no acredita 027:RF-42.

T2, 2026-11-02, Fase 2 (medición real en CUDA, revisión 05eee54d con la Fase 1; conjunto sintético del maestro sin cambiar, SHA-256 `88245a07…5c36a`, 76 preguntas: 66 con respuesta y 10 sin ella; vectores `nomic-embed-text` de los 5319 trozos). Informe: `docs/EVALUACION_RAG_047.json`. MRR@10 / Recall@10 / p95: BM25 0,553 / 0,753 / 20 ms; híbrido 0,565 / 0,788 / 24 ms; `BAAI/bge-reranker-v2-m3` 0,771 / 0,908 / 492 ms; `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` 0,786 / 0,905 / 168 ms. Decisión de la política declarada: híbrido adoptado; reranker adoptado, mmarco (frente a híbrido +0,221, IC95 % 0,133 a 0,314; frente a BM25 +0,233, IC95 % 0,135 a 0,335). Es un conjunto sintético: no acredita 027:RF-42.

**T2 sigue abierta: abstención.** Acierto al abstenerse: BM25 3 de 10; híbrido y rerankers 0 de 10. El coseno cruza `UMBRAL_COSENO` en las 10 preguntas sin respuesta, BM25 en 7. Por la vía real, «¿cuál es la capital de Mongolia?» responde con citas verificadas de `estructura.py`: el fragmento existe, pero no responde, y eso incumple RF-18 de la 026 y la abstención de RF-3. La política de adopción no incluía la abstención y no se cambia tras ver las cifras. Siguiente acción: calibrar la abstención con un conjunto nuevo y separado, declarado antes de medir, sin usar este; después repetir esta medición.

T2, 2026-11-02, abstención calibrada (RF-31 a RF-37), con los conjuntos y la puerta confirmados antes de medir (`8828ca5f`) y los umbrales antes de abrir el sellado (`34fdfd09`). Solo mmarco. Calibración, `docs/CALIBRACION_ABSTENCION_047.json`: reranker −0,909; BM25 12,386 o coseno 0,766; BM25 solo 12,386. Medición única del sellado (40 con respuesta, 40 sin ella), `docs/EVALUACION_ABSTENCION_047.json`; abstención, Recall@10 y MRR@10 con la puerta (Recall@10 y MRR@10 sin ella entre paréntesis): reranker 0,950, 0,950 (0,950), 0,938 (0,938), **cumple**; híbrido 0,925, 0,800 (0,925), 0,673 (0,746), **no cumple**; BM25 0,950, 0,750 (0,900), 0,652 (0,730), **no cumple**. Ninguno baja de 0,90 en abstención; sin reranker se pierden respuestas: híbrido 5 de 40 y BM25 7 de 40 dicen «No lo sé» teniendo respuesta en el índice. Fallos del reranker: respondió 2 de 40 sin respuesta («¿cómo se leen los medidores a distancia por la línea eléctrica?» y «¿qué potencia tiene la SED XQ7741?»).

**T2 sigue abierta:** el plan declaró que se cierra solo si los tres métodos cumplen, y no se recalibra con lo visto en el sellado. La decisión de aceptar esa pérdida sin reranker corresponde al responsable, no a esta medición. El conjunto es sintético: no acredita 027:RF-42.

T1, T3 y T4, 2026-11-03, revisión base `ede5dc93`, sin GPU (`CUDA_VISIBLE_DEVICES=-1`), sin Ollama ni DIgSILENT, en `tests/`, por fichero y con `-rs`. Salida estructurada 109, intérprete 5, Ollama 10, tareas 4, revisión por roles 14, web 13, equipo 26, equipo web 5, aceptación 28, ajuste condicionado 19, QLoRA 5: todas aprobadas, ninguna omitida. El revisor de las pruebas de T3 es de prueba: no acredita la calidad de ningún LLM.

**T1, cerrada.** Lo que faltaba de RF-2, hallado probando el resolutor tarea por tarea: un código vecino (102 por 101) daba un plan listo sobre otra entidad, sin una duda, y una SET sin contexto salía lista en lo que escribe. Falla antes del cambio y pasa después; entrada en `docs/regresiones/2026-11-03-codigo-vecino-en-el-plan.md`. RF-1 y RF-10 ya estaban hechos: se añadieron solo las pruebas que el plan nombra.

**T3 sigue abierta, solo por la comparación real.** RF-5 a RF-7 tienen código y pruebas. Añadido a lo que ya había: encargo propio de cada rol, esquema en `schemas/revision_propuesta_v1.schema.json`, la segunda ronda ve los dictámenes de la primera, evidencia sin proyecto ni fuente no acredita, presupuesto en `ollama.json`, propuesta final en el resultado. Los casos de la comparación quedan declarados antes de medir: `docs/REVISION_ROLES_CASOS_047.json`, 12 sintéticos del maestro (6 con defecto), huella del contenido `102bdfbf1c049c893aa5906594a1cc20503a1b5344a20dc62c905bb84a21ca6d`. No se midió: la GPU estaba reservada y había cerca de 1 GB de memoria libre.

**T4 sigue abierta.** `asistente/ajuste_condicionado.py` da `decidir_ajuste` y las puertas de 027:RF-18 sobre lo humano, y `decidir_aceptacion` las publica. `test_adaptador_reabre` reabre un adaptador PEFT en otro proceso con un modelo diminuto en CPU: prueba el contrato, no acredita la base NF4 ni el paso en CUDA. Decisión con la evidencia real publicada (último informe: 3 órdenes humanas medidas, 2 de 3 tareas; en el almacén ya hay 45 eventos y 43 órdenes únicas): **bloqueada**, porque son 3 de 200 órdenes reales y el informe no acredita huella ni independencia. El déficit de 188 de 200 es de propuestas: no habilita RF-8. T7 sigue por su autorización expresa de experimento (plan, T7), sin que esto la apruebe; por eso la exigencia no se conectó a su herramienta.

Sin ejecutar o sin completar en esta revisión, por la GPU oculta: `tests/test_asistente_transformer.py` (exige CUDA; aquí solo cambió de dónde toma sus puertas, con el mismo valor) y `test_opcion_sin_pedirla_las_confirmadas_solo_examinan` de `tests/test_validacion_cruzada_ordenes.py` (violación de acceso en `codificador_ordenes.py:311`, igual en `integracion/065` sin este cambio; las otras 57 aprueban). No es la suite completa.

T3, 2026-11-03, primera medición real, `qwen3:8b`: **no vale como evidencia**. Rol único 11 de 12 sin respuesta y equipo 12 de 12, con unos 505 de 512 tokens por intervención. Causa probable: el razonamiento del modelo agota el tope, sin confirmar con una respuesta capturada (`docs/regresiones/2026-11-03-revision-sin-respuesta-por-razonar.md`). La revisión pide ahora `think: false` y el informe guarda el motivo de cada respuesta no reconocida. T3 sigue abierta hasta repetir la medición.

T3, 2026-11-03, segunda medición, `qwen3:8b` sin razonamiento (corrección 39844656): responden los 12 casos en los dos modos. Rol único: 6 de 6 defectos hallados, 0 perdidos y **6 falsas alarmas de 6 sanos**, 124 s. Equipo: lo mismo (6, 0, 6), 481 s y unas cuatro veces los tokens. Conclusión: la revisión no discrimina, marca defecto en todo, y el equipo no mejora al rol único. Informe en `docs/asistente/COMPARACION_REVISION_047.json`; `autoriza_ejecucion` es falso. La T3 queda medida; la discriminación es la T8.

T8, 2026-11-03, medición tras corregir el encargo y el contrato del dictamen (`qwen3:8b`, 12 casos, huella `102bdfbf…`): **no pasa su puerta**. Rol único: 5 de 6 defectos, 1 perdido (el de riesgo), 3 falsas alarmas de 6 sanos, 0 sin respuesta, 123 s. Equipo: 5 de 6, 1 perdido, 5 falsas alarmas, 1 sin respuesta, 448 s. Informe en `docs/asistente/COMPARACION_REVISION_047_T8.json`. Mejora frente a la medición anterior, que marcaba defecto en todo, pero la T8 sigue abierta y estos 12 casos ya orientaron el diagnóstico: la próxima medida necesita un conjunto nuevo declarado antes de medir.
- [x] T9. Las puertas dicen el valor medido y los ejemplos, o que falta la métrica. (RF-42)
      Hecho cuando: `tests/test_entrenamiento_dataset_puertas.py` en verde.
- [ ] T10. Contradicciones estructuradas, decididas por el código, y medida con un conjunto nuevo. (RF-48, RF-49, RF-50, RF-51)
      Hecho cuando: `tools/asistente_comparar_revision.py --modelo qwen3:8b --conjunto docs/REVISION_ROLES_CASOS_047d.json --tokens 1024 --salida docs/asistente/COMPARACION_REVISION_047_T8d.json`
      da 0 falsas alarmas, 0 perdidos y 0 sin respuesta en los dos modos, con el informe en `docs/asistente/` y sin
      ajustar nada mirando esos casos; entonces se cierra también la T8.
      Código, 2026-11-21 (MEJ24b): el esquema pide cada contradicción como `{campo, valor_propuesta,
      valor_evidencia, fuente}` (RF-48); `revision_roles.filtrar_contradicciones` descarta, con su motivo, las que
      tienen los dos valores iguales con la unidad normalizada y una tolerancia relativa del 0,5 %, e interpreta las
      de texto libre «X vs Y» (RF-49); con algo descartado, la decisión sale de las listas que quedan y se guarda la
      devuelta, y el informe cuenta las descartadas y las recalculadas (RF-50); el encargo dice «anota solo los
      valores distintos» (RF-51). Pruebas, con dobles y sin LLM: `tests/test_revision_contradicciones.py` y
      `tests/test_revision_conjunto_047d.py`.
      Conjunto nuevo, 2026-11-21: el 047c orientó este diagnóstico y no vale para la aceptación, así que la medida es
      con `docs/REVISION_ROLES_CASOS_047d.json`, 12 casos sintéticos del maestro (6 sanos y 6 con un error cada uno:
      física por caída de tensión sobre el límite y por corriente sobre la capacidad del conductor, coste por precio
      unitario por cantidad y por precio por kilómetro, riesgo por usuarios sin enlace durante el corte, fuentes por
      una demanda que la evidencia da en otra unidad y con otro valor), sin repetir propuestas ni evidencias del 047,
      del 047b ni del 047c, nombres opacos, con las mismas reglas de declaración, declarado antes de medir con huella
      sha256 `2da22130778488aa9e2a71583e6799c30fb41ce403796a5d6261fbb1a50887cc` (2026-11-21), la misma en el fichero,
      en la herramienta y en la prueba. Lo escribió quien escribió la corrección: limitación declarada.
      Bloqueada por la medida en su turno de GPU (cola de d8, Ollama con `qwen3:8b`), con la orden de arriba.
      Medida del 047d, 2026-11-21 (bloque de GPU, `qwen3:8b`, huella `2da22130…1a50887cc`): **no pasa**. Rol único y
      equipo: 6 de 6 defectos, 0 perdidos, 5 falsas alarmas de 6 sanos; el equipo, 1 sin respuesta. Causa, en los
      dictámenes: cifras con marcas o dentro de una frase («>$14500», «_3_», «Cargabilidad máxima de A71 74 %»),
      valores inventados («user», «kOhm») y un total frente a un precio por unidad. Los defectos se «hallaban» con esos
      mismos valores inventados: el 0 perdidos no lo acredita. Sigue en la T11 (RF-52 a RF-56).
- [ ] T11. Contradicciones fundadas y por base, y medida con un conjunto nuevo. (RF-52, RF-53, RF-54, RF-55, RF-56)
      Hecho cuando: `tools/asistente_comparar_revision.py --modelo qwen3:8b --conjunto docs/REVISION_ROLES_CASOS_047e.json --tokens 1024 --salida docs/asistente/COMPARACION_REVISION_047_T8e.json`
      da 0 falsas alarmas, 0 perdidos y 0 sin respuesta en los dos modos, con el informe en `docs/asistente/` y sin
      ajustar nada mirando esos casos; entonces se cierran también la T10 y la T8.
      Código, 2026-11-21 (MEJ24c): `asistente/contradicciones.py` lee las cifras con sus marcas, prefijos y dentro de
      una frase, resuelve la cifra ambigua con el otro valor (RF-52), descarta como no fundada la contradicción cuyos
      valores no están en la propuesta o en la fuente citada (RF-53), toma el valor de la propuesta cuando el campo es
      suyo (RF-54), pide y comprueba la base y calcula la cuenta del total (RF-55) y no compara el texto de la acción
      (RF-56). Pruebas, con dobles y sin LLM: `tests/test_revision_contradicciones_fundadas.py` y
      `tests/test_revision_conjunto_047e.py`. Diagnóstico sin LLM, que no vale como medida: volver a filtrar con este
      código las contradicciones que el LLM devolvió en la medida del 047d deja 1 falsa alarma de 6 en cada modo y
      2 (rol único) y 3 (equipo) perdidos: los defectos que solo se «hallaban» con valores inventados.
      Conjunto nuevo, 2026-11-21: el 047d orientó este diagnóstico y no vale para la aceptación, así que la medida es
      con `docs/REVISION_ROLES_CASOS_047e.json`, 12 casos sintéticos del maestro (6 sanos y 6 con un error cada uno:
      física por tensión bajo el límite y por sobrecarga de una SED, coste por precio unitario por cantidad y por precio
      por kilómetro, riesgo por quedar sin respaldo durante una transferencia, fuentes por la evidencia de otro
      alimentador), con cifras escritas de formas distintas (miles con punto, coma o espacio, coma decimal, moneda
      delante, otra unidad) y precios por unidad, por kilómetro y totales en sanos y con error, sin repetir propuestas
      ni evidencias del 047 al 047d, nombres opacos, con las mismas reglas de declaración, declarado antes de medir con
      huella sha256 `649863d4f383978a1e1e62984a4aa7b95140a76c556078a057b667adae0ae5da` (2026-11-21), la misma en el fichero,
      en la herramienta y en la prueba. Lo escribió quien escribió la corrección: limitación declarada.
      Bloqueada por la medida en su turno de GPU (cola de d8, Ollama con `qwen3:8b`), con la orden de arriba.
      Medida del 047e, 2026-11-21 (bloque de GPU, `qwen3:8b`, huella `649863d4…adae0ae5da`): **no pasa**. 0 falsas
      alarmas en los dos modos, pero perdidos 3 de 6 (rol único) y 2 de 6 (equipo), 0 sin respuesta. Lo que el modelo
      sí vio acabó descartado por las reglas de la T11: una cuenta que citaba solo la fuente de la cantidad, un precio
      por km frente al total, y la base «unidad» que el modelo declaraba en «0,92 p.u.» o «124 %». Sigue en la T13.

- [x] T12. Órdenes revisadas por el maestro: registro sellado y decisión de ajuste mientras falten humanas. (RF-62, RF-63, RF-64, RF-65, RF-66, RF-67, RF-68)
      Hecho cuando: `tests/test_asistente_revisadas_maestro.py`, `tests/test_asistente_ajuste_condicionado.py`,
      `tests/test_aceptacion_agente.py` y `tests/test_asistente_qlora.py` pasan, y el conjunto de 200 queda sellado en
      `<almacén>/maestro_real/revisadas_047/` con `tools/asistente_ordenes_reales.py revisar-maestro`.
      Evidencia, 2026-11-21 (MEJ35, d8): `D:/csg/PM_IMPL/MEJ35_ORDENES/HANDOFF.md` (rojo por aserción sobre `7ed2c05d`,
      verde, órdenes con su huella y la cuenta de `decidir_ajuste` antes y después). 200 órdenes de las 67 tareas de
      `TAREAS` (3 por tarea y 2 en `conectar_nube`), redactadas por el maestro con los alias del repositorio y revisadas
      una a una por un revisor independiente de origen `maestro` (Claude en un contexto aparte): 196 aceptadas y 4
      rechazadas en la primera revisión; esas 4 y otras 7 observadas, corregidas por el autor y aceptadas en la segunda.
      Ninguna coincide en texto ni familia con las 45 humanas, las 899 del maestro de la 085 ni el entrenamiento de los
      corpus `asistente_integral_20261107c_integral` y `corpus_maestro_085_20261103`. Antes: «bloqueada», 3 órdenes reales
      de 200. Después, sin medir aún: «bloqueada» solo por «métricas ausentes», con base `maestro_revisadas`, 200
      revisadas, 3 humanas y 197 que faltan. **No cierra la T4:** su evaluación final en GPU es `aceptar_agente.py
      evaluar` con este conjunto, y la decisión que dé (`decision_ajuste.json`) es la que abre o no el QLoRA de la 043 T9.

- [ ] T13. Cuentas evaluadas por el código, precios por unidad pasados a total y coste comprobado sin el LLM, y medida con un conjunto nuevo. (RF-75, RF-76, RF-77, RF-78)
      Hecho cuando: `tools/asistente_comparar_revision.py --modelo qwen3:8b --conjunto docs/REVISION_ROLES_CASOS_047f.json --tokens 1024 --salida docs/asistente/COMPARACION_REVISION_047_T8f.json`
      da 0 falsas alarmas, 0 perdidos y 0 sin respuesta en los dos modos, con el informe en `docs/asistente/` y sin
      ajustar nada mirando esos casos; entonces se cierran también la T11, la T10 y la T8.
      Código, 2026-11-21 (MEJ24d): `contradicciones.evaluar_cuenta` evalúa cuentas por descenso recursivo y cada
      operando debe estar en las fuentes citadas (RF-75, RF-78); un precio por unidad o por km se multiplica por la
      cantidad anclada y la base la decide el texto (RF-76); `contradicciones.comprobar_coste` calcula el coste de la
      evidencia sin el LLM y una revisión que no cuadra no se aprueba (RF-77). Pruebas, con dobles y sin LLM:
      `tests/test_revision_cuentas_y_coste.py` y `tests/test_revision_conjunto_047f.py`. Diagnóstico sin LLM, que no
      vale como medida: con este código, la comprobación del coste halla los 9 defectos de coste del 047 al 047e sin
      ninguna falsa alarma, y volver a filtrar lo que devolvió el LLM en la T8e deja 0 falsas alarmas y 2 perdidos en
      cada modo, de riesgo y de fuentes (otro alimentador), que el modelo no vio.
      Conjunto nuevo, 2026-11-21: el 047e orientó este diagnóstico y no vale para la aceptación, así que la medida es
      con `docs/REVISION_ROLES_CASOS_047f.json`, 12 casos sintéticos del maestro (6 sanos y 6 con un error cada uno:
      coste por una partida que falta en la suma y por precio por km, física por sobrecarga tras una transferencia y
      por cortocircuito sobre la capacidad del interruptor, riesgo por trabajo en caliente prohibido, fuentes por una
      demanda distinta en otra unidad), con costes por partidas, por unidad, por km y totales en sanos y con error y
      cifras escritas de formas distintas, sin repetir propuestas ni evidencias del 047 al 047e, nombres opacos, con las
      mismas reglas de declaración, declarado antes de medir con huella sha256 `05c423913e4e49d4ebb370fd8d760f89e4cfb3319ce9001395dde08da33afea6`
      (2026-11-21), la misma en el fichero, en la herramienta y en la prueba. Lo escribió quien escribió la
      corrección: limitación declarada.
      Bloqueada por la medida en su turno de GPU (cola de d8, Ollama con `qwen3:8b`), con la orden de arriba.
      Medida del 047f, 2026-11-22 (bloque de GPU, `qwen3:8b`, tope 1024, huella `05c42391…afea6`): **no pasa**. Rol
      único 5 de 6, 1 perdido (riesgo, f06: nadie vio el trabajo en caliente prohibido), 1 falsa alarma (f07: el
      coste frente a cada partida). Equipo 6 de 6, 0 perdidos, 2 falsas alarmas (f05: «buzones» como incertidumbre
      cuando la acción dice «2 buzones», y una partida frente al total en la segunda ronda; f07: el coste frente a
      cada partida) y 1 sin respuesta (f12: riesgo «bloqueada» sin hallazgo). El código resolvió solo los dos
      defectos de coste (f02 y f10, `comprobaciones_fallidas` 2); el modelo, los de física y fuentes. El riesgo del
      equipo se «halló» por una contradicción de la acción que comparaba un 2 de su frase con 22,9 kV. Sigue en la T14.

- [ ] T14. El código decide el coste que comprobó, las dudas que fija la acción y el riesgo por prohibición, y medida con un conjunto nuevo. (RF-79, RF-80, RF-81, RF-82, RF-83)
      Hecho cuando: `tools/asistente_comparar_revision.py --modelo qwen3:8b --conjunto docs/REVISION_ROLES_CASOS_047g.json --tokens 1024 --salida docs/asistente/COMPARACION_REVISION_047_T8g.json`
      da 0 falsas alarmas, 0 perdidos y 0 sin respuesta en los dos modos, con el informe en `docs/asistente/` y sin
      ajustar nada mirando esos casos; entonces se cierran también la T13, la T11, la T10 y la T8.
      Código, 2026-11-22 (MEJ24e): con la comprobación del coste que cuadra, el LLM no decide ese campo (RF-79); una
      incertidumbre que es un campo fijado por la acción se descarta (RF-80); un dictamen no válido se pide de nuevo
      (RF-81); el encargo de riesgo incluye las prohibiciones de la evidencia, que van en incertidumbres (RF-82); la
      frase de la acción no se compara como cifra (RF-83). Pruebas, con dobles y sin LLM:
      `tests/test_revision_reglas_t13.py` y `tests/test_revision_conjunto_047g.py`. Diagnóstico sin LLM, que no vale
      como medida: volver a filtrar con este código lo que devolvió el LLM en la medida del 047f deja 0 falsas alarmas
      y 1 perdido en cada modo, el riesgo de f06, que el encargo nuevo pide y solo una medida puede comprobar.
      Conjunto nuevo, 2026-11-22: el 047f orientó este diagnóstico y no vale para la aceptación, así que la medida es
      con `docs/REVISION_ROLES_CASOS_047g.json`, 12 casos sintéticos del maestro con las clases del 047f (coste por
      precio unitario por cantidad y por precio por km, física por tensión bajo el límite y por sobrecarga de una SED,
      riesgo por una maniobra que el procedimiento prohíbe, fuentes por la evidencia de otro reconectador) y cifras
      escritas de otras formas (decimales con coma, moneda delante o detrás, «dólares», «/km», «cada una», miles con
      punto o espacio), sin repetir propuestas ni evidencias del 047 al 047f, nombres opacos, con las mismas reglas
      de declaración, declarado antes de medir con huella sha256 `6553d4ae2cdb29b228e56d209cebb15ce53c4ae823deb0d9e17628ed60b4ca8a`
      (2026-11-22), la misma en el fichero, en la herramienta y en la prueba. Lo escribió quien escribió la
      corrección: limitación declarada.
      Bloqueada por la medida en su turno de GPU (cola de d8, Ollama con `qwen3:8b`), con la orden de arriba.
