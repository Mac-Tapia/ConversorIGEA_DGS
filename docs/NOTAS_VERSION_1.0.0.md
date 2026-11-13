# ConverterSmartGrid 1.0.0 — notas de la versión

Notas para la etiqueta `v1.0.0`. Recogen solo lo integrado en la rama `trabajo/puerta-por-ramas` hasta `ee1151f3`; cada punto lleva
el commit que lo trae. La publicación la ordena el usuario (086 T34): estas notas no la fechan.

## Qué hace

ConverterSmartGrid lleva a DIgSILENT PowerFactory la red de distribución que exporta una distribuidora, y estudia en DIgSILENT lo
que pasa al añadir demanda. Se usa desde una página web local, en el propio equipo, sin salir a internet.

**Lo que se entrega en la 1.0** (alcance de la spec 086):

- Cargar la fuente y convertir a DGS: los tres TXT de CYMDIST, una base Access `.mdb` o un paquete VNR-GIS, una fuente por vez.
- Importar en DIgSILENT con el «Caso base» verificado por el flujo de carga.
- Calibrar («Sin proyecto») con los libros de medición de la empresa.
- Cargas nuevas y «Con proyecto», con la escalera de obras (bancos, sección y terna).
- Informes de estudio y de factibilidad, cada uno con su libro Excel.
- Estudios de flujo, N-1 y transferencia.

**En beta**, marcadas en su pantalla y desactivables con `CSG_BETA_APAGADAS`: asistente de órdenes, SET nueva, diagnóstico y borrador
del PIDE, y confiabilidad (`src/convertersmartgrid/edicion.py`).

**No se entrega activo** en la edición de producto: entrenar modelos, revisión por roles, gemelo digital (PINN, GRU, aprendizaje
continuo), pronóstico por modelos y las preguntas del asistente sobre el código; el servidor niega esas rutas y tareas
(`src/convertersmartgrid/edicion.py`).

**Del programa instalable**, ya en el rc5 (`6306cc65`) y que esta versión mantiene:

- Instalador por usuario de Windows, sin administrador ni internet, con su Python, programa y datos en carpetas separadas,
  actualización con copia previa de los datos y vuelta atrás; diagnóstico (`doctor`), registro rotativo y paquete de soporte
  anonimizado (`9fdb9fab`).
- DIgSILENT PowerFactory de cualquier versión desde la 2021, la más nueva que funcione o la que se elija en la web; el instalador
  trae los Python 3.9, 3.10 y 3.11 que piden las versiones 2021 a 2023 (`b4d34a5c`, `295c6e4b`, `676e7bab`, `c649074b`).
- El perfil de la empresa se carga desde la web y se valida antes de guardar (`88436c41`); el diagnóstico avisa si al perfil le
  faltan las fichas de transformadores o los bancos por tensión (`ad6ff538`).
- Sustituir un fichero de estado reintenta un bloqueo pasajero de Windows (`3f17b3aa`).

## Qué cambió desde el último candidato (rc5, `6306cc65`)

**Instalación y uso del programa instalado**

- Cinco defectos del rc5 corregidos: el instalador deja en su registro y en su aviso el motivo por el que no terminó, también en
  silencio; no reutiliza la carpeta de una instalación anterior que está en la temporal de Windows o que ya no tiene el programa;
  tras «Cargar perfil», la web enseña el sistema de coordenadas del perfil sin recargar; «DIgSILENT» bien escrito; los avisos de
  salida a la red dicen «al» y «del»; y «Recalibrar» vuelve a leer los libros de medición cuando cambian (`f7110865`).
- La copia de los datos guarda cada fichero físico una vez, aunque tenga varios nombres; reintenta ante un destino que se
  bloquea y se hace también desde la web, con «Hacer una copia ahora» (086:RF-78 a RF-86, `ee1151f3`).
- Fondo de mapa con calles y satélite en la vista previa, con un interruptor en «Opciones de conversión» que el equipo recuerda;
  apagado salvo que se encienda, porque sale a internet (`9b33b85a`).
- Cada aviso de un trabajo fallido, cancelado o interrumpido sale en el paso de la web que lo lanzó, con «Ver su registro», «Dar por
  visto» y, si se puede repetir, «Reintentar»; desaparece solo si después el mismo trabajo terminó bien (`073638c9`; pruebas en
  `020261c5` y `3b6fd02f`).
- Sin un espacio recordado en el navegador, la web retoma el último trabajado en vez de crear uno vacío (`499c2383`).

**Estudios y obras**

- «Con proyecto» sin cargas nuevas: «Obras para el estado actual» corrige, también desde la web, los alimentadores que ya violan
  límites (`f3007698`).
- «Cargas nuevas» se copia de nuevo de «Sin proyecto» en cada inserción y se compara con él (`689d7905`).
- La ubicación de una carga nueva se comprueba antes de conectarla, con su propuesta de corrección (`261f90cb`).
- La tensión medida en la cabecera, en la tabla de la máxima y en la fuente en p.u. (`406a276a`).
- Las etiquetas de los ejes de las gráficas tienen el mismo tamaño en pantalla que el título (`4de71002`).

**Datos de demanda**

- Los libros nuevos de demanda se reconocen, se verifican y se avisan solos (`61c1af58`); su revisión corre en un carril de fondo
  que cede al operador (`56feb680`).
- Evolución de los clientes fijos de cualquier alimentador, con tablero, libro Excel, conciliación de fuentes y archivo (`5faf20a2`).
- La tabla cruzada muestra el nombre del cliente del libro de suministros cuando el libro mensual no lo trae (`84ca4561`).

**Internos, sin efecto en lo que se entrega activo**

- Pronóstico y PINN, que la edición de producto no ofrece: `a190e8df`, `483fa4af`, `c74a6154`.
- La suite y los entrenamientos se turnan la GPU de la máquina de desarrollo (`9063b8af`).
- Las pruebas de una rama prueban el código de su propia rama, y el entorno de DIgSILENT no hereda otro paquete del conversor
  (`eedaf7d4`).
- La búsqueda de hiperparámetros se limita por ensayos y no por reloj; un intérprete de órdenes nuevo no se promueve si acierta peor
  que el que está en uso en las órdenes reales del operador (`675c8f68`).
- Un dataset de demanda interrumpido ya no se queda en «regenerando»: se avisa y se retoma. El lector reconoce libros de clientes
  sin títulos por el contenido de sus columnas, avisa de cada libro que no sabe leer y deja confirmar un formato nuevo (`375200ae`).
- Evidencia de la suite completa sin omitidas sobre el rc5 (`ee5befb6`).

## Requisitos

- Windows 10 u 11 de 64 bits y al menos 2 GB libres en el disco de los datos.
- Para importar, calibrar, estudiar e informar: DIgSILENT PowerFactory 2021 o posterior, con su licencia. Sin él se convierte a DGS.
- Opcionales, cada uno para su fuente o función: Microsoft Access Database Engine de 64 bits (base `.mdb`), «ODBC Driver 18 for
  SQL Server» y SQL Server Express si la copia es local (`.bak` de VNR-GIS), y Tesseract con el idioma español (PDF escaneados).
- Nada más: el instalador trae su Python y sus librerías, y no instala nada al arrancar.

Los pasos están en `MANUAL_INSTALACION.md`.

## Limitaciones conocidas

Sacadas de las specs en estado «aprobada» o «implementada» y de sus tareas abiertas en `specs/README.md`.

**Aceptación de la propia 1.0 (spec 086).** Quedan abiertas:

- T32: instalar con el `setup.exe` y llevar una empresa distinta, de punta a punta, hasta un informe que un ingeniero dé por bueno.
- T33: el ensayo de corte de luz a media calibración y a media importación.
- T36: el flujo completo con la red del equipo cortada de verdad.
- T40: instalar, actualizar y volver atrás con el `setup.exe` y una importación real con el Python del programa; el complemento de
  IA construido e instalado con sus modelos.
- T41: una persona ajena instala y convierte siguiendo el manual (guía en `GUIA_PRUEBA_PERSONA_AJENA.md`).
- T9: renombrar la carpeta del proyecto, que es del entorno de desarrollo.
- T34: el repositorio de producto y esta etiqueta, que espera la orden del usuario.

**Aceptación automática por versión (spec 100).** Sustituye a las comprobaciones por proyecto que se cerraron sin corrida propia el
2026-11-08 (entre ellas las de protecciones, 049). No se ha corrido ninguna vez: sus cuatro tareas siguen abiertas.

**Corridas en DIgSILENT pendientes** de funciones ya programadas: calibrar con la tensión medida en la cabecera (021 T25); la
calibración por año con bancos y tramos de dos conductores (025 T27); el asistente de punta a punta con un candidato entrenado
(070 T11).

**Fuera de la 1.0 o en beta, por diseño:**

- Cortocircuito y protecciones no se venden en la 1.0 (fuera de alcance de la 086); su spec (049) se cerró sin corrida propia.
- PIDE y planeamiento de largo plazo: en beta; falta su aceptación real y la base de módulos de transmisión (072 T9b, T11, T13, T14).
- Asistente de órdenes: en beta. Faltan el intérprete con codificador preentrenado (069 T7), la búsqueda multilingüe (097 T3) y la
  revisión por roles (047 T4, T7, T8).
- Pronóstico de demanda: falta la corrida larga real de todos los modelos (089 T7) y la proyección para todos los años del PIDE
  (031 T4, T5); no se ofrece en la edición de producto.
- Libros nuevos de demanda: falta verlo en la web real arrancada por el operador (104 T6).
- Modelos que no se entregan: gemelo físico PINN/GNN (045 T3), aprendizaje continuo (050 T3b, T4b, T5b), puertas de los modelos
  (071 T5), gobierno de modelos (043 T9), agente en producción (027 T11, T26), piloto MADRL (074 T5, T7, T8). La 1.0 no trae pesos
  entrenados.
- Internas, sin efecto para el usuario: arquitectura por capas (002 T7, T8, T9, T11, T12), renombrar la carpeta (058 T6) y el turno de
  GPU de la suite (106 T2).

**Del producto:**

- Solo Perú en la 1.0 (decisión D1): 60 Hz, soles y normas peruanas, salvo lo que diga el perfil de la empresa.
- Un puesto local por licencia, sin servidor multiusuario (D2): la web escucha solo en `127.0.0.1` y se instala por usuario de
  Windows.
- Solo Windows de 64 bits. El instalador no va firmado.
- El programa instalado no trae los manuales aparte: se entregan junto al instalador.
- La pantalla «Acerca de» del programa muestra todavía las notas del 1.0.0rc1 (`src/convertersmartgrid/recursos/NOTAS_VERSION.md`), y
  la versión del paquete en el código es `1.0.0rc1`: el candidato fija la suya al construirse con `--version`. Hay que poner las dos al
  día antes de etiquetar.

## Licencias

- El código de ConverterSmartGrid se publica con licencia MIT (`LICENSE`, `50cb9307`).
- Las librerías de terceros que viajan en el instalador, con su licencia y su texto, están en `THIRD_PARTY_NOTICES.txt`, y su lista
  con huella en `sbom.cdx.json`, los dos en los documentos del candidato.
- El programa **no incluye ni concede** ninguna otra licencia (decisión D7, 2026-11-07). Cada usuario necesita las suyas:
  DIgSILENT PowerFactory, los datos de la distribuidora y de Osinergmin, y los modelos que instale con el complemento de IA.
