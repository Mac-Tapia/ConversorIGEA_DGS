# Spec 068 — Dataset real del maestro: órdenes del operador, etiquetas de plata y currículo con su estilo

Estado: aprobada

Rama de trabajo: `asistente/maestro`.
Cita: 026 (asistente), 027 (agente en producción: RF-19, RF-33, RF-34, RF-65 a RF-67), 047 (destilación:
RF-11, RF-13).

## Por qué

El usuario, el 2026-11-02: «haz lo que falta para que llegue a las puertas; ahí tienes los archivos para
construir el dataset o lo que necesites; debemos dejarlo funcional, con datos reales, y que no alucinen».
Antes: «tú eres el maestro, entrena con la metodología de destilación».

Lo medido: en la prueba sellada de frases sintéticas, el Transformer en uso acierta el 42,3 % y el último
candidato el 51,4 %, con puertas de 0,95 en tarea y 0,85 en F1 de datos por familia; hay solo tres textos
humanos confirmados. El currículo trae una frase de entrenamiento por tarea, limpia, cuando el operador
escribe con imperativos cortos y erratas. Sus mensajes reales existen en las sesiones de trabajo y nadie
los había reunido; muchos son conversación sobre el desarrollo y no órdenes.

## Requisitos

Fuera de git y de los mensajes de commit: los textos reales y sus etiquetas viven solo en el almacén local.

### Extraer los textos reales

- RF-1: CUANDO se pida extraer, EL SISTEMA reunirá los mensajes que el usuario escribió en las sesiones de
  Claude Code del proyecto.
- RF-2: CUANDO se pida extraer, EL SISTEMA reunirá los mensajes que el usuario escribió en las sesiones de
  Codex cuyo directorio de trabajo pertenezca al proyecto.
- RF-3: CUANDO se pida extraer, EL SISTEMA reunirá los textos del registro de órdenes del almacén.
- RF-4: SI un mensaje es resultado de herramienta, recordatorio, meta, de una cadena lateral o empieza por
  una etiqueta, ENTONCES EL SISTEMA lo descartará.
- RF-5: SI una sesión de Codex la lanzó otro agente, ENTONCES EL SISTEMA descartará sus mensajes, porque su
  «usuario» es ese agente.
- RF-6: EL SISTEMA descartará los textos de menos de 5 o más de 400 caracteres.
- RF-7: EL SISTEMA deduplicará por texto normalizado y anotará cuántas veces apareció cada texto.
- RF-8: EL SISTEMA clasificará cada texto como `orden` o `charla` sin descartar ninguno de los dos.
- RF-9: CUANDO termine de extraer, EL SISTEMA escribirá de forma atómica `<almacén>/maestro_real/textos.jsonl`.

### Revisión humana

- RF-10: CUANDO se pida exportar, EL SISTEMA creará `<almacén>/maestro_real/revision.xlsx` con el texto, la
  tarea propuesta, los datos propuestos y las columnas vacías `¿correcta? (s/n)` y `tarea correcta`.
- RF-11: SI un texto empieza por un carácter que una hoja de cálculo tomaría por fórmula, ENTONCES EL SISTEMA
  lo escribirá como texto.
- RF-12: CUANDO se vuelva a exportar, EL SISTEMA conservará las marcas que el operador ya hubiera puesto.
- RF-13: SI una fila no tiene marca, ENTONCES EL SISTEMA no la importará.
- RF-14: CUANDO una fila esté marcada como correcta, EL SISTEMA la anotará en `ejemplos` con origen
  `confirmado`, con su tarea y sus datos propuestos.
- RF-15: CUANDO una fila esté marcada como incorrecta con una tarea correcta, EL SISTEMA la anotará en
  `ejemplos` con origen `corregido`, con los datos que esa tarea admita.
- RF-16: SI una fila está marcada como incorrecta sin tarea correcta, ENTONCES EL SISTEMA no la importará.
- RF-17: SI una fila contradice una etiqueta humana ya anotada para el mismo texto, ENTONCES EL SISTEMA no la
  importará y lo dirá.
- RF-18: SI una marca no se entiende, ENTONCES EL SISTEMA no importará ninguna fila y nombrará la fila.
- RF-19: SI la importación falla a mitad, ENTONCES EL SISTEMA dejará `ejemplos` como estaba.
- RF-20: CUANDO se importe dos veces la misma revisión, EL SISTEMA no duplicará ninguna fila.

### Etiquetas del maestro

- RF-21: EL SISTEMA guardará cada etiqueta en `<almacén>/maestro_real/etiquetas.jsonl` con calidad
  `silver_maestro_texto_real`, su maestro, su confianza y su tarea, o `ninguna` si no es una orden.
- RF-22: SI una etiqueta nombra una tarea que no existe, ENTONCES EL SISTEMA la rechazará y la contará.
- RF-23: SI un dato de una etiqueta no aparece en su texto, ENTONCES EL SISTEMA la rechazará y la contará.
- RF-24: SI la tarea de una etiqueta es `ninguna` o su confianza es menor que 0,7, ENTONCES EL SISTEMA no la
  llevará al corpus.

### Corpus

- RF-25: CUANDO se prepare el corpus con etiquetas, EL SISTEMA las pondrá solo en la partición de entrenamiento,
  como respuestas del maestro.
- RF-26: SI una etiqueta o una frase de estilo coincide en texto normalizado con selección, calibración, prueba,
  una orden humana o una fija de prueba, ENTONCES EL SISTEMA la descartará y la contará.
- RF-27: SI una etiqueta o una frase de estilo coincide en familia, con sus datos enmascarados, con selección,
  calibración, prueba o una orden humana, ENTONCES EL SISTEMA la descartará y la contará.
- RF-28: EL SISTEMA dejará idénticas las filas de selección, calibración y prueba, con o sin etiquetas y estilo.
- RF-29: EL SISTEMA dará en el manifiesto los denominadores de cada calidad en cada partición.
- RF-30: EL SISTEMA no contará las etiquetas de plata como órdenes humanas.
- RF-31: MIENTRAS el operador no haya confirmado 200 órdenes, EL SISTEMA seguirá pidiendo confirmación de lo que
  escribe, sean cuantas sean las etiquetas de plata.
- RF-32: EL SISTEMA aceptará la calidad `silver_maestro_texto_real` al releer un corpus guardado.
- RF-33: CUANDO una herramienta prepare el corpus para entrenar, EL SISTEMA leerá las etiquetas del almacén.
- RF-34: EL SISTEMA dará el mismo corpus con las mismas entradas.

### Currículo y aumentación

- RF-35: EL SISTEMA tendrá para cada tarea al menos 12 frases de estilo real, solo de entrenamiento.
- RF-36: EL SISTEMA no llevará en esas frases nombres reales de la distribuidora.
- RF-37: EL SISTEMA conservará las cuatro columnas de `FAMILIAS`, cuya posición decide su partición.
- RF-38: EL SISTEMA añadirá al entrenamiento variantes con las erratas observadas en las órdenes reales,
  deterministas por semilla.
- RF-39: EL SISTEMA dejará cada dato de una variante con errata en el sitio de su valor intacto.
- RF-40: EL SISTEMA no aplicará esas erratas a selección, calibración ni prueba.
- RF-41: EL SISTEMA dejará la huella de las 200 órdenes fijas y su reparto como estaban.
- RF-42: EL SISTEMA dejará la política y las puertas de evaluación como estaban.

## Fuera de alcance

Entrenar el Transformer o usar la GPU (lo hace el integrador), cambiar puertas, cambiar `transformer.py`, marcar
nada como confirmado en nombre del operador, una clase de abstención dentro del Transformer.

## Limitaciones declaradas

El Transformer no tiene clase «ninguna»: las etiquetas `ninguna` no pueden entrenarlo y solo sirven para medir su
rechazo fuera de catálogo. Una etiqueta de plata de un solo maestro no es un voto independiente (047:RF-11).
