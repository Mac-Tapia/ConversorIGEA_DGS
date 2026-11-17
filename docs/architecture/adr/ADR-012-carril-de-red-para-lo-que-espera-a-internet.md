# ADR-012 · Lo que espera a internet va en su propio carril y no bloquea la entrada

- Estado: vigente
- Fecha: 2026-11-17
- Specs: 080:RF-61
- Elementos C4: jobs, vnrGis, frontend
- Tareas: 080 T18
- Evidencia: `src/convertersmartgrid/web/jobs.py::LANES`

## Contexto

La búsqueda de publicaciones oficiales de VNR-GIS iba en el carril del motor. Sin red, o con una red lenta, dejaba
bloqueado todo el panel de entrada (alternativa, empresa y subida del propio paquete) hasta agotar su tiempo; lo
encontró el recorrido F01 en un navegador real.

## Decisión

Un carril «red» en la cola local (ADR-007) para el trabajo que solo espera a internet. La entrada se bloquea solo con
el motor ocupado. La barra de trabajos nombra cada carril por su nombre.

## Alternativa descartada

Bajar el tiempo de espera de la búsqueda: el panel seguiría bloqueado mientras dura, y una red lenta lo agota igual.

## Consecuencias

Una tarea de red futura (descargas oficiales, correo) usa ese carril o el suyo, nunca el del motor.

## Contratos afectados

`JobRespuesta.lane` admite «red».

## Vuelta atrás

Volver a encolar la búsqueda en «engine»; el carril vacío no estorba.
