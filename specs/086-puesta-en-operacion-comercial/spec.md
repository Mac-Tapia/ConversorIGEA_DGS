# Spec 086 — Puesta en operación comercial: versión 1.0 instalable, segura y probada de punta a punta

Estado: aprobada · Fecha: 2026-11-04 · Origen: petición del usuario; aprobada con «sigue», tras avisar de que seguiría con lo recomendado en lo reversible

Cita: 002, 017, 025, 042, 047, 052, 055, 056, 058, 062, 065, 067, 072, 073, 077, 081, 083, 084, 085.

## Contexto y objetivo

Usuario: «has un plan de de tdo lo que falta y integarcion y listo para poner comnercial revsia bien profundo tdos el poeyecto y deja
lsito para implmentarlo todo». Cuatro revisiones de solo lectura sobre `f50146e8` (flujos, instalación y seguridad, universalidad, código y
modelos) dan la conclusión: el motor de ingeniería es sólido, pero **hoy es un árbol de desarrollo que corre en sitio, no un producto**.
Falta probar con el código final los flujos que se venderían, y faltan cosas que ninguna spec cubría: instalador, licencia, seguridad de la
web, durabilidad de los datos y separar lo que es de Electro Dunas.

El objetivo es una **versión 1.0** para una distribuidora, instalable en un equipo limpio, en la que cada flujo vendido se haya probado
en DIgSILENT real con el código congelado. Lo que no se venda queda apagado o marcado como beta, sin retrasar la entrada.

## Alcance de la 1.0

Se vende: cargar fuente y convertir; importar con «Caso base» verificado; calibrar; cargas nuevas; «Con proyecto» con escalera; informes
de estudio y de factibilidad con su Excel; estudios de flujo, N-1 y transferencia.

Como beta, desactivable y dicho en pantalla: asistente de órdenes (provisional, con confirmación, 085), SET nueva (con revisión de un
ingeniero), diagnóstico y borrador F01–F15 del PIDE, confiabilidad.

No se entrega activo: entrenamiento de modelos, revisión por roles (047 T8 no pasa su puerta), índice RAG 077, QLoRA, PINN, GRU, ciclo de
aprendizaje continuo, MADRL.

## Decisiones del usuario que este plan pide

Se marcan con su recomendación; hasta que se respondan, el plan sigue con la recomendación en lo que es reversible.

- D1 Alcance geográfico. Recomendado: **solo Perú** en la 1.0 (60 Hz, soles y normas peruanas siguen en el perfil o como jurisdicción).
- D2 Modelo de venta. Recomendado: **puesto local por licencia**, un equipo por operador, sin servidor multiusuario.
- D3 Repositorio. Hoy el repositorio de GitHub es **público y sin licencia** (comprobado el 2026-11-04). Recomendado: **hacerlo privado** y
  entregar desde un repositorio de producto con historia limpia. Los clones ya hechos no se recuperan.
- D4 Entrega. Recomendado: **empaquetada**, sin `tests/`, `specs/`, `.claude/` ni `.git`.
- D5 Comentarios con casos reales en el código entregado. Recomendado: **neutralizarlos en la línea de producto**, conservando el motivo
  sin el nombre del cliente. Choca con la regla de `CLAUDE.md` de citar el caso real.
- D6 Datos para las corridas: libro real de confiabilidad, fuente de «CA101 13», y qué hacer con PA217 en 025 T21 (es un proyecto vetado).
- D7 Asesoría legal: licencia comercial, DIgSILENT, datos de Osinergmin y Electro Dunas, modelos. **No es decisión técnica**: la revisión solo
  señala qué mirar.

## Requisitos

### Datos que no se pierden

- RF-1: CUANDO se guarda un fichero de estado, EL SISTEMA lo sincronizará a disco antes de reemplazar el anterior.
- RF-2: SI `workspace.json` está dañado, ENTONCES EL SISTEMA mostrará el espacio como dañado con la opción de restaurar su copia anterior.
- RF-3: SI una entrada apunta a un fichero que no existe al cargar, ENTONCES EL SISTEMA la conservará marcada como no disponible.
- RF-4: EL SISTEMA leerá la versión de `workspace.json` y lo migrará con copia previa, por pasos numerados.
- RF-5: SI `workspace.json` es de una versión futura, ENTONCES EL SISTEMA no lo sobrescribirá y lo dirá.
- RF-6: EL SISTEMA guardará las rutas de dentro del espacio relativas al espacio.
- RF-7: EL SISTEMA identificará la instalación con un identificador estable, independiente de la ruta.
- RF-8: CUANDO el destino está en otra unidad o en una ruta de red, EL SISTEMA publicará el resultado con un temporal junto al destino.
- RF-9: CUANDO se reinicia la web con trabajos a medias, EL SISTEMA los mostrará como interrumpidos, con su registro.
- RF-10: EL SISTEMA dará una orden de copia y otra de restauración de sus datos, con manifiesto.
- RF-47: SI la última copia supera la antigüedad configurada, ENTONCES EL SISTEMA lo avisará en la web.

### Informes veraces

- RF-11: EL SISTEMA ligará cada informe a la corrida que lo generó.
- RF-12: SI «Con proyecto» falla, agota su tiempo o se cancela, ENTONCES EL SISTEMA no usará un flujo anterior en el informe sin decirlo.
- RF-13: CUANDO se retoma una corrida, EL SISTEMA verificará el «Caso base» aunque no se importe de nuevo.
- RF-14: EL SISTEMA escribirá la huella del «Caso base» con la que 081 detecta que dejó de converger.

### Producto y seguridad

- RF-15: EL SISTEMA no lanzará la suite de pruebas ni entrenamientos en la edición de producto.
- RF-16: EL SISTEMA ocultará en la edición de producto lo que esté fuera del alcance de la 1.0.
- RF-17: EL SISTEMA rechazará las peticiones cuyo `Host` no sea de su lista.
- RF-18: EL SISTEMA exigirá un `Origin` propio en las peticiones que cambian algo y en el WebSocket.
- RF-19: EL SISTEMA exigirá un token de la sesión, entregado por el lanzador, en toda la API.
- RF-20: SI se pide escuchar fuera de `127.0.0.1` sin usuarios ni TLS, ENTONCES EL SISTEMA se negará y dirá por qué.
- RF-21: EL SISTEMA servirá sus páginas con su propio Leaflet y con una política de contenido.
- RF-22: EL SISTEMA no saldrá a la red por defecto en la edición de producto, y cada salida se activará de forma explícita.
- RF-23: EL SISTEMA clasificará cada tarea del asistente por su efecto: lee, usa licencia, sale a la red o escribe.
- RF-24: CUANDO una tarea usa licencia o sale a la red, EL SISTEMA pedirá confirmación.
- RF-25: EL SISTEMA pedirá confirmación antes de ejecutar un guion guardado en un proyecto.
- RF-26: EL SISTEMA reintentará solo los trabajos declarados idempotentes.
- RF-27: SI un modelo temporal no tiene GPU disponible, ENTONCES EL SISTEMA seguirá el trabajo sin ese modelo y lo avisará, en vez de fallar.

### Universal

- RF-28: EL SISTEMA tomará del perfil la moneda de informes y pantallas.
- RF-29: EL SISTEMA no mostrará en la web nombres ni tensiones de una empresa concreta como ejemplo fijo.
- RF-30: EL SISTEMA validará el perfil con un esquema, con una orden que diga qué falta y qué función afecta.
- RF-31: DONDE la empresa no trae modelo de informe, EL SISTEMA generará el informe con una plantilla neutra y lo dirá.
- RF-32: EL SISTEMA entregará un perfil plantilla y otro ficticio, sin el de Electro Dunas.
- RF-33: EL SISTEMA comprobará en cada versión que lo entregado no contiene términos de una lista prohibida guardada fuera de git.
- RF-34: EL SISTEMA no entregará pesos entrenados con datos de otra empresa.
- RF-35: DONDE el perfil no define las bandas y la tensión nominal, EL SISTEMA las pedirá en vez de tomar valores de una empresa.

### Instalar y operar

- RF-36: EL SISTEMA se instalará en un Windows limpio sin Node, sin pytest y sin salida a internet.
- RF-37: EL SISTEMA dará un núcleo sin torch y un complemento de IA aparte.
- RF-38: EL SISTEMA separará programa y datos, y su actualización conservará los datos con copia previa y vuelta atrás.
- RF-39: EL SISTEMA verificará sus dependencias por huella al instalar y nunca instalará al arrancar.
- RF-40: EL SISTEMA dará una orden `doctor`, y una pantalla, que digan qué falta, qué función afecta y cómo arreglarlo.
- RF-41: EL SISTEMA escribirá su registro en ficheros rotativos.
- RF-42: EL SISTEMA dará una orden que reúna un paquete de soporte anonimizado.
- RF-43: EL SISTEMA tendrá una sola versión, mostrada en la web y con sus notas.
- RF-44: EL SISTEMA dará manuales de instalación y de operador, una hoja de seguridad y privacidad, y las licencias de terceros.

### Aceptación

- RF-45: CUANDO se congela un candidato, cada flujo vendido tendrá evidencia en DIgSILENT, por la web y ligada a esa revisión, antes de aceptarlo.
- RF-46: La 1.0 se aceptará en un equipo limpio, con una empresa distinta de Electro Dunas y con un corte de luz simulado a media corrida.

## Fuera de alcance

Multiusuario en servidor, firma de código si D2 no la exige, otros países, cortocircuito y protecciones (049, que no existen y hay que
declararlo al cliente), mover los módulos a sus capas (002 T7 y T9), MADRL (074), aprendizaje continuo con datos reales (050), QLoRA (047 T7),
PINN (045 T3), optimización mixta (048), 072 T3 y T9, 027 T11 y T26, 071 T5.
