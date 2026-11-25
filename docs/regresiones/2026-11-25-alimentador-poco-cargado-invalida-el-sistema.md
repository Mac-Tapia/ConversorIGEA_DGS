# Un alimentador poco cargado dejaba sin validar la calibración de todo el sistema

## Síntoma

La aceptación de una versión con un sistema entero de 17 alimentadores terminó en «parcial»: los 17 quedaron en
`FALLO_VALIDACION_NATIVA` o `FALLO_VALIDACION_NATIVA_EN_EL_PROYECTO`, y el Registro daba para todos el mismo motivo,
«…: la red da 410 kVAR frente a 350 medidos: no falta ningún banco.», que era un aviso informativo de otro alimentador.

## Causa

Dos alimentadores medían 18,8 y 55,2 kW en su cabecera, sin ninguna fija, frente a varios MVA instalados: el factor común
de sus escaladas (0,0033 y 0,0164) quedaba por debajo de 0,05 y 015:RF-71 lo daba por inválido, como si las fijas se
comieran la cabecera (el caso para el que se escribió). Un alimentador inválido invalida el proyecto (015:RF-49), y los
otros quince cayeron con él. El motivo vacío del fallo (no es de consumo, `aviso_consumo_fisico` no dice nada) dejaba
que el Registro tomara el primer aviso de la lista común del proyecto.

## Comprobación permanente

`escaladas_casi_cero` calcula también el factor que daría la cabecera sola, sin restar las fijas: si también es anormal,
el alimentador está poco cargado en ese instante y se avisa con esa causa sin invalidar; solo invalida cuando son las
fijas las que hunden el factor. El motivo de un alimentador con un fallo de validación que no es de consumo es el aviso
de ese fallo, y los que no valen por otro del proyecto dicen por cuáles; nunca el primer aviso común (081:RF-19).

## Prueba

- `tests/test_ajuste_cabecera.py::test_015_rf71_alimentador_poco_cargado_sin_fijas_se_avisa_sin_invalidar`
- `tests/test_ajuste_proyecto_guion.py::test_081_rf19_el_motivo_es_el_fallo_de_su_alimentador_y_no_el_primer_aviso_comun`
- La corrida en DIgSILENT: la aceptación de la versión que lo corrige (spec 100, T4).
