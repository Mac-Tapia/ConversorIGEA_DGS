# Tareas — Spec 065

- [x] T1 Candidato aislado y coordinación de M0. (RF-1)
  Hecho cuando: registro, base y fronteras de escritura comprobados.
  Evidencia (2026-11-03): `pytest -q tests/test_trazabilidad_candidato.py` (registro por fase en `docs/implementacion065/progreso.md`).
- [x] T2 Propagación de códigos de salida del lanzador. (RF-2)
  Hecho cuando: batch real conserva 0/1/2/3 en pruebas aisladas.
  Evidencia (2026-11-03): `pytest -q tests/test_lanzador_exitcode.py` (0/1/2/3 con el batch real).
- [x] T3 Integridad y publicación completa del frontend. (RF-3, RF-4)
  Hecho cuando: faltantes y compilación fallida no publican un frontend incompleto.
  Evidencia (2026-11-03): `pytest -q tests/test_web_runtime_front.py` y `npm test` (`buildPreservado.test.mjs`).
- [x] T4 Bloqueo de grupos y paridad del modelo del control previo. (RF-5, RF-6, RF-7)
  Hecho cuando: pruebas negativas/positivas y reproducción de auditoría están verdes.
  Evidencia (2026-11-03): `pytest -q tests/test_preflight_contract.py tests/test_oraculo_corrige.py tests/test_powerfactory_fresh_report.py`; el bloqueo pasó a aviso por 081:RF-57 (aclaración de RF-5 y RF-7).
- [x] T5 Dependencias frontend y rutas con espacios. (RF-8, RF-9)
  Hecho cuando: ci/audit/test/build pasan con lock y Node/npm declarados.
  Evidencia (2026-11-03): `npm ci`, `npm audit` (0 vulnerabilidades), `npm run typecheck` y `pytest -q tests/test_frontend_rutas.py`.
- [x] T6 Raíces externas, staging y ciclo de vida de temporales. (RF-10, RF-11, RF-12, RF-13)
  Hecho cuando: import/pruebas/build/trabajos no crean temporales administrados bajo el checkout y protegen datos durables.
  Evidencia (2026-11-03): `pytest -q tests/test_runtime_paths.py tests/test_batch_staging_externo.py tests/test_publicacion_externa.py tests/test_workspace_runtime.py`.
- [x] T7 Capacidades runtime e instalación reproducible. (RF-14, RF-15)
  Hecho cuando: faltantes se diagnostican y un entorno limpio arranca con dependencias coherentes.
  Evidencia (2026-11-03): `pytest -q tests/test_web_runtime_dependencies.py tests/test_fijar_entorno.py`; venv nuevo de CPython 3.12.10 con `pip install -r requirements.txt -c constraints-python312-win.txt`, `pip check` sin conflictos, las diez capacidades disponibles y `/api/health` 200 en un puerto propio (`cierre_20261103/instalacion/` de la evidencia externa).
- [x] T8 Guardas de arquitectura y contrato API/frontend. (RF-16, RF-17)
  Hecho cuando: negativas deliberadas fallan y contratos positivos pasan.
  Evidencia (2026-11-03): `pytest -q tests/test_capas.py tests/test_contrato_api.py` y `tools/generar_contrato_api.py --check`.
- [x] T9 Trabajos prolongados y presupuestos de almacenamiento. (RF-18, RF-19)
  Hecho cuando: progreso, cancelación, cuotas y limpieza se verifican.
  Evidencia (2026-11-03): `pytest -q tests/test_operaciones_en_cola.py tests/test_descarga_cancelable.py`.
- [x] T10 Trazabilidad íntegra de RF y evidencia pendiente. (RF-20, RF-21)
  Hecho cuando: matriz enlaza fuentes/pruebas/resultados y no cierra aceptaciones ausentes.
  Evidencia (2026-11-03): `pytest -q tests/test_trazabilidad_candidato.py -k matriz_real`.
- [x] T11 Herramientas y equipo del asistente LLM verificados. (RF-22, RF-23)
  Hecho cuando: capacidades, permisos, roles, decisiones y concurrencia tienen pruebas positivas y negativas.
  Evidencia (2026-11-03): `pytest -q tests/test_asistente_equipo.py tests/test_asistente_equipo_web.py tests/test_asistente_web.py`.
- [ ] T12 [DIgSILENT] Aceptaciones del plan por proyecto y caso. (RF-21)
  Hecho cuando: ejecuciones reales, persistencia, reapertura y umbrales quedan documentados por sus specs; no se sustituyen por dobles.
- [ ] T13 Regresión, instalación y arranque final del candidato. (RF-24)
  Hecho cuando: evidencia integrada conserva resultados y pendientes sin omisiones ocultas.
- [x] T14 Un hilo de cálculo por proceso en el reparto. (RF-25)
  Hecho cuando: `pytest -q tests/test_batch_hilos.py` y `pytest -q tests/test_linea_base_001.py -k cuatro_procesos` en verde.
- [x] T15 Los espacios guardados se abren con el contrato de la API. (RF-26)
  Hecho cuando: `pytest -q tests/test_contrato_api.py tests/test_libros_por_anio_web.py` en verde y todos los `workspace.json` reales validan contra `EspacioRespuesta`.
