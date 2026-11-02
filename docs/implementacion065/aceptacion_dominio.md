# Preaceptación y aceptación del dominio — M9

Responsable: aceptacion_dominio. Candidato: `codex/mejoras-auditoria-integral`,
base `f5c9c89d`. Lectura y pruebas del 2026-11-02. Evidencia externa:
`D:/converter/auditorias/ConversorIGEA_DGS_20261102/implementacion065/aceptacion_dominio/`.
No se abrió, cerró ni conectó PowerFactory en esta fase. Los GET de 8765 pertenecen
al main de otra sesión; no acreditan despliegue del candidato.

## Herramienta reutilizable y límites

`tools/aceptar_dominio.py` implementa 065:RF-21: reabre manifiesto, archivos fuente,
vínculo y evidencias del caso; compara el contexto solicitado y exige identidad
exacta de ejecución para un replay. Consume `load_source_run`, `fingerprint`,
`require_project_binding`, el nombre canónico del registro y la custodia existentes.
El registro compartido aislado conserva su precedencia. No crea bindings, proyectos,
copias ni sesiones nativas. Solo imprime el resultado salvo `--output-json` explícito,
que exige un archivo nuevo fuera del checkout. `--requiere-ml` consulta el control
de memoria común sin cargar pesos. `listo_diagnostico` permite preparar una ejecución;
`aceptacion_electrica` permanece siempre falso.

La API operativa vigente permite otra ejecución de modalidad/huella iguales y emite
un aviso `PROJECT_BINDING_SOURCE_RUN_CHANGED`. El replay exige el ID exacto por su
proveniencia; esta herramienta no modifica esa política general. La guía histórica
de aceptación de memoria es más estricta y no se usa para reformar la API.

Entrada de evidencias: lista JSON con `custodia={ruta,sha256,bytes,localizador}` y
`contexto={project,caso,periodo,source_tuple:[run,mode,fingerprint]}`. El contexto es
la atribución explícita del operador que prepara el replay; sellar un documento no
demuestra por sí solo que sus resultados eléctricos sean válidos.

Pruebas enfocadas: **40 aprobadas, cero omisiones**, incluyendo los contratos de
binding existentes; `regresion_final.xml`. Negativas nuevas: bytes modificados, run distinto,
slots repetidos, precedencia del registro, vínculo alterado, artefacto ausente,
período ajeno y RAM insuficiente. La primera
ejecución conserva el error por módulo aún inexistente (`rojo.xml`). Ruff de los dos
archivos nuevos pasó. La suite completa y los motores reales quedan separados.

## Inventario y clon revisable

Se leyeron 24 workspaces y 203 rutas de artefactos seleccionadas. El inventario
de tareas encontró **30 casillas nativas anteriores a 065**, más su T12 agregadora.
`tareas_nativas_abiertas.json` conserva texto y ruta; `bindings_compactos.json`
conserva las identidades por workspace. Estos inventarios no cierran tareas.

| Caso | Workspace y ejecución fuente exacta | Proyecto y modalidad |
| --- | --- | --- |
| A, INKA/SM218 | `374e622963ae496e` / `20261029T163302-44904af5f1ed` | `20261029-163414_IGEA_SM218`, TXT |
| B, NA203–NA205/COPARA | `5f11283a33c94ea5` / `20261029T120943-7979902c8ba6` | `20261029-121129_IGEA_NA203_NA205`, TXT |
| C, CA101–PE104 | `5f11283a33c94ea5` / `20261019T091959-d48b94364672` | `20261019-092142_IGEA_CA101_PE104`, TXT |
| D, PA217 | `5f11283a33c94ea5` / `20261029T075656-8d7c41066e13` | `20261029-075804_IGEA_PA217`, TXT |
| E, TM105 | `5f11283a33c94ea5` / `20261025T222907-188f45cc53b5` | `20261025-222951_IGEA_TM105`, MDB |
| F, SI213/PN107 | `5f11283a33c94ea5` / `20261016T092722-e8e14c73784b` | `20261016-093124_IGEA_SI213` / `20261016-095754_IGEA_PN107`, MDB |
| G, Electro Oriente | `db9fa4d6c0ad4945` / `20261101T094918-9d614f5934f3` | `20261101-095744_CSG_NJA202` / `20261101-101524_CSG_0205`, VNR |

A y B comparten huella TXT `c3df248bfe29a734a1c34139cc1259d9962a223ca574f45c4cf45c152198c708`,
pero conservan identidades distintas. G usa huella
`66d8d93d9043694c3f4c3f59cfcc986bb9a77bfebe9c0848fd902a700f22b59f`;
no se combina con Electro Dunas. Los períodos de calibración se toman del informe
correspondiente, nunca de la fecha del TXT o del nombre del proyecto.

El run de A en 374e contiene 34 archivos, **33 782 606 bytes**, y `workspace.json`
2 292 979 bytes: aproximadamente 34,4 MiB para copiar ambos. Sus tres fuentes
fueron rehasheadas: RED_231026.txt 10 073 039 bytes; CARGA_231026.txt 1 383 321;
260927_Equipo.txt 23 797. Los SHA coinciden con el manifiesto de 1393 bytes.
`sm218_clon_preflight.json` conserva detalle. Los bindings del workspace están vacíos;
el registro `output/web/vinculos_pf.json` es la autoridad compartida. Debe copiarse
a la raíz web candidata aislada, manteniendo el ID y el manifiesto del run. No se
adopta ni renombra un proyecto ajeno. No se escriben rutas ni metadatos en main.

Para clonar: usar destino nuevo externo, copiar `workspace.json`, el run exacto y
el registro, comprobar todos los SHA y tamaño antes/después, conservar originales
y modificar únicamente las rutas runtime de la copia necesarias para su raíz.
No se copia todo output ni se trae otra fuente para llenar una casilla.
La copia autorizada se publicó en `implementacion065/candidato_http/datos/374e622963ae496e`
y su registro aislado: 36 archivos, 69 139 179 bytes, con SHA antes/después/copia
idénticos en todos. `clon_sm218_manifiesto.json` conserva la evidencia, sin hardlinks.
La ejecución real de `aceptar_dominio.py` contra la copia devolvió
`LISTO_DIAGNOSTICO`, `aceptacion_electrica=false`, cero operaciones nativas y
licencia no verificada (`sm218_preaceptacion_real.json`). El informe custodiado
de calibración identifica la máxima de 2026-10-23 11:30, período 2026-10, medición
de fuente común única ante dos troncales; no se eligió una rama parcial.

## Evidencia histórica reabierta y operaciones necesarias

`evidencia_nativa_historica_reabierta.json` conserva rutas, SHA y tamaños de cuatro
informes reabiertos. INKA tiene los tres estados guardados: Sin proyecto converge
con 3 barras MT fuera de límite y cargabilidad 130,823%; Cargas nuevas converge con
70 MT fuera y 161,801%; Con proyecto converge con MT dentro, 4 BT fuera y 95,295%.
Dos barras sin resultado se declaran explícitamente. La actualización documental
del día 2 dice que no volvió a ejecutar el modelo. No acredita el botón de 4.4 ni
cumplimiento de toda la red. El PDF/documento queda conservado.

COPARA tiene evidencia más reciente que el fallo de calibración del día 29:
`set_nueva_operacion_87ace2d82986.json`, 28 517 574 bytes, SHA
`2a637163184e777597749b00a3e75957bfdc0d79fd60c6486284917565430fa6`,
acción diagnóstico, aceptada, sin variaciones nuevas y sin errores de restauración.
El informe verificado acredita Con proyecto equilibrado y desequilibrado,
0,964209–1,049746 p.u., máximo 98,5597%, 35 cargas y térmica fuera de servicio.
Sin proyecto alcanza 0,901 p.u.; Cargas nuevas completo no converge. Su aceptación
histórica es específica de 063:T24 y esa configuración; no prueba óptimo global,
causalidad de pérdidas ni cierre automático de 042/048/052.

La aceptación histórica 064 sobre copia de SM218 confirma fotografía/readback y
borrado de la copia. Reutilizarla exige ejecutar el candidato por el mismo arnés;
no basta citar la evidencia anterior. Copiar o aplicar cambios queda reservado a
la etapa autorizada y a la exclusión del motor compartida.

| Tarea abierta | Caso/fuente y período exigido | Operación/evidencia pendiente |
| --- | --- | --- |
| 005:T12 | dos DGS de una misma fuente declarada; sin período eléctrico | nombres repetidos, subcarpeta, inventario y confirmación del usuario |
| 007:T11 | F/SI213; período de su ajuste | copia exclusiva, variación por carga, nodo cercano y base restaurada |
| 008:T7 | C, instante del ajuste | tres pasos web e inventario nativo final |
| 011:T19 | C u otro par calibrado declarado | carga/obra por clase, tres casos y Sin proyecto intacto |
| 012:T13 | dos alimentadores calibrados + libro empresarial propio | índices/ENS, reconectador, banco, capacidad y PV nativos |
| 013:T7 | C/CA101–PE104, mismo instante explícito | transferencia, SED, descargable y readback |
| 016:T18 | F/PN107, ajuste de referencia | carga con/sin cable según distancia y lectura final |
| 017:T13 | CA101, fuente de CA101 13 por resolver | informe desde cero con bancos y aprobación documental usuario |
| 017:T14 | carga individual y su fuente; AD08 V4 | informe/punto de diseño y aprobación documental usuario |
| 025:T21 | D+E separados, Con/Sin proyecto 2025 | obra elegida, variantes y conservación de Sin proyecto; no mezclar TXT/MDB |
| 026:T12 | una fuente y tarea real por vez | cada herramienta nativa por consola web, siete variables y suite sin omisiones |
| 027:T14 | Nasca/Chincha/Pisco/Ica, run por sistema | proyecto completo hasta PIDE, >=2 familias gemelo y puertas asistente |
| 027:T29 | Nasca y su ajuste, run exacto | hipercubo latino en copias por web |
| 027:T30 | Chincha y su ajuste | top-k de bancos contra medidas nativas completas |
| 027:T31 | cada sistema independiente | episodios 30/10/10 y curva por familia |
| 028:T6 | Nasca; diagnóstico actual de central | releer central real/barra antes de recalibrar; respetar CT existente |
| 028:T11 | individual + par unido de fuente propia | convertir/calibrar/recalibrar/informe, no solo flujo |
| 037:T4 | proyecto real con nuevas cargas | tres casos/año, escenarios, cargas y exclusiones releídos |
| 039:T4 | B/NA203, 2026-09 coincidente | ambos criterios; fijas mes 7707,5 kW/3725,5 kvar y registros instantáneos |
| 042:T6 | B/COPARA, período del plan | destinos/cargas, PIT/punto y 0,94–1,06; contrastar evidencia nueva con todos RF |
| 044:T4 | alternativas declaradas de un caso sellado | tests nativos aún ausentes, reapertura y métricas completas |
| 045:T4 | B u otra red capturada con cuatro roles | contrato físico/central/bancos, etiquetas y contraste por rol |
| 048:T4 | B u otra propuesta con 044 aprobada | variaciones, costes, referencia intacta y reapertura |
| 049:T4 | caso conocido con datos/curvas/licencia | ajustes/tiempos/fallas y readback; flujo no demuestra selectividad |
| 051:T3 | G/NJA202 2024-11 y R205 2022-01 | identidad R205 frente a 0205 sin suponer alias; cabeceras <1%, R205 activa |
| 052:T4 | B, período del plan | cronómetro <20 min y comparación oráculo/native; evidencia COPARA no prueba tiempo |
| 055:T2 | G, estructura VNR Electro Oriente | sistemas/SET y conversión de un sistema por web |
| 056:T3 | G/NJA202, VNR propio | importación y vocabulario según fuente |
| 058:T7 | alimentador de fuente declarada | importación nueva con nombre CSG y readback |
| 063:T7 | A/INKA, tres casos de su ajuste | botón 4.4, trabajo completo y comparación informe manual |

No se asigna una fuente o período desconocidos por semejanza de nombre. Las tareas
que piden confirmación visual/documental del usuario permanecen explícitas aunque
se automatice su evidencia objetiva.

Comando HTTP revisable para A, solo tras arrancar la API aislada y obtener el turno
compartido: `POST http://127.0.0.1:18765/api/workspaces/374e622963ae496e/pf/obras/set-nueva/operacion`
con cuerpo `{"project":"20261029-163414_IGEA_SM218","feeders":["SM218"],"accion":"diagnostico","verificar_flujos":false,"sincronizar_cargas":false,"conciliar_fases":false,"cambios":[],"salidas":[],"ajustes_flujo":{}}`.
La ruta existente genera el contexto nativo y ejecuta por el arnés. Este diagnóstico
genérico no exige crear una SET y restaura los casos en `finally`, también al éxito;
debe comprobarse `restauracion_errores=[]`, los tres casos y el estado inicial/final.
No acredita flujo ni aceptación. Para B se exige otro workspace aislado con su run
exacto y el proyecto de B, conservando CT/COPARA. No se ejecutó el comando en fase 1.

El escaneo actual `escanear_alimentador_pf.py` activa Sin proyecto y ejecuta ComLdf,
pero no restaura al éxito; 064 solo restituye globalmente ante error. Por ello su
etiqueta «solo lectura» no basta para usarlo sobre estado activo ajeno. No se lanza
en esta etapa. Tampoco se selecciona una troncal cualquiera para calibrar: la
frontera de medición debe cubrir todos los ramales o una fuente común inequívoca.

La revisión posterior corrigió una brecha real del diagnóstico existente:
`set_nueva_operacion_pf.py` no desactivaba el proyecto diagnosticado si al entrar no
había uno activo. Ahora repone esa ausencia solo para el proyecto de la operación,
comprueba el readback y registra fallo si no puede hacerlo. Si había proyecto/caso
y `IsLdfValid` consultable, captura la validez anterior; únicamente si era válida
recalcula el caso original mediante su ComLdf sin cambiar opciones. El informe
conserva el error original y separa `estado_inicial`, `estado_inicial_restituido` y
`restauracion_errores`; el fallo bloquea aceptación. No se guarda el escenario.
No se impuso una guarda de iopt_fls: la ruta solo modifica iopt_net y lo restaura.

El plan comercial histórico `374e.../planes/cargas_pf_9d656a0c5797.json` no existe.
Por eso el diagnóstico estructural ya no solicita `_cargas_nuevas_aplicadas`:
envía `nuevas=[]` y registra `validacion_de_nuevas=no_solicitada_diagnostico_estructural`.
Los flujos, evaluación y aplicación mantienen el manifiesto estricto. No se
rellenaron demandas faltantes ni se habilitó verificar_flujos con lista vacía.
La regresión enfocada final de estas correcciones y binding/preaceptación: **109
aprobadas, cero omisiones**, `diagnostico_integrado_final.xml`; Ruff de archivos
propios pasó. Los dobles prueban restauración y permisos, no física nativa.

## Recursos y LLM

GET main `/api/powerfactory` anuncia API PF2024/3.12 disponible; no comprueba licencia
ni conexión. La inspección SO no encontró proceso PowerFactory; el turno guardado
estaba liberado y no se reclamó. Ollama responde en 11434, sin modelos cargados.
RTX4060 Laptop tiene 8188 MiB, 68 usados al observar. La RAM física/comprometible
estuvo aproximadamente en 1,2/4,8 GiB: insuficiente para QLoRA según la puerta común
de 6 GiB físicos o, en Windows, >=0,5 físicos y >=8 comprometibles. No se entrenó.

La sonda real `asistente_qlora.py preflight` con corpus_sellado_v5 produjo un
bloqueo anterior al de memoria: seis referencias a `referencia/` ausentes tras su
retiro, entre 22 custodias únicas; cero archivos existentes con hash alterado.
`corpus_referencias_rotas.json` y `qlora_preflight_20261102/training_manifest.json`
conservan resultado. La migración a un corpus externo nuevo, verificando SHA y
conservando particiones, corresponde a `corpus_llm_reubicacion`; v5 se preserva.

La entrega posterior del responsable del corpus reabrió el nuevo
`aceptacion_dominio/corpus_reubicado_065`: preflight real exit 0,
`auditoria.ok=true`, 1734/54/54/200 registros y 96 contextos. El manifiesto dice
RECHAZADO porque no se solicitó entrenamiento ni promoción; no contradice la
validez de datos. Evidencia `corpus_llm/qlora_preflight_real/training_manifest.json`
releída en esta tarea. El bloqueo de recursos sigue siendo independiente.

GET `/api/asistente/aceptacion`: 200 propuestas únicas del maestro, 188/200 tareas
correctas (0,94), F1 0,9393939394; puertas 0,98 y 0,95 incumplidas. Cinco eventos
humanos corresponden a tres órdenes únicas; su acierto es 2/3 y F1 1,0. 047:RF-13
no exige 200 humanas para evaluar uso asistido. No se reducen umbrales ni se declara
aceptación integral/autónoma/eléctrica. El inventario de modelos da Transformer
RECHAZADO, QLoRA ERROR_ENTORNO y `complete=false`.

## Bloques de implementación concretos de 045–050

| Spec | Funciones/archivos previstos aún ausentes al inspeccionar | Pruebas previstas |
| --- | --- | --- |
| 045 | contratos_fisicos: validar_alcance_fisico, contexto_fisico, perdidas_fisicas; benchmark_fisico: comparar_fisicas, comprobar_dominio | test_gemelo_contratos_v2, test_pinn_fisica_y_fronteras, test_benchmark_pinn, test_gemelo_fisico_nativo |
| 046 | pronostico/adaptador_neuralforecast/evaluacion_temporal: candidatos NHITS/TFT/PatchTST reales y evaluación causal por horizonte | nombres y contratos de 046/plan; no basta alias de GRU |
| 047 | reranker/QLoRA y comparación rol único/equipo con corpus sellado, coste/latencia | pruebas reales del benchmark, sin convertir controles de permisos en calidad |
| 048 | problema mixto, adaptadores pymoo/PNL, benchmark con >=20 semillas y top-k completo | test_problema_mixto, test_adaptador_pnl, test_optimizacion_mixta_nativa |
| 049 | protecciones: disponibilidad_protecciones, plan_protecciones, evaluar_coordinacion; tools/protecciones_pf.py | test_protecciones_datos, test_protecciones_pf_guion, test_protecciones_coordinacion, test_protecciones_web, test_protecciones_nativas |
| 050 | instantánea común, vistas causales, evaluación/retención conjunta, manifiesto de conjunto y reversión | test_aprendizaje_continuo, tests_ml/test_aprendizaje_continuo_real |

Esta tabla orienta implementación; no demuestra que toda función parcial existente
sea incorrecta ni sustituye inspección/test individual antes de editar.

## Fundamento verificado en la web

Thomas (2017), tesis de maestría RWTH, compara conformidad estática y observable:
https://swc-rwth.de/theses/software-architecture-conformance-analysis-large-scale-industrial-case-study/
De Silva (2014), tesis doctoral St Andrews, estudia conformidad durante ejecución:
https://research-repository.st-andrews.ac.uk/handle/10023/5220
Li, Liang, Soliman y Avgeriou (2022), artículo en Journal of Software: Evolution
and Process, mapea detección y gestión de erosión arquitectónica:
https://doi.org/10.1002/smr.2423
Consulta primaria web del 2026-11-02. Fundamentan comprobar comportamiento y
procedencia además del código; no certifican métricas, licencia ni física de estos casos.
