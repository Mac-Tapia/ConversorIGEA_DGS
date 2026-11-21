# Tareas — Spec 006

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. `src/convertersmartgrid/dominio/ajuste_cabecera.py`: objetivo, demandas fijas de los clientes y
      reparto inicial por kVA, con los modos «todo escala» y «solo kW». (RF-1, RF-3, RF-5,
      RF-6, RF-7, RF-8, RF-13, RF-14, RF-24)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_ajuste_cabecera.py` en verde.
- [x] T2. Cuadre: secante sobre `kp` y `kq`, tolerancia, último reparto que convergió y
      escalera de remedios, contra la red de juguete con pérdidas. (RF-11, RF-12, RF-16,
      RF-17, RF-18)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera.py` en verde, con un caso que
      cuadra en menos de 30 flujos y otro que agota los remedios.
- [x] T3. Doble de PowerFactory: `ElmTr2` con tipo, cubículo de cabecera del `ElmFeeder`,
      `ComLdf` que calcula la cabecera con pérdidas y falla por encima de un umbral, en
      `tests/fake_pf.py`. (apoyo de RF-4, RF-11, RF-15)
      Hecho cuando: `tests/test_cargas_pf_guion.py` sigue en verde con el doble ampliado.
- [x] T4. `tools/ajuste_cabecera_pf.py`: cargas y kVA del alimentador, simular, aplicar en
      variación nueva, medir la cabecera, diagnóstico, remedios con los ajustes del `ComLdf`
      restituidos, cancelación e informe. (RF-4, RF-9, RF-10, RF-15, RF-17 a RF-22, RF-24)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T5. Web: `services.ajuste_plan` (objetivo comprobado contra el trabajo de la máxima,
      clientes del alimentador, kVA de la entrada original) y `ajuste_ejecutar` como trabajo
      del carril `powerfactory`; endpoints y tolerancia validada entre 0,1 % y 10 %.
      (RF-1, RF-2, RF-3, RF-10, RF-19, RF-20, RF-24)
      Hecho cuando: `pytest -q tests/test_demanda_medida_web.py` en verde.
- [x] T6. Interfaz: elegir el medidor de la cabecera, tolerancia, «Simular» y «Ajustar en
      DIgSILENT» con el proyecto de la pestaña, y el informe por SED y del alimentador.
      (RF-2, RF-3, RF-20, RF-21, RF-23)
      Hecho cuando: `npx tsc --noEmit -p .` y `npm run build` en `frontend/` correctos.
- [x] T7. Validación: cada RF citado por al menos una prueba y en verde; suite completa. (Todos)
      Hecho cuando: `grep -rnoE "006:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-30.
- [x] T9. Casilla por cliente importante en la tabla del cruce, marcada por defecto; los
      desmarcados van al plan aparte y el guion pone fuera de servicio, en la variación,
      la carga de la SED que se queda sin ningún cliente conectado. (RF-25, RF-26)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_ajuste_cabecera_web.py`
      en verde y `npm run build` correcto.
- [x] T10. El resultado del ajuste también en el escenario de operación del caso y, con los
      tres casos de la 011, en los de los tres; la cabecera medida con el escenario
      restaurado en el informe y en la web, con aviso si no coincide. (RF-27 a RF-30)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_casos_pf.py`
      en verde y `npm run build` correcto. Hecho el 2026-10-12.
- [x] T8. [DIgSILENT] Prueba real en DIgSILENT con un alimentador, a cargo del usuario: comprobar el
      signo y el lado de lo medido en la cabecera y que cuadra al 1 %. Y que, con el
      «Operation Scenario» activo, «Verificar la convergencia» da la cabecera ajustada
      (RF-27): SI213 daba 229,2 kW antes del cambio, con el ajuste en 1.621,8 kW.
      Hecho el 2026-10-22 con CA101 desde cero por la web (espacio 66fdc0868df54784): máxima de
      septiembre 4994 kW (L-CA131), calibrado tras los transformadores NTP de 4 SED fijas (spec 020),
      cuadrado a −0,00015 kW; «Verificar la convergencia» con «Sin proyecto» activo da 4993,2 kW.
      Hecho cuando: en DIgSILENT la cabecera ajustada cuadra al 1 % con el signo y el lado de lo medido.
- [x] T11. `demanda_medida.py`: `MaximaCabecera.curva` y `fuera_de_curva`, fuera de
      `to_dict`, y `reducir_curva` mín./máx. por intervalo. (RF-31, RF-37, RF-39)
      Hecho cuando: `pytest -q tests/test_demanda_medida.py` en verde. Hecho el 2026-10-12.
- [x] T12. Web: guardar la curva del último trabajo de máxima en el espacio y servirla
      entera o por tramo, reducida a 2 000 puntos. (RF-31, RF-32, RF-35, RF-38, RF-39)
      Hecho cuando: `pytest -q tests/test_demanda_medida_web.py` en verde. Hecho el 2026-10-12.
- [x] T13. `CurvaCabecera.tsx` en la caja del ajuste: línea cronológica, franja del mes
      de la máxima, punto marcado, zoom por arrastre y «Ver todo», kVAR opcional,
      selector de medidor y aviso de registros fuera; entra en `CODIGO_FUENTE.md`.
      (RF-32 a RF-38)
      Hecho cuando: su prueba de front en verde, `npx tsc --noEmit -p .` y `npm run build`
      correctos, y `grep -rnoE "006:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-39.
      Hecho el 2026-10-13; visto en el navegador con un libro sintético de 92 días.
- [x] T14. Retro (033, 2026-10-29): RF-40 a RF-44, añadidos a la spec como cambio después de
      escribir las tareas e implementados con su prueba sin tarea propia. (RF-40 a RF-44)
      Hecho cuando: las pruebas que los citan pasan (pruebas de `tests/test_ajuste_cabecera_guion.py`).
- [x] T15. Letra de los ejes de las gráficas del mismo tamaño en pantalla que el título. (RF-45)
      Hecho cuando: `frontend/test/letraFija.test.mjs` (006:RF-45) en verde.
- [x] T16. MEJ3-CALIB (orden del usuario del 19-11): `reparto_inicial` deja las fijas siempre con su P y Q; con las
      fijas que llenan la cabecera, `Reparto.causa` IMPOSIBLE, escaladas a 0, un flujo y `Cuadre.imposible` (086:RF-124),
      también en `cuadrar_conjunto` del proyecto; sin escaladas con kVA, `Reparto.causa` NO_CALIBRABLE,
      `Cuadre.no_calibrable` sin flujos, y el guion devuelve el error sin escribir. (RF-46)
      Hecho cuando: rojo por aserción sobre faf67626 y verde con `tests/test_ajuste_cabecera.py -k rf46`,
      `tests/test_calibracion_imposible.py -k rf46` y `tests/test_ajuste_cabecera_guion.py -k rf46`; la corrida en
      DIgSILENT va en el bloque de 086 T105.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
- [x] T17. MEJ10-FIJAS (orden del usuario del 20-11): el guion para en `_preparar_alimentador` con `FIJA_A_REVISAR`, sin flujos ni escrituras, y en el proyecto sigue con los demás alimentadores. (RF-47)
      Hecho cuando: rojo por aserción sobre 2f9de358 y verde con `tests/test_ajuste_cabecera_guion.py -k rf47`; la corrida en DIgSILENT la decide d8.
      Hecho el 2026-11-20 (d8, cierre de la fila gSIG por orden del usuario «nada abierto»): rojo D:/csg/PM_IMPL/MEJ10_FIJAS/rojo.log (test_006_rf47_en_el_proyecto_el_alimentador_a_revisar_no_frena_a_los_demas);
      verde D:/csg/PM_IMPL/MEJ10_FIJAS/verde_py.log; verde integrado del hueco de MEJ567 sobre c4326366 (D:/csg/PM_IMPL/MEJ567/verde_20261120_163024.log, 2423 passed, rc=0;
      npm_test_20261120_163024.log y e2e_20261120_163024.log) y la puerta gSIG que integra esta casilla (0 fallidas, 0 omitidas).
