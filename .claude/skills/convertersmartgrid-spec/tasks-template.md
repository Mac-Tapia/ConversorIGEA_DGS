# Tareas — Spec NNN

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [ ] T1. <Qué>. (RF-1, RF-2)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/<fichero>.py` en verde.
- [ ] T2. <Qué>. (RF-3)
      Hecho cuando: <comprobación verificable>.
- [ ] Tn. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "NNN:RF-[0-9]+" tests | sort -u` lista todos los RF.
