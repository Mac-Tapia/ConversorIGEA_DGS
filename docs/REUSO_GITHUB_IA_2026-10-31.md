# Reutilización de proyectos GitHub en el conversor

Consulta y ejecución: 2026-10-31. Contratos: specs 043 y 045–048.

Se descargaron nueve repositorios públicos en `external/upstream/`, separados del
código del conversor. El [catálogo fijado](UPSTREAM_IA_LOCK.json) registra URL,
commit completo, licencia revisada, ruta de licencia y SHA-256 de su blob Git.
Las copias conservan los avisos de sus autores y no se publican dentro del repositorio
padre. La licencia del código no acredita automáticamente licencias de pesos o datos.

## Selección y uso concreto

| Proyecto | Licencia revisada | Uso en el conversor | Estado comprobado |
| --- | --- | --- | --- |
| [PowerFlowNet](https://github.com/StavrosOrf/PoweFlowNet) | MIT | Candidato GNN de flujo, reutilizando `networks/MPN.py` desde el adaptador opcional de 045. | Clonado; forward, gradientes, descenso de pérdida y recarga de pesos se ensayan con CUDA. Falta benchmark y aceptación nativa. |
| [PyTorch Geometric](https://github.com/pyg-team/pytorch_geometric) | MIT | Motor de grafos del MPN original. | Clonado; paquete 2.9.0 construido desde esa revisión y utilizado por el ensayo. |
| [SafePowerGraph](https://github.com/LISTEnergyIntelligence/SafePowerGraph_Powergrid) | MIT | Referencia para métricas de seguridad y benchmark PF/OPF. | Clonado y verificado; falta revisar su contenido y adaptar el benchmark. |
| [NeuralForecast](https://github.com/Nixtla/neuralforecast) | Apache-2.0 | GRU, NHITS, TFT y PatchTST detrás del contrato causal de 046. | Clonado; paquete 3.3.0 construido e importación de las cuatro clases comprobada. Adaptador, entrenamiento y evaluación pendientes. |
| [pymoo](https://github.com/the-dual-space/pymoo) | Apache-2.0 | Optimización mixta, GA y NSGA-II para obras y equipos de 048. | Clonado y verificado; adapter y benchmark pendientes. |
| [Pyomo](https://github.com/Pyomo/pyomo) | BSD-3-Clause | Modelo algebraico de ajuste continuo y restricciones en 048. | Clonado; importación de `ConcreteModel` comprobada. Solver, integración y solución validada pendientes. Conservar además los avisos de terceros del repositorio. |
| [Sentence Transformers](https://github.com/huggingface/sentence-transformers) | Apache-2.0 | Recuperación local y reranking del asistente, frente a BM25, en 047. | Clonado y verificado; adaptación y benchmark pendientes. |
| [PEFT](https://github.com/huggingface/peft) | Apache-2.0 | LoRA/QLoRA local, solo si el corpus y el benchmark lo justifican. | Clonado y verificado; no se descargaron pesos ni se ejecutó fine-tuning. |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Apache-2.0 | Referencia para revisión por roles del asistente en 047. | Clonado para lectura. Su dominio financiero exige rediseñar contratos y criterios eléctricos; no se ejecutó su motor. |

Prioridad de integración: PowerFlowNet/PyG → NeuralForecast → pymoo/Pyomo →
recuperación y revisión por roles. SafePowerGraph aporta una referencia de evaluación.
PEFT queda condicionado a disponer de datos y demostrar una ventaja medida.

## Reproducir la preparación

Desde la raíz, con Python 3.12 y Git:

```powershell
.venv\Scripts\python.exe tools\preparar_upstream_ia.py --output-json output\upstream_preparacion.json
.venv\Scripts\python.exe tools\preparar_upstream_ia.py --verificar --output-json output\upstream_verificacion.json
.venv\Scripts\python.exe -m pytest -q tests/test_upstream_ia.py
```

La primera orden obtiene el commit fijado, no la última rama. Si una copia existente
tiene otra revisión, otro origen o cambios locales, se informa el problema y se
conserva. `--verificar` nunca descarga. La herramienta no instala dependencias ni
ejecuta scripts de los proyectos. Un informe con `ok: false` devuelve código 2.
`--destino` permite otra carpeta de clones y `--catalogo` un catálogo explícito.

## Adaptador PowerFlowNet implementado

`Entrenamiento(arquitectura='powerflownet')` selecciona el MPN original mediante
`digital_twin/adaptador_pyg.py`; `arquitectura='csg'` conserva el candidato vigente.
Antes de importar código ajeno se verifica su copia contra el catálogo. Las
dependencias Torch/PyG se cargan al seleccionar el candidato, sin impedir importar
el núcleo cuando no están disponibles. No se ejecuta `train.py` de PowerFlowNet.

El adaptador usa siete atributos del conversor, tres de rama y la firma común
`(x, aristas, atributos_rama) → (V, ángulo)`. Predice correcciones acotadas sobre la
base física e impone magnitud y referencia angular de las fuentes. Requiere dos
capas como mínimo. Es una adaptación de arquitectura: no importa pesos del artículo
ni presupone equivalencia con su problema o sus resultados publicados.

Ensayo explícito del entorno opcional usado localmente:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\output\ml_dependencies"
.venv\Scripts\python.exe -m pytest -q tests_ml/test_reuso_github.py
Remove-Item Env:PYTHONPATH
```

Ese directorio contiene dependencias experimentales locales, excluidas de Git;
no representa un entorno ML distribuible ya cerrado. Se utilizó Torch
2.14.1+cu126, CUDA y una RTX 4060 Laptop. Las dependencias de `.venv` permanecieron
iguales al inventario previo. La reproducción en otro equipo exige preparar y
validar su entorno ML; el catálogo de fuentes sí permite reproducir los clones.
No se añadieron dependencias obligatorias a `requirements.txt`.

`tests_ml/` se ejecuta explícitamente: requiere CUDA, las copias verificadas y PyG.
No usa skip ni sustituciones para acreditar esos requisitos. Respeta el bloqueo
GPU compartido. La suite ordinaria comprueba por separado que importar el núcleo
y el adaptador no carga Torch, PyG, NeuralForecast, pymoo o Pyomo.

## Evidencia y pendientes de aceptación

Evidencia local en `output/implementacion_ia_20261031/`:
`upstream_verificacion.json`, `clones_github.json`, `upstream_tests.xml`,
`reuso_github.xml`, `core_freeze_antes.txt` y `optional_versions.json`.
Los informes son regenerables; este documento y el catálogo son las fuentes
versionadas, aunque `output/` y los clones estén excluidos.

La tarea 043 T5 acredita la custodia de clones. No cierra 045 T3: faltan
particiones independientes, ablaciones física/red/híbrido, comparación por familia,
contraste con datos nativos y decisión de promoción. Tampoco cierra los adaptadores
de 046–048, los lanzadores pendientes de 043 ni protecciones de 049. No se modifican
planos de la distribuidora ni se envían datos de la distribuidora a GitHub o a servicios de IA.

## Justificación académica

La [tesis de maestría de Shaorong Zhang, UCR (2024)](https://escholarship.org/uc/item/4g839337)
y el [doctorado de Jochen Stiasny, DTU (2023)](https://doi.org/10.11581/DTU.00000277)
fundamentan estudiar modelos que combinan física y aprendizaje en sistemas eléctricos.
Sus trabajos sobre dinámica no acreditan por sí solos el flujo algebraico del conversor.

El artículo [Lin et al., *PowerFlowNet*, International Journal of Electrical Power
& Energy Systems 160 (2024), 110112](https://doi.org/10.1016/j.ijepes.2024.110112)
motiva reutilizar una arquitectura de paso de mensajes en lugar de reescribirla.
[Blank y Deb, *pymoo*, IEEE Access 8 (2020)](https://doi.org/10.1109/ACCESS.2020.2990567)
fundamenta el candidato evolutivo; [Lim et al., *Temporal Fusion Transformers*,
International Journal of Forecasting 37 (2021)](https://doi.org/10.1016/j.ijforecast.2021.03.012)
fundamenta evaluar el candidato temporal. Son publicaciones de revistas indexadas.

[Kapoor y Narayanan, Patterns (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856/)
justifican separar procedencia, entrenamiento y evaluación para evitar fugas.
La elección final depende de la evaluación local especificada, no de la popularidad
del repositorio ni de los resultados obtenidos por sus autores.
