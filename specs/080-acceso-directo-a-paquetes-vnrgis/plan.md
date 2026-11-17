# Plan — Spec 080

## Módulos

- `src/vnr_etl/discovery/official.py` (RF-1 a RF-10): `PORTAL_VNR`, `paginas_de_ciclos`, ampliación de `parse_official_publications` y de `refresh_official_catalog`, `vigentes_por_empresa`. `_fetch_html` decodifica por los bytes: con `apparent_encoding` esas páginas no se leían bien.
- `src/vnr_etl/discovery/download.py` (RF-18 a RF-24): `preparar_unrar`, comprobación antes de descargar y `extraer_copia_sql`.
- `src/convertersmartgrid/web/app.py` (RF-9, RF-14, RF-18, RF-20): `/api/vnr/publications` añade `vigente`, `empresa` y `portal`; la descarga extrae y asigna.
- `frontend/src/components/InputsPanel.tsx`, `frontend/src/types.ts` (RF-11 a RF-17): `VnrDiscovery` por distribuidora.

## Decisiones

- Se amplía el buscador existente. Descartado: una tabla de URL en la interfaz, que caduca con cada ciclo y va contra VNR-GIS.md D4.
- La vigencia se decide en el servidor, y la interfaz solo la muestra (skill frontend: sin reglas duplicadas).
- La vigencia compara resoluciones por año y número, no por el título de la página: la página «publicación de la resolución de fijación 2025» trae en realidad el proyecto (RCD 154-2026), y la definitiva es otra (RCD 184-2026).
- Solo se extraen `.bak` y `.config` de la carpeta de la copia, escritos por su nombre base. Descartado: extraer todo el paquete, que trae ejecutables y varias decenas de MB que nadie usa.
- El archivo descargado se conserva junto a su manifiesto, como evidencia del SHA-256.

## Memoria de la lectura de la red BT (RF-60, 2026-11-15)

- `sqlserver_vnr.leer_datos(con_bt=True, salidas=…)`: la red BT se pide al motor por bloques (`_por_bloques`, `fetchmany` de `FILAS_POR_BLOQUE` = 5 000 filas) y `_leer_red_bt` la reparte al vuelo, con las mismas claves (`_s`) que `_tramos_bt`. Recorre btSalida, btTramo y verTramoBT una vez cada una. De cada salida BT queda un entero (dónde cae su SED; manda la última fila) y la fila de las pedidas; de los tramos, los de las salidas pedidas, y de los que no tienen salida MT, el recuento y los 20 primeros por código; de los vértices, los de los tramos guardados.
- `DatosVnr.resumen_bt` lleva lo contado. `_tramos_bt` lo suma a lo que dan las listas, así que un `DatosVnr` hecho a mano con las tablas enteras da lo mismo que antes. Pedir a `modelo_canonico` una salida que no se pidió a la lectura da `ValueError`.
- `capas.leer_base_restaurada` pasa las mismas salidas a la lectura y al modelo.
- Antes de leer, `_avisar_memoria_bt` hace tres `SELECT COUNT(*)`: los tramos y los vértices de las salidas pedidas, con subconsultas `IN` y las salidas como parámetros (con más de `MAX_SALIDAS_EN_LA_CUENTA`, la tabla entera), y las salidas BT. Los multiplica por `BYTES_POR_TRAMO_BT`, `BYTES_POR_VERTICE_BT` y `BYTES_POR_SALIDA_BT` (medidos en MEM-BT y redondeados hacia arriba), más el bloque. Si no cabe en `psutil.virtual_memory().available`, da el aviso nombrado en `DatosVnr.avisos`, que `modelo_canonico` pone los primeros.
- Descartado:
  - un `WHERE … IN (?)` por salida: el aviso `TRAMO_BT_SIN_SALIDA_MT` cuenta los tramos de toda la copia, y replicar en SQL el «manda la última fila» y el recorte de espacios de `_s` cambiaría el resultado;
  - unir las tablas en el motor, por lo mismo.
- Lo que sigue creciendo con la empresa es un entero y un código por salida BT (unos 100–220 B; medido en MEM-BT). Las tablas MT siguen leyéndose enteras: las usa la conversión de todas las salidas.
- Pruebas: en `tests/test_vnr_sqlserver.py`, con un motor de mentira que da las filas a medida que se piden y anota cómo se leen:
  - el pico de tracemalloc con 4N salidas BT no pedidas frente a N;
  - ningún `fetchall` de una tabla BT sin `WHERE`, con un bloque igual en las dos empresas;
  - el aviso de memoria, con una cuenta grande y una memoria libre falsa, que no sale con una cuenta pequeña;
  - la huella sha256 del modelo y sus avisos igual a la de las tablas enteras, sobre una red sorteada con salidas BT repetidas, códigos con espacios y tramos sin salida.

## Exportación de la red BT en flujo (RF-60, MEM-BT v2, 2026-11-15)

- El ensayo con la empresa entera dio en una distribuidora un pico de 1,40 GiB con la v1: lo pone el canónico ENTERO (MT y BT) en memoria antes del GeoPackage, unos 4,7 KB por tramo BT. La v1 solo acotaba la lectura.
- `capas.exportar_base_a_capas_en_flujo(base_red, base_parametros, destino, *, servidor, lote_salidas, mostrar, con_modelo_mt)` → `ExportacionEnFlujo` (destino, avisos, resumen MT, ilegibles, tramos BT, lotes, escrituras, metadatos y, si se pide, el canónico MT). La usan el CLI `bak-a-capas` (con `--lote-salidas` y la estimación impresa) y el guion de ensayo de 82 (`--flujo`). `leer_base_restaurada`, `exportar_canonico_a_capas` y `exportar_copia_a_capas` siguen igual para quien quiera el canónico entero.
- La red MT: `leer_datos` sin `con_bt`, `modelo_canonico` una vez y sus capas escritas de una en una (`capas_una_a_una`; `capas_del_canonico` es su `dict`). Es mucho menor que la BT y queda en memoria: es el pico que queda.
- La red BT: `sqlserver_vnr.volcar_red_bt` la lee una vez por tabla, por bloques (`_crudas`: tuplas, sin diccionario) y una tabla detrás de otra (sin MARS no caben dos consultas abiertas), y la vuelca a un SQLite temporal junto al GeoPackage (`RedBtEnDisco`). En el SQLite, la SED de cada salida BT es la de su última fila y la salida MT, la de esa SED, como en `_tramos_bt`. `RedBtEnDisco.secciones` da los tramos por lotes de `LOTE_SALIDAS` salidas (8) y piezas de `TRAMOS_BT_POR_PIEZA` tramos (5 000), ordenados por salida, código y orden de lectura, con `_seccion_bt`, el mismo constructor que `_tramos_bt`; los avisos (`_avisos_bt`) salen con los mismos recuentos y ejemplos.
- La capa BT se escribe en UNA escritura de `pyogrio.write_arrow` que va pidiendo las piezas como lotes de Arrow: la capa se crea una vez y su índice espacial se arma al cerrarla. Sin pyarrow (no va en el extra `web`), cada pieza se añade con `mode='a'`: el mismo GeoPackage, más despacio (cada tramo añadido actualiza el índice espacial).
- La estimación (`_avisar_flujo_bt`): `COUNT` de las tablas BT enteras, la memoria de dos piezas (`BYTES_POR_TRAMO_BT_EN_PIEZA`, `BYTES_POR_VERTICE_BT_EN_PIEZA`) frente a la libre y el disco del SQLite (`BYTES_EN_DISCO_POR_*`) frente al libre de su carpeta. Cada línea va al registro (`logging.warning` si no cabe, `info` si cabe) y a `mostrar`.
- Descartado:
  - una consulta al motor por salida o por lote: multiplica el tiempo y las consultas con la empresa;
  - ordenar o unir en el motor por salida MT: la tabla BT no trae la salida MT, y el «manda la última fila» y el recorte de `_s` no se pueden replicar en SQL;
  - un diccionario en memoria de la salida BT o del tramo a su lote: crece con la empresa.
- Pruebas (`tests/test_vnr_sqlserver.py` y `tests/vnr_bt_sintetica.py`, una empresa sintética generada fila a fila y un motor de mentira sin MARS):
  - el pico de `peak_wset` de la cadena entera del CLI en un proceso hijo, con N y con 4N salidas (rojo con la vía de antes);
  - el GeoPackage, tabla a tabla y con la sha256 de sus filas ordenadas, igual al de la vía de antes, con lotes y piezas distintos y sin pyarrow;
  - las mismas consultas con N y con 4N salidas, cada tabla BT una vez y por bloques;
  - la línea de la estimación en el registro (`caplog`) y en la pantalla del CLI (`capsys`).

## Exportación de la red MT en flujo (RF-60, MEM-MT, 2026-11-15)

- Con la v2, la red BT ya iba en flujo, pero la MT se leía entera con `fetchall` (`leer_datos`) y su canónico y sus capas estaban enteros en memoria: con datos sintéticos, 260 MiB con 80 000 tramos MT frente a 156 MiB con 20 000. Es el pico que la v2 dejaba (su limitación 1).
- `sqlserver_vnr.volcar_red_mt(cn_red, cn_param, ruta) → RedMtEnDisco`: las mismas tablas que `leer_datos` sin `con_bt`, en el mismo orden y con las mismas ilegibles, todas por bloques (`_consulta` + `_tuplas_por_bloques` / `_por_bloques`, `fetchmany` de `FILAS_POR_BLOQUE`) y una detrás de otra. Las pequeñas (empresa, salidas, SET, sistemas y las de parámetros, `_leer_parametros`, la misma de `leer_datos`) quedan en `RedMtEnDisco.datos`; las que crecen con la empresa (tramos, vértices, SED, enlaces y equipos) van a un SQLite temporal. En el disco van limpios (`_s` o `_f`) los campos por los que se busca, ordena o cuenta; los demás, tal cual si son texto, `None` o un real finito, y limpios si no: el canónico les aplica `_s` o `_f` al leerlos y da lo mismo.
- La red BT va al MISMO SQLite (`volcar_red_bt(…, seds=red_mt.seds(), cn=red_mt.cn)`): una sola caché de 8 MiB.
- `modelo_canonico` se parte sin cambiar nada (la referencia byte a byte de RF-59 sigue igual): `_ContextoMt` (tablas pequeñas, norma más usada por tensión, tipos de conductor, tramos mínimos de las salidas sin tramos), `_IndicesMt` (las filas por salida, SED o tramo) y `_canonico_de_la_salida`, el cuerpo del bucle por salida.
- `RedMtEnDisco.canonico_por_lotes(lote_salidas)` da el canónico por lotes de `LOTE_SALIDAS` salidas con esa misma función; lo que toman de la red entera sale del disco: los códigos operativos de las SED con sus avisos (`ROW_NUMBER` por etiqueta en mayúsculas de Python, en el orden de `CodSed` y de lectura), la norma más usada de cada tensión (contada al volcar) y los tramos mínimos de lotes anteriores. Una salida repetida en `mtSalida` va entera en un lote (`_lotes_de_salidas`): su segunda vez ve lo que dejó la primera, como con las tablas enteras.
- `capas._CapasMtEnDisco`: las filas de cada capa MT, lote a lote, al SQLite, con las funciones de fila de `capas_una_a_una` (`_fila_de_tramo`, `_fila_de_nodo`, `_fila_de_sed`, `_equipos_del_canonico`), y la posición de cada nodo (manda el último, como el diccionario de antes). Cada capa se escribe después en UNA escritura (`pyogrio.write_arrow`, o por añadidos sin pyarrow) en el orden de antes, así que hasta los `fid` coinciden. El tipo de cada columna sale de los tipos de Python de todos los valores escritos, como lo deduce `GeoDataFrame` + pyogrio (`_tipo_de_columna`: solo enteros, INTEGER; números con real o `None`, REAL; solo booleanos, BOOLEAN; lo demás, TEXT); si alguna fila se queda fuera (sin nodo con posición), se deduce con las que entran.
- El resumen se suma lote a lote (`_CuentaDeTramos`) y `con_modelo_mt` junta los lotes (`_sumar_al_modelo`).
- Descartado: una consulta al motor por salida o por lote; leer la red MT dos veces (una por capa); guardar las filas como JSON (pierde tiempo y no hace falta: las columnas sin tipo de SQLite conservan entero, real, texto y `None`).
- Pruebas (`tests/test_vnr_sqlserver.py`; `tests/vnr_bt_sintetica.py` con `tramos_mt` y `mt_rica`):
  - el pico de `peak_wset` de la cadena entera del CLI con N y 4N salidas de cientos de tramos MT (rojo con la v2);
  - ninguna tabla leída con `fetchall`, cada tabla MT grande una vez y por bloques, las mismas consultas con N y 4N (rojo con la v2);
  - el GeoPackage, los avisos, el resumen y el canónico MT iguales a los de las tablas enteras en cuatro redes (una con valores sucios), con lotes de 1, 3 y 1 000 y sin pyarrow;
  - las capas MT por lotes frente al canónico entero en los casos que VNR-GIS no suele traer (nodo repetido entre lotes, SED y equipo sin nodo, tramo sin vértices, columna toda `None`).

## Pruebas

`tests/test_vnr_accesos_directos.py`: HTML sintético con la forma del portal (filas de dos empresas, tabla escapada, secciones SICODI y mapa), ZIP sintéticos para la extracción y la API con `TestClient`. La web y el portal reales se prueban en el navegador, como pide el skill frontend (T4).
