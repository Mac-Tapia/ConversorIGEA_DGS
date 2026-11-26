# Tareas — Spec 039

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. `criterio_fijas` en el plan del ajuste y en `demanda_clientes`; bloqueo sin el registro
      coincidente, con el periodo de la misma fecha; criterio en el informe. (RF-1 a RF-4, RF-6)
      Hecho cuando: `pytest -q tests/test_tabla_en_el_instante.py tests/test_ajuste_cabecera_web.py` en verde.
      Hecho el 2026-10-31: `solo_instante` en `registros_de_maxima` (hoja sin el instante → `None`),
      `criterio` en el cruce y `criterio_fijas` en el plan (`FIJAS_SIN_REGISTRO_COINCIDENTE`), en
      `recalibrar_sistema` y en el informe del guion; 57 + 8 + 16 pruebas en verde.
- [x] T2. `comparar_criterios_fijas` en el servicio, con su ruta. (RF-5)
      Hecho cuando: `pytest -q tests/test_tabla_en_el_instante.py` en verde con un libro sintético.
      Hecho el 2026-10-31: reutiliza la tabla (`_clientes_en_sus_maximas`) con los dos criterios;
      la calibración guardada lleva ahora la cabecera simulada y los kvar de los bancos, de donde
      sale la Q de la red; `POST /demanda/clientes/comparar` como trabajo del motor.
- [x] T3. Web: selector del criterio, botón y tablas de la comparación; `--criterio-fijas` en
      `tools/sistema_web.py`. (RF-1, RF-5)
      Hecho cuando: `npm run build` sin errores y la comparación de NA293 vista en el navegador real.
      Hecho el 2026-10-31: un solo `SelectorCriterio` (2.3 y «Recalibrar»), «coincidente» por
      defecto; `--criterio-fijas` en `sistema_web.py` y en la recalibración rápida. En el navegador,
      NA293 con septiembre de 2026 (máxima 29/09 15:30, 10 043 kW y 1 777 kvar): «máximo del mes»
      7 707,5 kW y 3 725,5 kvar; «coincidente» 6 505,9 kW y 2 906,1 kvar; red y bancos −278,1 kvar
      del último informe; quedan −851,1 y −1 670,4 kvar para las escaladas.
- [x] T5. Criterio por alimentador: `criterio_por_alimentador` en el cruce, en el plan y en `sistema_web.py`
      (`--maximo-mes COD…`), y el desplegable en 2.3 y en «Recalibrar». (RF-7, RF-8)
      Hecho cuando: `pytest -q tests/test_tabla_en_el_instante.py tests/test_ajuste_cabecera_web.py tests/test_escaneo.py`
      en verde, `npm run build` sin errores y el desplegable comprobado en el navegador real.
      Hecho el 2026-11-05: 88 pruebas en verde, `npm run build` sin errores; en el navegador, el desplegable en 2.3 y en
      «Recalibrar» de Pisco.
- [x] T6. Cliente a su máxima en el servidor: los dos valores y la diferencia en la tabla, la selección guardada en el
      espacio (`PUT /demanda/clientes/a-su-maxima`), `a_su_maxima` en el cruce, en el plan del ajuste, en
      `RecalibrarIn` y en `sistema_web.py --a-su-maxima`, y la lista en el informe del guion. (RF-9, RF-10, RF-12,
      RF-14 a RF-16, RF-18 a RF-22)
      Hecho cuando: `pytest -q tests/test_fijas_a_su_maxima.py tests/test_tabla_en_el_instante.py tests/test_ajuste_cabecera_web.py
      tests/test_q_con_bancos.py tests/test_sistema_web.py` en verde.
      Hecho el 2026-11-07: 11 pruebas nuevas, que fallan todas sin el cambio; 158 en verde con las de esos ficheros
      y `tests/test_escaneo.py`.
- [x] T7. Web: columnas de los dos valores y de la diferencia, orden y filtro por la diferencia, casilla «a su máxima»
      con «Desmarcar todos», y el botón «Recalibrar con estos criterios» en 2.3. (RF-9 a RF-14, RF-17)
      Hecho cuando: `npm run build` sin errores y `pytest -q tests/test_fijas_a_su_maxima.py` en verde.
      Hecho el 2026-11-07: `npm ci && npm run build` y `tsc --noEmit` sin errores; la vista en el navegador real
      queda con la prueba en DIgSILENT (T8).
- [x] T8. [DIgSILENT] CA191_CHN192 recalibrado desde la web con un cliente a su máxima. (RF-12, RF-17 a RF-19)
      Hecho cuando: el informe de la calibración lista ese cliente con su registro, sus kW y sus kvar de máxima, la
      cabecera cuadra dentro de la tolerancia y la tabla, vista en el navegador real, muestra sus dos valores.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T4. [DIgSILENT] NA293 recalibrado con los dos criterios desde la web. (Todos)
      Hecho cuando: «máximo del mes» da 7 707,5 kW y 3 725,5 kvar de fijas y «coincidente» con
      2026-09 el registro de cada fija en el instante de su máxima de cabecera.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T9. MEJ10-FIJAS (orden del usuario del 20-11): `correccion_vigente` y `aplicar_correccion` en `aplicacion/demanda_medida.py`; `Workspace.correcciones_medidor`, `registrar_correccion_medidor` y la ruta `correccion-medidor` (GET y PUT); la tabla, el plan y la evidencia de 015:RF-73 con la corrección; el botón de la fila en `DemandaMedida.tsx`. (RF-23)
      Hecho cuando: rojo por aserción sobre 2f9de358 y verde con `tests/test_demanda_medida.py -k rf23` y `tests/test_tabla_en_el_instante.py -k rf23`, `npm test` y `npm run typecheck`; la corrida en DIgSILENT la decide d8.
      Hecho el 2026-11-20 (d8, cierre de la fila gSIG por orden del usuario «nada abierto»): rojo D:/csg/PM_IMPL/MEJ10_FIJAS/rojo.log (2 F de rf23); npm y tipos en D:/csg/PM_IMPL/MEJ567/npm_test_20261120_163024.log y
      D:/csg/PM_IMPL/MEJ567/checklist.txt.tsc; verde integrado del hueco de MEJ567 sobre c4326366 (D:/csg/PM_IMPL/MEJ567/verde_20261120_163024.log, 2423 passed, rc=0;
      npm_test_20261120_163024.log y e2e_20261120_163024.log) y la puerta gSIG que integra esta casilla (0 fallidas, 0 omitidas).
- [x] T10. MEJ27-FIJAS (orden del usuario del 21-11): `_energia_de_un_dia` con días completos del mes; `registros_atipicos`, `cabecera_estable`, `diagnostico_fija_imposible` y `MOTIVOS_QUE_LIBERAN` en `dominio/ajuste_cabecera.py`; `_evidencia_fijas` con el diagnóstico, `_corregir_fila_automaticamente`, `_escalar_fila` y `_reparar_registro_excluido` en la web, y `registrar_correccion_medidor` con `origen` y `evidencia`; el guion libera las fijas imposibles y sigue. (RF-24, RF-25)
      Hecho cuando: rojo por aserción sobre e98f3f89 y verde con `tests/test_fijas_imposibles.py`, las vecinas y las de gobierno (D:/csg/PM_IMPL/MEJ27_FIJAS/).
- [x] T11. [DIgSILENT] La corrida A del bloque del 20-11 (cuatro alimentadores de dos SET, por `tools/sistema_web.py` sobre la copia del espacio) repetida sin la corrección manual del medidor: el conversor deduce solo el FM (origen `automatico`) y los cuatro quedan válidos con `VERIFICADO_PERSISTENCIA`. (RF-24, RF-25)
      Hecho cuando: el informe de la corrida dice la corrección automática con su evidencia y ningún alimentador con `FIJA_A_REVISAR` ni rc=2; la orden está en D:/csg/PM_IMPL/MEJ27_FIJAS/HANDOFF.md.
      Hecho el 2026-11-21 (implementador de d8, wt_d8_fijas27 = e98f3f89 + MEJ27, web propia 8794 sobre la copia del espacio del bloque DIgSILENT): la corrida A del 20-11 repetida sin ninguna corrección manual del medidor (las 4 retiradas de la copia, con respaldo). El conversor dedujo solo el FM (×0,3000, origen `automatico`, con su evidencia: FM 545,4545 → 1818,1818, energía ×3,82 y cabecera ×0,89) y los cuatro alimentadores quedaron válidos en 6 flujos con `VERIFICADO_PERSISTENCIA`, sin `FIJA_A_REVISAR` y rc=0. Evidencia: D:/csg/PM_IMPL/MEJ27_FIJAS/corrida_039_T11/.
- [x] T12. La corrección del medidor de cabecera, en el espacio y al leer la cabecera. (RF-26)
      Hecho cuando: `tests/test_demanda_medida.py` y `tests/test_tabla_en_el_instante.py` (039:RF-26) en verde con su
      rojo por aserción; el control «Corregir un medidor de cabecera» en 2.2, con `tsc` y `npm run build`.
      Hecho el 2026-11-26: rojo `D:/csg/PM_IMPL/CORRECCION_CABECERA/rojo.log`; verde 185 passed (`verde.log`).
