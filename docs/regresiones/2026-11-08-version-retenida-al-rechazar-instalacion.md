# Versión retenida borrada al rechazar una instalación

Spec 081 (regresión permanente); 086:RF-38/39. Corrección `a1e137c609cd22eb4b7659962de376744ddbec95`, integrada por root como `f16e1e5c`.

## Síntoma

Después de volver de rc6 a rc5, rc6 permanece como versión anterior reutilizable.
Reintentar instalar rc6 se rechaza por existir su carpeta, pero el manejador de
error borraba esa carpeta preexistente. La reproducción CPU con archivos propios
demostró pérdida del testigo de la versión retenida; no se ejecutó setup real.

## Causa

El instalador retiraba incondicionalmente la carpeta de la versión solicitada al
fallar preparación, doctor o copia, sin distinguir una creación propia de una
carpeta anterior. El preparador ahora reserva exclusivamente su carpeta con
`mkdir(exist_ok=False)` antes del bloque de limpieza. Si rechaza una preexistente,
no adquiere su propiedad. Limpia su propia preparación fallida; el llamador solo
retira una preparación devuelta con éxito si después fallan doctor o copia.

## Comprobación permanente

La negativa crea rc6 retenida, rc5 y punteros/lanzador propios, conserva sus SHA y
comprueba que rechazar rc6 deja exactamente el mismo árbol. Otro caso verifica
la limpieza de una creación propia fallida. Las regresiones anteriores cubren
actualización normal, fallo del doctor/copia, web abierta y restauración.

Para regresar de rc5 a la rc6 ya retenida se usa el flujo `volver --sin-restaurar`
tras comprobar ambos punteros, en lugar de instalar otra copia de esa versión.
Esto no sustituye la comprobación de datos/copia v2 ni la aceptación nativa.

## Prueba

`tests/test_instalacion_programa.py::test_rechazar_version_preexistente_conserva_arbol_y_punteros`
y `::test_preparar_version_fallida_retira_solo_su_propia_creacion`.

Evidencia externa: `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/p25_revision_instalacion_20261108/red_instalador.xml`
y `green_instalador.xml`: rojo2 → verde10 enfocado, sin pip, setup real ni entorno
nuevo. La ejecución completa combinada corresponde al integrador; no se cierra
producción ni aceptación comercial con estos resultados CPU.
