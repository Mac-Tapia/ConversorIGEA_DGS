# Sustento técnico de RF-24 y RF-25

Consulta web: 2026-10-28. Esta revisión fundamenta los criterios eléctricos; la aceptación
del código se comprueba con pruebas y la aceptación eléctrica requiere ejecución nativa.

## Criterios aplicados

- **Distinguir máximas individuales y coincidentes.** Erickson (1980), tesis de maestría,
  distingue la suma de máximas individuales de la máxima coincidente del sistema por la
  diversidad de las cargas. RF-24 adopta la máxima propia de cada alimentador para un
  proyecto individual o unido; la calibración por sistema conserva la máxima de barra.
  Esta elección procede de la especificación del usuario: la tesis sustenta la distinción,
  no prescribe este CLI. Las máximas propias de varios alimentadores pueden corresponder
  a instantes distintos; su combinación no representa una máxima simultánea observada.
- **Vincular la estimación a mediciones y al alcance del modelo.** Seppälä (1996), tesis
  doctoral, combina modelos de carga y mediciones de la red para estimar la demanda.
  Carmona-Delgado et al. (2013) relacionan asignación de cargas y estimación de estado con
  curvas diarias y ventanas de mediciones. Estos trabajos sustentan usar las mediciones
  del periodo y de los alimentadores del proyecto registrado. No justifican inferir la
  pertenencia eléctrica únicamente de un nombre de archivo o proyecto.
- **Exigir evidencia de validación.** Pau y Pegoraro (2024) estudian la estimación con
  instrumentación escasa y evalúan su desempeño en una red de prueba desequilibrada.
  La consecuencia adoptada aquí es comprobar la validación nativa y detener la cadena
  cuando falla una etapa previa. Es un criterio de implementación del proyecto, no una
  equivalencia entre su calibración y el estimador WLS de ese artículo.

## Referencias

Erickson, G. D. (1980). *Peak demand cost management through load control* [Tesis de
maestría, University of Tennessee, Knoxville]. TRACE.
https://trace.tennessee.edu/handle/20.500.14382/37180

Seppälä, A. (1996). *Load research and load estimation in electricity distribution*
[Tesis doctoral, Helsinki University of Technology]. VTT Technical Research Centre
of Finland. https://publications.vtt.fi/pdf/publications/1996/P289.pdf
Ficha institucional y grado doctoral:
https://cris.vtt.fi/en/publications/load-research-and-load-estimation-in-electricity-distribution-dis/

Carmona-Delgado, C., Romero-Ramos, E., & Riquelme-Santos, J. (2013). Fast and reliable
distribution load and state estimator. *Electric Power Systems Research, 101*, 110–124.
https://doi.org/10.1016/j.epsr.2013.03.004
Registro de indexación PASCAL/INIST:
https://pascal-francis.inist.fr/vibad/index.php?action=getRecordDetail&idt=27419241

Pau, M., & Pegoraro, P. A. (2024). WLS-based state estimation for unobservable distribution
grids through allocation factors evaluation. *IEEE Transactions on Instrumentation and
Measurement, 73*, artículo 9003013. https://doi.org/10.1109/TIM.2024.3387498
Registro bibliográfico DBLP:
https://dblp.org/pid/14/9565.html

Se verificaron metadatos y resúmenes en repositorios institucionales y editoriales.
No se atribuye una revisión íntegra de las tesis ni la implementación de los métodos
de estimación descritos en estos artículos.
