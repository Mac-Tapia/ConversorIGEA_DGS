# Notas de la versión

## 1.0.0rc6 (candidata, sin aceptar)

Candidata a la 1.0.0. Las notas completas de la publicación se instalan con el programa, en
`documentos\NOTAS_VERSION_1.0.0.md` de la carpeta del programa, junto al manual de instalación, el de órdenes y la guía para
que la pruebe una persona ajena. El menú Inicio abre el manual de instalación.

Cambia en el instalador:

- Los manuales y las notas quedan en la carpeta del programa: antes se borraban al terminar la instalación.
- La versión se escribe en un solo sitio, el paquete; el instalador la lee de su rueda, y «Acerca de» enseña solo estas notas.
- Al instalar sobre otra versión, esa queda registrada para volver atrás, también si era un rc que no lo registraba.

Pendiente de aceptar: la prueba en un equipo limpio, y las corridas en DIgSILENT con esta versión congelada.

## 1.0.0rc1 (candidata, sin aceptar)

Primera versión que se instala fuera del entorno de desarrollo.

- Instalador sin internet, con Python propio, y programa y datos en carpetas separadas.
- Actualización con copia previa de los datos y vuelta atrás.
- Orden `doctor` y pantalla de diagnóstico: qué falta, qué función afecta y cómo arreglarlo.
- Registro en ficheros rotativos y paquete de soporte sin datos del cliente.

Incluye: cargar la fuente y convertir; importar con «Caso base» verificado; calibrar; cargas nuevas; «Con proyecto» con escalera;
informes de estudio y de factibilidad con su Excel; estudios de flujo, N-1 y transferencia.

En beta, dicho en pantalla: asistente de órdenes, SET nueva, diagnóstico y borrador del PIDE, confiabilidad.

No existen en esta versión: cortocircuito y protecciones.

Pendiente de aceptar: la prueba en un equipo limpio, y las corridas en DIgSILENT con esta versión congelada.
