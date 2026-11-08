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

Decisiones de los cierres (RF-57 a RF-63):

- Un control sin verificar (sin contrato, con el modelo o el DGS distintos de su contrato, o un cálculo que revienta) cuenta como «el oráculo no puede
  calcular»: se importa con su aviso. Sigue en `no_convergen`, que ya solo informa; lo que para va en `red_vacia` y en los errores de fijar la copia.
- Un error al fijar la copia del DGS sí deja ese alimentador fuera (RF-60): no es un veredicto, es que no hay fichero que importar con su hash.
- `nombre_de_perfil` sigue rechazando una carpeta mal escrita (005:RF-4) para quien lo llame directo: guiones sueltos y `pf_proyectos`. Decide la web, en `decidir_carpeta`.

Decisiones:

- Carpeta: `empresa_ajena` no cambia, porque decide las convenciones del perfil (055:RF-6). La carpeta tiene su propia regla, en un solo sitio, porque
  ahí un dato ausente sí mezcla. Se reutiliza `asegurar_carpeta` (005:RF-5), que crea sin mover nada.
- `source_company` no vale de empresa del espacio: es lo elegido dentro de un paquete VNR-GIS y se borra al cambiarlo. Empresa y fuente son dos cosas (P13).
- El panel de entradas guarda `empresa_espacio` por separado en TXT, MDB y VNR. El nombre declarado por la fuente conserva prioridad. Guardar vacío retira el dato con `null`; un PUT que omite el campo lo conserva. El control se bloquea durante un trabajo del motor o DIgSILENT. No mueve proyectos existentes ni sustituye su vínculo al cambiar el nombre.
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
`tests/test_suite_por_tandas.py`, `tests/test_cierre_web.py`, `tests/test_regresiones.py`. Sintéticas, sin datos de la distribuidora.
P21 añade una suite real minúscula de una prueba propia en un repositorio temporal: verifica que el proceso
separado sobrevive a matar su servidor y que su muerte abrupta se reconoce como interrumpida.
No ejecuta la suite completa ni DIgSILENT y no cierra T14, que exige el ensayo nocturno completo.

Punto de unión con `fix/acopladores-con-fases`: `Elemento`, `Barra`, `comprobar` y `ubicar_nuevo` de `comprobacion_fases.py`. `poner_bancos` y
`resolver_nuevas` son de esa rama: llaman a `ubicar_nuevo` en vez de «no se crea».

Lo nuevo con las fases de su barra (RF-64 a RF-69, T19):

- `comprobacion_fases.py`: `FASES_POR_PHTECH` (un solo sitio; la aceptación lo importa), `fases_de_phtech` y `corriente_por_fase_a`, puros.
- `tools/cargas_pf.py`: `resolver_nuevas` mira las fases del punto (`fases_en_el_punto`: el tramo que se parte o la barra) y pasa por
  `ubicar_sed_nueva` (`ubicar_nuevo`): la compatible más cercana o, sin ninguna, `fases` en lo resuelto y el aviso con `cifras_de_sed_adaptada`.
  `crear_carga` da esas fases a las barras (`poner_fases`), al interruptor, al trafo (`_tipo_trafo(..., n)`) y a la línea
  (`tipo_de_linea_con_fases`, copia `_nF` que el deshacer borra como los tipos de trafo).
- `tools/ajuste_cabecera_pf.py::poner_bancos` y `tools/obras_pf.py::construir_condensador`: primero barras trifásicas; las que faltan, con las
  fases de su barra (`adaptar_banco`, el `ctech` del DGS) y aviso con `cifras_de_banco`.
- Descartado: dejar el elemento trifásico en la barra de menos fases con solo el aviso. Es el fallo de origen: DIgSILENT no calcula nada.
- RF-70: `web/services.py::AVISO_CATALOGO_APLICADO`, que devuelve `apply_catalog` y escriben el Registro (`web/app.py`) y el aviso de
  `Modules.tsx`. Descartado: corregir solo las dos frases, que ya se habían separado una vez del código.

Lo que una variante cortada deja abierto (RF-80 a RF-85, T30):

- `tools/obras_pf.py::abrir` es la única vía para abrir en una obra: anota `[clase, nombre, caso]` en `fila['abiertos']` y en el
  registro de disco (`convertersmartgrid/obras_pf.py::fichero_aperturas`, uno por proyecto y carpeta en
  `~/.convertersmartgrid/aperturas_pf` o `CSG_APERTURAS_DIR`; el plan puede dar `aperturas_fichero`), y después abre.
- `restituir_lo_abierto` en el `finally` de `evaluar.con_variante`, tras borrar la variación; `cerrar_lo_abierto` busca también en
  los datos de red, porque `GetCalcRelevantObjects` no da lo fuera de servicio. `aplicar` saca del registro lo de las obras que quedan.
- `restituir_pendientes` al empezar `aplicar`, `evaluar` y `datos_escalera` (y con ella `datos_oraculo`): cierra, guarda el escenario
  (`IntScenario.Save`, referencia de Python de PF 2024, 5.6.38) y avisa.
- `comprobar_servicio_con_proyecto` en `datos_escalera`: una pasada por clase en cada caso (P2), lo grabado por las variaciones
  activas (`_grabados`) como explicación, y `ElmTerm.IsEnergized` tras un flujo en los dos casos para saber si corta.
- Descartado: dejar la apertura en la etapa de la variación con el escenario inactivo. El escenario guarda el servicio de todos los
  elementos y manda sobre la red al volver a activarlo (`IntScenario.Save`: «all operational attributes for all active network
  elements»), así que la variación no lo explicaría; y la referencia no documenta un modo de grabar datos de operación en la etapa
  con un escenario activo. Descartado también restituir todo lo que no explique una variación: borraría cambios del operador.
