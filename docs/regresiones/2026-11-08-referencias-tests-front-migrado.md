# Contratos Python después de mover el frontend

Specs 002 RF-19 y 076 RF-4/19; registro permanente 081.

## Síntoma

La migración conserva
el producto en `api/shared/features/app`, pero 27 tests Python aún abrían rutas
anteriores. Once módulos impedían coleccionar la suite y otras referencias
fallaban solo al ejecutar sus pruebas. Se conserva el rojo de la puerta sobre
`1c150695de0de3efdbdc86cec7042e2df7689fc6` en la evidencia externa P25.

## Causa

Las pruebas y el lector 076 conservaron ubicaciones anteriores a la migración.
Las corridas enfocadas no habían ejercitado todos esos lectores: algunos fallaban
al coleccionar, otros solo al ejecutar la lectura dentro de una prueba.

La corrida reveló además un warning de captura: el test de staging lanzaba un
hijo Python con `-I`, que ignora las variables UTF-8 del padre y emitía cp1252 en
Windows. `text=True` decodificaba como UTF-8 en el padre y el hilo lector fallaba
aunque el hijo devolvía cero. El test ahora captura bytes, comprueba el retorno y
la parte ASCII del mensaje semántico, y conserva stdout/stderr como diagnóstico.
No cambia el idioma del runtime ni fuerza su encoding global.

## Comprobación permanente

El primer correctivo cambia las rutas de los tests y de sus fixtures hacia los
archivos canónicos. Conserva sus aserciones y RF. La guardia de uso de API excluye
ahora exactamente `api/client.ts`, para que el cliente no cuente como consumidor
de sus propios métodos. No crea fachadas ni copias de componentes.

El segundo correctivo adapta el lector 076: API actual en `api/client.ts`, y
renombres explícitos de la migración para localizar el contenido vigente. La
cita original conserva su revisión `10fd3e1d`, fichero, línea y ancla literal.
Una ancla histórica inventada o un contenido vigente que la pierde siguen
siendo errores. La caché Git incluye la revisión completa y rechaza referencias
móviles, de modo que no presta un blob cacheado a otra revisión.

El corpus 076, las huellas, los RF, las anclas y su revisión fijada no se cambian.
Comprobar el contenido vigente no convierte una cita histórica en aceptación
actual ni acredita una pantalla. Los seis casos nuevos de
`tests/test_preguntas_entregables_migracion.py` incluyen Git real, autoridad de
API, caché entre revisiones y alteración del contenido vigente.

## Prueba

- `tests/test_cargas_tres_pasos_front.py::test_la_pestana_se_ve_sin_entradas`
- `tests/test_preguntas_entregables_migracion.py::test_cache_no_reutiliza_un_blob_fuera_del_sha_fijado`
- `tests/test_preguntas_entregables_migracion.py::test_contenido_vigente_alterado_se_rechaza_aunque_el_historico_siga_valido`
- `tests/test_web_runtime_front.py::test_validacion_staging_se_ejecuta_directa_sin_paquete_instalado`

Evidencia: `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/p23_referencias_tests_20261108/`.
La colección completa y las pruebas enfocadas son controles distintos; ninguno
se presenta como suite completa ejecutada, navegador ni aceptación nativa.
