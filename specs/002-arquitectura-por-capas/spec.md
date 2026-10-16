# Spec 002 — Arquitectura por capas y módulos enchufables

Estado: aprobada (2026-10-08) · Fecha: 2026-10-08 · Depende de: spec 001 cumplida

## Contexto y objetivo

El conversor va a crecer con módulos nuevos: otras entradas, otras salidas, estudios
(flujo de carga, cortocircuito, pérdidas) y automatización de PowerFactory. Hoy no está
preparado para ello. `igea_dgs` son 40 módulos planos sin fronteras, y `igea_dgs` y
`vnr_etl` se importan en ciclo: `vnr_etl` usa `dataset`, `schema` y `validate`, y
`igea_dgs.web` usa `vnr_etl`. Además, `reglas.py` depende de `powerfactory_env`,
`web/services.py` importa 22 módulos y `web/source_scope.py` usa funciones privadas de
`vnr_etl.pipeline`. Con esta forma, cada módulo nuevo toca a los demás. El objetivo es
la forma de CYME, PowerFactory o ETAP: un núcleo con un único modelo de red, módulos
alrededor que se enchufan por interfaces fijas, y una regla de dependencias que una
herramienta comprueba en cada ejecución de la suite. Todo ello **sin cambiar ningún DGS
que hoy sea correcto**.

La spec 001 va antes: deja cada responsabilidad en un solo sitio, y esta spec las coloca
en su capa.

El conversor es universal: carga TXT, MDB y VNR-GIS de cualquier distribuidora
(constitución P13). Los datos de Electro Dunas son un caso de prueba y de aceptación
antes de producción, no el diseño. Hoy hay tres convenciones suyas fijadas en el motor:
el CRS `EPSG:32718` por defecto (`batch.py`, `geography.py`, `cli.py`, `web/services.py`),
la exclusión de SED `M…` activada por defecto (`reglas.py`) y la escala del diagrama de
NA205 (`dgs.py`). Esta spec las lleva a un perfil de empresa.

## Usuarios / actores

- Desarrollador del proyecto, que añade módulos y mantiene el núcleo.
- Autor de un módulo externo, instalado como paquete aparte.
- Ingeniero de planificación (web) y usuario del CLI: no deben notar el cambio.

## Historias de usuario

- H1: Como desarrollador quiero añadir un lector, un escritor o un estudio sin tocar el
  núcleo, para que cada módulo nuevo no arriesgue los que ya funcionan.
- H2: Como desarrollador quiero que la suite falle si alguien rompe la dirección de las
  dependencias, para que la arquitectura no se degrade con el tiempo.
- H3: Como autor de un módulo quiero instalarlo con `pip install` y que el conversor lo
  descubra, para distribuirlo sin modificar este repositorio.
- H4: Como desarrollador del frontend quiero que un cambio en la API rompa la compilación
  del front, y no la pantalla del usuario en producción.

## Requisitos funcionales (EARS)

Capas (backend)

- RF-1: EL SISTEMA organizará el código Python en un único paquete `igea_dgs` con las
  capas `dominio`, `puertos`, `aplicacion`, `adaptadores` y `presentacion`, en ese orden
  de abajo arriba: los casos de uso de `aplicacion` usan los puertos, y los adaptadores
  los implementan.
- RF-2: SI un módulo importa de una capa superior a la suya, ENTONCES la comprobación de
  capas fallará y dejará la suite en rojo.
- RF-3: SI la capa `dominio` importa FastAPI, Tkinter, `powerfactory`, un driver de base
  de datos o cualquier módulo de `adaptadores` o `presentacion`, ENTONCES la comprobación
  de capas fallará.
- RF-4: SI dos módulos de `igea_dgs` se importan en ciclo, directa o indirectamente,
  ENTONCES la comprobación de capas fallará.
- RF-5: SI un módulo de `igea_dgs` importa un nombre privado (con prefijo `_`) de otro
  módulo, ENTONCES la comprobación de capas fallará. Las pruebas de `tests/` quedan
  fuera: pueden probar funciones privadas.
- RF-6: EL SISTEMA integrará `vnr_etl` dentro de `igea_dgs` como adaptador de entrada
  VNR-GIS y su descubrimiento de publicaciones, sin un paquete de nivel superior aparte.

Puertos y módulos

- RF-7: EL SISTEMA definirá en `puertos` las interfaces `LectorDeRed`, `EscritorDeRed`,
  `Estudio` y `SesionPowerFactory`.
- RF-8: CUANDO un paquete instalado declara un módulo en el grupo de entry points
  `igea_dgs.modulos`, EL SISTEMA lo descubrirá sin cambiar el código del núcleo.
- RF-9: EL SISTEMA registrará sus propios lectores (TXT, MDB, VNR-GIS) y su escritor DGS
  por la misma vía de entry points que un módulo externo.
- RF-10: EL SISTEMA cargará los módulos ordenados por su nombre declarado, de modo que el
  resultado no dependa del orden de instalación.
- RF-11: SI un módulo no cumple la interfaz de su puerto o falla al importarse, ENTONCES
  EL SISTEMA lo excluirá, lo nombrará en el diagnóstico y seguirá con los demás.
- RF-12: SI dos módulos declaran el mismo nombre, ENTONCES EL SISTEMA rechazará los dos
  con un error que nombre ambos paquetes.
- RF-13: CUANDO un `EscritorDeRed` genera una salida, EL SISTEMA le entregará el modelo
  ya pasado por `preparar_dataset`, `aplicar_reglas` y `auditar_completitud`.
- RF-14: MIENTRAS un `Estudio` o una `SesionPowerFactory` usan PowerFactory, EL SISTEMA
  los ejecutará en el carril único en serie de PowerFactory.
- RF-15: EL SISTEMA no instalará ni cargará módulos subidos desde la web: solo los
  instalados en el entorno de Python del servidor.
- RF-23: SI un módulo externo instalado no figura en la lista de módulos permitidos,
  ENTONCES EL SISTEMA no lo importará y lo nombrará en el diagnóstico.
- RF-24: EL SISTEMA no ofrecerá ninguna vía web para modificar la lista de módulos
  permitidos.
- RF-25: SI la versión mayor del puerto que declara un módulo es distinta de la del
  núcleo, ENTONCES EL SISTEMA lo excluirá y nombrará las dos versiones en el diagnóstico.
- RF-26: SI una dependencia de un módulo externo no está instalada, ENTONCES EL SISTEMA
  excluirá ese módulo y arrancará igual.
- RF-27: EL SISTEMA tratará como internos los módulos que declara la distribución
  `igea-dgs`, que no necesitan figurar en la lista de módulos permitidos; cualquier otro
  es externo.
- RF-28: SI los entry points instalados no coinciden con los que declara
  `pyproject.toml`, ENTONCES la suite fallará con un mensaje que pida reinstalar con
  `pip install -e .`.
- RF-29: CUANDO se convierte con `workers>1`, EL SISTEMA resolverá los módulos y la lista
  de permitidos en el proceso principal y pasará ese resultado a cada proceso hijo.
- RF-30: CUANDO se lanza un `Estudio`, EL SISTEMA lo ejecutará como un trabajo en cola,
  con progreso por WebSocket y cancelable, use o no PowerFactory.

Universalidad (constitución P13)

- RF-31: EL SISTEMA reunirá en un perfil de empresa las convenciones propias de una
  distribuidora: CRS de origen, patrón de las SED de medición, forma de los nombres de
  alimentador y escala del diagrama.
- RF-32: SI ni la entrada ni el perfil de empresa declaran el CRS de origen, ENTONCES EL
  SISTEMA pedirá elegirlo antes de convertir, en vez de suponer uno.
- RF-33: DONDE el perfil de empresa no define un patrón de SED de medición, EL SISTEMA no
  excluirá ninguna SED por su nombre.
- RF-34: SI un módulo de `dominio`, `puertos` o `aplicacion` contiene, fuera de
  comentarios, un código de alimentador, un CRS o un prefijo de nombre de una empresa
  concreta, ENTONCES la comprobación de universalidad fallará.
- RF-35: EL SISTEMA incluirá el perfil de Electro Dunas como un perfil más, y con él
  reproducirá los DGS de la línea base (RF-20).
- RF-36: CUANDO se ejecuta la suite, las pruebas sintéticas convertirán la misma red con
  al menos dos perfiles de empresa distintos.
- RF-37: CUANDO se convierte, EL SISTEMA registrará en el manifiesto del lote el perfil de
  empresa usado y sus valores.

Contrato API ↔ frontend

- RF-16: EL SISTEMA generará los tipos TypeScript del frontend a partir del esquema
  OpenAPI que publica la API.
- RF-17: SI los tipos generados no coinciden con el esquema OpenAPI actual, ENTONCES la
  comprobación de contrato fallará.

Frontend

- RF-18: EL SISTEMA organizará `frontend/src` en `api/` (cliente y tipos generados),
  `shared/`, `features/<funcionalidad>/` y `app/`.
- RF-19: SI una carpeta de `features/` importa de otra carpeta de `features/`, ENTONCES
  el lint del frontend fallará.

Compatibilidad

- RF-20: EL SISTEMA producirá, para la misma entrada, perfil y alias, los mismos DGS byte
  a byte que antes de esta spec.
- RF-21: EL SISTEMA no conservará, al cumplirse esta spec, reexportaciones desde las
  rutas de importación antiguas (`igea_dgs.batch`, `vnr_etl.*`…); `tools/` y las pruebas
  usarán las nuevas.
- RF-22: EL SISTEMA mantendrá los comandos `igea-dgs`, `igea-dgs-web` y `vnr-etl` con
  los mismos argumentos (`vnr-etl-web` lo retira la spec 001).

## Requisitos no funcionales

- Determinismo: DGS idéntico con `workers=1` y con `workers>1`, antes y después (P1).
- Escala: ningún paso introduce recorridos completos de tablas por alimentador (P2).
- Cada fase deja la suite en verde y se puede publicar sola.
- La comprobación de capas tarda menos de 10 s, para que se ejecute en cada `pytest -q`.

## Casos límite

- Módulo externo con el mismo nombre que uno interno (RF-12).
- Módulo instalado y no permitido (RF-23); módulo permitido pero no instalado.
- Módulo con versión de puerto 2.x frente a un núcleo 1.x, y 1.3 frente a 1.1 (RF-25).
- Módulo externo cuya dependencia no se pudo instalar (RF-26).
- Módulo externo que importa bien pero no implementa un método del puerto (RF-11).
- Módulo instalado cuyo paquete se desinstaló a medias: entry point que no importa (RF-11).
- Estudio lanzado mientras otro trabajo usa PowerFactory (RF-14).
- Disposición de export reducida y completa al mover los lectores (RF-9, RF-20).
- Herramientas de `tools/` que importan rutas antiguas (RF-21).
- Ejecución en paralelo con `workers>1`: los procesos hijos usan los mismos módulos, en
  el mismo orden y con la misma lista de permitidos, que el principal (RF-10, RF-29).
- Código actualizado con `git pull` sin reinstalar: entry points desfasados (RF-28).
- Estudio largo que no usa PowerFactory, cancelado a mitad (RF-30).
- Empresa nueva sin perfil: entrada sin CRS (RF-32) y SED cuyo nombre empieza por `M`
  que son subestaciones reales (RF-33).
- Entrada de una empresa en el hemisferio norte o en otra zona UTM (RF-32).

## Fuera de alcance

- Recuperar de la rama `feat/integracion-web-retiro-gui` la red unida en paralelo
  (`cd411caa`), el inventario de cargas (`6716f73b`, `2ae18fe0`, `d1cea923`), el mapa
  nombre→alimentador (`1ee0b022`), las herramientas de aceptación con PowerFactory real
  (`a67cdd99`, `19eb14b0`, `d8015dde`, `c45f3007`, `f5bc2fd4`) y las pruebas e2e con
  Playwright (`0e16321c`): van en la spec 003, ya sobre las capas. El resto de esa rama
  ya está aquí o lo reemplaza una implementación posterior (revisión del 2026-10-08).
- Módulos nuevos (cortocircuito, OpenDSS…): esta spec crea los puertos, no los módulos.
- Lint y tipado generales (`ruff`, `pyright`, ESLint completo, CI): van en otra spec.
  Aquí solo entran la comprobación de capas y la regla de fronteras del frontend.
- Cambios en el formato DGS o en el perfil de esquema.
- Versionado del puerto para módulos de terceros más allá de lo que pida RF-11.

## Criterios de finalización

- Cada RF lo cita al menos una prueba: `grep -rnoE "002:RF-[0-9]+" tests frontend | sort -u`
  lista RF-1 a RF-37.
- Suite en verde con las tres variables `IGEA_*`, y la comprobación de capas incluida en
  `pytest -q`.
- RF-20 comprobado contra la línea base de DGS de la spec 001 (T1).
- `npx tsc --noEmit -p frontend`, `npm run build` y el lint del frontend correctos.

## Dudas resueltas (2026-10-08)

- P8: se cambió la constitución. Un módulo externo declara sus dependencias en su propio
  paquete, y ninguna puede ser necesaria para el núcleo (RF-26).
- P9: se cambió la constitución. Hace falta una lista de módulos permitidos, que no se
  edita desde la web (RF-23, RF-24).
- Versión del puerto: una versión mayor distinta excluye el módulo (RF-25). Una versión
  menor distinta se acepta, porque una versión menor solo añade y no rompe.
