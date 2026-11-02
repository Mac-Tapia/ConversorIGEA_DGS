# Plan — Spec 064

## 1. Todos por `pf_arnes.conectar` (RF-1, RF-2)

- `tools/build_system_grid.py`, `run_one_study.py` (sus dos conexiones),
  `convertir_grupos_mdb.py`, `prueba_representacion.py`, `check_pf_license.py` y
  `show_pf_diagram.py` sustituyen el `sys.path` a mano y `powerfactory.GetApplication()`
  por `pf_arnes.conectar('<guion>')`. `PFNoDisponible` se traduce al mensaje y al código
  3 que ya daban.
- `powerfactory_acceptance.py` sigue como está (RF-1, excepción), con su `tomar_turno`.
- `tests/test_pf_arnes_sin_atajos.py`: recorre `tools/*.py` y `src/**/*.py`, busca
  `GetApplication` (con y sin `Ext`, y por `getattr`) en código, no en comentarios ni
  cadenas de ayuda, y falla con fichero y línea fuera de `pf_arnes.py` y de la excepción.

Descartado: un `GetApplication` envuelto en cada guion. Repetiría el turno, el vigía y
la reconexión del 4002 en siete sitios.

## 2. La web lanza esos guiones como guiones de DIgSILENT (RF-3)

`web/services.system_command` usa el intérprete de `_require_pf()` y `run_system` le pasa
`pf_subprocess_env(pf_dir)`. Con `PF_PYTHON` en el entorno, `jobs.run_process` ya cierra
huérfanos y pone el límite de arranque. `build_system_grid` y `base_scenario` no son
servibles (importan proyectos, como la aceptación): siguen en su propio proceso.

## 3. El estado de cada orden (RF-4 a RF-7)

`src/convertersmartgrid/pf_estado.py`:

- `Foto` (dataclass): proyecto, caso, hora, escenario y variaciones activas.
- `fotografiar(app) -> Foto | None`.
- `restituir(app, foto) -> list[str]`: si el proyecto activo es el de la foto, reactiva
  el caso, repone su `iStudyTime`, activa el escenario (o desactiva el que haya) y deja
  activas exactamente las variaciones de la foto. Devuelve lo que cambió, en frases.

`tools/pf_servidor.atender` fotografía antes de `main` y, si el código no es 0 o hubo
excepción, restituye dentro del mismo registro de la orden. Un fallo de la restitución
se escribe y no tumba el servidor (RF-7).

Pruebas con un doble de la API (sin DIgSILENT), en `tests/test_pf_servidor.py`.

## 4. Servidor (RF-8)

`pf_arnes.GUIONES_SERVIBLES` añade `set_nueva_operacion_pf.py`, que ya conecta con
`conectar` y tiene `main(argv)`.

## Pruebas en DIgSILENT

Desde la web, abierta con el acceso directo del escritorio, sobre un proyecto ya
importado: una orden de estudios y otra que falle a propósito (un plan con un caso que no
existe) seguidas de una lectura que confirma el caso y la hora de antes.
