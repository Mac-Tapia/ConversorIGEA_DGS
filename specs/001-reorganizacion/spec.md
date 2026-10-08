# Spec 001 — Reorganización: una responsabilidad, un sitio

Estado: borrador · Fecha: 2026-10-07 · Origen: `docs/DIAGNOSTICO_SDD_2026-10-07.md`

## Contexto y objetivo

El diagnóstico del 2026-10-07 encontró responsabilidades implementadas varias veces y
que ya divergen. La lectura de la entrada está en tres sitios (web, CLI, GUI), y por eso
el CLI no admite VNR-GIS ni pasa los alias al catálogo. Hay dos escritores de DGS (el
motor y `vnr_etl`), y el segundo se salta las reglas y la validación. Hay dos API web
con dos colas de trabajos. Y hay utilidades copiadas en hasta 7 sitios. Cada copia es un
sitio más donde corregir un fallo, y uno más donde olvidarse de hacerlo. El objetivo es
que cada responsabilidad viva en un solo sitio **sin cambiar ningún DGS que hoy sea
correcto**.

## Usuarios / actores

- Ingeniero de planificación que convierte desde la web.
- Quien convierte en lote con el CLI `igea-dgs`.
- Quien usa el módulo VNR-GIS (`vnr-etl`).
- Desarrollador del proyecto, que mantiene el código.

## Historias de usuario

- H1: Como usuario del CLI quiero cargar las mismas fuentes que la web (TXT, MDB y VNR-GIS)
  para no depender de la interfaz.
- H2: Como ingeniero quiero que diagnosticar y reconstruir muestren su avance y se puedan
  cancelar, para no esperar a ciegas con muchos alimentadores.
- H3: Como desarrollador quiero corregir cada cosa en un solo sitio, para que las vías no
  vuelvan a divergir.

## Requisitos funcionales (EARS)

Entrada

- RF-1: EL SISTEMA leerá la entrada (TXT, MDB y VNR-GIS) con un único conjunto de
  adaptadores, compartido por la web y el CLI.
- RF-16: EL SISTEMA ofrecerá la conversión solo por la web y el CLI: la GUI Tkinter, su
  orden `igea-dgs gui`, su script `igea-dgs-gui` y sus lanzadores `.bat` se retiran.
- RF-2: CUANDO el CLI recibe un paquete VNR-GIS, EL SISTEMA lo cargará con el mismo
  adaptador y el mismo resultado que la web.
- RF-3: CUANDO se completa o diagnostica el catálogo de conductores, EL SISTEMA aplicará
  los alias del usuario en todas las vías de entrada.

Utilidades

- RF-4: EL SISTEMA calculará el SHA-256 de un fichero con una única implementación.
- RF-5: EL SISTEMA escribirá los JSON de forma atómica con una única implementación.
- RF-6: EL SISTEMA reproyectará coordenadas con una única forma de construir el transformador.
- RF-7: SI el CRS de origen no se puede construir al crear una plantilla de cargas,
  ENTONCES EL SISTEMA rechazará la operación con un error que nombre ese CRS.

Trabajos

- RF-8: CUANDO se pide diagnosticar o reconstruir, EL SISTEMA lo ejecutará como un trabajo
  del carril `engine`, con progreso por WebSocket.
- RF-9: SI se cancela una reconstrucción, ENTONCES EL SISTEMA conservará como activo el
  dataset anterior a la reconstrucción.

VNR-GIS

- RF-10: CUANDO `vnr-etl` exporta a DGS, EL SISTEMA generará el DGS con el motor
  `igea_dgs` (reglas, validación y publicación atómica).
- RF-11: EL SISTEMA ofrecerá una única API web y una única cola de trabajos; el script
  `vnr-etl-web` se retira.

Front

- RF-12: SI una descarga falla con un error de validación (422), ENTONCES la interfaz
  mostrará los mensajes del servidor igual que en el resto de peticiones.
- RF-13: El cliente de la API no contendrá métodos que ninguna pantalla use.

Seguridad

- RF-15: SI la API escucha fuera de `127.0.0.1`, ENTONCES EL SISTEMA rechazará las rutas
  del disco del servidor como entrada, cualquiera que sea el lanzador y aunque la
  variable `IGEA_WEB_SERVER_PATHS` exista.

Salida

- RF-14: EL SISTEMA producirá, para la misma entrada, perfil y alias, los mismos DGS byte a
  byte que antes de la reorganización. La única excepción es la salida de `vnr-etl export`
  (RF-10).

## Requisitos no funcionales

- Determinismo: DGS idéntico con `workers=1` y con `workers>1`, antes y después.
- Escala: ninguna fase introduce recorridos completos de tablas por alimentador.
- Ninguna fase deja la suite en rojo; cada una se puede publicar sola.

## Casos límite

- Disposición de export reducida y completa (RF-1, RF-14).
- Estudio `.xml` con TXT, que filtra la selección pero no la lectura (RF-1).
- Cancelación con alimentadores en marcha durante la reconstrucción (RF-9).
- Paquete VNR-GIS con varias empresas o periodos, que exige elegir (RF-2).

## Fuera de alcance

- Cambios en el formato DGS o en el perfil de esquema.
- Lint y tipado (`ruff`, `pyright`): van en otra spec.
- Optimizar el rendimiento.

## Criterios de finalización

- Cada RF lo cita al menos una prueba: `grep -rnoE "001:RF-[0-9]+" tests | sort -u` lista
  RF-1 a RF-16.
- Suite en verde con las tres variables `IGEA_*`.
- RF-14 comprobado: DGS de referencia regenerados e idénticos a los anteriores.
- `npx tsc --noEmit -p frontend` y `npm run build` correctos.

## Dudas resueltas (2026-10-08)

- RF-10 y RF-11: nadie fuera del repositorio usa `vnr-etl export` ni `vnr-etl-web`, así
  que se unen al motor y a la API principal sin periodo de convivencia.
- La GUI Tkinter se retira (RF-16): la web cubre su uso, y mantenerla era una tercera vía
  de lectura que adaptar en RF-1. La rama `feat/integracion-web-retiro-gui` (commit
  `52974c8e`) ya lo hizo, sin integrar; se toma como referencia.
