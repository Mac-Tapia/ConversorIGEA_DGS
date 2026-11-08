# Tareas — Spec 052

- [x] T1. Lectura única del grafo y de las cargas nuevas por variación en «Con proyecto». (RF-1)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py -k lectura` en verde con el doble.
      Hecho el 2026-11-01: `obras_pf.py --oraculo-datos` (`datos_oraculo`), prueba con el doble.
- [x] T2. Variantes aplicadas al grafo y flujo del oráculo con k cargas, máxima y sorteos. (RF-2, RF-3, RF-9)
      Hecho cuando: en una red sintética, cada obra mueve la tensión como su flujo exacto.
      Hecho el 2026-11-01: `optimizacion_oraculo.Oraculo` (banco, terna, sección exactos a 1e-9;
      regulador aproximado y marcado); `tests/test_optimizacion_oraculo.py`.
- [x] T3. Búsqueda de k y elección con el oráculo; confirmación y discrepancias en DIgSILENT. (RF-4 a RF-8, RF-10)
      Hecho cuando: con un DIgSILENT doble que discrepa, se corrige hacia lo confirmado.
      Hecho el 2026-11-01: `buscar_k`, `elegir_para_k` y `services._optimizar_con_oraculo`; con un
      DIgSILENT doble que discrepa, k baja a lo confirmado; sin grafo, la búsqueda de la 042.
- [x] T4. [DIgSILENT] NA203 + NA205 optimizado por la web en menos de 20 min. (Todos)
      Hecho cuando: elegida y límite confirmados y la comparación oráculo–DIgSILENT en el informe.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T5. Búsqueda bayesiana, frente de Pareto, sorteos de Markov y reparto de Shapley sobre el
      oráculo. (RF-11 a RF-16)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py` en verde con redes sintéticas
      cuya solución se conoce.
      Hecho el 2026-11-01: `buscar_combinacion` (Optuna TPE), `frente_pareto` (`evolutivo.nsga2`),
      `sorteos_markov` y `reparto_shapley`; 7 pruebas en verde.
- [x] T6. El PINN promovido como segundo oráculo dentro de su dominio. (RF-17)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py -k pinn` en verde con un PINN doble.
      Hecho el 2026-11-01: `Oraculo(pinn=…)`; la medida dice `oraculo` = pinn o fisica.
- [x] T7. La SET nueva comprobada con el oráculo antes de crearla y con el nombre del operador. (RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py -k set_nueva` en verde.
      Hecho el 2026-11-01: `Oraculo.con_set_nueva`, `services._set_nueva_en_el_oraculo` y `nombre_set`.
