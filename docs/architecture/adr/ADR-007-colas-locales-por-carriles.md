# ADR-007 · Trabajos en colas locales por carriles; DIgSILENT, estrictamente en serie

- Estado: vigente
- Fecha: 2026-11-14
- Specs: 002:RF-14, 002:RF-30
- Elementos C4: jobs, api, engine, nativeRunner, operationStore
- Evidencia: `src/convertersmartgrid/web/jobs.py::LANES`, `src/convertersmartgrid/web/jobs.py::JobManager`, `src/convertersmartgrid/web/jobs.py::DiarioTrabajos`, `src/convertersmartgrid/web/jobs.py::EventLog`

## Contexto

Nada largo puede correr dentro de una petición HTTP. El motor de PowerFactory solo admite un proceso con su motor a
la vez. El Plan Maestro V1 (§30.6) pide trabajos resilientes con cancelación cooperativa, sin introducir Redis ni un
bus distribuido sin caso cuantificado.

## Decisión

`web/jobs.py` mantiene cuatro carriles (`engine`, `powerfactory`, `asistente` y `control`) en el mismo proceso web.
El de `powerfactory` es estrictamente serie; el de `control` solo cancela. Cada trabajo publica eventos numerados
(`EventLog`), así que el navegador reconecta sin perder ni duplicar nada, y el diario (`DiarioTrabajos`) deja
constancia de cada trabajo aunque el proceso caiga. Si un día hubiera que repartir entre máquinas, se sustituye
`web/jobs.py` sin tocar las rutas de la API.

## Alternativa descartada

Redis o RQ con trabajadores aparte. Añade un servicio que el operador tendría que instalar y vigilar, y no resuelve
la restricción real (un solo proceso con PowerFactory), que sigue obligando a un carril en serie.

## Consecuencias

- Un reintento nunca repite una escritura externa sin conocer el resultado anterior (correo, nube, promoción de
  modelos): eso lo decide cada trabajo, no la cola.
- La capacidad está acotada por una máquina; es el despliegue que el producto tiene.

## Contratos afectados

El WebSocket de eventos (números de secuencia), los estados de trabajo de la API y el diario de trabajos.

## Vuelta atrás

No hay nada que deshacer: es el estado actual. Pasar a una cola distribuida sería un ADR que sustituya a este.
