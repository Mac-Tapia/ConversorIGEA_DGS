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
- [ ] T4. [DIgSILENT] NA203 recalibrado con los dos criterios desde la web. (Todos)
      Hecho cuando: «máximo del mes» da 7 707,5 kW y 3 725,5 kvar de fijas y «coincidente» con
      2026-09 el registro de cada fija en el instante de su máxima de cabecera.
