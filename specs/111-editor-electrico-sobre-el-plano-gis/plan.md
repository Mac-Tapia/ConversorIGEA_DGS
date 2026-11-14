# Plan — Spec 111

Lee: `docs/constitution.md`, `specs/111-editor-electrico-sobre-el-plano-gis/spec.md` y sus «Decisiones (2026-11-14)».
Contexto de la auditoría G0, que no se rehace: `D:/csg/G0_PLAN_MAESTRO/B/B_FILAS_BP.md` (BP-10, BP-11),
`A/G0_FRONTEND_AS_IS.md`, `A/G0_UX_RUTAS_Y_WIREFRAMES.md` (W1) y `A/G0_CONTRATOS_API_DATOS.md` §4 (identificadores).
Base leída: `trabajo/plan-maestro-specs@51895566`.

## Contexto técnico

Lo que ya existe y se reutiliza (comprobado en el código):

- **Vértices de la fuente.** `batch.py:172,200` escribe `<alimentador>_geography.json` con
  `geography.write_geography_manifest`; `geography.geography_to_dict` guarda por tramo `from_node`, `to_node` y `path`
  completo en WGS84, y por alimentador `source_crs` y `target_crs`. El DGS lleva el GPS entero (`dgs.py:1277-1299`);
  solo el conector del diagrama se recorta. Es la geometría que pinta el plano (RF-1).
- **Custodia de la fuente.** `web/source_runs.py` (`create_source_run`, `verify_source_files`): `run_id` inmutable y
  SHA-256 de cada fichero. Da la base de la revisión de la red y de la prueba «el hash de los vértices de la fuente
  coincide antes y después».
- **Nombre en DIgSILENT.** `dgs.py:97` `_loc_name` (privado; se usará su nombre público `dgs.nombre_en_pf`, T3) da el `loc_name` de cada barra (`node_id`) y tramo (`section_id`).
  El DGS no lleva el código de origen en otro campo (`chr_name=''`), así que el cruce código ↔ nombre se calcula con
  esa misma función, nunca con una copia.
- **Origen y calidad del dato.** `reconstruction.py` (`ReconstructionDecision`: valor original, valor aplicado,
  `EvidenceLevel`, regla, motivo, confianza), `geography.validate_geography` y `reglas.auditar_completitud` (RF-3).
- **Modelo.** `model.py` (`FeederModel`, `Line`, `SwitchingDevice.on_off`, `CapacitorBank`), construido siempre por
  `reglas.preparar_dataset` y `reglas.aplicar_reglas` (P5). `fases_red.py` da las fases de cada tramo.
- **Motor abierto.** `oraculo.py` (`red_pandapower`, pandapower ya en `requirements.txt`) calcula la misma red que el
  DGS, sin licencia. Hoy solo devuelve agregados (`InformeOraculo`); falta el resultado por elemento.
- **Resultados de DIgSILENT.** `tools/estudios_pf.py:306` `geografia()` guarda por barra `[nombre, lat, lon, u_pu, kv]`
  y por tramo `[nombre, [[lat, lon]…], carga_%, bus1, bus2, tipo, km]`; los lee `web/services.py`
  (`_ultimo_estudio`). `mapa_informe.py` los pinta en PNG con las bandas del perfil.
- **Límites.** `estudios_pf.limites_de_perfil`, `violaciones` y `diferencia` (011:RF-32 a RF-35): el umbral sale del
  perfil de empresa; sin perfil, ±5 % y 100 %, y se dice.
- **Mapa en la web.** `web/mapa_cargas_api.py` + `mapa_cargas.pagina_del_mapa` + `frontend/src/features/powerfactory/
  MapaCargas.tsx`: página Leaflet generada por el servidor, con el Leaflet propio de `recursos/leaflet/`
  (`preview._recurso_leaflet`, huellas en `preview.HUELLAS_LEAFLET`), servida con `preview.politica_pagina_generada()`
  (CSP `sandbox allow-scripts`, sin `connect-src`) en un `iframe sandbox`, y fondos solo con la salida `teselas`
  (`preview.guion_de_fondos`, `salidas_red.salida_permitida`). Es el patrón que se amplía (decisión 4 de G1).
- **Estudio en DIgSILENT sin dejar rastro.** 011:RF-136 en `tools/estudios_pf.py` (variación temporal del conversor con
  su marca, 086:RF-87, borrada al terminar), `pf_estado.py` (foto y restitución, 064), `tools/casos_pf.py` (casos por
  marca), `powerfactory_binding.py` (vínculo proyecto ↔ ejecución de la fuente) y el doble `tests/fake_pf.py`.
- **Cola y API.** `web/jobs.py` (carriles `engine` y `powerfactory`, WebSocket con `since`), módulos de rutas con
  `registrar_rutas_*` montados con dos líneas en `web/app.py` (como `mapa_cargas_api`, `evolucion_fijas_api`),
  contratos en `web/api_contract.py`, `tools/generar_contrato_api.py` y `frontend/src/api/esquema.ts`.

**No se tocan** (son del integrador f9 mientras corrige H1–H14): `web/services.py`, `pide_economia.py`,
`adaptadores/entrada/vnr/**` y `catalog_resolution.py`. **Corrección del implementador (2026-11-14):** el plano NO
importa nombres privados de otro módulo (`services._ultimo_estudio`, `services._guion_pf`). Lo prohíbe
`tests/test_capas.py::test_no_quedan_nombres_privados_entre_modulos`, y es justo el patrón de `mapa_cargas_api.py`
que tiene hoy la rama en rojo (G0, BP-30). Antes de T1 se pide a f9 que exponga en `web/services.py` dos funciones
públicas (`ultimo_estudio`, `guion_pf`), o que las mueva a un módulo de aplicación. Hasta entonces, el plano usa solo
`carpeta_de`, que es pública. El catálogo se lee con `catalog.py`.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Identidad y revisión de la red: cada elemento por su código de la fuente; cruce código ↔ `loc_name` con `dgs.nombre_en_pf` (función pública que añade la T3 en `dgs.py`, igual a `_loc_name` y sin cambiar ningún DGS; ningún módulo importa el nombre privado), con aviso si dos códigos dan el mismo nombre; huella de revisión = SHA-256 del `run_id` y de los `<alimentador>_geography.json` elegidos | nuevo `src/convertersmartgrid/plano_red.py` | RF-2, RF-11 |
| Vista del plano: por alimentador, todos los vértices de su fuente sin simplificar; por elemento, dato original, lo deducido con su regla y motivo (`ReconstructionDecision`) y su estado de calidad (`validate_geography`, `auditar_completitud`); dobles ternas como elementos distintos en el mismo trazo; alimentador sin coordenadas listado y sin pintar | `plano_red.py` | RF-1, RF-2, RF-3 |
| Variación del plano: maniobras, tramos nuevos (vértices tal como se dibujaron, longitud GIS geodésica con `pyproj.Geod` y longitud eléctrica aparte) y equipos insertados; diario de ediciones con versión, deshacer y rehacer hasta confirmar; guardado atómico (`util.write_json_atomic`) en `<espacio>/variaciones_plano/`; la revisión de la red de partida va dentro | nuevo `src/convertersmartgrid/variacion_plano.py` | RF-4, RF-5, RF-9, RF-15 |
| Reglas de la edición, en el servidor: dos tramos solo se unen por un nodo o un equipo comunes, nunca por cruzarse; ajuste de un extremo a un nodo cercano como propuesta con su distancia, aplicada solo al confirmar (radio `editor_ajuste_m` del perfil, en `perfil_esquema.py`; sin perfil, 5 m, y la propuesta lo dice); validación de tensión, fases y conexión de un equipo insertado, con la lista de lo que falta | `variacion_plano.py`; `perfil_esquema.py` (clave nueva) | RF-6, RF-7, RF-8 |
| Resultado por elemento con el motor abierto: función pública nueva `oraculo.resultados_por_elemento(model)` (tensión por barra, corriente y carga por tramo y estado de cada equipo, con los códigos de la fuente); la variación se aplica a una copia derivada del `FeederModel` (`dataclasses.replace`), nunca al dataset ni a la geografía | `oraculo.py` (función nueva); nuevo `src/convertersmartgrid/resultados_plano.py` | RF-10, RF-11, RF-17, RF-18 |
| Capas de resultados: magnitud, unidad, banda, umbral del perfil (`estudios_pf.limites_de_perfil`), caso, revisión y motor; un incumplimiento lleva texto, icono, valor y umbral además del color; los resultados de DIgSILENT de 4.2 se traducen por el cruce de identidad; nada se pinta si el caso no convergió o si la revisión no coincide, y se dice por qué con los mensajes del motor | `resultados_plano.py` | RF-10, RF-11, RF-13, RF-18 |
| Comparación de dos casos por elemento (valor A, valor B, diferencia y banda), con aviso si los motores son distintos | `resultados_plano.py` | RF-12, RF-19 |
| Guion de DIgSILENT: aplica la variación en una variación temporal del conversor con su marca dentro de una copia del caso elegido (y en una copia del escenario de operación si lo tiene activo), corre `ComLdf`, lee con `tools/estudios_pf.geografia`, borra lo temporal y compara la foto de `pf_estado` | nuevo `tools/variacion_plano_pf.py` | RF-4, RF-10, RF-17 |
| Elección del motor: DIgSILENT si hay licencia (`health.capabilities`) y el proyecto está vinculado a esta ejecución de la fuente (`powerfactory_binding`); si no, el motor abierto. El resultado guarda cuál fue | `resultados_plano.py` | RF-17, RF-18 |
| API: `GET …/plano` (vista), `GET …/plano/pagina` (HTML), `GET/POST/PATCH …/plano/variaciones[/{id}]` con versión (`409` si la versión o la revisión de la red cambiaron), `POST …/deshacer`, `…/rehacer`, `…/confirmar`, `POST …/estudiar` (trabajo en `engine` o en `powerfactory`), `GET …/plano/resultados` y `…/comparar`. Toda regla eléctrica vive aquí, no en el navegador | nuevo `src/convertersmartgrid/web/plano_api.py` (`registrar_rutas_plano`); contratos en `web/api_contract.py`; **cableado mínimo, pactado con el integrador**: dos líneas en `web/app.py`, como `mapa_cargas_api` | RF-4, RF-9, RF-15, RF-17 |
| Página del plano generada por el servidor: Leaflet propio con lienzo (`preferCanvas`), capas por vista (tramos, SED, maniobras, cargas, resultados), nivel de detalle solo gráfico y reversible (`smoothFactor` al alejar; los datos siguen enteros), leyenda, tokens claro/oscuro con `prefers-color-scheme`, sin fondo si la salida de teselas está apagada; mensajes `postMessage` validados con el padre (seleccionar, resaltar, capa, propuesta) | nuevo `src/convertersmartgrid/pagina_plano.py` (reutiliza `preview._recurso_leaflet`, `politica_pagina_generada`, `guion_de_fondos`) | RF-1, RF-2, RF-10, RF-13, RF-14 |
| Pestaña «Plano de la red» en la web: plano en `iframe sandbox`, buscador por código, inspector, ediciones pendientes con deshacer y rehacer, tabla enlazada y virtualizada, capas, caso y comparación; anuncios `aria-live`; todo con teclado (trazar un tramo eligiendo nodo de origen y de destino y pegando los vértices; mover un extremo editando sus coordenadas o eligiendo la propuesta en una lista) | nuevos `frontend/src/api/plano.ts`, `frontend/src/features/plano/{PlanoRed,InspectorElemento,EdicionesPlano,TablaElementos,CapasResultados}.tsx`, `mensajesPlano.ts`, `textosPlano.ts`; `frontend/src/app/App.tsx` (una pestaña más en `TABS`) | RF-2, RF-3, RF-9, RF-13, RF-14, RF-15, RF-16 |
| Arnés e2e en navegador real | nuevos `frontend/playwright.config.ts`, `frontend/e2e/{preparar.mjs,linea_base.spec.ts,medicion_plano.spec.ts,plano.spec.ts}`; devDependencies `@playwright/test` y `@axe-core/playwright` en `frontend/package.json` | RF-1, RF-10, RF-12, RF-13, RF-14, RF-16 |

Cada fichero nuevo entra en `CODIGO_FUENTE.md` con la spec 111 y su subsistema en `docs/architecture/subsistemas.json`
en la misma tarea que lo crea (`tests/test_inventario.py`, spec 009 y 090); el guion responde a `--help` sin DIgSILENT.

## Decisiones

- **Se amplía el Leaflet de `MapaCargas`** (decisión 4 de G1): una página generada por el servidor con el Leaflet propio,
  en un `iframe sandbox`, igual que `mapa_cargas.pagina_del_mapa`. Descartado: el prototipo deck.gl de
  `D:/csg/s35772b80/agente_web/parte2/mapa_proto`, porque añade una dependencia y su licencia (086:RF-21), y sus
  149 ms con 220 alimentadores no se han medido aquí. Solo entra si la medición de T2 con todos los alimentadores de una
  entrega sorteada demuestra que Leaflet con lienzo no cumple el presupuesto; entonces se cambia la página, no la API.
- **El mapa no comparte origen con la web.** Los nombres vienen de la entrega: con `sandbox` sin `allow-same-origin` y
  sin `connect-src`, un nombre con código dentro no alcanza la API. La página y la pestaña hablan por `postMessage`; la
  pestaña acepta solo mensajes de `iframe.contentWindow` con un esquema cerrado (`mensajesPlano.ts`). Descartado:
  importar Leaflet como paquete de npm en la propia pestaña, que pondría los textos de la entrega en el origen con la
  cookie de sesión.
- **Pestaña nueva y no dentro del paso 4.** El plano sirve sin DIgSILENT (H1 y el motor abierto) y `CargasTab.tsx` ya
  tiene 1 516 líneas. La pestaña se añade a `TABS`, junto a «Resultados»; no se quita ni se mueve nada
  (memoria «web, línea base: no eliminar»). Descartado: el banco de trabajo W1 dentro del paso 4, que exigiría un
  proyecto de DIgSILENT para ver el plano. La regla de fronteras (002:RF-18) impide importar `features/plano` desde
  `features/powerfactory`; desde el paso 4 se llega con `?panel=` y el proyecto elegido.
- **El código de la fuente es el identificador.** Plano, tabla, inspector y resultados usan el `section_id`, el
  `node_id` o el código del equipo; el `loc_name` de DIgSILENT se calcula con `dgs.nombre_en_pf` (función pública que añade la T3 en `dgs.py`, igual a `_loc_name` y sin cambiar ningún DGS; ningún módulo importa el nombre privado). Descartado: unir por
  nombre como `mapa_informe.py` (G0 §4), porque un nombre recortado o repetido pinta el resultado en otro tramo; aquí
  una colisión deja ese elemento sin pintar y lo dice.
- **Revisión de la red = huella del `run_id` y de la geografía elegida.** Cada variación y cada resultado la llevan; un
  resultado de otra revisión no se pinta (RF-11) y una edición sobre una revisión cambiada devuelve `409` y se conserva
  marcada, sin estudiarse. Descartado: el `FID` del DGS, que cambia con el orden de escritura (G0 §4).
- **El motor según la licencia** (decisión 4 de G1): DIgSILENT si hay licencia y el proyecto está vinculado a la
  ejecución de la fuente; el motor abierto si no. Siempre se dice cuál (RF-17 a RF-19). Descartado: solo DIgSILENT,
  que deja sin estudio a quien no tiene licencia; y elegirlo en silencio, que mezcla cifras de motores distintos.
- **La variación vive en el espacio y no en DIgSILENT.** En DIgSILENT solo existe mientras dura el estudio, en una
  variación temporal del conversor dentro de una copia del caso, y se borra (011:RF-136, 086:RF-87). Descartado:
  grabarla como variación permanente del proyecto, que es escribir en el proyecto nativo sin carril, copia ni
  confirmación (fuera de alcance).
- **Longitud eléctrica aparte de la GIS.** La GIS se calcula de los vértices (geodésica); la eléctrica la da el operador
  y, mientras no la dé, vale la GIS y el inspector lo dice. Descartado: una sola longitud, que esconde las flechas y
  los recorridos por poste que la GIS no ve.
- **e2e con Playwright como dependencia de desarrollo del frontend**, no del núcleo (P8): no se instala con
  `requirements.txt` ni lo necesita la web para arrancar. Descartado: los recorridos de `D:/csg/AUD_ux/recorrido.cjs`,
  que viven fuera del repositorio y no se repiten en CI.
- **Tablas virtualizadas sin librería**: ventana de filas propia en `TablaElementos.tsx`, como el buscador propio de la
  105. Descartado: `react-window`, una dependencia más para una sola tabla.

## Comprobación contra la constitución

- **P1 Determinismo.** El plano no cambia la conversión: el DGS y `<alimentador>_geography.json` son los mismos antes y
  después de editar y estudiar (prueba de huellas). El resultado del motor abierto, con la misma variación, es igual.
- **P2 Escala.** La vista se arma con un índice por alimentador (los manifiestos de geografía, uno por alimentador) y
  nunca recorre una tabla entera por alimentador. Las pruebas sortean el número de alimentadores; la medición de T2 usa
  una entrega sorteada grande y escribe el número que salió, sin fijarlo.
- **P3 Dos disposiciones.** No se toca el lector; aun así, la vista se prueba con `ExportSpec(layout='completo')` y la
  reducida, porque depende de los vértices que lee.
- **P5 Una sola vía.** El modelo de la variación sale de `reglas.preparar_dataset` y `aplicar_reglas`; el nombre en
  DIgSILENT, de `dgs.nombre_en_pf` (función pública que añade la T3 en `dgs.py`, igual a `_loc_name` y sin cambiar ningún DGS; ningún módulo importa el nombre privado); los límites, de `estudios_pf.limites_de_perfil`. Nada se copia.
- **P6 Atomicidad.** Cada variación y su diario se escriben con `write_json_atomic`; un estudio fallido no deja
  resultado a medias ni variación en DIgSILENT.
- **P7 Nada largo en una petición.** Estudiar es un trabajo (`engine` para el motor abierto, `powerfactory` para
  DIgSILENT), cancelable y con progreso por WebSocket; las ediciones son peticiones cortas.
- **P9 Datos de la distribuidora.** El plano no sale a la red salvo las teselas con su salida encendida; las pruebas
  usan exports sintéticos.
- **P12 La spec manda.** Los RF-17 a RF-19 entran con sus tareas; cada prueba cita `111:RF-n`.
- **P13 Universal.** Ningún código de empresa ni de alimentador en el código ni en las pruebas; el radio de ajuste y los
  umbrales vienen del perfil; las pruebas corren con dos perfiles sintéticos con CRS distintos.

## Estrategia de pruebas

- **Sintéticas sorteadas** (`tests/synthetic_export.py`, `ExportSpec(seed=…)`), con un número de alimentadores sorteado
  y las dos disposiciones, convertidas con dos perfiles sintéticos distintos (P13):
  - `tests/test_plano_red.py`: identidad, revisión, vértices completos, origen y calidad, doble terna, alimentador sin
    coordenadas, colisión de nombres.
  - `tests/test_variacion_plano.py`: maniobra, tramo nuevo, cruces, ajuste propuesto, equipo con lo que le falta,
    deshacer y rehacer, revisión cambiada, la geografía y el DGS intactos.
  - `tests/test_resultados_plano.py`: motor abierto por elemento, no converge, revisión distinta, umbrales del perfil y
    sin perfil, texto e icono junto al color, traducción de resultados de DIgSILENT, comparación y motores distintos.
  - `tests/test_variacion_plano_pf_guion.py`: el guion con `tests/fake_pf.py`: la variación temporal y la copia del
    escenario se borran, el caso del operador queda como estaba (foto de `pf_estado`), el caso base no se escribe.
  - `tests/test_plano_api.py`: rutas, `422` con el motivo, `409` por versión o revisión, trabajos en su carril, CSP de la
    página, las rutas de antes siguen (RF-16) y `tools/generar_contrato_api.py --check` sin deriva.
  - `tests/test_pagina_plano.py`: el HTML lleva el Leaflet propio con su huella, todos los vértices y el esquema de
    mensajes; sin teselas, sin fondo.
- **Frontend sin navegador**: `frontend/test/plano.test.mjs` (protocolo de mensajes, navegación con teclado, textos sin
  RF ni jerga, ninguna constante de umbral en `features/plano/`) con `npm test`; `npm run lint`, `typecheck` y `build`.
- **e2e en navegador real** (`npx playwright test` en `frontend/`), contra la web arrancada con un espacio sintético
  sorteado (`e2e/preparar.mjs` llama a `tests/synthetic_export.py`; la semilla sale en el registro):
  - `linea_base.spec.ts`: todas las pestañas y acciones de hoy siguen ahí (RF-16).
  - `medicion_plano.spec.ts`: tamaño de la página y tiempo hasta el primer dibujo con todos los alimentadores.
  - `plano.spec.ts`: maniobra → flujo con el motor abierto → resultados sobre el plano; comparación de dos casos; los
    dos recorridos solo con teclado; `@axe-core/playwright` sin fallos serios en claro y en oscuro; huellas de los
    vértices iguales antes y después.
- **DIgSILENT real**, solo por la web y sobre una copia de un proyecto de prueba (memorias «probar en DIgSILENT» y «no
  tocar proyectos trabajados»): el recorrido de la maniobra y del tramo nuevo estudiados en DIgSILENT.
- **Accesibilidad y microcopia a mano**, en navegador real: solo teclado, lector de pantalla y contraste en los dos
  modos (memoria «frontend sin exceso de texto»).
- Cada prueba cita su requisito: `"""111:RF-n — …"""`.

## Riesgos

- **Rendimiento con todos los alimentadores.** Si la página pesa demasiado o tarda en dibujar, se detecta en T2 antes de
  construir el editor; la salida es partir la geometría por alimentador visible o pasar a deck.gl solo en la página.
- **Llamadas a `web/services.py`.** Solo a funciones públicas (ver arriba): las dos que hoy son privadas se piden a f9
  como públicas antes de T1. `tests/test_plano_api.py` falla si cambian. El cableado en `web/app.py` se pacta con f9
  antes de integrar.
- **Resultados de DIgSILENT sin código de la fuente.** Si una red unida o reconstruida renombra elementos (puentes
  fundidos, `naming.py`), el cruce por `dgs.nombre_en_pf` deja huecos: esos elementos no se pintan y se cuentan; la prueba de
  colisiones lo vigila.
- **Escenario de operación en DIgSILENT.** Una maniobra se graba en el escenario activo y no en la variación; si la copia
  del escenario no se borra, el caso del operador cambia. Lo detecta la comparación de la foto de `pf_estado` en el
  guion y la prueba con `fake_pf`; la tarea [DIgSILENT] lo confirma en el proyecto. **Regla dura** (memorias del
  usuario: pruebas solo en copias; no tocar proyectos trabajados): toda maniobra o variación se estudia en una copia
  temporal del caso, que se borra siempre, también si el guion revienta. La foto de `pf_estado` de antes y de después del
  caso del operador tiene que ser idéntica; si no, el guion falla y lo informa.
- **Contrato OpenAPI.** Las rutas nuevas cambian la huella de `esquema.ts`; hay que regenerarlo en la misma tarea o
  `tests/test_contrato_api.py` falla.
- **Navegadores de Playwright en CI.** Su descarga es una salida a la red en la instalación de desarrollo, no en el
  producto; si GitHub Actions no la permite, los e2e corren en la puerta local y se dice en la entrega.
