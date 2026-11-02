# Cierre verificable de la auditoría integral

Estado: aprobada (2026-11-02, implementación integral solicitada por el usuario)

## Motivo

La auditoría del 2 de noviembre encontró fallos de arranque, de control previo por grupos,
de almacenamiento temporal y de trazabilidad. El usuario autorizó ejecutar todo el plan
M0–M10 y confirmó que incluye el asistente LLM y su equipo. Esta spec enlaza las
correcciones y guardas; no amplía silenciosamente specs ya cumplidas.

## Requisitos

- RF-1: EL SISTEMA conservará un registro de candidato, propietarios, cambios, dependencias y evidencia por fase del plan M0–M10.
- RF-2: CUANDO termine el proceso web iniciado por el lanzador, EL SISTEMA devolverá su código de salida real.
- RF-3: SI falta un recurso local referenciado por la compilación web, ENTONCES EL SISTEMA rechazará esa compilación antes de abrir una instancia nueva.
- RF-4: SI falla una compilación, ENTONCES EL SISTEMA conservará la compilación completa publicada anteriormente.
- RF-5: SI un miembro de un grupo no supera el control previo requerido, ENTONCES EL SISTEMA impedirá solicitar la importación del grupo.
- RF-6: EL SISTEMA comprobará antes de importar el mismo modelo efectivo que produjo el DGS, con el mismo perfil y los mismos alias.
- RF-7: SI falla el cálculo del control previo requerido, ENTONCES EL SISTEMA bloqueará la importación e informará el motivo.
- RF-8: EL SISTEMA instalará el frontend desde su lock verificado y declarará las versiones compatibles de Node y npm.
- RF-9: EL SISTEMA ejecutará las pruebas frontend en rutas con espacios y sin espacios con el mismo resultado.
- RF-10: EL SISTEMA dirigirá sus cachés y temporales administrados a raíces externas al checkout, separadas por proyecto y ejecución.
- RF-11: CUANDO publique un artefacto de forma atómica, EL SISTEMA preparará su staging en el volumen de destino.
- RF-12: CUANDO termine o cancele un trabajo, EL SISTEMA eliminará solamente sus temporales administrados sin retirar fuentes originales, modelos, informes ni evidencia durable.
- RF-13: CUANDO revise restos tras una interrupción, EL SISTEMA seleccionará exclusivamente temporales con propietario, estado terminal y ninguna referencia vigente.
- RF-14: EL SISTEMA comprobará las dependencias y los drivers por capacidad antes de anunciarla disponible.
- RF-15: EL SISTEMA verificará Python 3.12 y mantendrá coherencia entre la instalación principal y los extras requeridos para arrancar.
- RF-16: EL SISTEMA detectará nuevas violaciones de capas, ciclos e importaciones privadas mediante una guarda reproducible con excepciones explícitas que no puedan crecer sin revisión.
- RF-17: EL SISTEMA detectará divergencias entre el esquema público de la API y los tipos de respuesta consumidos por el frontend.
- RF-18: CUANDO solicite una operación remota, inferencia, indexado o compresión prolongada, EL SISTEMA la tramitará como trabajo con progreso y cancelación.
- RF-19: EL SISTEMA limitará el almacenamiento temporal de cargas y descargas mediante presupuestos configurables por trabajo.
- RF-20: EL SISTEMA generará una matriz requisito → implementación → prueba → ejecución → pendiente sin considerar una cita vacía como evidencia.
- RF-21: SI falta evidencia eléctrica o científica de una spec, ENTONCES EL SISTEMA conservará su aceptación pendiente sin sustituirla por pruebas con dobles.
- RF-22: EL SISTEMA registrará las herramientas, roles y permisos efectivos del asistente LLM sin conceder capacidades por la mera presencia de un modelo.
- RF-23: CUANDO coordine el equipo del asistente, EL SISTEMA vinculará cada acción con su responsable, entradas, salida, decisión de revisión y límites de concurrencia.
- RF-24: EL SISTEMA verificará el candidato integrado mediante instalación reproducible, regresión, build y arranque aislado, conservando los fallos y las exclusiones.

## Relación con specs existentes

036: arranque; 057: bloqueo antes de importar; 062: retención de siete días; 002:
arquitectura y contrato; 027 y 043–050: asistente, evaluación y gobierno; 061:
operación; 064: exclusión del motor nativo. Sus RF siguen vigentes y no se cierran
por aprobar esta spec. Las tareas nativas y científicas requieren su propia evidencia.

## Fuera de alcance

No se borran datos originales ni se declaran obsoletos archivos por nombre/tamaño/hash.
No se publican datos empresariales ni se invocan LLM externos con esos datos. No se
emite certificación acreditada ni se inventan resultados eléctricos o científicos.

## Fundamento

Thomas (2017), tesis de maestría RWTH: https://swc-rwth.de/theses/software-architecture-conformance-analysis-large-scale-industrial-case-study/

De Silva (2014), tesis doctoral St Andrews: https://research-repository.st-andrews.ac.uk/handle/10023/5220

Li, Liang, Soliman y Avgeriou (2022), artículo en Journal of Software: Evolution and
Process: https://doi.org/10.1002/smr.2423

Justifican combinar conformidad estática, comportamiento observable y control de
deriva; no certifican este producto ni sus modelos. Consulta web: 2026-11-02.
