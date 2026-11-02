# Retención automática del conversor — 2026-11-01

La política elegida por el usuario revisa cada24 horas las ejecuciones y temporales
gestionados y retira los obsoletos con más de siete días. Está implementada en062
y verificada activa por HTTP en el servidor principal.

## Funcionamiento implementado

- El lifespan de la web comprueba vencimientos cada60 segundos y ejecuta el trabajo
  de archivos fuera del hilo HTTP. Al arrancar recupera revisiones vencidas; si la
  web está apagada, no hay una tarea externa que limpie archivos.
- La fecha de la revisión queda persistida: reiniciar no reinicia el plazo de24h.
- La limpieza se aplaza si hay trabajos pendientes o activos. La admisión de trabajos
  y el mantenimiento comparten exclusión para impedir su ejecución simultánea.
- Protege las ejecuciones activas, cargadas, reconstruidas y referenciadas por los
  metadatos de cualquier espacio. Protege también archivos recientes en árboles viejos.
- Conserva modelos e informes. No recorre proyectos ajenos ni borra toda `output`.
- Solo contempla `runs/<run_id>`, `tmp` y `entradas/_auto` de espacios reconocidos.
  Verifica el árbol y sus rutas absolutas antes de retirar; no sigue symlinks o
  junctions. Retirar un enlace duro obsoleto conserva el original externo.
- El monitor muestra la última revisión, la próxima fecha y su detalle. Utiliza
  sus eventos existentes y «Actualizar evidencia», sin otro intervalo del navegador.
- El resumen único en `<raíz web>/_mantenimiento/retencion.json` limita cada categoría
  a200 entradas y conserva sus totales. Los bytes son lógicos: no equivalen al
  espacio físico liberado cuando varias rutas son enlaces al mismo archivo.

## Comprobaciones efectuadas

`output/retencion_20261101/regresion.xml`: **179 pruebas aprobadas**, sin fallos,
errores ni omisiones, sobre retención, monitor, API, asistente, modelos, trabajos,
orquestador, inventario y trazabilidad. La última ampliación de los casos de JSON
corrupto se verificó después en `politica_final.xml`: **15 pruebas aprobadas** de
la política. Son verificaciones parcialmente repetidas, no194 pruebas distintas.

Los contratos crean y retiran archivos reales en carpetas temporales. Comprueban
límites de fecha, referencias cruzadas, enlaces duros, una junction real en Windows,
modelos e informes conservados, bloqueo de admisión con hilos y rechazo de errores
reales de E/S. La consulta HTTP se prueba mediante TestClient y lifespan real de la
aplicación. No se presentan esas carpetas de contrato como ejecuciones eléctricas.

Compilación TypeScript y Vite aprobada: `frontend/dist/assets/index-LaVIhUHn.js`.
Ruff sobre el módulo y sus pruebas: aprobado. No se afirma haber ejecutado toda
la suite del repositorio ni haber hecho una inspección visual automatizada.

## Activación verificada en el servidor principal

La revisión automática rechazó el primer intento de arranque separado mediante
`Start-Process ... -WindowStyle Hidden` con `blocked by policy`. Una invocación
posterior del lanzador en sesión controlada encontró un trabajo eléctrico activo y
respetó su protección: no cerró el servidor.

Durante la verificación cambió el proceso del servidor. La consulta posterior al
servidor principal, PID48152, acreditó la política y su primera revisión completada:
**12 ejecuciones retiradas,110 conservadas y cero errores**. Se comprobaron las12
rutas retiradas como ausentes y la presencia del original VNR y del modelo GGUF.
El resumen registra874.475.006 bytes lógicos retirados; no se presenta como una medida
independiente del ahorro físico. La próxima revisión queda programada para
**2026-11-02 a las13:37, America/Lima**, aplazable si hay trabajos activos.

Evidencia: `AUDIT/retencion_20261101/verificacion_servidor.json` y
`output/web/_mantenimiento/retencion.json`. No se atribuye el cambio de proceso al
comando rechazado. El servidor tenía una operación eléctrica activa al verificarlo;
no se volvió a reiniciar. Su huella es7d3a6675d66e9ddf; no acredita la recarga de
cambios concurrentes posteriores de todo el repositorio.

El cierre final del índice y del contrato se comprobó con **120 pruebas aprobadas**
(`output/retencion_20261101/cierre.xml`). Este conjunto se solapa con las regresiones;
no se suman los resultados como si fueran casos distintos.

## Fundamento consultado

La [tesis de maestría de Ozen, Harvard](https://dash.harvard.edu/entities/publication/c73dfe9f-e3f6-48ba-bd48-d52559ed9ea2)
estudia políticas de reemplazo de caché. La [tesis doctoral de Cui, CityU](https://scholars.cityu.edu.hk/en/studentTheses/secure-deduplication-systems-with-advanced-applications/)
estudia deduplicación segura. El [artículo de revista IEEE sobre deduplicación](https://ieeexplore.ieee.org/abstract/document/7529062)
revisa reducción de almacenamiento redundante. [Nectar, OSDI2010](https://www.usenix.org/conference/osdi10/nectar-automatic-management-data-and-computation-datacenters)
fundamenta recolectar derivados regenerables conservando referencias y protegiendo
trabajos concurrentes. Los siete días y las24 horas son la elección expresa del
usuario; la bibliografía no impone esos umbrales ni acredita resultados locales.
