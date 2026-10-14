# Plan — Spec 015

Lee: `docs/constitution.md`, `specs/015-caso-base-verificado/spec.md` y, por los requisitos
que cambia, las specs 006, 011 y 014.

## Contexto técnico

Hoy la verificación del modelo físico está partida en dos sitios:

- `tools/powerfactory_acceptance.py`. Con `--manifest` (importación desde la web)
  `run_acceptance` ya compara el GPS de las barras con el manifiesto, el trazado de las
  líneas (`compare_line_gps`, spec 010), la conectividad de las líneas, el diagrama, los
  recuentos de equipos y los bancos (`reread_capacitors`). Con `--existing-project` y
  sin manifiesto (CA101, 2026-10-13) solo corre el flujo, y `attach_project_binding`
  vincula el proyecto como `IDENTIDAD_VERIFICADA_PENDIENTE_CONVERGENCIA`. Ninguna de las
  dos vías compara la potencia de los transformadores ni la corriente de las líneas.
- `src/igea_dgs/powerfactory_binding.py`. `promote_project_binding_after_calibration`
  da el vínculo por verificado cuando cuadra un ajuste (`services.ajuste_ejecutar`).

La calibración (`tools/ajuste_cabecera_pf.py`) crea una variación `Ajuste_<alim>_…`,
mide con el escenario apagado y luego copia el resultado a los escenarios. De esa
variación dependen `services.base_del_ajuste` (cargas y estudios), `casos_pf.preparar`
(«no hay ajuste aplicado»), `casos_pf.clasificar` y la detección del cambio manual de
la 014 (`cambios_manuales`, que lee la etapa del último ajuste).

Piezas que se reutilizan: `validate.parse_dgs` (lee el DGS del archivo original, ligado al
vínculo por `dgs_sha256`); el inventario nativo (`native_inventory_records`, que no
incluye P/Q, así que calibrar no lo cambia) y su aviso `PROJECT_BINDING_NATIVE_MODIFIED`;
`casos_pf._escenario_propio` y `_marcar`.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Equipos del archivo original | `src/igea_dgs/capacidades.py` (nuevo): de las tablas del DGS, `strn`×`ntnum` de cada `ElmTr2` y `sline`/`InomAir`×`nlnum` de cada `ElmLne`, y de cada `TypTr2` el grupo de conexión (`tr2cn_h`, `tr2cn_l`, `nt2ag`) y la tensión de baja (`utrn_l`); comparación con lo leído en DIgSILENT → sin dato / distinto, con lo que toca hacer con cada uno (capacidad distinta: aviso; grupo o tensión de baja: corregir) | RF-6, RF-7, RF-11, RF-32, RF-33 |
| B. Verificación del «Caso base» | `tools/powerfactory_acceptance.py`: `run_acceptance` también con `--existing-project`, que pasa a exigir `--manifest`; activa el caso marcado «Caso base» si existe; añade la conectividad de las cargas, las capacidades, el grupo de conexión y la tensión de baja de los transformadores de SED (A) y la lista de variaciones activas; el flujo, sin remedios (`--fix-until-converge` prohibido aquí); el informe dice el resultado de cada comprobación | RF-1 a RF-9, RF-12, RF-31 a RF-33 |
| B2. Corrección de transformadores de SED | `tools/powerfactory_acceptance.py`, antes del flujo: a cada `ElmTr2` con grupo o tensión de baja distintos se le asigna un tipo con los valores del archivo original (el mismo `TypTr2` si todos los que lo usan necesitan la corrección; si no, una copia del tipo con su nombre y los valores corregidos), como ya hace `reread_capacitors` con los bancos | RF-34 a RF-36 |
| C. Estado del vínculo | `powerfactory_binding.py`: `native_reread['caso_base'] = {alimentador: {status, fallos}}`; `caso_base_verificado(ws, proyecto, alimentadores)`; desaparecen `IDENTIDAD_VERIFICADA_PENDIENTE_CONVERGENCIA` y `promote_project_binding_after_calibration` | RF-10, RF-13, RF-22 |
| D. Web: verificar el «Caso base» | `web/services.py` (`pf_verificar_base`), su ruta y `frontend/src` (paso 1 de la pestaña de cargas): botón, tabla por alimentador y comprobación, repetible | RF-9, RF-14 |
| E. Casos | `tools/casos_pf.py`: `preparar_sin` (marca el «Caso base» y lo copia a «Sin proyecto» con una copia de su escenario, solo si está verificado, sin activar variaciones) y `preparar_con` (copia de «Sin proyecto» con escenario propio); sale el camino `sin_base` | RF-16 a RF-18, RF-27, RF-28 |
| F. Calibración solo de cargas | `tools/ajuste_cabecera_pf.py`: sin `crear_variacion` ni desactivar ajustes; escribe y mide con el escenario de «Sin proyecto» activo; copia a «Con proyecto» si existe (014:RF-4); no lee la relectura del vínculo ni hace otra comprobación de red; `services.ajuste_plan` separa los alimentadores sin base verificada | RF-13, RF-15, RF-17, RF-19 a RF-21, RF-23 a RF-26 |
| G. La base sin variación | `services.base_del_ajuste`: un alimentador está calibrado si su ajuste aplicado no tiene error, sin pedir variación; la última calibración por alimentador queda en el espacio y viaja en el plan, para el cambio manual de la 014 (RF-10) | RF-22, RF-26 |
| H. Cargas nuevas | `tools/cargas_pf.py`: antes de insertar, `preparar_con` si falta «Con proyecto»; variaciones solo allí, una por carga | RF-28, RF-29 |
| I. Aviso de red cambiada | El aviso `PROJECT_BINDING_NATIVE_MODIFIED` se compara contra la huella tomada al verificar el «Caso base»; una calibración no lo dispara | RF-19, RF-30 |

## Decisiones

- La capacidad esperada sale del DGS del archivo original (`parse_dgs` sobre el fichero
  con el `dgs_sha256` del vínculo). Descartado: añadirla al manifiesto de geografía,
  porque obligaría a reconvertir todo lo ya entregado y el DGS ya la trae.
- Se compara la capacidad del elemento: la potencia del tipo por el número de unidades
  en paralelo. Descartado: comparar el nombre del tipo, porque un tipo renombrado con la
  misma potencia no es un fallo, y un tipo cambiado por el operador es un aviso (RF-11).
- El estado verificado va por alimentador dentro del vínculo. Descartado: un fichero
  aparte, porque el vínculo ya es la evidencia firmada que exige toda acción nativa
  (`native_action_context`).
- La calibración escribe con el escenario de «Sin proyecto» activo y mide así. Descartado:
  medir con el escenario apagado y copiar después (lo de hoy), porque sin variación lo
  escrito con el escenario apagado iría a la red compartida y cambiaría el «Caso base»
  (RF-19).
- El grupo y la tensión de baja se corrigen en el tipo asignado, no se bloquea.
  Descartado: bloquear (usuario, 2026-10-14), porque el archivo original ya dice el valor
  correcto y un flujo no debe pararse por el grupo de una SED. El tipo compartido se copia
  antes de corregirlo, para no cambiar los transformadores que ya estaban bien (RF-36).
- La demanda que dejó la última calibración se guarda en el espacio de la web. Descartado:
  una marca en DIgSILENT, porque escribirla en la carga sería otro dato fuera del
  escenario.
- **Resultado de T1 (2026-10-14, copia de `20261009-215203_IGEA_CA101`, borrada;
  `output/spec015/T1_sonda_escenario.json`):** el escenario de operación guarda `plini`,
  `qlini`, `scale0` y `outserv` de la carga (41,8 kW en el base, 63,7 kW escritos en la
  copia, y el base siguió en 41,8 kW). `i_scale` **no**: escrito en la copia, cambió
  también en el caso original. Sin variación grabando en la copia (`GetRecordingStage`
  vacío). El usuario decide escribir `i_scale` igual (RF-37): el «Caso base» conserva
  su demanda porque en él no se calibra.
- **Depende de T1:** si `i_scale` (fija o escalable) no es dato de operación, escribirlo
  sin variación cambia el «Caso base». En ese caso se para la implementación y se lleva
  la decisión al usuario como cambio de la spec, sin elegir una salida por nuestra cuenta.

## Comprobación contra la constitución

- P2 escala: la verificación recorre cada alimentador una vez (`GetCalcRelevantObjects`
  por clase, como hoy), y las capacidades esperadas se leen del DGS una vez por
  alimentador.
- P9 datos de la distribuidora: las pruebas sintéticas usan DGS y dobles generados; la
  prueba real es en DIgSILENT, sobre el proyecto existente y sin publicar nada.
- P11: las pruebas son la puerta, pero los guiones de DIgSILENT se validan en DIgSILENT
  real (T1 y T12); la suite sintética solo cubre la lógica pura y el doble `fake_pf`.
- P12: la spec está aprobada antes de este plan. Los RF que cambia de la 006, la 011 y la
  014 se anotan en esas specs (T11).
- P13 universal: nada depende de nombres de una empresa; sin manifiesto de geografía no
  se verifica (RF-1), sea cual sea la fuente.

## Estrategia de pruebas

- `tests/test_capacidades.py`: DGS sintéticos con transformadores y líneas con y sin
  tipo, con unidades en paralelo, con la capacidad cambiada, con un transformador de
  380 V leído como 220 V y con otro grupo de conexión (A). En `fake_pf`, la corrección de
  un tipo propio y la de un tipo compartido (B2).
- `tests/test_powerfactory_existing_project_acceptance.py` y el doble `tests/fake_pf.py`:
  proyecto existente con manifiesto; cada comprobación falla por separado; caso
  «Caso base» marcado; variación activa en el base (B).
- `tests/test_powerfactory_binding.py`: estado por alimentador, ajuste bloqueado sin base
  verificada, ninguna promoción tras calibrar (C).
- `tests/test_casos_pf.py`, `tests/test_ajuste_cabecera_guion.py`,
  `tests/test_cargas_pf_guion_007.py`: con `fake_pf`, que el «Caso base» y su escenario
  no cambian al calibrar ni al insertar, que no hay variación en «Sin proyecto» y que
  «Con proyecto» tiene una por carga (E, F, H).
- Las pruebas de la 006, 011 y 014 que esperan la variación `Ajuste_…` se reescriben
  citando el RF de la 015 que las cambia.
- Cada prueba cita su requisito: `"""015:RF-n — …"""`.

## Riesgos

- `i_scale` fuera del escenario (T1): rompería RF-19; se para y se pregunta.
- Proyectos ya calibrados con variaciones `Ajuste_…` (CA101): siguen funcionando, sus
  variaciones no se tocan (014:RF-3) y la verificación las nombra si están activas en el
  «Caso base» (RF-31).
- Los estudios de la 011 y la 012 que activaban «la base calibrada» por sus variaciones:
  se detectaría en las pruebas de `estudios_pf`; con la 015 la base calibrada es el
  escenario de «Sin proyecto».
- `test_inventario.py` exige que toda función de `src/` tenga uso: al quitar
  `promote_project_binding_after_calibration` se quitan también sus pruebas.
