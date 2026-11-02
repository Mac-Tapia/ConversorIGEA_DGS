# Plan — Spec 052

1. `tools/obras_pf.py --oraculo-datos`: en «Con proyecto», con todas las cargas nuevas activas,
   el grafo de `digital_twin_snapshot_pf.grafo`, la troncal y las barras de media de cada
   alimentador (lo de `--escalera-datos`) y, por variación de carga nueva (índice de la 040),
   el nodo del grafo de su carga y su P y Q. Una sola lectura por trabajo.
2. `src/convertersmartgrid/optimizacion_oraculo.py`: copia del grafo con una variante aplicada (banco,
   terna, sección, regulador), demanda con k cargas, flujo con `digital_twin.flujo`, medidas en
   la forma de `medida_para_criterio` (tensión por barra y cargabilidad por rama) y el criterio
   `escalera_optima.cumple`; búsqueda de k con `set_nueva.cuantas_caben` y elección con
   `escalera_optima.elegir`.
3. `web/services.optimizar_con_proyecto`: el oráculo busca y elige; DIgSILENT confirma con
   `obras_escalera` (la elegida con k y las más cercanas con k + 1, en el orden del oráculo y con
   «basta una»); discrepancias y tiempos en el informe; si el oráculo no puede, la búsqueda de la
   042 en DIgSILENT.
4. Pruebas con el doble de DIgSILENT y con redes sintéticas cuyo flujo se conoce; después, NA203
   + NA205 por la web.

## Ampliación del 2026-11-01 (RF-11 a RF-16), con los módulos que ya tiene el proyecto

5. Búsqueda bayesiana (RF-11, RF-12, RF-16) en `optimizacion_oraculo.buscar_combinacion`: Optuna
   (TPE, ya en el extra `ml`) con una variable entera por barra candidata (módulos de banco, 0 a
   `escalera.modulos_max`) y una categórica por tramo de la troncal (nada, terna o la sección que
   da `escalera_optima._conductores`); objetivo, el costo anual de `escalera_optima.costo`, con
   penalización por lo que no cumple (`cumple`). Presupuesto: `escalera.evaluaciones_bayes` del
   perfil (sin él, 200). Alternativa descartada: rejilla completa (crece como 4^tramos).
6. Frente de Pareto (RF-13): `digital_twin.evolutivo.nsga2` (el del gemelo, sin pymoo para no
   tener dos implementaciones) sobre el mismo genoma, con tres objetivos: costo, pérdidas y
   1 − tensión mínima.
7. Sorteos de Markov (RF-14): `optimizacion_oraculo.sorteos_markov`, de la curva de cabecera del
   año: niveles por cuantiles (`escalera.niveles_markov`, sin él 5), matriz de transición entre
   instantes consecutivos contada y normalizada, distribución estacionaria por el autovector de
   valor propio 1; cada sorteo es un instante de la cadena simulada desde el estacionario, con la
   semilla de la escalera. Misma forma que `escalera_optima.sorteos`.
8. Shapley (RF-15, RF-16): `optimizacion_oraculo.reparto_shapley`, permutaciones sorteadas
   (`escalera.permutaciones_shapley`, sin él 50); el costo de un grupo, el de la variante más
   barata de la lista que cumple con él, buscado desde la del grupo anterior (el costo no baja al
   añadir cargas), con memoria por grupo. Alternativa descartada: Shapley exacto (2^k grupos).

