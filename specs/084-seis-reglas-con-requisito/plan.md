# Plan — Spec 084

Lee: `docs/constitution.md`, 042, 073, 017 (RF-128 a RF-135), 064 y 081.

| Parte | Cubre | Encaje |
| --- | --- | --- |
| `sitio_set.py`, nuevo y puro: distancias, apartar, estado y frase | RF-1 a RF-7, RF-10 | Capa aplicación; solo lee el disco |
| `web/services.set_nueva_proponer` | RF-2, RF-8, RF-10, RF-11 | Aparta antes del oráculo y de crear la obra; lo dice en sus `avisos`, que la web ya muestra |
| `tools/obras_pf.construir_set_nueva`, `_ambos_flujos`, `_trazados_de_la_red` | RF-8, RF-9 | Cada intento se aparta antes de medir; los trazados se leen antes de crear las salidas |
| `instalacion_ternas.py`, nuevo y puro | RF-12, RF-13, RF-15, RF-17, RF-18 | Sin factores en el código: la tabla es del perfil |
| `tools/obras_pf._instalar_ternas` en la terna y en la salida | RF-12, RF-14, RF-15 | `ElmLne.fline`; el tipo no se toca |
| `escalera_optima`, `optimizacion_oraculo` | RF-16 | `capacidad_terna_a` en la obra; entra en la clave de la red factorizada |
| `informes.describir_obra`, `obra_para_informe`; `services` guarda `instalaciones` | RF-17, RF-30 | La obra aplicada admite campos propios (065:RF-26): la API no cambia |
| Solo pruebas sobre `escalera_optima.elegir` y `alternativas_de_obras` | RF-19, RF-20, RF-28, RF-29 | Lo hacen 073 y 017: no se duplica código |
| `pf_arnes.exigir_fuera_de_pruebas`, en `conectar` y en la aceptación | RF-21, RF-22 | Lo real se reconoce por ser `.pyd`; un doble sigue |
| `asistente/plan.resolver` | RF-23, RF-25 | El contraste de nombres ya existía; se añade el verbo de borrar. No toca el corpus ni su huella |
| `pf_arnes.borrar_en_su_proyecto`, en `tools/cargas_pf` | RF-24, RF-26 | `proyecto_de` sustituye a la copia de `tools/obras_pf` |
| Lista `BORRADOS` en la prueba | RF-27 | Un `Delete` nuevo hace fallar la prueba hasta decir qué borra |

## Decisiones

- **Retiro en el perfil, sin valor en el código** (P13). Se descartó deducirlo del módulo de la SET: el libro CAPEX no trae el tamaño del predio. El
  de `config/perfiles/electro_dunas.json` es un supuesto marcado, a confirmar por el usuario.
- **Calles solo de un fichero local.** Se descartó usar el enrutador de `vias.py`: dice cómo ir, no dónde hay calle, y es un servicio externo.
- **La capacidad con `fline` y no con un tipo nuevo.** Copiar un tipo por configuración multiplicaría el catálogo; el factor es de esa línea y vive en su variación.
- **Guarda de pruebas por `PYTEST_CURRENT_TEST`.** La heredan los guiones lanzados por una prueba. Se descartó marcar los datos sintéticos: la marca solo cubriría un generador.
- **Inventario de `Delete` en vez de envolverlos todos.** La mayoría borra lo que la misma ejecución creó en el proyecto que activó; la guarda va donde el operador ordena deshacer.

## Pruebas

`tests/test_seis_reglas.py`, con coordenadas y tipos que no son de ninguna empresa y el doble `fake_pf`; sorteadas donde hay geometría o red. No toca el lector
ni el DGS: no aplican las dos disposiciones. DIgSILENT, en las tareas marcadas.
