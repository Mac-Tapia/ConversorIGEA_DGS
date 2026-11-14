# Preguntas por entregable: informe

Generado con `tools/preguntas_entregables.py informe` (spec 076), sobre la revisión `10fd3e1d`. No editar a mano.

Filas: 441. Huella del contenido: `f8c5b4f34cc64a3f64adc6bda65e192928dbeedce650cf8c17da5041008a45a6`.
Huella de lo sellado: `5d07ca9a5a97906cd1c25b8bfe38d755ac7601b35a3c8237ee510127e110d411`.

| Entregable o tema | Filas | Con respuesta | Sin respuesta | Corpus | Sellado | Revisadas |
| --- | --- | --- | --- | --- | --- | --- |
| informe_estudio | 21 | 18 | 3 | 16 | 5 | 0 |
| factibilidad_conexion | 21 | 18 | 3 | 16 | 5 | 0 |
| libro_excel_informe | 19 | 16 | 3 | 14 | 5 | 0 |
| planos_informe | 17 | 14 | 3 | 12 | 5 | 0 |
| formatos_pide | 18 | 15 | 3 | 13 | 5 | 0 |
| planeamiento_pide | 22 | 19 | 3 | 16 | 6 | 0 |
| dgs_manifiesto | 19 | 16 | 3 | 14 | 5 | 0 |
| calibracion_alcance | 22 | 19 | 3 | 16 | 6 | 0 |
| estudios_resultados | 17 | 14 | 3 | 12 | 5 | 0 |
| transferencias | 19 | 16 | 3 | 14 | 5 | 0 |
| escalera_obras | 20 | 17 | 3 | 15 | 5 | 0 |
| set_nueva | 18 | 15 | 3 | 13 | 5 | 0 |
| pronostico | 19 | 16 | 3 | 14 | 5 | 0 |
| catalogo_parametros | 18 | 15 | 3 | 13 | 5 | 0 |
| salidas_auxiliares | 17 | 14 | 3 | 12 | 5 | 0 |
| flujo_conversor | 28 | 23 | 5 | 20 | 8 | 0 |
| arquitectura | 28 | 23 | 5 | 20 | 8 | 0 |
| estudios | 29 | 24 | 5 | 21 | 8 | 0 |
| tipos_de_informe | 27 | 22 | 5 | 19 | 8 | 0 |
| operacion_web | 42 | 37 | 5 | 31 | 11 | 0 |

## Pendientes

- Bancos y valle (spec 073): está en la rama asistente/073 y no en esta; sin filas hasta integrarla.
- Revisión del operador de la hoja y decisión del usuario sobre su uso (076 T6).

## informe_estudio

Filas: 21; con respuesta 18, sin respuesta 3. Fuentes: aprobada 19, cumplida 2.

Huecos encontrados:

- Un alimentador por informe, aunque la spec pida uno o varios.
- Sin PDF: solo Word y JSON.

## factibilidad_conexion

Filas: 21; con respuesta 18, sin respuesta 3. Fuentes: aprobada 5, cumplida 16.

Huecos encontrados:

- Exige una carga ingresada sola; las del bloque no tienen informe de factibilidad propio.

## libro_excel_informe

Filas: 19; con respuesta 16, sin respuesta 3. Fuentes: cumplida 19.

Huecos encontrados:

- Sin Excel o con otro programa que responda por COM no está comprobado el resultado en esta revisión.
- La capacidad de los equipos de salida queda como hueco porque la red no la trae.

## planos_informe

Filas: 17; con respuesta 14, sin respuesta 3. Fuentes: aprobada 15, cumplida 2.

Huecos encontrados:

- No hay mapa de fondo, en contra de la spec.

## formatos_pide

Filas: 18; con respuesta 15, sin respuesta 3. Fuentes: aprobada 18.

Huecos encontrados:

- N y D de la NTCSE, COyM sin perfil y el desglose de costos por componente quedan como huecos nombrados.

## planeamiento_pide

Filas: 22; con respuesta 19, sin respuesta 3. Fuentes: aprobada 21, cumplida 1.

Huecos encontrados:

- El adaptador de módulos estándar de transmisión está (072 T3), pero falta la base real de la resolución y una obra valorada con ella (072 T13).
- La evaluación con y sin proyecto solo mide pérdidas.
- La aceptación real con el usuario está pendiente (072 T11).

## dgs_manifiesto

Filas: 19; con respuesta 16, sin respuesta 3. Fuentes: cumplida 19.

Huecos encontrados:

- Solo se prueba el esquema de PowerFactory 2024.

## calibracion_alcance

Filas: 22; con respuesta 19, sin respuesta 3. Fuentes: aprobada 1, cumplida 12, implementada 9.

Huecos encontrados:

- El tope de tres alimentadores lo pone solo la web; el servidor no lo aplica.
- No hay prueba de cómo trata «Recalibrar» un proyecto de una sola SET.

## estudios_resultados

Filas: 17; con respuesta 14, sin respuesta 3. Fuentes: implementada 17.

Huecos encontrados:

- El cortocircuito no se ofrece en la web porque la impedancia de fuente viene por defecto.

## transferencias

Filas: 19; con respuesta 16, sin respuesta 3. Fuentes: implementada 19.

Huecos encontrados:

- Las curvas de la máxima viven en memoria: tras reiniciar la web hay que volver a buscarla.

## escalera_obras

Filas: 20; con respuesta 17, sin respuesta 3. Fuentes: aprobada 5, cumplida 14, implementada 1.

Huecos encontrados:

- La optimización con el oráculo espera su confirmación real en DIgSILENT (052 T4).

## set_nueva

Filas: 18; con respuesta 15, sin respuesta 3. Fuentes: cumplida 4, implementada 14.

Huecos encontrados:

- La regla del operador de ubicarla en área libre no está en el código.

## pronostico

Filas: 19; con respuesta 16, sin respuesta 3. Fuentes: aprobada 1, cumplida 17, solo_especificada 1.

Huecos encontrados:

- No hay panel propio en la web; ningún neuronal superó las puertas en la medición real.

## catalogo_parametros

Filas: 18; con respuesta 15, sin respuesta 3. Fuentes: cumplida 18.

Huecos encontrados:

- Las fichas de fabricante que falten quedan por confirmar.

## salidas_auxiliares

Filas: 17; con respuesta 14, sin respuesta 3. Fuentes: aprobada 14, cumplida 1, implementada 2.

Huecos encontrados:

- No hay deshacer cargas nuevas en la web: solo por línea de órdenes.

## flujo_conversor

Filas: 28; con respuesta 23, sin respuesta 5. Fuentes: aprobada 3, cumplida 23, implementada 2.

Huecos encontrados:

- La estructura de la empresa sale del perfil; leerla de la propia fuente está solo especificado (055).

## arquitectura

Filas: 28; con respuesta 23, sin respuesta 5. Fuentes: aprobada 26, cumplida 1, solo_especificada 1.

Huecos encontrados:

- La arquitectura tiene datos desactualizados: ver las contradicciones.

## estudios

Filas: 29; con respuesta 24, sin respuesta 5. Fuentes: implementada 28, solo_especificada 1.

Huecos encontrados:

- Protecciones, armónicos, cuasi-dinámica y flujo óptimo no se ofrecen; protecciones está solo especificada (049).

## tipos_de_informe

Filas: 27; con respuesta 22, sin respuesta 5. Fuentes: aprobada 21, cumplida 5, solo_especificada 1.

Huecos encontrados:

- No hay un tipo de informe para ampliaciones de clientes existentes.

## operacion_web

Filas: 42; con respuesta 37, sin respuesta 5. Fuentes: aprobada 1, implementada 41.

Huecos encontrados:

- Lo que se ve en pantalla queda sin comprobar en navegador.
- Los botones de solo estado del navegador quedan fuera del catálogo con su motivo.

## Contradicciones entre la documentación y el código

Manda el código; se anotan y no se corrigen aquí.

- La arquitectura dice que el estudio de planeamiento está sin implementar, y el código genera sus siete módulos. Documento: `docs/ARQUITECTURA.md:266`. Código: `src/convertersmartgrid/informes_planeamiento.py:250`.
- La arquitectura dice que el RAG no tiene reranker, y el índice lo usa con su abstención. Documento: `docs/ARQUITECTURA.md:184`. Código: `src/convertersmartgrid/asistente/indice.py:72`.
- La arquitectura dice que el pronóstico multihorizonte no tiene código, y la spec 046 está cumplida con su código. Documento: `docs/ARQUITECTURA.md:240`. Código: `src/convertersmartgrid/digital_twin/pronostico.py:328`.
- La arquitectura dice que N-HiTS, TFT y PatchTST solo están especificados, y hay adaptadores en CUDA. Documento: `docs/ARQUITECTURA.md:212`. Código: `src/convertersmartgrid/digital_twin/adaptador_neuralforecast.py:1`.
- La arquitectura habla de tres carriles y el código tiene cuatro, con «control». Documento: `docs/ARQUITECTURA.md:118`. Código: `src/convertersmartgrid/web/jobs.py:40`.
- La arquitectura cuenta 210 módulos con capa y pyproject.toml declara 230. Documento: `docs/ARQUITECTURA.md:47`. Código: `pyproject.toml:109`.
- La cifra de acierto del Transformer en uso no sale de ningún fichero del repositorio y el puntero del almacén de esta revisión no existe: hay que medirla de nuevo. Documento: `docs/ARQUITECTURA.md:202`. Código: `src/convertersmartgrid/asistente/modelos_en_uso.py:4`.
- La spec pide el informe de estudio de uno o varios alimentadores y el código lo hace de uno. Documento: `specs/017-informes-de-estudio-y-factibilidad/spec.md:137`. Código: `src/convertersmartgrid/web/services.py:6926`.
- El docstring del informe de factibilidad dice que las pérdidas reconocidas vienen del formulario, y el código ya las lee del libro de pérdidas. Documento: `src/convertersmartgrid/web/services.py:7545`. Código: `src/convertersmartgrid/web/services.py:7631`.
