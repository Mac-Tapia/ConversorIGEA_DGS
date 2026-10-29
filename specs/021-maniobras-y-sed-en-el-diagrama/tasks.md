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
- [x] T11. Objetivo y cuadre de dos zonas; sin central, igual que antes. (RF-33, RF-40,
      RF-41, RF-43, RF-45, RF-46)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera.py` en verde.
      Resultado del 2026-10-17: `ObjetivoZonas` y `objetivo_zonas_de` (de la máxima con
      central de la web), `MedidaZonas` y `cuadrar_zonas`: un factor por zona, cada uno
      con su secante sobre la medida de su zona en el mismo flujo, y los mismos pasos que
      `cuadrar` si no converge; una zona con solo clientes fijos queda a factor 1 (sus P y
      Q), se avisa y no decide; `CuadreZonas.resumen` para el informe. Cinco pruebas con
      una red de juguete de dos zonas; `cuadrar` sin central, igual. Dos pruebas del front
      que fijaban líneas cambiadas en la T10 (006 y 008) puestas al día: 195 en verde.
- [x] T12. La central en «Sin proyecto» y las zonas en el guion, con su informe. (RF-35 a
      RF-39, RF-42, RF-44)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
      Resultado del 2026-10-17: sonda en una copia de NA203 + NA205 (borrada): un
      `ElmGenstat` con `av_mode='constq'` inyecta la P y Q escritas, el flujo de cada
      línea sale con `m:Psum` del lado de la barra, y la etapa de la variación sigue
      grabando aunque se desactive y active (no hay llamada para dejar de grabar): el
      guion escribe la marca fija o escalable con la variación de la central apagada y
      después la crea o la reactiva, y en el cuadre solo escribe el escenario. En el
      guion, `_ejecutar_con_central` (con `barra_de_la_central`, `cargas_por_zona`,
      `central_en_sin_proyecto` y `medir_zonas`, que cuenta también el transformador de
      una SED en esa barra), validación nativa por zona y «Con proyecto» con su P y Q. En
      la web, `CentralIn` en el plan y `_central_del_plan` (barra obligatoria, balance
      roto: aviso y sin central, mes de los clientes el de la máxima de demanda).
      `fake_pf` calcula el flujo de cada línea y la inyección de la central. Pruebas en
      `test_ajuste_central_guion.py` (7), `test_ajuste_cabecera_web.py` (4) y el front.
      La prueba con NA205 en DIgSILENT desde la web queda para la T14.
- [x] T13. Curvas de la central en la gráfica, con las dos máximas marcadas. (RF-47, RF-48,
      RF-49)
      Hecho cuando: `pytest -q tests/test_curva_cabecera_front.py` en verde y
      `npm run build` sin errores.
      Resultado del 2026-10-17: la demanda registro a registro se calcula en el servidor
      (`demanda_medida.curva_de_demanda`, ruta `demanda/cabecera/{job}/central/curva`)
      porque las curvas reducidas de cada medidor no caen en las mismas fechas; su máxima
      marcada es la del objetivo, que descarta las transferencias. En la gráfica, por
      alimentador con central: cabecera, demanda (objetivo), generación, llegada y
      salida, como series más (mismo tramo y leyenda, RF-49). Pruebas del lector, de la
      API y del front en verde; `tsc` y `npm run build` sin errores.

Cierre

- [x] T14. DIgSILENT: NA203 + NA205 reimportado (sin grupos de puntos, SE50195 movida con
      el cable unido, «Caso base» con el mismo flujo, transferencia con los mismos
      seccionadores) y NA205 calibrado con su central desde la web. (Todos)
      Hecho cuando: los criterios de finalización de la spec, comprobados en DIgSILENT.
      Resultado del 2026-10-17:
      · Diagrama: NA203 + NA205 reimportado a escala real («NA203_NA205_142712», borrado):
        converge sin relajar con las mismas tensiones, idéntico al DGS, `PointTerm` de 1114
        a 428 y pares de puntos pegados de 117 a 3; el operador movió SE50195 y el cable la
        siguió.
      · Central: la de «NA203 NA205v1» (GENERADOR NASCA en Terminal(80), entre «Llegada de
        C. G.» y «Salida de C. G.») cae en el tramo SEC_1091_1046754 del proyecto del
        conversor, 1,17 km aguas arriba de 1527 (= 982654P(1) de v1, a 0,8 m), donde no
        hay nodo; con la barra 1720 el reparto de las zonas es el de v1 (2 775 kVA aguas
        arriba, 16 304 aguas abajo). Desde la web, NA205 con su central: máxima de demanda
        10 753,3 kW el 2026-08-20 16:45 (532 registros descartados) y su gráfica. El plan
        de la web, en una copia de «20261016-160231_IGEA_NA203_NA205» (borrada): central
        en 1720 con 9 605 kW / −593 kvar solo en «Sin proyecto» (el «Caso base» sin ella),
        15 cargas aguas arriba y 88 aguas abajo, cuadrado en 3 flujos sin remedios
        (−0,08 % y −0,01 %), validación nativa válida en las dos zonas, cabecera calculada
        1 146,5 kW frente a 1 123,1 kW medidos.
      · Pendiente fuera de esta spec: aplicarlo en el proyecto real necesita el libro de
        clientes de agosto de 2026 (la máxima de demanda es de agosto y solo hay de enero a
        julio: CLIENT_PERIOD_UNKNOWN, como ya pasaba con la máxima de cabecera) o la 013
        RF-11 (máxima dentro del mes elegido). La transferencia con los seccionadores
        plegados se probó con el doble (T4), no en DIgSILENT. Con la red sin cargar en el
        espacio, el desplegable de la central ofrece todos los medidores del libro que no
        son del proyecto (107), no solo los de la central.
- [x] T15. Validación: cada RF citado por al menos una prueba y en verde; `CODIGO_FUENTE.md`
      al día. (Todos)
      Hecho cuando: `grep -rnoE "021:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-49 y
      `pytest -q tests/test_inventario.py` en verde.
      Resultado del 2026-10-17: RF-1 a RF-49 citados por alguna prueba; suite completa
      con TXT, Access y libros de demanda, 2333 en verde (inventario incluido). Queda la
      T14, la prueba de punta a punta en DIgSILENT.

Añadido el 2026-10-17 (calibrar NA203 y NA205 con su central en julio y a la vez)

- [x] T16. Mes de análisis (013:RF-11) e instante coincidente (RF-50 a RF-53): lector, API
      y paso 2.2 de la web. (RF-50 a RF-53)
      Hecho cuando: pruebas del lector, de la API y del front en verde; `npm run build`.
      Hecho el 2026-10-17: `periodo` e `instante` en `maximas` y `demanda_con_central`; la
      búsqueda guarda su criterio y la central y el ajuste lo usan; con la cabecera negativa
      en el coincidente, el objetivo es la demanda del alimentador; mes en 2.2, antes de
      buscar, e instante entre las máximas de los marcados.
- [x] T18. Calibración por proyecto (RF-54 a RF-60): `cuadrar_conjunto` en
      `ajuste_cabecera.py` (y `cuadrar_zonas` sobre él), `ejecutar_proyecto` en
      `tools/ajuste_cabecera_pf.py` con varios `--plan`, y la web lanza un solo guion por
      proyecto.
      Hecho cuando: pruebas del cuadre conjunto, del guion con `fake_pf` y de la web en verde.
      Hecho el 2026-10-17: `cuadrar_conjunto` (2, 3 y 7 alimentadores acoplados),
      `ejecutar_proyecto` con central y sin ella, y la web con un proceso por proyecto; los
      transformadores nuevos (020) recalibran el proyecto entero.
- [x] T19. Tensión en la fuente (RF-61 a RF-63): campo en 2.4, plan, consigna de las redes
      externas en «Sin proyecto» y «Con proyecto» y fila en la tabla de cambios.
      Hecho cuando: pruebas del guion, de la web y del front en verde.
- [x] T20. Bancos que faltan (RF-64 a RF-69): tamaño por tensión en el perfil, déficit y
      posiciones en `ajuste_cabecera.py`, colocación en la troncal y recalibración en
      `tools/ajuste_cabecera_pf.py`, casilla en 2.4.
      Hecho cuando: pruebas del cálculo, del guion con `fake_pf`, de la web y del front en verde.
- [x] T17. Calibrar NA203 y NA205 con su central en «20261016-160231_IGEA_NA203_NA205»
      desde la web, en julio y en el instante de la máxima de NA203. (RF-50, RF-51)
      Hecho cuando: el ajuste aplicado cuadra en DIgSILENT y su informe lo dice.
      2026-10-17, desde la web y por proyecto (T18), registro del 2026-07-23 10:00: los
      dos cuadran en kW en los mismos 18 flujos (NA203 9 242,9 de 9 244 kW; NA205 aguas
      arriba 931,0 de 934,6 y aguas abajo 7 174,8 de 7 177,9; cabecera −1 546,1 frente a
      −1 520,8 medidos), pero solo converge con «adaptación automática del modelo» y 78
      cargas no consumen lo escrito: no es válida y vuelve a como estaba. Causa: 6 SED
      fijas de NA203 por encima de su transformador (SE50290 396 %, SE50150 297 %, SE50162
      232 %, SE50225 211 %, SE50307 108 %, SE50123 102 %). Falta implementar sus
      transformadores (spec 020) o corregir el cruce y recalibrar.
      Después, a petición del usuario, los 6 transformadores con su ficha NTP desde la web
      (la variación de la central de NA205 ya no lo bloquea, 020:RF-17) y recalibrado el
      proyecto: siguen cuadrando en kW (NA203 9 243,2 kW) y sigue sin converger sin
      `iopt_lev`, ni con las escaladas al 1,7 % de su kVA: lo impiden las 14 fijas de NA203
      (7 232 kW), con 0,906 pu en SE50290_BT. NA203 no tiene ningún banco en el modelo y la
      red da 2 656 kVAR frente a 1 560 medidos: falta compensación o la tensión de la SET.
      Con la fuente a 1,05 pu (T19, las dos «External Grid» de 1,0 a 1,05) la mínima sube a
      0,96 pu y sigue igual. Con los bancos que faltan (T20): NA203, 2 × 450 kvar en las
      barras 8937 y 8781 de su troncal (1 744 kVAR frente a 1 560 medidos); NA205 no tiene
      déficit (2 537 frente a 2 535). Los dos cuadran en kW, pero el flujo no converge desde
      el primer intento sin `iopt_lev` ni con las escaladas al 1,7 %: no es la tensión ni la
      compensación. Falta aislar qué isla (cada alimentador tiene su fuente) no converge.
      Aislada con los mensajes de DIgSILENT: NA203 solo converge en 3 iteraciones; la isla de
      NA205 no, con el Newton estancado en SE50293_BT: un cliente fijo de 1 392 kW sobre 125
      kVA, que no se avisaba porque con central no se miraban las fijas sobre su
      transformador (arreglado, 020:RF-1). Con los 5 transformadores de NA205 con su ficha
      (SE50293 3 × 630, SE50156 2 × 630, SE50100 2 × 630, SE50180 1 × 400, SE50184 1 × 500)
      y sin el registro de una calibración no guardada (arreglado: solo se registra la que
      queda en el escenario), cerrada el 2026-10-17 desde la web: los dos cuadran en el
      mismo flujo, en 2 flujos y sin ningún remedio, con la validación física correcta.
      NA203 9 190,9 de 9 244 kW (−0,57 %); NA205 aguas arriba 936,8 de 934,6 kW y aguas
      abajo 7 145,1 de 7 177,9 kW, cabecera −1 570,0 frente a −1 520,8 medidos.
- [x] T21. Retro (033, 2026-10-29): RF-70, añadidos a la spec como cambio después de
      escribir las tareas e implementados con su prueba sin tarea propia. (RF-70)
      Hecho cuando: las pruebas que los citan pasan (pruebas de `tests/test_ajuste_proyecto_guion.py`).
