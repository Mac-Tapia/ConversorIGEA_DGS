# Tareas 095

Lee: `specs/095-escaladas-proporcionales-a-su-kva/spec.md` y `plan.md`.

- [x] T1. Pendiente 0 desde las fijas y desde el perfil; dispersión alrededor de la media. (RF-1, RF-2, RF-3)
      Hecho cuando: `pytest -q tests/test_reparto_probabilistico.py tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T2. [DIgSILENT] AL209 recalibrado: cada escalada con la misma utilización esperada de su kVA. (RF-1)
      Hecho cuando: el informe de la recalibración da pendiente 0 y ninguna escalada pequeña con utilización muy por
      debajo de la media.
      Hecho el 2026-11-06: recalibración de `20261106-124315_CSG_TXT_AL209` (informe ajuste_cabecera_aplicacion_ee3df7a035a1):
      pendiente 0, dispersión 0,44 de 5 fijas; las 69 escaladas entre 9,6 y 11,6 % de su kVA, mínima 0,50 kW (5 kVA),
      P y Q cuadradas (+0,09 %, +0,38 %), validación nativa VÁLIDA.
