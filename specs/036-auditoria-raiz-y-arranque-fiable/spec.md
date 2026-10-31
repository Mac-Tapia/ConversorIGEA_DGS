# Auditoría de raíz y correcciones del arranque

Estado: aprobada (2026-10-29)

## Motivo

El usuario pidió auditar todas las carpetas de la raíz, corregir errores, integrar elementos
sueltos y limpiar lo obsoleto, conservando el trabajo de otras sesiones. La inspección encontró
dos dependencias usadas pero no declaradas y un lanzador que abre la web aun cuando falla npm.
Esta spec limita el cambio de comportamiento a esas correcciones comprobadas.

## Requisitos

- RF-1: EL SISTEMA declarará `psutil` tanto en la instalación principal como en los extras
  `web` y `all`, y comprobará su disponibilidad antes del arranque web para conservar la
  vigilancia de memoria de los trabajos.
- RF-2: EL SISTEMA declarará `pypdf`, usado por el extractor PDF del corpus PIDE, en la
  instalación principal y en los extras `pide` y `all`.
- RF-3: SI falla la instalación de dependencias del front o su compilación en el lanzador de
  Windows, ENTONCES EL SISTEMA terminará con código distinto de cero sin iniciar un servidor
  nuevo y mostrará el motivo para corregir la interfaz.

## Fuera de alcance

No se reorganizan las capas de la spec 002 ni se cambia la calibración de la spec 035.
No se borran datos empresariales, modelos, evidencias, Git, entornos operativos ni worktrees.
La auditoría, las correcciones documentales y el manifiesto de limpieza acompañan el cambio;
las mediciones de carpetas corresponden al equipo y a la fecha del informe.
