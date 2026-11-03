# Un temporal con un fichero abierto por otro proceso hacía fallar el guardado de un espacio

## Síntoma
La suite completa del 2026-11-03 cayó dos veces, en pruebas distintas (`tests/test_pide_web.py::test_decisiones_del_operador` y
`tests/test_universal_source_scope.py::test_source_scope_api_exposes_options_and_selection_invalidates_run`), con
`PermissionError: [WinError 32] … owner.json` al guardar un espacio de la web. Solas pasaban siempre: el fallo solo salía con la máquina
cargada.

## Causa
`write_json_atomic` publica el `workspace.json` por `staging_publicacion`, y al salir `temporal_administrado` retira su carpeta temporal.
En Windows otro proceso, como el antivirus o el indexador, puede tener abierto un instante el `owner.json` de esa carpeta. `_retirar_propio`
reintentaba una sola vez tras quitar el atributo de solo lectura y, al seguir abierto, el error subía y hacía fallar un guardado que ya
estaba publicado.

## Comprobación permanente
Un `WinError 32` al retirar el temporal se reintenta con esperas crecientes, hasta unos dos segundos. Si sigue abierto, el temporal queda
«terminado» con su manifiesto y lo retira `reconciliar_temporales`; el trabajo no falla, porque lo publicado ya está en su sitio. Otros
errores de permisos siguen subiendo.

## Prueba
- `tests/test_runtime_paths.py::test_el_borrado_reintenta_un_fichero_en_uso`
- `tests/test_runtime_paths.py::test_un_temporal_bloqueado_no_hace_fallar_lo_publicado`
