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
- [ ] T4. La puerta en uso: un commit con la puerta activa, una subida que pasa la suite completa sin omitidas y el flujo
      de GitHub en verde. (RF-3, RF-9, RF-12)
      Hecho cuando: el resultado de la revisión está en `.git/puerta_calidad/` y GitHub muestra el flujo en verde.
