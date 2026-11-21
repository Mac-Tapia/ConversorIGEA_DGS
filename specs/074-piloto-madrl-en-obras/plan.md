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
| Puerta en no vistos y confirmación | RF-6, RF-10, RF-13, RF-14 | `madrl_puerta.py` (separación sellada, decisión, orden), `tools/madrl_puerta.py`; los pesos, de `madrl_entrenar.py --modelo-salida` |

Decisiones:

- La corriente sale de sumar aguas abajo, no de la caída entre la impedancia: el oráculo sube la z de los tramos cortos.
- La separación se sella por el contenido de cada red y por sus cabeceras, no por el nombre del fichero: una copia de la red
  de entrenamiento no es una red no vista. Los límites y costos son los del manifiesto del modelo.
- Solo la política GATv2 se aplica en redes no vistas: MaskablePPO aprende el espacio de acciones de su red.
- La confirmación va por la web (`/obras`, `/pf/obras/simular`, `/pf/obras/aplicar`) y solo a un proyecto «PRUEBA…».
- `VERSION_GRAFO` no cambia aquí: lo decide quien integra los modelos, porque invalidaría los episodios con que se entrenan.
