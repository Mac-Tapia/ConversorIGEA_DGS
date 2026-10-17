# Tareas 021 — Maniobras y SED en el diagrama, curvas y central térmica

Plan: `specs/021-maniobras-y-sed-en-el-diagrama/plan.md`. Una tarea cada vez, pruebas
primero. Al terminarla: suite en verde, `- [x]`, y parar.

Bloque 1 · Maniobras de los puentes

- [x] T1. Plegar el equipo del puente en el cubículo de la línea vecina, con el lado de
      aguas arriba si valen los dos. (RF-1, RF-2, RF-3, RF-5, RF-6)
      Hecho cuando: `pytest -q tests/test_puentes.py` en verde.
      Resultado del 2026-10-17: `puentes._plegar`, decidido sobre la red antes de plegar
      (extremos fijados al empezar) y por `section_id`; una barra vale solo con el puente
      y una línea (con una carga, SED, banco u otro puente no, para no dejarlos detrás
      del fusible); el cubículo ocupado ya se respeta (las pruebas de RF-4 son la T2).
      `InformePuentes.plegados` nuevo. Con los TXT reales, 96 alimentadores y 12 388
      equipos plegados: maniobras, líneas y cargas iguales, una barra menos por equipo.
      Línea base de la 001 (`output/linea_base_001.json`) regenerada a propósito: cambian
      92 DGS; lote ok en TXT (96) y Access (101). 20 pruebas de puentes y la suite
      sintética en verde (una intermitente de `test_demanda_medida`, que pasa sola).
- [x] T2. Cubículo ocupado y fuente: queda `ElmCoup`. (RF-4)
      Hecho cuando: `pytest -q tests/test_puentes.py` en verde.
      Resultado del 2026-10-17: cuatro pruebas nuevas, sin cambiar el código de la T1:
      ocupado por un lado pliega por el otro; ocupado a los dos lados queda `ElmCoup`; el
      interruptor de cabecera en un puente de la fuente pasa a la primera línea en la
      barra de la fuente, que conserva su nombre; mismo resultado con los tramos en otro
      orden. 24 pruebas en verde.
- [x] T3. Fusible del trafomix sin destino quitado y contado; completitud; `SIN_REGLAS`.
      (RF-7, RF-8, RF-9, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_puentes.py tests/test_reglas*.py` en verde.
      Resultado del 2026-10-17: `trafomix._quitar_maniobras_sin_destino` (solo barras de
      un trafomix excluido que se quedan sin nada; con carga de MT conservada, el fusible
      se queda) e `InformeTrafomix.maniobras_quitadas`; la completitud cuenta los
      `ElmCoup` escritos en el DGS (menos uno por SED y los enlaces), no los del informe
      de puentes, y suma los quitados. NA203 + NA205 por Access: de 550 `ElmCoup`, 88
      barras muertas y 119 barras hechas solo de acopladores a 32, 0 y 0; 446 `StaSwitch`
      + 32 `ElmCoup` + 92 quitados = 570 maniobras de la entrada. Línea base de la 001
      regenerada otra vez (la herramienta usa el perfil de la máquina, con trafomix).
      Suite con TXT y Access: 2276 en verde y las 3 de la línea base tras regenerarla.
- [x] T4. Lectores de maniobras con el equipo en el cubículo: transferencia, oráculo e
      informe de estudio. (RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_transferencia_pf*.py tests/test_informes.py
      tests/test_caso_base_verificado.py` en verde.
      Resultado del 2026-10-17: sin cambios de código; los tres ya leían el equipo en el
      extremo de su línea (`Red.interruptores` y `Camino` de la transferencia miran los
      `StaSwitch` de los cubículos; el oráculo pone `model.devices` como maniobra de
      línea; el trecho del informe une tramos por su barra común). Tres pruebas nuevas en
      `test_puentes.py`: el seccionador plegado sale con `aUsage=dct` en el cubículo de
      su línea y `es_seccionador` lo reconoce; abierto en el oráculo deja sin tensión lo
      de detrás; dos tramos con barra común son un solo trecho. 167 pruebas en verde.
- [x] T5. Datos reales: NA203 + NA205 por la vía Access y TXT en las dos disposiciones; DGS
      idéntico con `workers=1` y `workers>1`. (RF-6, RF-10)
      Hecho cuando: la suite con las variables `IGEA_*` e `IGEA_MDB` en verde.
      Resultado del 2026-10-17: suite completa con TXT y Access en verde (T3); con el
      código final del bloque, `test_linea_base_001` (TXT con 1 y 4 procesos y Access,
      byte a byte), `test_export_layouts`, `test_reglas` (las dos disposiciones) y
      `test_access_input`: 62 en verde. El plegado actúa sobre el modelo, después del
      lector, así que las dos disposiciones dan el mismo resultado.

Bloque 2 · SED unida a su barra

- [x] T6. Sonda en DIgSILENT sobre una copia de NA203_NA205 importado: dos variantes del
      DGS de una SED y cuál sigue al mover la SED. Resuelve la duda abierta. (RF-12)
      Hecho cuando: la variante elegida queda escrita en la spec, sin
      `[NECESITA ACLARACIÓN]`, y la copia borrada.
      Resultado del 2026-10-17: la variante sale del NA205 que exporta PowerFactory (131
      SED sin conectores propios, la línea entra en la barra de MT interior; solo 4 con
      barra fuera y acoplador). En vez de dos variantes se importó la elegida (T7) en
      «Pruebas 021»; el operador movió SE50195 y el cable la siguió. Los dos proyectos de
      prueba se borran al cerrar la tarea.
- [x] T7. La SED unida a su barra en el DGS, con lo que dijo T6. (RF-12, RF-13, RF-14)
      Hecho cuando: `pytest -q tests/test_dgs_v2.py tests/test_graphics_sed.py` en verde.
      Resultado del 2026-10-17: `dgs.seds_con_barra_propia` (una SED sola en su barra y
      que no es la de una fuente) la escriben `dgs.py` y `validate.py`: la barra va dentro
      del `ElmSubstat` con su nombre, sin barra de MT aparte, sin `SW_SE…` y sin
      `PointTerm`; dos SED en una barra siguen con su acoplador. La completitud cuenta los
      `ElmCoup` fuera de las SED. NA203 + NA205 en DIgSILENT a escala real
      («NA203_NA205_142712»): converge sin relajar, mismas tensiones (0,924–1,000 pu),
      idéntico al DGS; `PointTerm` de 1114 a 428 y pares de puntos pegados de 117 a 3.
      `tools/convertir_grupos_mdb.py` importa ahora a escala real por defecto (A0 solo si
      se pide): con A0 el centro de NA203 + NA205 se amontonaba. Línea base de la 001
      regenerada. Fallo intermitente previo: dos pruebas de `test_demanda_medida` fallan
      solo en la suite completa y pasan solas (ya antes de este bloque).

Bloque 3 · Curvas de varios alimentadores

- [x] T8. Gráfica con varias series, leyenda con conmutador y arrastre común; un solo
      alimentador como antes. (RF-17 a RF-24)
      Hecho cuando: `pytest -q tests/test_curva_cabecera_front.py` en verde y
      `npm run build` sin errores.
      Resultado del 2026-10-17: `CurvaCabecera` dibuja una lista de series (`SerieCurva`)
      pedidas con `Promise.allSettled`, una por alimentador con el medidor elegido o el
      primero; colores `--serie-0…7` con modo oscuro; leyenda con `aria-pressed` que oculta
      sin volver a pedir; un alimentador sigue como en la 006. Probado en el navegador con
      IN111 + TA225 (proyecto aceptado del 2026-10-15): las dos curvas con su máxima
      (9 132 y 4 586 kW), ocultar TA225 sin petición nueva y arrastrar pide el mismo tramo
      a las dos (1 033 registros). 15 pruebas del front en verde, `tsc` y `npm run build`
      sin errores. En el camino se corrigió un fallo del lector que hacía fallar a veces
      dos pruebas sorteadas: python-calamine lee el registro de las 00:00 como fecha sin
      hora; la máxima a medianoche salía sin su hora (prueba fija nueva en
      `test_demanda_medida.py`; 400 semillas sin fallos).

Bloque 4 · Central térmica

- [x] T9. Medidas de la central: registros comunes, signos por balance, zonas, descarte por
      3·IQR y máxima de demanda. (RF-28 a RF-34)
      Hecho cuando: `pytest -q tests/test_demanda_medida.py` en verde; con
      `IGEA_DEMANDA_DIR`, NA205 da el registro del 2026-08-20 16:45.
      Resultado del 2026-10-17: `demanda_medida.demanda_con_central` sobre las cuatro
      curvas `(fecha, kW, kVAR)` que ya guarda la máxima (`MaximaCabecera.curva`):
      registros comunes, signos por la menor mediana de desbalance (desempate fijo),
      rechazo por encima del 5 % de la generación máxima, zonas y descarte por 3·IQR;
      `MaximaConCentral` con zonas, generación, cabecera y la máxima de cabecera de
      antes. Seis pruebas sintéticas sorteadas y la real: NA205 con CT_BH4 NA, CTNA_BH2 y
      CTNA_BH1 da 2026-08-20 16:45, signos (1, 1), central generando.
- [x] T10. Declaración de la central en la web y en el perfil; medidores sin alimentador de
      la red ofrecidos. (RF-25, RF-26, RF-27)
      Hecho cuando: `pytest -q tests/test_demanda_medida_web.py
      tests/test_perfil_empresa.py tests/test_ajuste_cabecera_web.py` en verde.
      Resultado del 2026-10-17: `perfil_empresa.centrales_termicas` (sección del perfil
      local, porque es un dato de la red y no una convención); rutas
      `demanda/medidores-externos` (los del libro cuyo alimentador no es del proyecto ni de
      la entrada cargada, y las centrales del perfil) y `demanda/cabecera/{job}/central`
      (la máxima con central sobre las curvas ya leídas). En 2.2, columna «Central
      térmica» por alimentador: tres desplegables, la barra y «Quitar central»; sus
      medidores van en el mismo trabajo de la máxima con el alimentador «Central …», que
      el ajuste no toma por cabecera. 2.4 muestra la máxima de demanda frente a la de
      cabecera (RF-34). Pruebas de la API, del perfil y del front en verde (121 con las de
      la web y el inventario); `tsc` y `npm run build` sin errores. La generación de prueba
      de la T9 sorteaba distinto con la central parada (86 de 300 semillas fallaban):
      corregida, 500 semillas sin fallos. Falta verlo en el navegador con NA205, que no
      está entre los proyectos de la carpeta de la web: queda para la T14.
- [ ] T11. Objetivo y cuadre de dos zonas; sin central, igual que antes. (RF-33, RF-40,
      RF-41, RF-43, RF-45, RF-46)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera.py` en verde.
- [ ] T12. La central en «Sin proyecto» y las zonas en el guion, con su informe. (RF-35 a
      RF-39, RF-42, RF-44)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
- [ ] T13. Curvas de la central en la gráfica, con las dos máximas marcadas. (RF-47, RF-48,
      RF-49)
      Hecho cuando: `pytest -q tests/test_curva_cabecera_front.py` en verde y
      `npm run build` sin errores.

Cierre

- [ ] T14. DIgSILENT: NA203 + NA205 reimportado (sin grupos de puntos, SE50195 movida con
      el cable unido, «Caso base» con el mismo flujo, transferencia con los mismos
      seccionadores) y NA205 calibrado con su central desde la web. (Todos)
      Hecho cuando: los criterios de finalización de la spec, comprobados en DIgSILENT.
- [ ] T15. Validación: cada RF citado por al menos una prueba y en verde; `CODIGO_FUENTE.md`
      al día. (Todos)
      Hecho cuando: `grep -rnoE "021:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-49 y
      `pytest -q tests/test_inventario.py` en verde.
