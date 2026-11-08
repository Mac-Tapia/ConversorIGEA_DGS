# Tareas 092

- [x] T1. `check_powerfactory_source_run` valida la reconstrucción con el disco al leer un proyecto importado, con
      sus pruebas. (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_powerfactory_binding.py` en verde.
- [x] T2. [DIgSILENT] El «Caso base» de Pisco verificado desde la web, sin «SOURCE_RUN_MISMATCH». (RF-1)
      Hecho cuando: el trabajo «Verificar el Caso base» de `20261103-013907_CSG_SISTEMA_PISCO` termina VERIFICADO.
      Hecho el 2026-11-08 sobre e1168c28 con el Pisco vigente, `20261107-043049_CSG_TXT_SISTEMA_PISCO` (espacio
      35ff5dab8b2b46a6; el de 2026-11-03 ya no tiene sus DGS en disco): trabajo f22b06a2046c VERIFICADO, las seis
      comprobaciones en verde y sin «SOURCE_RUN_MISMATCH». Antes hubo que corregir dos fallos de los rótulos de barra
      de SET (95063cea, e1168c28: el vínculo y el DGS unido).
