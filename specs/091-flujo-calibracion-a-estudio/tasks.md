# Tareas — Spec 091

- [ ] T1. Mensajes de DIgSILENT, causa en el Registro y marcas huérfanas. (RF-1 a RF-6)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k "digsilent or marcas or causa"` en verde.
- [ ] T2. Las pestañas visitadas siguen montadas y otro espacio las reinicia. (RF-7, RF-8)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k pestanas` en verde.
- [ ] T3. Clientes cruzados por su hoja. (RF-9 a RF-13)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k hoja` en verde.
- [ ] T4. La máxima de cada proyecto y el cruce antes de ajustar. (RF-14 a RF-19)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k "maxima or cruce"` en verde.
- [ ] T5. El estudio después de la recalibración, avisado y sin bloquear. (RF-20 a RF-23)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k estudio` en verde.
- [ ] T6. Lo que se informa. (RF-24 a RF-32, RF-34)
      Hecho cuando: `pytest -q tests/test_flujo_a_estudio.py -k "informa or texto or empate or doctor or foto"` en verde.
- [ ] T7. [DIgSILENT] Calibración, recalibración y estudio por la web con TM102 de los TXT originales, y el mensaje con DIgSILENT abierto. (RF-1, RF-7, RF-16, RF-17, RF-19, RF-21, RF-24, RF-25)
      Hecho cuando: el recorrido en el navegador deja el ajuste apagado y explicado hasta que le toca, el estudio con su aviso hasta la recalibración, y sus cifras constan en esta tarea.
