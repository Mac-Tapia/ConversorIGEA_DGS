# Plan — Spec 025

Lee: `docs/constitution.md` y `specs/025-calibracion-por-anio/spec.md`.

## Contexto técnico

- Lectura de libros: `src/igea_dgs/demanda_medida.py` (`libros_de_cabecera`, `Cabecera`,
  `hojas_del_medidor`, `maxima_de_registros`, `maxima_de_barra`, `mes_de_nombre`,
  `catalogar_libros_clientes`). Hoy recorren solo el primer nivel (`iterdir`).
- Web: `src/igea_dgs/web/services.py` (`demanda_asignar`, `_foto_fuente_clientes`,
  `demanda_clientes_indexar`, `_demanda_ruta`, `demanda_cabecera`, `_demanda_por_barra`,
  `ajuste_plan`, `_guardar_calibracion`), `web/app.py` (rutas), `web/workspace.py`
  (`calibraciones`), `frontend/src/components/DemandaMedida.tsx`.
- DIgSILENT: `tools/casos_pf.py` (`NOMBRES`, `MARCA`, `casos_del_proyecto`, `preparar_sin`,
  `crear_con_proyecto`), `tools/ajuste_cabecera_pf.py` (usa `caso_del_sistema(app, 'sin'|'con')`).
- Herramienta: `tools/sistema_web.py` (`LIBROS` con nombres de carpeta de una empresa).
- Perfil: `src/igea_dgs/perfil_empresa.py` (`patron_libro_clientes`).
- Carril `engine` para los índices (abrir libros); `powerfactory` para la calibración.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Árbol de libros por año | nuevo `src/igea_dgs/libros_por_anio.py`: `LibroDeAnio(ruta, relativa, anio)`, `arbol_de_libros(carpeta)` (subcarpetas `\d{4}` a cualquier profundidad; sueltos con `anio=None`; ignora `~$`), `anios_de(arbol)`, `libros_del_periodo(arbol, periodo)` | RF-1, RF-2, RF-3, RF-8, RF-9, RF-26, RF-27 |
| B. Periodo AAAA o AAAA-MM | `demanda_medida.py`: `en_periodo(fecha, periodo)` usado por `maxima_de_registros` y `maxima_de_barra`; `_mes_valido` acepta año | RF-7 |
| C. Mes por nombre universal | `demanda_medida.py`: `mes_generico(nombre, anio)` (MMAA, AAAAMM, AAAA-MM, MM-AAAA, nombre del mes es/en; exige un único candidato del año); `mes_de_nombre` acepta lista de patrones; `perfil_empresa.py` acepta lista | RF-5, RF-6, RF-6b |
| D. Catálogo de clientes por año | `catalogar_libros_clientes` sobre el árbol: `nombre` = ruta relativa, `anio` de carpeta, aviso RF-5; duplicados por mes (013:RF-5) | RF-3, RF-4, RF-5, RF-11 |
| E. Índice de cabecera | `demanda_medida.py`: `indexar_libro_cabecera(path)` → hojas útiles, meses con registro, motivo si no sirve; `services.demanda_cabecera_indexar` (trabajo `engine`, progreso por libro, cancelable, reutiliza por (tamaño, mtime), publica todo o nada); foto recursiva para RF-31 | RF-28, RF-29, RF-31, RF-32, RF-33 |
| F. Medidor → hoja | `Cabecera.maxima(..., alimentador)`: tras medidor y base, `hojas_del_alimentador(hojas, codigo)` (código solo o tras un prefijo separado); ambigüedad RF-12b; RF-30 entre libros del mismo año por mtime | RF-12, RF-12b, RF-13, RF-30 |
| G. Búsqueda por periodo | `demanda_cabecera` y `_demanda_por_barra` construyen `Cabecera` con `libros_del_periodo`; sin periodo y con años, `UserError` | RF-8, RF-9, RF-10 |
| H. Casos por año | `casos_pf.py`: `nombre_caso(rol, anio)` → «Sin proyecto 2025»; marca `igea-dgs:011:sin@2025`; `casos_del_proyecto(app, anio=None)`; sin año = casos actuales; `preparar_sin(plan)` con `plan['anio_casos']` copia del «Caso base»; `crear_con_proyecto` con año; `ajuste_cabecera_pf.py` pasa `plan['anio_casos']` a `caso_del_sistema` | RF-14 a RF-18, RF-21 |
| I. Plan y registro por año | `ajuste_plan`: `anio_casos` = año del periodo salvo que sea el de los casos sin año (registrado por proyecto en el espacio; por defecto, el de su primera calibración); los sin medición del año en `sistema['sin_medidor']`, con la demanda del «Caso base» porque «Sin proyecto <año>» sale de él; `ultima_calibracion` y `_guardar_calibracion` por `(proyecto, año)` | RF-19, RF-20, RF-24 |
| J. Tipos por contenido | `demanda_medida.py`: `clasificar_carpeta_demanda(dir)` → `{medidores, cabecera, clientes, suministros}` por sus libros (columnas alimentador+medidor; hojas con fecha+kW; hoja «resumen»; puntaje de suministros existente); `sistema_web.py` sin `LIBROS`, con `--medidores/--cabecera/--clientes` opcionales | RF-25, RF-25b, RF-25c |
| K. Web | `DemandaMedida.tsx`: selector de año (RF-22), «todo el año» y meses del año (RF-23); panel de libros por año (árbol con ruta relativa, meses, hojas, origen del mes, uso y motivo) y dónde dejar un año nuevo; botón «Actualizar índice» de cabecera; año y caso en el resultado del ajuste | RF-22, RF-23, RF-24, RF-34, RF-35 |
| L. Cargas en los casos del año | `services.base_del_ajuste` saca `anio_casos` del caso de la calibración base; `tools/cargas_pf.py` (`casos_pf.anio_del_plan`, `tres_casos(app, anio)`) escribe demandas en «Sin proyecto <año>» y cargas en «Con proyecto <año>»; el informe lleva `casos` y `anio_casos` | RF-36, RF-37, RF-38 |
| M. Obras en los casos del año | `obras_ejecutar(..., anio_casos)` y `ObrasIn.anio_casos`; `tools/obras_pf.py` crea «Con proyecto <año>» tras las obras de «Sin proyecto <año>»; `casos_pf.obras_del_con_proyecto_sin_anio` y `operacion_de_las_obras` para las cargas reutilizadas; `casos_pf.cargas_que_no_convergen_juntas` prueba cada carga sola y el caso sin cada una | RF-41, RF-42, RF-42b, RF-43 |
| N. Escalera de obras | `obras_pf.escalera_de_obras` (bancos en barras que existen sin la carga, sección de toda la troncal al conductor aéreo de su tensión con más corriente, terna); `services.obras_escalera` aplica escalón a escalón con el paso de obras y se detiene en el primero que converge; `POST /pf/obras/escalera`; en el informe de cargas, «Proponer obras en escalera» cuando hay `no_convergen_juntas` | RF-44 |
| O. Cargas nuevas incompletas | `cargas_pf.leer_hoja_nuevas` rechaza la fila sin alimentador (TRONCAL) con hoja, fila y SED; el plan las lista en `row_errors` y el paso de cargas las muestra | RF-45, RF-46 |
| P. Cargas independientes | `tools/cargas_pf.py`: `_a_un_extremo` conecta en un extremo existente del tramo que ya parte otra carga (de esta tanda o de otra); `_una_carga` mide con las variaciones de las demás cargas inactivas | RF-47, RF-48 |
| Q. Campos de la web | `InputsPanel.tsx`, `DemandaMedida.tsx`, `InformesPF.tsx`: subida y ruta siempre visibles para reemplazar; desactivados solo con un trabajo que los invalidaría, con el motivo | RF-39, RF-40 |

## Decisiones

- Año = carpeta de cuatro cifras a cualquier altura bajo la carpeta elegida; los libros de
  debajo heredan el año más cercano. Descartado: deducir el año solo del contenido, porque
  obliga a abrir libros de cientos de MB para listar y no decide si un libro trae dos años.
- Casos sin año en el nombre = los que ya existen (su año queda registrado); los demás años
  llevan sufijo. Descartado: renombrar los actuales a «Sin proyecto 2026», porque rompería
  estudios, obras, informes y gemelo, que los buscan por nombre y están fuera de alcance.
- «Sin proyecto <año>» copia del «Caso base»: los sin medición del año tienen la demanda del
  archivo sin escribir nada (RF-19). Descartado: copiar el «Sin proyecto» de otro año y
  restaurar cargas, porque mezcla años y lo hecho a mano en él.
- Índice de cabecera en el espacio, por (ruta relativa, tamaño, mtime). Descartado: reabrir
  todo en cada búsqueda, porque el coste crece con cada año y libro (RF-28).
- Hoja por código del alimentador con una regla general (código tras un separador).
  Descartado: prefijos de hoja en el perfil, porque cada empresa nombra distinto y la regla
  general las cubre sin configurar (P13).
- Tipos de libro por contenido (RF-25b). Descartado: nombres de carpeta en el perfil, porque
  cada empresa (y el mismo usuario) organiza las carpetas a su manera.

## Comprobación contra la constitución

- P7 (nada largo en una petición): índices y búsquedas son trabajos; asignar una carpeta solo
  lista ficheros, sin abrirlos.
- P9 (datos de la distribuidora): pruebas con libros sintéticos en `tmp_path`; las de datos
  reales tras `IGEA_DEMANDA_DIR`, sin imprimir valores.
- P13 (universal): ningún nombre de carpeta, libro, prefijo, código o año de una empresa en
  el código; un perfil solo añade patrones como opción.
- Determinismo: árbol ordenado por ruta relativa (casefold, luego literal), años ordenados.

## Estrategia de pruebas

- Sintéticas (`tests/test_libros_por_anio.py`, nuevo): árboles sorteados de años,
  subcarpetas, libros sueltos y nombres (semilla en el mensaje), con libros `.xlsx` mínimos;
  mes por nombre en todas las formas y con nombres de empresas inventadas; hojas por código
  con prefijos sorteados; ambigüedades.
- Web (`tests/test_demanda_medida_web.py`): índice como trabajo, cancelación que conserva el
  anterior, cambio de carpeta durante el índice, periodo sin año con años → error, plan con
  `anio_casos`.
- DIgSILENT doble (`tests/fake_pf.py`): casos por año, marca, caso ajeno, reutilización,
  «Sin proyecto» sin año intacto.
- Datos reales (con `IGEA_DEMANDA_DIR`): los 7 alimentadores de 2025 encuentran hoja y máxima;
  los libros de clientes 2025 y 2026 tienen mes; sin imprimir valores.
- DIgSILENT real: Chincha, Pisco e Ica con `tools/sistema_web.py --periodo 2025`; flujo de
  «Sin proyecto» (2026) igual antes y después.
- Cada prueba cita `025:RF-n`.

## Riesgos

- Otros guiones que llaman a `caso_del_sistema` sin año siguen en los casos actuales: correcto
  por alcance; una prueba lo fija.
- `ws.calibraciones` cambia de forma: se migra al cargar (clave antigua = casos sin año).
- Clasificar por contenido abre libros: solo la primera hoja con cabecera, y en el trabajo.
