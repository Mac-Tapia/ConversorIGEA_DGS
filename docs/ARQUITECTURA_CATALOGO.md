# Catálogo de la arquitectura

Generado por `tools/generar_arquitectura.py` (spec 090): **no se edita a mano**. Un gancho de git lo regenera en cada
commit y en cada fusión, y `tests/test_arquitectura_generada.py` falla si no está al día. Si hace falta a mano:
`python tools/generar_arquitectura.py --escribir`. Lo que explica el porqué está en [`ARQUITECTURA.md`](ARQUITECTURA.md).

## Cifras

| Parte | Carpeta | Ficheros |
| --- | --- | --- |
| Motor, web, gemelo y asistente | `src/convertersmartgrid/` | 472 |
| Módulo VNR-GIS | `src/convertersmartgrid/adaptadores/entrada/vnr/` | 52 |
| Herramientas y guiones | `tools/` | 133 |
| Interfaz | `frontend/src/` | 122 |
| Pruebas de la interfaz | `frontend/test/` | 66 |
| Pruebas | `tests/` | 689 |
| Pruebas de modelos | `tests_ml/` | 6 |
| Specs | `specs/` | 336 |

`web/services.py` tiene 14930 líneas y 475 funciones, pendiente de partir (002).

### Specs

| Estado | Specs |
| --- | --- |
| cumplida | 96 |
| aprobada | 14 |
| implementada | 1 |
| retirada | 1 |

112 specs con 4122 RF. El detalle, en [`specs/README.md`](../specs/README.md).

### Capas

| Capa | Abrev. | Módulos |
| --- | --- | --- |
| adaptadores | Ada | 197 |
| aplicacion | Apl | 134 |
| dominio | Dom | 73 |
| presentacion | Pre | 51 |
| puertos | Pue | 5 |

460 módulos y 0 excepciones en la deuda de `tools/arquitectura.py`.

### Carriles de trabajos

`engine`, `powerfactory`, `asistente`, `control`, `correo`, `red`.

### Rutas de la API

171 en `web/app.py`, y 13 bajo `/api/vnr` en `adaptadores/entrada/vnr/web/app.py`.

| Familia | Ámbito | Rutas |
| --- | --- | --- |
| `demanda` | espacio | 32 |
| `pf` | espacio | 25 |
| `informes` | espacio | 11 |
| `asistente` | general | 11 |
| `asistente` | espacio | 10 |
| `powerfactory` | espacio | 8 |
| `digital-twin` | espacio | 7 |
| `lote` | espacio | 4 |
| `catalog` | espacio | 3 |
| `inputs` | espacio | 3 |
| `obras` | espacio | 3 |
| `pide` | espacio | 3 |
| `jobs` | general | 3 |
| `powerfactory` | general | 3 |
| `sistema` | general | 3 |
| `(raíz)` | espacio | 2 |
| `agente` | espacio | 2 |
| `convert` | espacio | 2 |
| `feeders` | espacio | 2 |
| `outputs` | espacio | 2 |
| `runs` | espacio | 2 |
| `source-scope` | espacio | 2 |
| `vnr` | espacio | 2 |
| `perfil` | general | 2 |
| `salidas` | general | 2 |
| `workspaces` | general | 2 |
| `cargas` | espacio | 1 |
| `diagnose` | espacio | 1 |
| `estructura` | espacio | 1 |
| `events` | espacio | 1 |
| `files` | espacio | 1 |
| `inputs-auto` | espacio | 1 |
| `load` | espacio | 1 |
| `no-disponibles` | espacio | 1 |
| `options` | espacio | 1 |
| `outputs.zip` | espacio | 1 |
| `reconstruct` | espacio | 1 |
| `restaurar-copia` | espacio | 1 |
| `system` | espacio | 1 |
| `ws` | espacio | 1 |
| `health` | general | 1 |
| `modelos` | general | 1 |
| `pf` | general | 1 |
| `planeamiento` | general | 1 |
| `vnr` | general | 1 |
| `{full_path:path}` | general | 1 |

### Órdenes y módulos instalados

| Orden | Punto de entrada |
| --- | --- |
| `convertersmartgrid` | `convertersmartgrid.presentacion.cli:main` |
| `convertersmartgrid-web` | `convertersmartgrid.presentacion.web.__main__:main` |
| `vnr-etl` | `convertersmartgrid.adaptadores.entrada.vnr.cli:main` |

| Módulo enchufable | Objeto |
| --- | --- |
| `escritor-dgs` | `convertersmartgrid.adaptadores.escritores:MODULO_DGS` |
| `lector-mdb` | `convertersmartgrid.adaptadores.sources.mdb:MODULO` |
| `lector-txt` | `convertersmartgrid.adaptadores.sources.txt:MODULO` |
| `lector-vnr` | `convertersmartgrid.adaptadores.sources.vnr:MODULO` |

## El asistente y su equipo

El intérprete acepta al modelo de órdenes con confianza 0.85, salvo que traiga su umbral calibrado, y a Ollama con 0.6.

### Equipo

| Rol | Ejecuta | Lee el proyecto | Encargo |
| --- | --- | --- | --- |
| `operador` | sí | sí | Confirma cada escritura y es el único que ejecuta. |
| `fuentes` | no | sí | Revisa si cada afirmación de la propuesta está en la evidencia citada, con el mismo valor y del mismo elemento (alimentador, SET, tramo, poste, nodo o equipo): una evidencia de otro elemento no confirma ningún dato de la propuesta. |
| `fisica` | no | sí | Revisa la consistencia física: tensiones, cargas y límites de la propuesta frente a los de la evidencia. |
| `coste` | no | sí | Revisa los costes y cantidades de la propuesta frente a los precios y cantidades de la evidencia: el coste de la propuesta es el total de lo que, según la evidencia, necesita toda la acción. |
| `riesgo` | no | sí | Revisa el riesgo de operación: si, según la evidencia, la propuesta deja cargas sin respaldo o sin servicio, o si la evidencia prohíbe o limita la forma de hacer la acción (procedimiento de seguridad, trabajo en caliente, maniobra no permitida). Cada riesgo que señala la evidencia va en incertidumbres, con el ID y la frase de la evidencia. |
| `cliente_mcp` | no | sí | Un cliente MCP de esta máquina: solo las lecturas del proyecto. |

### Tareas (67)

Carril donde corre si se ejecuta; `opcional?` es un dato que no hace falta dar. Todas están en las dos ediciones (086:RF-15).

| Tarea | Modo | Escribe | Carril | Función | Datos | Qué hace |
| --- | --- | --- | --- | --- | --- | --- |
| `estado` | consulta | no | engine | `feeder_rows` | — | Qué hay cargado en el espacio, sus alimentadores, trabajos y salidas. |
| `proyectos` | consulta | no | engine | `pf_proyectos_guardados` | — | Los proyectos de DIgSILENT que la web ya conoce. |
| `resultados_pide` | consulta | no | engine | `pide_ejecutar` | proyecto? | Las obras, prioridades y formatos del último PIDE de un proyecto. |
| `episodios` | consulta | no | engine | `gemelo_episodios` | proyecto? | Los episodios del gemelo digital por clase y caso. |
| `pregunta` | consulta | no | engine | `asistente_pregunta` | texto | Cómo funciona el conversor, con cita de ficheros, funciones y RF. |
| `clasificar_informe` | consulta | no | engine | `asistente_clasificar` | texto | A qué tipo y subtipo de estudio corresponde un informe o un pedido. |
| `buscar_internet` | consulta | no | engine | `asistente_buscar` | texto | Busca librerías, proyectos o artículos, sin datos de la red (RF-29). |
| `leer_proyectos` | trabajo | no | powerfactory | `pf_projects` | — | Lee de DIgSILENT la lista de proyectos. |
| `evaluar_gemelo` | trabajo | no | engine | `gemelo_evaluar` | — | Cuánto se apartan de DIgSILENT el modelo del gemelo y la física (024:RF-74). |
| `cargar_fuente` | trabajo | sí | engine | `load_dataset` | — | Carga la fuente asignada al espacio. |
| `convertir` | trabajo | sí | engine | `convert` | alimentadores | Convierte alimentadores a DGS, uno por fichero. |
| `unir` | trabajo | sí | engine | `convert_group` | alimentadores | Convierte varios alimentadores en una red unida. |
| `convertir_sistema` | trabajo | sí | engine | `convert_group` | sistema | Convierte un sistema eléctrico a un DGS por sistema. |
| `sistema_completo` | proceso | sí | powerfactory | `sistema_web` | sistema, periodo, ruta? | Sistema eléctrico de punta a punta: convertir, importar y calibrar (022:RF-56). |
| `flujo` | trabajo | sí | powerfactory | `powerfactory_flow` | alimentadores | Flujo de potencia en DIgSILENT de los alimentadores. |
| `verificar_caso_base` | trabajo | sí | powerfactory | `pf_verificar_base` | proyecto, alimentadores? | Verifica el «Caso base» frente al archivo original (spec 015). |
| `cargas_nuevas` | trabajo | sí | powerfactory | `cargas_ejecutar` | proyecto, alimentadores, ruta | Integra las cargas nuevas de un Excel en «Con proyecto» (specs 007 y 014). |
| `obras` | trabajo | sí | powerfactory | `obras_ejecutar` | proyecto, alimentadores | Aplica en DIgSILENT las obras pendientes del espacio (spec 011). |
| `estudios` | trabajo | sí | powerfactory | `estudios_ejecutar` | proyecto, alimentadores, estudio? | Estudios de la red en los casos del proyecto (spec 011). |
| `obras_escalera` | trabajo | sí | powerfactory | `obras_escalera` | proyecto, alimentadores, ruta? | Escalera de obras en «Con proyecto»: bancos, sección y terna hasta dejar la red en norma (025:RF-44). |
| `optimizar_con_proyecto` | trabajo | sí | powerfactory | `con_proyecto_optimizar` | proyecto, alimentadores, ruta?, set? | Optimiza «Con proyecto»: escalera carga a carga y SET nueva para las que no caben (042:RF-13, spec 052). |
| `transferencia` | trabajo | sí | powerfactory | `transferencia_ejecutar` | proyecto, alimentadores | Transferencia de carga entre dos alimentadores (spec 011). |
| `pide` | trabajo | sí | powerfactory | `pide_ejecutar` | proyecto, alimentadores, periodo? | Metodología del PIDE: diagnóstico, obras propias y formatos (024, T13 y T14). |
| `gemelo_aprender` | trabajo | sí | powerfactory | `gemelo_aprender` | proyecto, alimentadores, numero? | Aprendizaje activo del gemelo: escenarios en una copia del proyecto (024, T10). |
| `gemelo_entrenar` | trabajo | sí | engine | `gemelo_entrenar` | — | Reentrena el oráculo PINN del gemelo con lo que hay en el búfer (024, T11). |
| `gemelo_temporal` | trabajo | sí | engine | `gemelo_temporal` | alimentadores? | Gemelo temporal del mes con las curvas de la última máxima (024, T12). |
| `informe_estudio` | trabajo | sí | engine | `informe_estudio` | proyecto, alimentadores, subtipo? | Informe de estudio eléctrico en Word (spec 017). |
| `informe_factibilidad` | trabajo | sí | powerfactory | `informe_factibilidad` | proyecto, alimentadores, sed, subtipo? | Informe de factibilidad de una carga nueva (spec 017). |
| `consultar_datos` | consulta | no | engine | `sed_de_alimentador` | alimentadores?, proyecto?, set?, periodo? | Consulta lo que hay: alimentadores, SED, medidores, clientes fijos, máximas buscadas, años de medición, catálogo, variaciones escaneadas, proyectos y última calibración, con su fuente (070:RF-41). |
| `no_disponible` | consulta | no | engine | `estudios_catalogo` | estudio?, proyecto? | Dice por qué un estudio no está disponible: cortocircuito, protecciones, optimización no lineal y los que el catálogo no ofrece, sin ejecutar nada (070:RF-47). |
| `evaluar_carga_nueva` | etapas | sí | powerfactory | `agente_proyecto` | proyecto, alimentadores, sed, periodo?, ruta? | Evalúa una carga nueva de una vez: diagnóstico, calibración si hace falta, carga, informe y obras solo si hay problemas (070:RF-50). |
| `cancelar_trabajo` | trabajo | sí | engine | `pf_projects` | — | Cancela los trabajos en curso del espacio, nombrándolos antes (070:RF-32). |
| `repetir_trabajo` | trabajo | sí | engine | `asistente_plan_repetido` | — | Repite el último trabajo del espacio que falló, con sus mismos datos (026:RF-43). |
| `convertir_set` | trabajo | sí | engine | `sistema_seleccion` | set | Convierte una SET sola, con sus alimentadores y su barra (022:RF-82). |
| `set_completo` | proceso | sí | powerfactory | `sistema_web` | set, periodo, ruta? | Una SET de punta a punta: convertir, importar y calibrar con su máxima de barra (070:RF-21). |
| `alimentadores_completo` | proceso | sí | powerfactory | `sistema_web` | alimentadores, periodo, ruta? | Uno o varios alimentadores de punta a punta: convertir, importar y calibrar (028:RF-25). |
| `buscar_maxima` | trabajo | no | engine | `demanda_cabecera` | alimentadores?, set?, sistema?, periodo?, alcance? | Busca la máxima según el alcance: alimentadores, SET o sistema (028:RF-27). |
| `cruzar_clientes` | trabajo | no | engine | `demanda_clientes` | alimentadores?, periodo? | Cruza los clientes de la máxima ya buscada: quiénes quedan fijos (035:RF-1). |
| `calibrar` | trabajo | sí | powerfactory | `ajuste_plan` | proyecto | Calibra un proyecto con la última máxima buscada: prepara el plan y lo aplica (spec 006). |
| `simular_calibracion` | trabajo | sí | powerfactory | `ajuste_plan` | proyecto | Simula la calibración de un proyecto con la última máxima, sin aplicarla (spec 006). |
| `recalibrar` | proceso | sí | powerfactory | `sistema_web` | proyecto, periodo, ruta? | Recalibra un proyecto ya importado, sin reconvertir (028:RF-21). |
| `escanear` | trabajo | no | powerfactory | `escanear_alimentadores` | proyecto, alimentadores | Lee del proyecto generadores, bancos y lo cambiado a mano, sin escribir (spec 028). |
| `verificar_convergencia` | trabajo | no | powerfactory | `pf_verificar` | proyecto, alimentadores? | Corre el flujo con lo activo para ver si el proyecto converge, sin grabar (008:RF-18). |
| `carga_nueva_sola` | trabajo | sí | powerfactory | `cargas_plan` | proyecto, alimentadores, sed | Conecta una carga nueva sola, con el formulario de 3.2 (008:RF-24, 070:RF-29). |
| `proyecto_entero` | etapas | sí | powerfactory | `agente_proyecto` | sistema, periodo, ruta? | El proyecto entero de un sistema, etapa por etapa, con la lista de etapas a la vista (027:RF-43). |
| `leer_solicitud` | trabajo | sí | engine | `informe_documentos` | ruta | Lee los PDF del solicitante y propone sus datos, sin rellenar el formulario (017:RF-137). |
| `descargar_resultados` | trabajo | no | engine | `feeder_rows` | alimentadores? | Prepara el ZIP de los resultados y da el enlace para bajarlo (spec 001). |
| `pronostico` | trabajo | sí | engine | `gemelo_temporal` | ruta, alimentadores? | Pronóstico de demanda de cabecera o de clientes fijos, con su competencia de modelos (spec 046). Es un pronóstico, nunca una medición. |
| `enviar_informe` | trabajo | no | engine | `correo_api.registrar_rutas_correo` | ruta? | Prepara el correo de un informe con sus adjuntos y lo deja listo para «Confirmar y enviar»; solo sale con ese clic. |
| `publicar_nube` | trabajo | no | engine | `nube_api.registrar_rutas_nube` | ruta? | Deja listo publicar una salida en Google Drive u OneDrive; se publica con el clic del operador. |
| `compartir_nube` | trabajo | no | engine | `nube_api.registrar_rutas_nube` | — | Deja listo compartir un expediente publicado, solo lectura y con quien diga la orden; se comparte con el clic del operador. |
| `importar_nube` | trabajo | no | engine | `nube_api.registrar_rutas_nube` | — | Abre el selector de Google Drive u OneDrive para traer un fichero a una entrada; entra con lo que el operador elija. |
| `conectar_nube` | trabajo | no | engine | `nube_api.registrar_rutas_nube` | — | Deja listo conectar la cuenta de Google o de Microsoft; la contraseña se escribe en la página del proveedor. |
| `pit_diagnostico` | trabajo | sí | engine | `rutas_pit.crear_router` | ruta | Diagnóstico del PIT de un área de demanda, año por año, con el libro de la red y la proyección que nombre la orden. |
| `pit_expediente` | trabajo | sí | engine | `rutas_pit.crear_router` | ruta | Arma el expediente del PIT de un área para un periodo, con sus formatos, su informe y lo que queda pendiente. |
| `vad_crear_estudio` | trabajo | sí | engine | `vad_api.registrar_rutas_vad` | — | Crea el estudio de costos del VAD de la empresa del perfil para un grupo y un periodo, con el TdR del registro normativo. |
| `vad_empresa_modelo` | trabajo | sí | engine | `vad_api.registrar_rutas_vad` | ruta | Arma la empresa modelo del estudio del VAD, sistema por sistema, con el caso que nombre la orden; deja su manifiesto. |
| `plano_maniobra` | trabajo | sí | engine | `plano_api.registrar_rutas_plano` | alimentadores, proyecto? | Abre o cierra una maniobra de un alimentador en una variación del plano, sin tocar el caso base, y la estudia con DIgSILENT o con el motor abierto. |
| `benchmark_anonimo` | proceso | sí | engine | `benchmark_anonimo` | — | Genera en local el benchmark anonimizado de la fuente TXT cargada; si el estudio no se reproduce o el control encuentra una fuga, no se emite nada. |
| `entrenar_asistente` | proceso | sí | engine | `asistente_entrenar` | — | Reentrena el Transformer de órdenes y, solo si hay informes reales en su prueba, el clasificador de informes; lo que no pase sus puertas deja el modelo en uso (026:RF-20, 067:RF-28). |
| `vnr_estudio` | trabajo | sí | engine | `vnr_api.registrar_rutas_vnr` | — | Estudio VNR de la red del espacio por la Guía 232-2017, con el SICODI de la empresa: el sector típico de la Guía y el del SICODI, su resolución, el año y la moneda (108:RF-20 a RF-25). |
| `clientes_fijos_evolucion` | trabajo | sí | engine | `evolucion_fijas_api.registrar_rutas_evolucion` | alimentadores | Evolución mes a mes de los clientes fijos de los alimentadores que nombre la orden, con los libros de clientes del rango de meses (105:RF-17). |
| `normativa_comprobar` | consulta | no | engine | `normativa_api.registrar_rutas_normativa` | — | Comprueba las fuentes oficiales de la biblioteca normativa: la huella de cada una contra la registrada y su vigencia hoy; solo lee y nada se descarga (107:RF-22). |
| `normativa_agregar` | trabajo | sí | engine | `normativa_api.registrar_rutas_normativa` | ruta | Agrega a la capa del usuario de la biblioteca normativa la norma del fichero .json que nombre la orden (con el esquema de la biblioteca normativa); lo que no valida no entra (107:RF-21). |
| `normativa_regenerar` | trabajo | sí | engine | `normativa_api.registrar_rutas_normativa` | — | Regenera un registro de la biblioteca desde su fuente oficial ya descargada, con su generador (Guía VNR 232, formatos 217, COES o reconsideraciones): comprueba la huella, dice qué reglas entran, salen o cambian y lo escribe en la capa del usuario (107:RF-22). |
| `asignar_entrada` | trabajo | sí | engine | `app.create_app` | ruta | Asigna un fichero de la máquina a una casilla de entrada del espacio (la red, las cargas, los equipos, la base de la red, el estudio, el paquete del VNR-GIS o los alias), como la subida de la web; lo que la casilla no admite no entra y la entrada vigente se queda (026:RF-42). |
| `subir_fuente_empresa` | trabajo | sí | engine | `fuentes_api.registrar_rutas_fuentes` | ruta | Sube un libro de las fuentes de la empresa (demanda, SICODI, perfil, interrupciones, catálogo y los demás de la empresa) a su carpeta y a su año, como la web; queda vigente para todos los módulos (026:RF-42). |

### Etapas del proyecto entero

| Etapa | Tarea | Opcional | Proceso aparte | Condición |
| --- | --- | --- | --- | --- |
| `fuente` | `cargar_fuente` | no | no | — |
| `sistema` | `sistema_completo` | no | sí | — |
| `caso_base` | `verificar_caso_base` | no | no | — |
| `cargas_nuevas` | `cargas_nuevas` | sí | no | — |
| `obras` | `obras` | no | no | — |
| `estudios` | `estudios` | no | no | — |
| `pide` | `pide` | no | no | — |
| `informe` | `informe_estudio` | sí | no | — |

### Etapas de una carga nueva

| Etapa | Tarea | Opcional | Proceso aparte | Condición |
| --- | --- | --- | --- | --- |
| `diagnostico` | `verificar_convergencia` | no | no | — |
| `calibracion` | `recalibrar` | no | sí | sin_calibracion |
| `carga` | `carga_nueva_sola` | no | no | — |
| `evaluacion` | `informe_factibilidad` | no | no | — |
| `obras` | `optimizar_con_proyecto` | no | no | si_no_factible |
| `informe` | `informe_factibilidad` | no | no | si_hubo_obras |

### Familias de modelos

Orden de entrenamiento: `transformer`, `clasificador`, `gru`, `pinn`, `evolutivos`, `embeddings`, `qlora`.

Con puntero en uso gobernado por `asistente/modelos_en_uso.py`: `clasificador` (informes), `transformer` (ordenes).
Qué modelo está en uso vive en `output/`, fuera de git: ver [`ARQUITECTURA.md`](ARQUITECTURA.md#modelos-024-026-043-045-046-060-069-075-079-085).

## Ficheros

Papel, specs y capa salen de `CODIGO_FUENTE.md` y `pyproject.toml`. El subsistema, de `docs/architecture/subsistemas.json`.
Las pruebas no se listan: cada una cita los `NNN:RF-n` que cubre.

### Motor: transversales

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Dom | 034, 106 | Paquete del motor y su versión. |
| `dominio/util.py` | Dom | 001, 086, 107, 108 | SHA-256, JSON atómico y duradero, con copia anterior, y números, entre ellos el FRC (`frc`), la única fórmula del factor de recuperación del capital… |
| `dominio/runtime_paths.py` | Dom | 065, 086 | Raíces externas, identidad estable de la instalación, staging por volumen o junto al destino, custodia y reconciliación de temporales. |
| `dominio/naming.py` | Dom | 034, 011 | Nombres y selectores de alimentador. |
| `dominio/perfil_empresa.py` | Dom | 002, 020, 021, 025 | Perfil de empresa: CRS de origen, patrón de las SED de medición, escala del diagrama y forma de los alimentadores, fuera del código. |
| `adaptadores/perfil_esquema.py` | Ada | 086 | Valida un perfil contra su esquema: valores imposibles, claves desconocidas y lo que falta con la función que afecta. |
| `dominio/edicion.py` | Dom | 086 | Qué edición corre (el programa instalado siempre es de producto) y las funciones en beta, activas y desactivables por el operador. |
| `dominio/salidas_red.py` | Dom | 086 | Lista de cada salida a la red con su interruptor: encendidas en desarrollo, apagadas en la edición de producto. |
| `dominio/sesion_web.py` | Dom | 086 | Token de la sesión de la web: el lanzador lo crea en un fichero solo del usuario y los clientes locales lo leen. |
| `dominio/traza.py` | Dom | 086, 127 | Referencia de soporte de cada petición (`X-CSG-Traza`), que el trabajo hereda, el motor recibe en `CSG_TRAZA` y el informe lleva en sus metadatos. |
| `adaptadores/registro_rotativo.py` | Ada | 086 | Registro del programa en ficheros rotativos, fuera de la carpeta del programa. |
| `presentacion/cli.py` | Pre | 001, 022 | Orden `convertersmartgrid`: `list`, `convert` y `web`.; `--por-sistema [ZONAL]` y `--estructura`, aparte de `--unir` |
| `dominio/privacidad.py` | Dom | 112, 086 | Patrones que tapan rutas, correos, IP, códigos y nombres, y los términos del perfil de una empresa (un perfil ilegible es un error, nunca «ningún… |
| `dominio/compat_pf.py` | Dom | 103 | Equivalentes de `itertools.pairwise` y `zip(..., strict=True)` para lo que cargan los guiones de DIgSILENT con el Python 3.9 de PowerFactory 2021. |
| `adaptadores/__init__.py` | Ada | 002 | Adaptadores de fuentes y servicios externos. |
| `adaptadores/entrada/__init__.py` | Ada | 002 | Adaptadores de entrada. |
| `adaptadores/fuentes_estables.py` | Ada | 034, 065 | Descriptor readonly identificado y protegido contra escritura/reemplazo durante el lector. |
| `dominio/__init__.py` | Dom | 002 | Paquete real de valores y reglas puras, sin lectores ni E/S. |
| `dominio/numeros_medidos.py` | Dom | 002, 004 | Un único cuerpo de normalización de códigos y números finitos de medición. |
| `presentacion/__init__.py` | Pre | 002 | Paquete de la capa presentacion. |

### Motor: entrada de datos

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `adaptadores/sources/__init__.py` | Ada | 001 | Registro de adaptadores, común a la web y al CLI. |
| `puertos/sources/base.py` | Pue | 001 | Contrato de los lectores de las tres procedencias. |
| `adaptadores/sources/txt.py` | Ada | 001 | Adaptador de los tres TXT. |
| `adaptadores/sources/mdb.py` | Ada | 001 | Adaptador de base Access. |
| `adaptadores/sources/vnr.py` | Ada | 001, 053 | Adaptador de un paquete VNR-GIS. |
| `dominio/sources/snapshot.py` | Dom | 001 | Qué ficheros forman una lectura y su huella. |
| `dominio/source_contract.py` | Dom | 001, 004, 006 | Contrato canónico y evidencia de auditoría compartidos por TXT, MDB y VNR-GIS. |
| `adaptadores/dataset.py` | Ada | 034 | Lector de los TXT (RED, CARGA, BD_Equipo), en las dos disposiciones. |
| `dominio/dataset.py` | Dom | 002 | La estructura del dataset común de CYMDIST (campos, índices por alimentador, tablas de tipos de línea) sin su lector. |
| `adaptadores/access.py` | Ada | 034, 001 | Lector de la base Access de CYMDIST (`.mdb`), la segunda vía de entrada. |
| `adaptadores/identify.py` | Ada | 034, 059 | Reconoce cada TXT por su contenido, no por su nombre, y a qué fuente (TXT, Access o VNR-GIS) pertenece un fichero. |
| `adaptadores/study.py` | Ada | 034 | Estudio de CYMDIST (`.zxst`/`.xst`), entrada opcional que filtra la selección. |
| `aplicacion/inventory.py` | Apl | 034 | Inventario detallado de un dataset cargado. |
| `adaptadores/feeder_metadata.py` | Ada | 034, 022 | Procedencia por alimentador de los objetos de una red conjunta.; la red externa de una barra de SET, una vez con sus alimentadores |
| `dominio/cargas_plantilla.py` | Dom | 004, 002 | Lectura y validación de las filas de los libros de cargas por SED (columnas, potencia y FP), sin E/S: pasó entera de `loads.py` (002 T7, a), y la usa… |
| `dominio/sources/__init__.py` | Dom | 002 | Paquete de `sources` en la capa dominio. |
| `puertos/sources/__init__.py` | Pue | 002 | Paquete de `sources` en la capa puertos. |

### Motor: reconstrucción y catálogo

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `dominio/reconstruction.py` | Dom | 001 | Contrato de la reconstrucción auditable del dataset. |
| `aplicacion/reconstruction_pipeline.py` | Apl | 001 | Reconstrucción de una selección de alimentadores, sin estado de la web. |
| `dominio/reconstruction_topology.py` | Dom | 001 | Reconstrucción determinista de la topología. |
| `aplicacion/catalog.py` | Apl | 034, 053 | Catálogo de parámetros eléctricos: tabla de entrada y auditoría del modelo. |
| `dominio/catalog_data.py` | Dom | 034 | Datos de fabricante y de norma para los parámetros eléctricos. |
| `aplicacion/catalog_merge.py` | Apl | 034, 001 | Completa el catálogo de equipos cuando el export llega incompleto. |
| `dominio/catalog_resolution.py` | Dom | 001 | Resolución de equipos por evidencia, sin renombrar los códigos de origen. |
| `dominio/coordenadas.py` | Dom | 034 | Completa las coordenadas que faltan con el grafo de la red. |

### Motor: modelo y reglas

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `dominio/model.py` | Dom | 034 | Modelo eléctrico de un alimentador. |
| `aplicacion/reglas.py` | Apl | 034, 002, 021, 022, 032, 057 | Reglas que se aplican a todo alimentador, venga de TXT o de base. |
| `dominio/puentes.py` | Dom | 034, 021 | Funde los tramos puente de CYMDIST en vez de modelarlos como líneas. |
| `dominio/trafomix.py` | Dom | 034, 002, 021 | Equipos de medición en MT que la base registra como SED, con el patrón del perfil de empresa. |
| `dominio/sed_potencia.py` | Dom | 034, 057 | Lleva al tamaño normalizado las SED cuya carga supera su transformador. |
| `dominio/fases_red.py` | Dom | 054 | Qué fases le llegan a cada tramo y SED desde la cabecera. |
| `dominio/comprobacion_fases.py` | Dom | 081 | Contrato de fases de toda la clase de fallos: ningún elemento con más fases que su barra ni con fases que no le llegan, en cualquier fuente. |
| `adaptadores/geography.py` | Ada | 034, 001 | Del CRS de origen a WGS84. |
| `adaptadores/capacidades.py` | Ada | 015 | Capacidades, grupo de conexión y tensión de baja de transformadores y líneas del DGS original, y su comparación con lo leído en DIgSILENT. |

### Motor: conversión, red unida y oráculo

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/batch.py` | Apl | 034, 001, 022, 065 | Conversión de uno, varios o todos los alimentadores, en serie o en paralelo.; la red unida por zonal y SET con su informe, aperturas y oráculo |
| `aplicacion/combine.py` | Apl | 034, 022 | Une todos los alimentadores en una sola red. |
| `aplicacion/enlaces.py` | Apl | 022 | Puntos de enlace de la red unida con sus SET y caminos cerrados (entre SET, entre alimentadores, anillos): abre la maniobra más lejana de su fuente… |
| `dominio/estructura.py` | Dom | 022, 055 | La estructura de la empresa: zonales, SET (con sus siglas) y alimentadores con su sistema eléctrico, sector típico y norma. |
| `adaptadores/oraculo.py` | Ada | 034, 022, 057, 082, 111 | Flujo independiente con pandapower antes de escribir el DGS. |
| `dominio/resolver_convergencia.py` | Dom | 081 | Si el «Caso base» no converge: su causa, corregir lo reconstruible, volver a medir, y decir lo que queda con su elemento y qué hacer. |
| `aplicacion/preflight_contract.py` | Apl | 065 | Contrato JSON del modelo efectivo, fijado al DGS antes de su importación. |
| `dominio/comprobacion_flujo.py` | Dom | 081 | Lo que un flujo o una calibración dijeron frente a lo que pasó: barras de baja a 0 p.u., cargas que no consumen, estado verdadero del trabajo y… |

### Motor: salida y módulos enchufables

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `adaptadores/schema.py` | Ada | 034, 054 | Perfiles de esquema DGS versionados. |
| `schemas/pf21_dgs_1_8_4.json` | — | 034 | Perfil DGS genérico de PowerFactory. |
| `schemas/perfil_empresa_v1.schema.json` | — | 086 | Esquema del perfil de empresa: cada clave con su tipo, la función que afecta, qué se hace sin ella y si es de la empresa o de una norma. |
| `schemas/protecciones_v1.schema.json` | — | 049 | Contrato del dispositivo de protección (campos obligatorios, clases con su clase de PowerFactory, unidades admitidas y campos que pide cada unidad o… |
| `schemas/asistente_orden_v1.schema.json` | — | 047 | Contrato base de salida estructurada para el intérprete local. |
| `schemas/revision_propuesta_v1.schema.json` | — | 047 | Contrato del dictamen de un rol: lo que se pide a Ollama y lo que se valida. |
| `schemas/digital_twin_episode_v1.schema.json` | — | 024 | Esquema JSON publicado del episodio del gemelo digital, igual al contrato de `digital_twin/episode.py`. |
| `schemas/digital_twin_episode_v2.schema.json` | — | 045 | Esquema JSON del episodio v2: cuatro casos y contexto físico con su identidad nativa y sus huellas. |
| `adaptadores/dgs.py` | Ada | 034, 010, 011, 128, 021, 022, 054 | Escritor DGS: tablas, FID, cubículos, maniobras, capa gráfica y trazado GPS de las líneas. |
| `adaptadores/validate.py` | Ada | 034, 010, 021, 022, 054 | Validación del DGS escrito, con el trazado GPS de cada línea.; reconoce la red por zonal y SET |
| `adaptadores/export_tables.py` | Ada | 034 | DGS a Excel multihoja o TSV. |
| `adaptadores/preview.py` | Ada | 034, 086 | Vista previa georreferenciada del modelo, con Leaflet propio dentro del fichero y su política de contenido. |
| `recursos/NOTAS_VERSION.md` | — | 086 | Notas de la versión que muestra la pantalla «Acerca de». |
| `recursos/estado_specs.json` | — | 100 | El estado de cada spec y la huella del `specs/README.md` del que sale, para la matriz estudio × motor del programa instalado, que no lleva `specs/`. |
| `recursos/leaflet/leaflet.js` | — | 086 | Leaflet, copia exacta con huella comprobada. |
| `recursos/leaflet/leaflet.css` | — | 086 | Estilos de Leaflet, copia exacta con huella comprobada. |
| `recursos/leaflet/LICENSE` | — | 086 | Licencia de la copia de Leaflet que sirve la propia web, sin salir a internet. |
| `aplicacion/registro_modulos.py` | Apl | 002 | Descubre, filtra y carga los módulos. |
| `adaptadores/escritores.py` | Ada | 002 | El escritor DGS como módulo y la entrega del modelo auditado a un escritor. |

### Motor: enlace con DIgSILENT

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `adaptadores/pf_arnes.py` | Ada | 019, 064, 091 | Arnés de DIgSILENT: turno del motor de la máquina, conexión común con reintento, caso restituido y proceso que se queda abierto. |
| `adaptadores/pf_estado.py` | Ada | 064 | Foto del estado de DIgSILENT antes de una orden del servidor (caso, hora, escenario, variaciones) y su restitución si la orden falla. |
| `adaptadores/powerfactory_env.py` | Ada | 034 | Dónde está la API de PowerFactory y qué intérprete la carga. |
| `adaptadores/powerfactory_metadata.py` | Ada | 034, 078 | Procedencia del conversor en los objetos de PowerFactory, y la lectura única del flujo y su clasificación. |
| `adaptadores/powerfactory_binding.py` | Ada | 004, 006, 011, 015, 078 | Vínculo auditable entre ejecución fuente, DGS, inventario releído y proyecto nativo aceptado, con el estado del «Caso base» de cada alimentador. |
| `dominio/native_action.py` | Dom | 004, 006, 011 | Contexto firmado fuente–proyecto–alimentadores y vocabulario común de resultados para toda acción nativa. |
| `adaptadores/carpeta_pf.py` | Ada | 005, 011 | Carpeta de DIgSILENT donde quedan los proyectos importados. |
| `aplicacion/studies.py` | Apl | 034, 012, 056 | Qué estudios de PowerFactory se pueden correr y qué dato falta para cada uno. |
| `dominio/estadistica_ordenes.py` | Dom | 081 | Estadística de las órdenes de DIgSILENT: registro por orden, descriptiva con IC 95 %, contraste de versiones (Mann-Whitney, Fisher) y fallos que se… |

### Motor: demanda y calibración

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/demanda_medida.py` | Apl | 004, 013, 021, 022, 025, 038, 039, 060, 088, 089, 091 | Máxima de cabecera por medidor y clientes importantes con su SED. |
| `aplicacion/libros_por_anio.py` | Apl | 025 | Libros de demanda por año de medición: árbol de libros con su año (carpeta de cuatro cifras a cualquier altura) y su ruta relativa, años disponibles… |
| `aplicacion/libros_nuevos.py` | Apl | 104 | Foto de una fuente de demanda y sus cambios, verificación de un libro de clientes (mes, registros frente a días × 96, nuevos, sin suministro, en… |
| `aplicacion/cabecera_ancha.py` | Apl | 051 | Medición de cabecera entregada a lo ancho (una columna por alimentador, fecha y hora en dos columnas, hojas de activa y reactiva) y tablas de máximas… |
| `adaptadores/loads.py` | Ada | 004, 002 | Reexportación temporal (hasta la T9 de la 002) de `dominio/cargas_plantilla.py`, donde pasó entero el lector de libros de cargas por SED. |
| `aplicacion/cargas_pf.py` | Apl | 004, 007, 008, 016, 030, 093, 099 | Lectura de los libros de demandas y cargas nuevas, y plan para DIgSILENT. |
| `dominio/ajuste_cabecera.py` | Dom | 006, 021, 035, 041, 095 | Reparto y cuadre de las demandas a la máxima de cabecera, sin DIgSILENT. |
| `adaptadores/oraculo_calibracion.py` | Ada | 083 | El oráculo antes de calibrar: los factores de arranque, sin gastar flujos de DIgSILENT. |
| `aplicacion/crecimiento.py` | Apl | 029 | Tasa anual de crecimiento de la demanda de cada alimentador desde la medición de cabecera: máximas de los meses comunes del primer y el último año,… |
| `aplicacion/valle.py` | Apl | 073 | El valle de un alcance desde la medición: limpieza de lo dudoso con su motivo, energía de sus medidores, inicio y duración por búsqueda exacta, por… |
| `aplicacion/escaneo.py` | Apl | 028 | Reglas del escaneo de un alimentador antes de recalibrar: de quién es cada generador, banco y variación por los prefijos del conversor, resumen y… |
| `dominio/transferencia_operador.py` | Dom | 098 | Transferencias de carga del operador: qué SED están transferidas, qué zona forman, qué abrir y qué cerrar para calibrar con la red de la fuente, y lo… |
| `aplicacion/trafos_sed.py` | Apl | 020 | Transformador nuevo para una SED fija sobrecargada: la menor potencia de la tabla de fichas del perfil (por tensión primaria) con la máxima en el… |
| `dominio/economia.py` | Dom | 004 | Datos de la evaluación técnico-económica (`ComTececo`). |
| `adaptadores/evolucion_clientes.py` | Ada | 105 | Evolución de los clientes fijos de uno o varios alimentadores con los lectores del pronóstico: conciliación de fuentes, indicadores, mes copiado,… |
| `dominio/meses_copiados.py` | Dom | 105 | Mes de cada registro de 15 minutos y detección del libro mensual que repite el mes anterior, día a día, por mayoría de las series. |
| `dominio/evolucion_mensual.py` | Dom | 105 | Indicadores mensuales de una serie (máximas con su instante, medias, energías, FP, factor de carga, registros) y su crecimiento, variación, tendencia… |
| `dominio/conciliacion_clientes.py` | Dom | 105 | Veredicto de cada cliente frente a sus fuentes, cadenas de renumeración, renumeraciones posibles por CL o SED y fijos por encima de la cabecera. |
| `aplicacion/__init__.py` | Apl | 002 | Paquete de la capa aplicacion. |

### Motor: obras y optimización

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/obras_pf.py` | Apl | 011, 016, 042, 048, 098 | Obras de mejora sin DIgSILENT: modelo y validación de cada obra (lo de «Sin proyecto» pasa a «Con proyecto». |
| `dominio/troncal.py` | Dom | 016 | Troncal de las obras sin DIgSILENT: camino continuo más largo desde la cabecera sobre el árbol de caminos más cortos en metros (anillos cerrados… |
| `aplicacion/escalera_optima.py` | Apl | 025, 073, 098 | Escalera optimizada de obras: variantes en el orden bancos, regulador, terna y sección con sus combinaciones, criterio de «no empeorar» por sorteo,… |
| `adaptadores/optimizacion_oraculo.py` | Ada | 052, 073, 098 | «Con proyecto» optimizado con el flujo del gemelo: obras sobre el grafo, búsqueda bayesiana (Optuna), frente de Pareto (NSGA-II), sorteos de Markov y… |
| `aplicacion/perfil_tension.py` | Apl | 094 | Perfil de tensión de un alimentador (tensión de cada barra de media frente a su distancia eléctrica) y bancos ubicados según el perfil hasta la… |
| `aplicacion/catalogo_reguladores.py` | Apl | 025 | Reguladores de tensión de catálogo (Eaton VR-32, 50 Hz): unidad por tensión del sistema y por corriente, y los datos de su `TypVoltreg`. |
| `aplicacion/instalacion_ternas.py` | Apl | 084 | Dos o más ternas subterráneas: una por ducto, triangular o rectangular, y la capacidad del fabricante para esa configuración, de la tabla del perfil. |
| `aplicacion/set_nueva.py` | Apl | 042 | SET nueva para las cargas que la red existente no atiende: potencia de diseño a la vida útil con la tasa de la 029 y el factor de seguridad, módulo… |
| `aplicacion/sitio_set.py` | Apl | 084 | Sitio de una SET nueva: distancia al trazado de los alimentadores y a las calles de un fichero local, punto apartado y «sin verificar en plano» si… |
| `aplicacion/vias.py` | Apl | 016 | Trazado de una línea nueva por la vía pública con un enrutador OSRM (OpenStreetMap): ruta con sus curvas, largo con los accesos, metros fuera de vía… |
| `adaptadores/madrl_obras.py` | Ada | 074 | Entorno multiagente de obras, sus controles, su fidelidad contra DIgSILENT y la puerta del aprendizaje. |
| `adaptadores/madrl_politica.py` | Ada | 074 | Política GATv2 compartida entre agentes, con crítico central y PPO, del piloto MADRL. |
| `adaptadores/madrl_puerta.py` | Ada | 074 | Puerta del aprendizaje en alimentadores no vistos: separación sellada con huella, decisión «pasa» o «archivar» y la orden de confirmación en un… |
| `dominio/medicion_obras.py` | Dom | 087 | Cuánto mejora una versión: fila por corrida de «Con proyecto» con tiempo, recursos, obras y normas, y comparación de dos métodos o versiones. |
| `dominio/modelo_obras.py` | Dom | 087 | Clasificador de árboles que decide en qué tanda se mide cada variante, con su puerta de validación por sistema. |
| `aplicacion/obras_integrales.py` | Apl | 087, 098 | Después de la escalera: transferencia y traslado a un vecino con margen (enlace y migración), solo desde barras con maniobra, y el área del… |
| `dominio/seleccion_bayesiana.py` | Dom | 087 | Cuándo dejar de sortear una variante: posterior Beta de que cumpla, y la certeza con que se dice. |

### Motor: estudios

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/estudios_pf.py` | Apl | 011, 012, 049 | Estudios sobre los casos «Sin proyecto» y «Con proyecto», sin DIgSILENT: qué estudios se ofrecen (los de la 012 según el libro de la empresa y la… |
| `dominio/matriz_estudios.py` | Dom | 100 | Matriz estudio × motor (DIgSILENT, motores abiertos, oráculo PINN y cálculo del conversor): por estudio de la web, la evidencia de cada celda (las… |
| `aplicacion/estudios_red_pf.py` | Apl | 012 | Resultados de confiabilidad y capacidad sin DIgSILENT: índices por alimentador y su comprobación por cargas, ENS total y diferencias, aportes, mejora… |
| `aplicacion/datos_empresa.py` | Apl | 012, 049 | Libro de la empresa de la confiabilidad, la capacidad y las protecciones: hojas, columnas y unidades validadas con hoja, fila y columna. |
| `adaptadores/entradas_estudios.py` | Ada | 012 | Entradas que faltan a los estudios cargadas por el operador: texto de TXT, PDF o imagen (OCR), tablas con cualquier separador, columnas por su… |
| `aplicacion/historico_interrupciones.py` | Apl | 012 | El libro de la empresa como histórico de interrupciones: columnas reconocidas por contenido y sinónimos, filtros de programadas, media tensión y… |
| `aplicacion/protecciones.py` | Apl | 049 | Estudio de protecciones sin DIgSILENT: contrato de cada ajuste (modelo, unidades, TC/TT, poder de corte y procedencia), fila DEFAULT de la fuente que… |
| `aplicacion/transferencia_pf.py` | Apl | 011, 110, 117, 121, 123, 125, 129 | Transferencia de carga sin DIgSILENT: pasos del camino y carga transferida, viabilidad y elemento que limita, máximo por seccionador y por nodo,… |
| `adaptadores/plano_red.py` | Ada | 111 | El plano de la red: cada elemento por su código de la fuente y su nombre en DIgSILENT (con aviso de colisiones), la revisión de la red y la vista con… |
| `dominio/disposicion_unifilar.py` | Dom | 111, 107 | La disposición de un unifilar por anchura desde la fuente (nivel y orden de cada barra), una sola regla para el unifilar del PIT y el del plano. |
| `adaptadores/pagina_plano.py` | Ada | 111 | La página del plano generada por el servidor: Leaflet propio con lienzo, capas por vista, nivel de detalle solo gráfico y reversible, leyenda con… |
| `aplicacion/variacion_plano.py` | Apl | 111 | La variación del plano en el espacio, nunca en el caso base: maniobras, tramos nuevos con su longitud GIS y eléctrica, reglas de la edición, equipos… |
| `adaptadores/resultados_plano.py` | Ada | 111 | Los resultados sobre el plano: elección del motor (DIgSILENT o el abierto), la variación aplicada a una copia del modelo y estudiada por elemento,… |

### Motor: informes

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `adaptadores/informes.py` | Ada | 017, 107, 108, 115, 121, 122, 128, 129, 132, 134 | Informes de estudio eléctrico y de factibilidad sin DIgSILENT: qué toman del perfil de empresa (modelos, banda y umbral, bandas de coloreado,… |
| `adaptadores/informe_docx.py` | Ada | 017, 106, 113, 114, 118, 120, 122, 128, 132, 135 | Escribe en Word los informes de estudio eléctrico y de factibilidad como esquemas generales sobre el modelo de la empresa: de él solo la forma… |
| `adaptadores/libro_informe.py` | Ada | 066 | El libro Excel de cada informe, relleno desde el modelo de la empresa con el plano de su perfil |
| `adaptadores/libros_informe.py` | Ada | 017 | Libro de pérdidas de la empresa (sistema eléctrico, % reconocidos en potencia y energía, precio de compra), buscado por los nombres de hojas y… |
| `adaptadores/mapa_informe.py` | Ada | 017, 116, 133 | Imágenes del informe de estudio (ubicación, tensión, cargabilidad y detalle de las obras) con el GPS y los resultados del flujo de DIgSILENT. |
| `adaptadores/mapa_cargas.py` | Ada | 017, 109, 111, 112, 124 | El mapa de las cargas nuevas (punto, nodo de conexión, enlace y red del alimentador), sus diferencias con lo leído en DIgSILENT, el punto de diseño… |
| `adaptadores/documentos_solicitud.py` | Ada | 017, 136, 141 | PDF del solicitante (carta, oficio, ficha del punto de diseño): capa de texto por página y, en las escaneadas, OCR con Tesseract y la imagen… |
| `adaptadores/archivo_informes.py` | Ada | 105 | Carpeta de archivo de la máquina (`config/archivo.json`) y `archivar(fichero, tipo, ambito, periodo)`: copia por temporal con reintentos, sin borrar… |
| `puertos/correo/__init__.py` | Pue | 110 | Contratos del envío: `ResultadoEnvio`, `ProveedorCorreo` y, hasta que la 109 publique los suyos, `FuenteDeCredenciales` y `Compartidor`. |
| `adaptadores/correo/borrador.py` | Ada | 110 | Borrador del correo (cuenta, para, cc, cco, asunto, cuerpo, adjuntos o enlace) y su firma SHA-256, que vuelve a leer los adjuntos del disco al… |
| `adaptadores/correo/envios.py` | Ada | 110 | Diario durable de los envíos de un espacio (`<espacio>/envios/<clave>.json`): reserva exclusiva de la clave antes de llamar al proveedor (también la… |
| `adaptadores/correo/mensaje.py` | Ada | 110 | El mensaje MIME del envío (`email.message`), con el `Message-ID` de la clave y los adjuntos releídos y comparados con su huella. |
| `adaptadores/correo/proveedores.py` | Ada | 110 | `EnvioGmail` (`gmail.send`) y `EnvioOutlook` (`Mail.Send`) con `requests`, sin redirecciones ni proxy del entorno, con plazo, salida declarada,… |
| `adaptadores/correo/de_la_109.py` | Ada | 110 | La 110 sobre las cuentas de la 109: `CredencialesDeLa109` da el token de `Cuentas.acceso` de la cuenta conectada en el espacio (solo con el permiso… |
| `adaptadores/correo/__init__.py` | Ada | 002 | Paquete de `correo` en la capa adaptadores. |

### Motor: PIDE y planeamiento

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/pide.py` | Apl | 024, 072 | Metodología del PIDE (RM 428-2017-MEM/DM): proyección y densidad de carga por cuadrículas de la Tabla N.º 2, diagnóstico con su causa (caída, FP,… |
| `aplicacion/pide_economia.py` | Apl | 024, 073, 072 | Evaluación económica y priorización del PIDE: libro CAPEX por nombres del perfil (sin datos personales), anualidad, costo anual, VAN y TIR del art. |
| `adaptadores/pide_dataset.py` | Ada | 024 | Corpus PIDE universal desde un expediente de la empresa en solo lectura: custodia, calidad y fragmentos de texto. |
| `dominio/estudio_planeamiento.py` | Dom | 072 | Estudio de planeamiento: del año de presentación, cada 4 años, salen el año 00 y los años de largo plazo y del PIDE. |
| `aplicacion/proyeccion_mercado.py` | Apl | 072 | Proyección anual por sistema desde el Formato 01: métodos comparados contra lo ocurrido, sin mirar el futuro. |
| `adaptadores/proyeccion_anual.py` | Ada | 031 | Proyección de todos los años del PIDE: competición por clase y magnitud con la regla declarada antes de medir, Formato 01 desde la cabecera con sus… |
| `aplicacion/costos_fuentes.py` | Apl | 072 | Costos oficiales: contrato de fuente, lectores del SICODI público y de los módulos estándar de transmisión, cruce por código, tensión, estructura y… |
| `aplicacion/metrados.py` | Apl | 072 | Metrados por código desde el modelo de la red, y su valoración con costos oficiales. |
| `aplicacion/formatos_pide.py` | Apl | 072 | Los formatos 01 a 15 de un estudio con cada hueco nombrado y su motivo. |
| `adaptadores/informes_planeamiento.py` | Ada | 072 | Los entregables de un estudio, un Word ligero por módulo, desde un mismo cálculo. |
| `adaptadores/aceptacion_publicada.py` | Ada | 072 | Aceptación del PIDE y del largo plazo con lo publicado y custodiado (orden del 2026-11-19): base de módulos vigente por huella y vigencia, obra real… |
| `dominio/registro_normativo.py` | Dom | 108, 107 | Registro normativo común de las specs 107 y 108 (tarjeta RN, dueña la 108): normas con estado jurídico (vigente_comprobada, modificada, prepublicada,… |
| `adaptadores/entrada/capex.py` | Ada | 072, 024 | Recibo de la lectura CAPEX efectiva desde descriptor protegido. |
| `adaptadores/pronostico_demanda.py` | Ada | 089 | Pronóstico de demanda en un módulo: libros descubiertos en cada carga, equivalencia alimentador–medidor con su clase, limpieza y sentido, cabecera,… |
| `dominio/planeamiento_etapas.py` | Dom | 087 | Cuándo construir cada obra: árbol de decisión y proceso de decisión de Markov. |

### Motor: PIT (plan de inversiones en transmisión)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `dominio/pit/__init__.py` | Dom | 107 | Paquete del PIT, aparte del PIDE, y su error común. |
| `dominio/pit/ambito.py` | Dom | 107 | Áreas de demanda del perfil y los elementos de cada una, sin mezclar áreas. |
| `aplicacion/pit/red_area.py` | Apl | 107 | Contrato neutro RedArea y lector del libro de la red del perfil. |
| `adaptadores/pit/red_pandapower.py` | Ada | 107 | De RedArea a pandapower (dos y tres devanados, compensación, acoplamientos de barras y redes externas PQ o PV con su consigna) y flujo del motor… |
| `adaptadores/pit/motores.py` | Ada | 107 | Matriz estudio × motor (abierto por defecto, DIgSILENT con licencia). |
| `adaptadores/pit/diagnostico.py` | Ada | 107 | Diagnóstico por año: demanda por barra de SET, caso base y N-1 contra los límites del registro o del perfil. |
| `dominio/pit/programa.py` | Dom | 107 | Programa por año, titular y área, con bajas y reemplazos. |
| `dominio/pit/observaciones.py` | Dom | 107 | Observaciones del regulador con su respuesta, enlazadas con la traza del expediente, y el documento de absolución con lo que cambió por cada una. |
| `adaptadores/pit/alternativas.py` | Ada | 107 | Alternativas excluyentes: inversión, COyM, pérdidas, confiabilidad y valor presente con la misma demanda y motor. |
| `adaptadores/pit/cuadros.py` | Ada | 107 | Cuadros desde su definición en el registro, formatos aplicables de la norma vigente (transcritos o nombrados), celdas con traza, vínculos entre… |
| `adaptadores/pit/reproduccion.py` | Ada | 107 | Aceptación con un expediente publicado (orden del 2026-11-19): lee por contenido los formatos publicados del PIT, reproduce F-119 a F-122 con… |
| `dominio/pit/f208.py` | Dom | 107 | Formato F-208 (fallas e índices de desempeño): estructura leída de la plantilla transcrita, celdas con traza desde las fuentes importadas, «Cumple»… |
| `dominio/pit/reserva.py` | Dom | 107 | Transformadores de reserva compartida: horizonte, costo de la ENS, umbral de beneficio/costo y exclusión por tensión desde el registro. |
| `adaptadores/pit/llenado.py` | Ada | 107 | Llenado de los formatos que exige el estudio del plan (regla del num. |
| `adaptadores/pit/plantillas.py` | Ada | 107 | Motor de llenado de un formato desde su plantilla transcrita y su mapeo declarado (config/pit_mapeo_formatos.json): comprueba rótulos y marcas, llena… |
| `adaptadores/pit/demanda_regulatoria.py` | Ada | 107 | Demanda regulatoria (paso 3b): curvas por devanado, SET y sistema sumadas instante a instante (los instantes incompletos se excluyen y se cuentan),… |
| `adaptadores/pit/formatos_red.py` | Ada | 107 | Datos de F-001, F-002 y F-003 desde la red del área, con los niveles de la regla 12.1.1 y sus cálculos declarados (Pcu%, Pfe%, B con la frecuencia… |
| `adaptadores/pit/expediente.py` | Ada | 107 | Expediente aparte del PIDE: instantánea del registro, aviso de modificatoria sin recalcular, reglas aplicadas, determinismo, memoria de cada sección,… |
| `adaptadores/pit/informe.py` | Ada | 107 | Resumen ejecutivo del PIT: demanda, alternativa elegida y programa, con cada cifra tomada de los ficheros del expediente y su huella. |
| `adaptadores/pit/unifilar.py` | Ada | 107 | Unifilar F-212 por alternativa y año: un espacio papel A3 por hoja con marco, rótulo y leyenda, barras con tensión nominal y calculada,… |
| `presentacion/web/rutas_pit.py` | Pre | 107 | Rutas /api/pit: áreas, matriz de motores, entradas (los cuatro libros de Excel y JSON), diagnóstico y expediente en cola con sus rutas dentro del… |
| `adaptadores/pit/armado.py` | Ada | 107 | Armado del expediente del PIT de punta a punta. |
| `adaptadores/pit/demanda_cadena.py` | Ada | 107 | Demanda regulatoria (paso 3c): F-108 (ventas proyectadas por nivel), F-109 (energía por barra con los FE de la fijación vigente de la empresa en… |
| `adaptadores/pit/demanda_resumen.py` | Ada | 107 | Demanda regulatoria (paso 3d): la historia del −20 al 0 (F-104 con las exógenas de la 031 y F-105), los modelos comparados con su ecuación y sus… |
| `adaptadores/pit/densidad.py` | Ada | 107 | F-123: los mapas de densidad de carga de los años de la nota de la plantilla, con la demanda de cada SED crecida con el factor regulatorio de su… |
| `adaptadores/pit/elementos_modificacion.py` | Ada | 107 | Los elementos de las modificaciones del PIT (agregan, reprograman, eliminan, baja) desde el registro, que guarda sus nombres por huella: casa por… |
| `adaptadores/pit/generacion.py` | Ada | 107 | F-124: los datos de generación deducidos del medidor de generación de cada central del perfil (`centrales_termicas`), con el lector de cabecera de la… |
| `dominio/pit/norma.py` | Dom | 107 | Lo que la Norma Tarifas fija para el PIT, leído del registro: años de la programación, horizonte, factor de potencia de MT, N-1 y reglas de la… |
| `adaptadores/pit/usuarios_libres.py` | Ada | 107 | F-113 a F-118: las demandas incorporadas del libro de cargas nuevas y los usuarios libres de `pit.usuarios_libres`, ubicados por su alimentador en la… |
| `adaptadores/pit/__init__.py` | Ada | 002 | Paquete de `pit` en la capa adaptadores. |
| `aplicacion/pit/__init__.py` | Apl | 002 | Paquete de `pit` en la capa aplicacion. |

### Motor: VAD y VNR (estudio de costos y Guía del VNR, spec 108)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/vad/__init__.py` | Apl | 108 | Paquete del estudio de costos del VAD (empresa modelo eficiente), aparte del PIDE y del PIT. |
| `aplicacion/vad/anexo2.py` | Apl | 108 | Validación de las tablas del estudio contra los formatos del anexo 2 transcritos (tabla, fila, columna, unidad, periodo), sin rellenar nada: huecos… |
| `aplicacion/vad/balance.py` | Apl | 108 | Balance de potencia y energía (6.10, A-VI) real y adaptado, con las fórmulas del formato transcrito. |
| `aplicacion/vad/calidad.py` | Apl | 108 | Calidad de servicio de la empresa modelo con el criterio del num. |
| `aplicacion/vad/caracterizacion.py` | Apl | 108 | Caracterización de la carga del Anexo 4 desde la medición: factor de carga, FCPP y FCFP en su periodo, pérdidas con la corriente y empíricas, y curva… |
| `adaptadores/vad/costos.py` | Ada | 108 | Costo estándar de la empresa modelo: valora solo la red dimensionada (`CostoEstandar` exige un `Dimensionamiento` con su huella) con el SICODI leído… |
| `aplicacion/vad/costos_explotacion.py` | Apl | 108 | VNR no eléctrico y costos de explotación por rubro del registro: total estándar solo con partidas dimensionadas y su fuente. |
| `aplicacion/vad/coym.py` | Apl | 108 | COyM del Anexo 7: cantidades adaptadas × costo unitario estándar por sistema y etapa, con los componentes y unidades del cuadro del registro (sin… |
| `adaptadores/vad/dimensionamiento.py` | Ada | 108 | Dimensionamiento de la empresa modelo del Anexo 6 sobre el modelo rural, sin tocar un vértice: potencia de cada SED con la tabla de transformadores… |
| `adaptadores/vad/entregables.py` | Ada | 108 | Entregables del estudio VAD: Formatos A y B del anexo 2 en Excel con una hoja por formato y cada celda calculada con su fórmula de Excel traducida de… |
| `aplicacion/vad/estudio.py` | Apl | 108 | Registro del estudio VAD (empresa del perfil, grupo, periodo, versión del TdR, estado) en `<espacio>/vad/<id>/estudio.json`, sin tocar las carpetas… |
| `aplicacion/vad/formulas.py` | Apl | 108 | Intérprete cerrado de las fórmulas del registro normativo del VAD (sin eval): números, variables, + - * / **, paréntesis y suma(n, …) sobre series… |
| `adaptadores/vad/informes.py` | Ada | 108 | Informe de Resultados Relevantes (anexo 3) e Informe del Estudio (numeral 9) en Word con los apartados del registro, cifras con origen o huecos… |
| `adaptadores/vad/linea.py` | Ada | 108 | La línea del VAD tras la empresa modelo: el modelo rural desde la red del espacio, el dimensionamiento con el sustento del caso y el costo estándar… |
| `adaptadores/vad/modelo_rural.py` | Ada | 108 | Modelo georreferenciado rural del Anexo 6: copia en solo lectura las trazas, longitudes y SED reales del VNR canónico o de la vía TXT/MDB… |
| `adaptadores/vad/modelo_urbano.py` | Ada | 108 | Anexo 5 urbano, las incoherencias del TdR resueltas como decidió 28: TRI_AREA, R_BT y NTRI en forma cerrada desde las fórmulas del registro, con… |
| `adaptadores/vad/observaciones.py` | Ada | 108 | Observaciones del regulador al estudio VAD en `<espacio>/vad/<id>/observaciones.json`: número, fecha, texto y lo que afectan (tablas del registro,… |
| `aplicacion/vad/pide_vad.py` | Apl | 108 | Contrato 072 → 108 (pide_vad_v1): lee el PIDE aprobado que entrega la 072 y calcula el VAD ajustado con el FRC de `util.frc`, la tasa de la LCE… |
| `aplicacion/vad/resultados_vad.py` | Apl | 108 | Cargo fijo y VAD de cada nivel por sistema y ponderado a nivel empresa, con los conceptos, variantes, fórmulas y ponderación del TdR registrado. |
| `adaptadores/vad/tablas_resultados.py` | Ada | 108 | Las Tablas de Resultados que lista el TdR registrado, en Excel: una hoja por tabla con su título, fuente, filas por sistema y total con =SUM, más el… |
| `aplicacion/vad/trabajo.py` | Apl | 108 | Armado de la empresa modelo como trabajo en cola (`armar_empresa_modelo(ctx, …)` para `JobManager.submit(..., lane='engine')`): sistema por sistema… |
| `adaptadores/vad/vnr_estudio.py` | Ada | — | Estudio VNR de una empresa desde su inventario VNR-GIS (modelo canónico del módulo ``vnr``), con la Guía del VNR |
| `adaptadores/vad/vnr_formatos.py` | Ada | — | Los formatos del Anexo 5 de la Guía del VNR (RCD 232-2017-OS/CD) en un libro Excel: una hoja por formato con sus |
| `aplicacion/vad/vnr_guia.py` | Apl | — | VNR según la «Guía de Elaboración del VNR de las Instalaciones de Distribución Eléctrica» (RCD 232-2017-OS/CD; |
| `adaptadores/vad/__init__.py` | Ada | 002 | Paquete de `vad` en la capa adaptadores. |

### Motor: biblioteca normativa y fuentes de la empresa (107, 109)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/biblioteca_normativa.py` | Apl | 107 | La biblioteca normativa general: la base del programa más la capa del usuario, actualizable, con su huella para reindexar. |
| `schemas/registro_normativo_v1.schema.json` | — | 108, 107 | Esquema del registro normativo común: cada norma con su estado jurídico, huella y vigencia, y cada regla con su cita literal y su página o líneas. |
| `dominio/huellas_terminos.py` | Dom | 107, 086 | La huella de un término, `sha256(sal:texto normalizado)[:16]` con la sal de la lista mínima: un solo cuerpo para la comprobación de la entrega y los… |
| `aplicacion/fuentes_empresa.py` | Apl | 109 | Los libros de la empresa del espacio, una vez y por periodo, y la red convertida que deja la carga para todos los módulos. |
| `adaptadores/pfd_vinculos.py` | Ada | 004, 109, 110 | Vínculos del proyecto de un `.pfd` (nombres de su diagnóstico y las SET) con los ficheros de su expediente por su contenido, con el inventario y la… |

### Motor: fachadas fuera del paquete

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `vnr_etl.py` | Pre | 002 | Fachada de CLI para python -m vnr_etl y el launcher anterior. |

### Motor: gobierno de modelos

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/model_registry.py` | Apl | 043, 060 | Candidatos inmutables, integridad, promoción atómica y reapertura en subproceso. |
| `aplicacion/training_coordinator.py` | Apl | 043 | Etapas reanudables, bloqueo GPU mediante guardia OS compartida y memoria física/comprometible antes de cargar pesos. |
| `aplicacion/trabajadores_ml.py` | Apl | 043 | Informes atómicos, dataset v2 verificado y herencia comprobada de la guardia GPU en procesos hijos. |
| `dominio/compat_gpu.py` | Dom | 106 | Fija en memoria la DLL del controlador NVIDIA antes del primer cuInit, para que su hilo no ejecute en ella descargada (0xC0000005). |
| `aplicacion/aprendizaje_continuo.py` | Apl | 050 | Ciclo común de aprendizaje: instantánea copiada y verificada, vistas por familia con particiones por observación, ciclo único sobre el coordinador,… |
| `aplicacion/evaluacion_modelos.py` | Apl | 044 | Política previa y validación de cuatro particiones por grupos. |
| `aplicacion/experimentos.py` | Apl | 043 | Contexto exacto y contratos inmutables de configuración, con SHA-256 canónico. |
| `adaptadores/upstream_ia.py` | Ada | 043 | Verifica origen, commit, licencia y árbol limpio de repositorios reutilizados. |
| `dominio/evaluacion_harness/estadistica.py` | Dom | 044, 069, 047 | Estadística común de la evaluación: Wilson, Holm, McNemar exacto, HAC, Diebold-Mariano con HLN, Wilcoxon con biserial, TOST, Bland-Altman, kappa,… |
| `aplicacion/evaluacion_harness/informe_final.py` | Apl | 044 | Informe único `docs/EVALUACION_FINAL_1.0.json`: rev, árbol limpio, huellas, IC, prueba, Holm y negativos. |
| `aplicacion/conjuntos_aprendizaje.py` | Apl | 050, 002 | Lectura verificada del conjunto activo para inferencia, separada de la preparación. |
| `dominio/contratos_aprendizaje.py` | Dom | 050, 002 | Identidad, procedencia y tipos puros de muestras y familias. |
| `adaptadores/productores_aprendizaje.py` | Ada | 050, 002 | Composición real y diferida por familia, con lectores/validadores existentes. |
| `puertos/puertos_muestras.py` | Pue | 050, 002 | Puerto de productores inyectado en la preparación del ciclo. |
| `aplicacion/evaluacion_harness/__init__.py` | Apl | 043, 044, 047 | Paquete de evaluación integral sin cargar modelos ni motores al importarlo. |
| `adaptadores/evaluacion_harness/adaptadores.py` | Ada | 043, 044, 047 | Adaptación de evaluaciones temporal, eléctrica y de herramientas externas, sin equivaler a aceptación nativa. |
| `presentacion/evaluacion_harness/cli.py` | Pre | 043, 044, 047 | Interfaz de sellado, replay y comprobación de informes del arnés. |
| `dominio/evaluacion_harness/contratos.py` | Dom | 043, 044 | Sello, política, identidad y particiones de las suites de evaluación. |
| `aplicacion/evaluacion_harness/ejecucion.py` | Apl | 043, 044 | Ejecución conservadora de suites y revalidación de sus resultados. |
| `adaptadores/evaluacion_harness/integracion.py` | Ada | 043, 044 | Puente al coordinador y registro, con guardas de identidad y activación explícita. |
| `dominio/evaluacion_harness/metricas.py` | Dom | 043, 044, 047 | Métricas con soporte, abstención y comparación pareada por grupos. |
| `adaptadores/evaluacion_harness/publicacion.py` | Ada | 043, 044 | Publicación atómica y relectura de informes sellados. |
| `adaptadores/evaluacion_harness/__init__.py` | Ada | 002 | Paquete de `evaluacion_harness` en la capa adaptadores. |
| `dominio/evaluacion_harness/__init__.py` | Dom | 002 | Paquete de `evaluacion_harness` en la capa dominio. |
| `presentacion/evaluacion_harness/__init__.py` | Pre | 002 | Paquete de `evaluacion_harness` en la capa presentacion. |
| `puertos/__init__.py` | Pue | 002 | Interfaces y versión de los módulos enchufables (`PUERTOS`) y puertos de los adaptadores internos de los casos de uso (`PUERTOS_ADAPTADORES`), en… |

### Motor: benchmarks anonimizados

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `adaptadores/benchmarks/__init__.py` | Ada | 112 | Paquete de los benchmarks de referencia anonimizados, con `generar_benchmark`, la única vía de emisión: escribe en un temporal, reproduce el estudio,… |
| `dominio/benchmarks/seudonimos.py` | Dom | 112 | Seudónimos por tipo con permutación sorteada, coherentes entre los tres ficheros y nunca serializables. |
| `adaptadores/benchmarks/manifiesto.py` | Ada | 112 | Manifiesto del benchmark en JSON canónico: huella del origen, versión y revisión del generador, semilla pública, transformaciones, columnas omitidas,… |
| `dominio/benchmarks/geometria.py` | Dom | 112 | Trazado sintético por el grafo, longitudes perturbadas con la semilla secreta y el control del atacante que empareja las longitudes ordenadas rango a… |
| `adaptadores/benchmarks/geometria_publica.py` | Ada | 112 | La geometría pública de una empresa: el paquete VNR-GIS vigente de Osinergmin, elegido por resolución y bajado bajo demanda a una carpeta fuera del… |
| `adaptadores/benchmarks/publicable.py` | Ada | 112 | Benchmark publicable: red sintética con los agregados de la entrega (al menos 5 alimentadores y 500 tramos, que se suben y no se bajan), sin un tramo… |
| `dominio/benchmarks/sintetico.py` | Dom | 112, 034 | Generador de TXT sintéticos y sorteados (antes en `tests/synthetic_export.py`, que lo reexporta), con longitudes y cargas por cuantiles para el… |
| `adaptadores/benchmarks/evaluacion.py` | Ada | 112 | Sellado de la prueba antes de elegir modelo (apertura exclusiva, huella fijada, rechazo si cambia) e informe publicado con todos los resultados,… |
| `dominio/benchmarks/interempresa.py` | Dom | 112 | Dejar una empresa fuera cada vez, sin E/S: un pliegue por empresa que ajusta con las demás y mide en la retenida, el veredicto (con menos de 3… |
| `adaptadores/benchmarks/interempresa.py` | Ada | 112 | Dejar una empresa fuera cada vez con datos en disco: el trío TXT de cada empresa para la conversión VNR, los benchmarks de series para el pronóstico… |
| `aplicacion/benchmarks/cohortes.py` | Apl | 112 | Cohortes de evaluación por empresa (una fuera) y por tiempo con franja de separación, por componente conexo de alimentadores y clientes, validadas… |
| `dominio/benchmarks/redes.py` | Dom | 112 | Benchmark de redes: el trío TXT con una lista cerrada de secciones y columnas, en la disposición del origen, sin texto libre y con el perfil neutro. |
| `adaptadores/benchmarks/reproduccion.py` | Ada | 112 | El mismo estudio (reglas y oráculo) en el original y en el benchmark, comparado alimentador a alimentador con la tolerancia del estudio o la de por… |
| `adaptadores/benchmarks/series.py` | Ada | 112 | Benchmark de series del 089: seudónimo, escala sorteada, semanas completas desplazadas, exógenas como columnas, potencia en bandas y CSV determinista. |
| `adaptadores/benchmarks/reidentificacion.py` | Ada | 112 | Control de reidentificación antes de emitir: identificadores, clientes, términos del perfil, rutas, coordenadas, fechas, secuencias de valores,… |
| `dominio/benchmarks/semilla.py` | Dom | 112 | La semilla secreta de los seudónimos: se sortea con 12 cifras o más, se guarda solo en la carpeta local por la huella del origen y sin pisar otra, y… |
| `aplicacion/benchmarks/__init__.py` | Apl | 002 | Paquete de `benchmarks` en la capa aplicacion. |
| `dominio/benchmarks/__init__.py` | Dom | 002 | Paquete de `benchmarks` en la capa dominio. |

### Gemelo digital: `digital_twin/`

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `adaptadores/digital_twin/__init__.py` | Ada | 024 | Paquete del gemelo digital: episodios, búfer y captura, sin PowerFactory ni PyTorch. |
| `dominio/digital_twin/episode.py` | Dom | 024 | Contrato del episodio: clase y caso, fuente y proyecto, resultados del flujo (balance, pérdidas, cargabilidad, tensiones, confiabilidad, o el motivo… |
| `adaptadores/digital_twin/buffer.py` | Ada | 024, 086, 120 | Búfer local e inmutable de episodios: un JSON por huella, escritura atómica e idempotente, colisión detectada, índice SQLite reconstruible con… |
| `adaptadores/digital_twin/capture.py` | Ada | 024 | Ensamblaje del episodio desde el contexto firmado, el resultado del guion y la lectura tras reabrir. |
| `adaptadores/digital_twin/integration.py` | Ada | 024 | Captura tras cada acción nativa de la web: plan de lectura, norma de cada alimentador por su sistema y límites más estrictos, referencia del último… |
| `adaptadores/digital_twin/native_snapshot.py` | Ada | 024 | Identidad estable de un objeto de DIgSILENT, huella SHA-256 de un trazado e islas por tramos cerrados, sin suponer red radial. |
| `adaptadores/digital_twin/evaluacion.py` | Ada | 024 | Evaluación por caso: «Caso base» y «Sin proyecto» con las violaciones como diagnóstico (y el cuadre de la calibración), «Con proyecto» contra la… |
| `adaptadores/digital_twin/escenarios.py` | Ada | 024 | Matriz de escenarios (demanda escalada y N-1), familia topológica y partición fija, elección por incertidumbre o diversidad y presupuesto de licencia… |
| `adaptadores/digital_twin/auditoria.py` | Ada | 027 | Auditoría del dataset de cada modelo antes de entrenar: muestras, redes distintas, nodos, columnas, fracción etiquetada, rangos, no finitos (no se… |
| `adaptadores/digital_twin/curva.py` | Ada | 027 | Episodios del gemelo por sistema eléctrico frente a los 30/10/10 (reparto fijo por la huella de cada episodio) y curva de aprendizaje que dice si un… |
| `adaptadores/digital_twin/hiperparametros.py` | Ada | 027, 060 | Búsqueda de hiperparámetros del gemelo con Optuna (TPE y poda por mediana), limitada por ensayos con el reloj como tope de seguridad que no elige,… |
| `adaptadores/digital_twin/contratos_fisicos.py` | Ada | 045 | Versión y alcance del grafo del gemelo: qué física representa y por qué rechaza una red, y huellas de controles y caso. |
| `adaptadores/digital_twin/oraculo.py` | Ada | 024, 060 | Oráculo PINN/GNN (PyTorch, GPU si la hay): grafo por unidad, red de grafos sobre la física mallada con pérdida física de balance por barra eléctrica,… |
| `adaptadores/digital_twin/flujo.py` | Ada | 024 | Flujo de carga físico por matriz de admitancias dispersa, con lazos: acopladores fusionados en una barra, factorización LU una sola vez, punto fijo… |
| `adaptadores/digital_twin/motores_flujo.py` | Ada | 083 | Motores de flujo del oráculo sobre la misma red: Z-bus, Anderson, Newton, power-grid-model y OpenDSS. |
| `adaptadores/digital_twin/benchmark_fisico.py` | Ada | 045 | Ablaciones del gemelo sobre las mismas particiones (física pura, red sin término físico, híbrido y PowerFlowNet) y comprobación de dominio antes de… |
| `adaptadores/digital_twin/adaptador_pyg.py` | Ada | 045 | Adapta el MPN de PowerFlowNet a correcciones físicas de tensión y ángulo, mediante carga opcional. |
| `adaptadores/digital_twin/evolutivo.py` | Ada | 024, 044, 048 | Algoritmo genético, NSGA-II y evolución diferencial autoadaptativa (jDE), deterministas con su semilla. |
| `adaptadores/digital_twin/problema_optimizacion.py` | Ada | 048 | Contrato común de una búsqueda de obras y consignas: variables tipadas con unidad, origen y coste trazable, restricciones, objetivos, contexto y… |
| `adaptadores/digital_twin/adaptador_pymoo.py` | Ada | 048 | GA, NSGA-II y DE de pymoo, opcionales, como candidatos del benchmark de la 048: genes reparados por la regla común y presupuesto cortado por el… |
| `adaptadores/digital_twin/benchmark_optimizacion.py` | Ada | 048 | Benchmark de los optimizadores vigentes y los de pymoo: al menos veinte semillas comunes, presupuesto en evaluaciones reales (caché aparte),… |
| `adaptadores/digital_twin/adaptador_pnl.py` | Ada | 048 | Tramo continuo con Pyomo y un solucionador PNL (Ipopt por omisión, HiGHS para cuadráticos) con las discretas fijas: punto local continuo, nunca… |
| `adaptadores/digital_twin/temporal.py` | Ada | 024, 046, 060 | Gemelo temporal: GRU de las curvas de cabecera (estacional sin PyTorch), GRU multihorizonte para competir en el pronóstico, métricas, desviaciones… |
| `adaptadores/digital_twin/temporal_entrenamiento.py` | Ada | 043, 046, 060 | Lectura de series mediante lectores existentes, ajuste causal GRU, objetivos de cabecera y clientes, competición de pronósticos con ganador por… |
| `adaptadores/digital_twin/series_causales.py` | Ada | 046 | Cadencia, unidades, huecos, disponibilidad de covariables, particiones por día y ventanas causales. |
| `adaptadores/digital_twin/pronostico.py` | Ada | 046 | Contrato multihorizonte: objetivos, conjunto en rejilla común, referencias ingenuo y estacional semanal, calibración de intervalos y filas con la… |
| `adaptadores/digital_twin/evaluacion_temporal.py` | Ada | 046 | Política predeclarada, pinball y cobertura por horizonte, error de la máxima y de su instante y familias para las puertas. |
| `adaptadores/digital_twin/adaptador_neuralforecast.py` | Ada | 046 | N-HiTS, TFT y PatchTST de neuralforecast, opcionales y solo en CUDA, con la interfaz común. |
| `adaptadores/digital_twin/productor_pinn.py` | Ada | 050, 002 | Vista PINN congelada, con particiones comunes. |
| `dominio/digital_twin/__init__.py` | Dom | 002 | Paquete de `digital_twin` en la capa dominio. |

### Asistente: núcleo y operación

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Apl | 026 | Paquete del asistente de órdenes en lenguaje natural. |
| `tareas.py` | Apl | 026 | Catálogo de tareas: datos tipados, si escribe (confirmación), modo (consulta, trabajo, proceso), función de la web que lo hace y plantillas de frases. |
| `interprete.py` | Apl | 026 | Intérprete híbrido: Transformer, si duda Ollama, si duda pregunta. |
| `plan.py` | Apl | 026, 078 | Del texto interpretado al plan: datos contrastados con lo que existe (parecido, tomados del texto), lo que falta, dudas y razonamiento. |
| `planes_guardados.py` | Apl | 067 | Planes que escriben guardados por espacio con escritura atómica: sobreviven a un reinicio, sin confirmación y sin reanudarse. |
| `contratos_salida.py` | Apl | 047 | Esquema de órdenes y validación de tareas, campos, confianza y entidades del contexto. |
| `ejecutor.py` | Apl | 026 | Ejecuta el plan confirmado por las rutas y trabajos de la web, paso a paso, esperando cada trabajo. |
| `orquestador.py` | Apl | 027, 061 | El proyecto entero desde el espacio, etapa por etapa por las rutas de la web (fuente, sistema, «Caso base», cargas nuevas, obras, estudios, PIDE,… |
| `equipo.py` | Apl | 065 | Gobierno de herramientas y permisos sellados por plan, rol y fuente. |
| `revision_roles.py` | Apl | 065, 047 | Revisión local por roles sin autorización de escrituras nativas, y su comparación contra un revisor único. |
| `contradicciones.py` | Apl | 047 | Qué contradicción de un dictamen de revisión cuenta: cifras normalizadas, cuentas evaluadas, valores en la propuesta y en la fuente, misma base. |
| `evidencias_web.py` | Apl | 067 | Custodia como evidencia del espacio el resultado de los informes y estudios que terminan bien, con su proyecto y su fuente verdaderos, para la… |
| `observacion.py` | Apl | 061, 026 | Diario SQLite por espacio, contexto inmutable, informes custodiados y control de identidad de reanudación, sin promoción. |
| `vigilancia.py` | Apl | 026, 050 | Vigilancia de trabajos (fallos, tiempos, colas, reintento del 4002), modelos, calidad de resultados y suite nocturna con el RF de cada fallo. |
| `mejoras.py` | Apl | 026 | Mejoras en una rama aparte (git worktree) con spec y pruebas y su suite. |
| `internet.py` | Apl | 026 | Búsquedas en GitHub, PyPI y arXiv con el filtro de identificadores de la red y rutas. |
| `almacen.py` | Apl | 026 | Dónde guarda el asistente lo suyo, en la máquina: registros JSONL de solo añadir (órdenes, ejemplos, decisiones, avisos, internet, suite) y JSON… |
| `senales.py` | Apl | 027 | Recompensas y penalizaciones de cada orden, pares de preferencia para DPO, memoria de reflexiones y contexto de órdenes parecidas para Ollama. |

### Asistente: modelos de órdenes y documentos

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `transformer.py` | Apl | 026 | Transformer propio por caracteres: tarea y datos (etiquetas por carácter decididas por palabra), entrenamiento en GPU, prueba fija, registro,… |
| `codificador_ordenes.py` | Apl | 069, 075 | Intérprete de órdenes con codificador preentrenado congelado, cabezas de tarea y de datos, clase «ninguna» y el lugar en que el modelo la ve. |
| `afinado_ordenes.py` | Apl | 079 | Afinado de las últimas capas del codificador junto con las cabezas: lo congelado una vez, tasas diferenciadas, contrastiva, lotes por grupo, parada… |
| `validacion_cruzada.py` | Apl | 075 | Validación cruzada con las órdenes confirmadas: familias de frases casi iguales, reparto en 5 vueltas estratificado por tarea, cabezas por vuelta… |
| `datos_por_palabra.py` | Apl | 026, 069 | Etiquetas de los datos de una orden y su decisión por palabra, comunes a los dos modelos de órdenes. |
| `clasificador.py` | Apl | 026 | Clasificador de informes en dos niveles (estudio o factibilidad, y subtipo del perfil) sobre el mismo codificador. |
| `clasificador_vectores.py` | Apl | 026 | Segunda arquitectura del clasificador de informes: vectores del codificador preentrenado (revisión fija, caché local) del informe y de su línea… |
| `modelos_en_uso.py` | Apl | 067, 085 | Pone en uso lo que el registro aprobó con un único puntero atómico, conserva el anterior y vuelve a él con el registro de acuerdo. |
| `ollama.py` | Apl | 026 | Cliente del modelo local de Ollama: solo direcciones de la máquina, tareas como herramientas con respuesta JSON, respuestas con cita y embeddings. |

### Asistente: datos y entrenamiento

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `sinteticos.py` | Apl | 026 | Órdenes sintéticas por plantilla con los nombres reales del espacio y erratas solo en las palabras de la plantilla. |
| `ordenes_fijas.py` | Apl | 027 | Las 200 órdenes fijas del asistente escritas por el maestro (Claude), de todas las tareas y distintas de las plantillas, con su huella y su reparto… |
| `ordenes_maestro.py` | Apl | 085, 047 | Órdenes que redacta el maestro en el estilo del operador: las valida, aparta por tarea un 25 % de sus familias para examen y dice qué conjunto decide… |
| `maestro_real.py` | Apl | 068 | Lee y valida las etiquetas de plata del maestro sobre textos reales, dice cuándo dos textos son la misma frase o familia y añade las erratas… |
| `curriculo_maestro.py` | Apl | 047, 068 | Familias sintéticas de órdenes escritas por el maestro de sesión, separadas antes del entrenamiento, y frases de estilo real solo de entrenamiento. |
| `curriculo_llm_real.py` | Apl | 047 | Solicitudes nuevas de prueba redactadas por el maestro. |
| `propuestas_maestro.py` | Apl | 047 | Corpus separado de 200 propuestas únicas, con anotaciones y procedencia del maestro. |
| `prueba_sellada.py` | Apl | 070 | La prueba sellada de las órdenes desde la 070: seis frases por tarea, un vocabulario propio y una huella fija. |
| `prueba_sellada_026.py` | Apl | 026 | La prueba sellada de las cinco tareas nuevas de la 026 (el Estudio VNR, la evolución de clientes fijos y las tres órdenes de la biblioteca… |
| `prueba_sellada_079.py` | Apl | 079 | La prueba sellada que decide desde la 079: seis frases por tarea escritas de una vez antes de medir, vocabulario inventado, huella fija y su método… |
| `aceptacion.py` | Apl | 047 | Auditoría, evaluación del intérprete/plan y puertas de aceptación por alcance. |
| `dataset_entrenamiento.py` | Apl | 043, 026 | Custodia de datos reales, sintéticos y de contexto. |
| `calidad_datos.py` | Apl | 043 | Calidad y contaminación entre particiones sin inflar el conjunto humano. |
| `entrenamiento_dataset.py` | Apl | 043 | Ajuste de clasificadores pequeños sobre particiones v2 explícitas. |
| `destilacion.py` | Apl | 027 | Destilación del modelo local de Ollama (maestro) al Transformer de órdenes: k votos con temperatura por orden sin etiqueta, filtro por acuerdo y… |
| `destilacion_integral.py` | Apl | 047, 069 | Comparación supervisado/destilado, calibración, prueba sellada, puerta de no regresión en las humanas frente al modelo en uso (McNemar exacto),… |
| `ajuste_condicionado.py` | Apl | 047 | Puertas de 027:RF-18 sobre órdenes reales independientes y decisión de ajustar el LLM, sin entrenar ni activar. |
| `llm_destilacion.py` | Apl | 047, 060 | Custodia de referencia, corpus del LLM con entidades reales y objetivos causales de respuesta. |
| `llm_checkpoint.py` | Apl | 002 | Comprobaciones de un checkpoint, comunes a entrenar y publicar. |
| `llm_runtime.py` | Apl | 047, 072 | Verifica checkpoints y publica exportación, GGUF e importación local secuencial con hashes y readback, con los parámetros de decodificación en su… |
| `custodia_corpus.py` | Apl | 047, 065 | Resolución explícita y verificable de fuentes custodiadas tras su traslado, sin alterar ejemplos ni particiones. |
| `corpus_contrato_llm.py` | Apl | 047 | Corpus v7 de órdenes del alumno destilado con las 67 tareas del contrato vigente: frases del maestro por partición, valores seudonimizados, orígenes… |
| `reubicacion_corpus.py` | Apl | 047, 065 | Nueva custodia externa del corpus LLM con cuotas, hashes, preflight y conservación del original. |
| `corpus_redaccion.py` | Apl | 072 | Corpus de redacción del PIDE: solo lo que una persona revisó y aprobó para redactar o dar formato, sin cifras ni códigos de otra red, en un registro… |
| `prueba_sellada_107_112.py` | Apl | 070 | La prueba sellada de las once tareas de las specs 107 a 112 (la nube, el correo, el PIT, el VAD, el plano y el benchmark): seis frases por tarea de… |

### Asistente: conocimiento y RAG

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `aplicacion/asistente/indice.py` | Apl | 026, 047 | Índice local del proyecto (CODIGO_FUENTE, RF de las specs, docstrings, manual, constitución), BM25 y vectores fusionados por posición, cálculo de… |
| `aplicacion/asistente/embeddings.py` | Apl | 043, 047, 097 | Pares contrastivos, métricas de recuperación (también hit@10), encoder CUDA local y persistencia de índices con hashes. |
| `aplicacion/asistente/reranker.py` | Apl | 047 | Reranker por cross-encoder en CUDA, con revisión fijada, la política que lee la decisión de la evaluación sellada y los umbrales de abstención… |
| `aplicacion/asistente/evaluacion_rag.py` | Apl | 047, 097 | Conjunto sintético sellado, medición de BM25, híbrido y rerankers, decisión según la política declarada, calibración de la abstención y su puerta en… |
| `aplicacion/asistente/fuga_evaluacion.py` | Apl | 097, 026 | Ninguna pregunta ni orden de un conjunto de evaluación en lo que la juzga: qué conjunto mide qué corpus, preguntas literales fuera de su fuente, de… |
| `aplicacion/asistente/pregunta_entregada.py` | Apl | 086, 097 | «Pregunta» en el programa instalado: calibra al construir el candidato la abstención por BM25 sobre los manuales y notas que se entregan, con la… |
| `aplicacion/asistente/corpus_proyecto.py` | Apl | 077 | Corpus ampliado del índice: ficheros, troceado sin perder líneas, caché por fichero y medida de tamaño. |
| `aplicacion/asistente/lectura_proyecto.py` | Apl | 077 | Lecturas del proyecto para el LLM y el MCP: leer un fichero, buscar un texto literal y consultar una ruta en el OpenAPI, con política local o… |
| `adaptadores/asistente/ejemplos_pide.py` | Ada | 027 | Ejemplos del agente desde el corpus PIDE entregado: por artículo sus evidencias en cada PIDE (por la ruta y el texto), por formato F01 a F15 sus… |
| `aplicacion/asistente/corpus_normativo.py` | Apl | 077 | La biblioteca normativa en el asistente, leída por su API: un fragmento por regla en el índice ampliado, su huella, la comprobación de una cita… |
| `adaptadores/asistente/__init__.py` | Ada | 002 | Paquete de `asistente` en la capa adaptadores. |
| `aplicacion/asistente/rutas_historicas.py` | Apl | 002 | Las rutas de fichero de antes de que cada módulo pasara a su paquete de capa: los conjuntos sellados no se reescriben y sus rutas se leen con las de… |

### Web: `web/`

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Pre | 001 | Paquete de la interfaz web. |
| `__main__.py` | Pre | 001 | Arranca la web: `python -m convertersmartgrid.presentacion.web` o `convertersmartgrid-web`. |
| `app.py` | Pre | 001, 004, 008, 011, 104, 017, 103, 021, 022, 025, 035, 039, 042, 061, 091 | Rutas FastAPI sobre el motor.; conversión por sistema eléctrico (`/convert/sistema`, `/estructura`) y la tabla de la estructura |
| `api_contract.py` | Pre | 065, 002 | Modelos públicos Pydantic y contratos OpenAPI del frontend. |
| `services.py` | Pre | 001, 004, 008, 092, 011, 121, 017, 104, 020, 021, 022, 025, 018, 030, 032, 035, 037, 038, 039, 041, 042, 060, 061, 091, 101 | Las acciones de la interfaz, sin interfaz. |
| `requisitos.py` | Pre | 002 | Lo que un servicio exige antes de trabajar y el error del operador. |
| `jobs.py` | Pre | 001, 011, 061, 086 | Trabajos largos en cola, con progreso, cancelación y límite de tiempo por guion (P7). |
| `operaciones_lentas.py` | Pre | 065 | ZIP cancelable, cuotas y entrega de archivos por trabajo. |
| `workspace.py` | Pre | 001, 011, 025, 018, 035, 038, 065, 086 | Espacio de trabajo: entradas, opciones, salida de una sesión y obras de mejora sin aplicar. |
| `source_runs.py` | Pre | 001 | Custodia inmutable de los ficheros de cada ejecución. |
| `source_scope.py` | Pre | 001, 059 | Empresa y periodo de los paquetes VNR-GIS. |
| `readiness.py` | Pre | 001, 053 | Puertas por alimentador antes de producir DGS. |
| `reconstruction_service.py` | Pre | 001 | Diagnóstico y reconstrucción como trabajos de la web. |
| `asistente_operacion.py` | Pre | 070 | Lo que cada tarea del asistente necesita del espacio, comprobado antes de ofrecer confirmar: calibración, libros, costeo, formulario y las formas que… |
| `asistente_consultas.py` | Pre | 070 | Las consultas del asistente sin escribir ni abrir DIgSILENT: qué dato se pide, su fuente, «no lo encuentro» y por qué un estudio no está disponible. |
| `equipo_api.py` | Pre | 065 | API del equipo LLM: permisos por plan y revisiones locales en cola. |
| `seguridad.py` | Pre | 086 | La puerta de la web, en un middleware ASGI: Host, Origin, token de la sesión (también en el WebSocket) y política de contenido. |
| `runtime.py` | Pre | 001, 036, 065 | Comprobación del entorno que hace el lanzador de Windows y huella del código. |
| `doctor.py` | Pre | 086, 091, 106 | Qué le falta a la instalación, qué función afecta y cómo arreglarlo, para la orden y la pantalla. |
| `soporte.py` | Pre | 086 | Paquete de soporte con una lista cerrada, sin datos del cliente: registros anonimizados y forma del perfil. |
| `copia_datos.py` | Pre | 086 | Copia y restauración de los datos con manifiesto, según la regla de la retención, cada fichero físico una vez, con reintentos y cálculo de lo que… |
| `copia_datos_api.py` | Pre | 086 | Rutas `/api/copia-datos/carpeta` y `…/copia-datos`: la copia de los datos como trabajo, con la carpeta recordada. |
| `correo_api.py` | Pre | 110 | Rutas del correo (`registrar_rutas_correo`): vista previa con el borrador y su firma, confirmar solo desde la ventana del navegador (reserva la clave… |
| `mapa_cargas_api.py` | Pre | 017, 109, 124 | Rutas `…/mapa-cargas`, `…/pagina`, `…/digsilent` y `…/confirmar`: el mapa de las cargas nuevas, la lectura sin escribir en DIgSILENT y «Usar este… |
| `plano_api.py` | Pre | 111 | Rutas `…/plano`, `…/plano/pagina`, `…/plano/variaciones` (listar lo guardado, abrir, leer, editar con versión, deshacer, rehacer, confirmar, ajuste y… |
| `entradas_estudios_api.py` | Pre | 012 | Rutas `…/pf/entradas-estudios`: leer ficheros como trabajo (borrador), guardar lo confirmado, descartar y listar, por proyecto en la carpeta del… |
| `retencion.py` | Pre | 062, 065 | Revisión diaria de ejecuciones y temporales sin referencias, de más de siete días, con protección de datos y resumen persistido. |
| `libros_nuevos.py` | Pre | 104 | La web reconoce sola los libros nuevos de demanda: compara fotos al arrancar, al abrir un espacio y cada intervalo. |
| `fondo.py` | Pre | 104 | Carril de fondo de la web: mira si el operador tiene trabajos en el motor o en DIgSILENT, corre cada libro en un proceso de prioridad baja que se… |
| `suspension.py` | Pre | 096 | Tiempo suspendido del equipo y petición a Windows de no suspender mientras corre un trabajo. |
| `cierre.py` | Pre | 081 | Registro de cada arranque y cierre de la web, con su motivo. |
| `evolucion_fijas.py` | Pre | 105 | Servicio de la evolución de los clientes fijos: libros del espacio, trabajo con avance, último resultado y curvas, libro en la salida y su archivo. |
| `evolucion_fijas_api.py` | Pre | 105 | Rutas `…/clientes-fijos/evolucion`, su curva y `/api/archivo`, montadas en la API única. |
| `nube_api.py` | Pre | 109 | Rutas de la nube (`/api/nube/…`, `…/nube/…` y `/nube/retorno`), con su modelo de respuesta: conectar, importar por la vía de una subida, versiones,… |
| `nube.py` | Pre | 109 | Vínculos con la nube (`nube/vinculos.json`): aviso de revisión nueva, comparación con la copia vigente y aceptación solo confirmada. |
| `nube_selector.py` | Pre | 109 | Página del selector de Google Picker y del File Picker v8 de OneDrive, con su propia CSP. |
| `fuentes_api.py` | Pre | 109 | Las fuentes de la empresa en la web: listar, subir, la red del espacio y la ayuda que usan los módulos para tomar un libro o su subida. |
| `normativa_api.py` | Pre | 107 | La biblioteca normativa general en la web: las normas con lo que obliga en una fecha, sus reglas con la cita la subida de una norma a la capa del… |
| `matriz_estudios_api.py` | Pre | 100 | `GET /api/estudios/matriz`: la matriz estudio × motor con el estado de las specs releído en cada petición: de `specs/` si está, si no del recurso… |
| `vad_api.py` | Pre | 108, 070 | Rutas `…/vad/estudios` (listar y crear el estudio con la empresa del perfil y un TdR del registro) y `…/vad/{estudio}/armar` (el caso subido a la… |
| `vnr_api.py` | Pre | — | 108 T28: el estudio VNR desde la web (Guía del VNR, RCD 232-2017-OS/CD; 108:RF-21 a RF-25). |

### Nube: Google Drive y OneDrive (spec 109)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `nube/__init__.py` | Ada | 109 | Paquete de la nube: contrato, transporte único, OAuth y un adaptador por proveedor. |
| `nube/proveedor.py` | Ada | 109 | Contrato `ProveedorNube`, `Item`, errores tipados con su causa y huellas locales (SHA-256 y QuickXorHash). |
| `nube/http.py` | Ada | 109 | El único transporte HTTP hacia la nube: sin proxy del entorno, sin redirecciones, lista de hosts, tope de bytes y `Retry-After`. |
| `nube/oauth.py` | Ada | 109 | Cliente OAuth desde `config/nube.json` (en `.gitignore`), PKCE (S256), `state` de un solo uso, permisos mínimos, canje, refresco y revocación. |
| `nube/cuentas.py` | Ada | 109 | Cuentas conectadas por espacio y proveedor: proveedores registrados, conexión, token de acceso en memoria, refresco desde el cofre, desconexión y el… |
| `nube_cofre.py` | Ada | 109 | Cofre DPAPI de Windows (por `ctypes`) del token de refresco, por espacio y proveedor, en `secretos/nube/`, fuera de los datos que se copian. |
| `nube/google_drive.py` | Ada | 109 | Google Drive API v3 por REST: metadatos con revisión y huella, listado, descarga por rangos, exportación a XLSX, subida reanudable y permisos. |
| `nube/onedrive.py` | Ada | 109 | Microsoft Graph v1.0 por REST: `cTag`, `downloadUrl` validado, `createUploadSession` sin sobrescribir e `invite` de solo lectura. |
| `entrada/nube.py` | Ada | 109 | Copia inmutable de un fichero de la nube en `nube/copias/<sha256>/` con `copia.json`. |
| `salida/__init__.py` | Ada | 109 | Paquete de las salidas hacia fuera de la máquina. |
| `salida/nube.py` | Ada | 109 | Paquete cerrado con manifiesto, publicación idempotente sin sobrescribir, previa y confirmación de un solo uso, permisos de solo lectura, recibos y… |

### VNR-GIS: `adaptadores/entrada/vnr/`

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Ada | 001 | Paquete del módulo VNR-GIS. |
| `__main__.py` | Pre | 001 | `python -m vnr_etl`. |
| `cli.py` | Pre | 001 | Orden `vnr-etl`. |
| `config.py` | Ada | 001 | Configuración del ETL. |
| `doctor.py` | Ada | 001 | Dependencias y capacidades (`vnr-etl doctor`). |
| `logging.py` | Ada | 001 | Registro estructurado de eventos. |
| `pipeline.py` | Ada | 001 | Capa de aplicación compartida por el CLI y la web. |
| `reglas_tramo.py` | Dom | 080 | Reglas de estado, medio y tipo de red de un tramo, sin dependencias: las usan la vía SQL, la de capas y el puente. |
| `application/__init__.py` | Ada | 001 | Servicios compartidos por el CLI y la API. |
| `application/cymdist_bridge.py` | Ada | 001 | Del modelo canónico VNR al contrato del motor. |
| `application/reconstruccion.py` | Ada | 001 | Reconstruye el modelo canónico antes del motor. |
| `application/services.py` | Ada | 001 | Validación y exportación VNR en un solo sitio. |
| `audit/__init__.py` | Ada | 001 | Auditoría de solo lectura. |
| `audit/project.py` | Ada | 001 | Auditoría del proyecto anfitrión. |
| `catalogs/__init__.py` | Ada | 001 | Catálogos aprobados de conductores y equipos. |
| `catalogs/conductor.py` | Ada | 001 | Mapeo del catálogo de conductores. |
| `connectors/__init__.py` | Ada | 001 | Conectores de fuente. |
| `connectors/base.py` | Ada | 001 | Contrato de los conectores. |
| `connectors/registry.py` | Ada | 001 | Registro de adaptadores de fuente. |
| `connectors/arcgis.py` | Ada | 001 | Conector ArcGIS REST. |
| `connectors/databases.py` | Ada | 001 | Bases de datos y volcados SQL. |
| `connectors/delimited.py` | Ada | 001 | Texto delimitado (CSV/TXT) con codificación y separador deducidos. |
| `connectors/vector.py` | Ada | 001 | GeoJSON, Shapefile y GeoPackage. |
| `connectors/sqlserver_vnr.py` | Ada | 023, 054 | Copia de SQL Server (`.bak`) de VNR-GIS de cualquier concesionaria: restaura con su huella, lee las tablas por sus campos y arma el modelo canónico… |
| `discovery/__init__.py` | Ada | 001 | Descubrimiento, huella, catálogo y descarga de fuentes. |
| `discovery/catalog.py` | Ada | 001 | Catálogo de publicaciones y empresas. |
| `discovery/download.py` | Ada | 001, 065 | Descargas y manejo seguro de archivos. |
| `discovery/fingerprint.py` | Ada | 001 | Huella de fuente y de esquema. |
| `discovery/freshness.py` | Ada | 001 | La publicación más nueva por fecha autoritativa. |
| `discovery/official.py` | Ada | 001 | Publicaciones oficiales de OSINERGMIN. |
| `discovery/schema.py` | Ada | 001 | Descubrimiento semántico del esquema. |
| `electrical/__init__.py` | Ada | 001 | Enriquecimiento eléctrico. |
| `electrical/enrich.py` | Ada | 001 | Completa los datos eléctricos del modelo. |
| `exporters/__init__.py` | Ada | 001 | Exportadores de simulador. |
| `exporters/base.py` | Ada | 001 | Contrato del exportador y perfil de destino. |
| `exporters/capas.py` | Ada | 080 | Copia VNR-GIS restaurada → paquete de capas (GeoPackage), sin un segundo ETL. |
| `exporters/cymdist.py` | Ada | 001 | Exportador CYMDIST. |
| `exporters/dgs.py` | Ada | 001 | Exportador DIgSILENT: delega en el motor. |
| `gis/__init__.py` | Ada | 001 | CRS, snapping y reconstrucción de nodos. |
| `gis/crs.py` | Ada | 001 | CRS de las capas y su deducción. |
| `gis/geometry.py` | Ada | 001 | Geometría auxiliar, sin `shapely`. |
| `gis/snapping.py` | Ada | 001 | Snapping y reconstrucción de nodos. |
| `models/__init__.py` | Ada | 001 | Modelo canónico VNR-GIS. |
| `models/canonical.py` | Ada | 001 | Clases del modelo canónico. |
| `reconciliation/__init__.py` | Ada | 001 | Reconciliación y comparación de periodos. |
| `reconciliation/diff.py` | Ada | 001 | Comparación incremental por ID estable. |
| `topology/__init__.py` | Ada | 001 | Topología y validación del grafo. |
| `topology/graph.py` | Ada | 001 | Validación de topología con NetworkX. |
| `validation/__init__.py` | Ada | 001 | Puertas de validación A–H. |
| `validation/gates.py` | Ada | 001 | Las puertas A–H. |
| `web/__init__.py` | Pre | 001 | Rutas web VNR-GIS, montadas en la API principal. |
| `web/app.py` | Pre | 001 | `APIRouter` bajo `/api/vnr`. |

### Guiones de DIgSILENT: `tools/` (corren con su intérprete)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `_plural.py` | — | 086, 110 | Concordancia de número de los textos de los guiones de `tools/` (`cuenta`, `plural`), con la biblioteca estándar de Python 3.9 para los que corren en… |
| `powerfactory_acceptance.py` | — | 034, 010, 015, 054, 078 | Puerta de aceptación: importa un DGS en PowerFactory, o adopta un proyecto existente, y verifica su «Caso base» frente al archivo original. |
| `casos_pf.py` | — | 011, 014, 015, 016, 025, 037, 073 | Guion de DIgSILENT: los casos «Caso base», «Sin proyecto» y «Con proyecto», cada uno con su escenario y sus variaciones. |
| `ajuste_cabecera_pf.py` | — | 006, 008, 011, 014, 015, 020, 021, 022, 025, 032, 035, 039, 041, 094, 095, 091 | Guion de DIgSILENT: ajusta un alimentador a su máxima de cabecera, en el escenario de «Sin proyecto». |
| `cargas_pf.py` | — | 004, 007, 008, 011, 016, 022, 035, 040, 054, 099 | Guion de DIgSILENT: demandas y cargas nuevas en un proyecto existente. |
| `obras_pf.py` | — | 011, 103, 016, 042, 048, 073, 098 | Guion de DIgSILENT de las obras de mejora: con `--bibliotecas`, alimentadores y tipos de las tres bibliotecas. |
| `estudios_pf.py` | — | 011, 017, 130, 131, 135, 012, 037 | Guion de DIgSILENT: un estudio en un caso, sin escalado por alimentador y sin aplicar lo que proponen los optimizadores. |
| `capacidad_pf.py` | — | 012 | Guion de DIgSILENT de la capacidad de alojamiento nodo a nodo y conjunta (`ComHostcap`), las curvas PV por alimentador con o sin contingencias… |
| `confiabilidad_pf.py` | — | 012 | Guion de DIgSILENT: con `--aplicar-datos`, el libro de la empresa en la variación «Datos de confiabilidad» (modelos `Sto*` por clase y tipo, equipos… |
| `estudios_entradas_pf.py` | — | 012 | Guion de DIgSILENT que llama `tools/estudios_pf.py`: cortocircuito (`ComShc`) con la Pcc confirmada en una variación temporal y cuasi-dinámica… |
| `protecciones_pf.py` | — | 049 | Guion de DIgSILENT de las protecciones: con `--capacidades`, el inventario de la versión conectada (órdenes `ComShc`, `ComShctrace` y… |
| `transferencia_pf.py` | — | 011, 104, 129, 016 | Guion de DIgSILENT: transferencia de carga entre dos alimentadores por su enlace, paso a paso en los dos sentidos, con la capacidad y el margen del… |
| `transformador_set_pf.py` | — | 017 | Guion de DIgSILENT: cargabilidad del devanado de la SET en el proyecto de transmisión, sin proyecto (el caso tal cual) y con proyecto (la carga de la… |
| `pit_pf.py` | — | 107 | Guion de DIgSILENT del PIT: exporta la red de transmisión al contrato RedArea, con un id único por elemento (su ruta desde la red), los acoplamientos… |
| `variacion_plano_pf.py` | — | 111 | Guion de DIgSILENT del plano de la red: la variación en una variación temporal del conversor dentro de una copia del caso (y del escenario de… |
| `set_nueva_operacion_pf.py` | — | 063 | Diagnóstico físico de conexiones y tipos de una SET existente. |
| `pide_pf.py` | — | 024, 029, 030 | Guion de DIgSILENT: cada año del horizonte del PIDE con la demanda escalada por el `ComLdf`, diagnóstico de la norma con el alimentador y la tensión… |
| `escenarios_pf.py` | — | 024 | Guion de DIgSILENT: escenarios del gemelo en una copia del proyecto (desactivado antes de copiar), demanda escalada y tramos abiertos, resultados y… |
| `digital_twin_snapshot_pf.py` | — | 024, 098 | Guion de DIgSILENT de solo lectura: reabre el proyecto, activa el caso, ejecuta el flujo y devuelve tensiones, cargabilidad, cabeceras, pérdidas,… |
| `escanear_alimentador_pf.py` | — | 028, 098 | Escaneo de solo lectura de alimentadores en DIgSILENT: generadores con su barra, bancos, variaciones y cargas cambiadas a mano. |
| `ubicacion_cargas_pf.py` | — | 017, 124 | Lectura de solo lectura en «Con proyecto» de dónde está conectada hoy cada carga nueva: nodo de media, línea de enlace y GPS, también de las… |
| `transferencia_operador_pf.py` | — | 098 | Transferencias de carga del operador en DIgSILENT: leerlas, desactivarlas mientras se calibra con registro en disco y restituirlas con su evidencia. |
| `verificar_pf.py` | — | 008 | Guion de DIgSILENT: convergencia del proyecto con lo activo. |
| `hojas_diagrama_pf.py` | — | 022 | Hoja de cada diagrama de un proyecto de DIgSILENT frente a sus gráficos y conectores, de solo lectura. |
| `pf_proyectos.py` | — | 005 | Proyectos de la carpeta de importación de DIgSILENT y sus alimentadores. |
| `show_pf_diagram.py` | — | 005 | Abre en DIgSILENT el diagrama de un alimentador. |
| `check_pf_license.py` | — | 005, 011, 012 | Qué módulos de PowerFactory permite la licencia. |
| `run_one_study.py` | — | 005 | Trabajador de PowerFactory: importa y mide, o ejecuta un estudio. |
| `base_scenario.py` | — | 005 | Escenario base (año 0): lo construye, lo hace converger y lo diagnostica. |
| `build_system_grid.py` | — | 034 | Todos los alimentadores en una sola red, importada en PowerFactory. |
| `convertir_grupos_mdb.py` | — | 034, 021 | Varios alimentadores de una base en un DGS, importado y con flujo, a escala real por defecto. |
| `prueba_representacion.py` | — | 034 | Red, cargas y SED del TXT en una hoja de PowerFactory. |
| `run_powerfactory_gate.bat` | — | 034 | Lanza `powerfactory_acceptance.py` con el intérprete de PowerFactory. |
| `pf_servidor.py` | — | 019, 064 | Proceso que mantiene DIgSILENT abierto y atiende las órdenes de los guiones. |
| `pf_cliente.py` | — | 019, 091 | Envía un guion de DIgSILENT al proceso que se queda abierto y reescribe su salida. |
| `restitucion_pf.py` | — | 064 | Órdenes de aceptación de la restitución del servidor: copiar, alterar y fallar, leer y borrar una copia `PRUEBA064_*`. |
| `aceptar_restitucion_pf.py` | — | 064 | Aceptación nativa de la restitución por el camino de la web y el servidor, con evidencia en JSON. |
| `estadistica_ordenes.py` | — | 081 | Resumen de las órdenes de DIgSILENT por guion y día, contraste de hipótesis entre dos versiones y fallos repetidos. |
| `pfd_diagnostico.py` | — | 004, 102, 117 | Importa un `.pfd` con `ComPfdimport` en un proyecto nuevo de la carpeta del conversor, identificado por su huella (reutilizar, versión nueva,… |

### Herramientas: operación, datos y aceptación

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `normativa/fuentes.py` | — | 107 | Comprobación permanente de las fuentes oficiales: cada una contra su sha256 registrado (o su SHA256SUMS.txt) antes de leerla, y el registro sin rutas… |
| `normativa/generar_formatos_217.py` | — | 107 | Transcribe los formatos de la Norma Tarifas (RCD 217-2013-OS/CD) desde sus libros Excel oficiales, con las llamadas a nota separadas del rótulo, a… |
| `normativa/sombreadas_217.py` | — | 107 | Celdas sombreadas («no_llenar») de cada formato de la Norma Tarifas (RCD 217-2013-OS/CD), desde el mapa de rellenos de los libros oficiales… |
| `normativa/generar_coes.py` | — | 107 | Genera el registro de datos del COES (máxima demanda anual y mensual del SEIN, reportes mensuales, convención por defecto y PR-30), las horas punta… |
| `normativa/generar_reconsideraciones.py` | — | 107 | Genera la causa del cambio de los factores de expansión de pérdidas del VAD 2023-2027 por empresa, desde los informes técnicos de las… |
| `sistema_web.py` | — | 022, 025, 039 | Un sistema eléctrico de punta a punta por la web: espera lo que corre, convierte por sistema, importa en DIgSILENT, busca la máxima por barra de SET… |
| `informe_web.py` | — | 017, 105 | Un informe de la spec 017 desde la línea de órdenes: lee el `.plan.json` que la web guardó junto al Word (o un formulario con `--tipo`), lo envía a… |
| `informe_casos_guardados.py` | — | 063 | Reproduce la evaluación Word con tres casos y sus seis flujos guardados por la web. |
| `accept_three_sources.py` | — | 001, 004, 006, 011 | Aceptación universal y separada de MDB, TXT y VNR-GIS hasta ajuste, relectura y estudio nativos. |
| `accept_digital_twin_in191_ta295.py` | — | 024 | Aceptación nativa del caso dorado del gemelo digital: dos lecturas en procesos nuevos, hechos del JSON `--esperado`, comprobaciones y episodio en el… |
| `aceptacion_nativa.py` | — | 044, 045, 048, 049 | Evidencia nativa de las T4: obra aplicada por la web, relecturas en procesos nuevos de `digital_twin_snapshot_pf.py`, retiro, capacidades de… |
| `aceptar_dominio.py` | — | 065 | Preaceptación de fuente, vínculo, caso, evidencia y recursos sin conectar ni modificar el motor nativo. |
| `apply_catalog_to_model.py` | — | 034, 032 | Corrige las características eléctricas del modelo con el catálogo de fichas. |
| `build_input_catalog.py` | — | 034 | Tabla de parámetros eléctricos en `input/` y auditoría de alimentadores. |
| `suggest_line_type_aliases.py` | — | 034 | Propone alias para tipos de línea sin ficha en el catálogo. |
| `compare_schema.py` | — | 034 | Cabeceras de un DGS externo frente a un perfil de esquema. |
| `fidelidad_seleccion.py` | — | 009 | Comprueba que una selección pasa entera del TXT al DGS. |
| `linea_base_dgs.py` | — | 001, 002 | Línea base de DGS para comprobar que una reorganización no cambia nada. |
| `validar_totalidad_vnr.py` | — | 080 | Cruza con consultas propias a la base restaurada las salidas, tramos y SED de una copia VNR-GIS con lo que lista la web. |
| `cabecera_ancha.py` | — | 051 | Herramienta de la spec 051: pasa la medición de cabecera a lo ancho o las máximas mensuales al formato de la calibración, con… |
| `proyeccion_mercado.py` | — | 072 | Compara métodos de proyección anual contra lo ocurrido con el Formato 01. |
| `proyeccion_anual.py` | — | 031 | Pronostica todos los años de un estudio del PIDE con el mejor modelo por métricas: construye el Formato 01 si falta, compite los candidatos y escribe… |
| `costos_cruce.py` | — | 072 | Mide cuánto de una red convertida encuentra costo en el SICODI público, y nombra lo que no. |
| `construir_dataset_pide.py` | — | 024 | Construye el corpus PIDE universal de una empresa con `pide_dataset`. |
| `corpus_redaccion_pide.py` | — | 072 | Revisión humana del corpus PIDE para redactar: lista lo pendiente, registra decisiones con su revisor y exporta lo aprobado sin cifras. |
| `copia_datos.py` | — | 086 | Órdenes de cálculo, copia, verificación, restauración, estado de la copia e identidad de la instalación. |
| `aceptacion_version.py` | — | 100 | Aceptación automática de una versión: recorre en serie la matriz `config/aceptacion/matriz.json` (cada fuente con un alimentador, varios y un… |
| `mudar_carpeta_principal.py` | — | 058 | Muda la carpeta principal del entorno de desarrollo a `ConverterSmartGrid`: plan en seco por defecto, y con `--aplicar` renombra, repara los… |
| `vad_estudio.py` | — | 108 | Guion del estudio VAD sin DIgSILENT ni web: comprueba el estudio con el registro y arma la empresa modelo de un caso (`--caso` o `CSG_VAD_CASO`, con… |
| `vnr_publico_empresa.py` | — | 112, 080 | Baja bajo demanda el paquete VNR-GIS vigente de una empresa de lo publicado por Osinergmin (`--plan` sin bajar nada), a una carpeta fuera del… |
| `benchmark_anonimo.py` | — | 112 | Genera en local el benchmark anonimizado de una red (y de las series del 089) con su manifiesto. |
| `interempresa_loco.py` | — | 112 | Deja una empresa fuera cada vez (`preparar-vnr` saca la red de la copia de SQL Server de un paquete público sin exportar a CYMDIST, con las fichas… |
| `benchmark_escala_web.py` | — | 112 | Mide la escala de la web y su API con redes sintéticas de 10, 50 y 200 alimentadores (carga de la red, p50 y p95 de las peticiones de la pantalla,… |
| `normativa/biblioteca.py` | — | 107 | La biblioteca normativa general desde la consola: listar, añadir una norma a la capa del usuario y exportar el dataset de normas y reglas. |
| `normativa/generar_guia_vnr_232.py` | — | — | 108 T23 (RF-20): la «Guía de Elaboración del Valor Nuevo de Reemplazo de las Instalaciones de Distribución Eléctrica» |

### Herramientas: modelos, asistente y MADRL

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `digital_twin_entrenar.py` | — | 024, 043 | Entrena el oráculo PINN/GNN en su propio proceso (la web lo lanza): reentreno si toca o forzado, promoción por puertas, respaldo en CPU si la GPU… |
| `digital_twin_temporal_entrenar.py` | — | 043, 046, 060 | Trabajador de entrenamiento y recarga GRU, inventario de la medición y competición de pronósticos de cabecera o clientes fijos. |
| `digital_twin_auditar.py` | — | 027 | Informe de la auditoría del dataset del gemelo y del asistente, sin GPU ni DIgSILENT. |
| `digital_twin_buffer.py` | — | 024 | Búfer de episodios desde la consola: listar, mostrar, validar, registrar y rehacer el índice, sin DIgSILENT. |
| `asistente_entrenar.py` | — | 026 | Entrena el Transformer de órdenes y el clasificador de informes en su propio proceso, en la GPU. |
| `asistente_medir_ollama.py` | — | 026 | Mide los modelos locales de Ollama con las mismas órdenes (acierto, segundos, sin respuesta) y guarda el elegido para la web. |
| `asistente_modelo_provisional.py` | — | 085 | Ve, pone y retira un modelo en uso provisional por decisión del usuario, sin aprobarlo ni bajar las puertas. |
| `asistente_embeddings.py` | — | 043, 047 | Ajuste solo con train y evaluación sobre consultas reservadas del recuperador local. |
| `asistente_indice_ampliado.py` | — | 077, 097 | Sin GPU: tamaño de los dos corpus, BM25 con el reparto `corpus` de la 076 y formación de los conjuntos nuevos, sin las preguntas que el corpus ya… |
| `asistente_evaluar_rag.py` | — | 047 | Medición real de la recuperación en la GPU, comprobación del conjunto sin ella con `--solo-conjunto`, calibración de la abstención y su medición… |
| `asistente_qlora.py` | — | 043, 047, 072 | Adaptador del coordinador al ajuste generativo NF4 existente y su corpus sellado. |
| `asistente_destilar.py` | — | 047 | Prepara el currículo, entrena con exclusión GPU y verifica el alumno en proceso nuevo. |
| `asistente_observar.py` | — | 061 | Incorpora y verifica informes locales del aprendizaje sin activar modelos. |
| `asistente_ordenes_reales.py` | — | 068, 047 | Reúne las órdenes reales de las sesiones y del almacén, crea el libro de revisión e importa solo lo que el operador marque. |
| `asistente_comparar_revision.py` | — | 047 | Rol único frente a cuatro roles con los mismos casos declarados: errores, coste y latencia. |
| `preguntas_entregables.py` | — | 076 | Preguntas de metodología y criterios por entregable: verifica fuentes, cifras y nombres, reparte en corpus y sellado, exporta e importa la hoja de… |
| `llm_destilar.py` | — | 047, 060 | Prepara el corpus del alumno LLM a partir de fuentes verificadas de este proyecto. |
| `aceptar_agente.py` | — | 047 | Materializa propuestas, selecciona configuración local y evalúa las 200 sin ejecutar acciones nativas. |
| `construir_dataset_entrenamiento.py` | — | 043, 026 | Construye el dataset de entrenamiento en una carpeta nueva, con las operaciones acabadas de los diarios de los espacios medidas y sin promover, y… |
| `reentrenar_modelos.py` | — | 043, 060, 047 | CLI de coordinación, validación de configuración y rechazo de resultados incompletos. |
| `aprendizaje_continuo.py` | — | 050 | Congela la instantánea, ejecuta el ciclo único con las etapas de `reentrenar_modelos` sobre las copias, muestra sus fases, lo cancela y vuelve al… |
| `preparar_ciclo_aprendizaje.py` | — | 050, 086, 120 | Prepara y valida el plan del ciclo desde el almacén con su matriz por familia (`--solo-preparar`, sin congelar ni entrenar) y genera en una carpeta… |
| `rellenar_identidad_043.py` | — | 086, 120 | Deduce el periodo y el criterio de fijas (de la calibración anterior del proyecto) y la huella del perfil vigente de los episodios del gemelo… |
| `unir_dataset_lenguaje.py` | — | 050 | Une datasets v2 ya construidos en uno solo para las familias de lenguaje, con el particionador existente y sin mover registros de partición. |
| `evaluar_evolutivos.py` | — | 043, 048 | Benchmark analítico calculado de GA, NSGA-II y DE (y los de pymoo si está) con al menos 30 semillas, el mismo presupuesto de evaluaciones reales y la… |
| `reubicar_corpus_llm.py` | — | 047, 065 | Valida o publica una nueva versión custodiada del corpus tras un traslado exacto de datos. |
| `preparar_modelos_ia.py` | — | 043 | Descarga explícita y auditoría de pesos fijados, sin activación. |
| `preparar_upstream_ia.py` | — | 043 | Prepara o verifica clones fijados sin instalar ni ejecutar sus programas. |
| `madrl_entrenar.py` | — | 074 | Entrena el control MaskablePPO del piloto y lo compara con sus referencias. |
| `madrl_obras.py` | — | 074 | Mide la escalera y NSGA-II y la fidelidad del entorno sobre una red del búfer de episodios. |
| `madrl_puerta.py` | — | 074 | Aplica la puerta del aprendizaje en redes no vistas con la separación sellada, escribe la medida y la decisión, y confirma lo que pasa por la web en… |
| `mcp_conversor.py` | — | 077 | Servidor MCP local, solo stdio y solo lectura, con las lecturas del asistente. |
| `evaluacion_final.py` | — | 044 | Consolida la evaluación final de la 1.0 en `docs/EVALUACION_FINAL_1.0.json` y, con `--comprobar`, la relee. |
| `asistente_informes_reales.py` | — | 026 | Anota informes reales etiquetados (Word, PDF con OCR o texto del maestro) para el clasificador, por grupo y sin repetir. |
| `entrenar_alimentadores_gpu.py` | — | 089 | Una red de pronóstico por alimentador, uno tras otro en la GPU, con los libros por argumento. |
| `evaluar_harness.py` | — | 043, 044, 047 | Entrada de consola para el arnés integral de evaluación. |
| `lanzar_pronostico_pide_gpu.py` | — | 031 | El pronóstico del PIDE en la GPU en un paso: comprueba CUDA y memoria y pasa a `proyeccion_anual.py` las redes como candidatos y el quinquenio y… |
| `medir_mejora.py` | — | 087, 071 | Registra una corrida de «Con proyecto» y compara dos métodos o versiones con sus medidas y su contraste. |
| `pronostico_demanda.py` | — | 089 | Dataset y backtest de demanda desde las carpetas que haya. |

### Herramientas: calidad y entrega

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `arquitectura.py` | — | 065, 002 | Guarda AST de capas, ciclos y accesos privados con deuda explícita. |
| `generar_contrato_api.py` | — | 065, 002 | Generación y comprobación determinista del contrato OpenAPI a TypeScript. |
| `estado_specs.py` | — | 033 | Estado de las specs: lee numeración, tareas, estado y citas de las pruebas, y escribe `specs/README.md`. |
| `matriz_operaciones.py` | — | 026 | Matriz de operaciones del asistente derivada del código: tareas, vías directas con recibo y lecturas, con sus pruebas, y los huecos de las specs del… |
| `suite_por_tandas.py` | — | 081 | La suite nocturna en un proceso separado de la web, por tandas. |
| `trazabilidad_candidato.py` | — | 065 | Matriz de requisitos, código, pruebas y ejecuciones vinculadas al candidato. |
| `verificar_candidato.py` | — | 065 | Regresión de un candidato con hashes antes/después, JUnit y matriz de trazabilidad. |
| `fijar_entorno.py` | — | 065 | Cierre reproducible de dependencias para CPython 3.12/Windows. |
| `comprobar_entrega.py` | — | 086 | Comprueba lo que se entregaría según `config/entrega.json`: términos prohibidos (perfiles excluidos, huellas con sal y lista local fuera de git),… |
| `construir_candidato.py` | — | 086 | Arma el candidato: rueda con lo de `config/entrega.json` y comentarios neutralizados, lock con huellas, Python embebido, documentos, SBOM y… |
| `instalar_candidato.py` | — | 086 | Instala, actualiza y vuelve atrás desde un candidato: huellas, sin red, puntero de versión y copia previa de los datos. |
| `build_interactive_architecture.py` | — | 009 | Página distribuible de la arquitectura C4 interactiva desde su fuente en `docs/architecture/`. |
| `verify_architecture_links.py` | — | 009 | Comprueba los enlaces públicos y locales del espacio Structurizr de la arquitectura. |
| `verify_interactive_architecture.mjs` | — | 009 | Comprobación en navegador de la página de la arquitectura C4 interactiva (Node.js). |
| `generar_arquitectura.py` | — | 090 | Genera `docs/ARQUITECTURA_CATALOGO.md` desde el repositorio: ficheros, capas, rutas, tareas del asistente y roles de su equipo. |
| `generar_c4.py` | — | 090 | Pone al día las cifras del C4 de `docs/architecture/` desde el catálogo generado y el Estado de cada spec. |
| `puerta_calidad.py` | — | 102 | Puerta de calidad: los ganchos `pre-commit` y `pre-push` de `.githooks/` y GitHub Actions corren con ella las pruebas del commit, la suite completa… |
| `comparar_suite_repartida.py` | — | 102 | La suite entera con N = 1, 2 y 3 procesos sobre el mismo árbol: memoria privada del árbol de procesos y por fichero, veredicto de cada prueba… |
| `rutas_sin_modelo.py` | — | 002 | Lista las rutas de /api sin modelo de respuesta y escribe la lista de excepciones, que solo baja. |
| `verificar_entrega_integral.py` | — | 065, 086 | Consolida backend, frontend, auditorías y ML sin confundir regresión con aceptación eléctrica u operativa. |

### Interfaz: compilación, cliente de la API y piezas comunes (`frontend/`)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `src/api/esquema.ts` | — | 002, 065 | Contrato TypeScript generado reproduciblemente desde OpenAPI. |
| `src/features/powerfactory/EntradasEstudios.tsx` | — | 012 | Paso 4.2: datos que faltan a los estudios. |
| `src/features/powerfactory/entradasEstudiosLogica.ts` | — | 012 | Lógica de esa tabla: entradas por estudio sin repetir, edición sin mutar, páginas y filas con error. |
| `src/api/entradasEstudios.ts` | — | 012 | Cliente de las entradas de los estudios: estado, leer, guardar y descartar. |
| `test/entradasEstudios.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `src/features/powerfactory/AvisosLibros.tsx` | — | 104 | «Novedades de los libros» en 2.1: avisos de los libros de demanda que la web reconoció sola, con «Dar por visto», y el estado del dataset del… |
| `scripts/build.mjs` | — | 065 | Compila fuera del checkout y publica `dist` completo, conservando el anterior ante cualquier fallo. |
| `scripts/runtime-paths.mjs` | — | 065 | Raíces externas de la compilación, en el volumen de `dist` y fuera del código. |
| `test/reconexion.test.mjs` | — | 086 | Pruebas de los trabajos al reconectar y de la edición en la web. |
| `scripts/README.md` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/buildPreservado.test.mjs` | — | 065 | Pruebas de la compilación y sus rutas, con y sin espacios. |
| `test/ambitoMaxima.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/clientesCatalogo.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/equipoAsistente.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/aprendizaje.test.mjs` | — | 050 | Contrato de consulta sin trabajos y representación de fases, rechazo, versiones y errores de lectura. |
| `test/operacionSet.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/projectBinding.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/solicitudLeida.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `src/api/evolucionFijas.ts` | — | 105 | Cliente tipado de la evolución de los clientes fijos y de la carpeta de archivo. |
| `src/api/mapaCargas.ts` | — | 017, 109, 124 | Cliente tipado del mapa de las cargas nuevas y de su punto de diseño. |
| `src/api/correo.ts` | — | 110 | Cliente tipado del envío de informes por correo: vista previa, confirmar con la firma, recibo y estado, historial y «Llegó»/«No llegó». |
| `src/features/powerfactory/MapaCargas.tsx` | — | 017, 109, 124 | El mapa de las cargas nuevas en la web, con «Actualizar desde DIgSILENT», la tabla de diferencias y «Usar este punto». |
| `src/features/powerfactory/puntosDeDiseno.ts` | — | 017, 109, 124 | Lógica del mapa de las cargas nuevas: la última lectura del proyecto, qué filas se pueden usar y cómo se dice cada diferencia. |
| `src/api/plano.ts` | — | 111 | Cliente del plano de la red con los tipos del contrato generado (`esquema.ts`): vista, variaciones con versión, ajuste, estudio, capas y comparación. |
| `src/features/plano/PlanoRed.tsx` | — | 111 | Pestaña «Plano de la red»: el plano en un marco aislado, buscador por código, inspector, maniobras, tramo nuevo, ajuste, equipo, deshacer y rehacer,… |
| `src/features/plano/InspectorElemento.tsx` | — | 111 | Inspector de un elemento del plano: código de la fuente, dato original, lo deducido con su motivo y la calidad. |
| `src/features/plano/EdicionesPlano.tsx` | — | 111 | Las ediciones de una variación del plano con deshacer, rehacer y confirmar. |
| `src/features/plano/TablaElementos.tsx` | — | 111 | Tabla de elementos del plano, virtualizada y con teclado, enlazada con el plano y el inspector. |
| `src/features/plano/CapasResultados.tsx` | — | 111 | Capas de resultados del plano (unidad, umbral, caso, motor e incumplimientos con texto e icono) y la comparación de dos casos con el aviso de motores… |
| `src/features/plano/mensajesPlano.ts` | — | 111 | Protocolo `postMessage` con la página del plano: esquema cerrado de entrada y salida, solo desde su marco y con su origen opaco. |
| `src/features/plano/textosPlano.ts` | — | 111 | Textos cortos de la pestaña del plano. |
| `src/features/plano/logicaPlano.ts` | — | 111 | Lógica de la pestaña del plano sin reglas eléctricas: elementos, búsqueda por código, teclado, ventana de filas, lectura de vértices y la variación… |
| `src/features/plano/UnifilarRed.tsx` | — | 111 | El unifilar del alimentador junto al plano, con la misma selección y los mismos resultados, sin tocar geometrías ni impedancias. |
| `src/features/plano/logicaUnifilar.ts` | — | 111 | Lógica del unifilar sin reglas eléctricas: coordenadas del dibujo desde el nivel y el orden del servidor, tramos por sus barras y bandas de… |
| `test/plano.test.mjs` | — | 111 | Pruebas de la pestaña del plano sin navegador: tipos del contrato, mensajes, teclado, tabla virtualizada, inspector, capas, comparación, ediciones,… |
| `test/planoEspacio.test.mjs` | — | 111 | Pruebas del plano en el espacio de ingeniería sin navegador: la selección enlazada entre plano, tabla, inspector y capas, el hallazgo con su norma o… |
| `test/planoVariosAlimentadores.test.mjs` | — | 111 | Pruebas del plano con varios alimentadores sin navegador: el principal primero y los añadidos sin repetir, las casillas con filtro, la lista que se… |
| `test/unifilar.test.mjs` | — | 111 | Pruebas del unifilar sin navegador: disposición desde la cabecera, mismos códigos que el plano, la misma selección y los mismos resultados, con el… |
| `test/puntosDeDiseno.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `src/app/ArchivoInformes.tsx` | — | 105 | Tarjeta para ver, poner y quitar la carpeta de archivo de los informes. |
| `src/shared/graficos.ts` | — | 105, 006 | Marcas de eje, tramos de línea y colores de serie de las gráficas SVG, compartidos sin librería de gráficos. |
| `src/features/clientesfijos/EvolucionFijas.tsx` | — | 105 | Pestaña «Evolución de clientes fijos»: alimentadores, rango de meses y trabajo. |
| `src/features/clientesfijos/Tablero.tsx` | — | 105 | Tablero: conciliación, buscador, tarjetas, gráficos, variaciones, cabecera, curva y avisos. |
| `src/features/clientesfijos/Graficos.tsx` | — | 105 | Gráficos de líneas por mes y curva de 15 minutos de un cliente, en SVG. |
| `src/features/clientesfijos/datosTablero.ts` | — | 105 | Lógica del tablero sin React: series, variaciones, avisos, reducción de la curva y buscador difuso. |
| `scripts/fronteras.mjs` | — | 002 | Regla AST y resolución TypeScript de fronteras. |
| `src/api/asistenteAceptacion.ts` | — | 047, 002 | Contrato web de propuestas, observaciones humanas, evaluación y aceptación del agente. |
| `src/api/client.ts` | — | 001, 011, 021, 022, 025, 039, 061 | Cliente tipado de la API.; conversión por sistema eléctrico y máxima por barra |
| `src/api/fuentes.ts` | — | 109 | La API de las fuentes de la empresa del espacio y de su red convertida. |
| `src/api/normativa.ts` | — | 107 | Cliente de la biblioteca normativa (listar, reglas, agregar) y el filtro por acto o título. |
| `src/api/matrizEstudios.ts` | — | 100 | Cliente de la matriz estudio × motor (`GET /api/estudios/matriz`) con sus tipos. |
| `src/api/nube.ts` | — | 109 | Cliente de la nube: cuentas, conectar y desconectar, selector, importar, versiones, publicar, compartir y recibos. |
| `src/api/pit.ts` | — | 107 | API del PIT (107 T13) con los tipos del contrato: áreas, motores, subida de entradas, diagnóstico y expediente como trabajos, observaciones y la… |
| `src/api/reconexion.ts` | — | 086 | Pone al día los trabajos de la pestaña al volver a conectar, y lista los interrumpidos por ver. |
| `src/api/types.ts` | — | 001, 011, 021, 025, 037, 039, 041, 061 | Tipos de las respuestas de la API. |
| `src/api/vad.ts` | — | 108 | API del estudio del VAD (108 T29) con los tipos del contrato: estudios, crear, detalle, armar con el caso, observaciones y su respuesta, e Informe… |
| `src/api/vnr.ts` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `src/app/AcercaDe.tsx` | — | 086 | La versión de la cabecera abre sus notas y el diagnóstico de la instalación. |
| `src/app/App.tsx` | — | 001, 008, 061, 091, 109 | Marco de la página: paneles, pestañas, resúmenes de trabajos. |
| `src/app/AvisosDatos.tsx` | — | 086 | Avisos generales de arriba: copia vieja y ficheros no disponibles en una línea, espacio dañado con su botón de restaurar, y los avisos de trabajo sin… |
| `src/app/CuentasNube.tsx` | — | 109 | Tarjeta de las cuentas de Google Drive y OneDrive del espacio: conectar, desconectar, la vuelta del proveedor y, sin registro, «Sin cuenta conectada». |
| `src/app/InstalacionesPowerFactory.tsx` | — | 103 | Las PowerFactory encontradas en la máquina, la que se usa y la elección del operador, desde la píldora de la cabecera. |
| `src/app/JobBar.tsx` | — | 001 | Barra de trabajos en curso. |
| `src/app/LogPanel.tsx` | — | 001 | Registro. |
| `src/app/NubeEnEntradas.tsx` | — | 109 | Da a cada entrada los orígenes de la nube con cuenta y trae la copia fija para que entre por su propia subida. |
| `src/app/Pestanas.tsx` | — | 086, 106 | Las pestañas de los módulos con el patrón de WAI-ARIA (lista, pestaña y panel enlazados) y su manejo por teclado. |
| `src/app/main.tsx` | — | 001 | Arranque de React. |
| `src/app/teclado.ts` | — | 086, 106 | El teclado de la web: flechas, Inicio y Fin en pestañas y grupos de opciones, y el separador del Registro con teclado y pulsación. |
| `src/shared/AvisosTrabajo.tsx` | — | 086 | El aviso de un trabajo interrumpido, fallido o cancelado en su paso, con «Reintentar», «Ver su registro» y «Dar por visto». |
| `src/shared/ElegirFuente.tsx` | — | 109 | Elegir el libro que ya cargó la empresa del espacio (la vigente de su clase) o subir otro, que queda para todos los módulos. |
| `src/shared/MarcaBeta.tsx` | — | 086 | La marca y el aviso de una función en beta. |
| `src/shared/MarcaValidacion.tsx` | — | 100 | La matriz estudio × motor del servidor, pedida una vez por página, y la marca «Sin validar» o «No disponible» junto a un estudio. |
| `src/shared/matrizEstudios.ts` | — | 100 | La celda de un estudio con su motor, su marca (aviso o apagado con su motivo) y el estudio y el motor de cada pestaña de módulo. |
| `src/shared/PfWarning.tsx` | — | 002, 008 | Aviso de disponibilidad de PowerFactory común a conversión y operación. |
| `src/shared/SinPantallaEnBlanco.tsx` | — | 042 | Si una pantalla falla al dibujarse, lo dice y deja recargar |
| `src/shared/accionesOperador.tsx` | — | 002, 070 | El contrato de lo que la tarjeta de operador del asistente usa de la nube y del correo. |
| `src/shared/carriles.ts` | — | 080 | El nombre que ve el operador de cada carril de trabajo del servidor («Motor», «DIgSILENT», «Red»…), uno por carril. |
| `src/shared/context.tsx` | — | 001 | Contexto común de la aplicación. |
| `src/shared/direcciones.ts` | — | 109, 110 | Separa y limpia las direcciones de correo que escribe el operador, sin repetidas, y nombra las mal escritas. |
| `src/shared/edicion.ts` | — | 086 | Pregunta a `/api/health` qué edición corre y qué funciones están en beta. |
| `src/shared/formato.ts` | — | 002, 001 | Formateadores numéricos y tamaños compartidos, extraídos sin cambiar su cuerpo. |
| `src/shared/nubeEntradas.ts` | — | 109 | Lo que el campo único y el «Guardar en…» saben de la nube. |
| `src/shared/origenes.ts` | — | 109 | El campo único de cada entrada: los orígenes (el equipo siempre. |
| `src/shared/pasoDeTrabajo.ts` | — | 086 | Tabla de cada tipo de trabajo del servidor al paso de la web que lo lanza. |
| `src/shared/projectBinding.ts` | — | 005, 018, 034 | Vínculo del proyecto de DIgSILENT con su ejecución de origen: separa los bloqueos de las advertencias por cambios manuales. |
| `src/shared/styles.css` | — | 001, 021 | Tokens y estilos, modo claro y oscuro. |
| `src/shared/ui.tsx` | — | 001 | Piezas comunes: modal, avisos, casillas, ficheros. |
| `src/shared/useWorkspace.ts` | — | 001, 059 | Espacio de trabajo, Registro en vivo y trabajos por WebSocket. |

### Interfaz: asistente

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `src/features/asistente/Aprendizaje.tsx` | — | 050 | Consulta de las siete fases del ciclo común, versiones y bloqueos. |
| `src/features/asistente/Asistente.tsx` | — | 026, 043, 061 | Pestaña «Asistente»: consola de órdenes, plan con datos, pasos, lo que falta, dudas y razonamiento, confirmar y ejecutar, corregir la tarea,… |
| `src/features/asistente/EquipoAsistente.tsx` | — | 065 | Roles, permisos y revisión de propuestas en la consola del asistente. |
| `src/features/asistente/MejorasPendientes.tsx` | — | 026 | Las mejoras que propone el asistente, sin decisión: su motivo, el resultado de su suite en palabras y las tres decisiones del operador, con… |
| `src/features/asistente/MonitorAgente.tsx` | — | 061, 062 | Monitor del asistente conectado al contexto WebSocket, etapas, operaciones, evidencia real y retención diaria. |
| `src/features/asistente/TarjetaOperador.tsx` | — | 070 | La tarjeta que el asistente deja en su panel: el correo con «Confirmar y enviar» (y su recibo), publicar, compartir, importar y conectar con las… |
| `src/features/asistente/estadoEquipoAsistente.ts` | — | 065, 047, 002 | Cliente tipado del estado y las operaciones del equipo del asistente (permisos, acciones y revisiones), sin dependencia de otros flujos. |
| `src/features/asistente/tarjetaOperadorLogica.ts` | — | 070 | Las cinco tarjetas posibles, cada una de su tarea y con su forma (borrador y firma). |

### Interfaz: conversión y perfil de la empresa

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `src/features/conversion/DescargaZip.tsx` | — | 065 | Descarga ZIP preparada como trabajo con progreso y cancelación. |
| `src/features/conversion/FeedersPanel.tsx` | — | 001, 022, 091 | Tabla de alimentadores y conversión.; conversión por sistema eléctrico con su zonal, aparte de unir, y el tipo de cada DGS unido |
| `src/features/conversion/InputsPanel.tsx` | — | 001 | Entrada de datos: TXT, MDB y VNR-GIS. |
| `src/features/conversion/Modules.tsx` | — | 001 | Pestañas de resultados, catálogo y sistema completo. |
| `src/features/conversion/OptionsPanel.tsx` | — | 001 | Opciones de conversión. |
| `src/features/conversion/PerfilEmpresa.tsx` | — | 086 | Carga y validación del perfil de la empresa desde la web. |
| `src/features/conversion/ReconstructionPanel.tsx` | — | 001 | Diagnóstico y reconstrucción. |

### Interfaz: módulos regulatorios (PIT, VAD, VNR y biblioteca normativa)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `src/features/normativa/BibliotecaNormativa.tsx` | — | 107 | Pestaña «Biblioteca normativa»: cada norma con lo que obliga en la fecha, sus reglas con la cita y la subida de una norma. |
| `src/features/pit/EstudioPit.tsx` | — | 107 | Pestaña «Estudio PIT» (107 T13): área, años, periodo y motor. |
| `src/features/vad/EstudioVad.tsx` | — | 108 | Pestaña «Estudio VAD» (108 T29): crear o elegir el estudio, subir el caso y armar la empresa modelo con el estado de cada sistema, registrar y… |
| `src/features/vnr/EstudioVnr.tsx` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |

### Interfaz: nube y correo

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `src/features/nube/ElegirDeLaNube.tsx` | — | 109 | Ventana para elegir ficheros de la nube y que entren en una casilla o un libro, como una subida. |
| `src/features/nube/PublicarExpediente.tsx` | — | 109 | Publicar el expediente en una carpeta de la nube y compartirlo: quién tendrá acceso, aviso del enlace público y bloqueo por datos crudos. |
| `src/features/nube/VersionesNuevas.tsx` | — | 109 | Los ficheros vinculados con su estado, comprobar versiones, traer y comparar la nueva y usarla con confirmación. |
| `src/features/nube/logica.ts` | — | 109 | Lo que deciden las pantallas de la nube: la vuelta del proveedor, el mensaje del selector, el destino de lo importado, el estado de un vínculo y… |
| `src/features/nube/useSelector.ts` | — | 109 | Abre el selector del proveedor en una ventana aparte y acepta solo sus ids del propio origen. |

### Interfaz: «Cargas en DIgSILENT», estudios, obras e informes

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `src/features/powerfactory/AjusteCabecera.tsx` | — | 006, 008, 020, 021, 025, 035, 039, 041, 091 | Paso 2.4: ajuste a la máxima de uno o varios alimentadores. |
| `src/features/powerfactory/CargasTab.tsx` | — | 004, 005, 008, 011, 016, 042, 091 | Pestaña «Cargas en DIgSILENT» en cuatro pasos. |
| `src/features/powerfactory/CurvaCabecera.tsx` | — | 006, 021 | Paso 2.4: curva del registro del medidor de cabecera, con el mes de la máxima sombreado y zoom por tramo. |
| `src/features/powerfactory/DatosEmpresaPF.tsx` | — | 012 | Paso 4.2: libro de la empresa del proyecto (subir, plantilla, lo que trae, aplicar en DIgSILENT). |
| `src/features/powerfactory/DemandaMedida.tsx` | — | 004, 008, 013, 021, 022, 025, 035, 038, 039, 091 | Paso 2: libros de medición, máxima de cabecera (con la central térmica de un alimentador, en el mes de análisis o en un instante coincidente) y… |
| `src/features/powerfactory/DeshacerLotes.tsx` | — | 007 | Deshacer un lote de cargas ya aplicado en DIgSILENT: se ofrece en los lotes aplicados del espacio, confirma lo que se deshace y corre como trabajo de… |
| `src/features/powerfactory/EnviarInforme.tsx` | — | 110 | Botón «Enviar por correo» y su ventana: cuenta, para, asunto, vista previa con avisos de validez y de contactos, confirmar, estado e historial. |
| `src/features/powerfactory/EstudiosPF.tsx` | — | 011, 012, 037, 049, 091 | Paso 4.2: estudios sobre la red calibrada, límites y resultados. |
| `src/features/powerfactory/GemeloPIDE.tsx` | — | 024, 072 | Paso 5 de «Cargas en DIgSILENT»: planificar con el PIDE (CAPEX opcional, aplicar solas las obras que funcionan), tabla de obras con prioridad, estado… |
| `src/features/powerfactory/GuionesPF.tsx` | — | 011 | Paso 4.2: guiones DPL y Python del operador, sus parámetros y su salida por caso. |
| `src/features/powerfactory/ImportarPfd.tsx` | — | 004, 117, 118 | Paso 1: subir un `.pfd`, importarlo en la carpeta de la empresa como trabajo de DIgSILENT y su resumen con los avisos agrupados. |
| `src/features/powerfactory/InformesPF.tsx` | — | 017, 100, 102, 104, 125, 110 | Paso 4.4: informe de estudio eléctrico y de factibilidad y punto de diseño con lo ya guardado por la web (flujos de 4.2, obras, cargas nuevas… |
| `src/features/powerfactory/ObrasPF.tsx` | — | 011, 016 | Paso 4.1: formulario de obras de mejora (también enlace, migración desde un nodo y sección de toda la troncal), bibliotecas de tipos, obras… |
| `src/features/powerfactory/OperacionSet.tsx` | — | 063 | Panel para diagnosticar, evaluar o reforzar una SET existente, sin recrearla. |
| `src/features/powerfactory/PerfilTension.tsx` | — | 094 | Perfil de tensión que deja la calibración: barras de media por su distancia a la cabecera, la troncal y el límite del perfil de la empresa. |
| `src/features/powerfactory/TipoDeAnalisis.tsx` | — | 072 | El recuadro del tipo de análisis en la pestaña de su módulo (corto plazo, PIDE o planeamiento de largo plazo), fijo, con su horizonte, obras,… |
| `src/features/powerfactory/guardadoOrdenado.ts` | — | 072 | El guardado del proyecto y los alimentadores del espacio con PUT /options: al momento en pantalla, y después solo la respuesta o el fallo del último… |
| `src/features/powerfactory/TransferenciaPF.tsx` | — | 011, 104, 123 | Paso 4.3: transferencia de carga entre dos alimentadores. |
| `src/features/powerfactory/alternativas.ts` | — | 042 | Las palabras y el orden de las alternativas por alimentador, las mismas del informe |
| `src/features/powerfactory/centralesDeSet.ts` | — | 086, 122 | La SET de cada central térmica del libro en la máxima por barra: las SET de los alimentadores analizados primero, el tramo de un alimentador de la… |
| `src/features/powerfactory/ambitoMaxima.ts` | — | 086, 126 | El ámbito de la máxima de 2.2 con su variante no coincidente (alimentadores, SET o sistema eléctrico, cada uno con la máxima de cada alimentador) y… |
| `src/features/powerfactory/clientesCatalogo.ts` | — | 004, 008, 025, 091 | Estado del catálogo mensual de clientes: un solo libro activo e índice vigente antes de cruzar. |
| `src/features/powerfactory/enviarInformeLogica.ts` | — | 110 | Lo que decide la ventana de envío: cuentas, motivo sin cuenta, petición de la vista previa, anulación al cambiar un campo y textos de estado. |
| `src/features/powerfactory/formularioOperacionSet.ts` | — | 063 | Valida el formulario de la operación de una SET y arma el cuerpo de la orden. |
| `src/features/powerfactory/obrasEstadoActual.ts` | — | 086 | Cuándo la web ofrece obras para el estado actual sin cargas nuevas, y cómo resume su resultado. |
| `src/features/powerfactory/solicitudLeida.ts` | — | 063 | Acumula por documento lo leído de los PDF del solicitante y detecta un alimentador distinto del de la carga. |
| `src/features/powerfactory/tensionFuente.ts` | — | 021 | El campo «Tensión en la fuente» de 2.4: relleno con la tensión medida en pu, su nota de dónde sale y lo que tocó el operador. |
| `src/features/powerfactory/tablaMaxima.ts` | — | 004, 116, 028 | Cómo se lee la tabla de la máxima de 2.2: su ámbito, el instante común, si la máxima propia va de referencia, la fila fuera del instante y el factor… |
| `src/features/powerfactory/ubicacionCarga.ts` | — | 004 | La ubicación de una carga nueva en la web: el rechazo con su propuesta junto al formulario, el nodo más cercano y la línea de conexión. |

### Interfaz: pruebas de `frontend/test/`

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `test/accesibilidad.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/alternativas.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/asistenteAprendido.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/avisosEnSuPaso.test.mjs` | — | 086 | Pruebas de los avisos de trabajo en su paso: tabla completa de los `kind` del servidor, render de cada paso, resolución automática y lo que queda… |
| `test/carriles.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/contratoNubeCorreo.test.mjs` | — | 109, 110 | Pruebas de que los clientes de la nube y del correo usan el contrato generado: sin tipos provisionales ni interfaces propias, modelos que existen y… |
| `test/copiaPrevia.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/comun.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/entorno.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/f01_vnr.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/f03_planificacion.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/f04_asistente.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/f05_selector_unico.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/f06_vad_linea.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/f07_nube_correo.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/f10_libros_nuevos.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/playwright.config.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/sin_omitidas.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/teclado.e2e.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/todos.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/e2e/vnr_sintetico.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/edicionTodoActivo.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/enviarInforme.test.mjs` | — | 110 | Pruebas de la ventana «Enviar por correo»: sin cuenta, vista previa, avisos, confirmar sin doble envío e historial. |
| `test/estudiosCasos.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/matrizEstudios.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/evolucionFijas.test.mjs` | — | 105 | Lógica y render real del tablero de la evolución de los clientes fijos y su buscador. |
| `test/fondoMapa.test.mjs` | — | 086 | Pruebas del interruptor «Fondo de mapa»: se cambia, se bloquea si lo fija la variable y explica que vale para las conversiones siguientes. |
| `test/fronteras.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/letraFija.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/librosFondo.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/modulosPlaneamiento.test.mjs` | — | 072 | Pruebas de las pestañas «Corto plazo», «PIDE» y «Largo plazo» sin navegador: son `CargasTab` con su módulo, la matriz de cobertura por pestaña… |
| `test/normativaPanel.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/nube.test.mjs` | — | 109 | Pruebas de la tarjeta de cuentas en la nube, del selector, de la importación, de las versiones y de compartir, pintadas con React. |
| `test/obrasEstadoActual.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/pideAnual.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/pitPanel.test.mjs` | — | 107 | Pruebas de la pestaña del PIT sin navegador: matriz de cobertura de las rutas /api/pit (llamada, control y prueba del servidor), los cuatro libros,… |
| `test/relecturaServidor.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/retomarEspacio.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/selectorUnico.test.mjs` | — | 109 | Pruebas del campo único por entrada, del filtro de tipo y de guardar una salida en el equipo o en la nube. |
| `test/superficies.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/tarjetaOperador.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/tensionFuente.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/tablaMaxima.test.mjs` | — | 004, 112, 116, 028 | Pruebas de la tabla de la máxima: el instante común y la propia de referencia en el coincidente, la propia en el no coincidente, la tabla de otro… |
| `test/centralesDeSet.test.mjs` | — | 086, 122 | Pruebas de la SET de cada central térmica en la máxima por barra: primero las SET de los analizados, el tramo de la SET elegida y por qué una central… |
| `test/maximaNoCoincidente.test.mjs` | — | 086, 126 | Pruebas del instante de la calibración: la máxima de cada alimentador (no coincidente) en los tres análisis, el valor por defecto sin cambiar y el… |
| `test/etiquetasMaxima.test.mjs` | — | 086, 123 | Pruebas de las etiquetas de las máximas en la gráfica de curvas: 200 repartos sorteados (la semilla en el registro) sin taparse ni salir del gráfico. |
| `test/tiposDeAnalisis.test.mjs` | — | 072 | Selector explícito, ficha, pasos de cada tipo, aviso del PIDE sin corto plazo y cuerpo de «Planificar» por tipo. |
| `test/guardadoOrdenado.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/ubicacionCarga.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/vadPanel.test.mjs` | — | 108 | Pruebas de la pestaña del VAD sin navegador: matriz de cobertura de las rutas del VAD (llamada, control y prueba del servidor), el panel con un… |
| `test/sinPluralEntreParentesis.test.mjs` | — | 086, 110 | Ningún texto de la interfaz con «palabra(s)» o «palabra(es)»: recorre los literales de `frontend/src` con el analizador de TypeScript (deja fuera… |

### Configuración, dependencias y entrega

| Fichero |
| --- |
| `.githooks/post-commit` |
| `.githooks/post-merge` |
| `.githooks/pre-commit` |
| `.githooks/pre-push` |
| `.githooks/python.sh` |
| `.githooks/regenerar.sh` |
| `config/aceptacion/matriz.json` |
| `config/archivo.example.json` |
| `config/casos_de_prueba/sitios.json` |
| `config/costes_referenciales.example.json` |
| `config/demanda_medida_alias.example.json` |
| `config/entrega.json` |
| `config/fichas/transformadores_sed.json` |
| `config/licencias_terceros/APACHE-2.0_Qwen3.txt` |
| `config/licencias_terceros/MICROSOFT_VCRUNTIME.txt` |
| `config/licencias_terceros/MIT_Ollama.txt` |
| `config/licencias_terceros/MIT_ggml_llama.cpp.txt` |
| `config/licencias_terceros/MIT_multilingual-e5-base.txt` |
| `config/licencias_terceros/NVIDIA_CUDA_EULA.txt` |
| `config/licencias_terceros/NVIDIA_cuDNN_SLA.txt` |
| `config/licencias_terceros/manifest.json` |
| `config/line_type_aliases.example.json` |
| `config/modulos/vinculos.json` |
| `config/modulos_permitidos.example.json` |
| `config/normativa/catalogo_tecnico.json` |
| `config/normativa/coes_maxima_demanda_sein.json` |
| `config/normativa/dl_1221_2015.json` |
| `config/normativa/dl_25844_lce.json` |
| `config/normativa/ds_006_2026_jus.json` |
| `config/normativa/ds_009_99_em.json` |
| `config/normativa/ds_028_2021_em.json` |
| `config/normativa/entradas/vad_2023_2027_reconsideraciones.entrada.json` |
| `config/normativa/it_565_2024_cuadros.json` |
| `config/normativa/lce_arts_71_77.json` |
| `config/normativa/medida_clase_precision.json` |
| `config/normativa/ntcse.json` |
| `config/normativa/ntcser.json` |
| `config/normativa/pide_dl_1208.json` |
| `config/normativa/rcd_018_2018.json` |
| `config/normativa/rcd_018_2018_diagnostico.json` |
| `config/normativa/rcd_074_2004.json` |
| `config/normativa/rcd_094_2022.json` |
| `config/normativa/rcd_112_2024.json` |
| `config/normativa/rcd_149_2024.json` |
| `config/normativa/rcd_163_2021.json` |
| `config/normativa/rcd_186_189_2026.json` |
| `config/normativa/rcd_199_2026.json` |
| `config/normativa/rcd_217_2013.json` |
| `config/normativa/rcd_217_2013_diagnostico.json` |
| `config/normativa/rcd_217_2013_formatos.json` |
| `config/normativa/rcd_217_2013_plan.json` |
| `config/normativa/rcd_217_2013_transitorias.json` |
| `config/normativa/rcd_218_2020_manual_costos.json` |
| `config/normativa/rcd_232_2017.json` |
| `config/normativa/rcd_242_2021.json` |
| `config/normativa/rm_129_2009_mem_dm.json` |
| `config/normativa/vad_2023_2027_perdidas.json` |
| `config/normativa/vad_2023_2027_reconsideraciones.json` |
| `config/normativa/vad_2026_2030_perdidas.json` |
| `config/nube.example.json` |
| `config/perfil_empresa.example.json` |
| `config/perfiles/electro_dunas.estructura.json` |
| `config/perfiles/electro_dunas.json` |
| `config/perfiles/ficticia.json` |
| `config/perfiles/plantilla.json` |
| `config/pide_universal_2017.json` |
| `config/pit_mapeo_formatos.json` |
| `config/pregunta_entregada/CONJUNTO_ABSTENCION_ENTREGA.json` |
| `config/suite_completa.example.json` |
| `config/terminos_huellas.json` |
| `config/vad/anexo2_formatos.json` |
| `config/vad/anexo5_urbano.json` |
| `config/vad/anexo6_rural.json` |
| `config/vad/anexo7_coym.json` |
| `config/vad/anexo9_estructura.json` |
| `config/vad/ds_018_2020_em_rlger.json` |
| `config/vad/tdr_vad_2026.json` |
| `config/vad/tdr_vad_2026_anexo4.json` |
| `config/vad/tdr_vad_2026_calidad.json` |
| `config/vad/tdr_vad_2026_requisitos.json` |
| `config/vad/tdr_vad_2026_resultados.json` |
| `config/vnr/anexo2_codigos.json` |
| `config/vnr/anexo5_formatos.json` |
| `config/vnr/anexo6_equivalencias.json` |
| `config/vnr/codigos_empresa_vnr.json` |
| `config/vnr_dgs_profile.json` |
| `config/vnr_settings.example.yaml` |
| `config/vulnerabilidades_justificadas.json` |
| `constraints-python312-win.txt` |
| `instalador/ComplementoIA.iss` |
| `instalador/ConverterSmartGrid.iss` |
| `requirements-complemento-ia.txt` |
| `requirements-drivers.txt` |
| `requirements-madrl.txt` |
| `requirements-mcp.txt` |
| `requirements-motores.txt` |
| `requirements-nucleo.lock` |
| `requirements.txt` |
| `run_gui.bat` |
