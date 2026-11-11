# Tareas — Spec 103

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Detección de todas las instalaciones y elección de la carpeta de la API por intérprete disponible. (RF-1, RF-2)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_powerfactory_versiones.py` en verde.
- [ ] T2. La más nueva por defecto, `PF_PYTHON` y la elección del operador recordada; ruta de la web. (RF-3)
      Hecho cuando: `tests/test_powerfactory_versiones.py` (103:RF-3) en verde.
- [x] T3. Mensajes y diagnóstico sin versión fija; sin DIgSILENT se sigue convirtiendo. (RF-4, RF-7)
      Hecho cuando: `tests/test_powerfactory_versiones.py` (103:RF-4, RF-7) en verde.
- [ ] T4. Guiones de DIgSILENT compatibles con Python 3.9 y sin más librerías que `numpy`. (RF-5)
      Hecho cuando: `tests/test_powerfactory_versiones.py` (103:RF-5) en verde.
- [ ] T5. Selector de instalación en la web. (RF-3)
      Hecho cuando: `npm test` en verde y probado en el navegador con la PowerFactory de la máquina.
- [ ] T6. Python embebidos en el instalador. (RF-6)
      Hecho cuando: el candidato construido trae 3.9, 3.10 y 3.11 con su SHA-256 y `numpy`, y `csg.cmd doctor` los lista.
- [ ] T7. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "103:RF-[0-9]+" tests | sort -u` lista los 7 RF.
