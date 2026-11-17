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
- [x] T13 Ningún mensaje ni texto de la web cita requisitos, specs ni tareas. (RF-78)
  Hecho cuando: `tests/test_textos_sin_requisitos.py` falla en e182c823 (66 textos) y pasa tras quitarlos, y
  `tests/test_trazabilidad_specs.py`, `npm run lint`, `npx tsc --noEmit -p .`, `npm run build` y `npm test` siguen como
  antes. Hecho el 2026-11-15 (tarjeta MENSAJES-SIN-RF): rojo y verde en `D:/csg/PM_IMPL/PISTA3/MENSAJES-SIN-RF/`.
- [ ] T14 Ningún aviso ni mensaje de las respuestas cita requisitos, specs ni tareas, por grupos de módulos. (RF-78)
  Hecho cuando: `tests/test_textos_sin_requisitos.py` recorre `src/` entero sin `EN_VUELO` (cuando la 107 limpie `pit/`) y
  está en verde con las pruebas de cada módulo.
  Avance del 2026-11-15, rojo y verde de cada tarjeta en `D:/csg/PM_IMPL/PISTA3/MENSAJES-SIN-RF/<tarjeta>/`: v2a (13
  módulos), v2b (4), v2c (2), v2d (2), v2e (`web/services.py`) y la final (src/ entero; también los avisos por `avisar(…)`).
  Falta solo `src/convertersmartgrid/pit/` (7 avisos con «107:RF-8/12»), que quita la 107. Está en `EN_VUELO`, y
  `test_la_lista_de_en_vuelo_no_esconde_nada` obliga a sacarla de la lista en cuanto quede limpia: entonces se marca.
- [ ] T15 Excepciones de cualquier clase, salida de los guiones y textos en variables sin citas, por tarjetas. (RF-78)
  Hecho cuando: `PENDIENTES_V3` de `tests/test_textos_sin_requisitos.py` está vacío, `tests/test_textos_sin_requisitos.py`
  está en verde con las pruebas de cada módulo, y los guiones de Playwright llaman a `comprobar_sin_citas`.
  Avance del 2026-11-15: v3a (detector v3, src/ limpio salvo pit/ de la 107, 57 textos; la función común de Playwright
  enganchada a los guiones de MAPA-IFRAME, F1 y web_rutas), en `D:/csg/PM_IMPL/PISTA3/MENSAJES-SIN-RF/v3/`. Quedan los
  19 guiones de tools/ de `PENDIENTES_V3` (v3b a v3e). v3b: los 16 guiones pequeños, la prueba de que ningún código decide
  por una cita y los 4 filtros que lo hacían, ahora por el sentido del aviso (tools/cabecera_ancha.py,
  tools/aceptar_restitucion_pf.py, tools/sistema_web.py y src/convertersmartgrid/pronostico_demanda.py); la lista explícita
  de «T<n>» permitidos en `sin_citas.py`. v3c: tools/cargas_pf.py (56 líneas). v3d: tools/obras_pf.py (64 líneas). v3e: tools/ajuste_cabecera_pf.py (107 líneas) y su filtro por «(083:RF-31)», ahora por el sentido: PENDIENTES_V3 queda vacío. v3f: el detector ve también el texto que devuelve una función (`return`) y las claves `error`, `origen` y `fuente`; se quitan sus 72 textos en 25 ficheros (los 137 medidos al cerrar v3e, contados una vez por línea y texto). Solo falta la parte del navegador.
- [x] T12 Un solo modelo del catálogo a la caché de la web. (RF-77)
  Hecho cuando: `pytest -q tests/test_preparacion_modelos_ia.py` en verde; la web de prueba reabre el intérprete con el codificador en su caché.
- [ ] T16 Correo y nube por el asistente: tareas, rutas de previa, la tarjeta del panel con su botón y el seguimiento
  del recibo; e2e con la nube y el correo simulados. (RF-79, RF-80, RF-81, RF-82, RF-83)
  Hecho cuando: `pytest -q tests/test_asistente_nube_correo.py` y el e2e del panel en verde.
- [ ] T17 Tareas del PIT por `/api/pit/…`. (RF-79)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k pit` en verde.
- [ ] T18 Ruta web del VAD y su tarea. (RF-79, RF-86)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k vad` en verde.
- [ ] T19 Tareas del plano: maniobra en una variación y su estudio. (RF-79)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k plano` en verde.
- [ ] T20 Tarea del benchmark anonimizado. (RF-79)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k benchmark` en verde.
- [ ] T21 Frases del maestro, sintéticos y la prueba sellada nueva con su huella; la anterior, histórica. (RF-84, RF-85)
  Hecho cuando: `pytest -q tests/test_prueba_sellada_107_112.py tests/test_asistente_maestro.py tests/test_maestro_real.py tests/test_asistente_sinteticos.py` en verde, y la destilación la mide (con la T22).
- [ ] T22 [GPU] Reentrenar el modelo de órdenes con las tareas nuevas y pasar sus puertas (085). (RF-84)
  Hecho cuando: el candidato pasa sus puertas, o queda el modelo en uso con su diagnóstico.
