# Plan — Spec 104

## Módulos

- `src/convertersmartgrid/demanda_medida.py` (RF-27 a RF-29): `catalogar_libros_clientes` da a los libros el año de la
  carpeta elegida cuando su nombre es un año; sin año, prueba el mes del nombre con los años de sus fechas
  (`mes_generico`); sin mes, deja un aviso. `_mes_de_valor` reconoce la FECHA en texto «dd/mm/aaaa» bajo una columna de
  fecha, como ya hacía `periodo_de_fecha`.
- `src/convertersmartgrid/libros_nuevos.py` (nuevo, capa aplicación; RF-1, RF-3, RF-7 a RF-20): foto de una fuente y
  cambios frente a lo conocido; verificación de un libro de clientes (mes y cómo, registros frente a días × 96, periodo,
  avisos de lectura, nuevos y faltan, sin suministro, libro de suministros de otro mes, en cero, solape, mes repetido) y de
  uno de cabecera (meses, meses incompletos y repetidos por hoja); los textos del aviso; el estado del reconocimiento
  (`demanda/libros_nuevos.json` del espacio), que se publica de una vez.
- `src/convertersmartgrid/web/libros_nuevos.py` (nuevo, presentación; RF-1 a RF-6, RF-16, RF-19 a RF-23):
  `VigilanciaLibros` compara fotos (al arrancar, al abrir un espacio en otro hilo y cada intervalo), encola el trabajo
  `libros_nuevos` en el carril del motor si está libre, reindexa con `services.demanda_clientes_indexar` y
  `demanda_cabecera_indexar`, verifica, avisa en el registro y en el estado, marca el libro repetido como inactivo y el
  dataset como desactualizado, y lo regenera en un proceso `spawn` propio, fuera de la cola, para no ocupar el carril del
  motor mientras lee todos los libros.
- `src/convertersmartgrid/web/services.py` (RF-16): el índice de clientes deja inactivos los libros que el estado marca
  como repetidos; `_foto_fuente_clientes` usa la foto de `libros_nuevos`.
- `src/convertersmartgrid/web/app.py` y `api_contract.py` (bloques propios; RF-1, RF-20, RF-21): la vigilancia en el
  `lifespan`, la revisión al abrir el espacio y tres rutas: `GET …/demanda/libros-nuevos`, `POST …/revisar` y
  `POST …/avisos/{id}/visto`. `__main__` enciende la vigilancia solo en el servidor real (`CSG_LIBROS_NUEVOS`).
- `src/convertersmartgrid/pronostico_demanda.py` (RF-23 a RF-26): `perfil_del_dataset` (del guion de la revisión del
  2026-11-12), que `guardar_dataset` escribe en `perfil.json`; `regenerar_dataset` arma y guarda sin entrenar;
  `_curvas_por_cliente` aparta el libro que repite el mes anterior. `tools/pronostico_demanda.py --guardar-dataset` ya
  pasa por `guardar_dataset`: no se duplica.
- `frontend/src/app/AvisosLibros.tsx` (RF-20 a RF-22): los avisos sin ver, «Dar por visto» y el estado del dataset; se
  relee al terminar un trabajo `libros_nuevos`.

- `src/convertersmartgrid/web/fondo.py` (nuevo, presentación; RF-30, RF-32, RF-33, RF-36, RF-37): el carril de
  fondo. `operador_trabajando` mira la cola (motor y DIgSILENT de todos los espacios); `ProcesoFondo` corre una función
  en un proceso `spawn` que baja su prioridad y se termina al ceder; `ContextoFondo` hace de `JobContext` para los
  índices de `services`, que reciben `ejecutar=` para leer cada libro en ese proceso.
- `src/convertersmartgrid/web/libros_nuevos.py` (RF-30 a RF-39): `VigilanciaLibros` deja de encolar en el motor. Un hilo
  propio atiende las revisiones pedidas, guarda la foto de cada fuente al publicar su índice y la lista `por_verificar`
  (lo hecho no se pierde al ceder), y regenera el dataset tras el reposo. Cada cambio se publica como evento
  `libros_nuevos`.
- `frontend/src/app/AvisosLibros.tsx` (RF-31, RF-35, RF-38, RF-39): indicador discreto del carril de fondo, botón
  «Verificar todos ahora», cuándo se regenerará el dataset; se relee con cada evento `libros_nuevos`
  (`useWorkspace` lo cuenta).

## Decisiones

- Carril de fondo fuera de `JobManager` (RF-30). Descartado: un carril `fondo` más en `LANES`, que el diario de trabajos
  guardaría y mostraría como interrumpido tras reiniciar, contaría en `en_curso` (el lanzador no cerraría la web) y
  aparecería en la barra de trabajos.
- Ceder terminando el proceso del libro (RF-32, RF-33). Descartado: puntos de control dentro del lector de libros, que
  no cortan una lectura de calamine de decenas de segundos y siguen compitiendo por el GIL de la web.

- Foto por listado (ruta relativa, tamaño y fecha), como el índice de cabecera (025:RF-28). Descartado: una huella del
  contenido, que obliga a leer libros de cientos de MB en cada revisión.
- Sin foto anterior, la base es el índice publicado (RF-6). Descartado: dar por nuevos todos los libros, que verificaría
  veinte libros en el primer arranque.
- Mes repetido: P y Q iguales en el mismo día del mes y hora, solo en los registros en que la P cambia (un medidor
  congelado no es una copia: IN216 de Ica daba «igual» todos los meses), ≥ 95 % en más de la mitad de las series.
  Descartado: comparar la energía del mes, que no distingue una copia de un mes parecido.
- El dataset se regenera en un proceso propio, no en la cola: la cola rechaza con 409 lo que el operador pida en el mismo
  carril, y leer todos los libros tarda decenas de minutos.

## Pruebas

- `tests/test_libros_nuevos.py`: libros sintéticos «0125 Pulso e», «1025 Pulso» y «0526clientesImportantes» en la
  carpeta de su año (fallan sin el arreglo), verificación, mes repetido, medidor congelado, cabecera, foto, dataset y
  herramienta.
- `tests/test_libros_nuevos_web.py`: la web con `TestClient`, sin vigilancia periódica; reconocimiento, aviso, visto,
  libro repetido inactivo también al reindexar, motor ocupado, revisión al abrir sin esperar y dataset regenerado.
- Comprobación real, solo lectura, con un espacio temporal fuera del repositorio: cifras en el informe de la tarea.
