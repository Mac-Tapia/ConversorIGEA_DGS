# Un banco trifásico en una barra de dos fases dejó sin flujo toda la calibración

## Síntoma
«Error in load flow data» en todos los alimentadores de la calibración de un sistema: «The no. of phases (3) of the element must be less than or equal to the no. of phases (2)».

## Causa
Dos caminos, y el segundo se halló al comprobar este en el código:

1. La calibración crea sus bancos en la troncal sin mirar las fases de la barra. Lo corrige la rama `fix/acopladores-con-fases` (054:RF-10), sin integrar cuando se escribe esto.
2. Un banco que viene de la fuente: el DGS deduce las fases de cada barra de sus tramos y SED, sin mirar los bancos, y lo escribía tal cual.

## Comprobación permanente
`comprobacion_fases.reconstruir_bancos`, en `aplicar_reglas`, da al banco de la fuente las fases de su barra y anota `FASE_RECONSTRUIDA`, en cualquier fuente. `ubicar_nuevo` es el contrato para lo nuevo: a la barra compatible más cercana y, sin ninguna, con las fases de la suya (081:RF-8, RF-9). Lo usan la obra de un banco, los bancos de la calibración y las cargas nuevas, que sin barra compatible quedan con las fases de la suya en vez de no crearse (081:RF-64 a RF-69). El guion corrige también un banco ya importado.

## Prueba
- `tests/test_comprobacion_fases.py::test_el_banco_de_la_fuente_toma_las_fases_de_su_barra`
- `tests/test_comprobacion_fases.py::test_elemento_nuevo_a_la_barra_compatible_mas_cercana`
- `tests/test_comprobacion_fases.py::test_obra_de_banco_va_a_una_barra_que_lo_lleve`
- `tests/test_resolver_convergencia.py::test_banco_trifasico_en_barra_de_dos_fases`
- `tests/test_fases_de_lo_nuevo.py::test_bancos_de_la_calibracion_sin_barras_trifasicas`
- `tests/test_fases_de_lo_nuevo.py::test_sin_barra_trifasica_la_sed_nueva_se_crea_con_las_fases_de_la_barra`
