# Plan — Spec 105

## Módulos

- `dominio/meses_copiados.py` (RF-4, RF-13, RF-14): `mes_de_registro` y `meses_copiados(series, meses)`, sin leer
  ficheros. Es la función que el reconocimiento de libros nuevos (spec 104, rama `trabajo/libros-nuevos`) puede usar
  para 104:RF-15: allí no existía todavía, y se acordó que quedara en el dominio.
- `dominio/evolucion_mensual.py` (RF-5 a RF-11, RF-37): indicadores por mes de una serie y crecimiento, variación,
  tendencia y mes de mayor valor. Las fórmulas son las del libro de AL209 hecho a mano.
- `dominio/conciliacion_clientes.py` (RF-34 a RF-38): `clave_cliente`, `cadenas_de_renumeracion`, `veredicto`,
  `posibles_renumeraciones` y `fijos_sobre_cabecera`.
- `evolucion_clientes.py` (RF-1 a RF-16, RF-27, RF-34 a RF-38): lee con `leer_suministros`, `libros_con_mes` y
  `curvas_por_cliente` (nombres públicos nuevos de `pronostico_demanda`, que añade `avance` y `asignaciones`), el
  resumen de cada libro mensual (`leer_maestro`) y la cabecera con `equivalencias` y `curvas_de_cabecera`; escribe el
  libro con pandas y openpyxl como el guion de referencia.
- `archivo_informes.py` (RF-28 a RF-33): `config/archivo.json` local (en `.gitignore`, ejemplo
  `config/archivo.example.json`) y `archivar(fichero, tipo, ambito, periodo)`.
- Web: `web/evolucion_fijas.py` (servicio y trabajo) y `web/evolucion_fijas_api.py` (rutas), montadas con dos líneas en
  `web/app.py`; contratos en `web/api_contract.py`. `services.propietarios_de_sed` sale de `_cruzar_clientes_en_red`
  para que la conciliación use la misma pertenencia de SED de la red cargada (RF-34).
- Frontend: pestaña `features/clientesfijos/` (`EvolucionFijas`, `Tablero`, `Graficos`, `datosTablero`), tarjeta
  `app/ArchivoInformes.tsx` junto a las opciones, cliente `api/evolucionFijas.ts` y `shared/graficos.ts` con las piezas
  de las gráficas SVG que ya usaba `CurvaCabecera`.

## Decisiones

- Sin librería de gráficos: la web ya dibuja en SVG con tokens (`CurvaCabecera`); se extraen sus piezas a `shared/` en
  vez de añadir una dependencia y su licencia (086:RF-21). Descartado: Recharts o Chart.js, que no hacen falta.
- El buscador del tablero es TypeScript propio (Levenshtein con transposición, sin tildes): la búsqueda es sobre los
  clientes del resultado, en el navegador, y no hace falta `rapidfuzz` ni otra dependencia en el lock.
- Mes copiado: P y Q iguales en el mismo día y hora en ≥ 95 % de las parejas, en más de la mitad de las series con los
  dos meses (la regla de 104:RF-15). El guion de referencia pedía la mitad o más y solo la P: con AL209 dan lo mismo.
- El total del alimentador suma las máximas de cada cliente, como el libro de referencia; la máxima coincidente de la
  suma va aparte.
- Un cliente del resumen de un libro que no está en suministros entra en el alimentador que dice el libro, con su
  veredicto «una sola fuente»; nunca por el nombre.
- La participación en la cabecera es opcional en la web (por defecto apagada): sus libros pesan cientos de MB.
- El archivo copia por un temporal y `os.rename`, que en Windows no reemplaza: nunca se pisa un fichero archivado.

## Pruebas

- `tests/test_evolucion_clientes_fijos.py`: dominio y cálculo con libros sintéticos (renumeración, mes copiado,
  cliente que entra a mitad, mes incompleto, tendencia con un mes faltante, cabecera, libro, archivo, conciliación).
- `tests/test_evolucion_fijas_web.py`: API, trabajo, resultado, curva, archivo y su fallo.
- `frontend/test/evolucionFijas.test.mjs`: lógica y render del tablero (`npm test`).
- Comprobación real, solo lectura y fuera de git: AL209 de enero a octubre de 2026 frente al libro hecho a mano, y otro
  alimentador; la web recorrida en el navegador.
