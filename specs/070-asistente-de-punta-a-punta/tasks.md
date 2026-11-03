# Tareas — Spec 070

- [x] T1 Huecos del ejecutor. (RF-1 a RF-16)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k huecos` en verde.
- [x] T2 Tareas nuevas por rutas existentes. (RF-17 a RF-39)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k tareas` en verde.
- [x] T3 Consulta de datos. (RF-40 a RF-46)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k consulta` en verde.
- [x] T4 Respuestas de no disponible. (RF-47 a RF-49)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k nodisponible` en verde.
- [x] T5 Encadenar la evaluación de una carga nueva. (RF-50 a RF-56)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k cadena` en verde.
- [x] T6 Reglas de dominio. (RF-57 a RF-61)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k dominio` en verde.
- [ ] T7 Vía antigua de entrenamiento. (RF-62 a RF-66)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k via` en verde.
- [ ] T8 Currículo y prueba sellada nueva. (RF-67 a RF-75)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k curriculo` en verde.
- [ ] T9 [DIgSILENT] Un alimentador y una SET de punta a punta y una carga nueva, desde la consola, en proyectos de prueba de la sesión.
  Hecho cuando: los informes de la calibración y de la factibilidad salen de órdenes escritas, con su evidencia.
- [ ] T10 [DIgSILENT] Las etapas, los faltantes y las consultas se leen en la consola de la web real, en el navegador.
  Hecho cuando: hay capturas de un plan de etapas, de un plan con faltantes y de una consulta.
- [ ] T11 [DIgSILENT] Un candidato entrenado pasa las puertas en la prueba nueva; lo lanza el integrador.
  Hecho cuando: el registro deja un candidato PROMOVIDO medido con esa prueba.
