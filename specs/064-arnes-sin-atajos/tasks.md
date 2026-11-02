# Tareas — Spec 064

- [x] T1. Prueba que detecta cualquier conexión fuera del arnés. (RF-2)
      Hecho cuando: `tests/test_pf_arnes_sin_atajos.py` falla sobre los siete guiones de hoy.
- [x] T2. Los siete guiones conectan con `pf_arnes.conectar`. (RF-1)
      Hecho cuando: T1 pasa y `--help` de cada guion responde (`test_inventario`).
- [x] T3. La web lanza la red del sistema y el escenario base con el entorno de DIgSILENT. (RF-3)
      Hecho cuando: una prueba de `system_command`/`run_system` ve `PF_PYTHON` en el entorno.
- [x] T4. `pf_estado`: foto y restitución. (RF-4, RF-5, RF-6)
      Hecho cuando: `tests/test_pf_servidor.py` (doble de la API con caso, hora, escenario y variaciones) pasa.
- [x] T5. El servidor restituye tras una orden fallida y sigue si no puede. (RF-5, RF-6, RF-7)
      Hecho cuando: `tests/test_pf_servidor.py` pasa con órdenes que fallan y que lanzan.
- [x] T6. `set_nueva_operacion_pf.py` en el servidor. (RF-8)
      Hecho cuando: una prueba lo encuentra en `GUIONES_SERVIBLES`.
- [x] T7. [DIgSILENT] Desde la web abierta con el acceso directo: una orden que falla y la siguiente encuentran el caso y la hora de antes. (RF-5, RF-6)
      Hecho cuando: el registro de la orden fallida dice qué se restituyó y una lectura posterior lo confirma.

- [x] T8. La foto que falla no deja la orden sin cerrar ni tumba el servidor. (RF-9)
      Hecho cuando: `pytest -q tests/test_pf_servidor.py -k "fotografiar or revienta"` en verde, y
      esas pruebas fallan con el código de `ac1c316b` (comprobado el 2026-11-02).
- [x] T9. La restitución comprueba retornos, identidades y la foto final. (RF-10)
      Hecho cuando: `pytest -q tests/test_pf_servidor.py -k no_surte_efecto` en verde para caso,
      caso que no cambia sin avisar, escenario y variación, y falla con el código de `ac1c316b`.

Evidencia de T7. El primer cierre (sonda directa sobre `pf_estado.restituir` y, aparte, una
orden fallida por la web sin estado que reponer) no probaba la cadena entera; la auditoría del
2026-11-02 (H3) lo señaló y T7 se reabrió. Cerrada de nuevo el 2026-11-02 con
`tools/aceptar_restitucion_pf.py`, que manda cuatro órdenes de `tools/restitucion_pf.py` por el
camino de la web (`services._guion_pf` → `pf_cliente` → `pf_servidor.atender`) sobre una copia
exclusiva `PRUEBA064_*`, borrada al terminar; el original no se modifica:

- copia de SM218 (`AUDIT/auditoria_otra_sesion_20261102/aceptacion_T7_064_sm218.json`): la orden
  cambió el caso («Caso base»), la hora de «Sin proyecto» (−10⁶ s), el escenario («Operation
  Scenario») y las variaciones (sin `SED_NTP_…`) y terminó con código 1; el registro dice
  «se deja DIgSILENT como estaba al empezar (064:RF-5): caso «Sin proyecto» activo de nuevo;
  hora de estudio repuesta a 1792309657», y la orden de lectura siguiente devolvió la foto
  inicial entera;
- copia de `20261101-101524_CSG_0205` (`…/aceptacion_T7_064.json`): caso y hora, igual.
