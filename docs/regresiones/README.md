# Regresiones: cada fallo real deja una comprobación permanente

Usuario, 2026-11-03: «debe hacerse cada vez más robusta e implementar mejoras, estos errores ya no deberían ocurrir, se supone
que estamos haciendo la mejora continua».

Esta es la regla para los próximos: **cuando un fallo real llega al operador, entra aquí en el mismo cambio que lo corrige**. Un fallo
sin entrada volverá. La corrección de un caso no basta: la entrada obliga a decir qué comprueba toda la clase, para siempre.

## Una entrada

Un fichero `AAAA-MM-DD-<nombre-kebab>.md`, con estos apartados y en este orden; `tests/test_regresiones.py` los comprueba (spec 081):

```markdown
# Lo que vio el operador, en una línea

## Síntoma
Lo que se vio, con el mensaje tal cual lo dio el programa.

## Causa
La causa comprobada en el código o en DIgSILENT. Si no se ha confirmado: «causa sin confirmar», qué se sabe y qué la confirmaría.

## Comprobación permanente
Lo que desde ahora lo detecta o lo corrige, para toda la clase de fallos y no solo este caso.

## Prueba
- `tests/test_x.py::test_y`
```

Reglas:

- Cada `tests/x.py::test_y` tiene que existir: una entrada que no apunta a nada se queda en papel y la suite falla.
- Sin nombres de clientes, alimentadores, sistemas o empresas: es un documento del conversor, y se sube a git.
- Nada de datos de la distribuidora. Las pruebas son sintéticas (constitución P9 y P13).
- Lo que solo se comprueba en DIgSILENT o en el navegador lleva además su tarea `[DIgSILENT]`: la entrada dice cuál.
- Una causa que se confirma después se escribe aquí, en la misma entrada.
