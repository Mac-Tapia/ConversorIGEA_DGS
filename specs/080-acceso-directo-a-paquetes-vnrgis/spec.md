# Spec 080 — Acceso directo a los paquetes VNR-GIS de cada distribuidora

Estado: aprobada · Fecha: 2026-11-02

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

Aéreo o cable, el tipo y el estado de cada tramo (hallazgo H2 del auditor, 2026-11-14: todo tramo VNR salía aéreo, con la reactancia y la capacitancia de una línea, y un tramo fuera de servicio entraba energizado). Para toda distribuidora; reconstruir, no bloquear.

- RF-53: EL SISTEMA modelará cada tramo VNR-GIS como aéreo o cable según lo diga, por este orden, la fuente (el tramo o su tipo, también el tipo de red `CODTIPORED`: `A` aérea y `S` subterránea, comprobado en las copias de cuatro empresas, o una palabra que lo diga, en la copia de SQL Server y en los paquetes de capas; un valor sin regla no se adivina y se anota), la regla del perfil de la empresa (`vnr_patron_tipo_cable`, opcional), la capa de la fuente o la norma del tipo (código y descripción); SI nada lo dice, ENTONCES lo modelará aéreo; y CUANDO lo deduzca, lo anotará una vez por tipo con el método y los tramos.
- RF-54: EL SISTEMA pasará al resolvedor de conductores lo que el tipo VNR-GIS trae (R1, X1, R0, X0, ampacidad) y la tensión nominal del tramo, y completará lo que falte con valores de su medio (cable o aéreo), nunca con los del otro.
- RF-55: SI un tramo está fuera de servicio en la fuente (normalmente abierto en su estado de operación, o `EstadoVNR` proyectado `P` o eliminado `X` según la leyenda `ESTADO_VNR` de VNR-GIS, en la copia de SQL Server o en `ESTADO`/`ESTADOVNR` de un paquete de capas; existente, modificado y nuevo están en servicio, y un valor sin regla queda en servicio y se anota), ENTONCES EL SISTEMA lo conservará en la red abierto por sus dos extremos, con su propia maniobra si la tiene, y lo anotará: no entrará energizado. Una copia `.bak` ya restaurada se convierte al formato de archivo de la vía de capas (GeoPackage) sin un segundo ETL: se lee con el lector canónico de la vía SQL y solo se serializa el canónico, con los valores de la fuente tal cual (`ESTADOVNR`, `CODTIPORED`…); las reglas las aplica la vía de capas al leerlos, y SQL → GeoPackage → capas da el mismo canónico. Eso prueba la equivalencia y que la vía de capas funciona con datos reales; no prueba que un paquete de capas de terceros use `ESTADOVNR` o `CODTIPORED`, porque esos nombres los pone el conversor. Los paquetes VNR-GIS en disco (2026-11-14: un `.rar` y un `.zip` de dos distribuidoras, listados sin extraer) solo traen la copia `.bak` y el instalador, ninguna capa. Un paquete de capas se lee entero: cada capa (todas las de un GeoPackage, con sus campos, su recuento y su CRS) recibe su rol por sus campos y su nombre con la tabla de alias de la fuente (tramos MT, tramos BT, SED, nodos, equipos); las de tramos MT se unen, cada tramo con su capa, y si traen los nodos de sus extremos (`CODNODOMT_INI`, `CODNODOMT_FIN`) la red se une por ellos y no por cercanía; las de nodos, SED y equipos se leen al canónico (la SED como carga en su nodo; el equipo como maniobra, banco o regulador según su `TIPO`, y un `TIPO` sin regla se anota `EQUIPO_SIN_REGLA` con su recuento), y las de tramos BT también (cada tramo con su SED, su salida BT, el alimentador MT de la SED, su padre, su norma, su longitud, su estado, su tipo de red y su geometría; la copia de SQL Server los da por `btTramo`, `verTramoBT` y `btSalida`, halladas por sus campos y leídas solo cuando se pide la red BT, porque la conversión a un simulador modela la red MT; las reglas de estado y medio son las de MT, y lo que no tiene regla se cuenta aparte de MT), de modo que SQL → GeoPackage → capas da la misma red entera, no solo los tramos (`comparar_red`, que compara también cada tramo BT y su geometría); las de un rol que no se modela se anotan `CAPA_SIN_MODELAR` y las que no se reconocen, `CAPA_NO_RECONOCIDA`, con su nombre y su recuento, nunca en silencio. Los filtros que pide quien lee una capa se aplican como en los demás conectores (`equals`) o fallan con un mensaje claro; nunca se ignoran. Antes (51895566), `connectors/vector.py:38-63` daba una sola capa con el nombre del fichero y `read_layer` hacía `del layer, filters`.

Las puertas en la vía de producción (hallazgo H3, 2026-11-14: solo el CLI de VNR corría las puertas A–H; en la web no se veían las incidencias de G y H). Informan y no bloquean: lo que les falta se reconstruye (001:RF-17, RF-22).

- RF-56: CUANDO se cargue una fuente VNR-GIS, sea paquete o copia de SQL Server, EL SISTEMA evaluará las puertas A–H y dará su veredicto y sus incidencias en el resultado de la carga, sin bloquearla nunca, tampoco si la evaluación falla.
- RF-57: EL SISTEMA mostrará en el resultado de la carga en la web, y guardará en su inventario, las incidencias de las puertas, también las de G y H, con un resumen de una frase en palabras del operador, sin RF ni jerga: cuántos avisos, por qué y que no impiden convertir.
- RF-58: EL SISTEMA no dejará ningún cable VNR-GIS con capacitancia 0. La tomará de la ficha de fabricante del catálogo para su sección y su clase (8,7/15 kV y 18/30 kV) y, sin ficha, la calculará con la geometría del cable apantallado, C = 2π·ε0·εr / ln(Di/dc) (εr del XLPE de IEC 60287-1-1, tabla 3, según quickfield.com; espesor de aislamiento de IEC 60502-2), marcada «supuesta», y anotará `CAPACITANCIA_DEDUCIDA` con el método, la clase y la referencia. La clase del cable será, por tramo y por este orden: la que traiga la designación del tipo en la fuente (`CLASE_DE_LA_FUENTE`); la del cable cuya ficha dio la R y la X, para que el tramo sea un solo cable (`CLASE_COHERENTE_CON_RX`); y la de la tensión de fase de la red (`CLASE_POR_TENSION_DE_FASE`): la menor clase U0/U(Um) de IEC 60502-2 con U0 no menor que kV/√3 con la banda de ±5 % y con Um que cubra la línea con la misma banda (IEC 60183, 5.3); si con la banda no cabe ninguna, la de IEC 60502-2, tabla 1, para esa Um con las categorías A y B (33 kV: 18/30 kV). Lo confirma el usuario, 2026-11-14: «sus cables de 10 kV son N2XSY 8,7/15 kV» y «la clase debe ser por tensiones de fase».

Escala de la lectura de la copia de SQL Server (auditoría 3e, 2026-11-14: `modelo_canonico` buscaba la fila de cada salida, sus SED, sus enlaces, sus equipos y las normas de su tensión recorriendo las tablas enteras una vez por salida).

- RF-59: EL SISTEMA leerá la copia de SQL Server de VNR-GIS recorriendo cada tabla un número de veces que no dependa del número de salidas MT: las filas de una salida (su fila, sus SED, sus enlaces, sus equipos y las normas de los tramos de su tensión) saldrán de índices por salida construidos una sola vez, que conservan el orden de lectura.

Memoria de la lectura de la red BT (hallazgo del integrador, 2026-11-15: con `con_bt=True`, `leer_datos` hacía un `SELECT` de `btTramo`, `verTramoBT` y `btSalida` enteras y las guardaba con `fetchall` como diccionarios aunque se pidieran tres salidas; `modelo_canonico` solo filtraba después, y la memoria crecía con la empresa entera).

- RF-60: CUANDO se lea la red BT de una copia de SQL Server de VNR-GIS, EL SISTEMA la pedirá al motor por bloques de un tamaño fijo, que no dependa de la empresa, y guardará solo las filas BT de las salidas MT pedidas (por su código de VNR-GIS o el operativo): de las demás salidas BT, solo dónde cae su SED, y de los tramos sin salida MT, su recuento y sus ejemplos. Así la memoria crecerá con lo que se pide y no con la red BT entera. Antes de leerla, estimará su memoria con las filas BT de las salidas pedidas, contadas en el motor (con las salidas como parámetros), por los bytes por fila medidos; si la estimación supera la memoria libre, dará el aviso `MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE` con las filas, los bytes estimados y los libres, y seguirá leyendo por bloques (es un aviso, no un error; sin cuenta o sin saber la memoria libre, `MEMORIA_BT_SIN_ESTIMAR`). El modelo canónico y sus avisos serán los mismos que con las tablas enteras, y pedir después una salida cuya red BT no se leyó será un error, no una red BT vacía. CUANDO se exporte a capas una base entera (el CLI `bak-a-capas`), EL SISTEMA no tendrá en memoria el canónico entero: leerá la red MT una vez y la red BT una vez por tabla y por bloques, la guardará en un temporal en disco y armará y escribirá su capa por lotes de salidas MT y piezas de tramos de tamaño fijo, liberando cada una antes de la siguiente, sin una consulta al motor por salida. El pico de memoria de la cadena entera (lectura, modelo y GeoPackage) no crecerá con la red BT de la empresa, y el GeoPackage será el mismo que con el canónico entero: mismas capas, filas y atributos, y los mismos avisos. La estimación por `COUNT` (la memoria de dos piezas y el disco del temporal) se verá en el registro y, en el CLI, en la pantalla antes de leer, con «estimado X GiB, libre Y GiB»; si no cabe, `MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE` o `DISCO_BT_ESTIMADO_SUPERA_EL_LIBRE` (aviso, no error). El aviso de la lectura por salidas también dejará su línea en el registro. En esa exportación, la red MT tampoco estará entera en memoria: sus tablas se leerán una vez cada una, por bloques de tamaño fijo y sin una consulta por salida, y las que crecen con la empresa (tramos, vértices, SED, enlaces y equipos) irán al mismo temporal en disco; su canónico se armará por lotes de salidas MT de tamaño fijo, con la misma regla por salida que con las tablas enteras (una salida repetida en la tabla, entera en un lote), y las filas de sus capas se guardarán en el temporal para escribir después cada capa de una vez. El pico de la cadena entera no crecerá con la red MT de la empresa, y el GeoPackage, los avisos, el resumen y el canónico MT serán los mismos que con las tablas enteras.

## Fuera de alcance

- Convertir, calibrar o entrenar con estos paquetes: es la vía ya existente (specs 023 y 027).
- Una lista de empresas o de años escrita en el código o en la interfaz.
- Mezclar paquetes: cada uno sigue siendo una fuente aparte, en su espacio de trabajo.
- Instalar o ejecutar el instalador VNRGIS que acompaña al paquete.

## Criterios de aceptación

- En el navegador real, con el portal real: elegir Electro Sur Este y dejar `ELSE_VNR_22_REC.bak` asignada; elegir Luz del Sur y ver su paquete de la RCD 184-2026.
- La carga de esa copia por la web lista sus alimentadores.
