# Plan — Spec 078

Lee: `docs/constitution.md`, `specs/015-caso-base-verificado/spec.md`, `specs/057-oraculo-corrige-antes-de-digsilent/spec.md`.

| Parte | Cubre | Encaje |
| --- | --- | --- |
| Lectura única `estado_flujo` | RF-1 a RF-8 | `powerfactory_metadata.py`, que ya importan el guion y la web |
| Clasificación | RF-9 a RF-12 | `classify_convergence`, sobre esa lectura |
| Estado del «Caso base» | RF-13 a RF-15 | `estado_caso_base` y `tools/powerfactory_acceptance.py` |
| Volver a verificar | RF-16, RF-17 | `fusionar_caso_base` y `caso_base_verificado`, en `powerfactory_binding.py` |
| Línea y recuentos de la web | RF-18 a RF-24 | `_importar_dgs_fijados` y `pf_verificar_base`, en `web/services.py` |
| Interfaz | RF-25 a RF-27 | `CargasTab.tsx`, `App.tsx`, `types.ts` |
| Informe de texto | RF-28 | `_write_reports` |
| Grupos y dudas del plan | RF-29 a RF-35 | `asistente/plan.py`, con `grupos=` que pasa `web/services.py` |

Decisiones:

- Un estado propio para cada caso, no una marca al lado de `VERIFICADO`. Descartado dejar `VERIFICADO` con un aviso: es lo que
  ya había, y por eso el operador leía «verificado» con el flujo en ✗.
- `NO_CONVERGE` y `SIN_DATO_DE_FLUJO` calibran. Bloquear contradiría 015:RF-38 a RF-40, y el usuario lo rechazó: «nada iba a
  bloquear el flujo». La puerta física sigue igual.
- `VERIFICADO` implica flujo convergido, sin excepción. Una verificación sin flujo (015:RF-39) sale `SIN_DATO_DE_FLUJO` del
  guion, y la web la completa con lo registrado en el vínculo. El guion no ve el vínculo: lo fusiona quien lo graba.
- El guion sigue terminando con 0 si el flujo no converge: `powerfactory_runtime_pass` es de la ejecución. La línea de la web
  mira las dos cosas. Cambiarlo haría creer `BLOQUEADO_PERSISTENCIA` y rompería `_validar_informe_actual`.
- Los recuentos: `sin_aceptar` aparte. Contarlos como `failed` diría que la importación falló, y hay proyecto y vínculo.
- Prefijo `IMPORTADO_SIN_CONVERGENCIA`, no `NO_CONVERGE`, que ya significa «el oráculo no dejó importar».
- `SIN_DATO` es un valor nuevo de `convergence_classification`; solo lo lee `tools/accept_three_sources.py`, que lo copia.
- Grupos aparte del vocabulario (`resolver(..., grupos=)`). `asistente_vocabulario` entra en la huella `vocabulario_hash` del
  corpus (070:RF-72) y en `sinteticos`: añadir una clave movería ambas. Tampoco se toca `tareas.py`: la prueba sellada depende de
  las descripciones y plantillas de `TAREAS_HASTA_069` (069:RF-13).
- Solo `flujo` admite grupo: es la tarea cuya plantilla «importa {alimentadores} en digsilent» recibe estas órdenes, y su ruta
  ya acepta el nombre de un grupo. No hace falta tarea nueva.

Pruebas: `tests/test_senales_de_convergencia.py`, con los JSON de los dos casos reconstruidos sin datos reales ni empresa, y
`tests/test_plan_grupos_al_importar.py`. Lo de DIgSILENT y el navegador, en sus tareas.
