# Tareas — Spec 047

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Esquema de salida y entidades del contexto activo. (RF-1, RF-2, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_salida_estructurada.py tests/test_asistente_interprete.py tests/test_asistente_ollama.py tests/test_asistente_tareas.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Recuperación híbrida con reranker contrastado. (RF-3, RF-4, RF-21 a RF-30)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_reranker.py tests/test_asistente_indice.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Revisión por roles acotada y trazable. (RF-5, RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_revision_roles.py tests/test_asistente_tareas.py tests/test_asistente_web.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4. Evaluación real y ajuste condicionado. (RF-8, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_ajuste_condicionado.py tests/test_asistente_qlora.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan.

- [x] T5. Destilación reproducible del maestro de sesión y ensayo del alumno. (RF-11, RF-12, RF-13, RF-14, RF-15)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_destilacion_integral.py tests/test_evaluacion_modelos.py` pasa, se ejecuta entrenamiento CUDA real con comparación supervisado/destilado, reapertura en proceso nuevo y ensayo del intérprete/plan; se informa por separado cualquier bloqueo de promoción por datos humanos.

- [x] T6. Auditar, materializar y evaluar 200 propuestas únicas, sin fuga y con puertas por alcance. (RF-13, RF-16, RF-17, RF-18)
      Hecho cuando: pruebas de `tests/test_aceptacion_agente.py` y regresiones de órdenes fijas/intérprete pasan; se ejecutan selección local de configuración y evaluación sellada de las 200 propuestas, con informe de métricas/errores/bloqueos y sin escrituras nativas.

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
