# Ejecución de las mejoras de IA — 31 de octubre de 2026

Continuación del [plan maestro](superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md).
La instrucción del usuario de implementar autoriza la ejecución de los paquetes;
las casillas se cierran por evidencia, no por esa autorización.

## Implementado y probado

- **044 T0:** `verificar_top_k` rechaza métricas ausentes, NaN/Inf, booleanos,
  pérdidas negativas y tolerancias inválidas. Una predicción de pérdidas cero ya no
  oculta una pérdida medida distinta. Se conservan descartes y búsqueda de la siguiente
  alternativa. Esto corrige el auxiliar; la integración nativa completa de T3 sigue abierta.
- **043 T2:** contexto exacto e inmutable de experimento, SHA-256 canónico,
  configuración versionada y semillas/política selladas. Se integraron custodia,
  agrupación y auditoría de datasets del donante. No se infiere pertenencia desde
  sufijos de nombres de red; se conserva la identidad explícita del inventario.
- **043 T1, avance parcial:** registro inmutable, promoción atómica, reversión y
  comprobación de integridad de artefactos. Exclusión real entre procesos mediante
  guardia del sistema operativo, con metadatos de dueño. Se verificó Windows real;
  no se declara verificada la rama POSIX en este equipo.
- **043 T3, avance parcial:** `run --config ... --validar-config`, comparación de
  configuración al reanudar y huellas de contenido de entradas. El búfer se identifica
  por sus objetos JSON, no por un manifiesto inexistente. Un subproceso fallido o sin
  informe nuevo no hereda un éxito anterior; los informes previos se archivan.
  `verify --fail-on-incomplete` exige siete familias distintas y evidencia explícita
  de entrenamiento completado; un rechazo de promoción no demuestra entrenamiento.
- **043 T4, avance parcial:** API `/api/asistente/modelos` y tabla del asistente,
  sin inferir promoción del fin de un proceso. La consulta lee manifiestos; la
  promoción hace la comprobación completa de pesos con hashing en streaming.
- **046 T1, avance parcial:** GRU ajusta escala solo con entrenamiento. Preparación
  causal valida cadencia, fechas, zona, unidades y disponibilidad de covariables;
  conserva huecos con máscara y rechaza instantes duplicados. Hubo entrenamiento
  sintético con CUDA real; el ensayo con la curva medida se bloqueó correctamente.

## Datos reales consultados, sin modificación de las fuentes

Se construyó el inventario con `construir_dataset(almacen.raiz(), raiz_buffer())`:
1.106 registros, de los cuales 5 son `gold_human`, 875 contexto y 226 cuarentena.
No hay `gold_native` admisible para el dataset del asistente en esta lectura.
Los episodios sin evidencia suficiente conservan su cuarentena; no se reinterpretó
su aceptación para aumentar el número de ejemplos.

Se leyó la medición de NA203 con los lectores existentes de `demanda_medida.py`.
El libro es `0.2_SISTEMA Nasca.xls`, hoja `L-NA113`. La curva de septiembre de 2026
contiene 2.880 filas pero solo 2.850 instantes distintos: los 30 instantes duplicados
contienen valores de potencia diferentes. No se promediaron ni se eligió una fila
en silencio. No hubo promoción, cambio de libros ni escritura en PowerFactory.

Evidencia local privada en `output/implementacion_ia_20261031/`:
`inventario_datos_reales.json`, `curva_real_local.json` y `auditoria_serie_real.json`.
Los datos privados permanecen fuera de git. La auditoría se reproduce agrupando por
`instante` las filas de septiembre obtenidas por los lectores de cabecera existentes
y contando los grupos con más de un valor distinto; no se necesita alterar la fuente.

## Pendientes para el siguiente agente

| Paquete | Pendiente concreto |
| --- | --- |
| 043 T1 | Integrar todos los lanzadores legacy con la exclusión común; actualmente el coordinador protege sus etapas, pero no se afirma exclusión de todos los accesos históricos directos a CUDA. |
| 043 T3 | Adaptar/verificar los ejecutables de entrenamiento de cada familia en raíz: varios argumentos y herramientas del donante todavía no están consolidados. No lanzar el runner global esperando siete entrenamientos correctos. Reapertura real de artefactos de cada familia y publicación mediante el registro único. |
| 043 T4 | Prueba visual de la tabla con los cuatro estados y artefactos de referencia. API y build verificados; no se cierra la aceptación visual por ello. |
| 044 T1–T2 | Particiones independientes de entrenamiento/selección/calibración/prueba y puertas por familia integradas en el entrenamiento vigente. La reutilización actual de validación del PINN sigue pendiente. |
| 044 T3–T4 | Contexto, flujo/referencia, norma y persistencia completos en los consumidores top-k; prueba nativa después de reapertura. |
| 045 | Episodios v2 con «Cargas nuevas», grafo v3, controles/fronteras/residuos y ablaciones con contraste nativo. No se cambió el schema actual ni sus hashes. |
| 046 T1 | Resolver la custodia de los duplicados conflictivos o seleccionar una fuente observada inequívoca antes de cerrar el ensayo de entrenamiento con datos reales. No corregir planos IGEA ni inventar valores. |
| 046 T2–T3 | Adaptadores multihorizonte y benchmark temporal real con calibración y promoción; no están implementados NHITS/TFT/PatchTST. |
| 047 | Salida estructurada/entidades, reranker, revisión por roles y ajuste condicionado. Las cinco órdenes humanas no sustituyen las 200 reales exigidas para la evaluación prevista. |
| 048 | Problema mixto, adaptadores pymoo/PNL, comparación con presupuesto común y aplicación nativa. |
| 049 | Datos y licencia reales de protecciones, escenarios, coordinación, web y persistencia. Catálogo no equivale a estudio ejecutado. |

## Verificación y decisiones registradas

Verificación final focalizada: **225 passed, 45 deselected en 39,07 s**, incluyendo las regresiones
del asistente web, contratos, bloqueo, datasets, top-k, GRU/CUDA, episodios y
trazabilidad y **13 comprobaciones de inventario/documentación**. Los 45 casos de
`--help` de herramientas anteriores no se repitieron en esa selección; el `--help`
del runner nuevo se ejecutó y pasó por separado.
El build de frontend terminó correctamente. La API del servidor local en puerto 8765
respondió HTTP 200 y expuso el contrato de familias; no se reinició el servidor.
Estas comprobaciones no equivalen a la suite global ni a aceptación nativa.

Se observaron fallos antes de corregir el auxiliar, contratos ausentes, reutilización
de informes, huellas de entradas, bloqueo y normalización. Las regresiones ejercitan
subprocesos y bloqueo OS reales; CUDA se utilizó en los ensayos temporales. Los casos
nativos pendientes no se cerraron con dobles.

La revisión independiente encontró tres defectos importantes: carrera al recuperar
lock obsoleto, huella que omitía objetos del búfer y consumo de informe previo tras
fallo del subproceso. Los tres tuvieron prueba roja y corrección verificada. La
comprobación final tras esas correcciones fue mediante pruebas, sin segunda revisión.

- **Decisión:** continuar sobre el checkout compartido conservando parches existentes,
  porque las specs/fuentes activas de otras sesiones ya estaban presentes. Los commits
  concurrentes `896bf93b` y `3e423f95` incorporaron parte de los archivos durante la
  ejecución; se releyó el estado y no se revirtió su trabajo. Coste de esta decisión:
  la procedencia no se interpreta únicamente mediante `git diff`; hay que leer código,
  pruebas y este registro.
- **Decisión:** preservar informes previos de etapa con sufijo `previous.<id>.json`
  antes de ejecutar de nuevo. Coste: más evidencia local; evita atribuir un informe
  viejo al proceso nuevo.
- **Decisión:** cerrar 043 T2 por sus interfaces y evidencia de custodia comprobadas,
  mientras 043 T1 conserva pendiente la cobertura de lanzadores históricos. Coste:
  el contrato de datos disponible no habilita por sí solo el entrenamiento global.
- **Decisión:** la consulta web muestra la decisión registrada y valida manifiestos;
  la integridad completa de los pesos se verifica al promover, fuera de la petición
  HTTP. Coste: la tabla no certifica una nueva reapertura o rehash completo en cada lectura.
- **Decisión:** faltantes de entrenamiento y adaptadores no se completan mediante
  resultados históricos, datos sintéticos presentados como reales o sustituciones de
  arquitectura. Permanecen abiertos y se informa el bloqueo concreto.
- **Decisión:** el chequeo 009:RF-15 cuenta palabras una sola vez, conservando su
  criterio de uso de definiciones. La primera ejecución encontró un constructor
  público sin consumidor y documentación faltante; ambos se corrigieron. El
  normalizador usa ahora la fábrica pública validada. Coste: un cambio de rendimiento
  en la prueba de inventario, sin excepciones nuevas ni requisitos relajados.

## Fundamento científico

El protocolo conserva las fuentes del plan: [maestría de Zhang, UCR](https://escholarship.org/uc/item/4g839337),
[doctorado de Stiasny, DTU](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/)
y [PowerFlowNet, IJEPES](https://doi.org/10.1016/j.ijepes.2024.110112).
La prevención de fuga y la evaluación separada también se apoyan en
[Kapoor y Narayanan, *Leakage and the reproducibility crisis in machine-learning-based science*, Patterns (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856/).
Los defectos corregidos se sustentan en sus reproductores locales; estas referencias
justifican el método de evaluación, sin aportar una aceptación eléctrica del proyecto.
