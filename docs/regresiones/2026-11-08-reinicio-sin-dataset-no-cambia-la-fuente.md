# Reabrir la sesión decía que las entradas habían cambiado

Spec 034 RF-20: selección vigente, carga de la sesión y rechazo de fuentes ajenas.

## Síntoma

Tras reabrir un espacio con fuente intacta, una operación que exige la red en
memoria responde `SOURCE_SELECTION_CHANGED` aunque el token actual coincide
con el manifiesto. El diagnóstico correcto es `SOURCE_RUN_MISMATCH`: hay que
volver a cargar la red en esa sesión.

## Causa

El reinicio conserva manifiesto y selección, pero no dataset ni identidad de
carga en memoria. La guarda comparaba el token del manifiesto con el token de
carga ausente antes de alcanzar su rama específica de reinicio. La diferencia
con `None` se interpretaba como una modificación de las entradas.

## Comprobación permanente

La comparación contra el token de carga solo se realiza cuando existe una
identidad de carga. Siempre se comparan modalidad y selección actuales contra
el manifiesto; un cambio real sigue devolviendo `SOURCE_SELECTION_CHANGED`.
Una carga ausente con selección intacta alcanza la rama existente que exige
recargar. Un manifiesto inválido o una identidad ajena siguen bloqueados.
No se crea dataset, token, aceptación ni permiso nativo al reabrir la sesión.

## Prueba

- `tests/test_source_adapters.py::test_reinicio_sin_dataset_pide_cargar_sin_inventar_cambio_de_seleccion`
- `tests/test_source_adapters.py::test_reinicio_guardas_de_una_red_cargada_siguen_vigentes`
- `tests/test_source_adapters.py::test_reinicio_con_seleccion_realmente_distinta_sigue_bloqueado`
- `tests/test_source_adapters.py::test_reinicio_con_manifiesto_invalido_nunca_habilita_una_fuente`

Los ocho casos usan una carga canónica de TXT sintéticos y la reapertura real
de su Workspace. Se conserva el rojo de reinicio y los siete controles de
rechazo en la evidencia externa `p25_g2_binding_fixtures_20261108`. Las pruebas
de CPU no ejecutan PowerFactory ni sustituyen la aceptación nativa/comercial.

La [maestría de Eriksson y Mosaddegh](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf),
el [doctorado de Strandberg](https://www.es.mdu.se/publications/6347-Automated_System_Level_Software_Testing_of_Industrial_Networked_Embedded_Systems)
y el [artículo indexado de Shahin, Ali Babar y Zhu en IEEE Access](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/)
fundamentan conservar feedback y contexto de las comprobaciones. Son fuentes
primarias consultadas en la web; no certifican este cambio ni su dominio físico.
