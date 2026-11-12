# Tareas 096

- [x] T1. `suspension.py` y el trabajo que no deja suspender por inactividad y se repite una vez tras una suspensión.
      (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_retomar_tras_suspender.py` en verde.
- [x] T2. Relanzar al arrancar la web el último «Recalibrar» interrumpido de cada espacio, una vez. (RF-5, RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_retomar_tras_suspender.py` en verde.
- [x] T3. [DIgSILENT] Una recalibración de Pisco con el equipo suspendido y despertado a mitad termina sola. (RF-2)
      Hecho cuando: el trabajo «Recalibrar» termina sin relanzarlo a mano.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).

Avance P21 del 2026-11-08, sin cerrar T3: diario real producido por servidores y trabajadores propios,
caída abrupta, cancelación persistida, exclusión de un hijo vivo por PID/creación, dos relanzadores,
rechazo de prevalidación recuperable y monitor del lifecycle con parada esperada antes de shutdown.
Pruebas: `tests/test_trabajos_interrumpidos.py` y `tests/test_retomar_tras_suspender.py`.
Evidencia: `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/paralelo_p21_20261108/`.
El consumidor de calibración está sustituido en estas pruebas de recuperación. No hubo motor,
licencia ni suspensión física; siguen pendientes la idempotencia nativa y el criterio íntegro T3.
Revisión adicional P21: ensayos reales cortan entre crear el hijo y confirmar su identidad, y tras
terminar un sucesor DONE/FAILED antes de marcar el ancestro. La reserva previa bloquea un lanzamiento
incierto; el recibo final del sucesor excluye el ancestro sin reemitir efectos al leerlo. Se comprueban
también PID muerto sin fecha, identidad residual terminal, creación fallida y diario sin espacio.

Corrección de revisión P21 I1–I3, 2026-11-08, sin cerrar T3: snapshot/publicación y
retirada serializados por trabajo; cancelación y marcado fallidos no se anuncian durables;
sucesor sin recibo no se admite. Retención protege identidades pendientes y cadenas causales
antes de cap/borrados, incluido un reloj atrasado; 50 se aplica al residuo seguro y puede
superarse por protección explícita. Admisión/cierre comparten frontera, con cancelaciones
y joins fuera del cerrojo; un fallo de notificación se informa tras liberar los carriles.
`tests/test_integridad_trabajos.py` conserva los rojos y pruebas de caída real propia,
intercalaciones, 51 recibos, referencia causal y resultado completo de 8 MiB. No se cerró
ningún criterio nativo/humano/global. Evidencia externa y revisión exacta:
`D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/correccion_revision_p21_20261108/HANDOFF.md`.
- [x] T4. Sin espacio recordado en el navegador, la web retoma el último trabajado en vez de crear uno vacío. (RF-8)
      Hecho cuando: `frontend/test/retomarEspacio.test.mjs` (096:RF-8) en verde.
