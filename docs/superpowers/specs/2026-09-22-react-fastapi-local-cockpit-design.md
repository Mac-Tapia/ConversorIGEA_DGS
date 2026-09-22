# Cockpit local React + FastAPI para IGEA/DGS/PowerFactory

**Fecha:** 2026-09-22  
**Estado:** diseño aprobado en conversación; pendiente revisión del documento  
**Alcance:** aplicación local monousuario para Windows con React como interfaz principal y Tkinter como respaldo temporal.

## 1. Objetivo

Construir una interfaz web local moderna que exponga el proyecto completo, no solamente el conversor heredado. Debe conservar la selección de RED, CARGA, BD_Equipo, carpeta de salida, CRS, alimentadores, mapa y exportaciones de la GUI actual; además debe integrar catálogo estricto, TRAFOMIX, trazabilidad, editor unifilar, puertas G1–G6, publicación atómica, PowerFactory y estudios.

React será la interfaz principal. FastAPI será el único acceso al dominio Python y a PowerFactory. Los TXT originales nunca se modificarán. Toda edición se almacenará como una revisión auditable de una copia de trabajo.

## 2. Decisiones aprobadas

- Aplicación exclusivamente local y monousuario.
- FastAPI escucha solo en `127.0.0.1`.
- React + TypeScript servido como recursos estáticos por FastAPI en producción.
- Cockpit técnico con navegación permanente, no un asistente rígido.
- Unifilar Cytoscape editable desde la primera versión.
- Mapa Leaflet incluido desde la primera versión.
- Selección nativa de carpeta/archivos, selección individual y arrastrar/soltar.
- TXT originales inmutables; las modificaciones son operaciones versionadas.
- El modo estricto es obligatorio; no existe interruptor para desactivarlo.
- Tkinter permanece disponible como respaldo temporal, sin recibir funciones nuevas.
- Ningún recurso de ejecución depende de CDN o Internet.

## 3. Arquitectura

```text
React 19 + TypeScript + Vite
  ├── cockpit, formularios y diagnósticos
  ├── Cytoscape.js: unifilar editable
  ├── Leaflet: mapa geográfico
  └── WebSocket: progreso de trabajos
                │ HTTP/JSON + WS (localhost)
FastAPI ────────┤
  ├── selección nativa de Windows
  ├── proyectos, revisiones y trabajos
  ├── PipelineService G1–G6
  ├── catálogo y reglas TRAFOMIX/SED
  ├── DGS estricto y publicación atómica
  ├── adaptadores PowerFactory
  └── manifiestos/evidencias
                │
Directorio local del proyecto + DIgSILENT PowerFactory 2024
```

FastAPI no duplicará reglas eléctricas. Adaptará los módulos existentes a contratos HTTP tipados. React nunca calculará parámetros eléctricos ni decidirá si una puerta aprueba.

### 3.1 Procesos

Un lanzador Python:

1. valida Python 3.12 x64 y dependencias;
2. reserva un puerto local disponible;
3. inicia FastAPI en `127.0.0.1`;
4. espera `/api/health`;
5. abre el navegador predeterminado;
6. registra PID y token de sesión;
7. al cerrar, cancela trabajos controladamente y libera recursos.

PowerFactory se ejecutará mediante el adaptador local. No se trasladará a trabajadores externos porque su API y sesión pertenecen a esta máquina.

## 4. Experiencia de usuario

### 4.1 Navegación

Barra lateral permanente:

1. Proyecto
2. Diagnóstico G1–G4
3. Unifilar
4. Mapa
5. PowerFactory G5–G6
6. Evidencias

La cabecera mostrará proyecto, revisión, alimentador activo, puerta actual, bloqueos y trabajo en ejecución.

### 4.2 Proyecto y entradas

La primera pantalla conserva y amplía la GUI anterior:

- seleccionar carpeta de entrada;
- detectar RED, CARGA y BD_Equipo por patrón;
- examinar cada archivo individualmente;
- arrastrar carpeta o archivos;
- seleccionar carpeta de salida;
- abrir proyecto existente;
- configurar CRS origen y destino;
- seleccionar política explícita de longitud;
- activar geografía, preview, XLSX y TSV;
- mostrar coherencia del lote, hashes y errores antes de continuar.

Los selectores nativos se abren desde endpoints locales y solo devuelven la ruta elegida expresamente. La carga por navegador copia archivos al proyecto. En ambos casos se calculan hashes antes de analizar.

No se conservarán los aliases libres ni el modo no estricto. Los aliases se reemplazan por mapeos de catálogo aprobados, versionados y con evidencia.

### 4.3 Diagnóstico

El tablero mostrará:

- cobertura de secciones TXT;
- conteos por alimentador y tipo de elemento;
- resultados G1–G4;
- diagnósticos con severidad, código, archivo, sección, fila y campo;
- equipos sin ficha o con mapping ambiguo;
- TRAFOMIX y cargas excluidas, junto con SED/cargas conservadas;
- filtros, búsqueda, exportación JSON/CSV y navegación al elemento.

Seleccionar un diagnóstico enfoca el mismo elemento en la tabla, el unifilar y el mapa.

### 4.4 Editor unifilar

Cytoscape representa nodos, tramos aéreos/subterráneos, cargas, SED, interruptores, fuentes externas, plantas solares y generadores térmicos. Los estilos indican fases, estado, bloqueo, exclusión y tipo de elemento.

Operaciones:

- crear o eliminar elementos;
- conectar, desconectar o reconectar extremos;
- mover la representación gráfica;
- editar fases, circuitos/ternas, conductores, sección, longitud y estado;
- editar P/Q y parámetros de fuentes/generadores cuando el dominio lo permita;
- asignar una ficha exacta del catálogo;
- deshacer/rehacer;
- comparar revisiones;
- validar el borrador.

El panel de propiedades diferencia:

- valor original TXT;
- valor efectivo de la revisión;
- unidad;
- evidencia/ficha;
- diagnóstico;
- justificación del cambio.

Mover un elemento solo cambia presentación. Alterar conectividad o atributos crea una operación de dominio y vuelve a ejecutar las puertas afectadas.

### 4.5 Mapa

Leaflet muestra coordenadas y geometría de la misma revisión que Cytoscape. La selección es bidireccional. Editar coordenadas o geometría crea operaciones explícitas; no cambia longitud eléctrica salvo que el usuario seleccione una política compatible y la validación dimensional apruebe.

### 4.6 PowerFactory

La pantalla exige seleccionar proyecto administrado, Study Case y escenario con identidad exacta. Presenta:

- DGS publicado y hash;
- estado de importación;
- conteos/diffs G5;
- idempotencia de segunda ejecución;
- flujo original inmutable;
- copia diagnóstica y diff separado;
- preflight y resultado IEC 60909;
- falta de datos diferenciada de falta de licencia;
- KPIs, tensiones, corrientes, P/Q, pérdidas y estados.

No existirá una acción equivalente a `--fix-until-converge` sobre el caso original. Una prueba correctiva requiere crear una copia diagnóstica con `run_id`.

## 5. Modelo de proyecto y revisiones

Cada proyecto contiene:

```text
projects/<project_id>/
  project.json
  inputs/              # copias con hash cuando se cargan por navegador
  revisions/
    base/
    r01/
      changes.jsonl
      validation.json
  runs/<run_id>/
  published/<revision_id>/
  evidence/
```

`project.json` registra rutas seleccionadas, hashes, fechas, versiones, CRS y política de longitud. Los archivos fuera del directorio solo se leen si fueron seleccionados explícitamente y su identidad coincide con la registrada.

### 5.1 Operación de cambio

Cada operación incluye:

- `operation_id` y secuencia;
- `revision_id`;
- acción: create/update/delete/connect/disconnect/move;
- clase y `external_id` estable;
- campo, unidad, valor anterior y nuevo;
- justificación;
- evidencia de catálogo cuando corresponda;
- fecha y origen `local-user`;
- resultado de validación.

Deshacer agrega la operación inversa. No se reescribe el historial.

### 5.2 Restricciones

- Eliminar un nodo conectado bloquea hasta resolver dependencias.
- No hay parámetros físicos por defecto.
- Una ficha exacta es obligatoria para impedancias, admitancias y ampacidad.
- Los IDs externos son únicos por clase/proyecto.
- Fases y conectividad deben ser eléctricamente compatibles.
- Circuitos, ternas y conductores son enteros positivos.
- Un borrador bloqueado puede guardarse, pero no publicarse.
- Solo una revisión publicada puede importarse a PowerFactory.

## 6. Contrato API

Prefijo `/api`; JSON UTF-8; OpenAPI generado por FastAPI. Errores:

```json
{
  "code": "SOURCE_SHORT_CIRCUIT_DATA_MISSING",
  "message": "Faltan datos IEC 60909 de la fuente SRC-01",
  "severity": "blocking",
  "location": {"file": "RED.txt", "section": "SOURCE", "row": 18, "field": "R1"},
  "details": {},
  "run_id": "..."
}
```

Endpoints principales:

- `GET /api/health`
- `POST /api/dialog/folder`
- `POST /api/dialog/file`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `POST /api/projects/{project_id}/inputs`
- `POST /api/projects/{project_id}/inspect`
- `GET /api/projects/{project_id}/feeders`
- `GET /api/projects/{project_id}/feeders/{feeder_id}/graph`
- `GET /api/projects/{project_id}/revisions/{revision_id}`
- `POST /api/projects/{project_id}/revisions`
- `POST /api/projects/{project_id}/revisions/{revision_id}/operations`
- `POST /api/projects/{project_id}/revisions/{revision_id}/undo`
- `POST /api/projects/{project_id}/revisions/{revision_id}/validate`
- `POST /api/projects/{project_id}/revisions/{revision_id}/publish`
- `POST /api/projects/{project_id}/powerfactory/import`
- `POST /api/projects/{project_id}/powerfactory/validate`
- `POST /api/projects/{project_id}/studies`
- `GET /api/projects/{project_id}/evidence`
- `GET /api/jobs/{run_id}`
- `POST /api/jobs/{run_id}/cancel`
- `WS /api/jobs/{run_id}/events`

Las mutaciones aceptan una clave de idempotencia. Respuestas largas devuelven HTTP 202 y un `run_id`. El WebSocket emite progreso, puerta, diagnóstico y resultado; reconectar recupera el último estado persistido.

## 7. Orquestación G1–G6

`PipelineService` será el único orquestador de interfaz. La API no llamará directamente a `convert_selection` ni al script heredado de aceptación.

1. G1: custodia, lectura, estructura y cobertura TXT.
2. G2: datos eléctricos, unidades, catálogo, relaciones y reglas TRAFOMIX/SED.
3. G3: fidelidad fuente → modelo/revisión.
4. G4: fidelidad modelo → DGS y publicación atómica.
5. G5: objetos efectivos y conectividad en PowerFactory.
6. G6: estudios, convergencia original, IEC 60909 y KPIs.

Una puerta bloqueada termina las etapas posteriores sin borrar el borrador ni la evidencia.

## 8. Trabajos y concurrencia

Un administrador persistente controla trabajos locales. No se introducen Redis, Celery ni servicios externos. Solo puede existir un trabajo PowerFactory mutante a la vez; inspecciones puras pueden coexistir cuando no leen una revisión en escritura.

Estados: queued, running, passed, blocked, unavailable, failed, cancelling, cancelled. Cancelar solicita terminación cooperativa y ejecuta rollback si una unidad PowerFactory estaba activa.

## 9. Seguridad local

- Enlace exclusivo a loopback.
- Token aleatorio por sesión requerido por HTTP y WebSocket.
- CORS desactivado salvo el origen servido por la propia aplicación.
- Validación y resolución canónica de rutas.
- Sin endpoints de listado arbitrario del disco.
- Selector nativo activado solamente por una acción local del usuario.
- Escape contextual de HTML/JSON y neutralización de fórmulas.
- CSP sin `unsafe-eval` y sin CDN.
- Límites de tamaño para uploads y JSON.
- Registro auditable de mutaciones.
- PowerFactory protegido por proyecto, revisión publicada y `run_id`.

## 10. Frontend

Stack:

- React 19 + TypeScript;
- Vite;
- React Router;
- TanStack Query para estado remoto;
- React Hook Form + validación derivada de OpenAPI;
- Cytoscape.js;
- Leaflet;
- Vitest + Testing Library;
- Playwright para flujo integral.

El estado del servidor no se duplicará en un store global. El estado visual local —selección, filtros, viewport— permanece en React. Los cambios optimistas se limitan a movimiento gráfico; las mutaciones eléctricas esperan confirmación de la API.

## 11. Backend

Stack:

- FastAPI y Uvicorn;
- Pydantic 2;
- servicios existentes `igea_dgs`;
- SQLite para proyectos, revisiones y trabajos; `changes.jsonl` como registro append-only de operaciones; artefactos grandes en archivos;
- pytest, Hypothesis y pruebas ASGI.

Se añadirá un extra/requirements web bloqueado por constraints. La instalación de producción construirá React y empaquetará `dist` dentro del paquete Python o en un directorio versionado servido por FastAPI.

## 12. Pruebas y aceptación

### 12.1 Backend

- contratos de rutas y errores;
- selección de rutas autorizadas/no autorizadas;
- inmutabilidad byte a byte de TXT;
- operaciones, undo y conflictos de revisión;
- G1–G6 y detención por puerta;
- publicación atómica;
- idempotencia;
- cancelación/rollback;
- recuperación de trabajos tras reconexión.

### 12.2 Frontend

- selección de carpeta/archivos y estados incompletos;
- tablas, filtros y navegación cruzada;
- edición Cytoscape y panel de propiedades;
- mapa sincronizado;
- bloqueo de publicación;
- progreso/reconexión WebSocket;
- distinción original/diagnóstico.

### 12.3 Integral

Playwright cubre proyecto → entradas → G1–G2 → alimentación → edición → validación → DGS. PowerFactory se prueba con fake para CI y mediante un procedimiento real separado. Una prueba fake jamás produce el estado “aceptación real”.

Los criterios de entrega son:

- un comando inicia la aplicación y abre el navegador;
- funciona offline después de instalar;
- la GUI reproduce todos los campos útiles de Tkinter;
- el pipeline web no llama al batch heredado;
- todos los elementos se convierten o se bloquean con causa;
- TXT originales permanecen iguales;
- no hay defaults ni mapping aproximado;
- DGS solo se publica tras G1–G4;
- PowerFactory distingue G5/G6, original y diagnóstico;
- cierre limpio sin procesos huérfanos.

## 13. Migración

1. Introducir API y almacenamiento de proyectos sin cambiar Tkinter.
2. Integrar pipeline estricto y pruebas de contrato.
3. Crear cockpit React y selección de archivos.
4. Añadir diagnóstico, unifilar y mapa.
5. Añadir publicación DGS y PowerFactory.
6. Convertir `run_gui.bat` en lanzador web; conservar un acceso `run_tkinter.bat`.
7. Retirar Tkinter únicamente en una decisión posterior y con aceptación real.

## 14. Fundamento técnico y científico

- La tesis de referencia de TU Wien emplea el flujo GIS/DGS → PowerFactory y controles de plausibilidad para detectar tipos de línea incompletos en miles de redes: https://repositum.tuwien.at/bitstream/20.500.12708/7709/2/Kadam%20Serdar%20-%202018%20-%20Definition%20and%20validation%20of%20reference%20feeders%20for...pdf
- La tesis de maestría de Alonso García construye en PowerFactory una red con datos reales, líneas y cargas monofásicas/desbalanceadas: https://digibuo.uniovi.es/dspace/handle/10651/38720
- La identificación conjunta de topología/parámetros muestra que información incompleta o inexacta afecta monitorización y control, y valida cuantitativamente sobre redes IEEE: https://doi.org/10.1109/TIM.2022.3175043
- La calibración de modelos con AMI/PV refuerza la necesidad de comparar parámetros y resultados contra evidencia independiente: https://doi.org/10.1109/TSG.2016.2531994
- Cytoscape.js proporciona un grafo serializable, multigrafo, selección, layouts y eventos apropiados para un unifilar interactivo: https://js.cytoscape.org/
- React 19 es la versión mayor estable documentada oficialmente: https://react.dev/versions
- FastAPI documenta WebSockets y trabajos posteriores a respuesta; los trabajos eléctricos pesados conservarán un administrador local explícito en lugar de depender solo de `BackgroundTasks`: https://fastapi.tiangolo.com/advanced/websockets/ y https://fastapi.tiangolo.com/tutorial/background-tasks/

Los proyectos GridMind, BambooGrid y TENSA se toman como referencias de combinación React/API/grafo/simulación, no como dependencias ni como prueba de validez eléctrica de este conversor.

## 15. Fuera de alcance

- exposición en LAN o Internet;
- autenticación multiusuario/RBAC;
- colaboración simultánea;
- nube, Redis, Celery o contenedores obligatorios;
- edición de TXT originales;
- sustitución inmediata de Tkinter;
- aceptar datos físicos sin evidencia;
- declarar éxito real de PowerFactory a partir de fakes.
