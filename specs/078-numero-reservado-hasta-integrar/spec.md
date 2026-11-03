# Spec 078 — Número de spec reservado hasta integrar las ramas que lo usan

Estado: reservada

## Motivo

La 079 necesita que la numeración no tenga huecos (033:RF-3), y 078 lo usan a la vez dos ramas sin integrar: `feat/078-accesos-vnrgis`
(`078-acceso-directo-a-paquetes-vnrgis`) y `fix/senales-de-convergencia` (`078-senales-de-convergencia`). Esta carpeta es solo un marcador de
la rama `asistente/079`: al integrar cualquiera de ellas se borra, junto con su fila de `CLAUDE.md`. El choque de número entre esas dos
ramas lo resuelve el integrador.
