# Plan — Spec 019

Lee: `docs/constitution.md` y la spec. Piezas que ya hay: `powerfactory_env.procesos`,
`terminar_arbol`, `cerrar_guiones_pf_huerfanos`, `powerfactory_abierto`; el carril
`powerfactory` de `web/jobs.py`; `CONSTRUCTORES` de `tools/obras_pf.py`.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Turno del motor | `src/igea_dgs/pf_arnes.py` (nuevo): `turno_del_motor(guion)`, un fichero de turno de la máquina (`%LOCALAPPDATA%/igea_dgs/powerfactory.turno`, con pid, guion y hora) creado en exclusiva; espera con aviso hasta 600 s; si el pid ya no vive, lo libera; si hay `PowerFactory.exe` abierto, error que lo dice | RF-1, RF-2, RF-4, RF-13 |
| B. Conexión común | `pf_arnes.abrir(guion)`: turno + `GetApplicationExt` con reintentos ante 4002 hasta el límite, primera línea (005:RF-21), tiempos de cada paso; y `caso_restituido(app)` que deja el caso activo como estaba. Los 13 guiones de `tools/` lo usan en su `main` | RF-3, RF-5, RF-6, RF-10 |
| C. Proceso que se queda | `tools/pf_servidor.py` (nuevo): abre con B y atiende órdenes de una carpeta de cola (`orden.json` → `respuesta.json`), llama a la `ejecutar(app, plan)` del guion pedido sin volver a activar si el proyecto es el mismo; se cierra a los 120 s sin órdenes o si deja de responder. `web/services._guion_pf` lo usa si está vivo y, si no, lanza el guion como hoy | RF-7, RF-8, RF-9 |
| D. Obras enchufables | `src/igea_dgs/obras_pf.py`: registro `VALIDADORES` por clase junto a `CONSTRUCTORES`; clase nueva `consigna` (tensión de la red externa en p.u., entre los límites del perfil, solo «Con proyecto») con su validación, su simulación y su construcción en el escenario de «Con proyecto» | RF-11, RF-12 |

## Decisiones

- Turno con un fichero creado en exclusiva (`os.O_EXCL`) y no con un mutex de Windows:
  funciona igual desde la web, el CLI y otra sesión, y se puede leer para decir quién lo
  tiene. Descartado: el carril de la web, que no ve a los procesos de fuera.
- Cola por carpeta y no por socket: no abre puertos y sobrevive a reinicios de la web.

## Pruebas

- `tests/test_pf_arnes.py`: turno exclusivo entre dos procesos, espera y aviso, pid muerto,
  DIgSILENT abierto, reintento ante 4002 (doble de `powerfactory`), restitución del caso.
- `tests/test_inventario.py` amplía: ningún `GetApplicationExt` fuera de `pf_arnes`.
- `tests/test_pf_servidor.py`: dos órdenes con una sola activación y cierre por inactividad,
  con `fake_pf`.
- `tests/test_obras_pf.py`, `tests/test_obras_pf_guion.py`: la obra `consigna`.
- Prueba real (P11): dos guiones a la vez, tres órdenes seguidas, consigna en CA101.
