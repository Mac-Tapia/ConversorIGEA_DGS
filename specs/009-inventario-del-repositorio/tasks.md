# Tareas — Spec 009

- [x] T1. Retirar las 10 herramientas de RF-4; `fidelidad_seleccion.py` con argumentos;
      docstrings en español. (RF-4, RF-6, RF-8)
      Hecho cuando: `git ls-files tools` no lista ninguna de RF-4.
- [x] T2. `CODIGO_FUENTE.md` completo. (RF-1)
- [x] T3. `tests/test_inventario.py`. (RF-2, RF-3, RF-5, RF-7, RF-9, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_inventario.py` en verde.
- [x] T4. Manual de órdenes y README. (RF-12, RF-13)
      Hecho cuando: `pytest -q tests/test_inventario.py -k documentacion` en verde.
- [x] T5. Validación: `grep -rnoE "009:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-15; suite completa.
