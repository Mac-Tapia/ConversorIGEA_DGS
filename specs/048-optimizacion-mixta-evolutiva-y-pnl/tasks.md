# Tareas — Spec 048

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Problema mixto y caché con contexto. (RF-1, RF-2, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_problema_optimizacion.py tests/test_digital_twin_evolutivo.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.
      Hecho el 2026-11-06: `digital_twin/problema_optimizacion.py` (variables tipadas con unidad, origen y
      coste trazable; `evaluar_vector`, `validar_vector`, `reparar`, `clave_evaluacion`, `CacheEvaluaciones`,
      `ContextoSintetico`) y `problema_bancos`/`problema_maniobras` en `evolutivo.py` sobre el flujo del gemelo.
      Rama `feat/048-optimizacion-mixta`; `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q
      tests/test_problema_optimizacion.py tests/test_digital_twin_evolutivo.py`: 37 passed, 0 omitidas.
      Sin cambio de lector ni de modelo del DGS: no aplican los TXT reales.

- [x] T2. Benchmark de algoritmos actuales y pymoo. (RF-3, RF-6, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_optimizacion.py tests/test_digital_twin_evolutivo.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.
      Hecho el 2026-11-06: `digital_twin/benchmark_optimizacion.py` (`comparar_optimizadores`, `hipervolumen`) y
      `digital_twin/adaptador_pymoo.py`; la etapa «evolutivos» (`tools/evaluar_evolutivos.py`) compara con él.
      `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q tests/test_benchmark_optimizacion.py
      tests/test_digital_twin_evolutivo.py`: 26 passed, 0 omitidas. Benchmark real local:
      `tools/evaluar_evolutivos.py --seeds 30 --presupuesto 300` (ver «Evidencia de ejecución»).

- [x] T3. PNL continua y selección top-k. (RF-4, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_adaptador_pnl.py tests/test_verificacion_top_k_completa.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.
      Hecho el 2026-11-06: `digital_twin/adaptador_pnl.py` (`resolver_continuo`, `verificar_candidatos`, `TOP_K = 3`).
      `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q -rs tests/test_adaptador_pnl.py
      tests/test_verificacion_top_k_completa.py`: 88 passed, 0 omitidas. El caso diminuto de óptimo conocido se
      resuelve con un solucionador real, HiGHS 1.15.1 (`pyomo.contrib.solver`, cuadrático convexo), sin dobles.
      Ipopt no está instalado en `.venv`: su vía devuelve ERROR_ENTORNO y su compatibilidad queda en T3b.

- [x] T3b. El tramo continuo con Ipopt instalado. (RF-4)
      Hecho cuando: con Ipopt disponible para `pyomo.contrib.solver`, `tests/test_adaptador_pnl.py` resuelve también
      el caso diminuto con `{'solver': 'ipopt'}` (LOCAL_CONVERGIDO, óptimo analítico) y la prueba pasa sin omitirse.
      Hecho el 2026-11-06, por orden del usuario («debe instalar todo lo que falta»): Ipopt 3.14.20 oficial de COIN-OR
      (`Ipopt-3.14.20-win64-msvs2022-md.zip`, SHA-256 1fd1de97d3e8e48c298f6ccf5ac91cbfc417b42c61262c08d193fd14117e9098) en
      `~/.convertersmartgrid/solvers/ipopt-3.14.20/`, fuera del repositorio; `adaptador_pnl.ejecutable_ipopt` lo encuentra por
      `CSG_IPOPT`, el `PATH` o esa carpeta. `pytest -q tests/test_adaptador_pnl.py`: 14 pasadas, la de Ipopt sin omitirse.

- [x] T4a. Aplicación de las obras elegidas en sus variaciones y comprobación de persistencia sin tocar el caso de
      referencia, con el DIgSILENT simulado (`tests/fake_pf.py`). (RF-9)
      Hecho cuando: una prueba que cita 048:RF-9 pasa con el falso: las obras quedan en su variación, se releen y el
      caso de referencia no cambia. Partida de la T4 el 2026-11-06 (spec 033: el código se cierra con sus pruebas).
      Hecho el 2026-11-06: `aplicar` de `tools/obras_pf.py` (la vía de siempre de las obras, sin otra) fotografía
      antes de escribir el «Caso base», y «Sin proyecto» si ninguna obra es de allí (`leer_foto`, una pasada por clase
      sobre toda la red: tipo, ternas, servicio, interruptores, escalones, tomas y demanda); al terminar reabre el
      proyecto (desactivar y activar, como la lectura del gemelo, 024:RF-27), relee cada variación (`releer_obras`:
      existe, cuánto graba, en qué casos está activa) y vuelve a fotografiar (`comprobar_persistencia`). El veredicto
      y la foto son de `convertersmartgrid/obras_pf.py` (`foto_de_referencia`, `cambios_de_foto`,
      `veredicto_persistencia`): sin persistir o con la referencia cambiada, `persistencia.ok` es falso, el informe
      dice la obra o el elemento y el valor, y sale 2. Rama `feat/048-t4a`; `PYTHONPATH=src .venv/Scripts/python.exe
      -m pytest -q -rs tests/test_obras_persistencia.py`: 13 passed, 0 omitidas. Las elegidas por
      `verificar_candidatos` llegan a `aplicar` como obras del plan; esa conexión con la web no se tocó.
- [x] T4 [DIgSILENT]. Aplicación en variaciones y reapertura nativa. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_optimizacion_mixta_nativa.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.
      Abierta el 2026-11-07: la persistencia está medida en DIgSILENT y las pruebas pasan, pero el plan no la cierra con un
      diseño que converge sin tensión admisible, y en el proyecto de prueba no hay uno: ver «T4, 2026-11-07» abajo.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).

## Evidencia de ejecución

### 2026-11-07 — T4 medida, abierta (rama `worktree-agent-a578852c96aa94605` sobre `7e81450c`)

- Proyecto de prueba `20261106-233549_CSG_TXT_8fc733e4_01_PE10` (CA101 + PE104), DIgSILENT 24.0.2. Obra: banco de 300 kvar en
  la barra 14932 de CA101, en «Con proyecto», por `tools/aceptacion_nativa.py obras --guion-local` (el mismo `tools/obras_pf.py`
  con el plan firmado por la web; detalle y arreglos de la fecha de «Con proyecto» en la T4 de la 044). Evidencia:
  `D:/converter/evidencia_nativa/20261107_PE10_t4c/` (manifiesto `e582c7c3a660f79b…`, fuera de git).
- `CSG_EVIDENCIA_NATIVA=… pytest -q -rs tests/test_optimizacion_mixta_nativa.py`: 3 passed, 0 omitidas.
  `test_obras_persisten_sin_tocar_referencia`: `persistencia.ok` del guion, la variación activa y el banco en su barra tras
  reabrir en otra sesión; «Caso base» y «Sin proyecto» releídos antes y después en procesos nuevos, iguales (1 065 barras,
  diferencia 0,0 p.u. y 0,0 kW; mismas huellas de topología, controles y escenario). `test_demanda_no_cae_artificialmente`:
  9,3457 MW en «Con proyecto» y en «Sin proyecto», ninguna barra sin tensión.
- Por qué sigue abierta: la evaluación nativa de «Con proyecto» con la obra es `converged_with_violations` (0,9361 p.u. en
  media en CA101, fuera de 0,95–1,05; «Sin proyecto» ya tiene 0,9215 p.u. en CA101 y tramos al 124 %). Un diseño admisible lo
  elige la escalera (025/042), que pide cargas nuevas, o la 052 con el oráculo en GPU; este proyecto no tiene cargas nuevas y la
  GPU no estaba disponible. Siguiente acción: repetir la etapa con un diseño elegido por `verificar_candidatos` en un proyecto
  de prueba con cargas nuevas.
- Las evidencias `…_t4` y `…_t4b` (por la web, con los guiones de `main`) guardan el fallo: obra inactiva en «Con proyecto»
  (687 barras sin tensión) mientras `persistencia.ok` del guion decía verdadero; la persistencia del guion no mira si la obra
  quedó activa donde se pidió.

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

### 2026-11-06 — T1 a T3 (rama `feat/048-optimizacion-mixta`)

- Pruebas: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q -rs` sobre `test_problema_optimizacion.py`,
  `test_digital_twin_evolutivo.py`, `test_benchmark_optimizacion.py`, `test_adaptador_pnl.py`,
  `test_verificacion_top_k_completa.py` y las regresiones de los módulos tocados (aprendizaje continuo,
  benchmark PINN, flujo, optimización con el oráculo, reentrenamiento, trabajadores, arquitectura):
  249 passed, 0 omitidas; `test_trazabilidad_specs.py`, `test_inventario.py` y `test_capas.py`: 145 passed.
- Benchmark real local de la etapa «evolutivos»: `tools/evaluar_evolutivos.py --seeds 30 --presupuesto 300`,
  320 s, `status RECHAZADO` (no acredita aceptación eléctrica ni promoción), pymoo 0.6.2 presente. Media
  e IC 95 % por semilla (bootstrap): Rosenbrock 3D, mejor valor GA de pymoo 1,068 [0,773; 1,416], NSGA-II
  1,046 [0,671; 1,463], jDE 1,32 [1,07; 1,58], DE de pymoo 1,068 [0,778; 1,397], todos con 300 evaluaciones;
  Schaffer N.1, hipervolumen normalizado NSGA-II 1,0399 [1,0398; 1,0400] frente a NSGA-II de pymoo
  1,0393 [1,0391; 1,0395]; entero cuadrático, todos llegan al óptimo 0 y paran antes del presupuesto al
  repetir solo vectores ya vistos (de 113 a 300 evaluaciones reales). Los de un objetivo se declaran
  `no_compatible` en Schaffer. El informe queda fuera del repositorio (es un producto de la etapa).
- Limitaciones: problemas analíticos, no una red; el PNL real se probó con HiGHS (cuadrático convexo), Ipopt
  no está instalado (T3b); `web/services.py` no se tocó: la conexión a la web queda para quien la integre.

### 2026-11-06 — T4a (rama `feat/048-t4a`, desde `main` fe3498ab)

- Pruebas: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q -rs tests/test_obras_persistencia.py`: 13 passed,
  0 omitidas (antes de implementar, error de importación: faltaba `foto_de_referencia`). Con `test_obras_pf.py`,
  `test_obras_pf_guion*.py`, `test_trazabilidad_specs.py`, `test_inventario.py`, `test_capas.py` y
  `test_arquitectura_generada.py`: 379 passed. Los 39 ficheros de pruebas que tocan obras, escalera o MADRL:
  1365 passed, 1 omitida (`test_valle.py`, sin `CSG_DEMANDA_DIR`) y 2 fallos ajenos a este cambio
  (`test_pf_servidor.py`, por `tools/powerfactory_acceptance.py`; `test_valle_front.py`, por el frontend).
- Limitaciones: el doble reabre el proyecto sin releer de una base; que DIgSILENT guarde las variaciones, que la foto
  real no varíe entre dos lecturas de la misma red y el tiempo de la foto en un proyecto grande los mide la T4.

