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
