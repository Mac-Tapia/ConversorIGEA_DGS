# Plan — Spec 070

Lee: `docs/constitution.md`, `specs/070-asistente-de-punta-a-punta/spec.md`, 067 y 069.

## Contexto técnico

`asistente/tareas.py` declara; `asistente/ejecutor.py` da los pasos por las rutas de la web; `web/services.py` arma el plan;
`asistente/equipo.py` gobierna; `asistente/orquestador.py` encadena etapas. Lo nuevo de la web va en un módulo aparte porque
`services.py` lo comparten varias sesiones.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Datos, tareas y frases literales | `asistente/tareas.py`, `asistente/plan.py`, `asistente/interprete.py`, `asistente/sinteticos.py` | RF-17, RF-18, RF-38, RF-39 |
| Pasos de cada tarea | `asistente/ejecutor.py` | RF-1, RF-3, RF-4, RF-9, RF-12, RF-13, RF-16, RF-19, RF-22 a RF-29, RF-32, RF-34 a RF-36 |
| Requisitos y extras de la web | `web/asistente_operacion.py`, llamado desde `web/services.py` | RF-2, RF-5 a RF-7, RF-10, RF-11, RF-14, RF-15, RF-30, RF-37, RF-58 |
| Consultas y «no disponible» | `web/asistente_consultas.py`; ruta de SED en `web/app.py` | RF-40 a RF-49 |
| Etapas | `asistente/orquestador.py`, `web/services.py` | RF-8, RF-31, RF-50 a RF-56 |
| Reglas de dominio | `web/services.py`, `tools/sistema_web.py` | RF-20, RF-21, RF-57, RF-59 a RF-61 |
| Cancelar sin esperar | carril `control` en `web/jobs.py`, `web/app.py` | RF-33 |
| Vía antigua | `tools/asistente_entrenar.py`, `asistente/transformer.py`, `asistente/clasificador.py` | RF-62 a RF-66 |
| Currículo y prueba | `asistente/curriculo_maestro.py`, `asistente/prueba_sellada.py`, `asistente/destilacion_integral.py` | RF-67 a RF-75 |

## Decisiones

- Cancelar va en un carril propio. Descartado encolarlo en `asistente`: `submit` da 409 con ese carril ocupado, y es justo cuando hace falta.
- La base calibrada se pide en un paso de lectura (`/demanda/ajuste/ultimo`) y no se guarda en el plan: en el proyecto entero aún no existe al proponerlo.
- La prueba sellada usa un vocabulario propio y fijo, sin nombres de empresa. Descartado el vocabulario del espacio: su huella cambiaría con cada espacio.
- La histórica se reconoce por tarea anterior y sin marca de conjunto; sus filas no cambian porque su semilla depende de la plantilla y de la tarea.
- Descartado añadir las tareas nuevas a las órdenes fijas: cambiaría su huella (068:RF-41, 069:RF-13).

## Pruebas

`tests/test_asistente_maestro.py` con la web real por `TestClient` y motores sustituidos, sin GPU ni DIgSILENT. Ningún nombre de
empresa ni número fijo de alimentadores salvo la regla de RF-57.
