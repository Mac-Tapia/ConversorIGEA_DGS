# Decisiones de arquitectura (ADR)

Un ADR por decisión de frontera (034:RF-36): qué se decidió, por qué, qué se descartó, qué contratos toca y cómo
se vuelve atrás. Acompañan al C4: el AS-IS (`../workspace.dsl`) describe lo que existe y el TO-BE
(`../workspace_to_be.dsl`) solo lo que cambia una frontera; cada elemento nuevo del TO-BE cita su ADR (034:RF-37).

`tests/test_interactive_architecture.py` lee estos ficheros y los compara con el código, así que el formato es
estricto.

## Formato

Fichero `ADR-NNN-<nombre-kebab>.md`. El número no se reutiliza ni se cambia: las pruebas y el TO-BE lo citan.

```
# ADR-NNN · Título

- Estado: vigente | pendiente | sustituida | retirada
- Fecha: AAAA-MM-DD
- Specs: NNN:RF-n, … o «spec NNN»
- Elementos C4: identificadores del AS-IS o del TO-BE
- Tareas: NNN Tn, …                      (opcional)
- Evidencia: `ruta::nombre`, …           (opcional)
- Consumidores: `ruta::nombre`, …        (opcional)
- Pendiente en: tarea o trabajo que lo cierra (obligatorio si está pendiente)
- Sustituida por: ADR-NNN (obligatorio si está sustituida)
- Motivo: … (obligatorio si está retirada)

## Contexto
## Decisión
## Alternativa descartada
## Consecuencias
## Contratos afectados
## Vuelta atrás
```

Las formas de la evidencia:

| Forma | Se cumple cuando |
| --- | --- |
| `ruta.py::nombre` en «Evidencia» | el módulo define `nombre` en su nivel superior (función, clase o asignación) |
| `ruta.py::nombre` en «Consumidores» | el módulo usa `nombre` (lo importa o lo nombra) |
| `pyproject.toml::dep:paquete` | `paquete` está en `[project].dependencies`: es obligatorio, no un extra |
| `ruta::palabra` (no Python) | la palabra está en el fichero |
| `ruta~texto` | el texto literal está en el fichero |

Las rutas son relativas al repositorio; una absoluta o con `..` es un error.

## Estados y lo que exige la prueba

- **vigente** (034:RF-38): toda su evidencia está en el código y todas sus tareas están cerradas. Si el código deja
  de declararla, la prueba falla con el ADR y lo que falta.
- **pendiente** (034:RF-39): aceptada, sin terminar. Dice qué la cierra («Pendiente en») y qué evidencia o qué
  tareas lo demostrarán. Cuando el código ya lo declara todo, la prueba falla por ADR desfasado: se pasa a vigente
  en el mismo cambio que la cierra.
- **sustituida**: nombra el ADR que la sustituye, que tiene que existir.
- **retirada**: dice su motivo.

Una cita a un RF que su spec no define, a una tarea o a un fichero que no existen, un campo o una sección que
faltan y un elemento C4 que no está en ningún modelo hacen fallar la prueba (034:RF-41).
