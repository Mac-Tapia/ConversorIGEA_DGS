# Tareas — Spec 050

- [x] T1. Contrato de la instantánea común: copia verificada, identidad por contenido, contexto 043 y bloqueo anotado. (RF-1, RF-2, RF-8)
      Hecho cuando: `tests/test_aprendizaje_continuo.py` prueba copia e idempotencia, otro contexto u otras versiones, fuente ausente o vacía, cambio durante la copia y copia tocada después.
      Hecho el 2026-11-03: `congelar_instantanea` y `verificar_instantanea` en `src/convertersmartgrid/aprendizaje_continuo.py`; `tools/aprendizaje_continuo.py congelar`.
- [ ] T1b. Instantánea real con los datos locales: dataset v2, vocabulario, búfer del gemelo, libro de cabeceras y corpus generativo sellado. (RF-1, RF-2, RF-8)
      Hecho cuando: existe el manifiesto local con copias verificadas de todos los datos requeridos y su `snapshot_id`, anotado aquí.
      Avance 2026-11-07: contexto multiproyecto con mapa de huellas 043 e identidad común implementado y probado. Falta preparar sus manifiestos reales y correr
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
      Avance 2026-11-07: GRU/PINN disponen de registro sin publicación individual y salida aislada; lenguaje v2 registra candidatos con puertas y reapertura sin activar. Comparación temporal conectada al conjunto por clase. Contratos verificados, sin acreditar una campaña real. Falta pasar `ciclo=` a `Vigilante` en `web/app.py`, conectar productores y ejecutar el cambio de datos real. Orden, con la GPU libre y RAM suficiente:
      `PYTHONPATH=src .venv/Scripts/python.exe tools/aprendizaje_continuo.py ciclo --contexto <ExperimentoSpec.json> --familias transformer,clasificador,gru,pinn,evolutivos,embeddings,qlora --politica-hash <huella 044> --tiempo-s 21600 --memoria-gib 12 --fuente ...` (las fuentes de T1b).
- [x] T4. Contrato de retención y publicación del conjunto: retención por contexto, evaluación conjunta sin empate, puntero único con anterior y relectura. (RF-5, RF-6, RF-7)
      Hecho cuando: las pruebas rechazan un contexto que retrocede o falta, un empate o un deterioro, un miembro sin puertas, sin reapertura o sin retención, un ciclo no terminado y un conjunto manipulado; y publicar, volver al anterior y `version_del_conjunto` se comprueban al releer sin tocar el registro individual.
      Hecho el 2026-11-03: `evaluar_retencion`, `evaluar_conjunto`, `publicar_conjunto`, `revertir_conjunto`, `conjunto_activo` y `version_del_conjunto`.
- [ ] T4b. Modelos reales entrenados en el ciclo de T3b, reabiertos y publicados como conjunto; los consumidores resuelven su versión desde él. (RF-5, RF-6, RF-7)
      Hecho cuando: modelos reales entrenados y reabiertos superan puertas individuales y conjuntas, y promoción y reversión se verifican por relectura.
      Avance 2026-11-07: lenguaje/PINN resuelven miembros verificados del conjunto; la competición multihorizonte de `temporal_entrenamiento.py` también compara contra su miembro GRU exacto, bloquea otra clase/familia ausente/corrupción y la publicación individual bajo conjunto. La reconstrucción de un paso en `temporal.py` no consume el artefacto multihorizonte de 046 y no se presenta como pronóstico. Contratos focales 153/153 en p19_temporal_conjunto_final2.xml. Faltan ciclo real completo, retención/evaluación conjunta con modelos auténticos, publicación/reversión por relectura y aceptación; esta tarea permanece abierta.
- [x] T5. Contrato del estado visible por CLI: las siete fases con versiones y motivos. (RF-10)
      Hecho cuando: `estado_aprendizaje` y `tools/aprendizaje_continuo.py estado` distinguen preparación, entrenamiento, selección, evaluación rechazada, publicación, activación y aceptación nativa pendiente.
      Hecho el 2026-11-03.
- [ ] T5b. Verificar el ciclo automático completo y sus estados en la web con una segunda captura real. (RF-4, RF-8, RF-9, RF-10)
      Hecho cuando: una segunda captura real demuestra deduplicación y actualización, con evidencia sin skips de funcionamiento y rechazo de regresiones, y la web muestra las fases en el navegador.
      Avance 2026-11-08: GET tipado `/api/asistente/aprendizaje` y panel adicional en la consola de desarrollo con las siete fases, motivos, versiones y bloqueos. POST tipado de cancelación compartido con la CLI: SHA canónico, marcador atómico, solicitud distinguida de terminación y diario publicado antes de trabajar. Integración del ciclo activo y cancelación durante la última etapa comprobadas con etapas ligeras de contrato. Datos corruptos se muestran como bloqueo y se conservan. Falta: T1b a T4b, cola automática cancelable, segunda captura real y comprobación en navegador; representación/API no cierran esta tarea. Se deriva interrupción ante propietario muerto/ausente y bloqueo ante marcador inválido, conservando el diario; relectura real rc73 y regresiones de representación verificadas. La creación del propietario y la campaña integral siguen pendientes.

## Evidencia y límites actuales

2026-11-08, P19 paralelo: productores y contraste obligatorios conectados antes de
construir etapas (dataset v2, consultas de embeddings, ventanas GRU, objetos PINN,
corpus generativo sellado y casos evolutivos declarados). Contexto documental separado
y con digests custodiados; contextos043 intactos. Vigilancia usa un plan declarativo
con hash y una solicitud común en JobManager, cancelación cooperativa y autoentrenamiento
apagado por defecto. Ausencia de plan no consume los avisos ni dispara modelos sueltos.
No se cierra T1b–T5b: el preflight de metadatos locales confirma faltantes de contexto,
procedencia050 y consultas reservadas; las nueve etiquetas humanas de informes conservan
7 train/0 validation/2 test y las 45 órdenes humanas 33/5/7. Sin reentrenar, copiar pesos/datasets,
GPU ni PowerFactory. El informe externo de entrega P19 identifica revisión, comandos,
pruebas enfocadas y pendientes; no representa aceptación científica/nativa ni producción.

2026-11-01: inspeccionados búfer/captura, oráculo, series, vigilancia, registro y
coordinador. Existen piezas de aprendizaje; no hay evidencia de aceptación de un
ciclo sincronizado integral. En 047 T7 se auditó el corpus real, pero el primer
ajuste generativo falló con error Windows 1455; no se produjeron pesos entrenados.
Estas observaciones justifican mantener todas las tareas abiertas.

2026-11-03: contrato del ciclo común en `aprendizaje_continuo.py` (T1 a T5), con 30 pruebas sin GPU
ni DIgSILENT. No hay entrenamiento real: las tareas «b» siguen abiertas y dicen qué falta y con qué orden.
