# SDD ledger — plan: specs/065-cierre-de-auditoria-integral/plan.md

Orden: implementar íntegramente M0–M10, incluida la operación del asistente LLM y equipo.
Base: f5c9c89db84d36f5256d103af98775bf49a88506. Rama y worktree propios.
Evidencia externa: D:/converter/auditorias/ConversorIGEA_DGS_20261102/implementacion065/.
Cambios previos ajenos: diff_ajeno_inicio_implementacion.patch, fuera del repositorio.

## Decisiones de arranque

Ruling: la orden expresa de implementar todo el plan autoriza las fases de spec, plan,
tareas y ejecución sin nuevas pausas — instrucciones del usuario prevalecen sobre
las pausas por fase del skill local — no autoriza borrar datos ni inventar aceptación.

Ruling: trabajo en un worktree propio dentro de la ubicación .worktrees ya existente
y excluida — coordinación global y plan M0 — el integrador conserva los cambios
concurrentes; antes de integrar compara de nuevo su base y el main vigente.

Ruling: ledger durable versionado y evidencias voluminosas externas — el usuario pide
no guardar temporales en el proyecto — se evita usar el directorio scratch del skill
para pruebas, builds o copias de datos. El marcador de identidad del skill es metadato.

## Preflight: consistencia interna por fase

| Fase | Contrato y comprobación | Decisión |
| --- | --- | --- |
| M0 | snapshot/dueño/archivos/evidencia | base y diff externo preservados; no usar árbol main mutable |
| M1 | error real, dist íntegro, build anterior | negativas reales aisladas antes del arreglo |
| M2 | rechazo por miembro, modelo publicado = validado | pruebas sin motor primero; nativo requiere turno separado |
| M3 | lock seguro, Node/npm y espacios | audit online y npm ci en copia propia |
| M4 | raíces externas, TTL y atomicidad | staging mismo volumen, no TEMP C: indiscriminado |
| M5 | capacidad/import/driver/versiones | no degradar permisos ni afirmar capacidad por import parcial |
| M6 | capas/contrato con deuda explícita | guardas no cierran por sí solas la migración de spec002 |
| M7 | HTTP corto, trabajo cancelable/cuota | preservar consumidores y semántica de descarga |
| M8 | RF→archivo→prueba→ejecución | cita no equivale a semántica; no cerrar 98 tareas por inventario |
| M9 | nativo y calidad científica separados | herramientas/roles efectivos y casos reales por proyecto |
| M10 | candidato único, regresión y arranque | no sumar resultados de revisiones incompatibles |

## Preflight: interfaces compartidas

| Productor / consumidor | Interfaz compartida | Regla |
| --- | --- | --- |
| M1 / M3 | frontend/dist, build y runtime | frontend publica completo; runtime valida referencias antes de arrancar |
| M1 / M5 | web/runtime.py y run_gui.bat | un implementador posee ambas superficies |
| M1 / M4 | entorno antes de importar Python | launcher aplica política de rutas común después de acordarla |
| M2 / M4 | web/services.py, workspace y source_runs | M2 no modifica workspace; raíz externa conserva contrato |
| M2 / M6 | modelo efectivo y núcleo/capas | no cambiar rutas públicas mientras se corrige control previo |
| M3 / M6 / M7 | API/types y consumidores frontend | cambios frontend funcionales posteriores a cesión del dueño de M3 |
| M4 / M5 | manifests/extras/rutas | pyproject solo lo integra root |
| M4 / M7 | subidas/ZIP/JobManager | cuotas y limpieza por trabajo, originales e informes intactos |
| M6 / M8 | guardas y matriz | toda excepción tiene identificación; sin cierre automático por cita |
| M7 / M9 | herramientas del asistente y carriles | operaciones largas se encolan; permisos efectivos conservados |
| M8 / M9 / M10 | tareas/specs/evidencias | evidencia nativa o científica ausente permanece pendiente |
| M0 / M1–M10 | índice, specs generadas, commits | un integrador único; las tablas se generan al combinar |

## Registro por fase

Candidato: rama `feat/065-cierre`, worktree `.worktrees/cierre-065`, desde `integracion/065`
(`3956ad2e`). Integrador único: sesión integradora de `integracion/065`. Implementación original:
`codex/mejoras-auditoria-integral` (base `f5c9c89d`), incorporada en `80d1c4b1`. Comprobación tarea por
tarea del 2026-11-03: `cierre_20261103/` de la evidencia externa. `tests/test_trazabilidad_candidato.py`
exige esta tabla. Estados: los del protocolo de coordinación; «revisión» es hecho y a la espera de integrar.

<!-- registro-fases -->
| Fase | Responsable | Cambios | Dependencias | Evidencia | Estado |
| --- | --- | --- | --- | --- | --- |
| M0 | integrador | `docs/implementacion065/progreso.md` | ninguna | `tests/test_trazabilidad_candidato.py` | revisión |
| M1 | implementador de arranque | `run_gui.bat`, `src/convertersmartgrid/web/runtime.py`, `frontend/scripts/build.mjs` | M0 | `tests/test_lanzador_exitcode.py`, `tests/test_web_runtime_front.py`, `frontend/test/buildPreservado.test.mjs` | revisión |
| M2 | implementador de control previo | `src/convertersmartgrid/preflight_contract.py`, `src/convertersmartgrid/web/services.py` | M0; decisión 081:RF-57 | `tests/test_preflight_contract.py`, `tests/test_oraculo_corrige.py`, `tests/test_powerfactory_fresh_report.py` | revisión |
| M3 | implementador de frontend | `frontend/package.json`, `frontend/package-lock.json`, `frontend/test/operacionSet.test.mjs`, `frontend/test/solicitudLeida.test.mjs` | M1 | `tests/test_frontend_rutas.py`, `tests/test_auditoria_raiz.py` | revisión |
| M4 | implementador de almacenamiento | `src/convertersmartgrid/runtime_paths.py`, `src/convertersmartgrid/web/retencion.py`, `src/convertersmartgrid/batch.py` | M1, M2 | `tests/test_runtime_paths.py`, `tests/test_batch_staging_externo.py`, `tests/test_publicacion_externa.py`, `tests/test_workspace_runtime.py` | revisión |
| M5 | implementador de instalación | `tools/fijar_entorno.py`, `constraints-python312-win.txt`, `src/convertersmartgrid/web/runtime.py` | M1, M4 | `tests/test_fijar_entorno.py`, `tests/test_web_runtime_dependencies.py`, `docs/implementacion065/instalacion_python.md` | revisión |
| M6 | implementador de arquitectura | `tools/arquitectura.py`, `tools/generar_contrato_api.py`, `src/convertersmartgrid/web/api_contract.py` | M2, M3 | `tests/test_capas.py`, `tests/test_contrato_api.py`, `docs/implementacion065/M6-arquitectura-contrato.md` | revisión |
| M7 | implementador de trabajos | `src/convertersmartgrid/web/operaciones_lentas.py`, `src/convertersmartgrid/adaptadores/entrada/vnr/discovery/download.py`, `frontend/src/features/conversion/DescargaZip.tsx` | M3, M4, M6 | `tests/test_operaciones_en_cola.py`, `tests/test_descarga_cancelable.py` | revisión |
| M8 | implementador de trazabilidad | `tools/trazabilidad_candidato.py`, `tools/estado_specs.py`, `CODIGO_FUENTE.md` | M6 | `tests/test_trazabilidad_candidato.py`, `tests/test_trazabilidad_specs.py` | revisión |
| M9 | implementadores de equipo y de dominio | `src/convertersmartgrid/asistente/equipo.py`, `src/convertersmartgrid/web/equipo_api.py`, `tools/aceptar_dominio.py` | M7, M8; T12 pide DIgSILENT | `tests/test_asistente_equipo.py`, `tests/test_asistente_equipo_web.py`, `tests/test_aceptar_dominio.py`, `docs/implementacion065/equipo_llm.md`, `docs/implementacion065/aceptacion_dominio.md` | en curso |
| M10 | integrador | `tools/verificar_candidato.py` | M0 a M9; suite completa con datos reales | `tests/test_verificar_candidato.py`, `docs/implementacion065/verificacion_integrada.md` | pendiente |
<!-- /registro-fases -->

M9 sigue en curso por la T12 (aceptaciones en DIgSILENT) y M10 pendiente por la T13 (suite completa,
instalación y arranque del candidato integrado). Asistente LLM/equipo: incluido por la aclaración del usuario.

Ruling: configurar sys.dont_write_bytecode dentro de __init__ no evita el primer
bytecode de ese mismo módulo: Python lo escribe antes de ejecutarlo. Se descartó
esa solución tras reproducción; los entrypoints administrados fijan -B/entorno antes
de importar. La regresión del producto usa el mismo contrato; una invocación manual
ajena a los entrypoints debe respetar la configuración documentada. No se cambian
permisos del checkout ni variables globales de otros proyectos para ocultar el problema.
