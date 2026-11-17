# ConverterSmartGrid 1.0.0 — notas de la versión

Notas para la etiqueta `v1.0.0`. Recogen lo integrado en la rama `trabajo/puerta-por-ramas` hasta la revisión que lleva el
manifiesto del candidato final; cada punto lleva el commit que lo trae. La publicación la ordena el usuario (086 T34): estas notas no la fechan.

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
- Entrenar los modelos, el gemelo digital (PINN y GRU), el pronóstico por modelos, las mejoras y el aprendizaje continuo (050), la
  revisión por roles y las preguntas del asistente sobre el código. Lo que entrena o usa el gemelo pide una GPU NVIDIA con CUDA y el
  complemento de IA; sin ella, el trabajo lo dice y no cae a la CPU. Ningún modelo pasa a uso sin sus puertas (071). La 1.0 no trae
  pesos entrenados: se generan en el equipo del cliente, con sus datos. El reentreno automático va solo, salvo que el operador lo
  pare (`CSG_AUTOENTRENAMIENTO=0`); las mejoras del código solo funcionan en el entorno de desarrollo.
- Estudios regulatorios con la forma que pide Osinergmin, con sus formatos oficiales: el Plan
  de Inversiones en Transmisión (PIT), el Valor Agregado de Distribución (VAD) y el Valor Nuevo de Reemplazo (VNR) según la
  Guía del VNR (RCD 232-2017-OS/CD), con el SICODI de la última fijación. Las normas vigentes salen de un registro normativo
  común, con la cláusula de vigencia de cada una.
- Fuentes y expedientes en la nube (Google Drive y OneDrive) y envío de informes por correo (Gmail y Outlook), desde la web.
- El editor eléctrico sobre el plano GIS, con los resultados en el mismo trazo.

**En beta**, marcadas en su pantalla y desactivables con `CSG_BETA_APAGADAS`: asistente de órdenes, SET nueva, diagnóstico y borrador
del PIDE, y confiabilidad (`src/convertersmartgrid/edicion.py`).

Nada está apagado en la edición de producto (usuario, 2026-11-13). La edición solo decide lo que es de seguridad: las salidas a
la red están apagadas hasta que el operador las encienda, y los datos del cliente se quedan en su equipo.

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

- Pronóstico y PINN, activos también en la edición de producto: `a190e8df`, `483fa4af`, `c74a6154`.
- La suite y los entrenamientos se turnan la GPU de la máquina de desarrollo (`9063b8af`).
- Las pruebas de una rama prueban el código de su propia rama, y el entorno de DIgSILENT no hereda otro paquete del conversor
  (`eedaf7d4`).
- La búsqueda de hiperparámetros se limita por ensayos y no por reloj; un intérprete de órdenes nuevo no se promueve si acierta peor
  que el que está en uso en las órdenes reales del operador (`675c8f68`).
- Un dataset de demanda interrumpido ya no se queda en «regenerando»: se avisa y se retoma. El lector reconoce libros de clientes
  sin títulos por el contenido de sus columnas, avisa de cada libro que no sabe leer y deja confirmar un formato nuevo (`375200ae`).
- Evidencia de la suite completa sin omitidas sobre el rc5 (`ee5befb6`).

**Estudios regulatorios (Osinergmin)** — BORRADOR (f7, 2026-11-17). Los huecos `<HASH-…>` se cambian por el commit de cada lote
al integrarlo.

- PIT: el diagnóstico de la red del área de demanda y el expediente con los formatos de la norma, sobre el registro normativo
  (`e182c823`, `24b4a19d`, `60044e5b`); la demanda de la cadena, el resumen por barra, la generación medida y deducida, los
  usuarios libres y los mapas de densidad de los formatos F-101 a F-124 (`016498fc`); y la pestaña «Estudio PIT» en la web, que
  sube el libro de la red en los cuatro formatos de Excel, lanza el diagnóstico y el expediente y registra las observaciones
  (`<HASH-L2>`).
- VAD: resultados, PIDE, calidad, costos, tablas e informes sobre el registro normativo (`24b4a19d`), la línea VAD con el
  diagnóstico del PIT (`8985d25f`) y el informe definitivo (`016498fc`).
- VNR según la Guía del VNR, desde el inventario VNR-GIS y desde la web: zonificación, adaptación por sector típico, códigos del
  Anexo 2, formatos del Anexo 5 y altas y bajas (`5cc6908d`).
- El diagnóstico del `.pfd` de DIgSILENT, con cada borrado demostrado en DIgSILENT (`948eddc9`), y los vínculos de cada elemento
  del `.pfd` con la red convertida (`016498fc`).

**Nube, correo y web**

- Cuentas en la nube, correo con sus borradores y un solo selector por entrada para elegir del equipo o de la nube (`60044e5b`,
  `8985d25f`).
- La web se maneja entera con el teclado, con su diseño accesible; el mapa y la vista previa se enmarcan con un solo mecanismo
  (`16125499`).
- Los avisos, los errores y los textos de la web dicen qué pasó y qué hacer, sin citar requisitos internos (`2962d35a`).
- La búsqueda en VNR-GIS va en su propio carril y no ocupa el del motor (`016498fc`).
- El asistente hace la nube, el correo, el PIT, el VAD, el plano y el benchmark por las mismas rutas que la web, y para
  enviar, publicar, compartir, importar o conectar espera el clic del operador (`e2a99c73`).

**Estudios y obras**

- 4.2 estudia cualquier caso de cualquier proyecto de DIgSILENT, con o sin calibración, sin dejar rastro en los casos del
  operador, y cada corrida deja su resumen ejecutivo (`bf0755df`); se calibra y se estudia cualquier proyecto, convertido o no por
  el conversor (`8164a81f`).
- Tras conectar una carga, la web dice qué ocasionó y si las obras lo corrigen; ningún informe se escribe sin comprobarlo en
  DIgSILENT (`38dc1581`).
- La solicitud de factibilidad se rellena con la carga sola, y la web no ofrece proyectos borrados de DIgSILENT (`3a02ea17`).
- El PIDE costea con la escala y la moneda del perfil y no mezcla soles con dólares (`9cb32b3a`); en la web pide el tipo de cambio
  de los precios de pérdidas (`0ce72a4c`).
- La proyección anual del PIDE parte, en su año base, del ganador de pronóstico que publica el ciclo común, y la evaluación
  dice cuál; sin ganador publicado, parte de lo medido y también lo dice (`<HASH-L2>`).
- El asistente distingue corto plazo, PIDE y largo plazo por la orden (`e405e9c9`) y nombra los alimentadores por su código,
  como la web (`51895566`).

**Instalación y datos**

- La 1.0 instalada lleva sus manuales y notas, una sola versión y una vuelta atrás que cambia documentos y punteros juntos
  (`bd4cc7d2`); todo queda activo en la edición de producto (`ccb81aa8`).
- Una subida rechazada ya no borra la entrada buena, y borrar un espacio no choca con un trabajo que se encola (`24d99d15`).
- Un corte no deja ficheros de estado a medias, DIgSILENT no tiene dos dueños y la GPU no queda tomada para siempre
  (`d958bb7e`).
- Los libros nuevos de demanda guardan su estado y sus avisos de una vez, aunque Windows niegue un instante el reemplazo
  (`40f8ad25`, `ccceb4c8`).
- El controlador de NVIDIA ya no tumba el programa al iniciar CUDA, y el diagnóstico aconseja actualizarlo (`cfc66465`).
- La conversión de los modelos de la red se hace sin recorrer las tablas una vez por cada salida (`a9918f93`).
- La entrega se construye con su Python oficial firmado, `pip-audit`, firma y `SHA256SUMS`, y el instalador muestra la licencia
  MIT y el acuerdo comercial opcional (`3ce72ece`, `24b4a19d`).

**Internos, sin efecto en lo que se entrega activo**

- Arquitectura por capas: los casos de uso piden sus adaptadores por puerto declarado en `pyproject.toml`, y la deuda de capas
  queda vacía (`<HASH-L2>`).
- La aceptación automática por versión (spec 100) tiene su matriz, su recorrido y su veredicto (`016498fc`).
- La arquitectura C4 rehecha, su TO-BE y 9 ADR (`00d30651`, `79d1da10`); la puerta de calidad exige el intérprete MCP y el lint de
  fronteras del frontend (`2962d35a`).

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
- Pronóstico de demanda: falta la corrida larga real de todos los modelos (089 T7) y la corrida real de la proyección de un
  sistema con sus métricas por modelo (031 T5); se ofrece en las dos ediciones.
- Libros nuevos de demanda: falta verlo en la web real arrancada por el operador (104 T6).
- Modelos que se entregan activos con tareas abiertas: gemelo físico PINN/GNN (045 T3), aprendizaje continuo (050 T3b, T4b, T5b), puertas de los modelos
  (071 T5), gobierno de modelos (043 T9), agente en producción (027 T11, T26), piloto MADRL (074 T5, T7, T8). La 1.0 no trae pesos
  entrenados.
- Internas, sin efecto para el usuario: arquitectura por capas (002 T7, T9, T12), renombrar la carpeta del entorno de desarrollo
  (058 T6, con su herramienta `tools/mudar_carpeta_principal.py` y a falta de la mudanza real) y el turno de GPU de la suite (106 T2).

**Del producto:**

- Solo Perú en la 1.0 (decisión D1): 60 Hz, soles y normas peruanas, salvo lo que diga el perfil de la empresa.
- Un puesto local por licencia, sin servidor multiusuario (D2): la web escucha solo en `127.0.0.1` y se instala por usuario de
  Windows.
- Solo Windows de 64 bits: Windows 11 probado; Windows 10, sin probar. El instalador y su desinstalador van firmados con el
  certificado del editor (OV o firma en la nube); un candidato sin firmar es de prueba y no se entrega.
- El programa instalado trae sus manuales en `documentos`, y el menú de inicio abre el de instalación (086:RF-89, RF-90).
- La pantalla «Acerca de» muestra las notas de la versión instalada, que salen de `__version__` del paquete (086:RF-92, RF-93).
- Se entrega directamente, por correo o enlace privado: instalador, complemento, notas, licencias y `SHA256SUMS`, que va por otro
  canal. Las actualizaciones 1.0.x llegan por el mismo canal, y cada versión tiene 12 meses de soporte.

## Licencias

- El programa se distribuye bajo la licencia MIT (`LICENSE.txt`). El instalador la muestra y pide aceptarla.
- El acuerdo comercial de soporte y garantía (`LICENCIA_COMERCIAL.txt`) es **opcional**: no es condición de la entrega ni del uso.
- El código fuente del repositorio sigue con licencia MIT (`LICENSE`, `50cb9307`); esa licencia no va en la entrega.
- Las librerías de terceros que viajan en el instalador, con su licencia y su texto, están en `THIRD_PARTY_NOTICES.txt`, y su lista
  con huella en `sbom.cdx.json`, los dos en los documentos del candidato.
- El programa **no incluye ni concede** ninguna otra licencia (decisión D7, 2026-11-07). Cada usuario necesita las suyas:
  DIgSILENT PowerFactory, los datos de la distribuidora y de Osinergmin, y los modelos que instale con el complemento de IA.
