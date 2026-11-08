# SDD ledger — plan: docs/superpowers/plans/2026-11-07-cierre-produccion-integral.md

## Autorización y contexto

Usuario: implementar el plan hasta poner en producción. Base main 56172510; responsable /root; rama codex/cierre-produccion-20261107.
Evidencia externa: D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/.

Ruling: ejecutar sin pausas por fase; la orden actual autoriza la implementación integral del plan, sobre las pausas genéricas del skill SDD. No autoriza inventar aceptación ni eliminar trabajo ajeno.
Ruling: worktree propio según coordinación y estrategia del plan; no se traslada el diff ajeno de services.py hasta comprobar su autoría/necesidad.
Ruling: ledger versionado y temporales/evidencias externos. Los helpers bash esperan encabezados Task N; este plan usa P00–P26, por lo que se usa el mismo contrato de brief/base/test/evidencia mediante este ledger y su estado.json.
Ruling: preparar publicación como puesto local según 086; la orden de poner en producción autoriza la entrega local del artefacto aceptado. Identidad del repositorio público o recurso externo distinto requiere estar definida antes de publicar allí.

## Preflight de interfaces

| Paquetes | Interfaz y resolución |
|---|---|
| P01/P03/P22 | security policy/locks/ejecutable real; auditar env y candidato por separado. |
| P02/P13 | alcanceDe y filas del informe; 098 prevalece sobre expectativa antigua 042. |
| P03/P25 | runner tests/ no acredita frontend/ML; consolidar ámbitos y no promover dominio por pruebas. |
| P04/P05/P07-P12 | source_run/contexto/caso; no mezclar modalidades/empresas/proyectos. |
| P14-P18/P19 | Muestra/punteros/conjunto; no activar un conjunto con miembro rechazado. |
| P23/P24/P25 | reordenación/renombrado invalida pase previo; revalidar candidato final. |

## Avances

P00: en curso; worktree creado; diff y plan preservados. Baseline enfocado pendiente.

Ruling: usuario confirma que no existen libro de confiabilidad/fichas de protecciones y ordena dejarlos pendientes. 012 T13 y 049 T4, y sus dependencias de datos reales, quedan pendientes_por_datos_usuario; no se falsean cifras ni aceptación. Se continúa con el alcance disponible.
P00: baseline enfocado 29/29, sin skips; worktree/plan/diff preservados.
P01: pruebas de mínimos RED 5 fallos por interfaz ausente, GREEN 21/21. Descarga de ruedas del lock con hashes verificados terminada; instalación limpia en curso.
P02: fallo de alcance reproducido; corregida expectativa que contradice 098 y el informe. npm test GREEN 43/43 sin skips.

Actualización del usuario: archivo de interrupciones recibido. Revisado BASE INTERRUPCIONES 2020 - 2026.xlsx en solo lectura: 7.967 eventos, 41 columnas, 2020-01-01 a 2026-11-01; original intacto por SHA-256. Historial disponible, libro normalizado/tasas/exposición/costos y protecciones aún pendientes. Evidencia externa base_interrupciones/REVISION_BASE_INTERRUPCIONES.md. No se cierra 012/049 por recibir historial bruto.

P01: núcleo instalado offline desde 58 ruedas verificadas por hashes en venv_candidato externo; Pillow13.0.0/pypdf6.21.4/certifi2026.10.18. pip check sin conflictos; pip-audit actual: 58 dependencias, 0 vulnerabilidades conocidas. Constraints alineados con mínimos; prueba RED guardada y 52 pruebas P01/P03 GREEN.
P03: herramienta integral implementada; 20 regresiones iniciales RED, luego GREEN. Revisión añadió negativos de backend sin hash y JSON npm no-objeto: 2 RED corregidos; total 26 pruebas GREEN. Conserva aceptación de dominio pendiente; no habilita production_ready por una tanda de tests.
P22 hallazgo: test opcionales_ia_y_tesseract dependía del OCR real del host por fallback de 091 fuera del PATH; el fixture ahora aísla ambas vías, preservando la detección real del producto. RED en entorno limpio, GREEN 3 pruebas enfocadas.
P02: typecheck y build real en worktree completados; build previo de main no se tocó.

P04: 121 pruebas de layouts/contratos/custodia/reconstrucción/seguridad sin omitidas. No es aún la conversión nativa de R1–R5. Baseline 143 rutas API y 46 archivos frontend preservado externamente.
P03: CLI real prepara edición completa y conserva acceptance pending; evidencia p03_preparacion/. Falta gate final completo, por eso 065 T17 conserva su condición pendiente.
P01/P22: wheel propia construida, neutralizada y validada; instalada en venv_candidato sin modificar el entorno activo de main. Entry points verificados con 72 pruebas de contratos/instalación/inventario.
P07: instancia propia en 127.0.0.1:8796, entorno seguro y raíces externas; health 200. Perfil copiado por hash, espacio vacío nuevo; no se han ejecutado acciones nativas todavía.
Ruling: commit del corte de ingeniería antes de las corridas nativas, con checks enfocados documentados; no se presenta ese commit como suite completa ni autorización eléctrica. La integración en main espera su gate.

P22: pruebas enfocadas del instalador GREEN 80/80, 16 deseleccionadas por alcance; evidencia instalacion_verde.log/xml. No es la instalación por tercero ni el gate completo.
P07: R1 real termina con código 2 tras conversión/importación/Caso base. CA101 y PE104 convergen; el preflight detecta problemas eléctricos (incluidos 0,8105 p.u. y 558,5 % en PE104). No se declara aceptación eléctrica. La calibración se bloquea con PROJECT_BINDING_NATIVE_UNREADABLE: Activate devolvió 1, evidencia p07_corrida.log y p07_job_*.json.
P07 diagnóstico: pf_proyectos.py compara wrappers con `is`, contradiciendo la identidad nativa por ruta ya usada en carpeta_pf y set_nueva_operacion_pf. Cinco regresiones RED reproducen falsa relectura, retorno 0 sin activación y restitución no verificada; se corrige el origen sin debilitar require_project_binding. Se añade 005 RF-23/T15 para su evidencia nativa pendiente.
P07: GREEN 138 pruebas carpeta/vínculo y 22 de trazabilidad; relectura nativa corregida f81b7d6770c7 finaliza done, sin native_warning, misma huella 020225af87e80f67fd54a30ea14ec0d5f2b39b13c48f797f79a987c00382b049 que la importación. Evidencia p07_relectura_resultado.json. Se continúa sobre el mismo proyecto, sin reconvertir ni borrar versiones para comprobar la calibración.
P07: continuación nativa en 9042ec98 termina con código 0; calibración 17a7799780e6 done, CA101 −0,02 %, PE104 −0,39 %, ambos VALIDO. Avisos KVAR y carga sin potencia instalada conservados. Se cierra solo la nueva 005 T15; P07 sigue en curso por cargas/obras/transferencia/reapertura. Evidencia p07_calibracion_resultado.json y p07_continuacion.log.
Ruling: adelantar los contratos puros de P19 sin esperar las campañas P14–P18; la dependencia condiciona su aceptación real, no impide implementar y probar la integración sin GPU. No se cierra ninguna T1b–T5b con fixtures. BASE 4009db49; baseline 69/69 (aprendizaje, experimentos, competición temporal).
P19 diseño: 050/plan.md concreta el mapa proyecto→huella 043 y la identidad común independiente de familia, con fecha UTC explícita y deduplicación por registro; se conserva ContextoExperimento individual. Fundamento ya verificado en web: maestría Witossek (DLR 220552), doctorado Mirzadeh (WSU 99900898638301842) y van de Ven et al. (Nature Machine Intelligence, DOI 10.1038/s42256-022-00568-3). No acredita resultados del producto.
P19 contratos T1b/T2b: 14 regresiones RED iniciales, GREEN 44/44; revisión detectó retirada del mapa, colisión oculta en replay y CLI sin manifiesto: 3 RED corregidos. Resultado combinado GREEN 86/86, sin omitidas (p19_green_final.log/xml). Captura multiproyecto v2 conserva mapa y hash; v1 conserva identidad. Aún faltan productores reales, trabajadores, consumidores y campaña, por lo que T1b–T5b permanecen abiertas.
P19 hallazgos de integración: la etapa GRU de reentrenar_modelos usa entrenar_temporal heredado sin candidate_id; el ciclo entrega el twin congelado como raíz de salida del trabajador. Se corregirán con negativas de comandos/aislamiento y sin sustituir evidencia real por dobles.
P07: reapertura nativa en procesos 57732 y 39364 sobre f641bb25, ambos código 0/reopen_verified true, PF 24.0.2 y sin avisos. «Sin proyecto» relee cabeceras CA101 4655,137 kW y PE104 5660,899 kW frente a objetivos 4656/5683; «Caso base» conserva demandas originales distintas (2241,702/3316,947 kW). Evidencia p07_reapertura/resultado.json y lecturas con hashes. P07 no se cierra: faltan obras/cargas/transferencia y conservación completa del caso base.
P19 trabajadores: 4 RED iniciales por falta de flag y salida sobre snapshot; revisión añadió 3 RED (aprobación PINN no llega al runner, algoritmo duplicado, parámetros CLI ausentes) y 2 RED (deriva de snapshot tras ejecutar y bloqueo de memoria no reintentable). GREEN combinado 127/127, sin omitidas, p19_trabajadores_final.log/xml. Candidatos registrados sin activación individual, copia de trabajo PINN, ruta temporal actual dentro del ciclo, parámetros en identidad y relectura final de snapshot. T3b sigue pendiente de vigilancia/cola, consumidores y ejecución real.
P19 hallazgo pendiente: entrenamiento_dataset.py guarda pesos reales pero no registra ni reabre candidatos; la publicación conjunta necesita además conservar el alias de registro de GRU (pronostico_cabecera). Se resolverán antes del ciclo real; no se declara concluido por el pase enfocado.
P19 conjunto: 7 RED por alias temporal, familia ausente con fallback, conjunto vacío, Iterable agotado y metadatos ignorados; otras 2 RED verifican reversión dañada y evaluación mutable. Conjunto v2 protege retención/evaluación, resuelve alias por identidad exacta y valida el destino antes de revertir. GREEN 76/76 con registro; lectura v1 conservada y probada por bytes. Falta conectar consumidores y ejecutar publicación/reversión con modelos reales, por lo que T4b sigue abierta.
P19 conjunto: regresión final ampliada GREEN 110/110, sin omitidas (p19_conjunto_final.xml), incluidos modelos web, compatibilidad v1 por bytes y trazabilidad de specs. No hay conjunto nuevo publicado en los datos del usuario: esta evidencia es de contratos temporales de prueba.
P19 consumidores lenguaje/PINN: 4 RED de selección/ruta/integridad, 1 RED adicional de identidad de la copia PINN, 4 RED por cambios individuales ignorados bajo conjunto. La guarda de capas detectó un ciclo transformer↔modelos_en_uso en la primera conexión: corregido, sin excepción nueva, con materialización común en model_registry. GREEN final 162/162 sin omitidas (p19_consumidores_cierre.log/xml): consumidores, provisionales, contratos del ciclo, experimentos, registro y capas. Punteros heredados conservados por bytes; no se cargó ninguna red real ni se acredita calidad científica con estos archivos de contrato.
P19 pendientes confirmados: consumidor temporal (pronóstico multihorizonte distinto de reconstrucción de 024/046), productores Muestra, entrenamiento_dataset con registro/reapertura, vigilancia/cola/vista web y campaña real. Ninguna T1b–T5b se marca cerrada.
P19 integración del catálogo: el gancho de commit avisó que el parser estático seguía buscando FAMILIAS en modelos_en_uso. Reproducción RED: 5 fallos/8 errores en arquitectura generada. Se apunta a la constante canónica FAMILIAS_MODELOS de transformer y se actualiza FUENTES para el índice/ganchos. GREEN final 149/149 (p19_generador_final.log/xml), incluidos commits y fusión en repositorios temporales. Catálogo actual comprobado; ninguna excepción de capa añadida.
Recursos actuales: 2026-11-07, unos 2,3 GiB de RAM física libres de 15,7 GiB; RTX 4060 con 7.957 MiB libres y 0 % de uso. El ciclo real de 050 T3b declara presupuesto 12 GiB. Se consulta al usuario si liberará memoria o prefiere dejar las campañas pendientes; se continúa con trabajo que no depende de su respuesta. No se cierran ni terminan procesos ajenos.

El usuario elige liberar memoria para ejecutar aquí las campañas: siguen previstas, no aplazadas por decisión del agente. Se mide de nuevo antes de ejecutar; no se bajan los requisitos para forzar una campaña.

Ruling: avanzar el campo de empresa de P11 mientras se libera RAM para P19 — implementa un requisito independiente y verificable — no cierra T16 sin navegador y dos empresas nativas. Base 3258ddf0; mismo worktree, UI existente preservada.
P11: cinco regresiones de render RED reproducen el campo ausente. El primer GREEN deja dos fallos del fixture de rutas, que solo copiaba dos helpers; se amplía a la clausura real de src. Resultado frontend 48/48, tipos y compilación correctos, p11_frontend_final.log/typecheck/build. Es render React de servidor, no aceptación visual del navegador.
P11: reproducción HTTP real en espacio propio 6006eab4167b460b detecta PUT empresa_espacio=null que devolvía 200 sin retirar el nombre. Regresión TestClient RED y corrección de la selección de cambios: null retira, omisión conserva. GREEN 134/134 de carpeta/API/espacio; p11_api_red.log y p11_backend_green.log/xml. Pendiente reiniciar solo la instancia propia inactiva para repetir persistencia HTTP real sobre este código.
P11 fundamento consultado en web: maestría Eriksson y Mosaddegh (2021), [Establishing Feedback in Continuous Delivery](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/index.html); doctorado Strandberg (2021), [Automated System-Level Software Testing](https://www.es.mdu.se/pdf_publications/6347.pdf); artículo indexado Shahin et al. (2017), [IEEE Access, DOI 10.1109/ACCESS.2017.2685629](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/). Fundamentan retroalimentación, pruebas por contexto y trazabilidad de entrega; no certifican este candidato ni su aceptación eléctrica.
P11 integración: 131 pruebas correctas y dos de inventario omitidas por variables de fuente ausentes; reejecutadas las dos con los TXT reales de R1: 2/2 correctas, sin omisiones (p11_integracion.xml y p11_inventario_real.xml). No se atribuye aceptación nativa a estas lecturas.
