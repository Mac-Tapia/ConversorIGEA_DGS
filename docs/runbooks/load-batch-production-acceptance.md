# Aceptación productiva de cargas en lote

Este procedimiento valida un lote universal sin asociarlo a una empresa. Cada libro,
proyecto y alimentador queda identificado por hash y orden. El plan conserva la carga
base: las actualizaciones se escriben en un escenario y las SED nuevas en una
variación; cada alimentador se relee y ejecuta `ComLdf`. Si falla, se eliminan solo sus
contenedores y se registra `ROLLED_BACK` o `ROLLBACK_FAILED`.

## 1. Contrato reproducible sin PowerFactory

```powershell
python tools/accept_load_batch.py --dry-run --audit-dir AUDIT/load-generic `
  --project UTILITY_PROJECT --feeder F-A --feeder F-B `
  --update-file cargas.csv --fail-feeder F-B
```

`SIMULATED_CONTRACT_ONLY` comprueba orden, hashes, antes/después y rollback, pero **no**
demuestra escritura ni convergencia real en PowerFactory.

## 2. Aceptación real controlada

1. En la web, cargue una fuente original y convierta/cargue el proyecto.
2. En **Cargas en DIgSILENT**, elija el proyecto exacto y uno o varios alimentadores.
3. Suba el libro, revise identidad, enrutamiento, valores antes/después, escenario y
   variación. Guarde el `load_batch_plan.json`; no cambie proyecto, fuente ni libro.
4. Ejecute:

```powershell
python tools/accept_load_batch.py --real-plan output/web/ID/plans/TOKEN/load_batch_plan.json `
  --audit-dir AUDIT/load-real
```

Solo `PASS_REAL_POWERFACTORY` con `REAL_ENGINE_REREAD`, resultados por alimentador y
`ComLdf.converged=true` permite afirmar aceptación real. Código 3 significa
`BLOCKED_POWERFACTORY_UNAVAILABLE`. No cierre una sesión interactiva del operador para
forzar la prueba; reintente con una instancia controlada.

## Evidencia y recuperación

- `acceptance_summary.json`: clasificación y hashes.
- `powerfactory_result.json`: antes/después, creados, `ComLdf` y rollback.
- `*.evidence.jsonl`: registro durable después de cada alimentador.
- `APPLIED`: escenario/variación conservados; `ROLLED_BACK`: restauración completa;
  `ROLLBACK_FAILED`: intervención manual obligatoria antes de continuar.

## Fundamento científico

La separación GIS/modelo eléctrico y la validación mediante flujo de carga siguen el
enfoque de Özdamar (tesis de maestría, METU) y Valverde et al. (IET GTD). La
interoperabilidad y trazabilidad del modelo siguen la tesis doctoral de McMorran sobre
CIM. La reconstrucción con datos incompletos se clasifica y conserva como procedencia,
en vez de ocultarse, de acuerdo con la investigación doctoral de Strathclyde sobre
redes con datos limitados y los trabajos IEEE/IET sobre estimación conjunta de
topología y parámetros. Enlaces y alcance completo: el runbook de aceptación de tres
fuentes.
