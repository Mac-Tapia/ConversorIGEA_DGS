# Spec 003 — Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`)

Estado: retirada (2026-11-07, decisión del usuario) · Fecha: 2026-10-29

## Motivo

Retirada el 2026-11-07 por decisión del usuario («los archivos viejos debe eliminarlos, nada debe quedar en el proyecto
si ya no se usa»): la GUI ya se retiró en la spec 001 (RF-16) y la rama `feat/integracion-web-retiro-gui` era código del
paquete heredado del conversor con `NA205.dgs`, un fichero con datos de la distribuidora; solo el 6 % de sus líneas estaba
en `main` porque el resto lo sustituyeron la web y las specs posteriores. La rama nunca se subió; borrarla en local queda pendiente del permiso del usuario (la protección de borrados la detuvo).

Lo que decía la reserva:


El número lo citan la spec 002 y las notas del proyecto para lo que queda de la rama
`feat/integracion-web-retiro-gui`: diez commits que no se fusionaron y que van después de la
arquitectura por capas (002). No tiene requisitos todavía: se escribirán con la entrevista
del skill `convertersmartgrid-spec` cuando la 002 esté cumplida. Se reserva para que la numeración no
tenga huecos (033:RF-3) y nadie lo reutilice para otra cosa.
