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
