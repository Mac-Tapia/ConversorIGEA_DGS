# Diseño de conversión web unificada con aislamiento de fuente

**Fecha:** 2026-10-05
**Estado:** aprobado por el usuario el 2026-10-05
**Alcance:** interfaz web, carga e inventario, conversión DGS y aceptación en
DIgSILENT PowerFactory para MDB, tres TXT y VNR-GIS.

## 1. Objetivo

La aplicación debe ofrecer tres alternativas equivalentes de entrada:

1. base CYMDIST/Access (`MDB`);
2. exportación IGEA/CYMDIST formada por `RED`, `CARGA` y `BD_Equipo` (`TXT`);
3. paquete completo de base de datos geográfica `VNR-GIS`.

Cada alternativa debe inventariar todos sus alimentadores, permitir convertir uno,
varios o todos y conducir los resultados por el mismo proceso de validación,
generación DGS, importación en PowerFactory, relectura y `ComLdf`.

## 2. Invariante principal: una ejecución, una procedencia

Una ejecución activa pertenece exactamente a uno de estos modos: `mdb`, `txt` o
`vnr`. Los archivos de modos distintos nunca se combinan para completar una
conversión.

- `txt` consume exclusivamente la instantánea de `red`, `loads`, `equipment` y,
  si existe, `equipment_extra`.
- `mdb` consume exclusivamente la instantánea de `mdb` y, si existen,
  `equipment_mdb` y `study`.
- `vnr` consume exclusivamente la instantánea del paquete `vnr_package` y sus
  archivos contenidos. No puede tomar nodos, cargas o fuentes de MDB/TXT.
- `aliases` y el catálogo de correcciones son entradas comunes explícitas. Su uso
  se registra con hash y no cambia la identidad de la fuente primaria.
- Cambiar modo o cualquier archivo invalida el dataset activo. Las conversiones y
  proyectos anteriores continúan como historial, pero no son elegibles para el
  nuevo flujo.
- Ninguna conversión o carga en PowerFactory se acepta si su `source_run_id` no
  coincide con la ejecución activa.

## 3. Custodia y procedencia

Al pulsar **Cargar / listar alimentadores**, el servidor crea una ejecución
inmutable en `runs/<run_id>/`:

```text
runs/<run_id>/
  source_manifest.json
  originales/<modo>/<slot>/<nombre_original>
  inventario/dataset_inventory.json
  salida/
```

`source_manifest.json` contiene modo, fecha, tamaño y SHA-256 de cada original,
origen de carga, versión del adaptador y huella conjunta. Los adaptadores leen las
copias custodiadas, no rutas mutables del operador. Un directorio o archivo
comprimido VNR se conserva sin alteración; su extracción se realiza en una carpeta
derivada separada y se registra en el manifiesto.

## 4. Arquitectura

Se incorpora un contrato común en `igea_dgs.web.sources`:

```python
class SourceAdapter(Protocol):
    mode: Literal['txt', 'mdb', 'vnr']
    def load(self, snapshot: SourceSnapshot, *, aliases: dict[str, str]) -> SourceLoadResult: ...
```

`SourceLoadResult` entrega un `CymdistDataset`, un informe de catálogo, la
preparación por alimentador y procedencia. Los adaptadores TXT y MDB encapsulan los
lectores actuales sin cambiar sus reglas. El adaptador VNR usa el modelo canónico
de `vnr_etl`, filtra por `CODEMP`/periodo cuando estén disponibles y transforma a
`CymdistDataset` mediante un puente explícito, no mediante un segundo conversor
DGS paralelo.

El resto del proceso —inventario, selección, conversión, agrupación, archivos de
salida y PowerFactory— consume el contrato común. Así las tres alternativas reciben
las mismas puertas de calidad.

## 5. Entrada VNR-GIS

La interfaz permite:

- cargar un paquete local completo o indicar una ruta del servidor;
- consultar publicaciones oficiales descubiertas y descargar una únicamente
  cuando el recurso sea un paquete de datos verificable;
- mostrar empresa, periodo, capas, esquema, CRS, huella y fecha de publicación;
- rechazar PDF regulatorios como fuentes convertibles;
- enumerar todos los valores no vacíos de `CODSALIDAMT` como alimentadores;
- filtrar Electro Dunas mediante códigos/alias oficiales sin inferencia difusa.

La Resolución 154-2026 encontrada es un proyecto de publicación del VNR adaptado al
31-12-2025. Hasta disponer de un paquete de datos oficial completo, la interfaz debe
mostrar `PAQUETE_NO_DISPONIBLE` y admitir carga manual; no debe simular que los PDF
son una base VNR.

## 6. Integridad eléctrica y catálogos

El sistema puede completar parámetros de equipos solo mediante coincidencia exacta
y trazable con catálogo VNR, catálogo global controlado o catálogo del fabricante.
No puede inventar:

- alimentadores o pertenencia de objetos;
- nodos extremos o conectividad;
- fuente/slack;
- demanda activa/reactiva o factor de potencia;
- tensión, fases o estado operativo;
- conductor ante una coincidencia ambigua.

Cada alimentador expone uno de estos estados:

- `INVENTORY_ONLY`: identificable, pero sin datos suficientes para convertir;
- `CONVERSION_READY`: tiene topología, fuente, datos eléctricos y mapeos exactos;
- `DGS_READY`: DGS generado y validado por round-trip;
- `POWERFACTORY_VERIFIED`: importado, releído y con `ComLdf` satisfactorio;
- `BLOCKED`: puerta obligatoria fallida, con códigos y campos faltantes.

La conversión de una selección es fail-closed: alimentadores bloqueados no generan
un DGS presentado como productivo. La tabla permite filtrar por estado y explica la
causa de bloqueo.

## 7. Interfaz web

El paso 1 muestra tres botones mutuamente excluyentes: **Tres TXT**, **Base MDB** y
**VNR-GIS**. Solo aparecen las casillas del modo activo y una banda persistente
indica `Fuente activa`, `run_id` y huella abreviada.

El paso 2 conserva la tabla y selección existentes, añadiendo procedencia y estado
de preparación. Las acciones son:

- seleccionar uno, varios o todos;
- convertir individualmente o como red unida;
- descargar originales/manifiesto/evidencias;
- cargar únicamente DGS vigentes de la ejecución activa en DIgSILENT.

Cambiar la fuente exige confirmación visual, crea una nueva ejecución al cargar y
desactiva las salidas del run anterior sin eliminarlas.

## 8. PowerFactory y evidencia de aceptación

Antes de escribir en PowerFactory se ejecuta un dry-run sobre exactamente el mismo
plan y `source_run_id`. Por alimentador se verifica:

1. identidad de proyecto, NetworkID y alimentador;
2. existencia y hash del DGS y metadatos asociados;
3. importación sin colisiones ambiguas;
4. relectura de alimentador, P, Q, FP y fases;
5. ejecución de `ComLdf` y convergencia;
6. informe JSON/TXT con objetos creados, advertencias y errores;
7. rollback ante fallo antes de declarar aceptación.

Éxito de comando, DGS generado e importación son estados distintos. Solo el último
estado, con relectura y flujo, es `POWERFACTORY_VERIFIED`.

## 9. API

Se amplía `input_mode` a `Literal['txt', 'mdb', 'vnr']`. Se agregan:

- `GET /api/vnr/publications` para descubrimiento oficial con evidencia;
- `POST /api/workspaces/{wid}/vnr/download` para custodiar un paquete elegido;
- `GET /api/workspaces/{wid}/runs` para historial y manifiestos;
- `GET /api/workspaces/{wid}/runs/{run_id}/manifest` para auditoría.

Las rutas existentes de carga, alimentadores, conversión y PowerFactory permanecen
y operan sobre el run activo. Si no existe run o no coincide la procedencia,
responden con `409 SOURCE_RUN_MISMATCH`.

## 10. Pruebas y aceptación

La implementación es TDD. Como mínimo debe demostrar:

- rechazo de mezcla TXT/MDB/VNR en API y servicio;
- conservación byte a byte y SHA-256 de originales;
- invalidación al cambiar modo o archivo;
- inventario y selección uno/varios/todos en las tres rutas;
- VNR con dos o más `CODSALIDAMT`, y bloqueo explícito si faltan carga/fuente;
- no resolución difusa o `DEFAULT` silencioso de catálogos;
- rechazo de DGS de un run anterior;
- build de frontend y suite completa de backend;
- aceptación real MDB y TXT con el conjunto disponible;
- aceptación real VNR solo cuando exista un paquete oficial/completo;
- importación real en PowerFactory con relectura y `ComLdf` para IN111.

Si el paquete oficial VNR no está disponible, el resultado correcto es
`BLOCKED_MISSING_OFFICIAL_PACKAGE`, no una aceptación sintética.

## 11. Fundamento técnico y científico

El modelo canónico y la validación antes de exportar siguen la tesis doctoral de
McMorran sobre intercambio de modelos mediante CIM y validación entre herramientas
propietarias: <https://doi.org/10.48730/bvtk-xz74>.

La reconstrucción GIS, teoría de grafos y comprobación mediante flujo de potencia
se sustentan en la tesis de maestría de Özdamar:
<https://open.metu.edu.tr/handle/11511/44535>, y en la disertación de Crispino:
<https://doi.org/10.11606/D.3.2001.tde-15042003-092110>.

La necesidad de fusionar datos heterogéneos conservando identidad y trazabilidad
está respaldada por el artículo indexado IEEE sobre modelado topológico GIS:
<https://doi.org/10.1109/ICEMCE60359.2023.10490965>, y la identificación conjunta
de topología y parámetros se apoya en el trabajo indexado IET:
<https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/gtd2.12634>.

Las fuentes regulatorias consultadas son la página oficial de resoluciones 2026 de
Osinergmin, <https://www.osinergmin.gob.pe/Resoluciones/Resoluciones-GRT-2026.aspx>,
y la publicación de la Resolución 154-2026 en El Peruano,
<https://busquedas.elperuano.pe/dispositivo/NL/2542336-1>.
