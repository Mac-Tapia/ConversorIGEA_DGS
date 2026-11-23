# Spec 034 — Motor base de conversión y contrato universal de fuentes

Estado: cumplida (2026-11-22: T7, RF-42, con su rojo y su verde; 2026-11-15: T4 a T6 con su rojo y su verde) · aprobada (2026-11-14: RF-34 a RF-41, C4 TO-BE y ADR; RF-1 a RF-33 cumplidos desde el 2026-10-29) · Fecha: 2026-10-29 · Origen: `docs/REVISION_SPECS_2026-10-29.md`; ampliación del 2026-11-14: F-20 del Plan Maestro V1 (§30.7), aceptada por el auditor ca

## Contexto y objetivo

El motor de conversión es anterior al desarrollo por specs: `CODIGO_FUENTE.md` marcaba sus
módulos como «base» y 60 ficheros de pruebas no citaban ninguna spec. Además, el 2026-10-13
entró sin spec el contrato universal de fuentes (commits `b5b70a8d`, `97fe38b7`, `1f415549`,
`ff4c2222`, `1ddff734`, `be8ce5cf` y `6d0ef204`, en inglés). La revisión del 2026-10-29
encontró que ese comportamiento, el más usado del conversor, no tenía un solo requisito.

Esta spec no añade nada: escribe como requisitos lo que el código ya hace y sus pruebas ya
comprueban, para que la 033 pueda exigir que todo fichero de `src/` y de `tests/`
pertenezca a una spec. Lo que cambie a partir de aquí entra en una spec nueva que cite la
034.

Ampliación del 2026-11-14 (F-20 del Plan Maestro V1, §30.7). El C4 AS-IS de RF-31 dice lo que hay, pero no adónde
va la arquitectura ni por qué: las decisiones de frontera (partir `web/services.py`, el DXF de los expedientes, la
escritura duradera del estado, los avisos en vez de excepciones mudas) estaban repartidas entre specs, veredictos y
chats. Por orden del usuario se amplía esta spec en vez de abrir otra (memoria «modificar lo que existe»): un C4
TO-BE que extiende el mismo modelo y un ADR por decisión, y pruebas que los comparan con lo que declara el código,
para que no se desfasen como se desfasaba la arquitectura escrita a mano (spec 090).

## Usuarios / actores

Quien convierte (web y CLI), PowerFactory al importar, y quien mantiene el motor.

## Historias de usuario

- H1: Como ingeniero quiero convertir un TXT, una base Access o un paquete VNR-GIS de
  cualquier distribuidora en un DGS fiel a la entrada, sin inventar datos.
- H2: Como ingeniero quiero que una entrada defectuosa falle con un mensaje que diga qué y
  dónde, sin tumbar los demás alimentadores.
- H3: Como responsable quiero que las tres fuentes pasen por el mismo contrato y que
  DIgSILENT solo consuma lo que salió de la ejecución fuente activa.

## Requisitos funcionales (EARS)

Entrada

- RF-1: EL SISTEMA leerá los TXT de RED, CARGA y BD_Equipo, en la disposición
  reducida y en la completa, leyendo cada tabla una sola vez.
- RF-2: EL SISTEMA reconocerá cada TXT por su contenido y no por su nombre, y SI un fichero
  no encaja, ENTONCES dirá qué es, qué se esperaba y con qué evidencia.
- RF-3: EL SISTEMA leerá como segunda entrada la base Access de CYMDIST (`.mdb`) y, como
  filtro opcional, su estudio (`.xst` o `.zxst`).
- RF-4: EL SISTEMA leerá paquetes VNR-GIS con un CRS proyectado en metros, rechazará con el
  nombre del CRS uno en grados o inexistente y no inventará valores al cargar sus filas.
- RF-5: SI una entrada está vacía, truncada o con referencias rotas, ENTONCES EL SISTEMA
  fallará con el fichero y la línea, y SI el fallo es de un alimentador, solo fallará él.
- RF-6: EL SISTEMA leerá el libro de cargas de SED en Excel o CSV con las variantes de
  nombre de sus columnas, y tratará como error un par de valores que no cuadra.

Catálogo y modelo

- RF-7: EL SISTEMA resolverá cada tipo de equipo por su código, por un alias explícito del
  usuario o por un vecino único, sin renombrar los códigos de origen ni inventar tipos.
- RF-8: CUANDO el catálogo de la entrega llega incompleto, EL SISTEMA lo completará con
  otros ficheros sin sobrescribir lo cargado, y dirá de dónde vino cada código y la
  cobertura antes y después.
- RF-9: EL SISTEMA modelará cada alimentador con sus cargas y SED en su alimentador, cada
  carga repartida entre sus fases, sus clientes y su tipo, y dibujará también el
  alimentador que solo trae su cabecera.
- RF-10: SI un alimentador tiene islas eléctricas, ENTONCES EL SISTEMA las dirá en el
  manifiesto; en modo estricto el alimentador fallará y fuera de él se convertirá con aviso.
- RF-11: EL SISTEMA convertirá sin coordenadas cuando no se pida geografía y, cuando se
  pida, exigirá coordenadas completas, usará las longitudes georreferenciadas y comprobará
  la escala.
- RF-12: EL SISTEMA conservará los bancos de condensadores de la fuente con su capacidad,
  fases y escalones, sin inventar los que falten.

Salida

- RF-13: EL SISTEMA escribirá el DGS con el perfil de esquema de PowerFactory (DGS 1.8.4) y
  lo validará en modo estricto (identificadores únicos, punteros y cubículos).
- RF-14: DONDE se pida, EL SISTEMA escribirá las tablas del DGS en TSV o Excel y una vista
  previa georreferenciada en HTML y GeoJSON.
- RF-15: EL SISTEMA publicará cada DGS de forma atómica, escribirá siempre el manifiesto del
  lote (también al cancelar o al fallar) y dará a dos salidas que chocan un sufijo
  determinista.
- RF-16: EL SISTEMA convertirá cualquier número de alimentadores con un coste lineal en el
  número de tramos.
- RF-17: DONDE se pida, EL SISTEMA unirá todos los alimentadores en una sola red,
  separando un nodo compartido a dos tensiones y dejando fuera de servicio lo inalcanzable.
- RF-18: EL SISTEMA convertirá los alimentadores de aceptación (PA297 de 22,9 kV y SL193 de
  10 kV) por las dos entradas con los mismos elementos que la fuente.

Contrato universal de fuentes (2026-10-13)

- RF-19: EL SISTEMA auditará las tres fuentes con un único contrato, sin ramas por modo, y
  la web mostrará la auditoría que calcula el servidor.
- RF-20: EL SISTEMA guardará cada ejecución fuente con los originales y sus huellas, y
  rechazará en la conversión un fichero de otra fuente o de otra ejecución.
- RF-21: EL SISTEMA solo dejará a PowerFactory consumir el DGS de la ejecución fuente
  activa, y escribirá los metadatos del alimentador una sola vez, deshaciéndolos si falla
  una escritura.
- RF-22: CUANDO se reconstruye un alimentador, EL SISTEMA no cambiará los datos originales y
  guardará de cada cambio el valor original, el nuevo y su evidencia.
- RF-23: EL SISTEMA incluirá en la aceptación los bancos que solo están en DIgSILENT, con el
  valor de catálogo de su tensión.
- RF-24: EL SISTEMA reunirá la evidencia de la aceptación de cada fuente hasta la carga y el
  estudio en DIgSILENT, y no dará por verificado un resumen con una diferencia de kVAR que
  bloquea.

Otros

- RF-25: EL SISTEMA calculará con pandapower el flujo de la red que escribe en el DGS antes
  de PowerFactory, sin modificar el modelo, y dirá si pandapower falta.
- RF-26: EL SISTEMA dirá qué estudios de PowerFactory se pueden correr y qué dato falta para
  cada uno; un dato ausente o por defecto bloquea el estudio.
- RF-27: EL SISTEMA preparará los datos de la evaluación técnico-económica de PowerFactory
  (`ComTececo`) y rechazará precios ausentes, fuera de rango o periodos inválidos.
- RF-28: EL SISTEMA dará el inventario detallado de un conjunto de datos cargado.
- RF-29: EL SISTEMA exigirá Python 3.12 en el intérprete, en `pyproject.toml` y en el
  entorno, y encontrará la API de PowerFactory desde él.
- RF-30: EL SISTEMA recordará en el espacio de trabajo los ficheros y opciones de la última
  sesión, y uno nuevo sustituirá al anterior.
- RF-31: EL SISTEMA generará la arquitectura C4 interactiva desde su modelo, con todas sus
  vistas y flujos.
- Aclaración de RF-31 (2026-11-14): el C4 AS-IS describe lo que existe y lo que tiene una spec aprobada en
  implementación, con la etiqueta «en implementación»; lo que cambia una frontera va en el C4 TO-BE con su ADR
  (RF-34 a RF-41), y ninguno de los dos repite al otro.
- RF-32: DONDE se pida, EL SISTEMA llevará al tamaño normalizado la SED cuya carga supera su
  transformador (apagado por defecto desde 032:RF-1).
- RF-33: EL SISTEMA dará herramientas de línea de órdenes para el catálogo y el esquema
  (aplicar el catálogo al modelo, construir la tabla de entrada, comparar un esquema y
  proponer alias de tipos de línea) que arrancan sin DIgSILENT.

Arquitectura TO-BE y decisiones (2026-11-14, F-20)

- RF-34: EL SISTEMA mantendrá junto al C4 AS-IS un C4 TO-BE que extiende el mismo modelo Structurizr y solo declara
  las fronteras nuevas o cambiadas, con sus propias vistas.
- RF-35: SI el C4 TO-BE redefine un elemento o una vista del AS-IS, o relaciona un identificador que no está en
  ninguno de los dos, ENTONCES la prueba de arquitectura fallará nombrando el identificador.
- RF-36: EL SISTEMA tendrá un ADR por cada decisión de frontera, con su estado, contexto, decisión, alternativa
  descartada, consecuencias, contratos afectados y vuelta atrás.
- RF-37: SI un elemento nuevo del C4 TO-BE no cita un ADR que lo nombre, o un ADR nombra un elemento C4 que no está en
  ningún modelo, ENTONCES la prueba de arquitectura fallará nombrando el elemento y el ADR.
- RF-38: MIENTRAS un ADR esté vigente, la prueba de arquitectura exigirá que el código declare cada evidencia que cita
  (definición, uso, dependencia o texto) y que sus tareas estén cerradas, y fallará nombrando el ADR y lo que falte.
- RF-39: SI un ADR pendiente ya tiene en el código toda su evidencia y sus tareas cerradas, ENTONCES la prueba de
  arquitectura fallará por ADR desfasado, para que pase a vigente en el mismo cambio que lo cierra.
- RF-40: SI un fichero de `src/` o de `tools/` tiene más excepciones amplias que callan (`pass`, `...`, `continue`,
  `return`, `return True` o `return None`, sin «# justificado:») que las registradas en la deuda del ADR de avisos,
  ENTONCES la prueba de arquitectura fallará con el fichero y sus líneas.
- RF-41: SI a un ADR le falta un campo o una sección obligatorios, o cita un RF, una spec, una tarea o un fichero que
  no existen, ENTONCES la prueba de arquitectura fallará nombrando el ADR y lo que falta.

Custodia sin duplicar (2026-11-22, tarjeta CUSTODIA-ENLACE)

- RF-42: CUANDO un fichero de entrada tenga la misma huella SHA-256 y el mismo tamaño que un original ya custodiado
  en el mismo espacio, EL SISTEMA lo custodiará en la ejecución nueva con un enlace duro a ese original, en lugar de
  copiarlo, sin cambiar el manifiesto ni la huella de la fuente.
- Aclaración de RF-42: SI el enlace no es posible (otro volumen, un sistema sin enlaces o un original que no da la
  huella de su manifiesto), ENTONCES EL SISTEMA copiará el fichero como hasta ahora. La custodia inmutable por
  ejecución de RF-20 se mantiene: cada ejecución conserva su ruta propia y la preparación sigue verificando sus bytes.
  Caso real: una copia VNR-GIS de 0,8 GB recargada varias veces dejó 15 copias idénticas (10,7 GB) en un espacio.

## Requisitos no funcionales

Los de la constitución: determinismo byte a byte (P1), escala (P2), dos disposiciones (P3),
modo estricto (P4), publicación atómica (P6) y universalidad (P13).

## Fuera de alcance

Cambiar el comportamiento del motor: RF-1 a RF-33 solo lo describen. La TO-BE y los ADR (RF-34 a RF-41) tampoco
ordenan mover código: cada cambio entra por la spec y la tarea que su ADR cita (002, 107, 111…). Renderizar la TO-BE
en la página interactiva y en PNG queda fuera, igual que la validación con Structurizr, que necesita Java o Docker.

## Atribución de los commits `feat` sin spec

| Commit | Spec |
| --- | --- |
| `b5b70a8d`, `97fe38b7`, `1f415549`, `ff4c2222`, `be8ce5cf` (2026-10-13) | 034 (RF-12, RF-19 a RF-24) |
| `1ddff734`, `6d0ef204` (2026-10-13, 2026-10-14) | 034 (RF-24) y 006 |
| `d80aab22` (2026-10-13) | 013 (RF-30 a RF-32) |
| `aa97bead` (2026-10-13) | 013 (RF-1 a RF-6) |
| `597d3831` (2026-10-28) | 034 (RF-31) y 027 (corpus PIDE) |
| `8abb25bc` (2026-10-25) | 026 |
| `4ec961e6` (2026-10-28) | 022 (RF-81 a RF-91) |
| `f7498632`, `ea4678e9`, `48fae6dc` (2026-10-18) | 019, 021 y 022 (sus specs se anotaron en el mismo commit) |
| `ee1cc536`, `3e3ea1e5` (2026-10-17, 2026-10-18) | 021 y 020 (RF-60 a RF-62) |

## Criterios de finalización

Cada RF citado por al menos una prueba (`grep -rnoE "034:RF-[0-9]+" tests | sort -u`) y la
suite en verde. Para RF-34 a RF-41, además, `tests/test_interactive_architecture.py` en rojo sobre 00d30651 sin la
TO-BE ni los ADR, y en verde con ellos.
