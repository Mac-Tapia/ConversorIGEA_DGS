# Tareas — Spec062

- [x] T1. Política, referencias y retirada delimitada. (RF-1, RF-2, RF-4, RF-5, RF-6, RF-7)
      Hecho cuando: pruebas reales de archivos demuestran fechas, custodia, aislamiento y fallos visibles.
- [x] T2. Exclusión de trabajos y ciclo de vida diario. (RF-1, RF-3, RF-7)
      Hecho cuando: pruebas de concurrencia impiden admisión durante mantenimiento y aplazan si hay trabajos.
- [x] T3. Estado visible y verificación de software. (RF-8)
      Hecho cuando: API/monitor, regresiones, compilación, inventario y trazabilidad pasan, con prueba de revisión real documentada.
- [x] T4. Activar en el servidor principal abierto. (RF-1, RF-8)
      Hecho cuando: el servidor principal expone la política y registra su primera revisión tras cargar la nueva versión, sin interrumpir trabajos.

Evidencia: `docs/RETENCION_AUTOMATICA_2026-11-01.md`,
`output/retencion_20261101/regresion.xml` y `politica_final.xml`.
T4 verificada por HTTP en el servidor principal: política7 días/24h, primera revisión
completada,12 ejecuciones retiradas y110 conservadas, sin errores. Evidencia:
`AUDIT/retencion_20261101/verificacion_servidor.json`. El primer intento de arranque
fue bloqueado; la comprobación posterior acredita activación tras un cambio de
proceso concurrente, sin atribuirla al comando rechazado.
