# Plan — Spec 065

Ejecución de producción del 2026-11-07, P01: `tools/fijar_entorno.py` aplica los mínimos
de `config/entrega.json` antes de emitir constraints; los mínimos se comprueban contra
el cierre solicitado, sin exigir extras ajenos. Las versiones corregidas se conservan
en el lock del candidato y la auditoría CVE sigue siendo una puerta independiente.

P03: `tools/verificar_entrega_integral.py` consume el runner existente para `tests/`
y añade frontend test/typecheck/build, auditorías y `tests_ml` en edición completa.
Las pruebas usan procesos reales, TAP/JUnit y negativos de omisión/timeout. La salida
mantiene aceptación eléctrica, científica y operativa pendientes hasta sus evidencias.

La orden del usuario autoriza implementar el plan integral sin pausas entre fases.
Contrato: spec.md, constitución y specs enlazadas. Base inicial: f5c9c89d;
worktree propio codex/mejoras-auditoria-integral. Evidencias voluminosas fuera del código.

| Fase | Implementación | RF | Verificación |
| --- | --- | --- | --- |
| M0 | Registro en .agents/coordination/ACTIVE.md y ledger por este plan | 1 | candidato, propietario, interfaces, hashes y cambios ajenos preservados |
| M1 | run_gui.bat, web/runtime.py, publicación de frontend | 2–4 | batch real aislado; recursos faltantes; build interrumpido |
| M2 | web/services.py y contrato de conversión/reconstrucción | 5–7 | individuales/grupos positivos y negativos; paridad efectiva; fallo cerrado |
| M3 | frontend/package*.json y pruebas de rutas | 8–9 | npm ci, npm audit, test y build con/sin espacios |
| M4 | política común de rutas, workspace, subidas y staging | 10–13,19 | rutas externas, propiedad, cancelación/crash, publicación y protección de referencias |
| M5 | runtime por capacidades, manifiestos Python y lock de instalación | 14–15 | faltantes por capacidad, versión y entorno limpio |
| M6 | guarda AST de arquitectura, contratos API y generación de tipos | 16–17 | violación deliberada falla; esquema y tipos no divergen |
| M7 | JobManager para llamadas lentas y ZIP | 18–19 | admisión, progreso, cancelación y cuotas sin dejar parciales |
| M8 | lector de specs, matriz de trazabilidad y documentación canónica | 20–21 | referencias reales, citas vacías, semántica y evidencia de ejecución |
| M9 | aceptación nativa por proyecto y evaluación/gobierno del LLM y equipo | 21–23 | no mezclar sistemas ni sustituir evidencia científica; herramientas y decisiones auditables |
| M10 | combinación, instalación, regresión y arranque del candidato | 24 | evidencia del mismo código, hash, build y proceso |

Rutas y staging se acuerdan antes de cambiar consumidores. Los agentes escriben en
superficies separadas; el integrador actualiza pyproject, índice y specs generadas.
El motor nativo sigue serializado. Las tareas se cierran con resultados, no con número
de citas ni con ausencia de error. Los estados parciales quedan visibles en el ledger.

Corrección Windows (2026-11-08, RF-24): `verificar_candidato` admite `--trabajo-root`
externo y crea una raíz corta propia automáticamente para la suite completa en Windows;
la evidencia permanece en `--output-dir`. El registro enlaza ambas ubicaciones y conserva
su propietario. La consulta de Python tiene plazo y termina solo su árbol propio, con
identidad de creación; la salida binaria conserva bytes nativos no UTF-8. Las cachés
generadas se marcan para reconfigurarlas sin desplazar los datos de la ejecución ni
los overrides manuales. Los avisos del puerto ocupado también conservan esa salida
binaria. Verificaciones enfocadas en `test_verificar_candidato`, `test_runtime_paths`
y `test_lanzador_web`; la regresión completa sigue siendo una puerta independiente.

Cobertura de la huella (2026-11-08, RF-1/20/24): se observan los requisitos y locks
de todas las capacidades declaradas en la raíz, el instalador, las licencias
entregadas y las dos referencias de comparación TXT/MDB. Cambiar o retirar
cualquiera invalida la observación anterior. Las demás salidas, modelos y cachés
siguen fuera de esa selección. Una regresión por mutación reproduce diez omisiones
con la selección anterior; ambos módulos de trazabilidad/verificador pasan 81
pruebas en el entorno integral Python3.12.16. Es comprobación enfocada, sin cerrar
M10 ni sustituir el instalador, la suite completa o la aceptación del dominio.
