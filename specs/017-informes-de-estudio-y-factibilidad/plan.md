# Plan — Spec 017

Estado: aprobado (2026-10-15) · Fecha: 2026-10-15

Lee: `docs/constitution.md` y `specs/017-informes-de-estudio-y-factibilidad/spec.md`.

## Resumen

El mismo reparto que las specs 011 y 016: lo que se calcula y se redacta va a `src/` y se
prueba sin DIgSILENT, y los objetos de DIgSILENT quedan en un guion de `tools/`. El guion
mide los casos y las etapas, exporta las imágenes y escribe un JSON. Con ese JSON, `src/`
escribe el `.docx`. Así el Word se puede regenerar sin volver a abrir DIgSILENT, y el JSON
de RF-25 es el contrato entre las dos mitades.

## Contexto técnico

- Medidas por alimentador: `tools/estudios_pf.py` (`medida`, `medidas`) y `Limites` de
  `src/igea_dgs/estudios_pf.py`. Se reutilizan, no se copian (P5).
- Obras en variaciones de «Con proyecto»: `src/igea_dgs/obras_pf.py` y `tools/obras_pf.py`
  (spec 011), con la troncal y la migración de la spec 016 (`troncal.py`, T6 a T8 de la
  016 pendientes).
- Casos y restauración del proyecto: `tools/casos_pf.py`.
- Medición de cabecera del mes de análisis: `src/igea_dgs/demanda_medida.py` (spec 013).
- Exportación del diagrama: `GetGraphicsBoard().WriteWMF`, ya usada en
  `tools/powerfactory_acceptance.py`. Para el `.docx` se exporta a PNG; si la versión no lo
  permite, se convierte de WMF (T4 lo comprueba en DIgSILENT).
- Trabajos de la web: carril `powerfactory` de `src/igea_dgs/web/jobs.py`, como los pasos
  3 y 4.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| 1. Configuración del informe | `src/igea_dgs/informes.py` (nuevo), `config/perfiles/electro_dunas.json` | RF-4, RF-5, RF-13, RF-14, RF-115 |
| 2. Cálculos y veredictos | `src/igea_dgs/informes.py` | RF-15 a RF-19 (forma de los datos), RF-31, RF-33, RF-34, RF-43, RF-54 a RF-60, RF-71, RF-72 |
| 3. Redacción | `src/igea_dgs/informes.py` | RF-20, RF-21, RF-22, RF-50, RF-107, RF-108, RF-121, RF-122 |
| 4. Libro de pérdidas y tabla de costes | `src/igea_dgs/libros_informe.py` (nuevo), `config/costes_referenciales.example.json` (nuevo) | RF-39b a RF-39e, RF-40c, RF-61 a RF-64 |
| 5. Escritura del `.docx` | `src/igea_dgs/informe_docx.py` (nuevo) | RF-2, RF-3, RF-6 a RF-9, RF-23 a RF-25, RF-27, RF-44, RF-45, RF-106, RF-113, RF-114, RF-118, RF-120 |
| 6. Guion: casos, medidas e imágenes | `tools/informes_pf.py` (nuevo), `tests/fake_pf.py` | RF-1, RF-1b, RF-10 a RF-12, RF-28 a RF-30, RF-46 a RF-49, RF-52, RF-53, RF-109 a RF-112, RF-116, RF-117 |
| 7. Guion: etapas de obras | `tools/informes_pf.py`, `tools/obras_pf.py` | RF-32, RF-35 a RF-42c |
| 8. Guion: transformador de la SET | `tools/informes_pf.py` | RF-65 a RF-70, RF-119 |
| 9. API y CLI | `src/igea_dgs/web/{app,services,jobs}.py`, `tools/informes_pf.py --plan` | RF-26, RF-82, RF-96, RF-97, RF-99, RF-103 a RF-105 |
| 10. Paso «5 · Informes» | `frontend/src/components/InformesPF.tsx` (nuevo), `FeedersPanel.tsx` | RF-73 a RF-95, RF-98, RF-100 a RF-102, RF-124, RF-125 |

### 1 a 3. `src/igea_dgs/informes.py`

- `ConfigInforme.de_perfil(perfil)`: modelos de los dos informes, banda y umbral (`Limites`
  de la 011), bandas de los dos coloreados, proyecto de transmisión, hojas y columnas del
  libro de pérdidas. Toda clave que falta se lista; no hay valor por defecto (RF-5, RF-14,
  P13). Se lee de una clave `informes` del perfil, y la banda reutiliza la clave
  `estudios` de la 011 si ya está.
- `Caso` y `Etapa`: dataclasses con lo que mide el guion (fuente, pérdidas, mínima por
  fase o trifásica, cargabilidad máxima, nodos y tramos fuera de límite, convergencia).
  `Caso.desde_json` es el contrato con el guion.
- `perdidas_anuales(kw_fuente, kw_perdidas, fc, reconocido_pct, precio)`: RF-54 a RF-58,
  con las fórmulas del libro `informeModeloperdidas.xlsx`. La prueba compara con los
  números de EMAPICA que da el modelo.
- `factor_de_carga(medicion_mes)`: energía entre máxima por horas (RF-60).
- `etapa_recomendada(etapas, limites, evaluar_todas)`: RF-31, RF-33, RF-34.
- `veredicto_factibilidad(proyectado, trafo, limites)`: RF-71, RF-72.
- `redactar_*`: frases a partir de los números, sin adjetivos que estos no sostengan
  (RF-20). Las frases fijas del modelo (antecedentes, descripción) son plantillas en el
  módulo, con los huecos del formulario.

### 4. `src/igea_dgs/libros_informe.py`

- `leer_libro_perdidas(ruta, alimentador, columnas)`: sistema eléctrico, pérdidas
  reconocidas en potencia y en energía, y precio de compra. Las hojas y columnas se buscan
  por los nombres del perfil (RF-63). Si el alimentador no está, devuelve el hueco con su
  motivo (RF-64). `openpyxl` ya está en las dependencias.
- `leer_costes(ruta)`: bancos y reguladores con kvar o tipo, inversión, mantenimiento,
  fuente, fecha y marca «referencial» (RF-39b, RF-39e, RF-40c).
- `config/costes_referenciales.example.json`: precios de mercado buscados en la web, cada fila con
  su URL y fecha (RF-39d). Es un fichero de ejemplo versionado, sin datos de la empresa.

### 5. `src/igea_dgs/informe_docx.py`

- Se escribe con `python-docx`, abriendo el modelo de la empresa como documento base: así
  quedan su cabecera, su pie, su logo y sus estilos. Se vacía el cuerpo y se escriben las
  secciones en el orden de RF-106 (factibilidad) y del modelo de Casa Blanca (estudio),
  con los estilos de título y de tabla del modelo.
- Los huecos (RF-23) se escriben con un estilo resaltado y su motivo, y se listan en el
  JSON para el resumen de la web (RF-102).
- Se escribe en un `.tmp` y se renombra al final: si se cancela, no queda un `.docx` a
  medias (RF-27).

### 6 a 8. `tools/informes_pf.py`

- Plan JSON → `ejecutar(app, plan)` → JSON de resultados + imágenes en la carpeta del
  trabajo. La CLI usa el mismo plan que la web (RF-105).
- Al empezar, se anotan el caso, las variaciones y los escenarios activos y el coloreado del
  diagrama. Al terminar, aunque haya un error o una cancelación, se restauran (RF-28,
  RF-116), como en `casos_pf.py`.
- Imágenes: coloreado por tensión y por cargabilidad con las bandas del perfil, diagrama
  geográfico con el mapa de fondo de DIgSILENT o esquemático si no hay (RF-10 a RF-12,
  RF-110 a RF-112), y un rótulo con flecha para la carga nueva (RF-117).
- Etapas (parte 7): cada etapa es una obra de la 011 o de la 016 en su variación. Bancos
  existentes: se leen los del proyecto estudiado y, si el plan trae un proyecto anterior
  («CA101 13»), los de ese. Los que faltan se crean en el mismo nodo, con el mismo tipo y
  los mismos kvar (RF-36 a RF-38). Bancos nuevos con `ComCapo` y reguladores con
  `ComPlaceopt`, con los costes de la parte 4 (RF-39 a RF-40d). Conductor y migración con la
  troncal de la 016 hasta la SED del operador (RF-41 a RF-42c).
- Transformador de la SET (parte 8): se activa el proyecto de transmisión, se busca la carga
  concentrada del alimentador por su nombre en la barra de la SET, se le pone la P y la Q de
  cabecera de cada estado, se corre el flujo, se lee la cargabilidad de cada devanado y se
  sale **sin guardar** (RF-65 a RF-68). Después se reactiva el proyecto del alimentador.

## Decisiones

- `python-docx` con el modelo como documento base. Descartado: `docxtpl` (se evaluó en la
  sesión anterior), porque obliga a marcar el Word de la empresa con etiquetas Jinja, y cada
  modelo nuevo de otra empresa necesitaría esa preparación. Con la base basta el `.docx` tal
  como lo usa la empresa (RF-4).
- El guion escribe un JSON y el Word se escribe fuera de DIgSILENT. Descartado: escribir el
  Word dentro del guion, porque cada cambio de redacción obligaría a repetir los flujos.
- Las etapas reutilizan las obras de las specs 011 y 016. Descartado: crear los objetos de
  DIgSILENT en el guion del informe, porque duplicaría la lógica de las variaciones (P5).
- Los bancos del proyecto anterior se emparejan por el nombre del nodo. Ese nombre sale del
  código de la red de origen, que es el mismo en los dos proyectos. El que no se encuentra se
  avisa y no se crea (RF-36d). No se busca el más cercano.

## Comprobación contra la constitución

- P8 (entorno): `python-docx` entra en `requirements.txt` y en `pyproject.toml`.
- P9 (datos): los informes, los JSON y las imágenes se escriben en el espacio de trabajo
  local. Las pruebas usan modelos `.docx` sintéticos, creados en la propia prueba. Ninguna
  lee `referencia/`.
- P13 (universal): banda, umbral, bandas de coloreado, modelos, libro y proyecto de
  transmisión salen del perfil. Las de Electro Dunas van en `config/perfiles/electro_dunas.json`
  como convenciones, con rutas relativas al espacio de trabajo.
- Escala: las medidas y las etapas van por alimentador marcado, sin número fijo. Cada
  imagen se recorta al alimentador, sin recorrer la red entera por alimentador.
- Cambios manuales en DIgSILENT: el informe no borra variaciones del operador; solo crea las
  suyas, con un prefijo propio.

## Estrategia de pruebas

- `tests/test_informes.py`: configuración, fórmulas de pérdidas con los números de EMAPICA,
  veredictos y redacción (partes 1 a 3).
- `tests/test_libros_informe.py`: libro de pérdidas y tabla de costes, con libros
  `openpyxl` sintéticos (parte 4).
- `tests/test_informe_docx.py`: un modelo sintético con cabecera y estilos; se comprueba el
  orden de las secciones, las tablas, los huecos y que no queda un `.tmp` (parte 5).
- `tests/test_informes_pf.py`: el guion sobre `fake_pf`, incluidas la restauración y la
  cancelación (partes 6 a 8).
- `tests/test_web_api.py`: un caso por endpoint nuevo (parte 9).
- Prueba en DIgSILENT (P: probar en DIgSILENT real): CA101 desde cero con el proyecto
  anterior «CA101 13» para los bancos, y una carga nueva del libro de cargas nuevas con
  AD08 V4.
- Cada prueba cita `017:RF-n`.

## Riesgos

- `ComCapo` y `ComPlaceopt` necesitan licencia y parámetros que aún no se han probado en
  DIgSILENT: la T6 empieza por una sonda, como la de `ComOpri` en la 012.
- Exportar PNG desde `GetGraphicsBoard` en PF 2024: si solo da WMF, hay que convertirlo, y
  eso añade una dependencia. La T4 lo comprueba antes de escribir nada más.
- AD08 abierto por otro usuario: RF-70 deja el hueco y el resto del informe sale.
- Las etapas 4 y 5 necesitan las T6 a T8 de la 016. Hasta entonces, el informe de estudio
  sale con las etapas 1 a 3 y dice que las 4 y 5 no se evaluaron.
