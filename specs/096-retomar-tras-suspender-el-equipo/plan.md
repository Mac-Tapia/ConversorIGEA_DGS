# Plan 096 — Retomar tras suspender el equipo

## Módulos

- `src/convertersmartgrid/web/suspension.py` (nuevo): `suspendido_s()` mide los segundos que el equipo estuvo
  suspendido desde el arranque, como `GetTickCount64` (cuenta la suspensión) menos `QueryUnbiasedInterruptTime` (no
  la cuenta); fuera de Windows, 0. `sin_suspender()` es un contexto que llama a `SetThreadExecutionState` con
  `ES_CONTINUOUS | ES_SYSTEM_REQUIRED` en el hilo del trabajo y lo devuelve a `ES_CONTINUOUS` al salir. (RF-1)
- `src/convertersmartgrid/web/jobs.py`, `JobManager._run`: el trabajo corre dentro de `sin_suspender()`; si falla con
  más de `SUSPENSION_MINIMA_S` suspendido entre su inicio y su fallo, y no está cancelado, se repite una vez. (RF-2 a
  RF-4). `submit(..., reanudar=...)` guarda en el diario la petición con que se puede repetir; `recuperar` la devuelve
  con el interrumpido. (RF-5)
- `src/convertersmartgrid/web/app.py`: al arrancar, por espacio, el último interrumpido con `reanudar` de un tipo
  conocido (`recalibrar`) se lanza otra vez con su petición, si no sigue vivo un `sistema_web.py` de ese espacio; el
  interrumpido se marca relanzado para no repetirlo. (RF-5 a RF-7)

## Decisiones

- Medir la suspensión con los relojes de Windows y no con un salto entre el reloj de pared y `time.monotonic`: en
  Windows `monotonic` es `GetTickCount64`, que sigue contando dormido, y un cambio de hora daría un falso positivo.
- Repetir el trabajo entero y no la orden de DIgSILENT: «Recalibrar» y el ajuste ya retoman o rehacen desde el
  escenario (015:RF-69), y así vale para todos los trabajos sin tocar cada guion.

## Pruebas

- `tests/test_retomar_tras_suspender.py`: suspensión simulada (`suspendido_s` parcheado) con un trabajo que falla la
  primera vez; sin suspensión no se repite; cancelado no se repite; el segundo fallo queda fallido; el contexto pide y
  suelta el estado de Windows; un interrumpido con `reanudar` se relanza una vez al crear la web, con su origen.

## Robustez P21 (2026-11-08)

RF-4 a RF-7 conservan la cancelación, el origen del relanzamiento y la identidad del trabajador
(`pid` y fecha de creación) en el diario. Un hijo vivo o una identidad ilegible impiden relanzar;
un PID reutilizado con otra fecha no equivale al hijo original. La recuperación no envía señales.
`JobContext.anotar_proceso` conecta también un lanzador supervisado propio con este diario.

La admisión precede a marcar el interrumpido como relanzado. Un cerrojo compartido excluye
el relanzamiento manual y el automático. El lifecycle vuelve a comprobar mientras espera un hijo,
y espera la terminación de su monitor antes de cerrar la admisión. Tras un rechazo de prevalidación,
conserva el interrumpido recuperable y su motivo; no vuelve a intentar automáticamente en ese arranque,
para evitar un bucle de errores. La comprobación manual permite reintentar una vez corregida la causa.

La revisión del integrador añade tres comprobaciones de las ventanas de caída:

- Una identidad sin fecha sigue bloqueando si su PID vive; si ya no existe el PID, se puede resolver.
  Los trabajos terminales no bloquean la recuperación por una identidad residual.
- Antes de `start`/`Popen` se guarda una reserva durable. Si no se puede guardar, no se crea el hijo.
  Un fallo de creación retira la reserva; una muerte del servidor entre crear y confirmar conserva
  la incertidumbre y exige revisión explícita, sin relanzar ni matar procesos ambiguos.
- Se conserva el recibo JSON final de los sucesores, incluido su origen, estado y resultado/error,
  retirando su log largo. La recuperación usa ese enlace para excluir ancestros aun si el servidor
  cayó antes de marcarlos. Los recibos terminales se leen sin reemitir eventos que repetirían capturas
  o custodia. El límite del residuo seguro no autoriza perder identidades pendientes ni relaciones causales.

## Corrección de la revisión P21 I1–I3 (2026-11-08)

- RF-4/RF-6, I1: cada Job tiene un RLock de diario distinto del gate de cancelación.
  Cubre captura de todos los campos, serialización y publicación durable; también la
  terminación/retirada. Un avance o recibo de proceso anterior no puede reemplazar
  una cancelación o un estado terminal posterior, ni recrear un diario retirado.
  Los fallos de escritura siguen devolviendo False desde el diario: cancelación y
  marcado de relanzado comunican el fallo, sin afirmar que se persistió. El evento
  cooperativo permanece pedido en memoria; un marcado fallido restaura su flag.
- RF-5/RF-6, I2: la recuperación protege identidades vivas/ambiguas y los componentes
  de la relación relanzado_de antes de podar. Selecciona los últimos 50 del residuo
  seguro y conserva además sus relaciones, incluso si el reloj del sucesor retrocedió.
  No se borran JSON ni logs de trabajos protegidos. 50 no es un techo absoluto cuando
  hay protección causal; no se reduce el límite ni se destruye una referencia para
  cumplir la cifra. Los archivos ilegibles siguen conservados por el lector previo.
  Un sucesor de otro servidor vivo también excluye su ancestro: se deriva en memoria
  desde el enlace durable leído, sin adjudicarse el sucesor ni reescribir sus recibos.
- RF-5/RF-6, I3: shutdown cruza la frontera de admisión bajo el mismo _admision que
  submit. Libera el cerrojo antes de cancelar y hacer joins: un worker puede intentar
  otro paso y recibir rechazo sin bloquear el cierre. Una cancelación/notificación
  fallida no impide cerrar los demás carriles; el error se comunica tras los joins.
  El timeout de cierre sigue siendo el vigente, no una promesa de preempción nativa.
- Una recuperación con relanzado_de exige recibo durable antes de registrarse,
  emitirse o entrar en la cola. Si falla, no ejecuta siquiera efectos directos de una
  función sin spawn. Una observación inicial rechazada retira ese recibo, porque aún
  no entró en cola. Se conservan las firmas públicas y el comportamiento previo de
  trabajos ordinarios sin hijos frente a un diario de mejor esfuerzo; cualquier hijo
  sigue exigiendo su reserva durable antes de crear el proceso.

Pruebas añadidas: `tests/test_integridad_trabajos.py`, con escrituras atómicas reales,
barreras de planificación, cortes de servidores propios, identidades de hijos reales,
51 recibos con el límite de producción, cadenas/reloj y errores de disco/notificación.
No se simula una calibración aceptada con estos contratos.

M1: el resultado de los recibos terminales se conserva completo para mantener API y
referencias. Se relee un resultado de 8 MiB sin truncarlo ni reemitirlo. No hay límite
de bytes JSON ni cuota absoluta de disco/RAM del diario; identidades y cadenas
protegidas pueden superar los 50 registros. La compactación con resultados separados
queda pendiente de diseño; no se presenta este comportamiento como una omisión ni
se recorta silenciosamente un resultado para aparentar un límite.

`tests/test_trabajos_interrumpidos.py` produce diarios con servidores y trabajadores propios reales,
mata el servidor sin cierre limpio, comprueba cancelación/identidad/concurrencia y mata después al hijo
para verificar la recuperación del lifecycle y su cierre. La calibración nativa se sustituye solo en
el consumidor de esas pruebas: no certifica idempotencia de DIgSILENT. T3 sigue abierta, incluida la
suspensión física, que no se provoca en una máquina compartida.

Fundamento metodológico consultado en web el 2026-11-08:

- Ramidi, H. R. (2010), [An Improved Crash Recovery Approach for Distributed Systems](https://opensiuc.lib.siu.edu/theses/218/),
  tesis de Master of Science, Southern Illinois University Carbondale. Su ficha y resumen públicos
  relacionan recuperación, puntos de control y mensajes huérfanos. Solo se consultó ese resumen; el texto
  completo exige acceso institucional. Motiva conservar estado y origen, sin trasladar sus garantías al programa.
- Beineke, K. (2018; depósito 2019), [Fast Parallel Crash Recovery in Distributed In-Memory Key-Value Stores](https://docserv.uni-duesseldorf.de/servlets/DocumentServlet?id=48474),
  tesis doctoral, HHU Düsseldorf. El resumen institucional describe registro durable, versiones y coordinación
  de recuperación. Motiva distinguir memoria de persistencia y verificar procesos después del corte;
  no se aplican al conversor sus cifras de rendimiento ni su arquitectura distribuida.
- Elnozahy, E. N., Alvisi, L., Wang, Y.-M. y Johnson, D. B. (2002),
  [A Survey of Rollback-Recovery Protocols in Message-Passing Systems](https://www.cs.rice.edu/~dbj/pubs/csur-rollback.pdf),
  ACM Computing Surveys 34(3), 375–408, DOI 10.1145/568522.568525,
  [registro bibliográfico indexado](https://dblp.org/pid/e/ENElnozahy.html).
  Distingue recuperación por puntos de control y por registro, y consistencia con efectos externos.
  Justifica ensayar cortes reales y conservación observable; no certifica idempotencia eléctrica ni aceptación PowerFactory.
