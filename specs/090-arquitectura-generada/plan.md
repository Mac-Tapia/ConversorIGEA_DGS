# Plan — Spec 090

## Módulos

- `tools/generar_arquitectura.py` (RF-1 a RF-10, RF-12): lee con `Fuente`, del árbol o del índice de git, y escribe `docs/ARQUITECTURA_CATALOGO.md`.
- `docs/architecture/subsistemas.json` (RF-1, RF-3): a qué subsistema va cada fichero. Es lo único escrito a mano del catálogo.
- `.githooks/pre-commit`, `post-commit` y `post-merge`, con `.githooks/regenerar.sh` (RF-11 a RF-14).
- `.gitattributes` (RF-13): `merge=union` para el catálogo. La fusión no se para y `post-merge` lo regenera y corrige ese commit. Descartado `pre-merge-commit`: git calcula el árbol antes de ejecutarlo, y lo que añade no entra.
- `docs/ARQUITECTURA.md` (RF-15, RF-16): la parte que explica, con su tabla de correcciones.

## Decisiones

- **Fichero aparte, no bloques dentro de `ARQUITECTURA.md`.** Con bloques, cada rama que añade un módulo chocaría con quien edita el texto.
- **El producto se lee con `ast`, sin importarlo.** Así el gancho no carga FastAPI ni PyTorch, y puede leer del índice. Descartado importar `tareas.py` y `equipo.py`: leerían el árbol de trabajo, con lo sin confirmar de otra sesión. Las pruebas sí los importan, y comparan.
- **Un gancho que falla no bloquea** (P: nada bloquea a las otras sesiones por un documento). Lo detiene la suite.
- **`post-commit` deja el índice como `HEAD`.** En un commit con rutas explícitas el gancho añade al índice temporal, y el real quedaría con el catálogo anterior.
- **`git ls-files -c`, no el disco.** Un fichero sin versionar de otra sesión no debe entrar en el catálogo de este commit.

## Pruebas

`tests/test_arquitectura_generada.py`: catálogo al día, cobertura de cada fichero, ficheros que aparecen y desaparecen, comparación de tareas y roles con el código real importado, y los ganchos de punta a punta en un repositorio temporal (commit normal, con rutas, fusión y generador roto).
