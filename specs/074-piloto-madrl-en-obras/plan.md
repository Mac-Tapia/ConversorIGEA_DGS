# Plan — Spec 074

Lee: `docs/constitution.md` y `specs/074-piloto-madrl-en-obras/spec.md`.

Se reutilizan el grafo y el barrido radial del oráculo (`digital_twin/oraculo.py`), el búfer de episodios y `pymoo`.

| Parte nueva | Cubre | Encaje |
| --- | --- | --- |
| Entorno, máscara y Lagrange | RF-1 a RF-4 | `madrl_obras.py`, sin dependencias nuevas |
| Controles y puerta | RF-5, RF-6 | `madrl_obras.py`, `tools/madrl_obras.py` |
| Fidelidad contra DIgSILENT | RF-7 | Compara cada red con lo medido en su episodio |
| Captura de `ntnum` y largo | RF-8 | `tools/digital_twin_snapshot_pf.py` |
| Entrenamiento | RF-9, RF-10 | Pendiente; entorno aparte para TorchRL |

Decisiones:

- La corriente sale de sumar aguas abajo, no de la caída entre la impedancia: el oráculo sube la z de los tramos cortos.
- `VERSION_GRAFO` no cambia aquí: lo decide quien integra los modelos, porque invalidaría los episodios con que se entrenan.
