# Plan — Spec 069

Lee: `docs/constitution.md` y `specs/069-interprete-con-codificador-preentrenado/spec.md`.

## Contexto técnico

`interprete.py` llama a `predecir`; `transformer.cargar`, `destilacion_integral.cargar_alumno` y `modelos_en_uso.activar`
manejan `pesos.pt` y `modelo.json`. Un modelo nuevo que respete eso no obliga a tocar el registro.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Codificador, cabezas, entrenamiento, predicción | `src/convertersmartgrid/asistente/codificador_ordenes.py` | RF-1 a RF-6, RF-9 |
| Etiquetas y voto por palabra, comunes | `src/convertersmartgrid/asistente/datos_por_palabra.py` | RF-1, RF-31 |
| Carga de heredados y nuevos | `asistente/transformer.py`, `asistente/destilacion_integral.py` | RF-7, RF-8 |
| Mensajes `ninguna`: lectura y reparto por hash | `asistente/maestro_real.py` | RF-10, RF-11 |
| Segunda pasada, corpus y reservados | `asistente/destilacion_integral.py` | RF-10 a RF-14 |
| Sin tarea y umbral del modelo | `asistente/interprete.py` | RF-15, RF-16, RF-26 |
| Puerta de rechazo, calibración, informe | `asistente/destilacion_integral.py` | RF-17 a RF-25, RF-27 |
| Herramientas | `tools/asistente_entrenar.py`, `tools/asistente_destilar.py` | RF-28 |
| Frases de operador | `asistente/curriculo_maestro.py` | RF-29 |

## Decisiones

- El codificador va por `transformers` con `local_files_only=True`, no por `sentence_transformers`: hacen falta los
  estados por token y sus posiciones. La media enmascarada normalizada es la frase del experimento. Descartado: reentrenarlo,
  porque 25 000 frases no bastan para ajustar 118 M de parámetros sin perder lo que trae.
- La cabeza de datos es una GRU bidireccional sobre los estados por token más seis rasgos de forma de cada pieza (dígitos,
  mayúsculas, separadores…). Los códigos de red no tienen significado para el codificador: su forma es lo que los delata.
- Las probabilidades por token se pasan a caracteres y se decide con el voto por palabra de `datos_por_palabra`, para que el dato siga saliendo
  entero, con el mismo voto por palabra. Descartado: un decodificador nuevo.
- Los mensajes reservados van en su propio fichero, `rechazo_reservado.json`, junto al corpus. Descartado: una partición más,
  porque `PARTES` entra en la política; y el manifiesto, porque acaba en el registro.
- La puerta de rechazo no va en `PoliticaEvaluacion`, cuya huella queda en los candidatos anteriores y no debe cambiar.
- Las frases se codifican una vez por ejecución y se guardan en la CPU en `float16`: los seis candidatos comparten frases y
  al equipo le falta memoria.

## Comprobación contra la constitución

- P8: `transformers` ya está en el extra de IA de `pyproject.toml`; el núcleo arranca sin él.
- P9: el codificador no recibe nada fuera de la máquina; los textos reales siguen en el almacén.
- P11, P12: cada RF con su prueba; la prueba sellada y las fijas se comparan con la línea base.

## Estrategia de pruebas

`tests/test_interprete_codificador.py`, con un codificador falso inyectado sobre la CPU, sin descargar nada; cada prueba
cita `069:RF-n`. La medida real es la ejecución única de `tools/asistente_entrenar.py --integral`.

## Riesgos

Con el modelo en uso, la web carga el codificador en la GPU la primera vez, unos segundos y 1,4 GB compartidos con Ollama.
Una frase con muchos tokens se recorta a 96: los datos que queden detrás no se marcan.
