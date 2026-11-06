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

- [ ] T3b. El tramo continuo con Ipopt instalado. (RF-4)
      Hecho cuando: con Ipopt disponible para `pyomo.contrib.solver`, `tests/test_adaptador_pnl.py` resuelve también
      el caso diminuto con `{'solver': 'ipopt'}` (LOCAL_CONVERGIDO, óptimo analítico) y la prueba pasa sin omitirse.
      Falta: instalar Ipopt (binario o `cyipopt`) en el entorno del proyecto, decisión del integrador.

- [ ] T4 [DIgSILENT]. Aplicación en variaciones y reapertura nativa. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_optimizacion_mixta_nativa.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

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

