# Plan — Spec 050

La petición del usuario autoriza continuar la implementación integral según SPEC.
Se conserva el trabajo de 047 T7: la memoria insuficiente no se resuelve declarando
un alumno ya entrenado. Primero se exige una ejecución generativa local válida.

## Arquitectura y situación comprobada

| Responsabilidad | Código existente | Brecha que debe cerrarse |
| --- | --- | --- |
| Evidencia nativa y captura | `digital_twin/episode.py`, `buffer.py`, `integration.py` | Instantánea común y trazabilidad entre familias |
| Planificación y lenguaje | `asistente/interprete.py`, `plan.py`, `ollama.py` | Alumno generativo entrenado y evaluación conjunta |
| Preparación desde referencia | `asistente/llm_destilacion.py` | Disparador por cambio validado, no por texto autogenerado |
| PINN/GNN y aprendizaje activo | `digital_twin/oraculo.py`, `escenarios.py`, servicios del gemelo | Coordinar dominio, revisión y publicación con las demás familias |
| RNN/GRU y series | `digital_twin/temporal.py`, `series_causales.py` | Misma instantánea, fecha de corte y evaluación causal |
| Evolutivos/PNL | `digital_twin/evolutivo.py`, spec 048 | Vincular propuestas a versiones y evidencia nativa |
| Recuperación | `asistente/indice.py`, spec 047 T2 | Benchmark real del reranker y versión de corpus |
| Entrenamiento y registro | `training_coordinator.py`, `model_registry.py`, `tools/reentrenar_modelos.py` | Incluir alumno T7 y publicación conjunta coherente |
| Disparador automático | `asistente/vigilancia.py`, spec 027 | Un ciclo idempotente común y cancelable, no entrenamientos independientes |

No duplicar estas piezas ni declarar resuelto un adaptador por mapear su nombre
a GRU. Mantener bloqueos explícitos de NHITS/TFT/PatchTST hasta su implementación
en 046. El coordinador actual ordena siete etapas; ordenar no demuestra que todas
compartan datos, contextos o versiones compatibles.

## Secuencia de implementación

### Contratos de integración concretados el 2026-11-07

RF-1/T1b: un ciclo de varios proyectos usa un mapa ordenado de identidad de proyecto
a huella de su contexto 043. `ContextoExperimento` conserva su contrato individual.
`crear_contexto_ciclo(proyectos)` devuelve un manifiesto con esquema, mapa y huella
agregada; se conserva en la instantánea y se comprueba al releerla. No se inventa un
proyecto único. Cada muestra conserva su contexto individual, que debe pertenecer
al mapa declarado. Cambiar un miembro cambia la identidad de la instantánea.
Las capturas de varios proyectos usan esquema de instantánea v2: quitar el mapa
se detecta; las capturas v1 conservan su identidad y lectura originales.

RF-2/T2b: `crear_observacion_id(contexto_hash, fuente_hash, registro_id, instante)`
calcula la identidad sin familia, partición ni snapshot. El instante exige zona
horaria explícita y se normaliza a UTC; no se presume la zona de la máquina.
Los productores usan la misma referencia a la observación fuente, nunca el hash
de su etiqueta o representación como sustituto. Una repetición idéntica de un
registro no aumenta su peso. Una identidad de registro con contenido incompatible
bloquea y se conserva para revisión; el replay no incorpora pruebas al entrenamiento.
Estos contratos no cierran T1b/T2b sin la preparación sobre fuentes reales.

RF-4/RF-7: `publicar_individual=False` en PINN y competición temporal registra el
candidato y su aprobación individual sin cambiar punteros. Los CLI admiten
`--sin-publicar`. El estado terminal de la decisión conserva el vocabulario 043;
`promovido=False` y `publicacion_pendiente=True` distinguen la activación pendiente.
El ciclo GRU usa la competición actual, con cadencia y horizontes declarados,
sin repetir algoritmos. Sus modelos salen a una carpeta de ejecución; la PINN
recibe una copia verificada del búfer para escribir índice/modelos sin alterar la
instantánea. También se comprueba la instantánea al terminar las etapas.
Semillas, zona horaria, cadencia, horizontes y modelo de embeddings entran en la
identidad de la captura mediante `parametros_ciclo`. Un preflight sin memoria
permanece bloqueado y reintentable antes de entrenar; no sella como hecho el ciclo.

El ajuste de lenguaje sobre dataset v2 registra ahora candidatos aislados y reabre
sus pesos en un proceso nuevo, usando el mismo contrato del consumidor. Selecciona
solo con validation; test queda reservado para evaluación. Las órdenes humanas se
miden solo con gold_human: un episodio gold_native no cuenta como una orden del
operador. Informes y órdenes tienen vistas separadas. Exige las puertas de órdenes (tarea, F1 y reales) o de
subtipo de informes, y no retroceder frente al modelo en uso sobre la misma prueba.
Sin prueba real, medida válida o recarga correcta se conserva un candidato rechazado.
En órdenes reutiliza además decidir_promocion del protocolo integral: cobertura
de todas las tareas, referencia por tarea y rechazo de mensajes reservados; los
promedios no sustituyen esas puertas. El constructor incorpora informes.jsonl:
confirmados/corregidos son humanos; generados son contexto y maestro queda en
cuarentena. Etiquetas humanas contradictorias del mismo texto se conservan en
cuarentena con motivo, sin elegir según el orden de llegada.
El runner pasa el registro común explícitamente; `PROMOVIDO` en la decisión del
registro acredita puertas, mientras `promovido=false` y `publicacion_pendiente`
conservan la activación para el conjunto. Falta ejecutar el entrenamiento y su
evaluación funcional con datos reales; las pruebas de contrato no los acreditan.

RF-7: los nuevos conjuntos usan esquema v2 y su identidad cubre miembros,
instantánea, ciclo, retención y evaluación conjunta. Los v1 conservan su lectura
y bytes, con el alcance de integridad anterior. Una familia ausente de un conjunto
configurado bloquea, sin recurrir a un puntero individual. `miembro_del_conjunto`
resuelve el candidato por su SHA-256 exacto entre los registros declarados de la
familia 043 y verifica sus artefactos; así GRU puede referenciar
`pronostico_cabecera` sin fingir otro registro. No se publica un conjunto vacío.
La reversión comprueba el manifiesto destino antes de cambiar el puntero vigente.

Consumidores: lenguaje y PINN consultan el miembro del conjunto antes del puntero
individual. La materialización común del registro verifica todos los artefactos,
incluida una copia ya existente; no reescribe el puntero heredado ni mueve el
original. PINN conserva una carpeta local identificada por el SHA-256 del candidato
para que la carga y sus metadatos de herencia usen la misma identidad. Las acciones
individuales de lenguaje/provisional/reversión y la promoción PINN se bloquean
cuando hay conjunto activo: no pueden anunciar un cambio sobre un puntero ignorado.
Sin conjunto configurado se conserva el comportamiento anterior, incluido el
provisional autorizado por 085. El consumidor temporal y su contrato causal aún
deben conectarse; no se intercambia un pronóstico multihorizonte por la reconstrucción
histórica a un paso de 024/046.

### Ejecución

1. Auditar fuentes, series, episodios y modelos reales disponibles. Congelar los
   archivos necesarios en el directorio del ciclo y registrar hash de contexto 043.
   Copiar datos, no punteros activos; verificar copia y detectar cambios de origen.
2. Preparar vistas por familia con IDs de observación comunes: lenguaje anotado,
   ventanas causales y grafos nativos. Cuarentena para contradicciones, ausencias
   o etiquetas procedentes únicamente de una predicción. Mantener pruebas reservadas.
3. Ampliar el coordinador y la vigilancia existentes. Cada etapa consume la misma
   instantánea inmutable y escribe candidatos aislados del modelo activo. Ejecutar
   familias en secuencia de recursos, con lock GPU y turno nativo existentes.
4. Evaluar candidato y versión vigente con el mismo conjunto reservado y casos
   históricos. Exigir umbrales, retención, confirmaciones y reapertura. No transferir
   acierto lingüístico a aceptación física ni mezclar métricas de familias distintas.
5. Publicar un manifiesto de conjunto compatible referenciando candidatos del
   registro único. Cambio atómico del conjunto tras aprobación; conservar anterior.
   Los consumidores deben resolver sus versiones desde ese manifiesto, no tomar
   arbitrariamente el último modelo individual.
6. Cerrar el ciclo con readback web/CLI y una segunda captura real. Confirmar
   deduplicación, actualización por datos nuevos, rechazo de regresión, cancelación
   y reversión. Documentar coste, latencia y decisiones verificables, sin simular éxito.

## Pruebas requeridas antes del cierre

Contrato: `tests/test_aprendizaje_continuo.py`, con citas `050:RF-n`.
Integración real: `tests_ml/test_aprendizaje_continuo_real.py` y evidencia local de
los trabajadores; no usar mocks ni skips para acreditar operaciones de modelos.
Regresiones: coordinador, registro, vigilancia, series causales, gemelo y asistente.
No ejecutar dos trabajos CUDA simultáneos para intentar acelerar la aceptación.

Casos de rechazo: fuente/contexto distintos; cambios durante preparación; prueba
reciclada como entrenamiento; etiqueta eléctrica inventada; adaptador ausente;
etapa que termina sin informe; regresión histórica; promoción individual antes del
conjunto; reinicio o cancelación entre publicación y readback.
