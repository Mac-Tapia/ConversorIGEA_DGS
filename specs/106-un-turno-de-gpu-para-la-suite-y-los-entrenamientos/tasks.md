# Tareas — Spec 106

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Espera del turno con plazo y dueño; la sesión de pytest toma el turno de la máquina; volcado de pila; marca
      `gpu` sola; la puerta cuenta la salida sin turno como fallo; y el controlador de NVIDIA no tumba la sesión ni el
      producto al iniciar CUDA, con su aviso en el doctor. (RF-1 a RF-11, RF-18, RF-19)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_turno_gpu_de_la_suite.py` en verde; y
      `tests/test_compat_gpu.py` (106:RF-18, RF-19) en verde, con su prueba lenta en Windows real (rc 0 con la DLL
      fijada) y el rojo del mismo subproceso sin fijarla (0xC0000005) guardado en `D:/csg/NV/rojo_*.log`; y la de la GPU
      oculta (106:RF-18): un backward en CPU y un `lgb.train` descargan la DLL sin el paquete y no con él, con el rojo
      de la suite del pronóstico y su verde con la DLL fijada en `D:/csg/OPENMP`.
- [x] T3. Los hijos de las pruebas cargan el src del árbol que se prueba; la puerta corre todo si cambia lo común; y la
      suite no escribe en los datos del usuario: su runtime y sus almacenes son de la sesión. (RF-12, RF-13, RF-16, RF-17)
      Hecho cuando: `tests/test_turno_gpu_de_la_suite.py` (106:RF-12) y `tests/test_puerta_calidad.py` (106:RF-13) en verde, y en rojo con el conftest anterior en un
      worktree; y `tests/test_suite_sin_datos_del_usuario.py` (106:RF-16, RF-17) en verde, con su rojo sobre el conftest
      anterior (3 failed, D:/csg/integrador_a3/datos_suite_rojo.log; verde 3 passed, …_verde.log).
      Y `tests/test_suite_sin_output_del_checkout.py` (106:RF-17, ampliado el 2026-11-13: ninguna raíz de datos cae en
      el `output/` del checkout real) en verde, con su rojo sobre el src anterior (1 failed,
      D:/csg/SUITE_OUTPUT_WEB/rojo.log; verde 2 passed, D:/csg/SUITE_OUTPUT_WEB/verde.log); y su caso de `config/` e
      `input/` locales y de la puerta, con su rojo sobre `raiz_local` sin redirigir (1 failed, rojo_config.log; verde
      4 passed, verde_config.log).
      Y `tests/test_puerta_corre_las_regresiones.py` (106:RF-13: `test_regresiones` en el gobierno de la puerta) en
      verde, con su rojo sobre la lista anterior (1 failed, D:/csg/SUITE_OUTPUT_WEB/rojo_regresiones.log; verde,
      verde_regresiones.log).
- [x] T5. El entorno de DIgSILENT no hereda otro paquete del conversor por PYTHONPATH. (RF-14)
      Hecho cuando: `tests/test_powerfactory_versiones.py` (103:RF-6, sin tocar) y `tests/test_turno_gpu_de_la_suite.py`
      (106:RF-14) en verde.
- [x] T4. El resultado de la suite guarda las más lentas y avisa de las que pasan del umbral del volcado. (RF-15)
      Hecho cuando: `tests/test_puerta_calidad.py` (106:RF-15) en verde.
- [x] T2. Suite completa con un entrenamiento esperando su turno: las 62 de 10a80812 en verde, sin omitidas. (RF-1, RF-4, RF-21)
      Hecho cuando: la suite completa corrida sola da 0 fallidas, 0 omitidas y 0 errores, y el entrenamiento esperó.
      Hecho el 2026-11-21 (d8, bloque GPU): la suite de la puerta CIE (D:/csg/PM_IMPL/CIE/gCIE_c2_091010.log) da «Puerta
      de calidad: 7316 pruebas, 0 fallidas, 0 omitidas.» y un entrenamiento corto (tools/madrl_entrenar.py, gatv2, 2
      iteraciones, CSG_GPU_ESPERA_S, RF-21) pidió el turno mientras esa suite lo tenía, esperó (36 avisos con su dueño) y
      terminó rc=0; evidencia en D:/csg/PM_IMPL/GPU_BLOQUE/106_T2c/ (espera.log, lock_suite.json, entrenamiento.log,
      entrenamiento.json) y en D:/csg/PM_IMPL/GPU_BLOQUE/estado.txt.
- [x] T6. La espera de trabajos de las pruebas (`tests/apoyo.esperar_trabajo`) va por estado y avance: `timeout` es la
      ventana sin avance, el tope total es de 900 s, e «interrumpido» también termina. Las 189 llamadas no cambian.
      (RF-20)
      Hecho cuando: `tests/test_espera_por_avance.py` (106:RF-20) en verde, con rojo previo sobre la espera de tope fijo,
      y `tests/test_web_api.py` en verde.
      Hecho en ecad83ea (LOTE-4, FIX-ESPERA-PARALELO); pruebas: tests/test_espera_por_avance.py.
- [x] T7. La suite toma el turno de GPU solo durante sus pruebas de GPU, que corren al final; mientras, un entrenamiento
      puede usarla; y queda registrado cuándo lo pidió, lo obtuvo y lo soltó. (RF-22, RF-23, RF-24; MEJ28)
      Hecho cuando: `tests/test_turno_gpu_de_la_suite.py` (106:RF-22 a RF-24) en verde, con su rojo por aserción sobre
      el `tests/conftest.py` anterior.
      Hecho el 2026-11-21 (d8, MEJ28): rojo por aserción sobre el `tests/conftest.py` de e98f3f89, 3 failed
      (D:/csg/PM_IMPL/MEJ28_TURNO/rojo.log); verde, 117 passed y 495 passed, 0 omitidas
      (D:/csg/PM_IMPL/MEJ28_TURNO/verde.log); repetidos sobre la punta que se integra en el hueco N2
      (D:/csg/PM_IMPL/N2/estado.txt). La suite completa con un entrenamiento esperando es la T2, también cerrada.
- [x] T8. Cada tanda de la suite nocturna espera a un entrenamiento con la GPU si falta memoria. (RF-25)
      Hecho cuando: `tests/test_suite_espera_recursos.py` (106:RF-25) en verde con su rojo por aserción sobre b5e0c45f,
      y una comprobación real con el turno de GPU tomado por un entrenamiento y poca memoria dice que la tanda espera.
      Hecho el 2026-11-24 (d8, N10): rojo por aserción sobre b5e0c45f (`N10_SINCODEX/T106_8/rojo_base_0412.log`, 6 failed)
      y verde (`N10_SINCODEX/T22/verde_0455f.log`, 245 passed con las pruebas de la revisión y de la suite). Comprobación real, 04:20, con el
      turno de GPU en manos de un entrenamiento del 089 (pronóstico) y 2,2 de 4 GiB disponibles: la tanda dice quién
      tiene la GPU y espera (`N10_SINCODEX/T106_8/real_0346.log`).
- [x] T9. La suite nocturna por tandas no hereda la temporal de la web. (RF-26)
      Hecho cuando: `tests/test_suite_espera_recursos.py` (106:RF-26) en verde con su rojo por aserción, y una tanda
      real con el entorno de la web pasa `tests/test_turno_gpu_de_la_suite.py` entero.
      Hecho el 2026-11-26: las tres tandas de las cuatro fallidas pasan solas (`D:/csg/PM_IMPL/ORDEN4/tanda_*.log`);
      rojo con el TEMP de la web, 1 failed (`ORDEN4/rojo_temp_real.log`) y por aserción (`ORDEN4/rojo_unitario.log`);
      verde 30 passed (`ORDEN4/verde_unitario.log`) y la tanda real, 29 passed (`ORDEN4/verde_real_tanda.log`).
- [x] T10. El guion de DIgSILENT importa el paquete de la web. (RF-27)
      Hecho cuando: `tests/test_turno_gpu_de_la_suite.py` (106:RF-27) en verde, con su rojo por aserción sobre el
      `powerfactory_env.py` anterior.
      Hecho el 2026-11-26: verde `D:/csg/PM_IMPL/PAQUETE_DE_LA_WEB/rojo.log` (la primera corrida esperó la GPU 50 min
      y ya leyó el arreglo); rojo sobre el anterior en `rojo_anterior.log`. El `.pth` se devolvió al árbol principal
      (copia del anterior en `D:/csg/PM_IMPL/editable_pth_antes_26-11.txt`).
