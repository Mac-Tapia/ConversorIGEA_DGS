# Tareas — Spec 008

- [x] T1. Guiones: error inesperado → informe con `error`. (RF-17)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_cargas_pf_guion.py` en verde.
- [x] T2. `tools/verificar_pf.py` y `services.pf_verificar` con su endpoint. (RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_verificar_pf.py tests/test_cargas_pf_web.py` en verde.
- [x] T3. Ajuste de varios alimentadores en un trabajo. (RF-10, RF-12 a RF-15)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_web.py` en verde.
- [x] T4. Carga del formulario delante de las del libro. (RF-24)
      Hecho cuando: `pytest -q tests/test_cargas_pf_web.py` en verde.
- [x] T5. Interfaz en tres pasos. (RF-1 a RF-9, RF-11, RF-16, RF-20 a RF-23)
      Hecho cuando: `pytest -q tests/test_cargas_tres_pasos_front.py tests/test_cargas_pf_front.py
      tests/test_demanda_medida_front.py`, `npx tsc --noEmit -p .` y `npm run build` correctos.
- [x] T6. Validación: `grep -rnoE "008:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-24; suite completa.
      Hecho cuando: `grep -rnoE "008:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-24 y la suite completa, en verde.
- [x] T8. Numeral 3.2 en la página: nombre, kW, FP 0,98, UTM X/Y y «Conectar al NMT más cercano». (RF-25 a RF-28)
      Hecho cuando: `pytest -q tests/test_cargas_pf_web.py tests/test_cargas_tres_pasos_front.py`,
      `npx tsc --noEmit -p .` y `npm run build` correctos, y probado en el navegador.
- [x] T7. [DIgSILENT] Prueba real en DIgSILENT con un proyecto de dos alimentadores, a cargo del usuario.
      Hecho cuando: el usuario confirma en DIgSILENT los tres pasos con un proyecto de dos alimentadores.
      Hecho el 2026-11-08: el usuario confirma los tres pasos de `20261106-065905_CSG_TXT_PRUEBA_007` (TM105 +
      PN103, espacio 35ff5dab8b2b46a6): calibración, cargas del libro (planes `cargas_pf_7f5a264873c2` y
      anteriores) y carga del formulario (`cargas_pf_d331a8d5cd79`). El proyecto de prueba se borra al cerrar.
- [x] T9. La mínima y la máxima del flujo sin las barras sin tensión, con su lista aparte; los umbrales de 063 de una
      sola fuente (`cargas_pf.UMBRAL_SIN_TENSION` y `KV_MINIMO_MT`, que `estudios_pf` importa). (RF-29)
      Hecho cuando: `pytest tests/test_cargas_pf_guion.py -k 008_rf29` falla por aserción con el código de antes (daba
      `vm_min` 0,0) y pasa después, y `tests/test_cargas_pf_guion.py`, `tests/test_estudios_pf_guion.py` y los vecinos
      de verificar siguen en verde.
      Hecho en la fila FLUJO-ISLAS (f7, 17-11): la verificación de la 080 T13 por la web (copia VNR-GIS, Caso base)
      daba «vm_min 0,0» en la barra de una isla; rojo VALIDO (0,0 frente a 0,97) y verdes en D:/csg/PM_IMPL/FLUJO_ISLAS.
- [x] T10. La verificación dice lo que informa DIgSILENT y avisa de `Fichas_`/`SED_NTP_` apagadas, sin encenderlas;
      el gemelo avisa igual; la tarjeta de convergencia lo enseña. (RF-30, RF-31)
      Hecho cuando: `pytest -q tests/test_verificar_pf.py tests/test_digital_twin_snapshot_pf.py
      tests/test_cargas_tres_pasos_front.py -k "rf30 or rf31"` falla por aserción sobre `a0ebd973` y pasa después, con
      `npm test` y `npm run typecheck` en `frontend/` correctos.
      Hecho el 2026-11-20 (d8, cierre de la fila gSIG por orden del usuario «nada abierto»): rojo D:/csg/PM_IMPL/MEJ9_NOCONV/rojo_a0ebd973.txt (15 F sobre a0ebd973, rf30 y rf31); verde D:/csg/PM_IMPL/MEJ9_NOCONV/verde_nuevas.txt
      (16 passed), verde_vecinos.txt (615 passed), frontend_test.txt (319 pass, 0 fail) y frontend_typecheck.txt; verde integrado del hueco de MEJ567 sobre c4326366 (D:/csg/PM_IMPL/MEJ567/verde_20261120_163024.log, 2423 passed, rc=0;
      npm_test_20261120_163024.log y e2e_20261120_163024.log) y la puerta gSIG que integra esta casilla (0 fallidas, 0 omitidas).
