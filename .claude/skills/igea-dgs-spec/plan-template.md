# Plan — Spec NNN

Lee: `docs/constitution.md` y `specs/NNN-<nombre>/spec.md`.

## Contexto técnico
<Módulos y ficheros reales que se tocan; qué índices del dataset, qué carril de trabajos.>

## Diseño por partes
| Parte | Ficheros | Cubre |
| --- | --- | --- |
| <parte> | `src/igea_dgs/...` | RF-1, RF-2 |

## Decisiones
- <Decisión>. Descartado: <alternativa>, porque <motivo>.

## Comprobación contra la constitución
<Principio por principio, solo los afectados: cómo se respeta.>

## Estrategia de pruebas
- Sintéticas sorteadas (`ExportSpec(seed=…)`), con las dos disposiciones si toca el lector.
- Datos reales (las tres `IGEA_*`) si toca el lector o el modelo.
- Cada prueba cita su requisito: `"""NNN:RF-n — …"""`.

## Riesgos
<Qué puede romperse fuera de lo planeado y cómo se detectaría.>
