# Spec 059 — La fuente es la del fichero que se carga, sin valor por defecto

Estado: cumplida (2026-11-01) · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01,
al abrir la web tras la spec 058 y verla «como TXT» con el espacio de Electro Oriente (VNR-GIS):
«no debe haber por defecto; debe ser claro y definido cada archivo según qué corresponde; si el
conversor es inteligente no debe volver a pasar»; «el conversor tiene tres tipos de archivos y
cada uno debe ser el correcto; nada debe ser por defecto, debe ser según el archivo que se carga».

## Contexto y objetivo

El espacio nuevo nacía con `input_mode = 'txt'` (`DEFAULT_OPTIONS`). El 2026-11-01 la spec 058
cambió la clave con la que el navegador recuerda su espacio; la web no encontró el de Electro
Oriente (`aee74107…`, VNR-GIS), creó uno vacío y lo mostró como «Tres TXT de CYMDIST», como si la
fuente fuera esa. Dos fallos: perder el espacio (058:RF-6) y suponer una fuente que nadie cargó.

El conversor tiene tres fuentes: los TXT de CYMDIST, la base Access (.mdb) y el paquete VNR-GIS.
La fuente la dice el fichero que se carga, reconocido por su contenido; sin nada cargado no hay
fuente; y el navegador vuelve al espacio con el que trabajaba.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se crea un espacio de trabajo, EL SISTEMA lo dejará sin fuente (`input_mode`
  nulo), y su lista de pendientes pedirá la fuente sin suponer una.
- RF-2: CUANDO se abre un espacio guardado, EL SISTEMA tomará como fuente la del único grupo
  (TXT, MDB o VNR-GIS) que tenga entradas; sin entradas, el espacio queda sin fuente.
- RF-3: CUANDO se carga un fichero en una de las tres entradas (TXT de CYMDIST, base Access o
  VNR-GIS), EL SISTEMA comprobará por su contenido que sea de esa entrada —TXT por sus tablas,
  Access por su cabecera, VNR-GIS por su formato— y la fuente del espacio pasará a ser esa.
- Aclaración de RF-3 (2026-11-13, auditoría c7): la comprobación se hace sobre lo subido en su staging, antes de tocar
  la entrada vigente; un fichero rechazado con el mismo nombre que el asignado (una base Access en la casilla de un TXT,
  un paquete VNR-GIS cortado) no lo pisa ni lo borra (086:RF-3).
- RF-4: SI en una entrada se carga un fichero de otra fuente, ENTONCES EL SISTEMA no lo asignará y
  dirá qué es y en qué entrada va: cada fichero en la suya, nada se mezcla.
- RF-5: MIENTRAS el espacio no tenga fuente, la web mostrará las tres entradas separadas, como
  siempre, sin ninguna marcada.
- RF-6: CUANDO el navegador guarda el espacio con la clave anterior al cambio de nombre, la web lo
  reabrirá, pasará el id a la clave nueva y borrará la anterior.
- RF-7: SI se pide una conversión sin fuente, ENTONCES EL SISTEMA responderá con un mensaje que
  pide cargarla, no con un error de modo desconocido.
- RF-8: CUANDO se asigna en la entrada VNR-GIS una copia de SQL Server (`.bak`, con o sin
  extensión), EL SISTEMA leerá su empresa y su base de `ConfigBD.config`, si lo hay, sin tratarla
  como un paquete de capas, y no dará error por ello.

## Fuera de alcance

- Subir por el navegador una copia `.bak` de varios GB: el paquete VNR-GIS sigue pudiéndose
  indicar por ruta del equipo (spec 023).
- Mezclar fuentes en un espacio: sigue prohibido («una fuente por vez»).

## Relación con otras specs

- Completa 058:RF-6 (los espacios guardados siguen funcionando tras el cambio de nombre).
- Amplía a MDB y VNR-GIS la identificación por contenido de los TXT (`identify.py`).

## Criterios de finalización

- `grep -rnoE "059:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-8.
- La web abierta desde el acceso directo muestra el espacio de Electro Oriente como VNR-GIS, y
  un espacio nuevo, sin ninguna alternativa marcada.
