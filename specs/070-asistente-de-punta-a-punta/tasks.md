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
- [x] T14 Ningún aviso ni mensaje de las respuestas cita requisitos, specs ni tareas, por grupos de módulos. (RF-78)
  Hecho cuando: `tests/test_textos_sin_requisitos.py` recorre `src/` entero sin `EN_VUELO` (cuando la 107 limpie `pit/`) y
  está en verde con las pruebas de cada módulo.
  Avance del 2026-11-15, rojo y verde de cada tarjeta en `D:/csg/PM_IMPL/PISTA3/MENSAJES-SIN-RF/<tarjeta>/`: v2a (13
  módulos), v2b (4), v2c (2), v2d (2), v2e (`web/services.py`) y la final (src/ entero; también los avisos por `avisar(…)`).
  Falta solo `src/convertersmartgrid/dominio/pit/` (7 avisos con «107:RF-8/12»), que quita la 107. Está en `EN_VUELO`, y
  `test_la_lista_de_en_vuelo_no_esconde_nada` obliga a sacarla de la lista en cuanto quede limpia: entonces se marca.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_textos_sin_requisitos.py.
- [x] T15 Excepciones de cualquier clase, salida de los guiones y textos en variables sin citas, por tarjetas. (RF-78)
  Hecho cuando: `PENDIENTES_V3` de `tests/test_textos_sin_requisitos.py` está vacío, `tests/test_textos_sin_requisitos.py`
  está en verde con las pruebas de cada módulo, y los guiones de Playwright llaman a `comprobar_sin_citas`.
  Avance del 2026-11-15: v3a (detector v3, src/ limpio salvo pit/ de la 107, 57 textos; la función común de Playwright
  enganchada a los guiones de MAPA-IFRAME, F1 y web_rutas), en `D:/csg/PM_IMPL/PISTA3/MENSAJES-SIN-RF/v3/`. Quedan los
  19 guiones de tools/ de `PENDIENTES_V3` (v3b a v3e). v3b: los 16 guiones pequeños, la prueba de que ningún código decide
  por una cita y los 4 filtros que lo hacían, ahora por el sentido del aviso (tools/cabecera_ancha.py,
  tools/aceptar_restitucion_pf.py, tools/sistema_web.py y src/convertersmartgrid/adaptadores/pronostico_demanda.py); la lista explícita
  de «T<n>» permitidos en `sin_citas.py`. v3c: tools/cargas_pf.py (56 líneas). v3d: tools/obras_pf.py (64 líneas). v3e: tools/ajuste_cabecera_pf.py (107 líneas) y su filtro por «(083:RF-31)», ahora por el sentido: PENDIENTES_V3 queda vacío. v3f: el detector ve también el texto que devuelve una función (`return`) y las claves `error`, `origen` y `fuente`; se quitan sus 72 textos en 25 ficheros (los 137 medidos al cerrar v3e, contados una vez por línea y texto). Solo falta la parte del navegador.
  Cerrada (2026-11-17, 4d): `comprobar_sin_citas` en `frontend/test/e2e/comun.mjs` (la llama `revisarAxe`, en cada
  estado de cada recorrido) y en `frontend/e2e/sin_red.ts` (la línea base, en cada pestaña); las fuentes literales
  del asistente van marcadas (`data-cita-de-fuente`) y no cuentan. En navegador real: F01 a F05 y teclado, 10
  passed; prueba permanente en `tests/test_e2e_arnes.py`. `PENDIENTES_V3` vacío y su prueba en verde.
- [x] T12 Un solo modelo del catálogo a la caché de la web. (RF-77)
  Hecho cuando: `pytest -q tests/test_preparacion_modelos_ia.py` en verde; la web de prueba reabre el intérprete con el codificador en su caché.
- [x] T16 Correo y nube por el asistente: tareas, rutas de previa, la tarjeta del panel con su botón y el seguimiento
  del recibo; e2e con la nube y el correo simulados. (RF-79, RF-80, RF-81, RF-82, RF-83)
  Hecho cuando: `pytest -q tests/test_asistente_nube_correo.py` y el e2e del panel en verde.
      Hecho en e2a99c73 (PUERTA3); pruebas: tests/test_asistente_nube_correo.py.
- [x] T17 Tareas del PIT por `/api/pit/…`. (RF-79)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k pit` en verde.
      Hecho en e2a99c73 (PUERTA3); pruebas: tests/test_asistente_107_112.py -k pit.
- [x] T18 Ruta web del VAD y su tarea. (RF-79, RF-86)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k vad` en verde.
      Hecho en e2a99c73 (PUERTA3); pruebas: tests/test_asistente_107_112.py -k vad.
- [x] T19 Tareas del plano: maniobra en una variación y su estudio. (RF-79)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k plano` en verde.
      Hecho en e2a99c73 (PUERTA3); pruebas: tests/test_asistente_107_112.py -k plano.
- [x] T20 Tarea del benchmark anonimizado. (RF-79)
  Hecho cuando: `pytest -q tests/test_asistente_107_112.py -k benchmark` en verde.
      Hecho en e2a99c73 (PUERTA3); pruebas: tests/test_asistente_107_112.py -k benchmark.
- [x] T21 Frases del maestro, sintéticos y la prueba sellada nueva con su huella; la anterior, histórica. (RF-84, RF-85)
  Hecho cuando: `pytest -q tests/test_prueba_sellada_107_112.py tests/test_asistente_maestro.py tests/test_maestro_real.py tests/test_asistente_sinteticos.py` en verde, y la destilación la mide (con la T22).
      Hecho el 2026-11-19 (ASISTENTE-C, wt_ce_c): `destilacion_integral.medir_selladas_nuevas` mide el candidato en la
      sellada 107-112 y en la 026, cada una con su huella comprobada, sin decidir; va en `metrics` y en `decision.json`
      como `selladas_nuevas`, y sus ficheros en `codigo_hashes`. Rojo VALIDO (2 failed, 2 passed) en
      D:/csg/PM_IMPL/ASISTENTE_C/070_T21/rojo.log; verde D:/csg/PM_IMPL/ASISTENTE_C/verde/verde_c.log (461 passed, rc=0) con las cuatro pruebas,
      `test_destilacion_integral.py` y `test_afinado_ordenes.py`. La medida real la da la T22 en la GPU.
- [x] T22 [GPU] Reentrenar el modelo de órdenes con las tareas nuevas y pasar sus puertas (085). (RF-84)
  Hecho cuando: el candidato pasa sus puertas, o queda el modelo en uso con su diagnóstico.
      Hecho el 2026-11-24 (d8, corrida limpia de 1 h 49 min en la GPU, rc=0, sin cortes): el candidato queda RECHAZADO
      y sigue el modelo en uso, con su diagnóstico en D:/csg/PM_IMPL/GPU_BLOQUE/070_T22_noche/diagnostico.md. En las 43
      humanas, lo que ejecuta solo (umbral 0,95) acierta 29 de 29; falla la ejecución sola en las sintéticas (0,964) y
      en el examen del maestro (0,946), bajo 0,98, con confusiones entre tareas vecinas del contrato nuevo; la no
      regresión no se pudo medir porque el modelo en uso no se abría con el contrato de 68 tareas, lo que arregla la T27.
      La mejora del candidato sigue en la T28.
- [x] T23 Esperas finitas del asistente (C2 del diagnóstico del 18-11, H03): «interrumpido» termina la espera, cada
  petición lleva su límite, la espera tiene plazo total y una web que no responde se dice. (RF-87)
  Hecho cuando: `pytest -q tests/test_asistente_espera_finita.py` en verde, con su rojo por aserción en la base (las
  sondas H03a y H03b de D:/csg/INTEGRA_54/auditoria_c0 reproducen lo mismo).
- [x] T24 Petición sin respuesta como paso fallido con su motivo, plazo propio de las rutas síncronas largas y la espera
  que sigue contándola como pasajera; con lo demás de la revisión de ASISTENTE-A de 1d (18-11). (RF-88)
  Hecho cuando: `pytest -q tests/test_asistente_peticion_sin_respuesta.py` en verde (070:RF-88, 086:RF-110, 026:RF-50,
  026:RF-46), con su rojo por aserción en la base, y `tests/test_asistente_espera_finita.py` sin cambios en verde.
- [x] T25 El interruptor `CSG_ASISTENTE_OLLAMA=0`: sin conexión a Ollama y la vía compatible, en las configuraciones de
  las pruebas de navegador sin modelo. (RF-89)
  Hecho cuando: `pytest -q tests/test_asistente_ollama_apagado.py` (070:RF-89) en verde; lo trajo ASISTENTE-A y le
  faltaba su RF (lo cazó test_trazabilidad_specs en el verde amplio de ce del 18-11).
- [x] T26 Contexto defensivo (tarjeta MEJ-070-INYECCION, 19-11): una prueba negativa por cada herramienta que escribe (45) y
  por cada una que envía o publica (5), con un intérprete doble que obedece al documento; el servicio exige el clic, la
  ruta de confirmación rechaza a los programas y la propuesta avisa de las instrucciones. (RF-90, RF-91)
  Hecho cuando: `pytest -q tests/test_asistente_inyeccion.py` en verde con su rojo por aserción en la base (faf67626), y
  `tests/test_modelo_provisional.py`, `tests/test_asistente_equipo_web.py`, `tests/test_asistente_nube_correo.py`,
  `tests/test_asistente_web.py` y `tests/test_asistente_operativo.py` sin cambios en verde. Rojo y verde de sus funciones
  ejecutados sin pytest (B44); el pytest lo corre el integrador d8.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T27 El modelo en uso con una parte de las tareas del contrato se abre y se compara (diagnóstico de la T22 del
  2026-11-24). (RF-92, RF-84)
  Hecho cuando: `tests/test_contrato_tareas_compatible.py` (070:RF-92) en verde, con rojo por aserción en la base, y
  `tests/test_afinado_ordenes.py`, `tests/test_destilacion_integral.py` y `tests/test_modelo_provisional.py` en verde.
      Hecho el 2026-11-24 (d8): rojo en la base (2 failed: «contrato de tareas o entidades incompatible» al abrir el
      modelo recortado y en `motivo_no_disponible`), D:/csg/PM_IMPL/N12/070_T27/rojo.log; verde con
      `codificador_ordenes.contrato_compatible` en `modelo_desde` y en `cargar_alumno` (159 passed con sus vecinas),
      D:/csg/PM_IMPL/N12/070_T27/verde.log. Con el modelo real en uso (prov-8fd8a405, 49 de 68 tareas),
      `motivo_no_disponible()` pasa de ese error a ninguno.
- [ ] T28 [GPU] Mejorar el candidato rechazado en la T22: separar las tareas vecinas que confunde y repetir la corrida
  con la no regresión ya medible (T27). (RF-84, RF-92, RF-93, RF-94)
  Causas medidas el 2026-11-24 (asistente_integral_20261124.json): en calibración buscar_maxima→sistema_completo (40),
  cruzar_clientes→alimentadores_completo (36), descargar_resultados→unir (36), proyecto_entero→enviar_informe (11);
  en selección estado→ninguna (10), proyecto_entero→sistema_completo (10), leer_solicitud→pit_expediente (7) y
  →subir_fuente_empresa (6). Ejecución sola: sintéticas 0,964 y maestro 0,946, bajo 0,98.
  Hecho cuando: el candidato pasa sus puertas, o queda el modelo en uso con el diagnóstico de lo que aún confunde.
      Código, 2026-11-24 (d8, wt_d8_t28): `PARAFRASIS_070_T28` en `curriculo_maestro.py` (14 tareas, 12 frases cada
      una, elegidas por la selección y la calibración, sin mirar los textos de las pruebas que deciden), su bucle en
      `destilacion_integral.preparar_corpus` (semilla 7331, origen `parafrasis_070_t28`, en el manifiesto y en
      `curriculo_hash`) y las paráfrasis en `fuga_evaluacion.textos_que_entrenan`. Pruebas:
      `tests/test_curriculo_070_t28.py` (070:RF-93), rojo por aserción de la fuga con el código anterior
      (D:/csg/PM_IMPL/N12/t28_rojo.log) y verde con sus vecinas (269 passed, D:/csg/PM_IMPL/N12/t28_vecinas.log).
      Corrida del 2026-11-24 14:19 (wt_d8_t28, fd9126de): ensayo rc=0; la corrida la cortó la guardia a las 15:33 en la
      vuelta 2 de 5 (0,85 GiB libres, rc=137; D:/csg/PM_IMPL/GPU_BLOQUE/070_T28_noche). Medido con su corpus: el
      codificador deja el proceso en 1,25 GiB y la caché del prefijo añade 2,75 GiB (D:/csg/PM_IMPL/N12/medir_memoria_t28.py).
      Código (RF-94): `afinado_ordenes.FilasPrefijo` con los estados en disco; la corrida la pide en su carpeta
      `cache_prefijo`. Con el mismo corpus el proceso queda en 1,91 GiB en vez de 4,00 y los 2,09 GiB de estados están en
      disco (D:/csg/PM_IMPL/N12/memoria_disco.txt). Pruebas: `tests/test_cache_prefijo_disco.py` (070:RF-94), con sus
      vecinas 206 passed (D:/csg/PM_IMPL/N12/rf94_vecinas.log).
      Queda la corrida en la GPU con la no regresión ya medible (T27).
      Corrida del 2026-11-24 17:49–19:43 (wt_d8_t28, 8de18dec, sin cortes): RECHAZADO por poco y sigue el modelo en uso.
      Ejecución sola: sintéticas 0,972 y maestro 0,959 (antes 0,964 y 0,946; puerta 0,98); humanas 0,698 (antes 0,651); la no
      regresión ya se mide y no bloquea; acierto total en sintéticas 0,816 frente a 0,829 del modelo en uso. En selección
      buscar_maxima, cruzar_clientes y sistema_completo a 1,000 y proyecto_entero de 0,44 a 0,69, pero carga_nueva_sola de
      0,82 a 0,35: sus paráfrasis decían «sin estudio», «sin evaluar», «sin informe», y el modelo aprende las palabras de
      evaluar_carga_nueva aunque vayan negadas; descargar_resultados → unir sigue (38 filas) porque «junta» solo va con
      unir; leer_solicitud 0,65. Evidencia: D:/csg/PM_IMPL/GPU_BLOQUE/070_T28_noche.
      Segunda vuelta, 2026-11-24 (d8): carga_nueva_sola con sus propios verbos y sin negaciones; descargar_resultados con
      «junta … para descargarlos»; leer_solicitud sin «documento» ni «papeles». Comprobadas sin choque con lo que se mide
      (tests/test_curriculo_070_t28.py, 6 passed). Queda su corrida en la GPU.
