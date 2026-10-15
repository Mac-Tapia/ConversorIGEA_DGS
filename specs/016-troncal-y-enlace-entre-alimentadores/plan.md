# Plan — Spec 016

Estado: aprobado (2026-10-14) · Fecha: 2026-10-14

## Resumen

La geometría y la topología van a un módulo puro nuevo, `src/igea_dgs/troncal.py`, que
se prueba sin DIgSILENT. Ese módulo calcula la troncal del camino más largo, lo que queda
aguas abajo de un nodo, el punto más cercano sobre un trazado y el reparto de longitudes
al partir. Los guiones de DIgSILENT (`tools/obras_pf.py` y `tools/cargas_pf.py`) solo leen
la red del proyecto, se la pasan y escriben lo que les devuelve. Es el mismo reparto que
`obras_pf.py` y `transferencia_pf.py` de la spec 011: lógica en `src/`, objetos de
DIgSILENT en `tools/`.

## Módulos

### 1. `src/igea_dgs/troncal.py` (nuevo) — RF-1 a RF-5, RF-15, RF-18, RF-20, RF-27, RF-28, RF-45, RF-64, RF-67

- `Red`: barras (nombre, kV, GPS opcional) y tramos (nombre, dos barras, longitud,
  cerrado y en servicio, cable o aéreo, trazado GPS opcional). Es lo que lee el guion.
- `troncal(red, cabecera) -> Troncal`: el camino más largo. Primero un recorrido desde
  la cabecera sobre los tramos cerrados (RF-4): el árbol de los caminos más cortos en
  metros (Dijkstra), con el nombre del tramo como desempate. La red de distribución es
  radial, pero IN111 trae tres anillos cerrados: un recorrido en anchura contaba saltos y
  colgaba barras del lado largo del anillo (T3). El tramo que cierra un anillo se avisa
  en `mallas` y no bloquea. Después, la barra más lejana en metros y su camino. Desempate
  (RF-5): a igual longitud, la tupla de nombres de tramo menor. Coste
  O((barras + tramos)·log barras) por alimentador (P2).
- `aguas_abajo(red, cabecera, nodo) -> Subarbol`: el subárbol del nodo, visto
  desde la cabecera (RF-64). Incluye el tramo que entra al nodo, para RF-58.
- `punto_mas_cercano(trazado, punto) -> (fraccion, distancia_m)`: la proyección sobre la
  polilínea en metros locales. Se reutiliza la conversión de `dgs._geo_to_meters` en vez de
  copiar la fórmula (P5). Sin trazado, la recta entre las dos barras (RF-15).
- `punto_en_troncal(red, tramos, punto, minima_m) -> Conexion`: el tramo y la fracción, o
  la barra del extremo si queda a menos de `minima_m` (RF-20). Si `minima_m` es `None`, la
  barra solo cuando la distancia es 0 (RF-67). A igual distancia, el tramo de nombre menor.
- `partir(longitud, fraccion) -> (l1, l2)`, con `l1 + l2 == longitud` (RF-18).
- `extremos_del_enlace(recibe, cede, candidatos) -> (Conexion, Conexion)`: RF-27 y luego
  RF-28. Se compara segmento con segmento y se descarta por caja envolvente el par que no
  puede mejorar. Se hace una vez por obra y con dos troncales: con TA225 e IN111 reales
  tarda 0,02 s (T4), así que se descartó la rejilla de celdas que preveía este plan.
- `cortar_trazado(trazado, fraccion)`: el trazado de cada mitad, porque `SplitLine` deja
  el entero en las dos (T1). `conexion_en(red, tramo, punto, minima_m)`: la conexión en un
  tramo dado, que usa la obra cuando el operador indica el punto (RF-31).

Alternativa descartada: calcular la troncal con `ComBbone`, que ya usan el N-1 y la
transferencia. No da troncal sin enlace (el caso de IN111), y RF-10 la deja para esos dos
usos.

### 2. `src/igea_dgs/obras_pf.py` — RF-6 a RF-9, RF-11 a RF-14, RF-23 a RF-25, RF-31, RF-38, RF-39, RF-41, RF-51 a RF-53, RF-57, RF-59, RF-61, RF-65, RF-66

- `CLASES` suma `'enlace'` y `'migracion'`. `Obra` suma `toda_troncal`, `tipo_cable`,
  `recibe`, `minima_m`, `origen`, `destino` y `nodo`.
- `_casos` cambia: «Sin proyecto» solo, rechazado (RF-13). «Sin proyecto» implica «Con
  proyecto» (RF-11). `enlace` y `migracion` solo en «Con proyecto» (RF-14, RF-25, RF-53).
- `RedAlimentador.troncal` pasa a ser la de `troncal.py`, solo para las obras. El N-1 y la
  transferencia siguen leyendo `ComBbone` (RF-10).
- `_seccion` con `toda_troncal`: aéreos al tipo pedido y cables al `tipo_cable`. Sin
  `tipo_cable`, los cables se listan (RF-6 a RF-8). La simulación suma los metros por tipo
  de origen (RF-9).
- `_enlace` y `_migracion` en el plan de la simulación. Dicen qué se parte, qué barras y
  tramos nuevos se crean, el seccionador y los tipos copiados (RF-41, RF-59). Con
  tensiones distintas, el aviso de RF-61. Para la migración, las reglas de copia de tipo
  de `_tension` (011:RF-82, RF-83, RF-99, RF-103), sobre el subárbol de RF-64.

### 3. `tools/obras_pf.py` — RF-2, RF-10 a RF-12, RF-16, RF-17, RF-19, RF-21, RF-22, RF-26, RF-30, RF-32 a RF-36, RF-40, RF-42, RF-43, RF-54 a RF-58, RF-60, RF-62

- `leer_red(elm, cabecera)` (en `tools/cargas_pf.py`, T6): barras con `uknom` y
  `GPSlat`/`GPSlon`; líneas y acopladores con `dline`, `outserv`, `GPScoords` y el estado
  de sus interruptores (`StaSwitch.on_off`, `ElmCoup.on_off`) → `troncal.Red`.
  `leer_troncal` del guion calcula con ella la troncal de las obras; `leer_troncales` y su
  `ComBbone` se retiraron de las obras (RF-10). Cada alimentador se lee en el caso de sus
  obras: en «Con proyecto» si todas son de allí (enlace, migración), si no en «Sin
  proyecto» (RF-2).
- `partir_tramo(app, linea, fraccion, nombre, gps)` (en `tools/cargas_pf.py`, T6): con
  `Application.SplitLine` (T1, abajo) dentro de la variación que graba (RF-22); pone a la
  barra nueva el nombre y el GPS del punto (RF-19) y a cada mitad su parte de `GPScoords`.
  Rechaza partir sin variación grabando, un tramo fuera de servicio o en un extremo.
- `construir_enlace`: el flujo de carga de «Con proyecto» antes del enlace para elegir
  los candidatos (RF-26, RF-30); las dos conexiones (RF-27 a RF-29); la línea nueva con la
  longitud recta y `GPScoords` de sus dos extremos (RF-34, RF-35); un `StaSwitch` abierto
  en el cubículo del lado que cede (RF-36). Nunca la cierra (RF-62). Después, el flujo
  (RF-42) y la comprobación de que no queda un camino cerrado (RF-43). RF-40: busca por
  `desc` una variación de enlace con los mismos dos alimentadores.
- `construir_migracion`: el subárbol leído con `leer_red`. Tensión nueva en sus barras y
  copias de tipo en sus líneas y transformadores (RF-54 a RF-56). Si no está separado de
  la parte que no pasa, abre el tramo que entra al nodo (RF-58). Aviso de RF-66.
- Orden de los casos: tras aplicar las obras de «Sin proyecto» se activa cada una también
  en «Con proyecto» (RF-11). Si «Con proyecto» no existe, `casos_pf` lo crea después
  (RF-12, 014:RF-18).

### 4. `tools/cargas_pf.py` y `src/igea_dgs/cargas_pf.py` — RF-45 a RF-50, RF-73

- La búsqueda de la barra más cercana (`cercanas`, RF-24 de la 007) pasa a
  `troncal.punto_en_troncal` sobre la troncal de cada alimentador marcado, leída una vez
  por alimentador y no una vez por carga (P2).
- Si la conexión cae dentro de un tramo, se parte con `partir_tramo`, en la variación de
  la carga (RF-46). `partir_tramo` está en `tools/cargas_pf.py`, que ya es el módulo
  común de los guiones (`crear_variacion`, `gps_de`): un módulo nuevo en `tools/` habría
  sido otra herramienta con `--help` y entrada en el manual (spec 009).
- RF-47 (cambiado en la T10): cada carga se crea y se mide sola, con las variaciones de
  las anteriores apagadas (007:RF-12), así que cada una parte el tramo original en su
  variación y el resultado no depende del orden. Partir «el trozo que hay tras las
  anteriores» haría depender una variación de objetos creados en otra, que no existen con
  ella apagada. Con dos cargas en el mismo tramo se avisa de revisarlo con las dos activas.
  (Texto anterior: «las cargas de un mismo tramo se aplican en orden de fracción desde la
  cabecera. Cada una parte el trozo que hay tras las anteriores, así el resultado no depende del
  orden del libro.
- La barra indicada (RF-48) y la línea de enlace de la carga (007:RF-39) no cambian. La
  simulación dice el tramo, si se parte y la distancia (RF-49).
- `armar_plan` recibe `minima_m` del formulario (RF-73).

### 5. Transferencia — RF-44, RF-63

`tools/transferencia_pf.py`: antes de cerrar un enlace, si sus dos barras tienen
distinto `uknom`, no se calcula ese enlace y se dice (RF-63). Encontrar el enlace nuevo
(RF-44) lo hace ya `GetTieOpenPoint` de `ComBbone`; se comprueba en DIgSILENT (T12).

### 6. Web — RF-68 a RF-73

- `src/igea_dgs/web/services.py` y `app.py`: los campos nuevos de la obra pasan por
  `validar_obra`, sin un esquema aparte. `minima_m` llega al plan de cargas.
- `frontend/src/components/ObrasPF.tsx`: clases «Enlace entre alimentadores» y «Migración
  de SED a otra tensión»; casilla «toda la troncal» y tipo de cable en la sección; campo
  del nodo y de la distancia mínima. En las dos clases nuevas, el selector de casos
  muestra solo «Con proyecto» (RF-71). El error de RF-72 sale del informe de la
  simulación.
- `frontend/src/components/CargasTab.tsx`: el campo de la distancia mínima (RF-73).

### 7. Specs anteriores

Se anotan en 007 (RF-24, RF-28, RF-30, RF-31) y en 011 (RF-57, RF-87) con «cambiado por
016:RF-n», sin borrar el texto. `CODIGO_FUENTE.md` suma `troncal.py` y las funciones nuevas
de `tools/cargas_pf.py` en el mismo cambio (spec 009).

## Resultado de la T1 (2026-10-14)

`Application.SplitLine(línea, porcentaje, interruptorLado0, interruptorLado1, gráfico)`
(`PythonReference_en.pdf`, cap. 3, «Application methods») devuelve la barra nueva, o 0 si
falla. Sonda en DIgSILENT sobre una copia de `20261014-220929_IGEA_IN111_TA225`, con
«Con proyecto» activo y la variación grabando; la copia se borró al terminar. Se partió
`SEC_1091_1058935` (319 m, N205003D_10kV) al 40 %:

- Todo queda en la etapa que graba: las dos líneas, la barra, los cubículos y el
  interruptor. Al desactivar la variación, la línea vuelve a estar entera y la barra no
  existe. RF-22 y el «deshacer» de 007:RF-38 salen solos.
- El porcentaje se cuenta desde `bus1`. La línea original conserva el nombre y va de
  `bus1` a la barra (127,6 m); la copia se llama `<nombre>(1)` y va de la barra a `bus2`
  (191,4 m). Las longitudes suman la original (RF-18).
- Las dos conservan `typ_id`, `nlnum` y `outserv` (RF-17).
- La barra se llama `Terminal`, con `uknom` del tramo (10 kV), en la misma red y **sin
  GPS** (`GPSlat` = `GPSlon` = 0). El guion le pone nombre y coordenadas (RF-19).
- **`GPScoords` no se reparte**: las dos líneas se quedan con el trazado entero. El guion
  corta el trazado en el punto (RF-23, spec 010).
- `interruptorLado1 = 1` crea un `StaSwitch` **cerrado** en el cubículo de la barra
  nueva. Para partir se pasan 0 y 0. El seccionador abierto del enlace (RF-36) se crea en
  la línea nueva, no aquí.
- El flujo de carga converge tras partir.

Se descarta la copia manual de la línea: `SplitLine` ya mueve los cubículos y registra
todo en la variación.

## Pruebas

- `tests/test_troncal.py` (nuevo): árboles sintéticos sorteados con tamaño aleatorio
  (`random.Random(semilla)`, sin tamaños fijos), contrastados con un recorrido de fuerza
  bruta. Empates, tramos abiertos, malla, un solo tramo, tramos de 1 m, proyección en el
  extremo, `minima_m` vacía, la rejilla frente a la comparación de todos con todos y el
  subárbol.
- `tests/test_obras_pf.py`: validación de casos y clases nuevas, simulación de sección
  con toda la troncal, del enlace y de la migración.
- `tests/test_obras_pf_guion.py` y `tests/test_cargas_pf_guion*.py` con `fake_pf`: partir
  un tramo en una variación, el seccionador abierto, la migración del subárbol y RF-47.
- `tests/test_obras_pf_web.py`, `tests/test_cargas_pf_web.py` y
  `tests/test_obras_estudios_front.py`: los campos nuevos.
- `tests/test_transferencia_pf.py`: RF-63.
- Datos reales: con las tres `IGEA_*`, la troncal de IN111 en el modelo del TXT mide
  13,58 km y tiene 71 tramos (tres anillos cerrados). Es una comprobación de `troncal.py` con una red real; el
  guion lee la de DIgSILENT.
- DIgSILENT (T12): sobre el proyecto de IN111 y TA225 ya importado, nunca sobre SED
  inventadas.

Cada prueba cita `016:RF-n`.
