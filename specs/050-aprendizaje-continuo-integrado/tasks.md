# Tareas — Spec 050

- [x] T1. Contrato de la instantánea común: copia verificada, identidad por contenido, contexto 043 y bloqueo anotado. (RF-1, RF-2, RF-8)
      Hecho cuando: `tests/test_aprendizaje_continuo.py` prueba copia e idempotencia, otro contexto u otras versiones, fuente ausente o vacía, cambio durante la copia y copia tocada después.
      Hecho el 2026-11-03: `congelar_instantanea` y `verificar_instantanea` en `src/convertersmartgrid/aprendizaje_continuo.py`; `tools/aprendizaje_continuo.py congelar`.
- [ ] T1b. Instantánea real con los datos locales: dataset v2, vocabulario, búfer del gemelo, libro de cabeceras y corpus generativo sellado. (RF-1, RF-2, RF-8)
      Hecho cuando: existe el manifiesto local con copias verificadas de todos los datos requeridos y su `snapshot_id`, anotado aquí.
      Falta: decidir el contexto 043 de un ciclo que abarca varios proyectos (hoy `ContextoExperimento` es de un proyecto) y correr
      `CUDA_VISIBLE_DEVICES=-1 PYTHONPATH=src .venv/Scripts/python.exe tools/aprendizaje_continuo.py congelar --contexto <ExperimentoSpec.json> --fuente dataset=<almacén>/dataset --fuente vocabulario=<almacén>/vocabulario.json --fuente twin=<búfer> --fuente cabeceras=<libro> --fuente llm_dataset=<corpus de 047 T7>`.
- [x] T2. Contrato de las vistas por familia: partición por observación, cuarentena de etiquetas no nativas, replay sin fuga y propuestas con contraste. (RF-2, RF-3, RF-6, RF-9)
      Hecho cuando: las pruebas rechazan una partición distinta entre familias, una muestra de otra instantánea, una etiqueta del LLM, del maestro o de una predicción en PINN y GRU, un replay que mete una prueba vigente, y una propuesta sin contraste independiente o con autorrecompensa, conservando las rechazadas.
      Hecho el 2026-11-03: `Muestra`, `preparar_vistas` y `validar_propuestas`.
- [ ] T2b. Preparación real sobre la instantánea de T1b, con los productores de cada familia emitiendo `Muestra`. (RF-2, RF-3, RF-6, RF-9)
      Hecho cuando: la preparación real contrasta fuentes y etiquetas, y su resumen por familia, cuarentena y replay constan aquí.
      Falta: que `dataset_entrenamiento.py`, `temporal_entrenamiento.py` y el búfer del gemelo emitan un `observacion_id` común; hoy cada uno agrupa por su cuenta.
- [x] T3. Contrato del ciclo único sobre el coordinador y la vigilancia: idempotencia, presupuestos, prioridad del operador, cancelación y aportes por versión. (RF-4, RF-5, RF-8)
      Hecho cuando: las pruebas dan un ciclo por instantánea, posponen con trabajos del operador, bloquean sin memoria, con licencia nativa, con tiempo agotado, con una etapa sin candidato o con una promoción individual, cancelan entre etapas, y la vigilancia une gemelo y asistente en un solo ciclo.
      Hecho el 2026-11-03: `ejecutar_ciclo`, `cancelar_ciclo`, `decidir_ciclo`, `registrar_aportes` y `Vigilante.ciclo`; `tools/aprendizaje_continuo.py ciclo` usa las etapas de `tools/reentrenar_modelos.py` sobre las copias.
- [ ] T3b. Un cambio de datos real inicia el ciclo desde la web y las etapas no promueven por separado. (RF-4, RF-5, RF-8)
      Hecho cuando: con `CSG_AUTOENTRENAMIENTO=1` un dato nuevo real lanza un ciclo único y cancelable, y ningún trabajador cambia el modelo en uso durante él.
      Falta: los trabajadores de GRU (`temporal_entrenamiento.py`) y PINN (`oraculo.py`) promueven al terminar; el ciclo lo detecta y se bloquea, pero dentro del ciclo deben solo registrar su candidato. Falta también pasar `ciclo=` a `Vigilante` en `web/app.py` cuando se decida el contexto de T1b. Orden, con la GPU libre:
      `PYTHONPATH=src .venv/Scripts/python.exe tools/aprendizaje_continuo.py ciclo --contexto <ExperimentoSpec.json> --familias transformer,clasificador,gru,pinn,evolutivos,embeddings,qlora --politica-hash <huella 044> --tiempo-s 21600 --memoria-gib 12 --fuente ...` (las fuentes de T1b).
- [x] T4. Contrato de retención y publicación del conjunto: retención por contexto, evaluación conjunta sin empate, puntero único con anterior y relectura. (RF-5, RF-6, RF-7)
      Hecho cuando: las pruebas rechazan un contexto que retrocede o falta, un empate o un deterioro, un miembro sin puertas, sin reapertura o sin retención, un ciclo no terminado y un conjunto manipulado; y publicar, volver al anterior y `version_del_conjunto` se comprueban al releer sin tocar el registro individual.
      Hecho el 2026-11-03: `evaluar_retencion`, `evaluar_conjunto`, `publicar_conjunto`, `revertir_conjunto`, `conjunto_activo` y `version_del_conjunto`.
- [ ] T4b. Modelos reales entrenados en el ciclo de T3b, reabiertos y publicados como conjunto; los consumidores resuelven su versión desde él. (RF-5, RF-6, RF-7)
      Hecho cuando: modelos reales entrenados y reabiertos superan puertas individuales y conjuntas, y promoción y reversión se verifican por relectura.
      Falta: la GPU, y que `modelos_en_uso.py`, `oraculo.py` y `temporal.py` lean `version_del_conjunto` en vez de su puntero individual.
- [x] T5. Contrato del estado visible por CLI: las siete fases con versiones y motivos. (RF-10)
      Hecho cuando: `estado_aprendizaje` y `tools/aprendizaje_continuo.py estado` distinguen preparación, entrenamiento, selección, evaluación rechazada, publicación, activación y aceptación nativa pendiente.
      Hecho el 2026-11-03.
- [ ] T5b. Verificar el ciclo automático completo y sus estados en la web con una segunda captura real. (RF-4, RF-8, RF-9, RF-10)
      Hecho cuando: una segunda captura real demuestra deduplicación y actualización, con evidencia sin skips de funcionamiento y rechazo de regresiones, y la web muestra las fases en el navegador.
      Falta: T1b a T4b; la web aún no tiene ruta ni vista del estado del aprendizaje.

## Evidencia y límites actuales

2026-11-01: inspeccionados búfer/captura, oráculo, series, vigilancia, registro y
coordinador. Existen piezas de aprendizaje; no hay evidencia de aceptación de un
ciclo sincronizado integral. En 047 T7 se auditó el corpus real, pero el primer
ajuste generativo falló con error Windows 1455; no se produjeron pesos entrenados.
Estas observaciones justifican mantener todas las tareas abiertas.

2026-11-03: contrato del ciclo común en `aprendizaje_continuo.py` (T1 a T5), con 30 pruebas sin GPU
ni DIgSILENT. No hay entrenamiento real: las tareas «b» siguen abiertas y dicen qué falta y con qué orden.
