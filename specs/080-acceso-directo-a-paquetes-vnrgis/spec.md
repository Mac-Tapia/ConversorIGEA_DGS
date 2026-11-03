# Spec 080 — Acceso directo a los paquetes VNR-GIS de cada distribuidora

Estado: cumplida · Fecha: 2026-11-02

## Contexto y objetivo

El usuario, 2026-11-02, tras localizar a mano los paquetes de Electro Sur Este y Luz del Sur: «en la
web también ponlo, esa ruta para acceso directo cuando se desee trabajar con VNR-GIS», para probar
con otras distribuidoras.

La web ya tiene «Buscar publicación oficial» (spec 001), pero no encuentra ningún paquete: busca en
las páginas anuales de resoluciones, y los paquetes están en las páginas de cada proceso VNR, en
tablas publicadas como HTML escapado. Además, el paquete oficial es un RAR o ZIP con la copia `.bak`
dentro (`DAT_VNR`), junto a instaladores. Asignado tal cual, se trataría como un paquete de capas y
no cargaría: la copia solo la lee la vía de la spec 023.

El objetivo es elegir la distribuidora en la web y dejar su copia lista para cargar, sin buscar
rutas a mano. VNR-GIS.md (D4) no admite una lista congelada de empresas o años: se descubren.

## Usuarios / actores

Ingeniero de planificación desde la web; el portal público de Osinergmin.

## Historias de usuario

- H1: Como ingeniero quiero elegir una distribuidora y tener su paquete vigente listo para cargar.
- H2: Como ingeniero quiero el enlace oficial del paquete a la vista, para abrirlo o citarlo.
- H3: Cuando Osinergmin publique un ciclo nuevo, quiero verlo sin que cambie el código.

## Requisitos funcionales (EARS)

Descubrimiento

- RF-1: CUANDO se busquen publicaciones, EL SISTEMA leerá de la página oficial del VNR de distribución las páginas de todos sus ciclos, sin ninguna lista de años ni de empresas.
- RF-2: EL SISTEMA leerá los enlaces de una tabla publicada como HTML escapado igual que los de una tabla normal.
- RF-3: EL SISTEMA clasificará como paquete VNR-GIS solo un archivo de datos de la sección VNR-GIS.
- RF-4: EL SISTEMA no ofrecerá como paquete de red los archivos de costos, los mapas de densidad ni los anexos de un informe.
- RF-5: EL SISTEMA dará a cada paquete el nombre de empresa de su propio enlace, aunque compartan fila varias empresas.
- RF-6: SI el texto del enlace no corresponde al nombre del archivo, ENTONCES EL SISTEMA usará el nombre del archivo como empresa (en 2026 el portal rotula «CVS Energía» el fichero `CVC Energia.zip`).
- RF-7: EL SISTEMA dará a cada paquete de un ciclo el año de su VNR y la resolución más reciente que cite su página.
- RF-8: EL SISTEMA guardará el nombre del archivo sin códigos de URL.

Vigente por empresa

- RF-9: EL SISTEMA marcará como vigente, por empresa, el paquete del VNR más reciente y, dentro de él, el de la resolución más reciente.
- RF-10: EL SISTEMA tratará como una sola empresa dos nombres del mismo ciclo cuando uno sea el comienzo del otro («Pluz Energia» y «Pluz Energia Peru»).

Web

- RF-11: MIENTRAS la entrada sea VNR-GIS, EL SISTEMA mostrará un selector con las distribuidoras encontradas.
- RF-12: CUANDO se elija una distribuidora, EL SISTEMA mostrará su paquete vigente con su VNR y su resolución.
- RF-13: EL SISTEMA ofrecerá en cada paquete una acción para descargarlo y usarlo.
- RF-14: EL SISTEMA mostrará en cada paquete su enlace oficial y el de la página de su resolución.
- RF-15: EL SISTEMA dejará ver las versiones anteriores de la empresa, sin ofrecerlas como primera opción.
- RF-16: SI al abrir la entrada VNR-GIS no hay ningún paquete en el catálogo, ENTONCES EL SISTEMA iniciará una búsqueda, una sola vez por apertura.
- RF-17: SI la búsqueda falla, ENTONCES EL SISTEMA dirá qué página falló y mostrará el enlace del portal oficial.

Descarga

- RF-18: CUANDO el paquete descargado contenga una copia `.bak`, EL SISTEMA extraerá solo la carpeta de esa copia y asignará la copia de red a la entrada VNR-GIS.
- RF-19: EL SISTEMA no extraerá de un paquete oficial ningún fichero que no sea `.bak` o `.config` al asignar su copia, y nunca ejecutará nada de lo que traiga.
- RF-20: SI el paquete no contiene una copia `.bak`, ENTONCES EL SISTEMA asignará el paquete como hasta ahora.
- RF-21: SI el espacio libre no alcanza para extraer la copia, ENTONCES EL SISTEMA lo dirá sin dejar ficheros a medias.
- RF-22: CUANDO se cancele el trabajo durante la extracción, EL SISTEMA parará sin dejar ficheros a medias.
- RF-23: EL SISTEMA encontrará el extractor de RAR aunque no esté en el PATH.
- RF-24: SI no hay extractor de RAR, ENTONCES EL SISTEMA lo dirá antes de descargar el paquete, sin reintentar.

Restauración

- RF-25: SI el motor de SQL Server no puede abrir la copia, ENTONCES EL SISTEMA dará permiso de lectura a la cuenta del motor solo sobre ese fichero y volverá a intentarlo.
- RF-26: SI ese permiso no se puede dar, ENTONCES EL SISTEMA dirá qué fichero y qué cuenta son y qué hacer.

Carga completa (usuario, 2026-11-02: «validar de cada empresa que lo cargado sea la totalidad de alimentadores, sin excepción alguna»; Electro Sur Este perdía 47 salidas con su SED)

- RF-27: SI todos los tramos de una salida tienen sus extremos en un mismo punto, ENTONCES EL SISTEMA la cargará igualmente, con un tramo mínimo, su SED y un aviso.
- RF-32: SI una salida tiene SED con coordenadas y ningún tramo, ENTONCES EL SISTEMA la cargará con un tramo mínimo en su SED, con el conductor más usado de su tensión y un aviso (`748055397` de Luz del Sur, 3 SED).
- RF-33: SI varios tramos raíz de una salida ya están en un mismo punto, ENTONCES EL SISTEMA seguirá la carga sin unirlos: por `11953196` no se cargaba ninguna salida de Luz del Sur.
- RF-34: DONDE la fuente cargada declare su CRS, EL SISTEMA lo usará antes que el del perfil de empresa, y lo que elija el operador prevalecerá sobre ambos (Electro Sur Este es WGS84 18S y Luz del Sur PSAD56 18S: suponer uno desplaza la red del otro).
- RF-28: EL SISTEMA no recortará el nombre de un alimentador a un último trozo solo numérico (`AN01-642-001` no es `001`: 498 salidas de Electro Sur Este se llamaban así).
- RF-29: EL SISTEMA dará una herramienta que cruce, por una consulta propia a la base restaurada, las salidas, los tramos y las SED con lo que lista la web.
- RF-30: SI una salida o una SED de la base no está en la web, y la salida tiene tramos o SED, ENTONCES esa herramienta terminará con error y la nombrará.
- RF-31: esa herramienta nombrará las salidas sin tramos ni SED, que no tienen red que cargar, y no las contará como fallo.

Equipos (usuario, 2026-11-03: «debes modelar todos los equipos que existen en los archivos, ya sean bancos, reguladores y otros; nada se debe omitir»)

- RF-35: EL SISTEMA modelará las celdas (`CE`) y las derivaciones de bóveda y de pedestal (`DB`, `DP`) como elementos de maniobra, con su estado de operación.
- RF-36: EL SISTEMA leerá la potencia de un banco de condensadores como el total de sus unidades: «3x200 kVAR» son 600 kvar, no 200.
- RF-37: SI un equipo es de un tipo que el lector no modela, ENTONCES EL SISTEMA lo anotará con su código y su tipo, en vez de perderlo en silencio.
- RF-38: EL SISTEMA modelará los bancos de regulación de tensión (`BR`) en serie en su tramo, con los datos de la leyenda de VNR-GIS (unidades, corriente y tensión), como `ElmVoltreg` en el DGS y con la toma en posición neutra.
- RF-39: EN la entrada VNR-GIS, EL SISTEMA no modelará los pararrayos (`PA`) ni los seccionadores cerrados (`SE`, `SF`, `SC`), y dirá cuántos dejó fuera de cada tipo (usuario, 2026-11-03: «no modeles los pararrayos ni seccionadores»).
- RF-40: EL SISTEMA conservará los seccionadores abiertos, porque definen dónde termina la red: Luz del Sur tiene 458 y, sin ellos, las ramas desconectadas quedarían conectadas.
- RF-41: EL SISTEMA anotará como deducidos el rango y los pasos de un `BR`, que la leyenda no trae.

Convergencia del «Caso base» (`TI01` de Electro Sur Este: 508 km a 22,9 kV; sus 14,5 MW son la potencia instalada por un factor fijo y no convergen)

- RF-42: EL SISTEMA tratará como demanda de relleno (057:RF-2) la de un alimentador cuyas SED tengan casi todas la misma proporción entre demanda y potencia instalada: seis razones o menos cubren el 90 % o más, con 20 SED o más (Electro Sur Este: solo 56 valores de kW en 11 813 SED).
- RF-43: EL SISTEMA buscará en la corrección de 057:RF-3 el mayor factor con el que el flujo converge sin tensiones imposibles, porque con ellas la importación se rechaza.

- RF-44: EN la entrada VNR-GIS, EL SISTEMA tratará como SED toda carga de la tabla `Sed`, sea cual sea el formato de su código: `004SED000188` y `12027990` no se reconocían, y sus alimentadores quedaban sin transformadores ni potencia instalada.

- RF-45: SI el flujo del oráculo sigue sin converger con la demanda de relleno corregida, o la demanda es propia de cada SED, ENTONCES EL SISTEMA reducirá por igual todas las cargas hasta el mayor factor con el que converge sin tensiones imposibles (015:RF-38, adelantado al oráculo como pide 057), conservará su reparto y anotará el factor. `C+æ02` de Luz del Sur: 10,77 MW en 105 km a 10 kV.

- RF-46: EL SISTEMA nombrará cada SED con su código operativo (`Sed.EtiquetaCampo`), no con el interno de VNR-GIS (`CodSed`), como ya hace con los alimentadores (056:RF-7): el usuario, 2026-11-03: «debe usar los códigos operativos, no los del VNR, de cada empresa».
- RF-47: SI varias SED comparten código operativo, ENTONCES EL SISTEMA añadirá un sufijo determinista a las siguientes y lo anotará; sin código operativo, conservará el de VNR-GIS y lo anotará.
- RF-48: EL SISTEMA contará los reguladores en lo que espera encontrar en DIgSILENT.

Sin mezclar empresas (usuario, 2026-11-03: «cada empresa debe ser con sus propios archivos, no debe mezclarse entre empresas»; `TI01` de Electro Sur Este usaba en 508,3 de 508,5 km filas añadidas al aparecer en Electro Oriente). Cambia 053:RF-8 («uno y universal») para la entrada VNR-GIS.

- RF-49: EN una copia VNR-GIS, EL SISTEMA leerá y ampliará el catálogo de conductores propio de la empresa que dice la fuente, y ningún fichero de catálogo llevará filas de dos empresas.
- RF-50: CUANDO una empresa no tenga catálogo, EL SISTEMA lo creará con una semilla que no lleve datos de ninguna empresa: R y amperios de la ficha del fabricante.
- RF-51: EL SISTEMA calculará la X de una línea aérea de la semilla por su geometría (radio del conductor y separación de fases de 1,2 m, a 60 Hz) y lo anotará, porque ninguna ficha de fabricante la da.
- RF-52: EL SISTEMA escribirá los reguladores a 60 Hz, como el resto de la red.

## Fuera de alcance

- Convertir, calibrar o entrenar con estos paquetes: es la vía ya existente (specs 023 y 027).
- Una lista de empresas o de años escrita en el código o en la interfaz.
- Mezclar paquetes: cada uno sigue siendo una fuente aparte, en su espacio de trabajo.
- Instalar o ejecutar el instalador VNRGIS que acompaña al paquete.

## Criterios de aceptación

- En el navegador real, con el portal real: elegir Electro Sur Este y dejar `ELSE_VNR_22_REC.bak` asignada; elegir Luz del Sur y ver su paquete de la RCD 184-2026.
- La carga de esa copia por la web lista sus alimentadores.
