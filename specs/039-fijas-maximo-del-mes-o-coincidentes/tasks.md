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
      Hecho cuando: `npm run build` sin errores y la comparación de NA203 vista en el navegador real.
      Hecho el 2026-10-31: un solo `SelectorCriterio` (2.3 y «Recalibrar»), «coincidente» por
      defecto; `--criterio-fijas` en `sistema_web.py` y en la recalibración rápida. En el navegador,
      NA203 con septiembre de 2026 (máxima 29/09 15:30, 10 043 kW y 1 777 kvar): «máximo del mes»
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
- [x] T8. [DIgSILENT] CA101_CHN102 recalibrado desde la web con un cliente a su máxima. (RF-12, RF-17 a RF-19)
      Hecho cuando: el informe de la calibración lista ese cliente con su registro, sus kW y sus kvar de máxima, la
      cabecera cuadra dentro de la tolerancia y la tabla, vista en el navegador real, muestra sus dos valores.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T4. [DIgSILENT] NA203 recalibrado con los dos criterios desde la web. (Todos)
      Hecho cuando: «máximo del mes» da 7 707,5 kW y 3 725,5 kvar de fijas y «coincidente» con
      2026-09 el registro de cada fija en el instante de su máxima de cabecera.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
