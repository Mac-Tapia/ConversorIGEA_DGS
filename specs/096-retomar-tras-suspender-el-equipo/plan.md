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
