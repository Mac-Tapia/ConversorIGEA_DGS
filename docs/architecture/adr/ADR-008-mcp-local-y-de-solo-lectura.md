# ADR-008 · El MCP del proyecto es local, por stdio y de solo lectura

- Estado: vigente
- Fecha: 2026-11-14
- Specs: 077:RF-25, 077:RF-37, 077:RF-38, 077:RF-60
- Elementos C4: mcp, assistant
- Evidencia: `tools/mcp_conversor.py::_servidor`, `tools/mcp_conversor.py~read_only_hint=True, destructive_hint=False`, `src/convertersmartgrid/asistente/lectura_proyecto.py::catalogo`

## Contexto

El asistente y un cliente MCP de esta máquina necesitan leer el proyecto (ficheros permitidos, búsqueda y la API).
El Plan Maestro V1 (ADR-AG-01 y ADR-AG-08) recomienda conservar el MCP de la 077 como solo lectura y no exponer un
MCP HTTP público en la V1. Un documento leído puede traer instrucciones dirigidas al agente (F-18).

## Decisión

`tools/mcp_conversor.py` sirve solo por stdio las mismas lecturas del catálogo de `lectura_proyecto`, con su misma
validación y su mismo gobierno, y marca cada herramienta como de solo lectura y no destructiva. Las escrituras del
asistente van por la API existente y solo tras la confirmación del operador; nunca por el MCP.

## Alternativa descartada

Un MCP HTTP con herramientas de escritura. Abre una superficie de ataque nueva (identidad, transporte, inyección en
documentos) que la V1 no necesita y que exigiría el broker de políticas que aún no existe.

## Consecuencias

- Añadir una herramienta que escriba exige un ADR que sustituya a este y una spec con su negación por cada vía (F-18).
- El cliente MCP ve exactamente lo que ve el asistente en la web.

## Contratos afectados

El catálogo de lecturas de `asistente/lectura_proyecto.py` y el esquema de herramientas del servidor MCP.

## Vuelta atrás

Retirar el servidor MCP: el asistente de la web no depende de él.
