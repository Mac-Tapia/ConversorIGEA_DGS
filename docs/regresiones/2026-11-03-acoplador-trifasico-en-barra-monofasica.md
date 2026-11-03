# Un acoplador de tres fases en una barra monofásica impedía todo el flujo

## Síntoma
Al importar un sistema, DIgSILENT no calculaba ningún alimentador: «The no. of phases (3) of the element must be less than or equal to the no. of phases (1)». Un solo elemento dejaba sin flujo a todo el proyecto.

## Causa
Al fundir un puente entre una barra trifásica y una monofásica, el acoplador salía siempre con `nphase=3`. Corregido en el escritor del DGS (054:RF-3), que le da las fases comunes de sus dos barras.

## Comprobación permanente
`comprobacion_fases.comprobar` mira toda la clase (acoplador, banco, carga, transformador, tramo, regulador) frente a cada barra suya, antes de importar y sobre el proyecto de DIgSILENT. Si un proyecto ya importado lo trae, el guion le da las fases de su barra y vuelve a medir (081:RF-26). La confirmación real es la T10 de la spec 081.

## Prueba
- `tests/test_fases_reales.py::test_un_acoplador_lleva_las_fases_de_sus_dos_barras`
- `tests/test_comprobacion_fases.py::test_toda_clase_con_mas_fases_que_su_barra`
- `tests/test_resolver_convergencia.py::test_caso_base_con_causa_reconstruible_llega_convergido`
