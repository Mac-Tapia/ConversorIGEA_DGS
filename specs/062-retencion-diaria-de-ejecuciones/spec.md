# Spec 062 — Retención diaria de ejecuciones y temporales

Estado: cumplida · Fecha: 2026-11-01

El usuario eligió revisar cada día y eliminar ejecuciones y temporales de más de
siete días. Amplía034/036/061: conserva originales, modelos e informes vinculados,
y sustituye la retención indefinida de ejecuciones obsoletas por esta política.

- RF-1: EL SISTEMA revisará los archivos gestionados cada24 horas mientras esté funcionando la web y recuperará revisiones vencidas al arrancar.
- RF-2: CUANDO revise una ejecución reconocida sin referencias vigentes y con todos sus archivos de más de siete días, EL SISTEMA retirará esa ejecución.
- RF-3: MIENTRAS existan trabajos en cola o en curso, EL SISTEMA aplazará la limpieza e impedirá una admisión simultánea al borrado.
- RF-4: EL SISTEMA conservará las ejecuciones activas, cargadas, reconstruidas o vinculadas mediante los metadatos de cualquier espacio.
- RF-5: EL SISTEMA limitará el borrado a ejecuciones y temporales gestionados dentro de su raíz web, rechazando enlaces de redirección y conservando originales externos, modelos e informes.
- RF-6: CUANDO retire temporales de las carpetas gestionadas, EL SISTEMA exigirá más de siete días de antigüedad y ausencia de referencias vigentes.
- RF-7: CUANDO termine o falle una revisión, EL SISTEMA conservará un resumen acotado con eliminados, conservados y errores, sin anunciar éxito ante errores de E/S.
- RF-8: CUANDO se consulte el monitor, EL SISTEMA mostrará la política, la última revisión y su próxima fecha, sin añadir sondeo periódico.

Fuera de alcance: limpieza de otros proyectos, edición de planos IGEA, borrado de
modelos o evidencia nativa, y tareas del sistema operativo cuando la web está apagada.
La antigüedad no prueba por sí sola que un archivo sea obsoleto. La revisión no
modifica fuentes ni el funcionamiento eléctrico.

## Fundamento científico

La [maestría de Ozen, Harvard](https://dash.harvard.edu/entities/publication/c73dfe9f-e3f6-48ba-bd48-d52559ed9ea2)
estudia reemplazo de cachés. El [doctorado de Cui, CityU](https://scholars.cityu.edu.hk/en/studentTheses/secure-deduplication-systems-with-advanced-applications/)
estudia deduplicación y seguridad de los datos. El [artículo de revista IEEE sobre
deduplicación](https://ieeexplore.ieee.org/abstract/document/7529062) fundamenta distinguir
datos únicos de redundancia. [Nectar, OSDI2010](https://www.usenix.org/conference/osdi10/nectar-automatic-management-data-and-computation-datacenters)
fundamenta proteger datos referenciados y trabajos concurrentes antes de recolectar
derivados regenerables. Siete días y24 horas son la elección del usuario, no umbrales
deducidos de esos estudios.
