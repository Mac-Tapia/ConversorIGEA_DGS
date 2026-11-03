# Plan — Spec 079

Lee: `docs/constitution.md`, esta spec, 069, 070 (RF-67 a RF-77) y 075.

## Contexto técnico

`codificador_ordenes.entrenar` recibe ejemplos y una caché; `validacion_cruzada.ejecutar` lo llama vuelta a vuelta; `destilacion_integral` elige, calibra y decide; `_guardar_alumno` escribe `pesos.pt` con `modelo.red.state_dict()`, y `modelos_en_uso` y `transformer.cargar` manejan `pesos.pt` y `modelo.json` sin distinguir modelos. Por eso el tramo afinado vive dentro de `red`: el puntero, el registro y `predecir` no cambian.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Corte del codificador, `Prefijo`, configuración, tramo en el modelo, huellas y reapertura, error de la caché | `asistente/codificador_ordenes.py` | RF-2, RF-5, RF-16, RF-18 a RF-23, RF-58, RF-59 |
| Bucle de afinado, parada, tope de memoria, contrastiva, lotes, confusiones | `asistente/afinado_ordenes.py` (nuevo) | RF-1, RF-3, RF-4, RF-6 a RF-15, RF-17, RF-25 a RF-30, RF-63 |
| Las dos selladas en el corpus y la decisión; rejilla de la regla | `asistente/destilacion_integral.py` | RF-24, RF-42 a RF-48, RF-49 a RF-54, RF-57, RF-63, RF-64 |
| Frases `sellada_079` | `asistente/prueba_sellada_079.py` (nuevo) | RF-38 a RF-41, RF-60 |
| Currículo | `asistente/curriculo_maestro.py`, `destilacion_integral._ampliar_entrenamiento` | RF-31 a RF-37 |
| Regla en el intérprete | `asistente/interprete.py`, `codificador_ordenes.ModeloCodificador` | RF-54 a RF-56 |
| Herramienta | `tools/asistente_entrenar.py` | RF-61, RF-62 |

`validacion_cruzada.py` no cambia: llama a `co.entrenar`, que despacha por `cfg.afinar_capas` a la caché, y esta lleva la selección y la medida para la parada (RF-49). `codificador_ordenes` no importa `afinado_ordenes`: reabrir un modelo no carga el bucle de entrenamiento, y `test_capas` no admite ciclos nuevos.

## Decisiones

- **El tramo es una copia por entrenamiento, dentro de `red`.** Lo congelado se comparte en el proceso (`obtener_codificador`) y no se toca. Descartado afinar el codificador compartido y restaurarlo: una vuelta olvidada heredaría pesos que ya leyeron lo que examina.
- **Se guarda la salida de las capas congeladas, nunca la de las afinadas (RF-15, RF-16).** Descartado no guardar nada: serían 10 capas más en cada paso, sin gradiente y para nada, porque esos pesos no cambian. Descartado guardar la salida del tramo original como calentamiento de las cabezas: duplica 1,2 GB de RAM; la rampa de la tasa del tramo da el mismo efecto.
- **Una sola pasada por lote con las tres pérdidas.** Descartado alternar lotes de tarea y de datos, como en las cabezas: cada uno recorrería el tramo por su cuenta.
- **Corte con `create_bidirectional_mask` y `encoder.layer`, comprobado.** Sobre el modelo real en la CPU, embeddings + 12 capas dieron la salida de `red(**lote)` con error 0,0, con relleno (medido el 2026-11-03). Depende de `transformers` 5.x; una prueba con un XLM-Roberta diminuto, sin descargar nada, lo vigila.
- **Cabezas y contrastiva fuera de `autocast`.** Solo el tramo va en float16: es donde está la memoria, y la GRU empaquetada bajo `autocast` no se puede probar sin GPU en esta fase.
- **Parada por época de 800 pasos, no por recorrido completo.** 44 298 filas son unos 2 000 lotes; medir selección solo al final de cada recorrido pararía tarde.
- **La regla de Ollama se elige por modelo, en rejilla.** Descartado subir `PUESTO_CHARLA` a un valor fijo: con el candidato medido, 2 no cumple, pero no hay ningún dato de qué pasará con un modelo afinado; y un valor elegido hoy sobre el modelo viejo sería adivinar. La constante queda para los modelos sin regla (RF-56).
- **`sellada_079` se escribió antes que el currículo**, sin abrir `prueba_sellada.py`, y se comprueba contra ella por código. Dos de sus frases chocaron por familia exacta con la anterior y se reescribieron antes de fijar la huella y de medir nada; seis del currículo se reescribieron igual por la familia ancha, y de esas tres eran de la anterior: eso dice muy poco de ella, y queda declarado para que no parezca un ajuste.
- **`--afinar` es explícito**, como `--validacion-cruzada`: la vigilancia lanza la vía integral sin opciones y no debe ocupar la GPU una hora sin que se pida.

## Convivencia con la 077 y la web real

- `CodificadorPreentrenado` lee con `local_files_only=True` y sin `cache_dir`: usa la caché que señalen `HF_HOME` y `HF_HUB_CACHE` del proceso. No se abre ninguna vía nueva a la red.
- La web llama a `runtime_paths.configurar_entorno`, que apunta `HF_HOME` a la caché administrada (`CSG_CACHE_HOME/huggingface`). `tools/asistente_entrenar.py` no la llama y lee la caché del usuario (`~/.cache/huggingface`), donde hoy está la revisión `d128750…`.
- Para abrir el modelo afinado en la web hay que tener la revisión también en la caché administrada, o pasarle un `HF_HOME` que la tenga, y se prepara con:
  `python tools/preparar_modelos_ia.py --descargar --backend huggingface --id intfloat/multilingual-e5-base --output-json preparar.json`, con el mismo `HF_HOME` de la web (070:RF-77). El error de RF-59 la nombra.
- Los pesos afinados van en el almacén, en `pesos.pt`, y por el puntero de siempre; no hay nada nuevo que descargar para ellos.
- `prueba_sellada_079.py` queda vedada a la lectura local por el patrón `*sellad*` de `lectura_proyecto.SELLADOS`, sin tocar ese fichero (RF-60).

## Lo medido sin GPU (2026-11-03) y lo que se estima

Medido con el modelo real en la CPU, `medir079.py` del scratchpad de la sesión:

- 12 capas; 278 M parámetros (1,06 GB en float32); 7,09 M por capa (27 MB). El «118 M» del plan de la 069 no es de este modelo.
- Con 2 capas: 14,2 M parámetros, 54 MB en memoria; `pesos.pt` pesa 58 MB con las cabezas.
- Corte con el modelo real: error 0,0 de frase y de pieza, con relleno a la derecha; la huella de lo congelado tarda 1,7 s en la CPU.
- Piezas por frase del corpus sintético (41 243 frases): media 18,3, percentil 95 de 29, máximo 55.
- RAM de `CachePrefijo` con 44 298 filas a esa media: 1,16 GB en float16.
- Un paso real, sobre la CPU y en float32, lote 32 × 24 piezas: 0,65 s, y hasta 275 MB más de memoria residente, con Adam.
- RTX 4060 Laptop, 8 188 MiB, 149 MiB ocupados en el momento de mirar.

Estimado a partir de eso, sin medir: en la GPU 1,06 GB del congelado, más 54 MB del tramo, más 162 MB de gradiente y Adam, más la activación del lote: del orden de 1,5 a 2 GB. El tope de 5 GB deja margen. El tiempo en la GPU no se ha medido y no se estima como dato: lo da RF-17 en la primera época.

## Comprobación contra la constitución

- P8: sin dependencias nuevas; `transformers` ya está en el extra de IA.
- P9: ningún texto del operador en git, pruebas, registro ni JSON; las frases son inventadas.
- P11: la medida real es la ejecución que lanza el integrador (T7).
- P12: cada RF con su prueba, en `tests/test_afinado_ordenes.py`.
- P13: grupos de tareas del catálogo, vocabulario inventado.

## Estrategia de pruebas

`tests/test_afinado_ordenes.py`: un doble de codificador partido sobre la CPU, un XLM-Roberta diminuto creado con `from_config` para el corte real, y dos subprocesos con un `HF_HOME` temporal y una instantánea diminuta para la caché local y la reapertura en proceso nuevo. Sin GPU, sin DIgSILENT, sin el almacén real. Lo que no se comprueba aquí: la precisión mixta en la GPU real, la memoria real y cualquier medida del modelo.

## Riesgos

- Hasta 12 afinados (6 candidatos, 5 vueltas y el final): `--semillas` reduce los candidatos. Cada vuelta libera antes de la siguiente.
- Abrir un modelo afinado hace la huella de 1 GB de pesos, una vez por proceso: 1,7 s en la CPU, sin contar el paso desde la GPU. `reabrir_en_subproceso` ya da 300 s.
- Otro agente puede añadir tareas al catálogo: `sellada_079` exige todas, igual que la anterior; hay que añadirle frases a esa tarea, declarándolo, y volver a fijar la huella.
