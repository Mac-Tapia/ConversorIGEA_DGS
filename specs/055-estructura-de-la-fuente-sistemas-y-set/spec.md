# Spec 055 — Estructura de sistemas y SET desde la propia fuente, para cualquier empresa

Estado: cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01, al cerrar la
prueba de Electro Oriente («después, para cerrar de Electro Oriente, debe ver si se cargaron
todos los alimentadores y sistemas y SET en la web para hacer cualquier conversión»; «de
cualquier empresa debería cargar todos los alimentadores, ya sea si se carga TXT, MDB y
VNR-GIS»).

## Contexto y objetivo

La web carga todos los alimentadores de una fuente (Electro Oriente: 168 de su VNR-GIS 2025,
todos convertibles), pero la estructura zonal → SET → alimentadores, que permite convertir un
sistema eléctrico o una SET entera (spec 022), solo sale de un Excel subido o del perfil de
empresa. El perfil activo es el de Electro Dunas, y con la fuente de Electro Oriente la web
mostraba 0 sistemas, 0 SET y los 168 alimentadores «sin SET», aunque la copia VNR-GIS trae su
estructura: cada salida con su SET (`CodSet`, con nombre) y su sistema eléctrico
(`CodSisElectrico`, con nombre).

Esta spec toma la estructura de la propia fuente cuando el Excel y el perfil no cubren los
alimentadores cargados, de modo que cualquier empresa tenga sus sistemas y SET sin configurar
nada.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA guardará con cada alimentador cargado lo que la fuente diga de su estructura:
  sistema eléctrico (código y nombre) y SET (código y nombre).
- RF-2: EL SISTEMA tomará la estructura, en este orden: el Excel que suba el operador; el perfil
  de empresa, si asigna SET a alguno de los alimentadores cargados; y si no, la de la fuente.
  La web dirá cuál usa.
- RF-3: CON la estructura de la fuente, cada sistema eléctrico será un zonal con sus SET, y
  cada SET con sus alimentadores; un alimentador sin SET en la fuente irá a un grupo «sin SET»
  de su sistema, convertible como los demás.
- RF-4: EL SISTEMA lo hará para TXT, MDB y VNR-GIS: la fuente que no traiga estructura dejará
  los alimentadores «sin SET», todos convertibles uno a uno o unidos, y se dirá.
- RF-5: Todos los alimentadores cargados aparecerán en la web y serán convertibles, tengan o no
  estructura.

Perfil de otra empresa (añadido el 2026-11-01: NJA202 de Electro Oriente se importó en la
carpeta «sistemaeletricoELD» de Electro Dunas, porque el perfil local hereda del suyo)

- RF-6: SI la fuente es de una empresa distinta de la del perfil de empresa, ENTONCES EL
  SISTEMA no le aplicará las convenciones de ese perfil (carpeta de DIgSILENT, CRS, SED de
  medición, escala) y lo dirá en la web.
- RF-7: EN ese caso, EL SISTEMA importará en una carpeta con el nombre de la empresa que dice
  la fuente (005:RF-2 a RF-5), y pedirá el CRS si la fuente no lo trae (002:RF-32).

## Relación con otras specs

- Completa la conversión por sistema eléctrico y por SET de la spec 022 (RF-1, RF-47 a RF-51,
  RF-82) y la fuente VNR-GIS de la 023.

## Criterios de finalización

- `grep -rnoE "055:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-5.
- Electro Oriente en la web con sus sistemas eléctricos y sus SET, y un sistema convertido por
  la web.
