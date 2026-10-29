# Tareas — Spec 028

Estado: pedida por el usuario el 2026-10-28; T1 a T5 hechas el mismo día (`tests/test_escaneo.py`,
`test_ajuste_proyecto_guion.py -k segunda`, `test_sistema_web.py -k escanea`); falta T6 en DIgSILENT,
cuando el usuario ponga a mano la central de NA205.

- [x] T1. `escaneo.py`: origen por los prefijos del conversor, resumen y barra de la central.
      (RF-3, RF-4, RF-5, RF-7, RF-11, RF-12)
      Hecho cuando: `pytest -q tests/test_escaneo.py -k reglas` en verde con nombres sorteados.
- [x] T2. `tools/escanear_alimentador_pf.py`, de solo lectura, con `--help` sin DIgSILENT.
      (RF-1, RF-2, RF-4, RF-5, RF-6, RF-8)
      Hecho cuando: prueba con `fake_pf` en verde: generadores, bancos, variaciones y un
      alimentador que no está.
- [x] T3. Servicio, ruta y botón en la web; la central sin barra toma la del escaneo.
      (RF-9 a RF-12)
      Hecho cuando: prueba de la API y del front compilado en verde.
- [x] T4. Generador del operador en la barra de la central y sin bancos repetidos. (RF-13, RF-14)
      Hecho cuando: pruebas con `fake_pf` en verde.
- [x] T5. `tools/sistema_web.py` escanea antes de calibrar. (RF-15)
      Hecho cuando: prueba de `sistema_web` en verde.
- [ ] T6. [DIgSILENT] Prueba en DIgSILENT: escanear Nasca con la central de NA205 puesta a mano por el
      usuario y recalibrar.
      Hecho cuando: el escaneo nombra el generador de NA205 y su barra, y la calibración lo usa.
      Pendiente (usuario, 2026-10-28: «no puedo modificar el DIgSILENT a mano, deja pendiente de
      central térmica a mano»): la central de NA205 no está aún en el proyecto. El escaneo en
      DIgSILENT ya corre (Nasca: 8 bancos de calibración en NA205 y 7 en NA203, ningún generador).
- [x] T7. Recalibrar sin bloqueos: escaneo automático al simular y aplicar, tramos nuevos frente al
      DGS aceptado, generador del operador sin central y central sin barra que no detiene.
      (RF-16 a RF-20)
      Hecho cuando: pruebas con `fake_pf` y de la web en verde, y el escaneo de Chincha en
      DIgSILENT con sus tramos nuevos.
      Hecho el 2026-10-28: pruebas en verde; en DIgSILENT, el escaneo de Chincha compara con los
      3358 tramos de su DGS aceptado (0 nuevos en el proyecto recién importado) y ve los bancos de
      calibración de TM106 y PN107; la calibración desde la web escanea antes y no se detiene.
- [x] T8. Botón «Recalibrar» con su ruta, que corre `tools/sistema_web.py` sin reconvertir.
      (RF-21 a RF-23)
      Hecho cuando: prueba de la API y del front en verde y una recalibración de Chincha desde el
      botón.
      Hecho el 2026-10-28: pruebas en verde; en la web, «Recalibrar» sobre
      20261028-103442_IGEA_SISTEMA_CHINCHA con 2026-07: 26 válidos y 0 con fallos en 261 s. La
      primera vez se esperaba a sí mismo (`sistema_web.py` esperaba al trabajo que lo lanzó):
      arreglado con `IGEA_TRABAJO_PROPIO`, también para el asistente y el agente.
- [x] T9. Recalibrar el proyecto de uno o varios alimentadores: ruta, botón y `sistema_web.py
      --red`. (RF-23 a RF-25)
      Hecho cuando: pruebas de la API y de la herramienta en verde, y en DIgSILENT, desde la web,
      un alimentador y dos unidos convertidos, calibrados, recalibrados y con su informe de estudio.
      Continuación 2026-10-28: CLI, API y botón implementados; la selección guardada manda sobre
      el nombre del proyecto, el grupo usa el mismo nombre seguro que la conversión y cada red
      usa máximas individuales. Se detiene ante trabajos fallidos, conversiones individuales
      omitidas/incompletas y ausencia de validación nativa. Verificación: 147 pruebas aprobadas
      en `test_sistema_web.py`, `test_escaneo.py`, `test_ajuste_cabecera_web.py`,
      `test_central_termica_front.py` y `test_demanda_medida_web.py`; `npm run build` aprobado;
      `git diff --check` sin errores. Las pruebas usan dobles del motor: no prueban aceptación
      eléctrica. La API local respondió a la consulta de lectura del espacio 5f11283a33c94ea5:
      fuente sin cargar y sin trabajos activos; no se ejecutó el recorrido nativo ni informes
      en esta continuación. T9 sigue abierta hasta obtener esa evidencia. Sustento: `research.md`.
      2026-10-29: un alimentador convertido, calibrado y recalibrado desde la web con `--red` (SM218 y
      CA101 de la entrega 231026, VÁLIDOS); dos unidos, IN111 + TA225 calibrados en DIgSILENT (025).
      Falta su informe de estudio: espera las cargas nuevas que el usuario sube en bloque (3.3).
      Código cerrado el 2026-10-29 (033): CLI, API y botón con sus pruebas en verde (028:RF-23 a RF-25); la prueba en DIgSILENT pasa a T11.
- [x] T10. Tramos cambiados a mano en el escaneo: los del DGS aceptado que graba una variación
      del operador, con su variación, tipo y longitud; resumen y columna en la tabla. (RF-26)
      Hecho cuando: `pytest -q tests/test_escaneo.py` en verde y en DIgSILENT el escaneo de CA101
      nombra la variación del operador.
      Hecho el 2026-10-28: suite del escaneo en verde; en DIgSILENT el escaneo de CA101 nombró
      «Prueba_operador_032» como del operador (vacía: sin tramos que listar).
- [ ] T11. [DIgSILENT] Desde la web, un alimentador y dos unidos convertidos, calibrados,
      recalibrados y con su informe de estudio (sigue a T9). (RF-23 a RF-25)
      Hecho cuando: los dos proyectos válidos tras recalibrar y con su informe.
