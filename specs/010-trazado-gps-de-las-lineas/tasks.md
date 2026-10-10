# Tareas — Spec 010

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Tabla `Matrix` en el perfil y trazado de cada línea en `write_dgs`. (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_trazado_gps.py` en verde.
- [x] T2. El validador acepta el FID repetido de `Matrix` y compara el trazado releído con la geografía. (RF-5)
      Hecho cuando: `pytest -q tests/test_trazado_gps.py tests/test_validate*.py` en verde.
- [x] T3. La aceptación en PowerFactory compara el trazado de las líneas con el manifiesto. (RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_powerfactory_gate.py` en verde.
- [x] T4. 001:RF-14 anota la excepción y se regenera `output/linea_base_001.json`.
      Hecho cuando: `pytest -q tests/test_linea_base_001.py` en verde con las tres `IGEA_*`.
- [x] T5. Prueba real: red unida NA203 + NA205 importada en PowerFactory con `--manifest`. (RF-6, RF-7)
      Hecho cuando: el informe da 0 líneas con trazado distinto del manifiesto.
- [x] T6. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "010:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-7.
