# Tareas — Spec 091

- [x] T1. Mensajes de DIgSILENT, causa en el Registro y marcas huérfanas. (RF-1 a RF-6)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k "digsilent or marcas or causa"` en verde.
      Evidencia (2026-11-07): 8 pasadas; `tests/test_pf_arnes*.py` con ellas, 36 pasadas.
- [x] T2. Las pestañas visitadas siguen montadas y otro espacio las reinicia. (RF-7, RF-8)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k pestanas` en verde.
      Evidencia (2026-11-07): 2 pasadas; `npx tsc --noEmit -p frontend` sin errores. En el navegador, T7.
- [x] T3. Clientes cruzados por su hoja. (RF-9 a RF-13)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k hoja` en verde.
      Evidencia (2026-11-07): 7 pasadas; `tests/test_demanda_medida*.py` con ellas, 159 pasadas (los totales del
      cruce llevan `por_hoja`).
- [x] T4. La máxima de cada proyecto y el cruce antes de ajustar. (RF-14 a RF-19)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k "maxima or cruce"` en verde.
      Evidencia (2026-11-07): 7 pasadas; con `test_contrato_api`, `test_libros_por_anio_*` y
      `test_ajuste_cabecera_web`, 114 pasadas; contrato de la API regenerado; `tsc` sin errores.
- [x] T5. El estudio después de la recalibración, avisado y sin bloquear. (RF-20 a RF-23)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k estudio` en verde.
      Evidencia (2026-11-07): 29 pasadas (el nombre del fichero lleva «estudio»: corren todas); con
      `tests/test_estudios_pf_web.py`, 24 pasadas; `tsc` sin errores.
- [x] T6. Lo que se informa. (RF-24 a RF-32, RF-34)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k "informa or texto or empate or doctor or foto"` en verde.
      Evidencia (2026-11-07): `tests/test_flujo_a_estudio.py` entero, 40 pasadas; con `test_ajuste_cabecera_guion`,
      `test_q_con_bancos`, `test_ajuste_cabecera_web` y `test_digital_twin_integration`, 227 pasadas. RF-34 ya estaba
      en `digital_twin/integration.py`: su prueba lo comprueba con una lectura bloqueada.
- [x] T7. [DIgSILENT] Calibración, recalibración y estudio por la web con TM102 de los TXT originales, y el mensaje con DIgSILENT abierto. (RF-1, RF-7, RF-16, RF-17, RF-19, RF-21, RF-24, RF-25)
      Hecho cuando: el recorrido en el navegador deja el ajuste apagado y explicado hasta que le toca, el estudio con su aviso hasta la recalibración, y sus cifras constan en esta tarea.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
