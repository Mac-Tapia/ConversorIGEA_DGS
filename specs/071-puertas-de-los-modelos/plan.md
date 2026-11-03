# Plan — Spec 071

Lee: `docs/constitution.md` y `specs/071-puertas-de-los-modelos/spec.md`.

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Redes del modelo y puertas | `digital_twin/oraculo.py` | RF-1 a RF-4 |
| Monitor | `web/services.py` | RF-5 |
| Vigilancia | `web/app.py` | RF-6 |
| Turno de GPU | `tools/digital_twin_entrenar.py`, `tools/llm_destilar.py` | RF-7, RF-8 |

Las puertas se separan en `fallos_de_comparacion`, pura, para probarlas sin GPU. Se reutilizan `red_de` y `turno_gpu`.
