# Plan — spec 038

1. Indexar una vez por fuente cargada las SED exactas de las cargas y su `section_owner` en la
   fuente canónica; usar `extract_sed_code` y `feeder_short_name`, compartidos con la
   conversión. Reutilizar el índice por identidad del dataset, invalidándolo al cambiar
   de fuente. No agrupar sufijos ni construir modelos completos por cliente (RF-1, RF-3, RF-4).
2. Conservar `radial_libro`, `radial_fuente` y `nota_asignacion` en `ClienteImportante`;
   leer notas opcionales del libro y añadirlas a la exportación (RF-2, RF-6).
3. Reconciliar antes de `del_alimentador` en las dos vías de `services.demanda_clientes`;
   el plan ya consume esa misma función. Mantener el tratamiento posterior de las
   reconstrucciones explícitas (RF-5).
   Rechazar el plan si quedan clientes ambiguos en su alcance (RF-8).
4. Mostrar notas por fila y un aviso visible del criterio. Aclarar que se usa la fuente
   exportada cargada y que los planos previos de la distribuidora quedan fuera del alcance (RF-2, RF-7).

## Verificación

Pruebas de pertenencia única, ausente y ambigua; regresión de tabla con/sin máximas,
notas y exportación; pruebas existentes de demanda, plan y reconstrucción; build del
frontend y trazabilidad de los ocho RF. Comprobar además la entrega real sin publicar
sus archivos de entrada. Las pruebas del motor nativo se informan separadas.
