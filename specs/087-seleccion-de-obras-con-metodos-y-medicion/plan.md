# Plan — Spec 087

Lee: `docs/constitution.md` y `specs/087-seleccion-de-obras-con-metodos-y-medicion/spec.md`.

## Contexto técnico
La escalera por alimentador es `escalera_por_alimentador` → `obras_escalera` (`web/services.py`). El oráculo es `optimizacion_oraculo.py`, que ya tiene
`Oraculo`, `buscar_combinacion`, `frente_pareto` y `sorteos_markov`, y lo usa `_optimizar_con_oraculo`, el camino por bisección de k de la 052.
La evaluación con sorteos es `evaluar` en `tools/obras_pf.py`. La estadística de órdenes es `estadistica_ordenes.py` (081).

## Diseño por partes
| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Orden por oráculo y tandas | `web/services.py`, `optimizacion_oraculo.py` | RF-1 a RF-6, RF-10 a RF-13 |
| Parada bayesiana | `seleccion_bayesiana.py` (nuevo), `tools/obras_pf.py` | RF-7 a RF-9 |
| Etapas | `planeamiento_etapas.py` (nuevo) | RF-14 a RF-16 |
| Modelo aprendido | `modelo_obras.py` (nuevo) | RF-17 a RF-20 |
| Medición | `medicion_obras.py` (nuevo), `tools/medir_mejora.py` (nuevo) | RF-21 a RF-27 |

## Decisiones
- Posterior Beta(1 + cumplen, 1 + no cumplen) con `scipy.special.betainc`. Descartado: parar a la 11.ª falla con 200 sorteos, porque no dice la certeza y no para cuando ya está clara a favor.
- Inducción hacia atrás exacta en el proceso de decisión de Markov. Descartado: aprendizaje por refuerzo, porque el problema es pequeño y su solución exacta es reproducible.
- Clasificador `GradientBoostingClassifier` de scikit-learn, ya instalado, con validación dejando fuera un sistema. Descartado: partir por variante, porque variantes del mismo alimentador filtrarían información y darían una mejora falsa.
- Sin XGBoost ni LightGBM: no están instalados y no se justifica otra dependencia con tan pocos datos.
- La medición se hace en un JSONL propio. Descartado: ampliar `ordenes.jsonl`, que es por orden y no por corrida.

## Comprobación contra la constitución
- 1: semillas fijas en Optuna, Markov, Beta y el árbol.
- 2: por alimentador, sin recorrer tablas enteras por cada uno.
- 7: todo dentro de los trabajos que ya existen.
- 9: `corridas_obras.jsonl` y el conjunto del modelo son locales, sin nombres de clientes, y no salen de la máquina.
- 11, 12: cada RF con prueba que lo cita.
- 13: nada de empresa ni de tensión fijada.

## Estrategia de pruebas
- Sintéticas sorteadas, sin DIgSILENT, con dobles de `obras_escalera` y de `_guion_pf`.
- Beta contra casos de valor conocido.
- Inducción hacia atrás contra un caso resuelto a mano.
- Modelo con datos sintéticos: uno que acierta pasa la puerta y uno al azar no.
- Cada prueba cita su requisito: `"""087:RF-n — …"""`.

## Riesgos
- El oráculo puede dar por buena una variante que DIgSILENT rechaza: lo cubren las tandas (RF-3) y el registro de discrepancias (RF-6).
- El oráculo puede rechazar una variante que sí cumple: tras agotar sus cumplidoras se miden las demás (RF-3), lo que cuesta tiempo pero no pierde solución.
