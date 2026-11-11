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

- [ ] T4. Evaluación real y ajuste condicionado. (RF-8, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_ajuste_condicionado.py tests/test_asistente_qlora.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan.
      Falta: carga cuantizada y un paso en CUDA con la revisión fijada, con su VRAM y la reapertura del adaptador real; exigir `decidir_ajuste` en `tools/asistente_qlora.py`, junto con T7; y la evaluación final con 200 órdenes reales.

- [x] T5. Destilación reproducible del maestro de sesión y ensayo del alumno. (RF-11, RF-12, RF-13, RF-14, RF-15)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_destilacion_integral.py tests/test_evaluacion_modelos.py` pasa, se ejecuta entrenamiento CUDA real con comparación supervisado/destilado, reapertura en proceso nuevo y ensayo del intérprete/plan; se informa por separado cualquier bloqueo de promoción por datos humanos.

- [x] T6. Auditar, materializar y evaluar 200 propuestas únicas, sin fuga y con puertas por alcance. (RF-13, RF-16, RF-17, RF-18)
      Hecho cuando: pruebas de `tests/test_aceptacion_agente.py` y regresiones de órdenes fijas/intérprete pasan; se ejecutan selección local de configuración y evaluación sellada de las 200 propuestas, con informe de métricas/errores/bloqueos y sin escrituras nativas.

- [ ] T8. Que la revisión distinga una propuesta sana de una con defecto antes de autorizar nada. (RF-5, RF-6, RF-38, RF-39, RF-40, RF-41)
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
      Falta: medir con `tools/asistente_comparar_revision.py --modelo qwen3:8b --salida docs/asistente/COMPARACION_REVISION_047_T8.json`
      (pide la GPU). Se cierra con 0 falsas alarmas, 0 perdidos y 0 sin respuesta en los dos modos.

## Evidencia de ejecución

- [ ] T7. Destilar el LLM generativo con fuentes reales y verificar su ejecución local. (RF-8, RF-9, RF-11, RF-14, RF-15, RF-19, RF-20)
      Hecho cuando: las pruebas de `tests/test_llm_destilacion.py` pasan, el corpus conserva fuentes reales y particiones sin fuga, se completa ajuste QLoRA CUDA con pérdida solo de respuesta, se comparan base/checkpoints por selección, se reabre/exporta la versión exacta y se evalúan las 200 propuestas nuevas más casos humanos separados; la integración conserva confirmaciones y solo activa una versión aprobada.

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
