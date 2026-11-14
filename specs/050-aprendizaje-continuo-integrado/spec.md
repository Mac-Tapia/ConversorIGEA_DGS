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
- RF-11: CUANDO se prepare un ciclo sobre rutas reales declaradas, EL SISTEMA generará un manifiesto de procedencia por registro y un contexto del ciclo en una carpeta nueva.
- RF-12: MIENTRAS prepara el ciclo, EL SISTEMA leerá los almacenes de origen sin escribir en ellos.
- RF-13: EL SISTEMA calculará la huella 043 de un episodio solo con los catorce campos de su identidad leídos del episodio o de un complemento declarado.
- RF-14: SI un complemento declarado contradice un campo del episodio, ENTONCES EL SISTEMA pondrá el episodio en cuarentena en vez de sustituir el campo.
- RF-15: SI un registro consumido por una familia no tiene procedencia demostrable, ENTONCES EL SISTEMA lo reportará en cuarentena con su motivo y no emitirá referencia para él.
- RF-16: CUANDO prepare la vista del búfer, EL SISTEMA copiará solo los episodios que pueden enseñar y tienen referencia.
- RF-17: DONDE un registro documental no traiga fecha propia, EL SISTEMA usará como instante la fecha de sellado de su manifiesto y dejará escrito ese origen.
- RF-18: SI el registro pertenece a una fuente física, ENTONCES EL SISTEMA no le aplicará el instante de sellado de RF-17.
- RF-19: CUANDO una serie de cabecera quede apartada, EL SISTEMA la reportará con el motivo textual del lector y conservará el bloqueo de la familia GRU.
- RF-20: SI una serie de cabecera no se vincula a una única identidad 043, ENTONCES EL SISTEMA la pondrá en cuarentena sin atribuirle otro contexto.
- RF-21: SI falta la ruta de una fuente, ENTONCES EL SISTEMA la declarará pendiente junto con las familias que quedan sin preparar.
- RF-22: MIENTRAS el ciclo no pida series concretas de cabecera, EL SISTEMA aplicará a sus objetivos el apartado con motivo y el tramo común de la lectura de cabeceras de 060:RF-5.
- RF-23: CUANDO capture un episodio, EL SISTEMA guardará en su contexto físico el periodo, el criterio de fijas y la huella del perfil que consten.
- RF-24: CUANDO una los datasets de lenguaje, EL SISTEMA bloqueará la unión si un registro de origen cambia de partición.
- RF-25: SI el complemento de identidad no nombra a su responsable, ENTONCES EL SISTEMA lo rechazará.
- RF-26: CUANDO referencie un registro generado por plantilla, EL SISTEMA usará como fuente la parte sellada del dataset y conservará su etiqueta de maestro.
- RF-27: DONDE se declare el proyecto de un libro de sistema, EL SISTEMA vinculará sus series al caso base más reciente de ese proyecto con identidad 043 completa.
- RF-28: CUANDO genere casos evolutivos desde escaleras guardadas, EL SISTEMA reportará el parámetro que falte en vez de crear el caso sin él.
- RF-29: CUANDO una consulta reservada de recuperación la redacte el maestro, EL SISTEMA la marcará con ese origen y la informará por separado de las humanas al evaluar.
- RF-30: CUANDO prepare las órdenes del ciclo, EL SISTEMA calculará la huella de la política a partir de las políticas 044 con que se evalúa.
- RF-31: EL SISTEMA medirá el presupuesto de memoria del ciclo con el mismo criterio que cada trabajador: en Windows, el margen comprometible con al menos 0,5 GiB físicos.

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
de autoentrenar estuvo apagado por defecto hasta el 2026-11-13; carecer de plan registra bloqueo.
Aclaración de RF-4 (usuario, 2026-11-13): el permiso de empezar desaparece. El ciclo se
programa siempre, salvo la orden explícita `CSG_AUTOENTRENAMIENTO=0` (071:RF-6), y lee su
plan de los datos del asistente (`aprendizaje/plan.json`) o de `CSG_APRENDIZAJE_PLAN`, que
solo cambia la ruta. Sin plan sigue el bloqueo visible de RF-8, y la promoción sigue con sus puertas.

Aclaraciones de RF-13/RF-15 (T6, 2026-11-08): los episodios reales traen fuente, proyecto,
alimentadores, caso y huellas de topología, controles y escenario, pero no `profile_hash`,
y la mayoría tampoco periodo ni criterio de fijas. `clave_contexto` exige los catorce campos:
una huella calculada con menos no es una identidad 043 y no entra en el mapa de proyectos,
porque abriría la comprobación física de `muestra_de_registro`. Lo que falta lo aporta un
complemento declarado por el responsable, o el episodio queda en cuarentena.

Aclaración de RF-19 (integrador, 2026-11-08): el bloqueo de la familia GRU rige cuando se piden series concretas; sin
pedirlas, las apartadas constan en la preparación con su motivo y el ciclo sigue con las demás (RF-22). Motivo: dos lectores
del mismo libro daban criterios distintos, y la excepción de 060:RF-5 no llegaba al ciclo.

Decisiones del integrador para los datos anteriores a RF-23 (2026-11-08): el complemento declara `declarado_por`; el
periodo es el del episodio si lo trae y, si no, el mes de la última calibración de su proyecto; el criterio de fijas es el
del informe de calibración; `profile_hash` es la huella del perfil vigente, declarada al preparar y no capturada. Las
consultas reservadas de recuperación del maestro no son humanas y no sustituyen a 047/077.

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
