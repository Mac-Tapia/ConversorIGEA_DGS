# Plan 102

## Módulos

- `tools/puerta_calidad.py` (RF-1 a RF-11):
  - `--commit`: lee los ficheros preparados (`git diff --cached --name-only`). `pruebas_del_commit(ficheros, raiz)`
    devuelve las de gobierno (RF-1), más los ficheros de prueba preparados y las pruebas que nombran el módulo o la
    herramienta (RF-2), o solo las de gobierno si no hay código ni specs (RF-4). Corre pytest y para si algo falla (RF-3).
  - `--push`: `variables_de_la_suite(raiz, entorno)` toma `config/suite_completa.json` (fuera de git) y el entorno, y
    comprueba cada ruta (RF-6, RF-7). Corre la suite completa con `-rs` y `--junitxml`; `veredicto(junit)` lista las
    fallidas y las omitidas con su motivo (RF-8, RF-9). El resultado queda en `.git/puerta_calidad/<revisión>.json`
    (RF-10), y una revisión ya aprobada con el árbol limpio no se repite (RF-11).
  - `--ci`: la suite sintética, que para solo por fallos (RF-12, RF-14).
  - `--arbol` (RF-11, aclaración del 2026-11-15, PUERTA-ESPECULATIVA): `puerta_arbol(raiz)` exige el disco igual al
    índice (`indice_igual_al_disco`), corre la suite entera con las variables de la puerta y las del fichero local,
    copia el junit junto al veredicto y publica `arbol_<write-tree>.json` con `util.write_json_atomic`, después del
    junit; si el árbol cambió durante la suite no deja veredicto. `veredicto_de_arbol(arbol, raiz, entorno_pytest)` lo
    acepta solo si todo cuadra (árbol, forma, `firma_de_la_puerta`, `variables_de_la_firma`, `entorno_de_la_firma`,
    aprobado, edad dentro de `HORAS_VEREDICTO_ARBOL`, junit con su sha256 y releído con el mismo total). `--commit` lo
    consulta antes de lanzar pytest, y solo lo usa si `rama_actual()` está en `RAMAS_CON_VEREDICTO_DE_ARBOL` (v2, 0d);
    `--push` no lo consulta nunca.
  - Suite entera repartida (RF-5, aclaración del 2026-11-15, PUERTA-XDIST): `procesos_de_la_suite()` da N y su motivo
    con la memoria libre (psutil), `RESERVA_GIB` = 2, `GIB_POR_PROCESO` = 3 (provisional, del pico de 2,74 GiB de un
    trabajador en los ensayos de la 106:RF-16 con -n 2; b3 lo medirá con los datos reales) y `PROCESOS_MAXIMOS` = 3.
    `_pytest(..., procesos=N)`: con 1, la orden de siempre por `subprocess.run`; con N, `_partes_de_la_suite(N)` lanza con
    `subprocess.Popen` «serie» (`-m "(gpu or serie) and not a_solas"`) a la vez que «reparto» (`-m "not gpu and not serie
    and not a_solas"`, con `-n N-1 --dist loadfile` desde N = 3) y después «a_solas» (`-m a_solas`); cada sesión con su
    junit, juzgada por su cuenta (106:RF-8, RF-16; código 5 con el junit vacío no es fallo) y `_unir` las suma.
- `.githooks/pre-commit`: regenera el catálogo (090) y llama a `--commit`. `.githooks/pre-push`: llama a `--push`.
  Los activa `tools/generar_arquitectura.py --instalar-ganchos`, que ya fija `core.hooksPath` (RF-16).
- `.github/workflows/ci.yml` (RF-12 a RF-15): Windows, Python 3.12, `requirements.txt`, `python tools/puerta_calidad.py
  --ci`; Node, `npm ci`, `npm run build` y `npm test` en `frontend/`.
- `config/suite_completa.example.json`: las variables con rutas genéricas; `config/suite_completa.json` va en `.gitignore`.

## Decisiones

- El juicio sale del XML de JUnit, no del texto de pytest: el texto cambia con los complementos y con `-q`. Descartado:
  leer la última línea del registro.
- En GitHub se aceptan las omitidas de datos reales: allí no hay ni puede haber datos de la distribuidora (RF-15). La
  regla de cero omitidas la impone la subida local (RF-9).
- RF-11 por árbol y no por commit: el integrador monta un grupo, lo prueba y lo comete; el commit aún no existe cuando
  corre la suite, pero su árbol sí (`git write-tree`), y es lo que juzgan las pruebas. Ante cualquier duda se repite:
  un veredicto de más vale menos que una puerta que deja pasar otra cosa.

- RF-5 con dos sesiones a la vez y no con un solo xdist: con xdist cada trabajador importa el conftest y pediría el
  turno de la GPU de la máquina (106:RF-1), y el segundo esperaría al primero; y `--dist loadgroup` cambia el nombre de
  cada prueba agrupada en el junit («…@grupo»), que usan `fallos_de_puerta.tsv` y las listas de los carriles. Con una
  sesión «serie» aparte, el turno y el orden de las pruebas de GPU son los de siempre, y el resto (`--dist loadfile`)
  conserva sus nombres y sus fixtures de módulo.

### Lo que no admite paralelo (102:RF-5), revisado sobre `tests/` entero el 2026-11-15

| Fichero | Recurso | Va | Por qué |
|---|---|---|---|
| los 66 con `torch`, `cuda` o `gpu` (marca `gpu`, 106:RF-6) | GPU | serie | el turno de la máquina lo pide una sesión (106:RF-1); se nombran por su marca, no a mano |
| `test_vnr_sqlserver.py` | SQL Server | serie | con `CSG_VNR_BAK`, `sv.cargar_copia` restaura la copia real: DROP y RESTORE DATABASE `CSG_VNR_<huella>` |
| `test_asistente_vocabulario.py` | SQL Server | serie | `test_vnr_real` restaura la misma copia con `sv.cargar_copia` |
| `test_flexibility_and_scale.py` | CPU (tiempos) | a solas | coste por tramo de 4N frente a N; ya tumbó puertas en un solo proceso |
| `test_performance_budget.py` | CPU (tiempos) | a solas | presupuesto absoluto de segundos y cociente de 4N |
| `test_arquitectura_generada.py` | el árbol entero | a solas | catálogo generado frente al árbol; falló en los dos ensayos de la 106:RF-16 con -n 2 |
| `test_trazabilidad_specs.py` | el árbol entero | a solas | `specs/README.md` frente al árbol; falló en los mismos dos ensayos |

Revisadas y en paralelo, con su motivo:
- DIgSILENT: los ficheros que nombran PowerFactory usan `fake_pf` o un `powerfactory` falso en `sys.modules`, y el turno
  de la 019 es de cada prueba (`VARIABLE_TURNO` en `tmp_path`, conftest). La puerta no abre DIgSILENT (fuera de alcance).
- Word, Excel y COM: `test_informe_corrida`, `test_libro_informe`, `test_libro_perdidas_por_sistema` y
  `test_vnr_official_web` pasan `ejecutar=` o `clase_com=` falsos; `test_instalacion_programa` va en serie por `gpu`.
- Access: `test_access_input`, `test_linea_base_001`, `test_feeder_pa217`, `test_feeder_sl143` y `test_sistema_web`
  abren las `.mdb` con `ReadOnly=1` (`access.py`): lectura compartida.
- Puertos: `test_descarga_cancelable`, `test_lanzador_web`, `test_copia_datos` y `test_web_api` piden el puerto 0 (uno
  libre); `test_seguridad_web` (8791), `test_asistente_equipo` (8765), `test_monitor_agente` (9898) y
  `test_interactive_architecture` solo usan el número en textos o clientes falsos, sin abrirlo.
- Candados: `test_util`, `test_experimentos_runner` y los de la 106 los crean en `tmp_path`; la guardia de GPU de cada
  prueba es suya (102:RF-22).
- Datos de la sesión: cada sesión de pytest tiene su `CSG_SUITE_DATOS`, su runtime, los almacenes del asistente y del
  gemelo y las sesiones de la web (conftest, 106:RF-16 y RF-17); cada trabajador de xdist hereda la carpeta de
  su controlador y tiene dentro, bajo su nombre, su runtime y sus dos almacenes (MEJ15-T20: en el ensayo con -n 2 del
  13-11, dos trabajadores en el mismo almacén del asistente contaron 17 órdenes donde había 8). La comparación de T20
  (`tools/comparar_suite_repartida.py`) dirá si algo más depende del orden o del disco común: compara el veredicto de
  cada prueba, mide la memoria privada de cada proceso y por fichero, y mira que el disco del worktree no cambie.

## Pruebas

- `tests/test_puerta_calidad.py`: selección de pruebas, variables, veredicto del JUnit y caché por revisión, sintéticas.
  Ganchos y flujo de GitHub, leídos como texto.
