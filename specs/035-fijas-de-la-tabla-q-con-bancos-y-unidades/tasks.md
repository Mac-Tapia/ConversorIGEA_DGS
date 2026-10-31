# Tareas — Spec 035

Estado: pedida por el usuario el 2026-10-29. Plan: [plan.md](plan.md).

- [x] T1. `derivacion_cliente` compartida por la tabla y `fijas_de`. (RF-2, RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_tabla_en_el_instante.py` en verde.
      Hecho el 2026-10-29: `derivacion_cliente` en `ajuste_cabecera.py`; `fijas_de` la usa.
- [x] T2. Cruce con la máxima de cada alimentador en la API y en la web. (RF-1 a RF-3)
      Hecho cuando: `pytest -q tests/test_tabla_en_el_instante.py` en verde y el front compila.
      Hecho el 2026-10-29: `maximas` en `/demanda/clientes/cruzar`; la tabla con P, Q, registro y origen.
- [x] T3. Cuadre de la Q en `cuadrar` y `cuadrar_conjunto`. (RF-5, RF-6, RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_q_con_bancos.py` en verde.
      Hecho el 2026-10-29: `con_q` en `cuadrar` y `cuadrar_conjunto`, estados CUADRADA, SIN_MARGEN, SIN_BASE.
- [x] T4. Guion: bancos en servicio, Q base por `b/a`, validación con el FP resultante, informe y
      relectura previa. (RF-7, RF-10 a RF-13)
      Hecho cuando: `pytest -q tests/test_q_con_bancos.py tests/test_ajuste_cabecera_guion.py` en verde.
      Hecho el 2026-10-29: `bancos_en_servicio`, `informe_de_la_q`, Q base por b/a en `escribir_reparto`.
- [x] T5. Unidades del proyecto antes de escribir. (RF-14 a RF-16)
      Hecho cuando: `pytest -q tests/test_unidades_pf.py` en verde.
      Hecho el 2026-10-29: `unidades_del_proyecto` y `error_de_unidades` en `cargas_pf.py`.
- [x] T7. Libro del mes anterior solo si falta el del mes de la máxima, en el plan y en la tabla.
      (RF-17, RF-18)
      Hecho cuando: `pytest -q tests/test_tabla_en_el_instante.py` en verde.
      Hecho el 2026-10-29: `mes_anterior_con_libro` y el estado `CLIENT_PERIOD_PREVIOUS` en
      `periodo_clientes_activo`; el plan y `_clientes_en_sus_maximas` cruzan con ese libro.
- [x] T8. Q a ±2 %, mes distinto sin bloquear, revisión de bancos para el evaluador y
      recalibración numerada desde la primera calibración. (RF-5, RF-19, RF-20, RF-21)
      Hecho cuando: `pytest -q tests/test_q_con_bancos.py tests/test_client_period_contract.py
      tests/test_tabla_en_el_instante.py` en verde y el front compila.
      Hecho el 2026-10-29: `TOLERANCIA_Q`, `revision_de_bancos`, `CLIENT_PERIOD_MISMATCH` como aviso,
      `recalibracion` en `ws.calibraciones` y su resumen público; botones de la web.
- [x] T9. Calibración solo P y recalibración P y Q, con las actualizaciones de «Sin proyecto».
      (RF-5, RF-10, RF-20, RF-22, RF-23)
      Hecho cuando: `pytest -q tests/test_q_con_bancos.py` en verde y el front compila.
      Hecho el 2026-10-29: `recalibracion` en el plan, `tipo_ajuste` en el informe, `con_q` solo al
      recalibrar; textos del paso 2.4.
- [x] T10. Q en toda recalibración al ±1 % con el FP de las escaladas, capacitivo si hace falta, y
      la revisión de bancos cuando quedan capacitivas. (RF-24 a RF-27)
      Hecho cuando: `pytest -q tests/test_q_con_bancos.py tests/test_ajuste_proyecto_guion.py
      tests/test_ajuste_cabecera.py` en verde.
      Hecho el 2026-10-29: `TOLERANCIA_Q` 0,01; `con_q` al recalibrar sin pedir bancos; la
      recalibración no pone bancos de calibración. El 2026-10-31, por el usuario, las escaladas
      nunca con reactiva negativa: `_paso_q` vuelve a parar en FP 1 (`SIN_MARGEN`) y la revisión
      de bancos lo recomienda (RF-26, RF-27). 173 pruebas del ajuste en verde.
- [x] T11. Coherencia de la medida de cabecera: cuadre de la Q solo si es coherente; si no, la Q
      real de DIgSILENT con las escaladas a su FP de perfil, dicho. (RF-28 a RF-31)
      Hecho cuando: `pytest -q tests/test_q_con_bancos.py tests/test_tabla_en_el_instante.py` en
      verde y el front compila.
      Hecho el 2026-10-31: `Q_INCOHERENTE_ALTA/BAJA` y `q_extremo` en `cuadrar` y
      `cuadrar_conjunto`, `Reparto.al_perfil` y `factor_q_maximo`; `factor_potencia_minimo_escaladas`
      en el plan; `coherente` y `extremo` en `cuadre_q`; la comparación de 039 dice la Q alcanzable
      con cada criterio. Retira `SIN_MARGEN`.
- [x] T6. [DIgSILENT] SM218 desde la web: tabla en el instante de la máxima, fijas con la P y la Q
      de la tabla a escala 1, escaladas cuadrando P y Q con sus siete bancos, unidades MW/Mvar.
      Hecho cuando: el informe de la calibración de SM218 dice criterio kW y kvar, Q de cabecera
      dentro de la tolerancia (o los kvar que faltan, RF-8) y la validación nativa correcta.
      Hecho el 2026-10-31: SM218, recalibración n.º 13 (2026-09, coincidente): kW y kvar, Q de
      cabecera 2 519,6 frente a 2 506 medidos (+0,5 %, coherente) con las escaladas a FP 0,985,
      validación nativa VALIDO. NA203: medida no coherente (2 453,6 kvar a FP 1 frente a 1 777),
      Q real de DIgSILENT a FP 0,98 y dicho (RF-28 a RF-30).
