# Spec 042 — «Con proyecto»: escalera de obras carga a carga y SET nueva para las que no caben

Estado: implementada · Fecha: 2026-10-31 · Origen: petición del usuario, 2026-10-31, tras revisar
NA203 + NA205 en DIgSILENT («para con proyecto debe usar la optimización, de proponer nuevas obras
por variaciones por cierta cantidad de cargas nuevas hasta donde se puede hacer las mejoras de
infraestructura física existente, y si ya no se puede se proponen nuevas para lo que ya no están
en las obras anteriores: nuevos alimentadores, traspaso de alimentadores a una nueva SET con un
trafo nuevo, proponiendo un diseño para las cargas totales nuevas y factor de seguridad y factor
de crecimiento para 30 años; a ese trabajo se debe conectar los tramos de NA203 y NA205; esos
tramos deben ingresar a la potencia de diseño del nuevo trafo; la ubicación debe ser la óptima
tomando en cuenta las caídas y ubicación de cargas»).

Respuestas del usuario (2026-10-31): las cargas entran de mayor a menor potencia; la SET nueva se
alimenta como red externa con los datos de la SET actual; el crecimiento es el medido de cada
alimentador (spec 029) a 30 años y el factor de seguridad va en el perfil; la ubicación es el
centro de carga de lo existente y de las cargas nuevas en bloque, con probabilidad por zona según
la tendencia de crecimiento.

## Contexto y objetivo

En NA203 + NA205 (2026-10-31), las 37 cargas nuevas del libro suman unos 30 MW sobre 11 MW
calibrados. Cada una sola converge, pero juntas dejan la red a 0,63 pu en «Cargas nuevas», y en
«Con proyecto» el flujo cae a una solución sin sentido físico: el consumo baja 10,5 MW al entrar
KANTU. La escalera de la spec 025 (bancos, regulador, nueva terna, cambio de sección) busca una
sola obra para todas las cargas a la vez, y con tanta carga ninguna variante es factible: no
queda nada aplicado ni se dice qué hacer con lo que no cabe.

Esta spec reparte las cargas nuevas en dos destinos: las que la **red existente mejorada**
puede atender con la escalera, y las demás, que pasan con tramos de NA203 y NA205 a una **SET
nueva**, dimensionada a 30 años y situada donde menos caída y menos pérdidas da.

## Requisitos funcionales (EARS)

Red existente mejorada, carga a carga (amplía 025:RF-44 a RF-77)

- RF-1: CUANDO el operador pide la optimización de «Con proyecto», EL SISTEMA ordenará las
  cargas nuevas de los alimentadores marcados de mayor a menor potencia y las añadirá una a una,
  cada una con su variación (007:RF-9).
- RF-2: CON cada carga añadida, EL SISTEMA buscará con la escalera de la spec 025 (variantes de
  bancos, regulador, nueva terna y cambio de sección, sorteos y menor costo anual) la obra que
  cumple con esa carga y todas las ya aceptadas; si la hay, la carga queda aceptada en la red
  existente.
- RF-3: CUANDO ninguna variante cumple con una carga, ENTONCES EL SISTEMA la destinará, con
  todas las que siguen en la lista, a la SET nueva, y la red existente quedará con la obra de
  la última carga aceptada.
- RF-4: EL SISTEMA aplicará en «Con proyecto» solo las obras de la última solución factible,
  cada una en su variación (025:RF-54), y nada en «Sin proyecto» (025:RF-44b).

SET nueva para las que no caben

- RF-5: CUANDO quedan cargas para la SET nueva, EL SISTEMA propondrá una SET nueva con un
  transformador nuevo de la tensión de alta de la SET de cabecera de los alimentadores
  marcados a su tensión de media, alimentada como red externa en su barra de alta con la
  tensión y la potencia de cortocircuito de esa SET.
- RF-6: EL SISTEMA trasladará a la SET nueva los tramos de NA203 y NA205 donde se conectan las
  cargas de RF-3: cada rama que las contiene se abre del alimentador actual en el tramo donde
  sale de lo que se queda y pasa a un alimentador nuevo de la SET nueva, con una línea desde la
  SET hasta ese punto, cada alimentador nuevo en su variación.
- RF-7: EL SISTEMA calculará la potencia de diseño del transformador nuevo como (demanda
  calibrada de los tramos trasladados + cargas nuevas de RF-3) × (1 + g)^n × factor de
  seguridad: g la tasa de crecimiento de cada alimentador de la spec 029, ponderada por la
  demanda que traslada; n la vida útil del perfil (`planificacion.vida_util_anios`, 30); y el
  factor de seguridad del perfil. Elegirá la menor potencia normalizada del perfil que la cubra.
- Aclaración de RF-5 y RF-7 (usuario, 2026-10-31: «para la SET considera los módulos de PIT»):
  la SET nueva y su transformador se eligen entre los módulos del Plan de Inversiones en
  Transmisión (configuración, relación de tensiones, potencia y costo de módulo), el menor que
  cubre la potencia de diseño; su costo es el del módulo.
- Aclaración de RF-5, RF-7 y RF-9 (usuario, 2026-10-31): los módulos salen del libro CAPEX de la
  empresa (en Electro Dunas, hoja `PyOTx27` y obras PIT: transformadores 60/22,9/10 kV de 15, 25 y
  40 MVA y la SET nueva completa), leídos con la configuración del perfil; el factor de seguridad
  es 1,25, en el perfil; y la SET nueva de NA203 + NA205 es la SET Copara que la empresa ya
  planifica en Nasca: se dimensiona y se ubica con RF-7 y RF-9, y se compara con la planificada.
- Aclaración de RF-7 (usuario, 2026-10-31: «la tasa es para mediciones registradas, ya sea fijas y
  medición de cabecera; las nuevas son fijas, no tienen tasa de crecimiento»): la potencia de
  diseño es (demanda trasladada × (1 + g)^n + cargas nuevas) × factor de seguridad. g es la de la
  cabecera (029) cuando hay dos años; si no, la de la POT registrada de las fijas del alimentador
  en los libros de clientes de dos años, con las fijas que tienen registro en los dos y su código
  anterior (tabla de suministros). Vale para cualquier proyecto, alimentador y empresa: NA203 +
  NA205 es el caso de prueba (usuario, 2026-10-31: «debe ser universal, no exclusivo de Nazca»).
- RF-8: SI falta en el perfil el factor de seguridad o la tabla de potencias normalizadas, o un
  alimentador no tiene tasa de la spec 029, ENTONCES EL SISTEMA dirá cuál falta y no supondrá un
  valor (P13).
- RF-9: EL SISTEMA situará la SET nueva en el punto que minimiza el valor esperado de Σ P·d:
  la demanda calibrada de las SED de los tramos trasladados, las cargas nuevas en bloque y,
  sorteada, la demanda futura por zonas, con más probabilidad de crecer donde se concentran las
  cargas nuevas del bloque (usuario, 2026-10-31: «centro de carga y la ubicación de nuevas cargas
  en bloque y hacer probabilidades a zona [donde] está la tendencia de crecimiento»).
- RF-10: EL SISTEMA comprobará en DIgSILENT, con la SET en ese punto, que las barras de media de
  los alimentadores nuevos y de los que quedan quedan entre los límites de tensión del perfil;
  SI no, ENTONCES acercará la SET a las barras que caen y volverá a comprobar, y SI ningún punto
  cumple, lo dirá con el que más se acerca.
- RF-11: EL SISTEMA creará la SET nueva, su transformador, la red externa, los alimentadores
  nuevos y las aperturas en variaciones propias, activas solo en «Con proyecto».

Informe y web

- RF-12: EL SISTEMA informará por carga nueva su destino (red existente con qué obra, o SET
  nueva); las obras de la red existente con su costo; y de la SET nueva: su punto (UTM y GPS),
  la potencia de diseño con cada término de RF-7, el transformador elegido, los alimentadores
  nuevos con sus tramos trasladados, la tensión mínima, las pérdidas y el costo si el libro
  CAPEX lo trae.
- RF-13: EL SISTEMA ofrecerá la optimización de «Con proyecto» en la web, en el paso de obras,
  como trabajo del carril de DIgSILENT, cancelable entre cargas.
- RF-14: CUANDO ningún módulo PIT cubra solo la potencia de diseño y el perfil admita
  transformadores en paralelo (`planificacion.transformador_set.unidades_en_paralelo_max`), EL
  SISTEMA elegirá el de menor costo con n unidades iguales (la SET una vez y n − 1 transformadores
  de su potencia) y creará la SET con esas n unidades; sin el dato del perfil, un solo
  transformador. (Usuario, 2026-10-31: NA203 + NA205 pedían 45,5 MVA y el mayor módulo de
  22,9 kV era de 40; «la a)», transformadores en paralelo.)
- RF-15: EL SISTEMA abrirá cada rama que pasa a la SET nueva en una barra de la red sin las cargas
  nuevas, la más cercana aguas arriba de las cargas que lleva, porque la obra se lee y se graba con
  esas cargas apartadas. (NA203 + NA205, 2026-11-01: la barra de CIMAS la crea la variación de su
  carga al partir un tramo, y la SET COPARA no se creaba con «no es del alimentador NA203».)
- RF-16: EL SISTEMA dejará el transformador de la SET nueva con el cambiador en carga regulando la
  barra de media a la consigna de la red externa de la cabecera actual, y en la toma fija que la
  deja más cerca de esa consigna, para que el flujo del caso la cumpla aunque no ajuste tomas.
  (NA203 + NA205, 2026-11-01: sin regular, 15 barras de media bajo 0,95 p.u. con la SET COPARA.)
- RF-17: CUANDO el operador pide la escalera primero, EL SISTEMA buscará carga a carga aunque las cargas pasen de `set_nueva_desde_kw` (063:RF-34); solo van a la SET nueva las que no quepan. Pisco (2026-11-03): 25,7 MW; el usuario eligió la escalera para saber qué resuelve cada obra.
- RF-18: CUANDO una carga que pasa a la SET nueva se conecta partiendo un tramo, EL SISTEMA tomará como barra de su rama el extremo más cercano de ese tramo, porque su nodo solo existe en la variación de la carga, apartada al leer la red. Pisco (2026-11-03): 6 de 13 cargas quedaban fuera de la SET con «no se halló su barra». Usuario: «debió entrar todo».
- RF-19: SI la obra de la SET nueva queda inactiva en un caso o falla al crearse, ENTONCES EL SISTEMA volverá a cerrar en ese caso los tramos y acopladores que abrió, y lo dirá: abrir es dato de operación y DIgSILENT lo guarda en el escenario, no en la variación de la obra. Pisco (2026-11-03): la obra quedó inactiva y sus 3 tramos abiertos dejaron 341 barras de AL209 sin tensión en «Con proyecto»; la corrida siguiente no halló camino desde la cabecera.
- RF-20: CUANDO las ramas que pasan a la SET nueva son de distintas tensiones de media, EL SISTEMA le pondrá una barra de media por tensión, cada una con su transformador desde la de alta y la potencia por devanado del módulo (el del CAPEX es 60/22,9/10 kV de 40/40/40 MVA); nunca une una rama a una barra de otra tensión. Pisco (2026-11-03): SI112, de 10 kV, quedaba en la barra de 22,9 kV.
- RF-21: ANTES de diseñar la SET nueva, EL SISTEMA agrupará las cargas que no caben por zona geográfica: ninguna a más de `planificacion.radio_zona_set_km` del centro de carga de su zona. Sin ese dato no se supone ninguno y se agrupan todas, como antes (P13). Pisco (2026-11-03): una sola SET para 13 cargas dejaba Salud Huaytará a 90 km y 120 km de líneas; usuario: «para el diseño debe tener en cuenta la ubicación geográfica».
- RF-22: SI una zona suma al menos `set_nueva_desde_kw`, ENTONCES EL SISTEMA le diseñará su SET nueva en su centro de carga; SI suma menos, ENTONCES la atenderá con un alimentador expreso desde la barra de media de la SET de su alimentador, con su tramo de entrada abierto y la ruta por las vías, y lo dirá por zona.
- RF-23: EL SISTEMA medirá «Con proyecto» con el plan completo: creará las obras de todas las zonas (primero los alimentadores expresos, después las SET nuevas) y hará un solo flujo con todas activas; SI converge, ENTONCES quedan todas; SI no, ENTONCES se apagan todas, se cierra lo que abrieron (RF-19) y se dice. Pisco (2026-11-03): cada expreso medido solo, con las cargas de las otras zonas sin resolver, no convergía nunca.
- RF-24: CUANDO el operador pide la escalera primero, EL SISTEMA la hará por alimentador, como siempre: cada alimentador con sus cargas nuevas, las de los demás apartadas, sube bancos, sección y terna; los que cumplen quedan con su obra en «Con proyecto» y las cargas de los que no cumplen pasan al alimentador nuevo o a la SET nueva por zona (RF-21 a RF-23). Usuario (2026-11-03): «las obras deben ser por alimentador como siempre: primero bancos, luego sección, ternas, nuevos alimentadores y si es necesario una SET nueva». La búsqueda de mayor a menor del conjunto (RF-2) paraba en la segunda carga y mandaba 13 de 14 a la SET.
- RF-25: EL SISTEMA dará a cada etapa nueva un segundo propio antes de la hora del estudio; SI ya no queda ninguno después de la última, ENTONCES tomará el libre más alto anterior, nunca uno usado. Pisco (2026-11-03): las 14 cargas nuevas y la etapa de fichas quedaron en el mismo segundo (hora − 1) y DIgSILENT no aplicaba las que parten un tramo: 5 de 14 no estaban en la red.
- RF-26: SI una fila está a 30 m o menos de una SED existente pero su demanda pasa de la potencia del transformador de esa SED, ENTONCES EL SISTEMA no la tomará como ampliación por distancia (040:RF-3) sino como SED nueva con su propio transformador, y lo dirá; por el nombre sigue siendo ampliación (040:RF-3, RF-5). Pisco (2026-11-03): SUREXPORT, 1 600 kW, quedó como ampliación de SE30380, de 100 kVA y 3 kW, y «Cargas nuevas» no convergía con ella.
- RF-27: DONDE el perfil dé `escalera.secciones_normalizadas`, EL SISTEMA solo propondrá cambio de sección a esos conductores, y de cada uno una sola variante (la de ficha si existe). Electro Dunas (usuario, 2026-11-03): aéreos AL 50, 120 y 240 mm² y subterráneo N2XSY 120 mm², los de su CAPEX y sus ratios; la escalera de Pisco probaba AA095, AA150 y CU070, y cada uno dos veces.
- RF-28: DONDE el perfil dé `escalera.cargabilidad_planeamiento_pct`, EL SISTEMA lo usará como límite de la escalera para los conductores de los alimentadores y para los transformadores de su SET, en la máxima con las cargas nuevas; si un alimentador no lo cumple con bancos, sección ni terna, pasa a alimentador nuevo (RF-22). Usuario (2026-11-03): «los alimentadores solo pueden cargar hasta 80 % de capacidad».
- RF-29: CUANDO aplica la escalera por alimentador, EL SISTEMA aplicará en cada uno solo la obra que eligió su evaluación, sin volver a evaluar sus variantes, y nada en el que ya cumple. Pisco (2026-11-03): la aplicación repetía las 40 variantes de cada alimentador con 200 sorteos, 32 min por alimentador.
- RF-30: SI un conductor de `escalera.secciones_normalizadas` no está en ninguna biblioteca a la tensión de las cargas, ENTONCES EL SISTEMA creará su tipo en el proyecto biblioteca con los datos de su ficha (o deducidos, spec 053) y lo ofrecerá en la escalera; y la combinación de sección y terna solo irá sobre el mismo camino (la doble terna del conductor nuevo), antes que las demás combinaciones. Pisco (2026-11-03): el AL 240 mm² nunca se probó porque no había tipo en la red, y AL209 y SI112 no cumplían; usuario: «240 mm2 doble terna».
- RF-31: CUANDO se pide con `tools/sistema_web.py --con-proyecto` sobre un proyecto ya calibrado, EL SISTEMA esperará el «Con proyecto» de ese proyecto que ya corra o lo lanzará, dirá por alimentador si ya cumple, su obra o que ninguna cumple, dejará el resultado en `--resumen-json` y la estadística de sus órdenes de DIgSILENT (081:RF-71), sin que nadie lo vigile. Usuario (2026-11-03): «lanza en DIgSILENT lo que falta del sistema de Pisco de forma automática».
- RF-32: ANTES de la escalera por alimentador, EL SISTEMA activará en «Con proyecto» las variaciones de las cargas nuevas de esos alimentadores que estén desactivadas, y dirá cuáles. Pisco (2026-11-03): una caída de DIgSILENT a mitad de una evaluación dejó apartadas 6 de 14; AL209 y SI112 se midieron sin sus cargas y sus barras salían «a ? p.u.», así que ninguna variante cumplía aunque la red estuviera descargada.
- RF-33: SI no hay libro CAPEX, no se puede leer o ningún módulo cubre la potencia de diseño, ENTONCES EL SISTEMA creará la SET igual: con el menor transformador normalizado que la cubre y el costo por MVA del módulo más parecido del libro, o sin costo si no hay ninguno, y lo anotará como por confirmar. Sustituye a «no se crea» y a pedir el libro. Usuario (2026-11-04): «no se puede aceptar una respuesta que no se puede, no existe en el CAPEX […] si falta se creará nuevo».
- RF-34: EL SISTEMA creará en el proyecto biblioteca los tipos de regulador del catálogo a las tensiones de la escalera antes de evaluarla, activándolo si DIgSILENT no deja escribir en él sin activar. Pisco (2026-11-03): todas las variantes con regulador fallaban con «No está el tipo VR32_10kV_50A» y SI112 solo tenía esas.
- RF-35: SI el camino a una carga nueva alcanza `escalera.linea_larga_km` (10 km si el perfil no lo da), ENTONCES EL SISTEMA planteará el regulador de tensión solo, combinado con cada escalón y con la doble terna, antes que las demás combinaciones, para que el tope de variantes no lo deje fuera. Usuario (2026-11-04): «si es muy larga la línea debería plantearlo, lo posible, incluso los reguladores de tensión».
- RF-36: CUANDO aplica obras, EL SISTEMA dejará en el informe de cada una sus elementos con las coordenadas de sus barras, en latitud y longitud y en el CRS del perfil. Usuario (2026-11-04): «todas las obras tienen que tener una ubicación óptima y georreferenciada […] estos cambios serán aplicados para los siguientes análisis, no es solo para este sistema».
- RF-37: SI el camino a una carga nueva alcanza `escalera.linea_larga_km`, ENTONCES EL SISTEMA probará además los bancos en la barra existente a 2/3 del camino, el punto que más reduce las pérdidas en una línea con carga repartida, y se queda la que mide mejor.
- Aclaración de RF-10 (2026-11-01): de los puntos probados queda el mejor (converge, menos barras
  fuera, mayor tensión mínima); si un paso empeora, se vuelve al mejor y se acerca la mitad. Antes
  quedaba el último, sin medir, y la SET COPARA acabó a 18 km de las cargas con 460 barras fuera.

## Relación con otras specs

- Amplía la escalera de la 025 (RF-44 a RF-77): allí una obra para todas las cargas; aquí carga a
  carga y, cuando ya no cabe, la SET nueva. Reutiliza sus variantes, sorteos y costos.
- Usa la tasa de crecimiento de la 029 y las cargas nuevas sin duplicados de la 040.
- Las aperturas reutilizan el enlace y el corte de tramos de la 016.

## Fuera de alcance

- La línea de alta hasta la SET nueva y la ampliación de la transmisión: la SET nueva es una red
  externa con los datos de la actual (usuario, 2026-10-31).
- Comprar el terreno: el punto es el óptimo eléctrico.

## Criterios de finalización

- `grep -rnoE "042:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-14.
- NA203 + NA205 desde la web: cada carga nueva con su destino; la red existente con obras que
  cumplen; la SET nueva con su punto, su potencia de diseño a 30 años y sus alimentadores, y
  «Con proyecto» convergiendo dentro de los límites de tensión.
