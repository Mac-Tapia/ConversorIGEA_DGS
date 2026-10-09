# Tareas — Spec 005

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. `src/igea_dgs/carpeta_pf.py`: nombre por defecto, validación y lectura de
      `config/perfil_empresa.json`; `config/perfil_empresa.example.json` versionado y
      `config/perfil_empresa.json` local con «sistemaeletricoELD», fuera de git. (RF-2, RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_carpeta_pf.py` en verde,
      con la prueba de que `src/` y `tools/` no contienen el nombre de la empresa.
- [x] T2. Doble de PowerFactory: `IntFolder`, `Move`, `Delete`, `ComImport` simulado y
      fallo opcional al mover, en `tests/fake_pf.py`. (apoyo de RF-5 a RF-9)
      Hecho cuando: `tests/test_cargas_pf_guion.py` sigue en verde con el doble ampliado.
- [x] T3. Árbol: `buscar_carpeta`, `asegurar_carpeta`, `nombre_libre`, `proyectos_de` con
      subcarpetas sorteadas, `proyecto_por_ruta`. (RF-1, RF-5, RF-7, RF-12, RF-13, RF-16)
      Hecho cuando: `pytest -q tests/test_carpeta_pf.py` en verde.
- [x] T4. `alimentadores_de` en los datos de red, con la búsqueda completa de reserva y su
      nota. (RF-17, RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_carpeta_pf.py` en verde.
- [ ] T5. `import_dgs_file` con carpeta: nombre provisional, mover, nombre libre, activar
      por objeto, borrar el recién creado si mover falla; informe con `project_folder` y
      `project_path`; los proyectos de la raíz no se tocan. (RF-5, RF-6, RF-7, RF-8, RF-9, RF-20)
      Hecho cuando: `pytest -q tests/test_carpeta_pf.py tests/test_powerfactory_gate.py` en verde.
- [ ] T6. `--pf-carpeta` en `powerfactory_acceptance.py`, `build_system_grid.py`,
      `convertir_grupos_mdb.py`, `prueba_representacion.py` y `run_one_study.py`, con el
      perfil cuando falta. (RF-10)
      Hecho cuando: una prueba recorre los cinco guiones y comprueba que pasan la carpeta a
      `import_dgs_file`; `--help` de cada uno sale con 0.
- [ ] T7. `tools/pf_proyectos.py --carpeta`: solo la carpeta, aviso si no existe, sin
      escribir. (RF-11, RF-13, RF-14, RF-15)
      Hecho cuando: `pytest -q tests/test_carpeta_pf.py` en verde, con la prueba de que el
      doble no registra ninguna creación ni escritura al leer.
- [ ] T8. Web: `services.pf_projects` y `powerfactory_flow` pasan la carpeta validada;
      nombre inválido falla sin lanzar el guion; `ws.pf_projects` guarda la ruta.
      (RF-2, RF-4, RF-10, RF-16)
      Hecho cuando: `pytest -q tests/test_web*.py` en verde.
- [ ] T9. Cargas por ruta: el plan lleva la ruta y la carpeta; `tools/cargas_pf.py`
      activa con `proyecto_por_ruta`. (RF-16)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion.py tests/test_cargas_pf.py` en verde.
- [ ] T10. Front: `PfProject.path`, desplegable por ruta con « / » y aviso de carpeta
      inexistente. (RF-12, RF-14, RF-16)
      Hecho cuando: `cd frontend && npm run build` sin errores de tipos.
- [ ] T11. Validación: cada RF citado por al menos una prueba y en verde; suite completa
      con las variables `IGEA_*`. (Todos)
      Hecho cuando: `grep -rnoE "005:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-20.
- [ ] T12. Prueba manual en DIgSILENT (la hace el usuario): importar dos DGS, uno con
      nombre repetido, crear una subcarpeta y leer los proyectos. (RF-5 a RF-17)
      Hecho cuando: el usuario lo confirma, y la lista de caracteres no admitidos queda
      comprobada.
