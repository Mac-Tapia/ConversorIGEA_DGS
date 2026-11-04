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
- RF-38: EL SISTEMA combinará los escalones de bancos, sección, terna y regulador también de tres en tres y los cuatro juntos, con la sección y la terna sobre el mismo camino, sin repetir ninguna; `escalera.max_variantes` de Electro Dunas pasa de 40 a 150. Usuario (2026-11-04): «debe ampliarse la cantidad de variantes, deben integrarse todas las obras para las soluciones».
- RF-39: SI al perfil, o a una empresa sin perfil, le falta un criterio técnico de planeamiento (límites de estudio, parámetros de la escalera, vida útil, tasa, horizonte o factor de la SET, tamaño de banco), ENTONCES EL SISTEMA usará el valor técnico de referencia y lo dirá como supuesto; lo que la empresa da nunca se pisa. Las convenciones de la empresa (CRS, patrón de SED, carpeta) se siguen sin suponer. Usuario (2026-11-04): «que no se pueda proponer obras, que no se pueda converger en otro análisis de otro sistema de cualquier empresa, todo esto debe ser implementado de forma robusta, estable». Sustituye a 025:RF-57 y a 042:RF-8 en «Con proyecto».
- RF-40: EL SISTEMA creará los conductores normalizados y los reguladores a la tensión que lee de cada alimentador, no a una tabla; sin lista de la empresa, los AAAC de 50, 120 y 240 mm². Con 13,8 kV o 33 kV la escalera tiene las mismas obras que con 22,9 kV.
- RF-41: SI un alimentador no tiene tasa de crecimiento, ENTONCES EL SISTEMA diseñará la SET con la media de los demás o, sin ninguna, con la tasa de referencia, y lo dirá.
- RF-42: SI un alimentador no tiene máxima, medidor o curva del año, o ningún instante tiene a todos medidos, ENTONCES EL SISTEMA evaluará las obras igual, a su demanda calibrada en la máxima y sorteando solo los medidos, y lo dirá.
- RF-43: SI con las cargas nuevas un tramo del alimentador pasa del límite de carga, ENTONCES EL SISTEMA añadirá a cada variante las ternas que ese tramo necesita para quedar bajo el límite, descontando lo que ya le dé la propia variante, y probará también ese refuerzo solo. Pisco (2026-11-04): un alimentador con cinco cargas en varios ramales tenía un tramo al 141 %; cada variante reforzaba un solo camino, las tensiones cumplían (0,97 p.u.) y ninguna podía cumplir.
- RF-44: EL SISTEMA buscará el camino eléctrico de cada carga nueva pasando por los acopladores cerrados y los demás equipos en serie, y solo las líneas de ese camino recibirán obras. Pisco (2026-11-04): el camino se buscaba solo por líneas, se cortaba en cada maniobra y ningún alimentador lo tenía; las obras se colocaban por cercanía GPS, y SI112 reforzaba una rama de 36 A que no era la de su carga de 58 A.
- RF-45: SI no hay camino eléctrico hasta una carga nueva, ENTONCES EL SISTEMA dirá que coloca las obras por cercanía GPS.
- RF-46: EL SISTEMA encontrará los tipos del proyecto biblioteca por el nombre con que se piden, aunque el proyecto conserve su nombre anterior. Pisco (2026-11-04): la biblioteca conservaba su nombre anterior, la obra pedía `CSG_Biblioteca_tipos` y todas las variantes con regulador fallaban con «No está el tipo»: el regulador nunca se había medido.
- RF-47: DONDE la lectura dé la tensión de las barras, EL SISTEMA planteará el regulador sobre el camino de cada carga: en el último tramo con la tensión dentro del límite y a mitad de la caída hasta ese punto, con la unidad que lleva la corriente del tramo bajo el límite de planeamiento. Usuario (2026-11-04): «tienen que integrarse los reguladores en puntos óptimos cuando bancos y sección no solucionan la caída de tensión».
- RF-87: EL SISTEMA sorteará primero `escalera.sorteos_etapa` flujos (50 si el perfil no lo da; 0 lo apaga) y solo seguirá hasta todos si la fracción queda entre `escalera.sorteos_decide_no` (0,90) y `escalera.sorteos_decide_si` (0,98). Usuario (2026-11-04): «un sistema con más alimentadores va a demorar mucho tiempo, debería ser más eficiente». En Pisco, 200 sorteos costaban unos 25 min por alimentador.
- RF-88: EL SISTEMA medirá la referencia sin obra de los sorteos solo cuando vaya a usarlos, y dirá en cada variante cuántos midió.
- RF-86: EL SISTEMA proyectará el alcance de RF-73 con `planificacion.crecimiento_demanda_anual`, o la tasa de referencia si el perfil no la da, y dirá la tasa medida en un aviso. Sustituye a la tasa del alimentador de RF-73: en AL209 salía 16,5 % al año, que a 20 años multiplica su demanda por 21. Usuario (2026-11-04): «haz la recomendación».
- RF-85: CUANDO una barra de un flujo de valle estaba en límites sin la obra y la obra la sube menos que `escalera.tolerancia_pu` sobre el máximo, EL SISTEMA no rechazará la obra por ello. Usuario (2026-11-04), a la pregunta de si se aplica esa tolerancia: «sí». Caso: una barra a 1,049 p.u. pasaba de 1,05 por milésimas, y la única obra que cumplía era una terna de 61 km.
- RF-79: CUANDO una pantalla de la web falla al dibujarse, EL SISTEMA dirá que falló y dejará recargar, en vez de quedar en blanco.
- RF-80: CUANDO las cargas van directo a la SET nueva, EL SISTEMA devolverá el mismo resultado que los demás flujos, para que la web lo muestre. Hasta ahora ese resultado no se veía.
- RF-81: EL SISTEMA ofrecerá las obras en escalera y «Con proyecto» siempre que haya una aplicación de cargas, converja o no: una red que converge con barras bajas también las necesita.
- RF-82: CUANDO un alimentador ya cumple, EL SISTEMA lo dirá en la web, en vez de «ninguna cumple».
- RF-83: EL SISTEMA mostrará en la web el diseño de cada zona de SET nueva y la variación creada con su error.
- RF-84: EL SISTEMA dejará escribir en la web el proyecto de transmisión que pide su mensaje de error, y el asistente mostrará el enlace del ZIP que anuncia.
- RF-76: EL SISTEMA dejará elegir en la web la evaluación por alimentador con sus alternativas, marcada por defecto, y rehacer las obras ya aplicadas, desmarcado por defecto. Hasta ahora solo se llegaba por la línea de órdenes: el botón corría el flujo anterior.
- RF-77: EL SISTEMA mostrará en la web, por alimentador, las alternativas con su costo, sorteos, valle, alcance y cuál se aplica, y aparte las del déficit previo y las sin comparación, avisando de que estas no están en «Con proyecto».
- RF-78: CUANDO la web abre un resultado del flujo por alimentador, EL SISTEMA lo mostrará sin exigir las pruebas por tandas, que ese flujo no tiene. Pisco: `e.pruebas.length` sobre un dato ausente rompía la página.
- RF-73: EL SISTEMA medirá cada alternativa de RF-55 con la demanda proyectada a `planificacion.horizonte_anios` (20 años si el perfil no lo da), con la tasa de crecimiento del alimentador, o con el factor de RF-70 si no la tiene; las cargas nuevas no crecen, porque su potencia es la solicitada. Usuario (2026-11-04): «sí me vale, sería para el horizonte de 20 años, su tiempo de vida útil de proyecto».
- RF-74: EL SISTEMA llamará definitiva a la alternativa con que, a ese horizonte, el flujo converge, todas las barras quedan en límites y ningún tramo pasa del límite de planeamiento; a la que no, temporal, con la mitad y la cuarta parte del horizonte medidas para decir cuántos años aguanta.
- RF-75: EL SISTEMA dirá el alcance de cada alternativa en el informe, sin cambiar su orden por costo ni la elección de RF-56. Usuario: «la más barata sería según los criterios de selección de priorización de alternativas».
- RF-71: EL SISTEMA dimensionará el regulador con el mismo factor que el elevador de RF-70, porque su corriente medida tampoco cuenta el crecimiento. Usuario (2026-11-04), por el integrador: «sí aplica para regulador 1.25» (086:RF-53).
- RF-72: CUANDO una alternativa lleva regulador o elevador, EL SISTEMA dirá en el informe el factor con que se dimensionó.
- RF-67: CUANDO presenta una obra de RF-64, EL SISTEMA dirá en el informe que no está en «Con proyecto» ni en sus flujos y que se midió con la máxima, sin sorteos.
- RF-68: EL SISTEMA evaluará aparte las barras sin tensión de comparación, rotuladas «sin comparación» y nunca «déficit previo».
- RF-69: EL SISTEMA dirá de cada alternativa si cumple en valle o si no se comprobó; la que no cumple en valle no se presenta (073:RF-40).
- RF-70: EL SISTEMA dimensionará el elevador de RF-61 con `planificacion.factor_seguridad_set_sin_tasa`, porque la corriente medida no cuenta el crecimiento (086:RF-51). Usuario (2026-11-04): «sí es 1.25 para transformador elevador».
- RF-64: SI tras la obra de la carga, o sin obra por cumplir ya, quedan barras bajo el límite que la carga no causa, ENTONCES EL SISTEMA evaluará una segunda escalera con esas barras como objetivo, sobre el camino a la más baja, y presentará hasta 3 alternativas. Usuario (2026-11-04): «si existe barra que ya estaba baja se presenta obra» (086:RF-52).
- RF-65: EL SISTEMA presentará esa obra aparte de la de la carga, con su propio costo, y no la aplicará en DIgSILENT: se mide con la máxima, sin sorteos, porque la máxima es el peor caso de tensión baja.
- RF-66: SI ninguna variante corrige esas barras, ENTONCES EL SISTEMA dirá la más cercana y lo que queda, con su motivo.
- RF-61: SI la SET no tiene barra a la tensión de destino y el alimentador comparte cabecera, ENTONCES EL SISTEMA planteará un transformador elevador dedicado en su salida, de la tensión de origen a la de destino, dimensionado para que la corriente del tramo de salida quede bajo el límite de planeamiento. Usuario (2026-11-04): en cabecera compartida se propone solución, no se deja sin obra. Aclara RF-53: el escalón se omite solo si RF-62 lo descarta.
- RF-62: SI el elevador pasa de 20 MVA o no se conoce el primer nodo de la salida, ENTONCES EL SISTEMA lo dirá con su motivo y seguirá hasta la SET nueva de RF-6.
- RF-63: CUANDO rechaza cambiar la tensión de un alimentador por compartir cabecera, EL SISTEMA dirá las obras que sí lo resuelven: celda nueva, elevador dedicado o SET nueva.
- RF-60: CUANDO el operador pide rehacer las obras, EL SISTEMA retirará de «Con proyecto» las variaciones `Obra_*` de los alimentadores marcados, solo esas, y los evaluará de nuevo; con el nombre de cada una en el informe. Pisco: las obras de tres alimentadores se eligieron por cercanía GPS, sin camino eléctrico (042:RF-44), y no había cómo repetirlas.
- RF-55: CUANDO la escalera por alimentador evalúa un alimentador, EL SISTEMA seguirá probando variantes hasta tener 3 alternativas de obras distintas que cumplan con la máxima, o hasta agotar las variantes. Usuario (2026-11-04): «debe presentar en el informe o PIDE por alternativas hasta 3 alternativas de solución por alimentador; el orden debe ser según el criterio de selección, evaluación económica, de menor a mayor».
- RF-56: EL SISTEMA elegirá para aplicar la alternativa de menor costo anual, salvo que los bancos solos basten (063:RF-22) y con el regulador solo si ninguna otra cumple (RF-49). Sustituye a 063:RF-22 entre los demás escalones.
- RF-57: EL SISTEMA sorteará las alternativas de menor a mayor costo hasta la primera que cumpla, y las demás quedarán marcadas sin sortear, para no gastar una medición entera en una obra que no se aplica.
- RF-58: EL SISTEMA dejará las alternativas de cada alimentador numeradas de menor a mayor costo anual, con su inversión, su costo anual y cuál se aplicó, en el informe de estudio, en el plan y en el PIDE.
- RF-59: CUANDO aplica la obra que la misma corrida acaba de sortear, EL SISTEMA no repetirá los sorteos. Pisco: 37 minutos por alimentador repetidos al aplicar.
- RF-50: DONDE un alimentador está a `escalera.migrar_desde_kv` (10 kV si el perfil no lo da), EL SISTEMA planteará pasarlo entero a `escalera.migrar_a_kv` (22,9 kV) como escalón propio, después de los bancos y antes de la sección. Usuario (2026-11-04): «en alimentadores de 10 kV se debe poner obras de cambios de nivel de tensión a 22,9 kV o migración a 22,9 kV».
- RF-51: SI la SET del alimentador tiene una barra a la tensión de destino a menos de 500 m de su cabecera, ENTONCES EL SISTEMA abrirá la salida actual, creará una celda nueva en esa barra hasta el primer nodo y pasará todo lo de aguas abajo, con los bancos, a la tensión de destino.
- RF-52: SI la SET no tiene esa barra y el alimentador no comparte cabecera, ENTONCES EL SISTEMA planteará el cambio de tensión del alimentador entero con su fuente.
- RF-53: SI la SET no tiene esa barra y el alimentador comparte cabecera, ENTONCES EL SISTEMA no planteará el escalón, lo dirá en un aviso y seguirá la escalera hasta la SET nueva de RF-6.
- RF-54: EL SISTEMA costeará el escalón por km del alimentador, por SED y por celda, con el libro o el perfil, y lo que falte se deducirá del cambio de sección o de un valor de referencia, y quedará marcado por confirmar.
- RF-49: EL SISTEMA planteará el regulador de tensión solo si el camino más largo a una carga nueva, o la troncal si no hay camino, pasa de `escalera.regulador_min_km` (15 km si el perfil no lo da). Usuario (2026-11-04): «los reguladores deben ser en casos extremos, en alimentadores largos mayores de 15 km». Aclara RF-35 y RF-47: dentro de ese largo sigue siendo el último escalón, y por debajo se dice en un aviso.
- RF-48: CUANDO la escalera por alimentador elige la obra de un alimentador, EL SISTEMA la aplicará en DIgSILENT antes de evaluar el siguiente. Usuario (2026-11-04): «una vez que termine un alimentador […] ya debería pasarlo por DIgSILENT y a la vez haciendo lo que continúa». Pisco: las obras se aplicaban todas al final, y una caída a mitad perdía lo ya resuelto.
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
