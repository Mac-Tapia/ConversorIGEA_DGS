# Plan — Spec 081

Lee: `docs/constitution.md`, specs 015, 054, 057, 078, y las notas `reconstruir-no-bloquear` y `oraculo-corrige-antes-de-digsilent`.

| Parte | Cubre | Encaje |
| --- | --- | --- |
| Fases, contrato puro | RF-1 a RF-9 | `comprobacion_fases.py`; `reglas.aplicar_reglas`; `pandapower_preflight`; `tools/obras_pf.py` |
| Fases y lectura en DIgSILENT | RF-10 a RF-13 | `tools/powerfactory_acceptance.py`, solo lectura |
| Resultado del flujo | RF-14 a RF-16, RF-32 | `estado_flujo`, `estado_caso_base`, `classify_convergence`, `_importar_dgs_fijados` |
| Veracidad del trabajo | RF-17 a RF-24 | `comprobacion_flujo.py`, `web/jobs.py`, `web/services.py`, `tools/sistema_web.py`, front |
| Resolver | RF-25 a RF-31 | `resolver_convergencia.py` y el guion de aceptación |
| Huella | RF-33 a RF-36 | `comprobacion_flujo.py`, `_correr_guion_ajuste` |
| Suite | RF-37 a RF-41 | `asistente/vigilancia.py`, `tools/suite_por_tandas.py` |
| Cierre | RF-42 a RF-45 | `web/cierre.py`, `web/app.py`, `web/__main__.py` |
| Mejora continua | RF-46 a RF-49 | `docs/regresiones/`, `tests/test_regresiones.py` |
| Carpeta por empresa | RF-50 a RF-56 | `carpeta_pf.decidir_carpeta`, `web/services.destino_carpeta` y `carpeta_de`, opción `empresa_espacio` |

Decisiones:

- Carpeta: `empresa_ajena` no cambia, porque decide las convenciones del perfil (055:RF-6). La carpeta tiene su propia regla, en un solo sitio, porque
  ahí un dato ausente sí mezcla. Se reutiliza `asegurar_carpeta` (005:RF-5), que crea sin mover nada.
- `source_company` no vale de empresa del espacio: es lo elegido dentro de un paquete VNR-GIS y se borra al cambiarlo. Empresa y fuente son dos cosas (P13).
- La comprobación mira el modelo común y no cada fuente (P13). Descartado leer el DGS: el `.dgs` ya está fijado por su hash al importar,
  y se corrige antes, en `aplicar_reglas`, por donde pasa toda conversión (P5).
- Lo que llega a cada nodo se calcula aquí, de solo lectura, aunque la rama de fases traiga `fases_red.py`. Una guarda no reutiliza al
  corrector: si el corrector falla, ella tiene que verlo. Tras integrar, debe contar cero en esas clases.
- `dgs.py` y `model.py` no se tocan. El banco se corrige con `dataclasses.replace` en la regla, y el DGS ya le saca `ctech` de sus fases.
- `parcial` y `no_converge` son estados del trabajo, no una marca en el resultado. Descartado dejar `done` con una marca: es lo que
  leyó el operador. Es un trabajo que terminó con resultado: `CON_RESULTADO` en `jobs.py` y los consumidores (RF-23).
- El flujo no bloquea, y se corrige antes de bajar la demanda. Bajar por igual esconde la causa: 057 lo midió (del 90 % al 10 % sin converger).
  El orden es fases (corregibles), luego `converger_caso_base` (015:RF-38). Isla: no se inventa conexión; queda dicho.
- En DIgSILENT solo se corrige lo que es del elemento: `nphase` del acoplador y `ctech` del banco. Tramos y trafos comparten tipo: se dice
  y se reconvierte. Quien escribe es el guion, y DIgSILENT confirma con su flujo.
- `CONVERGE_SIN_SERVIR` entra en `CASO_BASE_CALIBRABLE` para no bloquear: VERIFICADO significa flujo limpio, y calibrar sigue permitido.
- La suite se lanza con un paso intermedio que termina enseguida. `taskkill /T` sigue la cadena de padres: sin intermedio, cerrar la web
  la mataba; `DETACHED_PROCESS` no basta.
- Vía demostrada de cierre: un lanzador de otro worktree con otra huella cierra la web del operador sin trabajos (RF-44). Y otra: `/F` a un
  servidor que tardó 8 s en contestar, por ejemplo con la suite corriendo (RF-45). Cualquier otra queda registrada por RF-42 y RF-43.
- Regresiones: una entrada por fallo, con cabeceras fijas para poder probarlas. La prueba resuelve `tests/x.py::test_y` con `ast`.

Pruebas: `tests/test_comprobacion_fases.py`, `tests/test_comprobacion_flujo.py`, `tests/test_resolver_convergencia.py`,
`tests/test_suite_por_tandas.py`, `tests/test_cierre_web.py`, `tests/test_regresiones.py`. Sintéticas, sin datos de la distribuidora; ninguna lanza
una suite real ni DIgSILENT.

Punto de unión con `fix/acopladores-con-fases`: `Elemento`, `Barra`, `comprobar` y `ubicar_nuevo` de `comprobacion_fases.py`. `poner_bancos` y
`resolver_nuevas` son de esa rama: llaman a `ubicar_nuevo` en vez de «no se crea».
