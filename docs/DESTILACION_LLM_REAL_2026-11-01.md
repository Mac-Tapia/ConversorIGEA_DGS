# Destilación del LLM alumno con fuentes reales

Contrato: [047 T7](../specs/047-asistente-estructurado-y-revision-por-roles/tasks.md).
La autorización del usuario exige al LLM generativo como alumno y datos reales de
`referencia/`. Los ensayos anteriores del clasificador y de un paso LoRA se
conservan como antecedentes, sin atribuirles una entrega generativa completa.

## Datos y custodia

Se leyeron los TXT reales mediante `CymdistDataset.from_files`, sin cambiar el
lector: 96 alimentadores, 38.657 tramos y 7.287 cargas en esta instantánea.
La fuente tiene huella `1980a3760ef655f18b1eddd79b1f5234c4e9bc10045ea5fc5e8f42796ead8363`.
Las entidades de proyecto proceden exclusivamente de vínculos TXT con esa misma
huella; no se deduce pertenencia a partir del nombre de un proyecto o red unida.
Se copiaron sus archivos de workspace para conservar una instantánea inmutable.

El PDF de sistemas aporta texto consultivo, sin corregir planos ni prevalecer
sobre `section_owner` del TXT. El período 2025-01 se leyó de celdas fechadas del
libro real de mediciones de cabecera. El Excel de nuevos clientes existe y conserva
su huella. Ninguna cifra de tensiones, pérdidas, convergencia o capacidad aceptada
se genera como si procediera de un estudio nativo.

El maestro de sesión redacta **solicitudes**, anotadas con las tareas y spans del
catálogo. Sus entidades proceden de estas fuentes; el número de escenarios es un
parámetro solicitado, no una medición. Las solicitudes no se presentan como
operaciones realizadas ni como órdenes humanas observadas. El generador sintético
anterior podía inventar valores aun con vocabulario: no se usa en este corpus.

El primer reparto se rechazó al carecer de pares del mismo proyecto en prueba.
Se eligió, antes de entrenar, el primer reparto hash que conserva pares reales en
las cuatro particiones; cada alimentador queda en una sola. La cobertura decide
ese reparto, nunca las métricas del modelo. Se reservan también los textos humanos
para impedir coincidencias exactas en el ajuste.

Corpus vigente preparado: 1.734 entrenamiento, 54 selección, 54 calibración y
200 pruebas nuevas. SHA-256 canónico:
`a93b21e3939b9294d99f2a43487c5d2660b3344aaebb1b8e5798094045ba893e`.
Incluye 64 controles de abstención redactados por el maestro y fundamentados en la
constitución, solo en entrenamiento. No son maniobras reales ni observaciones humanas.
Los archivos JSONL se sellan por separado para que el entrenador no abra prueba.
Datos y evidencia permanecen en `output/alumno_llm_referencias_20261101/`.

La auditoría real `auditoria_fuentes_final/auditoria.json` contrasta 11 archivos y los
96 contextos: 1.035 menciones de alimentadores, 796 de proyectos, 151 de sistemas,
75 de SED, 75 de períodos y 76 de rutas. Son menciones verificadas, no observaciones
independientes. Los tres textos humanos únicos están excluidos de todas las
particiones redactadas. Ningún resultado eléctrico ni escritura nativa se atribuye
a este dataset. Los parámetros solicitados y los textos redactados se cuentan aparte.

## Protocolo del alumno

Base NF4 fijada: `unsloth/Qwen3-4B-Instruct-2507-bnb-4bit`, revisión
`f12db89cd5156e090618dded9b4367f23f8f3b33`. Se usa destilación de respuestas:
etiquetas verificadas del maestro y pérdida causal exclusivamente en su respuesta.
No se poseen logits internos del maestro ni votos independientes adicionales.
El valor 0,9 anotado en las respuestas es una etiqueta, no una probabilidad calibrada.

Receta declarada antes del ajuste: QLoRA all-linear, rango 8, alpha 16, dropout
0,05, BF16, checkpointing de gradientes, batch 1, acumulación 8, semilla 11,
LR 0,0002 con diez actualizaciones de warmup y máximo 2048 tokens sin truncar
entidades o etiquetas. Cada época consume el train completo. Se conservan pesos,
optimizador, posición de datos y RNG cada 64 actualizaciones y al terminar.

Comparar la base y los checkpoints únicamente con los 54 casos de selección.
Presupuesto: hasta dos épocas; puede detenerse después de una si selección cumple
las puertas globales y por tarea. Fijar ganador antes de abrir las 200 nuevas.
Calibración y humanas se informan separadas; no entrenan los pesos. Mantener 98 %
de tarea, 95 % de F1 y puertas por tarea. Ninguna escritura pierde confirmación.

## Ejecución local y compatibilidad

Ollama instalado: 0.40.13. La prueba real rechazó `ADAPTER` con «LoRA adapters are
no longer supported»; la importación Safetensors usa MLX, ausente en Windows.
Se conservan ambos fallos. No se declara instalado un adaptador por producirlo.

La ruta comprobada es exportar tensor a tensor usando desquantización NF4 y las
deltas de PEFT, convertir con llama.cpp y cuantizar externamente antes de importar
GGUF. El export de base produjo 398 tensores FP16, 8.044.936.192 bytes, en shards
con SHA-256. La conversión y cuantización reales terminaron con código 0.

Una importación prematura mientras el cuantizador aún escribía fue rechazada por
Ollama por cambio de digest. Se conserva como fallo; la secuencia de despliegue debe
esperar ambos procesos y publicar el GGUF completo antes de importarlo.

La segunda importación terminó con código 0. GGUF de base:
`a7051bf4fce0bfe5b41e61ff56cd245dae261bde2cf786404c2348df31cd2f96`,
tag local `csg-alumno-base:20261101-nf4q4`. Es una base de comparación, no el alumno
entrenado ni el modelo activo. Su selección real de 54 casos terminó: 7/54 tareas
correctas (0,1296296296), F1 de datos 0,1, en `seleccion_base_v2/resultado.json`.
Este ensayo usa el sellado anterior; no se reasigna su hash al corpus vigente.
La comparación con un GGUF oficial también produjo errores de intención y respondió
correctamente una comprobación aritmética genérica. Eso no acredita capacidades
eléctricas ni demuestra que el ajuste vaya a superar las puertas.

llama.cpp se clonó y verificó con revisión/licencia fijadas en
`UPSTREAM_ALUMNO_LLM_LOCK.json`; el binario oficial Windows b12024 conserva hashes
de ZIP y ejecutable en `LLAMA_CPP_RUNTIME_LOCK.json`. Se instaló SentencePiece
0.2.1, requerido por el conversor; `pip check` pasó sin cambiar el núcleo existente.

## Estado verificable

- Preparación del corpus real y sellado: ejecutados.
- Validación final: 54 pruebas aprobadas, cero fallos/errores/omisiones
  (`validacion_fuentes_y_contratos_final.xml`): 31 contratos del nuevo flujo y cliente,
  22 de trazabilidad y 1 con el corpus y fuentes reales.
- Regresión adicional del intérprete, esquema, tareas, web, aceptación y particionado:
  70 aprobadas sin fallos/errores/omisiones (`regresion_interpretacion.xml`), con
  almacenamiento aislado de los datos reales. Total de esta validación: 124 pruebas.
  No es la suite completa del repositorio ni una nueva ejecución CUDA.
- Base exportada, convertida, cuantizada e importada: ejecutada; no activada.
- Primer ajuste completo solicitado: falló con error Windows 1455 de archivo de
  paginación, sin producir un checkpoint ni pasos de entrenamiento acreditados.
  Evidencia: `entrenamiento_epoca1/error.json` y `entrenamiento_epoca1.log`.
- Memoria diagnosticada después: servicio Windows AppXSvc con más de 17 GiB privados;
  memoria comprometible disponible variable, de aproximadamente 2,5 a 5,7 GiB.
  Es diagnóstico de recursos, no motivo para cerrar servicios o procesos ajenos.
  La sesión no tiene permisos administrativos. Se conserva
  `diagnostico_memoria_1455.log`; la disponibilidad puede cambiar después.
- Ajuste QLoRA completo, selección del alumno, recarga y prueba final: no acreditados.
- No hay promoción, ejecución eléctrica ni aceptación integral derivadas de este documento.

## Continuación reproducible

El CLI `tools/llm_destilar.py` mantiene `--help` sin importar modelos y ofrece
`preparar`, `sellar`, `auditar`, `entrenar-epoca`, `exportar`, `publicar`, `evaluar`
y `elegir`. `publicar` verifica checkpoint y herramientas fijadas; espera cada proceso,
cuantiza a `.incomplete`, verifica código/hash y renombra antes de importar. Solo
un readback de digest permite declarar publicación; nunca activa el candidato.
Este flujo del alumno entrenado aún requiere ejecución real, no solo pruebas puras.

Revisión independiente del código T7: tres hallazgos importantes corregidos en una
pasada, con pruebas que fallaron antes del arreglo y pasaron después. Se impide
saltar una época previa incompleta; el checkpoint vincula identidad/revisión e
inventario de base y tokenizador; el lector comprueba hashes canónicos de los
subconjuntos, procedencia y reserva humana, y la auditoría exige igualdad exacta
con el corpus aprobado. Las pruebas adicionales cubren una regeneración parcial
que renueva hashes de archivos sin cambiar el corpus global. No hay una segunda
revisión ni se acredita por inspección la equivalencia numérica de la fusión.

Registro de la revisión: `test_no_salta_la_epoca_previa_incompleta`,
`test_cambio_de_revision_base_rechaza_reanudar_y_exportar` y
`test_jsonl_regenerado_no_puede_heredar_identidad_del_sellado` fallaron antes de la
corrección y pasaron después. Se añadieron además dos variantes de regeneración
parcial para comprobar el corpus global y las humanas reservadas. No quedaron
hallazgos menores aplazados del revisor; la validación numérica pendiente se
mantiene como condición de aceptación de T7, no como hallazgo resuelto.

Sellado vigente tras estas correcciones: `corpus_sellado_v4`, misma identidad de
datos indicada arriba, con hashes adicionales por subconjunto. Los sellados previos
se conservan como evidencia histórica, sin modificarlos en el sitio.
Segundo intento, código vigente y este sellado: rechazo previo a Torch por memoria
disponible de 0,67 GiB física y aproximadamente 2,00 GiB comprometible, frente al
mínimo de 8 GiB comprometibles. Evidencia `entrenamiento_epoca1_reintento2/error.json`.
No hay un entrenamiento ejecutándose en segundo plano ni un checkpoint entrenado.

El fallo real se registró en el `RegistroModelo` común de la aplicación como
QLoRA `ERROR_ENTORNO`, candidato
`b0588643ff0301aa3d82a943078d9fe157c5480368fe1fbf8c8aeb310adf262d`,
con error y auditoría de fuentes como artefactos; no existe puntero activo QLoRA.
Se releyó `/api/asistente/modelos` mediante HTTP local real: esa familia muestra el
bloqueo de memoria y el conjunto informa `complete=false`.
Evidencia `registro_error_llm.json` y `estado_modelos_web.json`. HTTP 200 acredita
esa consulta, no entrenamiento ni aceptación del asistente.

Decisiones de esta continuación: usar únicamente el contexto de la entrega ELDUNAS
identificada, sin mezclar otros datos de referencia; conservar solicitudes del
maestro como anotaciones; no sustituir etiquetas nativas por predicciones; mantener
el presupuesto de dos épocas y selección previa a prueba. Si los datos disponibles
no representan otros dominios, esa generalización no queda demostrada.

Con recursos disponibles, usar un destino nuevo para el ajuste fallido; no reutilizar
ni borrar su evidencia. Entrenar el corpus sellado vigente completo, conservar y
verificar hashes de pesos/optimizador, publicar y evaluar por selección; repetir la
base sobre este mismo sellado para la comparación. Elegir y fijar digest antes de
abrir prueba. Si hay segunda época, reanudar desde el checkpoint completo de la primera.
No rebajar umbrales ni usar los fallos del test para elegir la versión.

La petición de sincronizar todos los modelos está recogida en
[spec 050](../specs/050-aprendizaje-continuo-integrado/spec.md) y su plan trazable.
Las piezas existentes no acreditan aún un ciclo integral: quedan abiertas sus tareas.

## Fundamento consultado

- Maestría [Witossek, Leipzig/DLR, 2025](https://elib.dlr.de/220552/): comparar maestro,
  alumno y base en el dominio; los datos anotados no sustituyen la evaluación.
- Doctorado [Zhang, HKUST, 2025](https://repository.hkust.edu.hk/ir/Record/1783.1-151306):
  distinguir tipos de conocimiento y métodos de transferencia.
- Revista indexada [Gou et al., IJCV, 2021](https://doi.org/10.1007/s11263-021-01453-z):
  distinción entre esquemas, arquitectura y comparación de desempeño.
- [QLoRA, Dettmers et al.](https://arxiv.org/abs/2305.14314) y
  [PEFT oficial](https://huggingface.co/docs/peft/developer_guides/quantization):
  base congelada de cuatro bits y adaptación de bajo rango.
- [Ollama, contrato actual](https://github.com/ollama/ollama/blob/main/api/types.go),
  [importación actual](https://docs.ollama.com/import) y
  [llama.cpp oficial](https://github.com/ggml-org/llama.cpp): compatibilidad de ejecución,
  comprobada localmente antes del ajuste. La bibliografía no certifica este modelo.
