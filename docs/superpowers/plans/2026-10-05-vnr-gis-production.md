# Plan de implementación VNR-GIS para producción

Especificación: `VNR-GIS.md`.

## Restricciones globales

- Preservar los cambios existentes del usuario.
- TDD estricto para cada corrección funcional.
- Fallar cerrado ante pérdida de datos, CRS ambiguo, mapeo incompleto o perfil no verificado.
- No confundir pruebas sintéticas con importación real en PowerFactory/CYMDIST.
- CLI y Web deben compartir la misma capa de servicios.

## Tarea 1: Contrato fuente a modelo canónico

Normalizar GeoJSON, preservar atributos/linaje, rechazar identificadores vacíos o duplicados y registrar correctamente el CRS de trabajo.

## Tarea 2: Descubrimiento y adquisición oficial

Implementar compañías, periodos, búsqueda, actualización, descarga y validación de conteos/manifiestos contra fuentes oficiales.

## Tarea 3: Puertas, perfiles y exportación transaccional

Hacer reales las puertas A-F, exigir `TargetProfile` verificado, staging atómico, round-trip y procedencia reproducible.

## Tarea 4: Paridad CLI/Web y seguridad

Centralizar servicios, aplicar las mismas puertas, completar trabajos y rutas principales, límites de archivos y redacción de secretos.

## Tarea 5: Pruebas de integración y evidencia real

Ejecutar fixtures multiempresa, fuente OSINERGMIN real, suite completa y aceptación PowerFactory/flujo cuando el entorno lo permita.

## Tarea 6: Auditoría y entrega

Actualizar matriz L0-L7, documentación, requisitos, manifiestos y reporte final con estados PASS/FAIL/BLOCKED/NOT_RUN.
