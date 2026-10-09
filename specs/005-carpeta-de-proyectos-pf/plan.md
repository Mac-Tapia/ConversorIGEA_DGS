# Plan — Spec 005

Lee: `docs/constitution.md` y `specs/005-carpeta-de-proyectos-pf/spec.md`.

## Contexto técnico

- Toda importación de DGS pasa por `import_dgs_file` (`tools/powerfactory_acceptance.py`):
  `ComImport` con `iopt_prj=0` crea el proyecto en la raíz del usuario y luego lo activa
  por nombre. La llaman la web (`powerfactory_flow` en `web/services.py`, por la línea de
  órdenes de `powerfactory_acceptance.py`) y los guiones `build_system_grid.py`,
  `convertir_grupos_mdb.py`, `prueba_representacion.py` y `run_one_study.py`.
- «Leer proyectos» es `tools/pf_proyectos.py`, lanzado por `services.pf_projects` en el
  carril `powerfactory`: recorre `GetCurrentUser().GetContents('*.IntPrj')` y, en cada
  proyecto, `GetContents('*.ElmFeeder', 1)` sobre todo el árbol.
- El guion de cargas (`tools/cargas_pf.py`, `activar_proyecto`) busca el proyecto por
  nombre en la raíz del usuario; el plan de la web lo guarda en `plan['project']`.
- La web elige el proyecto en `frontend/src/components/CargasTab.tsx` por `p.name`
  (`PfProject` en `frontend/src/types.ts`).
- Precedente de convención de empresa en un fichero local: `config/demanda_medida_alias.json`
  (spec 004), con su `.example.json` versionado.
- Los guiones de PowerFactory ya importan `igea_dgs` (`powerfactory_metadata`, `economia`),
  con `PYTHONPATH=src` desde la web.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Regla del nombre y perfil | `src/igea_dgs/carpeta_pf.py` (nuevo): `NOMBRE_POR_DEFECTO`, `validar_nombre`, `nombre_de_perfil(ruta)`; `config/perfil_empresa.example.json`; `config/perfil_empresa.json` local (no versionado) con «sistemaeletricoELD» | RF-2, RF-3, RF-4 |
| Árbol de DIgSILENT | `src/igea_dgs/carpeta_pf.py`: `buscar_carpeta(user, nombre)`, `asegurar_carpeta(user, nombre)`, `nombre_libre(carpeta, nombre)`, `proyectos_de(carpeta)` → `[(ruta_relativa, IntPrj)]`, `proyecto_por_ruta(carpeta, ruta)`, `alimentadores_de(proyecto)`. Solo usan la API por duck typing, sin importar `powerfactory`; se prueban con `tests/fake_pf.py` | RF-1, RF-5, RF-7, RF-12, RF-13, RF-16, RF-17, RF-18, RF-19 |
| Importación | `import_dgs_file(app, dgs, project_name=None, carpeta=None)`: importa con un nombre provisional único en la raíz, mueve el proyecto a la carpeta, le da el nombre libre y lo activa por objeto (`prj.Activate()`), no por nombre. Si mover falla, borra ese proyecto recién creado y devuelve error con la carpeta. El informe añade `project_folder` y `project_path` | RF-5, RF-6, RF-7, RF-8, RF-9 |
| Guiones | `--pf-carpeta` en `powerfactory_acceptance.py`, `build_system_grid.py`, `convertir_grupos_mdb.py`, `prueba_representacion.py`, `run_one_study.py`; sin la opción, `nombre_de_perfil(config/perfil_empresa.json)` | RF-10 |
| Activar después de importar | `carpeta_pf.activar_proyecto(app, ruta, carpeta)`: busca la ruta en la carpeta y, si no está, un proyecto de la raíz con ese nombre exacto (los anteriores, RF-20), y lo activa por objeto. La usan los estudios de `run_one_study.py` (que antes hacían `ActivateProject(nombre)`, que solo mira la raíz), `check_pf_license.py --project` y `show_pf_diagram.py`. `base_scenario.py` pasa a los estudios el proyecto que devolvió la importación, que puede llevar `_2`, y `--pf-carpeta` | RF-10, RF-16 |
| Lectura | `tools/pf_proyectos.py --carpeta`: lista `proyectos_de`, alimentadores con `alimentadores_de`, `{'folder', 'exists', 'aviso', 'projects': [{name, path, feeders}]}`. Si no existe la carpeta: lista vacía y aviso, sin crearla | RF-11, RF-13, RF-14, RF-15 |
| Web | `services.pf_projects` y `powerfactory_flow` pasan `--carpeta`/`--pf-carpeta` tomada de `nombre_de_perfil`, validada antes del subproceso; `ws.pf_projects[feeder]` guarda la ruta | RF-2, RF-4, RF-10, RF-16 |
| Cargas | `tools/cargas_pf.py`: `activar_proyecto(app, carpeta, ruta)` con `proyecto_por_ruta`; el plan lleva `project` = ruta y `folder` | RF-16 |
| Front | `PfProject.path`; el desplegable usa `path` como valor y lo muestra con « / »; aviso de RF-14 bajo el botón | RF-12, RF-14, RF-16 |

## Decisiones

- **Mover tras importar con nombre provisional.** `ComImport` con `iopt_prj=0` crea en la
  raíz; el proyecto se importa como `_igea_<sello>`, se mueve con `carpeta.Move(prj)` y se
  renombra con el nombre libre. Descartado: el atributo de carpeta destino de `ComImport`,
  porque no aparece en el ejemplo oficial de la API que sigue el guion y no está probado en
  PF 2024; y descartado importar con el nombre final en la raíz, porque chocaría con los
  proyectos anteriores que siguen allí (RF-20) y DIgSILENT renombraría o fallaría.
- **Una sola implementación en `src/igea_dgs/carpeta_pf.py`.** Los guiones ya importan
  `igea_dgs`; la web valida el nombre con la misma función antes de abrir DIgSILENT (RF-4).
  Descartado un `tools/pf_carpeta.py`, porque la web tendría que copiar la validación (P5).
- **El nombre de la empresa en `config/perfil_empresa.json`, local y fuera de git.** Igual
  que `demanda_medida_alias.json`. Cuando exista el perfil de la spec 002 (RF-31), la clave
  `carpeta_proyectos_pf` pasa a él sin cambiar la regla. Descartado guardarlo en las
  opciones de cada espacio de la web, porque cada espacio nuevo volvería al nombre por
  defecto y los guiones no lo verían.
- **El proyecto se identifica por su ruta relativa** con `/` como separador
  (`2026-10/SI213`); la interfaz la muestra con « / ». Descartado el nombre solo, porque dos
  subcarpetas pueden tener un proyecto con el mismo nombre (RF-16).
- **Alimentadores en los datos de red.** `alimentadores_de` toma las carpetas de modelo de
  red del proyecto (`IntPrjfolder` de tipo `netdat`) y busca `ElmFeeder` solo ahí,
  recursivo; si no hay ninguna, busca en todo el proyecto como hoy y lo anota (RF-18).
  Descartado `app.GetProjectFolder('netdat')`, porque solo vale para el proyecto activo y
  leer no activa nada (RF-15).
- **Validación del nombre:** no vacío tras quitar espacios, ≤ 40 caracteres y sin
  `\ / : * ? " < > | .` [NECESITA ACLARACIÓN en la prueba manual: la lista exacta de
  caracteres que DIgSILENT rechaza en `loc_name`; se toma la de Windows más el punto, que
  DIgSILENT usa como separador de clase].

## Comprobación contra la constitución

- **P2 Escala:** ningún número fijo de proyectos ni de alimentadores; las pruebas sortean
  cuántos proyectos y subcarpetas crea el doble.
- **P5 Una sola vía:** una implementación de la carpeta, usada por la web y todos los guiones.
- **P7 Carril `powerfactory`:** la lectura y la importación siguen en cola; no se añade nada
  dentro de una petición HTTP.
- **P9 Datos:** las pruebas usan el doble, sin datos de la distribuidora.
- **P10 Idioma:** español.
- **P13 Universal:** el código solo conoce «Conversor IGEA-DGS»; «sistemaeletricoELD» vive
  en el perfil local. La comprobación de universalidad de la spec 002 aún no existe; hasta
  entonces, una prueba exige que ni `src/` ni `tools/` contengan ese nombre.

## Estrategia de pruebas

- No toca el lector ni el modelo: no hacen falta las dos disposiciones ni los datos reales.
- `tests/fake_pf.py` gana `IntFolder`, `Move`, `Delete` y `ComImport` simulado (crea un
  `IntPrj` en la raíz), y la opción de fallar al mover.
- `tests/test_carpeta_pf.py`: reglas de nombre, perfil, carpeta, nombre libre, rutas con
  subcarpetas sorteadas y alimentadores; `import_dgs_file` con el doble.
- Ampliar `tests/test_cargas_pf_guion.py` (proyecto por ruta) y las pruebas de la web
  (`services.pf_projects` pasa la carpeta; nombre inválido falla sin lanzar el guion).
- Prueba del front: `npm run build` y su comprobación de tipos.
- Cada prueba cita `005:RF-n`.
- Prueba real en DIgSILENT, la hace el usuario a mano (memoria «no probar PF con datos
  inventados»).

## Riesgos

- `Move` sobre un proyecto recién importado puede fallar si DIgSILENT lo deja activo o
  bloqueado tras `ComImport`; se detecta en la prueba manual y el error nombra la carpeta.
- La estructura de carpetas `netdat` puede variar en proyectos hechos a mano: RF-18 lo cubre.
- Los informes de aceptación antiguos no traen `project_path`: `_proyecto_importado` cae al
  nombre.
- *Hallado en la T6 (2026-10-09):* `run_one_study.py` activaba cada estudio con
  `ActivateProject(nombre)`, que solo busca en la raíz; tras importar en la carpeta, el
  estudio no encontraba el proyecto o activaba uno antiguo con el mismo nombre. Lo
  cubre la fila «Activar después de importar».
- Que el guion de un usuario llame a `import_dgs_file` sin carpeta: toma la del perfil o la
  de por defecto, así que todo cae en una carpeta, nunca en la raíz.
