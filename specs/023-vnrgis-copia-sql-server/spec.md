# Spec 023 — VNR-GIS desde la copia de SQL Server de cualquier concesionaria

Estado: cumplida (revisión 033 del 2026-10-29) · aprobada (2026-10-18) · Fecha: 2026-10-18

## Contexto y objetivo

VNR-GIS es el sistema del regulador con el que todas las concesionarias entregan su red: el
mismo modelo de datos para todas. La entrega real no es un paquete de capas, que es lo que lee
la vía VNR-GIS de hoy (spec 001, RF-4), sino una copia de seguridad de SQL Server (`.bak`) con
su base de parámetros y un `ConfigBD.config` que dice la empresa y los nombres de las bases. La
de Electro Dunas (`ELDU_VNR_24_APR.bak`, 819 MB) es el caso de prueba, no el diseño: el usuario,
el 2026-10-18, «este conversor debe ser funcional para cualquier empresa concesionaria». Una
`.bak` no se puede leer sin restaurarla en un motor de SQL Server (la vía estándar y gratuita:
`RESTORE DATABASE … WITH MOVE` y lectura por ODBC); los convertidores que la abren sin motor son
de pago o suben los datos a terceros, y quedan descartados.

## Usuarios / actores

Ingeniero de planificación desde la web o el CLI; el motor de SQL Server local de la máquina.

## Historias de usuario

- H1: Como ingeniero quiero dar la copia `.bak` de VNR-GIS de mi empresa y convertir un
  alimentador a DGS, igual que con un TXT o una `.mdb`, sin exportar nada a mano.
- H2: Como ingeniero de otra concesionaria quiero que funcione con mi copia sin cambiar código.

## Requisitos funcionales (EARS)

Entrada

- RF-1: EL SISTEMA aceptará como fuente VNR-GIS la copia `.bak` de SQL Server de la base de
  VNR-GIS de cualquier concesionaria, en la web y en el CLI, sola o con su base de parámetros.
- RF-2: DONDE junto a la `.bak` haya un `ConfigBD.config`, EL SISTEMA tomará de él el código
  de empresa y los nombres de las bases; si no, los tomará de la cabecera de la copia y del
  contenido de la base, nunca de un valor fijo de una empresa.

Restauración

- RF-3: CUANDO se carga una `.bak`, EL SISTEMA la restaurará en el motor de SQL Server local
  configurado (por omisión la instancia `SQLEXPRESS`), con un nombre propio que lleve la
  huella del fichero y sus ficheros de datos en una carpeta del conversor (`WITH MOVE`).
- RF-4: SI ya hay restaurada una base con la misma huella, ENTONCES EL SISTEMA la reutilizará
  sin volver a restaurar.
- RF-5: SI no hay motor de SQL Server disponible, ENTONCES EL SISTEMA lo dirá con lo que hay
  que instalar, sin intentar leer la `.bak`.
- RF-6: EL SISTEMA solo leerá la base restaurada: no escribirá en ella ni en otras bases del
  motor.

Lectura

- RF-7: EL SISTEMA descubrirá las tablas de tramos, SED, cargas, maniobras y geometría por sus
  campos (los alias de VNR-GIS, como `CODTRAMOMT` y `CODSALIDAMT`), no por el nombre de tabla.
- RF-8: DONDE una tabla traiga geometría de SQL Server, EL SISTEMA la leerá como coordenadas
  con el CRS que diga la base o el perfil de la empresa; sin ninguno de los dos, lo pedirá.
- RF-9: EL SISTEMA convertirá un alimentador de la copia por la misma vía canónica que un
  paquete VNR-GIS, y el DGS pasará la validación, el inventario y la puerta de aceptación.
- RF-10: SI falta en la base algo que el modelo necesita, ENTONCES EL SISTEMA lo
  reconstruirá con el catálogo y lo anotará, o lo dirá, sin bloquear salvo la red vacía.

## Requisitos no funcionales

- Universal: ningún código, tabla, empresa o CRS fijo; lo propio de cada empresa en su perfil.
- Datos: la copia y la base restaurada no salen de la máquina ni se suben a un tercero.
- Escala: la copia trae todos los alimentadores de la empresa; leer uno no recorre la base
  entera por cada alimentador.

## Casos límite

Copia de una versión de SQL Server más nueva que el motor (no restaura: se dice); copia sin
`ConfigBD.config`; base de parámetros ausente; dos empresas en una misma base; alimentador sin
tramos; geometría vacía.

## Fuera de alcance

Instalar SQL Server desde el conversor; motores remotos con usuario y contraseña; escribir en
la base de VNR-GIS.

## Criterios de finalización

Cada RF citado por una prueba (`grep "023:RF-"`); las sintéticas sin SQL Server con un doble del
motor; la copia de Electro Dunas restaurada y un alimentador convertido e importado en
DIgSILENT; suite completa sin omitidas.

## Dudas abiertas

- [NECESITA ACLARACIÓN] Qué tablas y columnas trae la base restaurada: se exploran al
  restaurar la copia de Electro Dunas, antes del plan.
