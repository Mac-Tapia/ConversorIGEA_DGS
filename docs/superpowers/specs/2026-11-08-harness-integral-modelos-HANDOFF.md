# HARNESS-20261108 — entrega al integrador comercial

Responsable: sesión «Mejorar precisión y recall del LLM», Codex /root.
Worktree: `D:/converter/ConversorIGEA_DGS/.worktrees/harness-integral-20261108`.
Rama: `codex/harness-integral-20261108`.
Base: `5617251012f39193297e19b299d8a179a8fe1f61`.
El commit de entrega es el HEAD de esta rama; su hash se comunica en ACTIVE.md
después de crear el commit, sin referencia circular en este documento.

## Implementación entregada

- Métricas de clasificación/entidades y recuperación con soporte, abstención,
  gold parcial explícito y ausencia de denominador representada por null.
- Configuración, particiones, matriz de suites, referencias y políticas selladas.
- Ejecución pareada con casos fallidos/cancelados conservados; puertas por
  clase/tipo/familia, contrastes por grupos y dirección mayor/menor es mejor.
- CLI de sellado, replay, auditoría de órdenes, importación auxiliar GitHub y
  verificación; publicación atómica con relectura y recuperación del informe.
- Puente ejecutable mediante `TrainingStage` al `TrainingCoordinator` y
  `RegistroModelo` existentes: evaluar, conservar evidencia, registrar rechazado
  o aprobado y activar solo mediante decisión explícita y todas las guardas.
- Destino de registro absoluto, slot/familia, etapa, recursos, activo esperado y
  artefactos vinculados al sello previo a la prueba. Revalidación de candidato y
  referencia; recibo heredado exacto de esta campaña, no solo hash de política.

La única modificación de un archivo preexistente de esta rama será el catálogo
que genera el hook090 normal, autorizado expresamente por el integrador. No se
modifican main, la rama comercial, modelos, corpus, entornos o módulos compartidos.

## Evidencia y comandos

La [evidencia JSON](2026-11-08-harness-integral-modelos-evidencia.json) registra
intérprete, resultados, revisión, archivos y huellas. Los logs propios quedan en
`output/harness_integral_20261108/`. Consultar la evidencia antes de atribuir un
resultado al corte final; este documento no convierte contratos en campañas.

```powershell
# Pruebas propias sin paquetes opcionales ni motores:
py -3.12 -I -B -c "import sys,unittest; sys.path[:0]=['src','tests']; r=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('tests',pattern='test_harness_*.py')); sys.exit(not r.wasSuccessful())"

# CLI aislada:
py -3.12 -I -B tools/evaluar_harness.py --help

# Lint sobre superficies propias:
.venv/Scripts/ruff.exe check src/convertersmartgrid/evaluacion_harness tools/evaluar_harness.py tests/test_harness_*.py
```

La regresión enfocada añade los cuatro módulos de pruebas existentes de registro,
coordinación, evaluación y aceptación, y la comprobación de citas de specs033.
El comando exacto y la salida se conservan en la evidencia; no se ejecutó la suite
completa del producto, GPU, PowerFactory ni instalación/build.

## Resolución de la revisión provisional de producción

I1: eliminado el formato escalar de `por_grupo`. Ahora exige
`por_grupo[group_id][metrica]`; una clave ausente o escalar bloquea el contraste.
El control de prueba contrapone MAE que mejora y RMSE que empeora, con negativa
del escalar y control mapeado, usando la misma función en ejecución e integridad.

I2, trazabilidad: los seis módulos de prueba citan requisitos aplicables:
043:RF-1/5/7/9/13, 044:RF-1/2/3/5/6/8 y 047:RF-4 según su contenido. No son citas
para cerrar tareas nativas ni evidencia de corpus humano. La parte de **capas e
inventario permanece a cargo del root integrador**, que reservó pyproject y los
documentos generales. No se añaden excepciones ni se apagan guardas.

El snapshot provisional revisó siete módulos antes de existir el puente. Esta
entrega contiene **ocho** módulos de paquete. Altas que debe clasificar el
integrador en `tool.convertersmartgrid.capas.modulos`, propuesta `aplicacion`
(misma capa de los evaluadores/coordinador/registro consumidos):

```toml
"convertersmartgrid.evaluacion_harness" = "aplicacion"
"convertersmartgrid.evaluacion_harness.adaptadores" = "aplicacion"
"convertersmartgrid.evaluacion_harness.cli" = "aplicacion"
"convertersmartgrid.evaluacion_harness.contratos" = "aplicacion"
"convertersmartgrid.evaluacion_harness.ejecucion" = "aplicacion"
"convertersmartgrid.evaluacion_harness.integracion" = "aplicacion"
"convertersmartgrid.evaluacion_harness.metricas" = "aplicacion"
"convertersmartgrid.evaluacion_harness.publicacion" = "aplicacion"
```

Actualizar también `CODIGO_FUENTE.md` y el catálogo desde el corte combinado según
las reglas existentes. Revalidar capas, inventario, trazabilidad y regresión
afectada sobre ese corte. El árbol de main permanece sin estas altas hasta que
el integrador incorpore la rama; no se atribuye al harness el estado previo de
la campaña G2 de producción.

## Activación operativa y aceptación pendientes

El puente está implementado y probado con clases reales del registro/coordinador
en temporales, usando proveedores y decisiones dobles. Los productores/jobs
reservados deberán incorporar la etapa con su configuración, evaluadores del
dominio y admisión de un escritor por slot. El factory usa el coordinador vigente;
no se modifica el bloqueo GPU ni se proporciona un fallback que eluda su turno.
El turno nativo y la admisión de la aplicación siguen siendo obligatorios.

La aceptación eléctrica, científica y una ganancia de precision/recall requieren
campañas independientes con datos/etiquetas revisados, soporte y política sellada,
modelos reales, backend efectivo, recarga y evidencia nativa cuando corresponda.
No se entrenó ni promovió un modelo del usuario. Las pruebas que simulan metadata
`real` y activación utilizan exclusivamente registros efímeros y son contratos.

## Procedencia metodológica

El diseño conserva las fuentes web verificadas: [maestría de König](https://publications.ait.ac.at/de/publications/automated-evaluation-and-parameter-optimisation-for-retrieval-aug/),
[doctorado de Stiasny](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/),
[RAGAs, EACL 2024](https://aclanthology.org/2024.eacl-demo.16/), PowerFlowNet y JMLR.
El anexo de fuentes fija commits/licencias de GitHub. Estas referencias justifican
el protocolo comparativo y la separación de componentes, sin certificar nuestros
resultados ni establecer límites normativos.
