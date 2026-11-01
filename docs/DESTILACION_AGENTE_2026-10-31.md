# Destilación y pruebas del agente — 31 de octubre de 2026

Contrato: [047 T5](../specs/047-asistente-estructurado-y-revision-por-roles/tasks.md),
con particiones y registro de 044/043. El maestro de esta ejecución es Codex de
sesión; el alumno es el Transformer local de tareas y entidades del asistente.
Se conserva el LLM local como fallback. Esto no equivale a entrenar un LLM general
ni a enseñar al modelo a resolver estudios eléctricos sin el motor nativo.

## Metodología implementada

1. **Maestro y custodia.** Codex escribe cuatro familias de frases por cada una de
   las 27 tareas y revisa el catálogo histórico como material de entrenamiento.
   Los ejemplos conservan etiquetas, spans de entidades, revisión del maestro y
   una justificación breve tomada de la descripción pública de la tarea.
   Es destilación de respuestas mediante CE de tarea y entidades. No se dispone de
   logits internos del maestro; una anotación no se transforma en cinco votos ni
   en una orden confirmada por el operador. Las justificaciones se guardan para
   auditoría; no se declara entrenada una cabeza de razonamiento.
2. **Cuatro particiones.** Las familias se asignan antes de generar sus variantes.
   Entrenamiento, selección, calibración y prueba no comparten grupos ni textos
   canónicos. Los caracteres del alumno se aprenden solo con entrenamiento.
   Las órdenes humanas admisibles se reservan para evaluación. Los cinco eventos
   locales contienen tres órdenes únicas; las repeticiones no aumentan el soporte.
3. **Auditoría completa del corpus.** Las variantes sintéticas con entidades
   contradictorias quedan en cuarentena. Una contradicción humana bloquea la
   preparación para no ignorar una corrección. La ejecución exploratoria inicial
   se interrumpió antes de abrir la prueba final al detectar el conflicto «todos
   los alimentadores», etiquetado unas veces como entidad y otras como literal.
   Se conservaron sus cuatro checkpoints terminados, protocolo y registros.
4. **Comparación.** Entrenar supervisado y destilado con las mismas semillas
   `11,23,37`, arquitectura y 24 épocas. El baseline usa ejemplos deterministas;
   el alumno añade las respuestas del maestro. Elegir por macroacierto y F1 de
   selección; en empate, preferir el supervisado. El conjunto de prueba no decide
   semilla, método o hiperparámetros.
   Los corpus tienen distinto tamaño y, con igual número de épocas, distinto
   número de actualizaciones: esta comparación mide el currículo ampliado, no
   aísla causalmente la destilación frente a un presupuesto computacional idéntico.
5. **Calibración.** Con el ganador ya fijado, elegir temperatura exclusivamente
   en calibración mediante NLL. No presentar esa calibración como garantía de
   cobertura. La temperatura se conserva tanto en el formato nuevo como en las
   APIs estándar de guardado y carga.
6. **Evaluación.** Abrir la prueba final del ganador y separar métricas sintéticas,
   humanas y por tarea, con denominadores. Ninguna media compensa una familia
   ausente o bajo puerta. Esta ejecución exige un mínimo predeclarado de 200
   órdenes humanas independientes para promoción. Es una política adicional de
   047:RF-13: la 027:RF-19 exige confirmaciones con menos de 200, no establece por
   sí sola ese mínimo para toda promoción histórica.
7. **Persistencia y funcionamiento.** Guardar pesos, configuración, hashes de
   corpus/política, entorno, snapshots de código y decisión. Recargar el alumno en
   un proceso CUDA nuevo y comparar sus predicciones. Ensayar intérprete y plan
   reales, resolución de entidades y confirmaciones; probar separadamente el
   alumno solo y el agente con Ollama. Estos ensayos no ejecutan escrituras nativas.
8. **Registro y activación.** Registrar la decisión en `RegistroModelo` y conservar
   el modelo activo. `latest.json` identifica la última decisión, mientras
   `active.json` identifica el modelo autorizado. Un candidato bloqueado puede
   verse en la web sin presentarse como activado ni como siete familias entrenadas.

## Corpus y ejecución reproducible

El corpus final consultado contiene 9.773 registros: 7.171 de entrenamiento, 859
de selección, 871 de calibración y 872 de prueba. Entre ellos hay 3.685 ejemplos
deterministas, 6.085 del maestro y tres órdenes humanas únicas. Un texto sintético
conflictivo queda excluido. Son filas correlacionadas dentro de familias, no 9.773
observaciones humanas independientes.

Hash del corpus final:
`873832710f28e6c4f5ca7b995f2d92c48173ca9e985f27233642e44da8f78c29`.

Desde la raíz, con Python 3.12 y el entorno Torch/CUDA existente:

```powershell
.venv\Scripts\python.exe tools\asistente_destilar.py preparar --destino output\mi_corpus --por-familia 40
.venv\Scripts\python.exe tools\asistente_destilar.py entrenar --dataset output\mi_corpus --destino output\mi_entrenamiento --semillas 11,23,37 --epocas 24
.venv\Scripts\python.exe tools\asistente_destilar.py verificar --modelo output\mi_entrenamiento\alumno
.venv\Scripts\python.exe tools\asistente_destilar.py ensayar --modelo output\mi_entrenamiento\alumno --ollama qwen2.5:3b --output-json output\ensayo_agente.json
.venv\Scripts\python.exe tools\asistente_destilar.py evaluar --modelo output\mi_entrenamiento\alumno --dataset output\mi_corpus --ollama qwen2.5:3b --output-json output\evaluacion_agente.json
```

Para publicar la decisión en el registro que consulta la web, `entrenar` acepta
`--registro RUTA`; eso no activa el modelo. Para la cola existente:

```powershell
.venv\Scripts\python.exe tools\asistente_entrenar.py --integral --output-json output\resultado_integral.json
```

La web usa ese modo. Si el alumno no se promueve, conserva el clasificador y los
umbrales del modelo vigente. La preparación rechaza sobrescribir otro corpus y
el entrenamiento conserva ejecuciones previas en lugar de reutilizar informes.
El bloqueo GPU compartido impide dos entrenamientos simultáneos.

El lanzador histórico sin `--integral` se conserva por compatibilidad experimental;
sus antiguas métricas no acreditan este protocolo ni cierran la consolidación de
todos los lanzadores de 043. Los adaptadores generativos de 047 T4 y las demás
familias de 045–049 conservan sus condiciones propias de evaluación y aceptación.

## Evidencia local y límites

Resultados de la ejecución final: seis entrenamientos CUDA completados en 393,2 s;
ganador `destilado`, semilla 23, elegido exclusivamente por selección. La prueba del
alumno contiene 869 sintéticas (acierto 0,5086; F1 de entidades 0,7464) y tres humanas
únicas (3/3 tareas correctas, F1 1,0). Temperatura calibrada: 3,0. La recarga en un
proceso nuevo produjo las mismas predicciones. Estos resultados no pasan las puertas
por tarea ni el mínimo humano predeclarado: **BLOQUEADO_POR_DATOS, sin activación**.

El smoke híbrido de tres órdenes pasó con Ollama `qwen2.5:3b`; el alumno solo se
abstuvo ante una de ellas. Al ampliar a una orden sintética por cada una de las 27
tareas y las tres humanas únicas, se detectó un defecto del esquema genérico: el
modelo añadía campos de otras tareas y la validación posterior rechazaba su salida.
Se corrigió la generación mediante `oneOf` por tarea, conservando el validador estricto
y un máximo de 512 tokens de respuesta. El diagnóstico sobre los mismos casos pasó
de 13/27 a 22/27 tareas sintéticas correctas (81,48 %); humanas 3/3. Se conservan
confirmaciones y cero escrituras nativas. Es una regresión funcional tras corregir
software, no una nueva muestra independiente ni una mejora estadística demostrada.
Los pesos y el ganador no se reajustaron a partir de esos resultados.

El registro común contiene el candidato
`1d9e4fff8149c5dbaee70597a5b9f016899d85c668daa55ed6dc2dd631ffd3e7`.
Se verificó mediante HTTP real en un servidor transitorio de loopback que la API
devuelve esa decisión bloqueada y `complete: false`. El servidor transitorio se
cerró; no se reinició la sesión web activa ni se alteraron trabajos PowerFactory.

El comando inicial terminó con código 2 al imprimir una flecha Unicode en la consola
CP1252, después de guardar entrenamiento, evaluación y registro completos. Se corrigió
la emisión JSON a ASCII escapado, se añadió su reproductor con consola ASCII y se
ejecutaron de nuevo la recarga y los ensayos con código 0. El error de presentación
se conserva junto al informe, sin reinterpretarlo como éxito del proceso inicial.

Todo el material de ejecución está en `output/destilacion_integral_20261031/`:
`corpus_final/`, `entrenamiento_final/`, `entrenamiento_v1/`, los logs y los informes
JUnit. `funcionamiento_hibrido.json`, `evaluacion_agente_hibrido.json` y
`evaluacion_agente_hibrido_schema_por_tarea.json` distinguen smoke, diagnóstico
inicial y regresión del esquema. `api_modelos_http.json` acredita la consulta HTTP.
Los datos humanos se mantienen locales y fuera de Git; el currículo y el
generador sí están versionados. La ejecución exploratoria v1 se conserva con
`auditoria_interrupcion.json`, `training_completed: false`, sin prueba final abierta.

El informe `entrenamiento_final/decision.json` distingue entrenamiento completado,
decisión de promoción, métricas, reapertura y funcionamiento. No confundir código
probado, entrenamiento, precisión suficiente, activación y aceptación eléctrica.
La falta de 200 órdenes humanas no impide experimentar, pero bloquea la promoción
de esta ejecución. Tampoco se declara validado el rechazo estadístico de consultas
fuera de distribución por probar unos pocos casos negativos.

Verificación final de código: 105 pruebas focalizadas, 35 de inventario/trazabilidad,
dos ayudas CLI, 11 regresiones CUDA del Transformer/destilación anterior y una prueba
CUDA del alumno calibrado por las APIs estándar: **154 pasaron, sin omisiones**.
La prueba adicional de persistencia exige un candidato local explícito y CUDA;
no forma parte de la instalación básica. No se ejecutó una nueva suite global ni
una aceptación eléctrica. La revisión independiente encontró cinco defectos
importantes (cobertura, correcciones, temperatura, salida inválida y estado web
obsoleto), reproducidos y corregidos con regresiones. La auditoría local adicional
detectó los conflictos sintéticos, la salida CP1252 y el esquema genérico.

## Fundamento consultado en la web

- **Maestría:** Konstantin Witossek (2025), Universität Leipzig/DLR,
  [*Knowledge Distillation of Large Language Models for Use Cases of the German
  Aerospace Center*](https://elib.dlr.de/220552/). Motiva comparar alumno destilado,
  maestro y baseline en una tarea concreta; su dominio no demuestra seguridad eléctrica.
- **Doctorado:** Yun Zhang (2025), HKUST,
  [*Knowledge Distillation for Generative Models*](https://researchportal.hkust.edu.hk/en/studentTheses/knowledge-distillation-for-generative-models/).
  Expone diferencias entre tipos de conocimiento y métodos de transferencia;
  no justifica afirmar que tenemos logits o capacidades que no se entrenaron.
- **Revista indexada:** Gou et al. (2021), *International Journal of Computer Vision*
  129, 1789–1819, [*Knowledge Distillation: A Survey*](https://doi.org/10.1007/s11263-021-01453-z).
  Fundamenta distinguir conocimiento, esquema de entrenamiento y evaluación.
- **Método de referencia:** Hsieh et al. (2023),
  [*Distilling Step-by-Step!*](https://aclanthology.org/2023.findings-acl.507/) y su
  [código oficial](https://github.com/google-research/distilling-step-by-step).
  Aquí se usa destilación de respuestas; no se anuncia implementada su tarea
  adicional de racionales ni se importa su entorno antiguo como dependencia.
- **Prevención de fuga:** Kapoor y Narayanan (2023), *Patterns*,
  [*Leakage and the reproducibility crisis in machine-learning-based science*](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856/).
- **Contrato técnico:** [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).
  El cliente envía JSON Schema y valida después tarea, campos y confianza;
  la validación determinista y las confirmaciones mantienen la autoridad de ejecución.
  La [documentación oficial de llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
  explica la restricción de no combinar `properties` y `oneOf` en el mismo nodo;
  [Ollama Modelfile](https://docs.ollama.com/modelfile) documenta `num_predict`.
