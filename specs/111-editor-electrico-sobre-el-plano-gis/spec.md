# Spec 111 — Editor eléctrico sobre el plano GIS, con los resultados en el mismo trazo

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-32, BP-10 y BP-11, y orden del usuario del
2026-11-14: «haz nuevos spec». G0: `D:/csg/G0_PLAN_MAESTRO/G0_UX_RUTAS_Y_WIREFRAMES.md` y `B/B_FILAS_BP.md`.

## Contexto y objetivo
El conversor conserva los vértices GPS reales de cada línea (010). La web, en cambio, solo muestra los resultados en
tablas, y el mapa coloreado solo existe como imagen en el informe (017:RF-124). No hay ningún editor de topología ni de
equipos (G0: BP-10, BP-11 y BP-32). El operador quiere ver y operar la red sobre el plano real:
- ver la red;
- seleccionar un equipo por su código;
- proponer una maniobra o una obra;
- correr el estudio;
- ver la tensión, la corriente y la cargabilidad sobre la misma polilínea.

Todo esto sin tocar nunca el caso base ni la geometría de la fuente.

## Usuarios / actores
- El ingeniero de redes y el operador, en la web.
- El revisor, que compara dos casos.

## Historias de usuario
- H1: Como ingeniero, quiero ver el alimentador sobre su trazo real, seleccionar un tramo o una SED y ver sus datos de
  origen, lo que se dedujo y su estado.
- H2: Como operador, quiero abrir o cerrar un seccionador o proponer un tramo nuevo como variación, correr el flujo y
  ver los resultados pintados sobre el mismo trazo.
- H3: Como revisor, quiero comparar dos casos sobre el mismo plano.

## Requisitos funcionales (EARS)
- RF-1: EL SISTEMA mostrará en la web cada alimentador sobre la secuencia de vértices de su fuente, sin simplificar
  la geometría que se calcula. Un nivel de detalle solo gráfico se permite, y es reversible.
- RF-2: EL SISTEMA identificará cada elemento con el mismo código en el plano, la tabla, el inspector y los
  resultados.
- RF-3: CUANDO el operador seleccione un elemento, EL SISTEMA mostrará su dato original, lo que se dedujo y por qué,
  y su estado de calidad.
- RF-4: CUANDO el operador cambie el estado de un interruptor o de un seccionador, EL SISTEMA lo guardará como
  variación del escenario y nunca en el caso base.
- RF-5: CUANDO el operador trace un tramo nuevo, EL SISTEMA guardará sus vértices tal como los dibujó, como variación,
  con la longitud GIS y la longitud eléctrica por separado.
- RF-6: SI dos tramos se cruzan en el plano sin un nodo ni un equipo que los una, ENTONCES EL SISTEMA no los
  conectará.
- RF-7: CUANDO el operador ajuste un extremo a un nodo cercano, EL SISTEMA lo mostrará como propuesta, con la
  distancia de desplazamiento, y solo lo aplicará con su confirmación.
- RF-8: CUANDO el operador inserte un equipo, EL SISTEMA validará su tensión, sus fases y su conexión antes de
  aceptarlo, y dirá qué falta.
- RF-9: EL SISTEMA permitirá deshacer y rehacer las ediciones de una variación que aún no se ha confirmado.
- RF-10: CUANDO termine un estudio, EL SISTEMA pintará sobre las mismas polilíneas la tensión por barra, la corriente
  y la cargabilidad por tramo, y el estado de cada equipo, con su leyenda, sus unidades, su umbral y el caso.
- RF-11: EL SISTEMA solo pintará una magnitud que el motor haya calculado para ese caso y esa revisión de la red.
- RF-12: CUANDO el operador elija dos casos, EL SISTEMA mostrará sus diferencias sobre el mismo plano.
- RF-13: EL SISTEMA no comunicará un incumplimiento solo con color: también lo hará con texto, icono, valor y umbral.
- RF-14: EL SISTEMA permitirá todas las acciones del editor con el teclado, con una alternativa a arrastrar.
- RF-15: EL SISTEMA aplicará las ediciones a través de la API, que valida y versiona cada cambio. El navegador no
  calcula ninguna regla eléctrica.
- RF-16: EL SISTEMA no eliminará ninguna vista ni acción actual de la web: el editor se añade.
- RF-17: CUANDO el operador corra el estudio de una variación, EL SISTEMA lo correrá en DIgSILENT si hay licencia y el
  proyecto está vinculado a la red cargada, y con el motor abierto si no.
- RF-18: EL SISTEMA dirá, en la leyenda y junto a cada resultado pintado, qué motor lo calculó.
- RF-19: SI los dos casos comparados se calcularon con motores distintos, ENTONCES EL SISTEMA lo dirá junto a la
  diferencia.
- RF-20: CUANDO el operador seleccione un elemento en el plano, en una tabla de resultados o en el inspector, EL SISTEMA
  lo seleccionará en las otras vistas abiertas, con el mismo código (RF-2), y encuadrará el plano en él con un zoom que
  lo deja visible entero; la selección se puede quitar con el teclado (RF-14). (Plan Maestro v1.6, BP-20: «workspace de ingeniería, zoom, selección enlazada, informe explicable, accesibilidad y e2e por rol»; orden del usuario del 17-11.)
- RF-21: CUANDO el operador abra un hallazgo del informe o de una tabla (una barra fuera de su banda, un tramo
  sobrecargado, una obra propuesta), EL SISTEMA lo llevará al elemento en el plano y mostrará en el inspector el valor,
  el umbral, la norma que lo fija (de la biblioteca normativa, 107:RF-21) y el caso y el motor que lo calcularon (RF-18).
- RF-22: EL SISTEMA mantendrá el espacio de trabajo de ingeniería como una sola pantalla con el plano, la tabla de
  resultados y el inspector a la vez, redimensionables y recordados por espacio, sin quitar ninguna vista actual (RF-16).
- RF-23: (Plan Maestro §7.5, «Unifilar») EL SISTEMA ofrecerá, junto al plano, un diagrama unifilar automático del
  alimentador o de la red elegida, sincronizado con el plano, la tabla y el inspector (el mismo código, 111:RF-2): un
  esquema que no cambia las geometrías físicas ni las impedancias, y que pinta los mismos resultados del estudio
  (111:RF-10, RF-11). Elegir un elemento en uno lo elige en el otro.

## Requisitos no funcionales
- Escala: un plano con todos los alimentadores de la entrega, sin bloquear la página mientras calcula, con capas por
  vista y tablas virtualizadas. El presupuesto de latencia se mide primero sobre la línea base.
- Accesibilidad WCAG 2.2 AA: foco visible y anuncios con `aria-live`.
- Modo claro y oscuro con tokens.
- Funciona sin mapa base ni conexión.

## Casos límite
- Una doble terna superpuesta.
- Dos alimentadores cruzados sin unión.
- Un tramo con CRS distinto.
- Un equipo sin parámetros.
- Un estudio que no converge.
- Una edición sobre una revisión de la red que ya cambió.

## Fuera de alcance
- Escribir en el proyecto nativo de DIgSILENT desde el editor sin pasar por el carril, la copia y la confirmación.
- Operar equipos reales de campo, SCADA o ADMS.

## Criterios de finalización
Cada RF citado por una prueba (`grep "111:RF-"`). Pruebas en navegador real (e2e) de dos recorridos: maniobra → flujo
→ resultados sobre el plano, y comparación de dos casos. El hash de los vértices de la fuente coincide antes y después.
Revisión de accesibilidad con herramienta y a mano.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario (`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 4).
- Se amplía el Leaflet de `MapaCargas`: la web no pierde nada. El prototipo deck.gl solo entra si la medición con
  todos los alimentadores de la entrega demuestra que Leaflet no alcanza el presupuesto de latencia, que se mide
  primero sobre la línea base (tarea T2 del plan).
- La variación se estudia en DIgSILENT cuando hay licencia y con el motor abierto (pandapower) cuando no la hay, y
  siempre se dice qué motor se usó: RF-17 a RF-19.
