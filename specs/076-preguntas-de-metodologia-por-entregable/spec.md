# Spec 076 — Preguntas de metodología y criterios por entregable, del flujo, de la arquitectura y de la web

Estado: aprobada · Fecha: 2026-11-02 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-02, pide un conjunto de preguntas de la metodología y los criterios de cada entregable «con datos reales
y no alucinen». Lo amplía el mismo día a las preguntas del flujo del proyecto, el conversor, su arquitectura, los estudios y los
tipos de informe, y después a la operación de la web, sus botones y sus casillas de carga, también generadas de forma estocástica.

Hoy el asistente no tiene un conjunto que diga qué debe responder de cada entregable ni con qué fuente, y el operador solo ha
confirmado pocas órdenes. El conjunto se escribe contra el código y las specs, cada fila con su fuente comprobable, y queda sin
integrar en el índice del RAG ni en ningún entrenamiento hasta que el usuario lo revise.

## Usuarios / actores

El operador que revisa la hoja, el usuario que decide cómo se usa y quien mida al asistente con lo sellado.

## Requisitos funcionales (EARS)

### Filas

- RF-1: EL SISTEMA guardará cada pregunta con entregable, aspecto, pregunta, tipo, respuesta esperada, fuentes, estado de la
  fuente, origen y marca de revisión.
- RF-2: EL SISTEMA tendrá por cada entregable al menos 12 preguntas con respuesta y 3 sin respuesta, y por cada tema transversal
  al menos 20 con respuesta y 5 sin respuesta.
- RF-3: DONDE una funcionalidad no exista en el código, EL SISTEMA tendrá como respuesta esperada que aún no está.
- RF-4: CUANDO se compruebe el conjunto, EL SISTEMA verificará en la revisión fijada que cada fuente existe, que su línea
  contiene su ancla y que su RF está definido.
- RF-5: SI una respuesta esperada lleva una cifra que no está junto a la línea citada, ENTONCES EL SISTEMA la rechazará.
- RF-6: SI una fila contiene un nombre de empresa, cliente, proyecto o alimentador reales, ENTONCES EL SISTEMA la rechazará, con una
  lista negativa derivada del perfil y de patrones, sin escribir datos privados.
- RF-7: EL SISTEMA fijará en una prueba la huella SHA-256 del contenido del conjunto.
- RF-8: EL SISTEMA repartirá las filas en `corpus` y `sellado` por grupos de paráfrasis, sin que un grupo quede en los dos, y su
  método estará declarado en un docstring.
- RF-9: EL SISTEMA dejará fuera de la huella la marca de revisión, de modo que revisar no toque lo sellado.
- RF-14: DONDE una regla de las memorias del operador no se confirme en el código, EL SISTEMA la guardará aparte como
  `regla_operador_sin_codigo` para revisar, sin darla por hecha.
- RF-15: EL SISTEMA anotará cada contradicción entre la documentación y el código con sus dos fuentes; manda el código.
- RF-16: EL SISTEMA no llevará este conjunto al índice del RAG ni a ningún entrenamiento, y no tocará los conjuntos sellados del RAG.
- RF-17: EL SISTEMA tendrá los temas `flujo_conversor`, `arquitectura`, `estudios`, `tipos_de_informe` y `operacion_web`.
- RF-18: EL SISTEMA no tendrá preguntas que comparen o mezclen las fuentes TXT, MDB y VNR-GIS.
- RF-26: MIENTRAS «bancos y valle» (073) no esté en la rama, EL SISTEMA no tendrá filas de ese entregable y lo dará como pendiente.

### Revisión del operador

- RF-10: CUANDO se pida `exportar`, EL SISTEMA escribirá un Excel de revisión con pregunta, respuesta esperada, fuente, «¿correcta?
  s/n» y corrección, en `output/`, fuera de git.
- RF-11: CUANDO se pida `importar`, EL SISTEMA marcará `revisado_por_operador` solo en lo marcado, sin duplicar filas.
- RF-27: SI una marca de la hoja no se entiende, ENTONCES EL SISTEMA rechazará la hoja entera sin escribir nada.
- RF-12: EL SISTEMA no contará una fila sin marca como humana, y ninguna fila contará como orden confirmada del operador (068:RF-30).
- RF-13: CUANDO se pida `informe`, EL SISTEMA dará por entregable sus filas, con y sin respuesta, y sus huecos.

### Operación de la web y preguntas estocásticas

- RF-19: EL SISTEMA tendrá un catálogo de hechos de la web, botón a botón y casilla a casilla, con su componente, su línea, y su ruta
  comprobada en la API.
- RF-20: CUANDO se pida `generar` con una semilla, EL SISTEMA dará la misma salida byte a byte, y otra muestra con otra semilla.
- RF-21: EL SISTEMA sacará la respuesta de cada pregunta estocástica de su hecho, nunca del azar.
- RF-22: CON el número declarado de muestras, EL SISTEMA preguntará por cada botón y casilla del catálogo al menos una vez.
- RF-23: EL SISTEMA no pondrá en un corpus estocástico los hechos de una fila sellada, y marcará en una muestra de medida los
  hechos ya vistos al enseñar.
- RF-24: EL SISTEMA no contará una pregunta estocástica como humana ni como orden confirmada.
- RF-25: EL SISTEMA marcará `sin_comprobar_en_navegador` lo que solo se comprueba viendo la pantalla.

## Requisitos no funcionales

Sin GPU, sin DIgSILENT y sin entrenar. Sin datos de la distribuidora. Universal: criterios propios de una empresa, «según el perfil».

## Casos límite

Un fichero citado que cambia después: la línea se comprueba en la revisión fijada y el ancla sigue en el árbol, o la prueba avisa de
que la fila hay que revisarla. Git en Windows puede sacar CRLF: la huella se calcula sobre el contenido, no sobre los bytes.

## Fuera de alcance

Integrarlo en el RAG o entrenar con él, que decide el usuario al revisar. Corregir lo que el conjunto halle en el código o en la
documentación: se anota. Comprobar la web en un navegador. Las filas de «bancos y valle».

## Criterios de finalización

Cada RF con su prueba, la huella fijada y la hoja revisada por el operador, que es lo único que queda abierto.
