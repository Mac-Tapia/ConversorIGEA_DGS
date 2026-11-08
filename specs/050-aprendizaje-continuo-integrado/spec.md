# Spec 050 — Aprendizaje continuo integrado

Estado: aprobada · Fecha: 2026-11-01

## Contexto y objetivo

El usuario exige que LLM, PINN, RNN y los demás componentes integrados cooperen
en aprendizaje automático, diagnóstico, propuestas y mejora de sus propios datasets,
usando evidencia real de este proyecto. Entrenar familias por separado no acredita
su sincronización. Esta spec amplía 024/027 y consume 043–048, sin reabrir specs cerradas.

## Requisitos funcionales (EARS)

- RF-1: CUANDO comience un ciclo de aprendizaje, EL SISTEMA fijará una instantánea común de archivos, contexto, episodios y versiones, con hashes, antes de preparar los datasets de cada familia.
- RF-2: CUANDO el ciclo prepare datasets, EL SISTEMA conservará el vínculo de cada muestra con la instantánea, su origen observado, simulado nativo o redactado, y las particiones causales compartidas por observación o escenario.
- RF-3: SI falta una etiqueta física nativa, ENTONCES EL SISTEMA impedirá que una respuesta del LLM o de otro sustituto se use como si fuera verdad eléctrica observada.
- RF-4: CUANDO haya nuevos datos válidos o deriva según 027, EL SISTEMA programará un ciclo idempotente mediante la cola y el coordinador existentes, con presupuestos de tiempo, memoria, GPU y licencia, cancelación y prioridad del operador.
- RF-5: CUANDO los modelos cooperen en una propuesta, EL SISTEMA conservará qué aportó cada versión: interpretación del LLM, pronóstico temporal, estimación física, alternativas de optimización, evidencia recuperada y validación nativa.
- RF-6: CUANDO ajuste un candidato, EL SISTEMA conservará ejemplos históricos válidos y comprobará por familia y contexto la retención de capacidades anteriores, sin reutilizar prueba para elegir hiperparámetros.
- RF-7: CUANDO publique versiones compatibles para uso conjunto, EL SISTEMA exigirá puertas individuales y evaluación conjunta sobre evidencia reservada, reapertura de los artefactos y reversión al conjunto anterior; un empate o deterioro no acredita mejora.
- RF-8: SI falta un adaptador, dato, recurso o validación obligatorios, ENTONCES EL SISTEMA registrará el bloqueo del ciclo y mantendrá el conjunto aceptado, sin anunciar entrenamiento ni sincronización completos.
- RF-9: CUANDO el sistema proponga nuevos escenarios o anotaciones para aprender, EL SISTEMA validará su procedencia y consistencia, conservará los rechazados y evitará usar sus propias predicciones como recompensa o etiqueta verdadera sin contraste independiente.
- RF-10: CUANDO web o CLI muestren el aprendizaje, EL SISTEMA distinguirá preparación, entrenamiento, selección, evaluación, publicación, activación y aceptación nativa, con las versiones y motivos reales de cada estado.

## Requisitos no funcionales

Reutilizar búfer 024, cola web, `TrainingCoordinator`, `RegistroModelo` y contexto
043; no crear un segundo motor nativo ni promover modelos desde texto libre.
Los datasets de lenguaje, series y grafos tienen representaciones distintas;
comparten identidad y procedencia, no objetivos ni etiquetas intercambiables.
Los permisos y las condiciones de implementación nativa siguen sus specs vigentes.

Aclaraciones de RF-1/RF-2/RF-3/RF-8 (P19, 2026-11-08): el corpus documental
tiene identidad propia por nombre y huellas, separada de los proyectos físicos 043.
Una referencia a una observación declara contexto, fuente congelada, registro fuente,
instante con zona y huella del contenido representado; ninguna familia inventa esos
datos ni infiere aceptación eléctrica del contexto documental. La preparación relee
las particiones que consume cada trabajador y bloquea discrepancias antes del ajuste.
Una fuente sin productor verificable conserva un bloqueo; no se presenta como vista válida.

Aclaraciones de RF-4/RF-10 (P19, 2026-11-08): la vigilancia encola un único ciclo
con plan explícito, idempotencia y cancelación cooperativa entre etapas. El permiso
de autoentrenar permanece apagado por defecto; carecer de plan registra bloqueo.

## Fuera de alcance

No prometer inteligencia general, progreso ilimitado ni que todo ajuste mejore.
No modificar los planos anteriores a la exportación de la distribuidora. No mezclar otros
proyectos, entrenar en servicios externos ni convertir datos redactados en humanos.

## Criterios de finalización

Cada RF requiere prueba trazable y evidencia del ciclo completo sobre datos locales.
Un contrato puro probado con fixtures no acredita un entrenamiento real. Todas las
familias obligatorias deben ejecutarse y evaluarse, sin omisiones encubiertas.

## Fundamento científico

- Maestría de [Konstantin Witosek, DLR/Leipzig, 2025](https://elib.dlr.de/220552/):
  destilación de LLM y evaluación de su utilidad en tareas del dominio.
- Doctorado de [Mirzadeh, WSU, 2022](https://doi.org/10.7273/000004632):
  el aprendizaje secuencial puede perder conocimientos anteriores; exige evaluar retención.
- [Van de Ven, Tuytelaars y Tolias, Nature Machine Intelligence, 2022](https://doi.org/10.1038/s42256-022-00568-3):
  separar contextos y escenarios de aprendizaje incremental y contrastar replay.
- [Yang et al., Neural Networks, 2026](https://doi.org/10.1016/j.neunet.2025.108226):
  revisión del aprendizaje continuo, deriva y olvido catastrófico.

Las referencias sustentan la metodología; no prueban resultados del conversor.

Consulta web primaria P19 (2026-11-08): la tesis de maestría respalda evaluar el
alumno con fuentes del dominio; el [doctorado de Mirzadeh](https://rex.libraries.wsu.edu/esploro/outputs/doctoral/Alleviating-Catastrophic-Forgetting-in-Continual-Learning/99900898638301842)
respalda medir el olvido antes de sustituir modelos; el artículo de Nature Machine
Intelligence respalda explicitar contextos y escenarios de aprendizaje incremental.
Estas fuentes justifican procedencia, reserva y retención como método; no certifican
las puertas, el software ni aceptación eléctrica de esta implementación.

## Fronteras de implementación 002/050 (U0, 2026-11-08)

RF-2/3 conservan un único contrato puro de muestra, procedencia y etiquetas, compartido
por productores y consumidores. RF-7 conserva un lector verificado del conjunto que
no importa preparación ni entrenamiento. RF-4/8 requieren composición explícita de
los productores reales en las entradas CLI y plan de vigilancia; su ausencia en una
llamada Python directa bloquea con motivo explícito. No se cambian las fuentes,
particiones, puertas, planes ni la API web. La corrección no añade excepciones a la
política de capas de 002 y no acredita las tareas reales T1b–T5b.

Fundamento de la separación consultado en web: la [maestría de Avilés Redondo,
UPM, 2025](https://oa.upm.es/90309/) estudia una migración de capas a puertos y
adaptadores; el [doctorado de Uzun, Wageningen, 2021](https://doi.org/10.18174/544468)
contrasta código y vistas arquitectónicas para detectar divergencias. El artículo
[Murphy y Notkin, IEEE Computer, 1997](https://www.cs.ubc.ca/~murphy/papers/rm/rm-case-study.pdf)
sustenta comparar un modelo intencionado con dependencias extraídas del código y
refinarlo iterativamente. Se aplican como método de separación y comprobación; no
certifican pureza semántica, conservación científica ni aceptación nativa del producto.
