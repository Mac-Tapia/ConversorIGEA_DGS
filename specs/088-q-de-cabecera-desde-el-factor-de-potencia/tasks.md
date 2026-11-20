# Tareas — Spec 088

- [x] T1. Q negativa desde el factor de potencia en la lectura de cabecera. (RF-1 a RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_q_desde_fp.py` en verde.
- [x] T2. MEJ3-CALIB (orden del usuario del 19-11): `derivacion_cliente` no da Q negativa a una fija sin EA/ERI con la
      cabecera capacitiva y `objetivo_de` saca la Q de una máxima sin kVAR con el signo de su FP. (RF-13, RF-14)
      Hecho cuando: rojo por aserción sobre faf67626 y verde con `tests/test_ajuste_cabecera.py -k "088"`.
      Hecho el 2026-11-19 (d8, fila MEJ2): rojo sobre la base por aserción (D:/csg/PM_IMPL/MEJ2/rojo.log) y verde en el
      hueco de MEJ2 (D:/csg/PM_IMPL/MEJ2/estado.txt: fase 1, pruebas nuevas con sus vecinas y e2e).
