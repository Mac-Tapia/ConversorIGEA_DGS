# Tareas 102

- [x] T1. Puerta del commit: pruebas de gobierno y las del commit; para si fallan. (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` en verde.
- [x] T2. Puerta de la subida: variables, suite completa, sin fallidas ni omitidas, y resultado por revisión. (RF-5, RF-6,
      RF-7, RF-8, RF-9, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` en verde.
- [x] T3. Ganchos `pre-commit` y `pre-push`, y flujo de GitHub Actions con la suite sintética y el frontend. (RF-12, RF-13,
      RF-14, RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` en verde.
- [x] T5. GitHub con el entorno de desarrollo y la falta de GPU omitida con su motivo. (RF-17)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` en verde.
- [x] T4. La puerta en uso: un commit con la puerta activa, una subida que pasa la suite completa sin omitidas y el flujo
      de GitHub en verde. (RF-3, RF-9, RF-12)
      Hecho cuando: el resultado de la revisión está en `.git/puerta_calidad/` y GitHub muestra el flujo en verde.
      Evidencia (2026-11-10): 9d449eee entró por la puerta del commit (222 pruebas, 0 fallidas) y pasó la de la subida,
      suite completa con los datos reales: 8 615 pruebas, 0 fallidas, 0 omitidas (`.git/puerta_calidad/9d449eee….json`).
      GitHub Actions en verde en los dos trabajos (corrida 42896786760 del flujo CI, `gh run view 42896786760`):
      suite sintética 8 615, 0 fallidas, 188 omitidas por datos de la distribuidora o GPU; frontend 93 en verde.
      Por el camino la puerta detuvo y se corrigieron: cuatro fallas de la suite completa (048:RF-9, 076:RF-4, una
      intermitente de JSON a medio escribir y 086:RF-54) y las 71 que solo fallaban en GitHub (102:RF-17).
- [x] T6. Las ramas de trabajo suben sin la suite completa; la exige la integración en `main`. (RF-5, RF-18)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` en verde.
- [x] T7. La puerta lanza las pruebas sin las variables GIT_* del gancho. (RF-19)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` en verde.
- [x] T8. Cada prueba deja el entorno del proceso como lo encontró. (RF-20)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` en verde y la puerta sin fallos por orden.
- [x] T9. La puerta del commit corre la prueba de los procedimientos. (RF-21)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` (102:RF-21) en verde.
- [x] T10. Cada prueba con su guardia de GPU. (RF-22)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` (102:RF-22) en verde.
- [x] T11. La lista de variables de la puerta cubre las que nombran las pruebas y el ejemplo. (RF-23)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py` (102:RF-23) en verde.
- [x] T12. El lint de fronteras en GitHub Actions y en la puerta del commit cuando cambia `frontend/`. (RF-24)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q -rfs tests/test_puerta_calidad.py -k rf24` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_puerta_calidad.py -k rf24.
- [x] T13. Acciones de GitHub fijadas por SHA con su etiqueta en un comentario. (RF-25)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q -rfs tests/test_puerta_calidad.py -k rf25` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_puerta_calidad.py -k rf25.
- [x] T14. El flujo con `permissions: contents: read` en lo más alto. (RF-26)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q -rfs tests/test_puerta_calidad.py -k rf26` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_puerta_calidad.py -k rf26.
- [x] T15. Los dos checkout con `persist-credentials: false`. (RF-27)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q -rfs tests/test_puerta_calidad.py -k rf27` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_puerta_calidad.py -k rf27.
- [x] T16. Paso de ruff (`E9,F63,F7,F82`) en el trabajo del backend. (RF-28)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q -rfs tests/test_puerta_calidad.py -k rf28` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_puerta_calidad.py -k rf28.
- [x] T17. Un grupo de concurrencia común a la subida y a la petición de fusión de una rama. (RF-29)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q -rfs tests/test_puerta_calidad.py -k rf29` en verde.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_puerta_calidad.py -k rf29.
- [x] T18. PUERTA-ESPECULATIVA: el veredicto de un árbol (`--arbol`) y el gancho del commit que no repite la suite
      sobre ese mismo árbol; cualquier duda la repite; solo en la rama de trabajo, nunca en main ni en su subida
      (v2, condición de 0d). (RF-11, RF-9, RF-5)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py -k rf11` en verde: con el veredicto válido no la repite en la
      rama de trabajo, la repite en main, en otra rama y sin rama, el pre-push a main la corre fresca, y cada campo
      alterado, uno por uno, la fuerza.
- [x] T19. PUERTA-XDIST: la suite entera repartida en N procesos según la memoria libre, con lo que no admite paralelo
      en serie (`EN_SERIE` del conftest y la marca `gpu`) y lo que mide tiempos a solas; sin xdist o con poca memoria,
      N = 1. (RF-5)
      Hecho cuando: `pytest -q tests/test_puerta_calidad.py -k rf5` en verde: reparte con memoria, no con poca, y cada
      sesión se juzga por su cuenta.
- [ ] T20. La suite entera repartida da lo mismo que en una sola sesión: con N = 1, 2 y 3 sobre el mismo árbol, las
      mismas pruebas, 0 fallidas y 0 omitidas, el pico del árbol de procesos con ≥ 1,5 GiB libres, y `GIB_POR_PROCESO`
      fijado con el pico medido; es la T20 la que sube PROCESOS_MAXIMOS (hoy 1, FIX-XDIST-UNO) al N medido. (RF-5)
      Hecho cuando: el guion de comparación (PUERTA-XDIST/comparar_n.py), lanzado por b3 por los carriles en un hueco sin
      puerta, deja su informe con «iguales» y los picos, y la constante queda con su medida.
- [x] T21. El tope de la suite sintética en Actions con margen: `timeout-minutes` 180 en `ci.yml`. (RF-30)
      Hecho cuando: `pytest tests/test_puerta_calidad.py -k rf30` en verde. Hecho en esta entrega (FIX-CI-TOPE, 4d).
- [x] T22. Los dos arneses de navegador en un punto de entrada y en GitHub Actions (auditoría del 18-11, C5: H06).
      `frontend/test/e2e/todos.mjs` (`npm run e2e:todo`) y el trabajo `e2e` de `ci.yml`. (RF-31)
      Hecho cuando: `tests/test_ci_e2e_y_evidencias.py -k rf31` en verde, con rojo previo por aserción, y
      `npm run e2e:todo` corrido en local sobre la revisión con los dos arneses en verde.
- [x] T23. JUnit, veredicto y evidencias de la CI conservados y subidos aunque falle (C5: H07). (RF-32)
      Hecho cuando: `tests/test_ci_e2e_y_evidencias.py -k rf32` en verde, con rojo previo por aserción.
- [x] T24. Auditoría de dependencias de npm y de Python en cada subida, con versión fijada (C5: H14). (RF-33)
      Hecho cuando: `tests/test_ci_e2e_y_evidencias.py -k rf33` en verde, con rojo previo, y la auditoría local
      registrada (D:/csg/INTEGRA_54/auditoria_c0/pip_audit_venv.txt). Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/c5/`.
- [x] T25. El hook de sintaxis en todo el código del proyecto y las guías de Claude con rutas vigentes (auditoría
      del 18-11, C7: H10 y H11). (RF-34)
      Hecho cuando: `tests/test_gobierno_hook_y_guias.py` (102:RF-34) en verde, con rojo previo por aserción.
      Evidencia: `D:/csg/INTEGRA_54/auditoria_c0/c7/`.
