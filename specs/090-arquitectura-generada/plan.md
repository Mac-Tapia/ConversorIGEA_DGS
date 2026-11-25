# Plan — Spec 090

## Módulos

- `tools/generar_arquitectura.py` (RF-1 a RF-10, RF-12): lee con `Fuente`, del árbol o del índice de git, y escribe `docs/ARQUITECTURA_CATALOGO.md`.
- `docs/architecture/subsistemas.json` (RF-1, RF-3): a qué subsistema va cada fichero. Es lo único escrito a mano del catálogo.
- `.githooks/pre-commit`, `post-commit` y `post-merge`, con `.githooks/regenerar.sh` (RF-11 a RF-14).
- `.gitattributes` (RF-13): `merge=union` para el catálogo. La fusión no se para y `post-merge` lo regenera y corrige ese commit. Descartado `pre-merge-commit`: git calcula el árbol antes de ejecutarlo, y lo que añade no entra.
- `docs/ARQUITECTURA.md` (RF-15, RF-16): la parte que explica, con su tabla de correcciones.
- `docs/architecture/workspace.dsl` y `arquitectura-interactiva-c4.html` (RF-20 a RF-22, RF-24): contenedores «Motores abiertos de
  flujo» y «VNR de la Guía 232-2017», el VAD con su propio componente, las propiedades «Carril …» de las colas, y en la página
  las vistas «Carriles», «Motores de flujo» y «Regulatorio» con el pseudocódigo de cada vista.
- `docs/architecture/subsistemas.json` (RF-20, RF-21): grupos «Motor: motores abiertos de flujo» y «Motor: VNR de la Guía
  232-2017»; el VAD queda en «Motor: VAD (estudio de costos de la empresa modelo)».
- `docs/architecture/pseudocodigo.md` (RF-23): un bloque `## <id> — <título>` por flujo, con su código entre vallas.
- `tools/generar_c4.py` (RF-20, RF-22, RF-24): lee `MOTORES` y `LANES` con `ast`, exige su presencia en el DSL y la página, y
  pone el pseudocódigo en la página entre `<!-- pseudocodigo:inicio -->` y `<!-- pseudocodigo:fin -->`.
- `frontend/scripts/exportar-c4.mjs` (RF-26): abre la página en Chromium con el Playwright de `frontend/`, saca una PNG por
  pestaña y compone el PDF con las vistas y el pseudocódigo.

## Decisiones

- **Fichero aparte, no bloques dentro de `ARQUITECTURA.md`.** Con bloques, cada rama que añade un módulo chocaría con quien edita el texto.
- **El producto se lee con `ast`, sin importarlo.** Así el gancho no carga FastAPI ni PyTorch, y puede leer del índice. Descartado importar `tareas.py` y `equipo.py`: leerían el árbol de trabajo, con lo sin confirmar de otra sesión. Las pruebas sí los importan, y comparan.
- **Un gancho que falla no bloquea** (P: nada bloquea a las otras sesiones por un documento). Lo detiene la suite.
- **`post-commit` deja el índice como `HEAD`.** En un commit con rutas explícitas el gancho añade al índice temporal, y el real quedaría con el catálogo anterior.
- **`git ls-files -c`, no el disco.** Un fichero sin versionar de otra sesión no debe entrar en el catálogo de este commit.
- **Pseudocódigo en un fichero y copiado a la página (RF-23, RF-24).** Descartado escribirlo dos veces: se separarían como se
  separó la cifra de los carriles. La página es autónoma (la entrega de `build_interactive_architecture.py` no lee otros
  ficheros), así que la orden lo copia y la puerta comprueba la copia.
- **Motores y carriles leídos con `ast` (RF-20, RF-22).** Igual que el catálogo: la puerta no importa el producto.
- **La exportación con el Playwright de `frontend/` (RF-26).** El `.venv` no lleva Playwright para Python, y el del frontend ya
  está fijado con su versión para las pruebas e2e.
- **U0 002/050 (2026-11-08).** El orden de familias se lee con AST desde su dueño
  `contratos_aprendizaje.py`; `training_coordinator.py` lo importa, sin duplicar el
  literal. `FUENTES` conserva ese proveedor también en la prueba de hooks aislada.
  Cambiar de proveedor no cambia el orden, no importa el producto ni convierte un
  fallo de generación en un éxito; se prueba que una constante obsoleta en el
  coordinador no sustituye al contrato canónico.

## Pruebas

`tests/test_arquitectura_generada.py`: catálogo al día, cobertura de cada fichero, ficheros que aparecen y desaparecen, comparación de tareas y roles con el código real importado, y los ganchos de punta a punta en un repositorio temporal (commit normal, con rutas, fusión y generador roto).

`tests/test_arquitectura_c4_al_dia.py` (RF-20 a RF-24): motores, carriles y pseudocódigo comprobados contra el código, con
cada defecto sembrado en una copia (un motor o un carril que falta o sobra, una función citada que no existe y la página
con otro pseudocódigo), RF-25 (los carriles de `docs/ARQUITECTURA.md` frente a `LANES`) y RF-26 (cada pestaña con su vista y el PDF con una página por vista y por bloque).
