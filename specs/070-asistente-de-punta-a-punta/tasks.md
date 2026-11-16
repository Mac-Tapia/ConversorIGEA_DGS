# Tareas — Spec 070

- [x] T1 Huecos del ejecutor. (RF-1 a RF-16)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k huecos` en verde.
- [x] T2 Tareas nuevas por rutas existentes. (RF-17 a RF-39)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k tareas` en verde.
  Ampliado el 2026-11-14 (prueba del auditor con órdenes reales, F3): «x … y …» y «coordenadas X Y» son la
  ubicación de la carga (RF-29), ni una SED ni un alimentador (`interprete.ubicacion_de`); evidencia en
  `tests/test_asistente_prueba_del_auditor.py`. Con ellos, F2 y F5 (026:RF-6): con un proyecto, «todos» son sus
  alimentadores, que la ruta toma de su vínculo, y no los de toda la fuente; una errata que se parece igual a dos
  alimentadores o proyectos se pregunta (`plan.empatados`).
- [x] T3 Consulta de datos. (RF-40 a RF-46)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k consulta` en verde.
- [x] T4 Respuestas de no disponible. (RF-47 a RF-49)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k nodisponible` en verde.
- [x] T5 Encadenar la evaluación de una carga nueva. (RF-50 a RF-56)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k cadena` en verde.
  Ampliado el 2026-11-14 (F4, F9): «si entra una carga … de punta a punta» va a esta cadena (RF-50); la primera
  frase literal del catálogo decide la tarea que el modelo no conoce, y también la que conoce cuando el modelo
  queda bajo su umbral (067:RF-36). Evidencia en `tests/test_asistente_prueba_del_auditor.py`.
- [x] T6 Reglas de dominio. (RF-57 a RF-61)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k dominio` en verde.
- [x] T7 Vía antigua de entrenamiento. (RF-62 a RF-66)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k via` en verde.
- [x] T8 Currículo y prueba sellada nueva. (RF-67 a RF-76)
  Hecho cuando: `pytest -q tests/test_asistente_maestro.py -k curriculo` en verde.
- [x] T9 [DIgSILENT] Un alimentador y una SET de punta a punta y una carga nueva, desde la consola, en proyectos de prueba de la sesión.
  Hecho cuando: los informes de la calibración y de la factibilidad salen de órdenes escritas, con su evidencia.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T10 [DIgSILENT] Las etapas, los faltantes y las consultas se leen en la consola de la web real, en el navegador.
  Hecho cuando: hay capturas de un plan de etapas, de un plan con faltantes y de una consulta.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [ ] T11 [DIgSILENT] Un candidato entrenado pasa las puertas en la prueba nueva; lo lanza el integrador. (RF-69)
  Hecho cuando: el registro deja un candidato PROMOVIDO medido con esa prueba, con su medida en
  `prueba_sellada_079.medida` (aclaración de RF-69) y la no regresión fuera de muestra (069, aclaración de RF-38 y RF-39).
- [x] T12 Un solo modelo del catálogo a la caché de la web. (RF-77)
  Hecho cuando: `pytest -q tests/test_preparacion_modelos_ia.py` en verde; la web de prueba reabre el intérprete con el codificador en su caché.
