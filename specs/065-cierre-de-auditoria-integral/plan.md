# Plan — Spec 065

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
