# Plan — Spec 075

Lee: `docs/constitution.md`, esta spec, 068, 069 y 070 (RF-67 a RF-76).

## Contexto técnico

`destilacion_integral.entrenar_destilacion` entrena los candidatos, elige en selección y mide. `codificador_ordenes.entrenar` recibe
ejemplos y una `CacheCodificada` compartida. `transformer.evaluar` solo llama a `predecir`, de modo que unas predicciones
guardadas se miden con el mismo código que un modelo. `interprete.interpretar` decide cuándo se consulta a Ollama.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Claves, familias, reparto, tareas sin independencia | `asistente/validacion_cruzada.py` | RF-1 a RF-9, RF-23, RF-24 |
| Vueltas, filas que entrenan, modelo final, predicciones fuera de grupo | `asistente/validacion_cruzada.py` | RF-10 a RF-17, RF-20, RF-27, RF-28, RF-32 |
| Integración en el protocolo y en la decisión | `asistente/destilacion_integral.py` | RF-18, RF-19, RF-21, RF-22, RF-25, RF-26, RF-29 a RF-31, RF-33, RF-34, RF-42 a RF-46 |
| Opción de la herramienta | `tools/asistente_entrenar.py` | RF-35, RF-36 |
| Regla de Ollama | `asistente/interprete.py`, `asistente/codificador_ordenes.py` | RF-37 a RF-41 |

## Decisiones

- Las confirmadas no entran al corpus: la huella del corpus, de la sellada y de la histórica no se mueven, y 070:RF-76 sigue valiendo sin la opción. Descartado marcarlas como `entrenamiento`: `particionar_registros` rechaza un mismo texto en dos particiones.
- La medida agregada es un objeto con `predecir` que devuelve lo guardado de cada vuelta. Descartado sumar a mano aciertos y F1: dos fórmulas pueden dejar de coincidir.
- Las vueltas corren después de elegir el ganador en selección, con su método y su semilla. Descartado elegir en cada vuelta: serían 30 entrenamientos más, para una elección que no mira a las confirmadas.
- La marca de dato es un solo carácter. Con la de `firma_familia` («datoalimentadores»), «flujo de X» y «obras de X» diferirían en menos del 25 % solo por lo largo de la marca.
- Las tareas `sin_independencia` no añaden puerta (ver Limitaciones de la spec). Descartado apartarlas del denominador: es una excepción que aprueba.
- La regla de Ollama es la posición de `ninguna`. Descartado pedir a Ollama que nombre su evidencia: cambiaría su prompt y su esquema, y lo que nombra lo puede alucinar. Descartado añadir un campo a `predecir`: 069:RF-2 fija sus campos; `puesto_ninguna` se calcula aparte y solo cuando el modelo duda. `ollama.py` no cambia.
- Peso de las confirmadas fijado a priori: 8 repeticiones y 8 variantes, frente a 1 + 8 de un texto de plata (`VARIANTES_POR_TEXTO_REAL`), porque valen más que él y son decenas entre decenas de miles.

## Comprobación contra la constitución

- P9: ningún texto del operador en git, pruebas, registro ni JSON; las pruebas usan frases inventadas.
- P11: la medida real es la ejecución que lanza el integrador (T6).
- P12: cada RF con su prueba, en `tests/test_validacion_cruzada_ordenes.py`.
- P13: la agrupación no conoce ninguna empresa; las palabras sin contenido son de la lengua.

## Estrategia de pruebas

Codificador falso inyectado sobre la CPU, como en `tests/test_interprete_codificador.py`; dobles para Ollama y para el modelo que duda.
Sin GPU, sin DIgSILENT y sin leer el almacén real.

## Riesgos

Son 5 + 1 entrenamientos más sobre los 6 candidatos, con la caché compartida: el tiempo sube y la memoria de la GPU no debería, porque cada
vuelta se libera antes de la siguiente; no se ha medido. Comparar cada clave de plata con cada confirmada es O(claves × confirmadas), una vez por ejecución y en la CPU.
