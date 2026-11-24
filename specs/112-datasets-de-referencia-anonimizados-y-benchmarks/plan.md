# Plan — Spec 112

Lee: `docs/constitution.md` y `specs/112-datasets-de-referencia-anonimizados-y-benchmarks/spec.md`. Revisión leída:
`51895566`. Contexto de G0, sin rehacerlo: `D:/csg/G0_PLAN_MAESTRO/C/C_FILAS_BP.md` (BP-21, BP-22),
`C/MATRIZ_EVENTOS_DATASET_CALIDAD.md` (particiones y as-of) y `C/C_DEFECTOS_PLAN_VERIFICADOS.md` (defectos b y c del 089).

## Contexto técnico

Lo que ya existe y se reutiliza (comprobado leyendo el código):

- `web/soporte.py:26-33` y `:66-77`: las expresiones de rutas, correos, IP, códigos y texto entrecomillado, los términos
  del perfil (`_terminos_del_perfil`) y `anonimizar(linea, terminos)`. Hoy solo sirven al paquete de soporte (086:RF-42),
  que se arma con una **lista cerrada** de lo que entra. El benchmark sigue la misma idea.
- `dataset.py:29-48` (`_parse_simple`) y `DatasetRed.from_files`: el export se lee como secciones con su línea
  `FORMAT_` y filas `dict[columna, valor]`, en las dos disposiciones (P3). Eso basta para volver a escribir un trío TXT
  con las columnas que se conservan.
- `tests/synthetic_export.py`: `ExportSpec(seed=…, layout=…, naming=…)`, `write_export` y `load_export`. Hacen de
  «origen» en las pruebas: ningún dato de la distribuidora entra en ellas.
- `reglas.py` (`preparar_dataset`, `aplicar_reglas`, `auditar_completitud`) y `batch.convert_selection`: la única vía de
  conversión (P5). El estudio del original y el del benchmark pasan por ella.
- `oraculo.py`: `disponible()`, `validar(model)` → `InformeOraculo` (`:100-161`) con `v_min_pu`, `v_max_pu`,
  `carga_linea_max_pct`, `carga_trafo_max_pct`, `perdidas_mw`, `recuento` y `veredicto`, y `validar_unida` para la red
  unida. Es el motor abierto (pandapower) con el que se comprueba que el estudio se reproduce.
- `pronostico_demanda.py` (089), **solo lectura**: `abrir_dataset(carpeta)` (`:1644`, comprueba la huella),
  `leer_exogenas`, `METODOS = ('semanal', 'perfil_calendario', 'perfil_anclado')` (`:74`), `predecir` (`:925`),
  `medir` (`:958`), `escala_estacional` (`:941`) y `backtest_objetivo` (`:983`, que ya separa elección y prueba). Este
  plan solo le añade el campo opcional `Exogenas.meses` y `_mes_de` (aclaración de RF-11); sin el campo, el 089 da lo
  mismo que antes. El benchmark lee lo que emita y anota su huella.
- `evaluacion_modelos.py`: `huella`, `texto_canonico` y `particionar_registros` (`:109`), que valida particiones ya
  asignadas, rechaza solapes de grupo y, en modo `generalizacion`, exige un sistema retenido entero para prueba.
- `asistente/prueba_sellada.py` y `prueba_sellada_079.py`: el patrón del sellado (`HUELLA` fijada antes de elegir
  modelos; `selladas()` rechaza si cambia).
- `evaluacion_harness/`: `contratos.huella`/`canonico`/`sellar` y `publicacion.publicar` (JSON canónico, publicación
  atómica con relectura por huella).
- `perfil_empresa.py`: `ruta_perfil_activo` y `perfil_con_nombre`. La empresa de un origen se identifica por la huella de
  su perfil, nunca por su nombre (P13).

Nuevo: el paquete `src/convertersmartgrid/adaptadores/benchmarks/` y la herramienta `tools/benchmark_anonimo.py`. Corre en el
carril del motor y en la máquina del usuario; no usa PowerFactory, GPU ni red. La salida va a
`output/benchmarks/<huella>/`, fuera de git.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Patrones de privacidad compartidos: se mueven de `web/soporte.py` sin cambiar su comportamiento; soporte los importa | `src/convertersmartgrid/dominio/privacidad.py` (nuevo), `web/soporte.py` | RF-2, RF-4 |
| Seudónimos: permutación sorteada con la semilla, coordenadas a un origen neutro con giro sorteado y distancias relativas conservadas, clientes y equipos renombrados de forma coherente entre RED, CARGA y BD_Equipo | `benchmarks/seudonimos.py` | RF-2, RF-3 |
| Redes: lista cerrada de secciones y columnas por disposición; escritura del trío TXT con su `FORMAT_`; perfil de empresa neutro con los prefijos ya traducidos | `benchmarks/redes.py` | RF-1, RF-2, RF-3, RF-10 |
| Series: objetivos del 089 con identificador nuevo, escala sorteada y desplazamiento de semanas completas; las exógenas viajan como columnas; CSV determinista | `benchmarks/series.py` | RF-2, RF-3, RF-11 |
| Reproducción: el estudio del original y del benchmark con `reglas` + `oraculo.validar` (o `validar_unida`) y los métodos de base del 089, comparados con la tolerancia | `benchmarks/reproduccion.py` | RF-3, RF-5, RF-11 |
| Control de reidentificación: busca en cada byte emitido identificadores, coordenadas, fechas, secuencias de valores y textos del origen, y los términos del perfil | `benchmarks/reidentificacion.py` | RF-4, RF-10 |
| Manifiesto y emisión: carpeta temporal, control, manifiesto y `os.replace`; nada sale si algo falla | `benchmarks/manifiesto.py`, `benchmarks/__init__.py` (`generar_benchmark`) | RF-1, RF-4, RF-5 |
| Cohortes: por empresa (una fuera cada vez) y por tiempo; unidad = componente conexo de alimentadores y clientes | `benchmarks/cohortes.py` | RF-6, RF-9 |
| Sellado de la prueba e informe con los resultados negativos | `benchmarks/evaluacion.py` | RF-7, RF-8, RF-9 |
| Herramienta local con `--help` sin DIgSILENT (spec 009) y alta en `CODIGO_FUENTE.md` | `tools/benchmark_anonimo.py`, `CODIGO_FUENTE.md` | RF-1 |

### Generación (RF-1, RF-2, RF-3, RF-5, RF-10, RF-11)

1. `generar_benchmark(origen, destino, *, semilla, tolerancia=None, perfil=None)` lee el trío con
   `DatasetRed.from_files` (o un MDB o paquete VNR por `adapter_for`, si el adaptador da las mismas tablas) y, si se
   pasa, la carpeta del dataset del 089 con `abrir_dataset`. No abre ningún socket ni llama a ningún proveedor: una
   prueba lo comprueba sustituyendo `socket.socket` por uno que falla (RF-1).
2. `seudonimos.Mapa(semilla)` recoge los valores originales por **tipo de identificador** (red, alimentador, SET,
   sistema, nodo, tramo, equipo, tipo de equipo, cliente, medidor), los ordena y les asigna `B` + tipo + número en el
   orden de una permutación de `random.Random(semilla)`. El mapa vive solo en memoria: no se escribe nunca (RF-2).
3. Coordenadas: se restan del centroide del origen, se giran un ángulo sorteado y se suman al origen neutro de
   `ExportSpec` (`500000, 8500000`, ninguna zona real). Las longitudes de los tramos son columnas propias del export y no
   cambian; la geografía solo dibuja (RF-3).
4. Los tipos de equipo se renombran, pero `redes.py` escribe en el BD_Equipo del benchmark los parámetros ya resueltos
   por el catálogo (impedancias, secciones, potencias): el benchmark no depende de deducir nada del nombre de un tipo.
5. `redes.py` escribe solo las secciones y columnas de su lista cerrada. Cualquier columna fuera de ella se omite y se
   anota por nombre (no por valor) en el manifiesto. Las columnas de texto libre (descripciones, comentarios,
   direcciones) están siempre fuera (RF-10).
6. `series.py` toma cada objetivo del 089 (`clase`, `ident`, `magnitud`, curva): `ident` pasa por el mapa, los valores
   se multiplican por un factor sorteado en `[0,5, 2]` (WAPE y MASE no dependen de la escala) y las marcas de tiempo se
   desplazan un número sorteado de semanas completas (≥ 104), que conserva hora y día de la semana. Las exógenas que el
   089 usa (`no_laborable`, temperatura y el mes de calendario, `mes`) se escriben como columnas de la misma fila, para que el calendario real no haga
   falta ni se pueda deducir (RF-11).
7. `reproduccion.py` corre el mismo estudio en el original y en el benchmark y compara: tensión mínima y máxima por
   alimentador (|Δ| ≤ 0,005 p.u.), carga máxima de líneas y transformadores (|Δ| ≤ 1 % relativo), recuento por clase
   igual y mismo veredicto del oráculo. Para las series, WAPE y MASE de cada método de `METODOS` con
   `backtest_objetivo` (relativo ≤ 1 %). Si algo supera la tolerancia, no se emite y se dice qué magnitud y qué
   elemento (con el seudónimo) (RF-3).
8. El manifiesto (`manifiesto.json`, JSON canónico de `evaluacion_harness.contratos`) lleva: huella SHA-256 del contenido
   del origen y del dataset del 089, versión del generador (`__version__` y revisión de git si la hay), semilla,
   transformaciones aplicadas, columnas omitidas, tolerancia y su fuente («spec NNN» o «por defecto»), métricas de
   referencia del original y del benchmark, y la huella de cada fichero emitido (RF-5).

### Control de reidentificación con fugas plantadas (RF-4, RF-10)

`reidentificacion.revisar(carpeta_temporal, origen)` devuelve una lista de hallazgos `(tipo, fichero, línea, motivo)`;
con uno solo, la emisión se detiene y el mensaje dice qué lo delató, sin repetir el valor original. Busca:

- cualquier identificador original de longitud ≥ 3 del mapa (con `texto_canonico`), como palabra completa;
- los términos del perfil de empresa (`privacidad.terminos_del_perfil`) y las rutas, correos e IP de `privacidad`;
- coordenadas a menos de 50 km de cualquier coordenada original, o dentro del recuadro del origen ampliado;
- marcas de tiempo dentro del intervalo del origen sin desplazar;
- secuencias de 8 valores consecutivos de una serie original iguales a 4 decimales (la escala sorteada las cambia; si
  coinciden, la transformación no se aplicó);
- fragmentos de 6 palabras seguidas de los textos del origen que no son tablas (nombres de libros, hojas, cabeceras,
  informes a mano), y cualquier fichero fuera de la lista cerrada de la salida (RF-10).

Para una serie con patrón único (una carga industrial), el control no la puede volver irreconocible sin romper su
forma (RF-3). Lo que sí hace es quitar lo que la ata a la empresa: su `ident`, su potencia contratada y su ubicación;
la potencia queda solo en bandas (`< 1 MVA`, `1–5 MVA`, `> 5 MVA`). El manifiesto lo declara como riesgo residual.

**Prueba negativa con fugas plantadas.** `tests/test_benchmarks_reidentificacion.py` genera un benchmark limpio de un
`ExportSpec` sorteado y, en copias, planta una fuga de cada clase: un código de alimentador original en un nombre, una
coordenada original, un código de cliente, un término del perfil, una fecha sin desplazar, una secuencia de valores
original, un fragmento de un «informe» sintético y un fichero de más. Cada una se rechaza y nombra su clase; la copia
limpia pasa.

### Cohortes por empresa y por tiempo (RF-6, RF-9)

- Cada registro de evaluación lleva `empresa` (la huella del perfil del origen, seudonimizada como `E1…En` en el
  benchmark), `alimentador`, `clientes` y su marca de tiempo.
- Unidad de partición: el componente conexo que une alimentadores que comparten un cliente o un medidor (unión-búsqueda,
  como en `asistente/dataset_entrenamiento.py:particionar_dataset`). Así un cliente transferido entre dos alimentadores
  nunca cae en dos particiones.
- Por empresa: «una fuera»; para cada empresa `k`, prueba = sus componentes, el resto = entrenamiento y selección. Se
  valida con `evaluacion_modelos.particionar_registros` en modo `generalizacion` con `sistema = empresa`.
- Por tiempo: corte por fecha con una franja de separación de un horizonte completo (sin datos de la franja en ninguna
  parte); entrenamiento antes, prueba después.
- Con una sola empresa, la cohorte por empresa no se forma: el informe lleva la frase «La generalización entre empresas
  no está demostrada: solo hay datos de una empresa», y solo se evalúa por tiempo (RF-9). Es el caso real de hoy.

### Sellado y resultados negativos (RF-7, RF-8)

- `evaluacion.sellar_prueba(cohorte, carpeta)` escribe `prueba_sellada.json` con apertura exclusiva (`'x'`): no se
  sobrescribe. Su huella va al manifiesto antes de entrenar o elegir ningún modelo, como `HUELLA` en
  `asistente/prueba_sellada*.py`. `abrir_prueba` recalcula la huella y rechaza si cambió (RF-7).
- `evaluacion.informe(resultados)` publica con `evaluacion_harness.publicacion.publicar` **todos** los candidatos y
  todas las cohortes, también los que pierden contra la base o no pasan la puerta, con su motivo. No hay filtro previo:
  una prueba comprueba que un candidato peor que el ingenuo aparece en el informe (RF-8).

### Escala de la web (RF-20, RF-21)

- `tools/benchmark_escala_web.py`: para cada tamaño lanza un proceso hijo (`--un-tamano N`), así la memoria pico de 200
  no arrastra la de 10. El hijo genera el trío con `ExportSpec(feeders=N, seed, size_cycle=10)` (los mismos tramos por
  alimentador en todos los tamaños), levanta `create_app` en una carpeta temporal con la sesión del lanzador en otra
  temporal (cabecera de token y Origin, cliente 127.0.0.1) y sin perfil de empresa, sube las tres casillas, carga la red
  (`POST /load` hasta su estado final) y cronometra `GET` del espacio, de `feeders` y de las SED de un alimentador.
- p50 y p95 con interpolación lineal sobre las llamadas que siguen a la primera; la primera, la fría, va aparte. La
  memoria pico es el máximo de la memoria residente muestreada con psutil cada 20 ms.
- El resultado lleva el commit, el árbol del índice y si había cambios sin registrar, para repetir la medición sobre el
  mismo SHA. El dibujo del frontend va como «no medido» con su motivo (RF-21).
- La prueba rápida mide 10 alimentadores con 3 repeticiones y comprueba la forma, no los tiempos; la corrida de 10, 50 y
  200 con 30 repeticiones es aparte (T18), y el dibujo con navegador, otra (T19).
- La red es una sola: `spec_de_escala` (`dominio/benchmarks/sintetico.py`, semilla 112, 200 tramos y 60 cargas
  típicos, tamaños de 10 alimentadores en ciclo) la usan la API y la web de prueba del navegador
  (`frontend/e2e/web_de_prueba.py` con `CSG_E2E_ESCALA=1`).
- El dibujo (T19): `frontend/e2e/escala_dibujo.mjs` arranca esa web en un puerto libre (nunca 8765 ni 8766), en una
  carpeta temporal y sin perfil, la abre en Edge sin salida a la red y, en cada repetición, mide con
  `PerformanceObserver` y `performance.mark` desde el final de la respuesta de `feeders` hasta la última fila pintada
  de la tabla, y el plano de la red unida hasta su «listo»; deja `dibujo_<N>.json` con p50, p95 y el commit.
  `benchmark_escala_web.py --dibujo CARPETA` (o `--solo-enlazar` sobre un resultado ya escrito) enlaza cada tamaño
  con el suyo solo si es del mismo commit, del mismo tamaño y de la misma red; si no, «no medido» con su motivo.

## Decisiones

- Benchmark de redes como trío TXT, el formato que el conversor ya lee. Descartado: exportar la red de
  pandapower o un DGS, porque romperían el camino de conversión (P5) y el benchmark no probaría el lector ni las reglas.
- Seudónimos por permutación sorteada con la semilla. Descartado: un hash del identificador original, porque con una
  lista de códigos candidatos se recupera por diccionario (RF-2).
- La huella del origen es SHA-256 de su contenido, sin clave. Descartado: HMAC con una clave local, porque añade un
  secreto que guardar y no protege nada que el hash no proteja: sin el original no se revela; con él, solo se verifica.
- Lista cerrada de secciones, columnas y ficheros, como el paquete de soporte. Descartado: quitar lo que se detecte de
  todo lo que hay, porque una columna que nadie previó se publicaría.
- Las expresiones de `web/soporte.py` pasan a `privacidad.py` del núcleo, y soporte las importa. Descartado: copiarlas
  (P5, un sitio) e importar `web/` desde el núcleo (capas de la spec 002).
- Series en CSV con formato numérico fijo. Descartado: Parquet, que guarda la versión del escritor y no garantiza los
  mismos bytes entre entornos (requisito no funcional de reproducibilidad).
- Desplazar las fechas por semanas completas, con las exógenas como columnas. Descartado: conservar las fechas, porque
  los feriados delatan el país y el año; y barajar los días, porque rompe la forma de la serie (RF-3).
- Tolerancia: la de la spec del estudio; por defecto 0,005 p.u. y 1 % (decisión del 2026-11-14). Descartado: una
  tolerancia única fija, porque cada estudio declara la suya.
- Las métricas de referencia de las series se calculan con `backtest_objetivo` y los métodos de base. Descartado:
  `backtest_modelos`, cuya puerta se calcula en el origen de prueba (defecto b de G0) y que necesita GPU.
- Privacidad diferencial formal: fuera de alcance (spec). El modelo de amenaza es un tercero sin los datos de la empresa
  que usa conocimiento público (nombres, coordenadas, feriados, potencias nominales).

## Comprobación contra la constitución

- P1 Determinismo: misma semilla y mismo origen dan los mismos bytes en cada fichero, en serie y con `workers>1` en la
  conversión del estudio. Prueba que genera dos veces y compara las huellas.
- P2 Escala variable: los índices por alimentador del dataset (`*_by_feeder`); ningún número fijo de alimentadores; las
  pruebas sortean con `ExportSpec(seed=…)`, incluido un solo alimentador.
- P3 Dos disposiciones: el escritor conserva la disposición del origen y se prueba con `reducido` y `completo`.
- P5 Una vía: el estudio pasa por `reglas.py`; los patrones de privacidad, por `privacidad.py`.
- P6 Publicación atómica: se escribe en `.csg-stage-benchmark` y se publica con `os.replace` solo si el control y la
  reproducción pasaron.
- P7: nada de esto corre en una petición HTTP; es una herramienta local (sin web en esta spec).
- P9 Datos de la distribuidora: todo corre en local; el benchmark no lleva datos crudos ni textos. Publicarlo sigue
  siendo decisión del usuario (fuera de alcance).
- P13 Universal: ningún código, CRS ni prefijo de empresa en el código; las pruebas usan dos perfiles distintos y dos
  convenciones de nombre (`naming`).

## Estrategia de pruebas

- Sintéticas sorteadas (`ExportSpec(seed=…)`), con las dos disposiciones y dos perfiles de empresa; series sintéticas con
  calendario y exógenas generadas en la prueba. Ningún dato de la distribuidora en `tests/`.
- Reproducción en al menos dos redes sintéticas distintas (semillas y disposiciones distintas) y, con las tres variables
  `CSG_*`, en la red real: la salida va a `tmp_path` y no se guarda.
- Prueba negativa de reidentificación con cada clase de fuga plantada.
- Cohortes: dos empresas sintéticas, un cliente transferido entre dos alimentadores y el caso de una sola empresa.
- Las pruebas no lanzan GPU: los métodos de base del 089 son de CPU.
- Ficheros: `tests/test_benchmarks_seudonimos.py`, `test_benchmarks_redes.py`, `test_benchmarks_series.py`,
  `test_benchmarks_reidentificacion.py`, `test_benchmarks_cohortes.py`, `test_benchmarks_evaluacion.py`.
- Cada prueba cita su requisito: `"""112:RF-n — …"""`.

## Riesgos

- El catálogo deduce parámetros del nombre de un tipo: si alguno no queda escrito en el BD_Equipo del benchmark, el
  estudio cambia. Lo detecta la reproducción (RF-3), que compara recuentos y tensiones.
- Una regla que depende de un prefijo del perfil (SED de medición) deja de aplicarse si el perfil neutro no traduce el
  prefijo. Lo detecta el recuento por clase.
- La limpieza del 089 no es as-of (defecto c de G0): el benchmark de series hereda esa limitación hasta que f9 corrija
  la 089; el manifiesto anota la huella del dataset del 089 del que salió.
- Con la semilla del manifiesto y el código público, quien tenga la lista de códigos originales puede reconstruir el
  mapa. Es aceptable en el modelo de amenaza (hace falta el original), y el manifiesto lo declara.
- Mover las expresiones a `privacidad.py` puede cambiar el paquete de soporte: sus pruebas de 086:RF-42 siguen en verde
  sin tocarlas.

## Revisión de privacidad (2026-11-14, tras la auditoría de la T2)
- **Semilla (RF-12).** `benchmarks/semilla.py`: la semilla de los seudónimos se guarda en `raiz_local()/benchmarks/<huella del origen>/semilla` (fuera del destino) y el manifiesto lleva `sha256("publica:" + semilla)`. El control de reidentificación busca la semilla secreta y su representación decimal en todos los ficheros publicados.
- **Geometría (RF-13, RF-14).** `benchmarks/geometria.py`: coordenadas por un trazado del grafo (capas por distancia a la cabecera, orden estable con la semilla pública), sin la forma real. Longitudes eléctricas × (1 + ε), con ε ~ U(−a, a) y a = 5 % por defecto, recortado a la mitad hasta que T4 reproduce dentro de la tolerancia (como mucho 4 intentos; si no, no se emite). `transformar_coordenadas` (T2) queda para el uso local.
- **Control (RF-14).** Huella del alimentador = longitudes ordenadas. Se marca como «identificado» con una correlación de Spearman ≥ 0,99 contra el original, o con un 95 % de los tramos dentro del 0,5 %. Una prueba planta la red sin perturbar y exige que se identifique (rojo) antes de dar por bueno que la perturbada no.
- **Control del atacante, revisado (aclaración de RF-13 y RF-14; decisión del coordinador del 2026-11-14).** Sustituye a
  la viñeta anterior. El atacante ordena las longitudes de un alimentador y las empareja **rango a rango** con las del
  candidato: la i-ésima con la i-ésima y, si los tamaños difieren, por cuantiles. El alimentador está «identificado» si
  el 50 % o más de los tramos quedan dentro del margen declarado (`geometria.fraccion_emparejada`). Se descarta Spearman,
  que da 0,988–0,9998 tramo a tramo y 1,0 sobre las longitudes ordenadas, porque marca como identificada cualquier red.
  También se descarta el emparejamiento **voraz** (cada longitud con cualquier otra dentro del margen): con muestras
  densas, casi todas encuentran pareja, así que da por identificada también la red sintética y no distingue nada.
  En una simulación con numpy (sin datos ni motor), el rango a rango da de media 0,03 (n = 10) a 0,30 (n = 1000) en
  muestras independientes de la misma distribución, y 1,0 en la red perturbada al ±5 %.

## Dejar una empresa fuera cada vez (2026-11-20, RF-15 a RF-19; Plan Maestro PM-17)
- **Dominio sin E/S.** `dominio/benchmarks/interempresa.py`: `dejar_una_fuera(datos, ajustar, medir, criterio)` hace un
  pliegue por empresa; `ajustar` recibe solo las demás y `medir` solo la retenida. El veredicto: con menos de 3 empresas,
  «NO DEMOSTRADA» y por qué (con 2 se miden los pliegues igual, para verlos); con 3 o más, «DEMOSTRADA» solo si pasan
  todas. Ahí van también el catálogo de fichas y su medida, que usan la misma regla del modelo para el conductor sin ficha
  (`suggest_catalog_code`), así que lo medido es lo que la conversión haría.
- **Adaptador.** `adaptadores/benchmarks/interempresa.py`: una subcarpeta por empresa, renombrada `E1…En` por la huella
  de su nombre (`seudonimos_de_empresa` de las cohortes). VNR (RF-22): `red_vnr.json` con los tramos y las fichas que
  `red_de_modelo` saca del modelo canónico de `cargar_copia` (la copia .bak del paquete público, restaurada en SQL
  Server), escrito por `interempresa_loco.py preparar-vnr`; también un trío TXT, leído con `redes.leer_fichero`. Una
  empresa sin tramos es un error, no un pliegue que no pasa. RF-23: `red_de_modelo(modelo, resolver=…)` guarda primero
  las fichas de la copia (propias) y luego deja que el resolutor de la conversión (`fichas_del_catalogo` de
  `adaptadores/sources/vnr.py`, por código, código sin su último carácter o familia de cinco caracteres) complete las
  demás («catálogo 053»); nunca `ampliar_con_lo_que_falta`, que escribe en el catálogo. `red_vnr.json` (v2) guarda el
  origen y la cobertura; `evaluar_vnr` mide con las del catálogo si alguna empresa las tiene, con `que_mide`,
  `ficha_propia` aparte y `cobertura_catalogo` por empresa. Pronóstico: el benchmark de series de la T5, leído con `series.leer`, y medido con `predecir`
  y `medir` del 089 (la base «semanal» y su WAPE): no se copia ninguna métrica (P5). El informe, con `write_json_atomic`.
- **Herramienta.** `tools/interempresa_loco.py vnr|pronostico --empresas CARPETA --salida INFORME.json`; sale con 0 si
  «DEMOSTRADA» y con 3 si no, con el informe escrito. `preparar-vnr --copia COPIA.bak --destino CARPETA` deja la red de
  una empresa desde su copia (RF-22). Es de desarrollo y no se entrega (`config/entrega.json`).
- **Por qué esas medidas.** En la conversión VNR lo único que se aprende de otras empresas es el catálogo de conductores
  (053): una empresa nueva se convierte bien si las fichas de las demás le dan la impedancia de los suyos. En el
  pronóstico, los métodos de base del 089 son de cada serie; lo transferible es la forma semanal, y se compara con la base
  propia de la retenida en el mismo origen y sin ver nada posterior a él.
- **Límites.** Las series del benchmark van con semanas desplazadas (T5): no se alinean en el calendario entre empresas,
  así que la forma de las demás puede ser de otras fechas que el origen de la retenida; para la forma semanal no importa,
  pero el informe no dice nada de la estación. Hoy en local solo hay datos de una empresa: la corrida real (T16) da «NO
  DEMOSTRADA» hasta tener los paquetes públicos de al menos tres.
