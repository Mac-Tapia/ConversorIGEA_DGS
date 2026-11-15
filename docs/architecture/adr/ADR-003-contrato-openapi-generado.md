# ADR-003 · La frontera entre la web y la API es el OpenAPI generado

- Estado: vigente
- Fecha: 2026-11-14
- Specs: 002:RF-16, 002:RF-17
- Elementos C4: frontend, api, cmpInterfaz, cmpWeb, security
- Tareas: 002 T10
- Evidencia: `tools/generar_contrato_api.py::generar`, `tools/generar_contrato_api.py::comprobar`, `frontend/src/api/esquema.ts~Generado por tools/generar_contrato_api.py`

## Contexto

La web React y la API FastAPI se escriben en dos lenguajes. Antes de la spec 065 los tipos del frontend se escribían
a mano y se separaban del servidor sin que nada lo avisara. El Plan Maestro V1 (BP-31, F-10) pide que el frontend
consuma tipos generados y que la integración continua falle si un tipo a mano duplica uno generado.

## Decisión

El contrato entre la web y la API es el esquema OpenAPI que sale de los modelos Pydantic del servidor.
`tools/generar_contrato_api.py` genera de él `frontend/src/api/esquema.ts`, con la huella del OpenAPI en la cabecera,
y `--check` falla si el fichero no está al día. La web no llama al motor Python por ninguna otra vía.

## Alternativa descartada

Mantener los tipos de TypeScript a mano, o pasar a GraphQL. A mano se desfasan en silencio; GraphQL cambiaría las 161
rutas y el cliente sin ganancia medida, contra la regla del plan de no sustituir el stack sin evaluación (§30.2).

## Consecuencias

- Un cambio de respuesta en el servidor obliga a regenerar `esquema.ts` en el mismo commit.
- Quedan tipos escritos a mano en `frontend/src/api/types.ts`; reducirlos es F-10 (002 T12), que no cambia esta
  decisión sino que la completa.

## Contratos afectados

`docs/asistente/openapi.json`, `frontend/src/api/esquema.ts` y el cliente `frontend/src/api/client.ts`.

## Vuelta atrás

Volver a tipos a mano sería quitar la generación y su comprobación; no se recomienda y requeriría un ADR que
sustituya a este.
