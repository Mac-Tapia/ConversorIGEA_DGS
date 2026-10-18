# Plan 022 — Red unida por zonal y SET

Estado: borrador · Fecha: 2026-10-17 · Spec: [spec.md](spec.md)

## Piezas

1. **Estructura de la empresa** — `src/igea_dgs/estructura.py` (nuevo). (RF-1 a RF-6, RF-25b)
   - `Estructura` (zonales → SET → alimentadores, con sistema eléctrico, sector y norma),
     indexada por código de alimentador una vez (escala).
   - `estructura_de_perfil(datos)` lee `estructura` del perfil, que puede apuntar a un
     JSON aparte (`config/perfiles/electro_dunas_estructura.json`, transcrito de la tabla
     pública; RF-3). `leer_tabla_excel(ruta)` lee la misma tabla en Excel (RF-4) con alias
     de columnas como `demanda_medida`, y rechaza filas mal formadas nombrándolas (RF-5).
   - `asignar(estructura, alimentadores_de_la_entrega)`: SET y zonal de cada uno, los
     «Sin SET» (RF-19), los que faltan (RF-20) y lo que se omite por no tener redes (RF-25b).
   - Alternativa descartada: leer la SET del nombre de la cabecera; no la traen ni TXT, ni
     MDB, ni VNR (sección `SOURCE`: alimentador, nodo y tensión).

2. **Red unida estructurada** — `src/igea_dgs/combine.py`. (RF-7, RF-10 a RF-14, RF-21,
   RF-26, RF-27)
   - `CombinedInfo` gana `sets` (SET → barras por tensión, con sus coordenadas), `zonales`,
     `zona_de` (alimentador → sistema eléctrico) y `cabeceras` (alimentador → interruptor).
   - `estructurar(combinado, asignacion)`: crea las barras de SET por tensión (RF-10, RF-21),
     un interruptor de cabecera por alimentador entre la barra y su nodo de cabecera (RF-12,
     RF-13) y deja una sola fuente por barra de SET (RF-11); los «Sin SET» conservan la suya.
   - Los enlaces (`TiePoint`) ya existen como nodos compartidos; se les añaden las dos SET
     (RF-27).

3. **Enlaces y radialidad** — `src/igea_dgs/enlaces.py` (nuevo). (RF-26, RF-29 a RF-31,
   RF-34)
   - Grafo de la red unida con los tramos y maniobras cerrados; recorrido desde cada barra
     de SET (el `arbol` de `troncal.py`, por metros). Una arista que vuelve a una barra ya
     alcanzada cierra un camino: entre dos SET, entre dos alimentadores o un anillo.
   - Qué abrir: el punto de enlace del camino si lo hay (RF-30); si no, la maniobra o el
     tramo del camino más lejano de su barra de SET (RF-31). Determinista: a igual
     distancia, el nombre.
   - Devuelve la lista de aperturas con su motivo para el modelo y el informe.

4. **Oráculo de la red unida** — `src/igea_dgs/oraculo.py`. (RF-28, RF-32, RF-33)
   - `red_pandapower` acepta la red unida: barras de SET con su red externa, interruptores
     de cabecera, enlaces abiertos. `validar_unida(model)` calcula el flujo una vez y da el
     veredicto por SET y zonal (la isla de cada barra de SET).
   - Si no converge, cada isla sola, y la barra de mayor desajuste de la isla que falla
     (lo que se hizo a mano en NA205 el 2026-10-17).

5. **Escritor DGS** — `src/igea_dgs/dgs.py` y el esquema `schemas/pf21_dgs_1_8_4.json`.
   (RF-8, RF-9, RF-11, RF-12, RF-14 a RF-18b, RF-27)
   - Un `ElmNet` por zonal; cada elemento con el `fold_id` de la red de su alimentador; las
     barras de SET dentro de su `ElmSubstat` («SET 21 El Carmen»).
   - Interruptor de cabecera como `ElmCoup` cerrado; `ElmFeeder.obj_id` en su cubículo del
     lado del alimentador (RF-14).
   - `ElmZone` por sistema eléctrico, con su sector y norma en la descripción, y `cpZone`
     en barras, tramos, SED y cargas (RF-15, RF-16). El esquema 1.8.4 no tiene `ElmZone`:
     se añade su tabla y la columna `cpZone` (se confirma en DIgSILENT, T11).
   - Coordenadas: la cabecera en las suyas (RF-17); la barra de SET en las de sus cabeceras
     (RF-18, RF-18b); el diagrama dibuja la SET junto a la cabecera.
   - Sin estructura, todo como hoy (RF-6).

6. **Lote, CLI y web** — `batch.py`, `cli.py`, `web/services.py`, `web/app.py` y el front.
   (RF-4, RF-7, RF-19, RF-20, RF-25, RF-34)
   - El lote unido llama a `asignar` → `estructurar` → `enlaces` → oráculo → `write_dgs`.
   - Informe de la conversión por zonal y SET con enlaces abiertos, «Sin SET» y faltantes.
   - Web: subir la tabla en Excel por espacio (RF-4) y ver el informe.

7. **Guiones de DIgSILENT** — `tools/cargas_pf.py` (`_frontera_cabecera`) y los que la usan.
   (RF-22 a RF-24)
   - Si el `ElmFeeder` está en el cubículo de un interruptor de cabecera, se mide esa rama
     (`RAMA_ELMFEEDER`) aunque la barra tenga varias troncales y una sola red externa; hoy
     «FUENTE_UNICA» sumaría todos los alimentadores de la SET.
   - La consigna de 021:RF-61 ya recorre todas las redes externas: vale por barra de SET.

8. **Calibración por barra de SET** — `demanda_medida.py`, `ajuste_cabecera.py`,
   `web/services.py` y `tools/ajuste_cabecera_pf.py`. (RF-37 a RF-45)
   - `leer_medidores` distingue las filas «Barra» (medidor, nivel, siglas); la estructura
     trae las siglas de cada SET.
   - Objetivo de la barra: la suma, registro a registro, de sus medidores de la misma
     tensión (T1 + T2) y su máxima (o el instante coincidente de 021:RF-50).
   - En `ejecutar_proyecto`, una clave por barra de SET con medidor: su medida es la P que
     entra por su red externa; su reparto, todas las SED escaladas de sus alimentadores con
     un factor; los alimentadores de barras sin medidor siguen con su clave propia (RF-42).
   - Central de barra (RF-44) con `central_en_sin_proyecto` en la barra de SET.

## Pruebas

- Sintéticas sorteadas (semilla) con un número variable de zonales, SET y alimentadores;
  dos disposiciones del TXT; DGS idéntico con `workers=1` y `workers>1`.
- `enlaces`: anillos, caminos entre SET y entre alimentadores, con y sin punto de enlace.
- Oráculo: red unida que converge, y una isla que no, nombrando SET y barra.
- Guion: `fake_pf` con dos alimentadores en la misma barra de SET, medida de cada uno.
- Datos reales: TXT, MDB y VNR con la estructura de Electro Dunas.
- DIgSILENT: la entrega importada como un proyecto; flujo; NA203 + NA205 en SET 51.

## Riesgos

- `ElmZone`/`cpZone` en el DGS 1.8.4: si DIgSILENT no los importa, las zonas se crean
  con el guion de importación (alternativa) — se decide en T11.
- Tamaño: la entrega entera en un DGS; el oráculo calcula una red de decenas de miles de
  barras con pandapower; se mide en T10.
