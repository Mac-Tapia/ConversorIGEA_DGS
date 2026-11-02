# Plan — Spec 068

Lee: `docs/constitution.md` y `specs/068-dataset-real-del-maestro/spec.md`.

## Contexto técnico

`preparar_corpus` (`asistente/destilacion_integral.py`) expande plantillas en una pasada cuya historia decide qué fila
entra y cuál va a cuarentena. Las columnas de `FAMILIAS` son posicionales: `llm_destilacion` las indexa, 067:RF-35 fija
que sean cuatro y la cuarta es la prueba sellada.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Extraer, exportar, importar | `tools/asistente_ordenes_reales.py` | RF-1 a RF-20 |
| Lectura y validación de etiquetas, claves de fuga, erratas | `src/convertersmartgrid/asistente/maestro_real.py` | RF-21 a RF-24, RF-38, RF-39 |
| Segunda pasada del corpus | `asistente/destilacion_integral.py` | RF-25 a RF-34, RF-40 |
| Frases de estilo real | `asistente/curriculo_maestro.py` | RF-35 a RF-37 |
| Herramientas que preparan el corpus | `tools/asistente_destilar.py`, `tools/asistente_entrenar.py` | RF-33 |

## Decisiones

- Las frases nuevas van en `ESTILO_REAL`, junto a `FAMILIAS`. Descartado: alargar las tuplas de `FAMILIAS`, porque su
  posición es su partición, y `llm_destilacion` y 067:RF-35 dependen de que sean cuatro.
- Todo lo nuevo entra en una segunda pasada, después de sellar la primera. Descartado: mezclarlo en la pasada existente,
  porque un conflicto de texto mandaría una fila de prueba a cuarentena y cambiaría la prueba en silencio.
- La fuga se comprueba por texto normalizado y por familia (datos enmascarados). Descartado: solo por texto canónico,
  porque «convierte AB101» y «convierte CD202» son la misma frase para el modelo.
- Las etiquetas `ninguna` y las de confianza menor que 0,7 quedan en el fichero: las primeras sirven para medir el rechazo fuera de catálogo y las segundas se ofrecen al operador.
- Las erratas son una función nueva. Descartado: tocar `sinteticos._ruido`, porque de él depende la huella de las fijas.
- `n` con tarea correcta se anota como `corregido`, el origen que ya distingue `normalizar_orden` (`operator_corrected`).
- La escritura de `ejemplos` copia los bytes existentes y sustituye el fichero; comprueba justo antes que nadie lo cambió.
  Descartado: añadir línea a línea, porque un corte dejaría media revisión.

## Comprobación contra la constitución

- P9: textos y etiquetas solo en el almacén; ninguna prueba ni frase versionada los lleva.
- P11, P12: cada RF con su prueba; las fijas y la prueba sellada se comparan con la línea base.
- P13: las frases llevan `{proyecto}`, `{alimentadores}`… y una prueba busca códigos con forma de alimentador en ellas.

## Estrategia de pruebas

`tests/test_maestro_real.py`, con sesiones y almacén sintéticos en `tmp_path`, sin GPU; cada prueba cita `068:RF-n`.
Las particiones selladas se comparan contra el corpus sin nada nuevo, y la huella de las fijas con su valor fijado.

## Riesgos

Un corpus mucho mayor alarga el entrenamiento; el manifiesto da los denominadores para decidir `por_familia`.
Una etiqueta del maestro equivocada enseña un error: por eso la confianza mínima y la revisión humana, que no se presume.
