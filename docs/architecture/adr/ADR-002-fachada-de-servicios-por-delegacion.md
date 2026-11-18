# ADR-002 · La fachada `web/services.py` se parte por delegación, un caso de uso cada vez

- Estado: vigente
- Fecha: 2026-11-14
- Specs: 002:RF-1, 002:RF-20, 002:RF-21
- Elementos C4: api, cmpWeb, cmpFachadaServicios, cmpCasosDeUso, cmpEntrada, cmpEstudios
- Tareas: 002 T7, 002 T9

## Contexto

`src/convertersmartgrid/presentacion/web/services.py` tiene 13 904 líneas en 00d30651 y `web/app.py`, 3 059: casi cada tarjeta
toca la fachada, y dos tarjetas en paralelo chocan en ella. La spec 002 tiene abiertas T7 (mover los módulos a sus
capas, con reexportaciones temporales) y T9 (retirar las reexportaciones). El Plan Maestro V1 (§30.5, fase A2)
pide «crear una interfaz pequeña para un flujo identificado y delegar desde la fachada», sin mover 13 000 líneas en
un commit.

## Decisión

`web/services.py` queda como fachada estable: cada caso de uso sale a su módulo de aplicación, de uno en uno y en un
commit propio, y la fachada solo delega en él. Los consumidores (rutas, CLI, asistente, pruebas) siguen llamando a la
fachada hasta que T9 los pase a la ruta nueva; entonces la fachada se retira. Cada paso se acepta con las respuestas
REST y los DGS idénticos byte a byte (002:RF-20) y la prueba de capas en verde.

## Alternativa descartada

Reescribir `services.py` en paquetes nuevos de una vez. Se descarta: rompe a la vez todas las tarjetas en curso, no
deja comparar byte a byte paso a paso y no tiene vuelta atrás parcial.

## Consecuencias

- Mientras dure, conviven la fachada y los casos de uso; la fachada no puede ganar lógica nueva.
- La tarjeta va la última de su tanda, para no chocar con las que tocan la fachada.
- El TO-BE muestra la fachada y los casos de uso (`cmpFachadaServicios`, `cmpCasosDeUso`).

## Contratos afectados

Rutas REST y WebSocket de `/api` (sin cambios de forma; el OpenAPI generado debe quedar igual), el CLI
`convertersmartgrid`, las importaciones de `tools/` y de las pruebas, y los DGS (byte a byte).

## Vuelta atrás

Cada caso de uso es un commit: se revierte ese commit y la fachada vuelve a tener su código. Mientras exista la
fachada no hay consumidor que cambiar de vuelta.
