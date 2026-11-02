# Tareas — Spec 065

- [ ] T1 Candidato aislado y coordinación de M0. (RF-1)
  Hecho cuando: registro, base y fronteras de escritura comprobados.
- [ ] T2 Propagación de códigos de salida del lanzador. (RF-2)
  Hecho cuando: batch real conserva 0/1/2/3 en pruebas aisladas.
- [ ] T3 Integridad y publicación completa del frontend. (RF-3, RF-4)
  Hecho cuando: faltantes y compilación fallida no publican un frontend incompleto.
- [ ] T4 Bloqueo de grupos y paridad del modelo del control previo. (RF-5, RF-6, RF-7)
  Hecho cuando: pruebas negativas/positivas y reproducción de auditoría están verdes.
- [ ] T5 Dependencias frontend y rutas con espacios. (RF-8, RF-9)
  Hecho cuando: ci/audit/test/build pasan con lock y Node/npm declarados.
- [ ] T6 Raíces externas, staging y ciclo de vida de temporales. (RF-10, RF-11, RF-12, RF-13)
  Hecho cuando: import/pruebas/build/trabajos no crean temporales administrados bajo el checkout y protegen datos durables.
- [ ] T7 Capacidades runtime e instalación reproducible. (RF-14, RF-15)
  Hecho cuando: faltantes se diagnostican y un entorno limpio arranca con dependencias coherentes.
- [ ] T8 Guardas de arquitectura y contrato API/frontend. (RF-16, RF-17)
  Hecho cuando: negativas deliberadas fallan y contratos positivos pasan.
- [ ] T9 Trabajos prolongados y presupuestos de almacenamiento. (RF-18, RF-19)
  Hecho cuando: progreso, cancelación, cuotas y limpieza se verifican.
- [ ] T10 Trazabilidad íntegra de RF y evidencia pendiente. (RF-20, RF-21)
  Hecho cuando: matriz enlaza fuentes/pruebas/resultados y no cierra aceptaciones ausentes.
- [ ] T11 Herramientas y equipo del asistente LLM verificados. (RF-22, RF-23)
  Hecho cuando: capacidades, permisos, roles, decisiones y concurrencia tienen pruebas positivas y negativas.
- [ ] T12 [DIgSILENT] Aceptaciones del plan por proyecto y caso. (RF-21)
  Hecho cuando: ejecuciones reales, persistencia, reapertura y umbrales quedan documentados por sus specs; no se sustituyen por dobles.
- [ ] T13 Regresión, instalación y arranque final del candidato. (RF-24)
  Hecho cuando: evidencia integrada conserva resultados y pendientes sin omisiones ocultas.
