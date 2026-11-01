# Los cuatro trabajadores del coordinador

Contrato: spec 043 RF-13/T7. Se implementan las herramientas ausentes detectadas
en la auditoría local, conservando abiertas la aceptación conjunta de 050 y el
ajuste generativo completo de 047 T7.

## Implementación

| Trabajador | Operación implementada | Contrato de datos |
| --- | --- | --- |
| `tools/digital_twin_temporal_entrenar.py` | GRU causal existente, selección por semillas, candidato persistido y recarga explícita | Cabeceras observadas, zona IANA explícita, cadencia de 15 minutos, objetivos finitos y al menos 30 días comunes; no imputa huecos |
| `tools/evaluar_evolutivos.py` | GA, NSGA-II y DE, 30 o más semillas y objetivos analíticos calculados | Problemas matemáticos declarados; no son mediciones ni aceptación de una red eléctrica |
| `tools/asistente_embeddings.py` | Ajuste contrastivo CUDA de E5, evaluación e índice candidato verificable | Train v2 verificado; consultas de prueba explícitamente independientes y distintas de train; no activa el índice |
| `tools/asistente_qlora.py` | Invocación real del entrenador generativo NF4 de 047, una o dos épocas completas | Corpus generativo sellado de cuatro particiones; no se sustituye por dataset v2 de tres particiones |

`tools/asistente_entrenar.py` ahora admite `--dataset-v2`. Ese modo consume
únicamente las particiones indicadas, comprueba su integridad y evita recurrir
silenciosamente a datos legacy. Guarda candidatos sin promoverlos. Los modos
legacy existentes se conservan.

El runner añade `--llm-dataset`, `--zona-horaria` y `--codigos-temporales`; usa la
base QLoRA fijada en el catálogo y conserva el motivo de los bloqueos del hijo.
La huella de reanudación incluye corpus, catálogo y parámetros temporales.
El proceso hijo hereda la guardia GPU únicamente al verificar el token y un
ancestro vivo del lock; esto contempla el redirector del venv Windows.
Los datos inválidos se distinguen de `ERROR_ENTORNO` por memoria insuficiente.

Una búsqueda evolutiva no aprende pesos: se informa `evaluation_completed`,
manteniendo `training_completed=false`. La verificación estricta distingue
`all_required_operations_completed` de `all_trained`; ninguna equivale a aprobar
calidad o aceptación eléctrica. El conjunto de 050 sigue sin publicarse.

## Procedencia del código y decisiones

Se inspeccionó el worktree del mismo repositorio `.worktrees/reentrenamiento-integral`,
HEAD `635fad90bcf54f13ad181ba3a818b6e8ae949cf3`. Se portó su módulo de embeddings
(SHA-256 original `55558b0deb32b6651ff492057d7bf30a9678ab1eec57e3e9b2f9620839a53c46`)
y sus pruebas, adaptando namespace, protocolo, CUDA local, particiones e integridad.
No hay imports hacia ese worktree en runtime. No se reemplazó la GRU actual por la
versión antigua del donante, que no conserva sus correcciones causales.
QLoRA reutiliza la implementación generativa actual, no el trainer anterior.

El benchmark conserva `RECHAZADO` para promoción: ejecutarlo no acredita una
alternativa eléctrica. Las consultas extractivas solo se admiten para ajuste,
nunca se presentan como preguntas humanas o evaluación independiente.

## Evidencia de ejecución

Directorio `output/auditoria_ia_20261101_actual/`:

- Los cuatro CLI terminan `--help` con código 0 sin cargar modelos. Los errores de
  datos dejan informes atómicos, código no exitoso y entrenamiento no completado.
- `trabajadores_guardia_corregida.xml`: 34 pruebas aprobadas, sin omisiones,
  incluida herencia real de guardia entre procesos y propagación de bloqueos.
- `regresion_trabajadores_final.xml`: 91 pruebas aprobadas, sin omisiones, antes
  de añadir tres casos adicionales de contrato. No es toda la suite del conversor.
- Entrega tras esos casos: `regresion_trabajadores_entrega.xml`, **94 aprobadas**,
  cero fallos/errores/omisiones, en 118,19 s. `pip check` también pasó.
- Control global de trazabilidad: `trazabilidad_entrega.xml`, 21 aprobadas y un
  fallo en la spec 053, que figura «implementada» mientras mantiene abierta su
  tarea de código T3. Esa spec tiene modificaciones concurrentes y no se cambia
  su estado ni se cierra su tarea para aparentar una validación global en verde.
- Benchmark real `evolutivos_operacion_real.json`: 30 semillas por algoritmo;
  medianas GA 0, NSGA-II 0,0000315694420234 de distancia al frente analítico y DE
  2,7478979327e-20. Duración 18,953 s. No hay resultados PowerFactory en ese informe.
- QLoRA, con el corpus real anterior: `qlora_con_datos_reales/training_manifest.json`
  conserva `BLOQUEADO_POR_DATOS`, por huella modificada. No produjo pesos.
- GRU, con el libro real `MEDICIONES ALIMEN_MOD PIT_2025.xlsx`: `gru_fuente_real.json`
  conserva `BLOQUEADO_POR_DATOS`, `L-TM105: fecha o potencia ausente`. No se descartó
  el registro para aparentar continuidad. Otra inspección de ese libro encontró
  timestamps duplicados y saltos en la curva leída; requiere reconciliación antes
  de acreditar entrenamiento. No se modifica el libro ni se imputa para superarlo.
- Embeddings: se prepararon 20 fragmentos literales del TXT real, con origen y
  rangos en `operaciones_reales/procedencia_embeddings.json`, solo para train.
  Los intentos quedaron bloqueados por memoria: el más reciente disponible antes
  de esta anotación informa `ERROR_ENTORNO`, 4,13 GiB comprometibles frente al
  mínimo preventivo de 6 GiB. No se atribuyen pérdidas ni pesos inexistentes.

## Revisión y correcciones

Una revisión independiente encontró dos fallos importantes y dos de menor alcance.
Se corrigieron los cuatro, con seis pruebas que fallaron antes del arreglo y
pasaron después (`revision_trabajadores_red.xml`/`revision_trabajadores_green.xml`).

1. Se rechazan consultas de entrenamiento recicladas como test y se exige la
   declaración explícita de independencia. Compartir corpus RAG sigue permitido
   cuando la consulta supervisada es distinta.
2. La identidad de un encoder local depende de sus archivos, configuración y
   tokenizador; cambiar pesos sin cambiar de ruta altera la huella y bloquea recarga.
   Para la base HF se contrasta el inventario local fijado; un identificador externo
   declarado no se convierte en pesos verificados ni puede cargarse por este CLI.
3. El candidato local E5 conserva un protocolo persistido de prefijos query/passage.
   Se trató como corrección importante: un nombre neutro de carpeta no puede cambiar
   la representación usada al ajustar respecto a la de evaluación.
4. Se corrigió la correlación biserial por rangos, usando sumas de rangos con
   empates y excluyendo ceros. Se trató como corrección importante de veracidad
   numérica: el campo no debe calcular otra estadística. No hay menores aplazados.

Los fixes se verifican mediante pruebas, sin pedir una segunda revisión. La revisión
de código no acredita ajustes CUDA completos ni puertas estadísticas o eléctricas.

## Fundamento consultado

- [Witossek, tesis de maestría, DLR/Leipzig, 2025](https://elib.dlr.de/220552/):
  comparar base, maestro y alumno; no atribuir aprobación por existir un worker.
- [Mirzadeh, tesis doctoral, WSU, 2022](https://rex.libraries.wsu.edu/esploro/outputs/doctoral/Alleviating-Catastrophic-Forgetting-in-Continual-Learning/99900898638301842):
  el entrenamiento secuencial exige contrastar retención antes de reemplazar modelos.
- [Van de Ven et al., Nature Machine Intelligence, 2022](https://doi.org/10.1038/s42256-022-00568-3):
  separar contextos y pruebas del aprendizaje incremental.
- [Documentación primaria de Sentence Transformers](https://www.sbert.net/docs/package_reference/sentence_transformer/losses.html#sentence_transformers.losses.MultipleNegativesRankingLoss)
  y [artículo E5](https://arxiv.org/abs/2212.03533): ajuste contrastivo de pares;
  nuestras semillas, mínimo de pares y presupuesto son opciones del proyecto.

## Qué permanece abierto

La ausencia de archivos y los argumentos incompatibles quedan corregidos. Aún se
requieren datos vigentes/aptos, margen de memoria y disco, ajustes completos y
reapertura independiente por familia, evaluación del asistente y publicación
conjunta. Estas condiciones no se cierran mediante los informes de bloqueo.
