# Tareas — Spec 061

- [x] T1. Diario por espacio e informes con custodia. (RF-1, RF-2, RF-3, RF-8, RF-9)
      Hecho cuando: las pruebas demuestran persistencia, aislamiento, contexto inmutable e integridad, sin cargar modelos.
- [x] T2. Conectar cola y consulta del monitor. (RF-1, RF-2, RF-3, RF-9, RF-10)
      Hecho cuando: trabajos reales de contrato completan/fallan y sus estados aparecen por API, y un error de persistencia no deja trabajos huérfanos.
- [x] T3. Proteger ejecución y reanudación del proyecto. (RF-5, RF-6, RF-7)
      Hecho cuando: un código1 no completa etapas, un cambio de identidad impide reusar el checkpoint y reiniciar conserva evidencia anterior.
- [x] T4. Integrar monitor en la web. (RF-2, RF-3, RF-4, RF-5, RF-9)
      Hecho cuando: TypeScript/build y pruebas de API pasan, la vista usa el contexto de trabajos y permite cancelar por la ruta existente.
- [x] T5. Incorporar evidencia real y verificar entrega. (RF-1 a RF-10)
      Hecho cuando: informes reales de060 están custodiados, regresiones e índice pasan y una prueba HTTP demuestra la integración servida, sin anunciar aceptación nativa o autonomía no acreditadas.

Evidencia de cierre: `docs/INTEGRACION_MONITOR_AGENTE_2026-11-01.md`; `output/integracion_monitor_20261101/entrega.xml` (176 pruebas sin omisiones), build TypeScript/Vite, `http_reinicio.json`, `websocket_real.json` y `http_principal.json`. La aceptación aquí corresponde al alcance de observación supervisada de061; no cierra050.
