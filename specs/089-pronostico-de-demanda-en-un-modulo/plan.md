# Plan — Spec 089

Lee: `docs/constitution.md`, 029, 046, 088.

| Parte | Cubre | Encaje |
| --- | --- | --- |
| `pronostico_demanda.py`: fuentes, equivalencia y curvas | RF-1 a RF-13, RF-35 a RF-37 | Capa adaptadores: lee por `demanda_medida` y no calcula con DIgSILENT |
| `pronostico_demanda.py`: limpieza | RF-18 a RF-28 | Sobre una copia de la curva: la lectura común no cambia |
| `pronostico_demanda.py`: clases | RF-16, RF-17, RF-29 a RF-34 | Objetivos con el contrato `Objetivo` de la 046 |
| `pronostico_demanda.py`: métodos y backtest | RF-38 a RF-51 | Sin GPU; no usa las ventanas de la 046, que exigen el horizonte sin huecos |
| `demanda_medida.curvas_de_clientes` | RF-14, RF-15 | Una responsabilidad, un sitio: sigue siendo el lector de esas hojas |
| `tools/pronostico_demanda.py` | RF-4, RF-5, RF-42 | Solo orquesta y escribe el informe |

## Decisiones

- **Un módulo nuevo; los modelos de la 046 no se mueven.** Moverlos rompería citas selladas de `docs/` y una spec cumplida. `objetivos_de_cabecera` y `objetivos_de_clientes` sí pasan aquí, y `temporal_entrenamiento` los importa.
- **El lector de clientes sigue en `demanda_medida`.** Duplicarlo en el módulo violaría P5, y el acceso a sus privados lo rechaza `test_capas`.
- **Backtest propio.** Con 28 días, las ventanas de la 046 quedarían casi vacías por los huecos de la limpieza; aquí se mide sobre lo observado.
- **Clases por tensión y no por SET.** La SET «CL» es de una empresa; a más de 35 kV ya no es media tensión en ninguna (P13).
- **Temperatura como climatología.** La medida futura no se conoce al emitir (046:RF-2).

## Pruebas

`tests/test_pronostico_demanda.py`: libros sintéticos con `openpyxl`, con número de alimentadores, clientes y meses sorteados; lectura y backtest reales con `CSG_DEMANDA_DIR`. No toca el lector de TXT, MDB ni VNR-GIS.

## Plan total de implementación

**Objetivo:** pronosticar kW y kVAR cada 15 minutos de cabecera, clientes fijos y escaladas con el mejor método medido a 28 días, actualizado cada mes sin tocar código, y llevar ese resultado a los sorteos de obras y a la proyección a años.

**Arquitectura:** todo lo nuevo en `pronostico_demanda.py` (capa adaptadores) y esta spec; los modelos neuronales se reutilizan por `digital_twin/adaptador_neuralforecast.py`. Los pronósticos nunca sustituyen a la medición (046:RF-20).

**Tecnología:** Python 3.12, pandas, neuralforecast 3.3 y PyTorch en CUDA para redes, LightGBM en CPU, Optuna ya instalado.

### Restricciones globales

- Datos base de 2026, que crecen cada mes; ni meses, libros, años ni códigos de empresa en código o pruebas (P13, RF-52).
- El apoyo 2023–2025 solo entra antes del primer dato base y nunca se evalúa sobre él (RF-35, RF-37).
- Fuera de la cuenta del tiempo de cómputo: hay un mes de plazo. Sí limita la GPU de 8 GB: cada modelo mide memoria antes de su corrida larga.
- Un modelo se promueve solo si supera al mejor perfil, con umbrales fijados antes de medir; si no, gana el perfil y se dice.
- Un trabajo pesado a la vez, por `turno_gpu`; DIgSILENT por `pf_arnes`. Commit solo con orden del usuario; `main` lo integra su responsable.

### Puntos que ninguna tarea cubre por sí sola y se prueban en la suya

1. Un mes nuevo a medias, con días sin dato: la serie sigue, y el último origen se mide solo sobre lo observado. Prueba en F0.
2. Un libro corregido que repite un mes: manda el más reciente y se dice cuántos instantes cambió. Prueba en F5.
3. Un cliente nuevo con pocas semanas: se aparta como historia insuficiente, y sus escaladas siguen. Prueba en F1.
4. Una maniobra que pasa carga entre alimentadores: el método no la toma como nivel nuevo sin aviso. Prueba en F1.
5. Falta de memoria en la GPU a mitad de corrida: ese modelo queda `ERROR_ENTORNO` y siguen los demás. Prueba en F2.

### F0. Cerrar la base (088 y T1 a T5 de esta spec)

- Repetir el backtest real con los dos errores corregidos y anotar sus cifras en T5.
- Revisar las series peores (WAPE mayor de 0,5) y las apartadas, y decidir con datos si son medidores o reglas.
- Declarar en el perfil las centrales que faltan al correr fuera del perfil local (`NA205`, y `PO101` si tiene).
- Ejecutar la suite completa con las nueve variables y sin omitidas. **Puerta:** ningún fallo nuevo frente a `main` c9c4d129.
- Hecho cuando: T1 a T5 marcadas y la 088 cumplida con evidencia.

### F1. Datos completos

- Medir los libros de clientes de 2025 con el lector y añadirlos como apoyo de clientes, con la misma regla de RF-35 y RF-36. Fichero: `pronostico_demanda.py`, `_curvas_por_cliente`.
- Marcar transferencias con `registros_de_maniobra` y comparar su efecto en el backtest; solo se quitan si mejoran. Se descartó quitarlas sin medir: marca miles de registros en algunas series.
- Probar los puntos 3 y 4 de arriba.
- Hecho cuando: el informe dice, por clase, cuántas series ganan historia y el WAPE antes y después.

### F2. Modelos potentes

Requisitos nuevos antes del código: horizontes de 1, 7 y 28 días; umbrales de promoción fijados y anotados con su huella antes de la primera medición.

- Interfaz en `pronostico_demanda.py`: `ajustar_modelo(nombre: str, objetivos: list[Objetivo], hasta: np.datetime64, horizonte: int, semilla: int) -> Modelo`, y `Modelo.predecir(objetivo: Objetivo, t_h, y_h, t_f) -> np.ndarray`. `backtest_objetivo` recibe `modelos: Mapping[str, Modelo]` y los mide en los mismos orígenes que los perfiles.
- Objetivo de aprendizaje: la relación entre la demanda y `perfil_anclado`, para no perder el nivel. Entrada: contexto, calendario, no laborables y nivel reciente. Salida directa de todo el horizonte, sin recursión.
- Un modelo global por clase y magnitud, reajustado en cada origen, con hasta 6 orígenes.
- Candidatos: N-HiTS, NBEATSx, PatchTST, TFT, iTransformer, TimesNet, TiDE, TSMixerx y BiTCN por `AdaptadorNeuralForecast`; GRU por `GemeloGRUMultihorizonte`; LightGBM directo, en CPU, añadido a `requirements.txt` con su versión.
- Etapas: (1) sonda de memoria y tiempo de cada modelo con pocos pasos; (2) búsqueda con Optuna (`digital_twin/hiperparametros.py`) en el primer origen; (3) corrida larga con 5 semillas; (4) reapertura en otro proceso y registro en `model_registry`.
- **Puerta:** por clase y magnitud, mejor que el mejor perfil en WAPE en el origen de prueba, sin peor máxima ni peor instante de máxima, con cobertura de q05–q95 entre 0,85 y 0,95.
- Hecho cuando: cada modelo y objetivo termina en un estado explícito, y el informe dice quién ganó o que no ganó ninguno.

### F3. Conjunto e intervalos

- Conjunto de los mejores modelos por objetivo, con pesos ajustados solo en los orígenes de elección. Compite como un candidato más, con la misma puerta.
- Intervalos conformales por horizonte, reutilizando `calibrar_intervalos`.
- Hecho cuando: gana o queda descartado con su evidencia.

### F4. Uso en obras y web

Parte de `entrega-087q`, porque toca `obras_pf` y `escalera_optima`; no empieza hasta que esa rama esté integrada.

- Sorteos con curva propia: `escalar` recibe factores por clase de carga, con cada fija por su curva, las escaladas por el resto de cabecera y las cargas nuevas constantes (decisión del usuario del 2026-11-04).
- Q de valle y sorteos con su propia curva, no atada a la P.
- Comparar sobre un proyecto de prueba, nunca sobre uno ya trabajado, y confirmar en DIgSILENT. **Puerta:** las obras válidas siguen pasando o el cambio se explica.
- Panel en la web por la API y por el asistente, como trabajo cancelable, probado en el navegador.
- Revisar con la máxima coincidente si hace falta el tramo julio–octubre: tres de sus alimentadores no operan.

### F5. Operación mensual

- Orden `actualizar`: al cargar un libro, inventario, limpieza y backtest de lo nuevo, y aviso de libros corregidos.
- Reentrenar cuando el error del mes supere al histórico de ese objetivo; promover solo por la puerta de F2.
- Registrar el error real de cada pronóstico emitido, mes a mes, frente a lo que después se midió.
- Temperatura: descarga mensual, con confirmación del usuario porque sale a un servicio externo; solo se envían coordenadas.
- Hecho cuando: con un libro nuevo real, todo corre sin tocar código ni configuración.

### F6. Proyección a años (requisitos en la 031)

- Solo con evidencia: backtest a 12 meses usando el apoyo 2023–2025.
- Cada registro de 15 minutos proyectado con exógenas medidas por ablación, no con (1+tasa)^n, comparado contra la tasa de la 029. Sigue siendo escenario, sin sustituir a la medición.
- Hecho cuando: gana a la tasa en un año no visto, o queda la tasa y se dice.

### Aparte, sin relación con la demanda

Probar el entrenamiento curricular del oráculo (NeurIPS 2021) subiendo `peso_fisico` por etapas. Spec propia, con las puertas de la 045, cuando la GPU esté libre.

### Orden y dependencias

F0 → F1 → F2 → F3; F4 necesita F2 e integrar `entrega-087q`; F5 necesita F2; F6 necesita F1 y F5. Una fase a la vez, integrando antes de la siguiente.
