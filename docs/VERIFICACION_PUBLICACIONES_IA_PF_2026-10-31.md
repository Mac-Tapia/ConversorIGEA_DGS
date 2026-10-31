# Verificación de las publicaciones y del código — 31 de octubre de 2026

Alcance: revisión del código local y de contenido público, con un reproductor del
validador de alternativas. Esto no es una certificación de modelos entrenados ni una
aceptación eléctrica. Las mejoras quedan especificadas en el [plan maestro](superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md).

## Qué dicen realmente los enlaces

1. [Publicación de Muhammad Danish Ali, 30-10-2026](https://www.linkedin.com/posts/muhammad-danish-ali-8a6399176_physics-informed-neural-networks-pinns-activity-7521830770215415808-zlAx).
   Presenta un procedimiento general: formular la física y el dominio, construir la
   red, incorporar restricciones, entrenar, contrastar y utilizar el modelo. El enlace
   repetido de la solicitud corresponde a esta misma publicación. No contiene un
   benchmark del conversor ni demuestra superioridad en una red eléctrica concreta.
2. [Enlace corto proporcionado](https://lnkd.in/p/eFTvD7Zc), resuelto a
   [Kenny Felix sobre TradingAgents, 27-10-2026](https://www.linkedin.com/posts/kenny-felix-984778175_tradingagents-aitrading-opensource-share-7520793926341955584-m92u/).
   Describe revisión mediante roles y debate. Remite al
   [repositorio oficial TradingAgents](https://github.com/TauricResearch/TradingAgents),
   de ámbito financiero y licencia Apache-2.0. La idea transferible es separar evidencia,
   propuesta y crítica; sus resultados financieros no validan ingeniería eléctrica.
3. [Publicación de DIgSILENT, 30-10-2026](https://www.linkedin.com/posts/digsilent-gmbh_digsilent-powerfactory-featureoftheweek-activity-7521833098511056896-zxnv).
   El destino del enlace sobre funciones es la página oficial
   [Protection Functions](https://www.digsilent.de/en/protection-functions.html).
   Trata de protecciones, bibliotecas, coordinación, auditoría y reportes; no anuncia
   un PINN. Las funciones disponibles dependen de versión y licencia; no se presume que
   un anuncio con etiqueta PF2026 esté disponible en la instalación local.

El lector web de búsqueda no pudo abrir los enlaces de LinkedIn. Se verificó su HTML
público mediante HTTP 200 y sus metadatos JSON-LD, sin iniciar sesión ni eludir accesos.
Las URL resueltas y huellas HTML se guardaron en
`output/investigacion_ia_conversor_20261031/linkedin_public_metadata.json`. Este informe
versionado conserva las conclusiones aunque ese directorio local no se distribuya.

## Matriz de cumplimiento y brechas

| Aspecto | Evidencia en el código principal | Dictamen y mejora exigida |
| --- | --- | --- |
| Física explícita | `digital_twin/oraculo.py:residuo`, `_residuo_torch`, `barras_electricas` calculan balance AC y consolidan acopladores. | Existe para la representación admitida; documentar hipótesis y rechazar equipos no representados. Spec 045, T2. |
| Dominio y fronteras | `muestra` construye el grafo; `_red` fija la magnitud de fuente a su consigna y corrige una base física. | Parcial: falta contrato completo de controles y versión; fijar también referencia angular por componente energizada. Spec 045, T1–T2. |
| Condiciones iniciales | El oráculo aproxima flujo estacionario; no integra una trayectoria diferencial. | No aplican condiciones iniciales temporales a este problema algebraico. RMS/EMT y PINN dinámico requieren otra spec y datos de estados. |
| Red entrenable y física | `_entrenar_en` usa PyTorch, Adam, parada temprana y `MSE_datos + peso_fisico × residuo_cuadrado`. | Existe; falta historial separado de términos, ablación y prueba de gradientes del residuo frente a diferencias finitas. Spec 045, T2–T3. |
| Validación independiente | `oraculo.py:entrenar` usa validación para parada y calibración conforme, con alternativas a entrenamiento si faltan particiones. | Parcial: separar selección, calibración y prueba sellada; no promover con sustitutos de entrenamiento. Spec 044, T1–T2. |
| Escala temporal causal | `temporal.py:GemeloGRU.entrenar` calcula `max(abs(s))` antes de separar su validación interna. | Hay acceso de la transformación a valores posteriores al corte; ajustar escala solo con entrenamiento. Spec 046, T1. |
| Optimización verificada | `evolutivo.py:verificar_top_k` acepta diferencias cero cuando faltan valores de tensión o pérdidas. | Brecha reproducida: con una alternativa sin métricas y medición `{'converge': True}` devuelve `verificada=True`. Spec 044, T0 puntual y T3 integral, prioridad P0. |
| Casos nativos | `episode.py:Caso` y el schema v1 solo enumeran base, sin y con proyecto. La spec 037 incorpora «Cargas nuevas» en web. | Contrato de episodios incompleto frente a la web; schema v2 y compatibilidad de lectura v1, sin alterar sus hashes. Spec 045, T1. |
| Custodia y promoción | Existe buffer inmutable, consultas y aceptación por caso; el worktree de reentrenamiento contiene registro/coordinador adicionales. | Integrar selectivamente el donante, medir de nuevo y evitar un segundo registro. Spec 043. No se verificó aquí qué pesos están activos en el servidor. |
| Revisión por roles | Hay intérprete, plan, ejecutor y orquestador de tareas en `asistente/`. | No equivalen al debate por especialistas del enlace corto. Añadir revisión estructurada y acotada de fuentes/física/coste/riesgo sobre un mismo contexto. Spec 047, T3. |
| Protecciones | `studies.py` declara `protecciones/ComProtgraphic`; `_CURVAS_PROTECCION` explica la ausencia de curvas reales. `estudios_pf.py` no lo incluye en los estudios ejecutables de esta iteración. | Catálogo no equivale a implementación ejecutable. Añadir inventario, disponibilidad real, coordinación y reporte nativo condicionados a datos. Spec 049. |

El reproductor anterior solo demuestra un defecto del auxiliar `verificar_top_k`;
no demuestra que todos sus consumidores hayan publicado alternativas incompletas.
Los puntos de entrada deben auditarse en 044 T3 para que ninguno conserve otra
aceptación parcial. Las pruebas futuras deben citar `NNN:RF-n`.

## Verificación ejecutada en esta revisión

Se ejecutaron trazabilidad de specs y las pruebas existentes de episodio, evaluación,
evolutivos y particiones: **91 passed**, sin skips, en 12,74 s. También se comprobaron
los enlaces locales de los 23 documentos nuevos y los 65 RF nuevos tienen tarea.
Estas pruebas verifican el estado actual y la estructura del plan; no prueban las
mejoras aún pendientes. El reproductor del auxiliar sigue exponiendo el defecto hasta
que se ejecute 044 T0. No hubo entrenamiento ni simulación nativa en esta revisión.

## Fundamento y límites de aplicación

- **Maestría:** Zhang, S. (2024), *Physics-Informed Machine Learning with Applications
  to Power Systems*, UCR, [registro](https://escholarship.org/uc/item/4g839337).
  Justifica estudiar modelos con física y optimización; no determina los umbrales
  eléctricos del proyecto.
- **Doctorado:** Stiasny, J. B. (2023), *Physics-Informed Neural Networks for Power
  System Dynamics*, DTU, [tesis y DOI](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/).
  Apoya un diseño híbrido modular y advierte dificultades de escalabilidad; sus
  resultados dinámicos no son evidencia de aceptación del flujo estático local.
- **Artículo de revista:** Lin et al. (2024), *PowerFlowNet*, IJEPES 160, 110112,
  [texto publicado](https://publications.tno.nl/publication/34643410/FBJD74Um/lin-2024-powerflownet.pdf),
  [DOI](https://doi.org/10.1016/j.ijepes.2024.110112). Sustenta comparar GNN con
  métodos numéricos, sin trasladar sus aceleraciones a este conversor.
- **Doctorado de protecciones:** Wan, H. (2007), *Protection coordination in power
  system with distributed generations*, PolyU,
  [registro institucional](https://ira.lib.polyu.edu.hk/handle/10397/84834).
  Sustenta considerar aportes de generación y coordinación primaria/respaldo.
- **Artículo de revista de protecciones:** Aminian, M., Jafari Shahbazzadeh, M. y
  Eslami, M. (2024), *Distance optimization and directional overcurrent relay
  coordination using edge-powered biogeography-genetic algorithms*, Journal of
  Cloud Computing 13, 109, [artículo y DOI](https://doi.org/10.1186/s13677-024-00672-2).
  Motiva comparar optimizadores bajo restricciones de coordinación; no fija CTI,
  curvas ni ajustes de la distribuidora.

La investigación previa contiene otros artículos de revistas indexadas y repositorios
oficiales. Las publicaciones sociales sirven para identificar funcionalidades; el
fundamento técnico proviene de tesis, artículos y documentación del fabricante.
La aplicabilidad, los datos, las pruebas y la aceptación nativa siguen siendo locales.
