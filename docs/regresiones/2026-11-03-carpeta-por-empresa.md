# Proyectos de una empresa en la carpeta de DIgSILENT de otra

## Síntoma
Una fuente de otra distribuidora se importó en la carpeta de la empresa del perfil, mezclada con sus proyectos. Los proyectos que ya quedaron así se conservan donde están, por orden del usuario.

## Causa
`empresa_ajena` daba `None` si la fuente no dice su empresa (un TXT, a veces una .mdb) o si el perfil no declara `codigo_empresa`, y entonces se iba a la carpeta del perfil. Un nombre de empresa no admitido por DIgSILENT daba error.

## Comprobación permanente
`carpeta_pf.decidir_carpeta` es la única regla: la empresa de la fuente o la que indicó el operador en el espacio; la suya, a la carpeta del perfil; otra, a la de su nombre, siempre válido. Sin saberla no se bloquea: el supuesto o la neutra, dicho en el plan, al importar y en el resultado. Lo importado se lee de su vínculo con `carpeta_de(ws, proyecto)`. Verlo en DIgSILENT y el campo en el navegador son la T16 de la spec 081.

## Prueba
- `tests/test_carpeta_por_empresa.py::test_regla_la_del_perfil_y_otra_empresa`
- `tests/test_carpeta_por_empresa.py::test_sin_saber_la_empresa_no_bloquea`
- `tests/test_carpeta_por_empresa.py::test_lo_ya_importado_se_lee_de_su_vinculo`
- `tests/test_carpeta_por_empresa.py::test_ningun_plan_sale_sin_la_carpeta_de_su_vinculo`
- `tests/test_carpeta_por_empresa.py::test_crea_su_carpeta_y_no_mueve_nada`
