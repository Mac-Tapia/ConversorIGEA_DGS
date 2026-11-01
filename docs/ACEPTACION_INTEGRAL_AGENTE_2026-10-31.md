# Aceptación del agente: propuestas, evidencia y dependencias

Trabajo autorizado: specs 047 T6 y 043 T6. La instalación, el entrenamiento,
la precisión del agente y la aceptación eléctrica tienen evidencias distintas.
Los planos de IGEA previos a la exportación permanecen fuera del alcance.

## Corrección del denominador

Las cinco anotaciones históricas de uso representan **tres textos humanos únicos**.
El conjunto histórico de 200 propuestas tenía **193 textos únicos**, dos textos
repetidos entre entrenamiento/prueba y 59 coincidencias con el entrenamiento
actual. Además, sus familias de plantillas ya participaban en el currículo.
Por ello no constituye un test independiente de 200 órdenes humanas.

Se materializaron **200 propuestas nuevas únicas**, distribuidas entre las 27
tareas del catálogo y 54 familias de plantillas. Sus parámetros y prefijos son
variantes correlacionadas: no equivalen a 200 familias independientes. La fuente
se identifica como maestro de sesión; ninguna fila se contabiliza como humana.
Los textos y grupos se contrastaron con el corpus real de entrenamiento antes de
evaluar. No se enviaron datos empresariales a proveedores externos.

- Corpus: `output/aceptacion_200_20261031/corpus/`.
- SHA-256 canónico de propuestas: `1971148f9223890e6ea0c67a1c011a815d992940a21b808671cec5cd59a21486`.
- Corpus previo de entrenamiento: `873832710f28e6c4f5ca7b995f2d92c48173ca9e985f27233642e44da8f78c29`.
- Generador versionado: `asistente/propuestas_maestro.py`; CLI `tools/aceptar_agente.py`.

RF-13 se corrigió: 200 propuestas no requieren inventar 200 observaciones humanas
para poder evaluar el uso asistido. Los umbrales de calidad se mantienen; toda
escritura sigue exigiendo confirmación. El requisito de muestra humana de 027 se
informa por separado. Esta corrección sustituye el bloqueo general por 200 humanas
añadido en la sesión anterior; no reescribe sus artefactos históricos.

## Selección y prueba realmente ejecutadas

La configuración se eligió usando únicamente 27 casos, uno por tarea, de la
partición de **selección anterior**. Las 200 propuestas quedaron fuera de ese
proceso. Se preservan tanto las configuraciones rechazadas como sus resultados.

| Candidato en selección | Acierto de tarea | F1 de datos | Decisión |
| --- | ---: | ---: | --- |
| Qwen2.5:3b, una etapa | 66,67 % | 57,14 % | No elegido |
| Llama3.1:8b, una etapa | 70,37 % | 54,17 % | Mejor acierto disponible |
| Qwen2.5:3b, dos etapas iniciales | 25,93 % | 13,33 % | Rechazado |
| Llama3.1:8b, dos etapas iniciales | 51,85 % | 44,44 % | Rechazado |
| E5-base, similitud de prototipos | 55,56 % | No aplica | No integrado; recall top-3 77,78 % |

El ensayo de dos etapas inicial usó un prompt que se simplificó posteriormente;
sus resultados no se atribuyen al prompt corregido. E5 fue una prueba de
recuperación, no un alumno entrenado ni un sustituto del benchmark completo.

Se repitió la selección ganadora con digest fijado antes de abrir las 200:
`llama3.1:8b`, digest
`46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`.
Temperatura 0, semilla 0, contexto 8192, máximo 512 tokens, esquema JSON por tarea
y revisión LLM obligatoria. No se activó esta configuración en el agente vigente.

La prueba completa produjo **157/200 tareas correctas (78,5 %)** y
**F1 de datos 86,46 %**. Las tres humanas se evaluaron aparte: **2/3 correctas**.
Informe individual: `output/aceptacion_200_20261031/evaluacion_llama/resultado.json`.
Se ejecutaron el intérprete y la resolución del plan; hubo **cero escrituras
nativas**. No se usó esta prueba para elegir hiperparámetros ni se entrenó con
sus errores. La muestra es sintética y no demuestra desempeño de campo.

**Resultado: uso asistido rechazado por calidad.** Las puertas declaradas antes
de la prueba exigen acierto ≥98 %, F1 ≥95 % y cobertura/calidad por cada tarea.
Tener 200 filas no compensa los fallos. No se promovieron pesos ni se habilitó
autonomía. La evaluación eléctrica sigue pendiente de ejecución y relectura nativas.

## Implementación y controles verificables

La web incorpora una consulta de solo lectura, `/api/asistente/aceptacion`, con
propuestas materializadas, sus textos, observaciones humanas únicas y resultado.
El registro anterior también cuenta textos humanos únicos, sin sumar duplicados.
Consultar la página no carga modelos ni ejecuta inferencia en la petición HTTP.
Una instancia del servidor iniciada antes del cambio requiere su reinicio normal
para disponer de la ruta nueva; no se interrumpieron trabajos de otras sesiones.

Se arrancó el servidor local actualizado cuando el puerto estaba libre y se
comprobó la ruta por HTTP real en `127.0.0.1:8765`: estado 200, 200 propuestas,
200 únicas, cinco registros humanos/tres textos únicos y aceptación asistida falsa.
La evidencia de lectura se conserva en `web_aceptacion.json`.

La CLI vuelve a contrastar el entrenamiento y el digest de pesos al evaluar,
exige la configuración elegida previamente y conserva informes anteriores.
Las puertas rechazan NaN, infinito, booleanos, valores fuera de rango y evidencia
incompleta por tarea. Las anotaciones comprueban procedencia, campos admitidos,
spans y hash individual. Si falla el revisor obligatorio, el alumno no lo elude
por declarar confianza alta.

El cliente que utiliza la web conserva `revisar_transformer`, `dos_etapas` y
`pensar` de la configuración medida, con tipos estrictos y compatibilidad con la
configuración anterior. Su prueba falló primero porque el lector descartaba esos
indicadores; se corrigió sin activar la configuración evaluada y rechazada.

## Instalación reproducible

El catálogo [MODELOS_IA_LOCK.json](MODELOS_IA_LOCK.json) fija los pesos seleccionados:
Qwen3:8b, Qwen3-4B para ajuste condicionado, E5-base, BGE reranker multilingüe y
nomic-embed-text. `tools/preparar_modelos_ia.py` audita por defecto; descargar es una
acción explícita. Comprueba tamaños y SHA-256 de pesos HF y digest Ollama. No
ejecuta código remoto ni activa candidatos.

Los nueve clones de [UPSTREAM_IA_LOCK.json](UPSTREAM_IA_LOCK.json) se verificaron
de nuevo. Para instalar los paquetes faltantes se guardaron las versiones previas
del núcleo y se usaron como restricciones de pip. La compilación de pymoo desde el
clone falló por ausencia de Visual Studio compatible; se descargó su wheel oficial
Windows de la misma versión 0.6.2. Esa distribución no se presenta como una
compilación comprobada del commit de desarrollo clonado. Los informes conservan
el fallo y la instalación que lo sustituye.

La instalación de pesos y bibliotecas se informa en los archivos de
`output/aceptacion_200_20261031/`; un proceso en curso o un archivo parcial no
acredita instalación terminada. El cierre de 043 T6 exige los informes completos
y operaciones reales de cada capacidad.

Se instalaron **33 paquetes** y `pip check` pasó. La comparación del inventario
antes/después confirmó **cero versiones previas cambiadas**. PyG 2.9.0,
NeuralForecast 3.3.0 y Pyomo 6.10.2.dev0 se construyeron desde sus clones fijados;
pymoo 0.6.2 usa wheel oficial Windows y HiGHS 1.15.1 su distribución oficial.
El [catálogo de dependencias](DEPENDENCIAS_IA_LOCK.json) conserva fuentes/hashes.
Las bibliotecas están declaradas en el extra `ml` de `pyproject.toml`; instalarlo
reproduce las dependencias de los adaptadores sin requerir la carpeta experimental
`output/ml_dependencies`. En un equipo nuevo hay que instalar primero Torch con
CUDA para Python 3.12 según su índice oficial; no sustituirlo por una build CPU.
Los directorios de compilación propios se preservaron bajo `output/` y las nueve
copias volvieron a pasar la verificación Git.

`tests_ml/test_dependencias_ia.py` y `tests_ml/test_reuso_github.py` ejecutaron
**nueve ensayos sin omisiones**: NSGA-II, solución LP con HiGHS, forward/gradiente
NF4 en CUDA, dos pasos de entrenamiento y predicción de cada arquitectura
GRU/NHITS/TFT/PatchTST, y los dos ensayos PowerFlowNet. Son fixtures de integración,
sin certificar precisión sobre demanda real. La comprobación de dispositivo se
registró durante el ajuste: Lightning devuelve los pesos a CPU al terminar.

Se instaló además **Ipopt 3.14.19** desde el
[binario Windows oficial](https://github.com/coin-or/Ipopt/releases/tag/releases%2F3.14.19),
SHA-256 `bd7818a19c2a627f1dcd538358833fbcb17c35080e19b4228be3f66cadf8c8fd`.
Una prueba adicional de Pyomo/Ipopt resolvió realmente una PNL con cotas y
restricciones. Su ruta está en el catálogo; `IGEA_IPOPT_PATH` permite otra
instalación sin modificar el PATH global. Esto acredita el solver, no la integración
eléctrica de 048. El método se apoya en
[Wächter y Biegler, Mathematical Programming (2006)](https://doi.org/10.1007/s10107-004-0559-y).

La revisión independiente confirmó dos defectos, corregidos con regresiones
observadas en rojo y después en verde: conservar etiquetas Ollama instaladas y
no elevar confianza de intención con la confianza de extracción de la segunda etapa.
Las transferencias reanudan prefijos de fragmentos y verifican el hash del conjunto
antes de publicar un blob; un parcial nunca se informa como modelo instalado.

`nomic-embed-text:latest` completó instalación y digest; una petición local real
produjo dos vectores de 768 componentes finitos. E5 ya se cargó en el ensayo de
selección y pasó la auditoría de pesos. Las primeras transferencias HF de Qwen3-4B
agotaron reintentos sin completar pesos; se sustituyeron por rangos IPv4 persistentes,
conservando sus registros. Los intentos fallidos no se contabilizan como instalación.
El inventario de E5 incluye también `1_Pooling/config.json`, necesario para reabrir
su arquitectura. El informe final debe contrastar todo el catálogo de nuevo.

Verificación de regresión: **230 pruebas pasaron, cero omitidas**, incluyendo
asistente, evaluación, inventario y trazabilidad; compilación TypeScript/Vite
correcta. No equivale a una nueva suite global del conversor ni a aceptación
PowerFactory. La reevaluación del alumno anterior se registró sin reentrenarlo:
`49faf8e6955d988c435f8427662134a93cbd99a6c9f774b90c04bf99299ddf5c`,
estado `RECHAZADO`; los motivos ya no confunden 200 propuestas con 200 humanas.

## Lo que falta para la aceptación integral

Actualización de la base de ajuste: se seleccionó
[`unsloth/Qwen3-4B-Instruct-2507-bnb-4bit`](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-bnb-4bit),
revisión `f12db89cd5156e090618dded9b4367f23f8f3b33`, licencia Apache-2.0 declarada,
NF4 con doble cuantización y arquitectura estándar `Qwen3ForCausalLM`, sin código
remoto. Los pesos principales ocupan unos 2,65 GB. Su variante FP16 inicial quedó
archivada en el catálogo y se conservaron sus parciales. La elección corresponde
a una GPU de 8 GB y PEFT; cambia el modelo de base y exige evaluación propia,
sin heredar precisión del original ni habilitar un ajuste de producción.
La compatibilidad metodológica se contrasta con
[la documentación oficial de bitsandbytes/Transformers](https://huggingface.co/docs/transformers/quantization/bitsandbytes).

La prueba adicional de E5 en CUDA falló con error Windows **1455**, de archivo de
paginación/memoria. El equipo tiene 16 GiB de RAM y en el diagnóstico quedaban
aproximadamente 0,5–0,6 GiB disponibles. No se acredita ese ensayo ni se cierra 043 T6.
Los nuevos ensayos comprueban recursos **antes** de cargar los modelos: 3 GiB libres
para E5, 4 GiB para BGE y 6 GiB para el paso NF4/LoRA. Falta de memoria es un fallo visible,
sin fallback ni omisión; no se cerraron aplicaciones ni servicios del usuario.
`tests_ml/test_pesos_ia.py` define la carga real de E5/BGE y un paso LoRA con recarga
en un proceso nuevo. Ese paso es una prueba de entorno, sin activación del adaptador.

El evaluador del agente exige 4 GiB de RAM disponible antes de abrir los datos o
cargar un modelo. Al terminar, libera únicamente el modelo de su ensayo; conserva
los demás modelos que Ollama tenga en uso. Los errores sucesivos conservan el
primer informe y devuelven el nuevo diagnóstico por consola, sin sobrescribirlo.
El catálogo rechaza rutas absolutas, unidades Windows y archivos sin una huella
válida antes de iniciar transferencias. La regresión de estos controles terminó
con **51 pruebas aprobadas**, sin omisiones (`controles_aislamiento_local_final.xml`).

BGE completó la descarga y pasó una auditoría local independiente del instalador;
evidencia `bge_verificado_local.json`. Sus pruebas de inferencia siguen sujetas a
recursos suficientes. El instalador continúa exclusivamente sobre el catálogo y
las rutas de este conversor; sus resultados están en `output/aceptacion_200_20261031/`.

| Alcance | Situación comprobada | Condición de cierre |
| --- | --- | --- |
| 200 propuestas | Materializadas y evaluadas, sin fuga exacta/de grupos con entrenamiento | Cumplir calidad; conservar prueba externa futura para nuevas iteraciones |
| Alumno destilado | Seis entrenamientos anteriores y reapertura acreditados; calidad insuficiente | Superar baseline y puertas por tarea sin entrenar sobre la prueba |
| Uso humano | Tres textos únicos observados | Ampliar observaciones reales representativas, sin sustituirlas por propuestas |
| Recuperación y revisión | E5 explorado; reranker/revisión por roles sin aceptación | Tareas 047 T2–T4, evaluación y evidencia correspondientes |
| Gobierno integral | Código y custodia parciales | Consolidar lanzadores pendientes y promoción común en 043 |
| Física/PINN/GNN | Contratos y adaptador disponibles | Benchmark independiente, ablaciones y aceptación nativa de 044–045 |
| Pronóstico y optimización | Datos causales y repositorios disponibles | Adaptadores, entrenamiento/evaluación y validación de 046–048 |
| Protecciones | Plan existente | Ejecución y evidencia de 049 con capacidades nativas |

Estas condiciones no desaparecen al instalar librerías o descargar pesos. El
estado canónico de cada spec permanece en su `spec.md`, con tareas abiertas.

## Fundamento consultado en la web

- **Maestría:** Witossek (2025), Universität Leipzig/DLR,
  [Knowledge Distillation of Large Language Models for Use Cases of the German Aerospace Center](https://elib.dlr.de/220552/).
  Sustenta comparar maestro, alumno y baseline para una aplicación concreta.
- **Doctorado:** Zhang (2025), HKUST,
  [Knowledge Distillation for Generative Models](https://researchportal.hkust.edu.hk/en/studentTheses/knowledge-distillation-for-generative-models/).
  Sustenta distinguir métodos y conocimiento transferido; no acredita capacidades no entrenadas.
- **Revista indexada:** Gou et al. (2021), *International Journal of Computer Vision*,
  [Knowledge Distillation: A Survey](https://link.springer.com/article/10.1007/s11263-021-01453-z).
  Fundamenta comparar esquemas de entrenamiento y evaluación.
- **Fuga de datos:** Kapoor y Narayanan (2023), *Patterns*,
  [Leakage and the reproducibility crisis in machine-learning-based science](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856/).
  Justifica separar conjuntos y procedencia; las verificaciones concretas son locales.
- **Referencia de implementación:** Hsieh et al. (2023),
  [Distilling Step-by-Step!](https://aclanthology.org/2023.findings-acl.507/),
  [código oficial](https://github.com/google-research/distilling-step-by-step).
  No se afirma implementar su supervisión multitarea de racionales.
- **Contratos técnicos:** [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs),
  [modelos BGE](https://huggingface.co/BAAI/bge-reranker-v2-m3),
  [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B),
  [instalación de solvers Pyomo](https://pyomo.readthedocs.io/en/stable/getting_started/solvers.html).
  La bibliografía justifica el método, sin sustituir pruebas eléctricas del conversor.
