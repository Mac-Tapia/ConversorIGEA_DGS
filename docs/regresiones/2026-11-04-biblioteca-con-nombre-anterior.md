# Ninguna variante con regulador se pudo medir, y parecía que el regulador no servía

## Síntoma
«No está el tipo VR32_10kV_50A (TypVoltreg) en la biblioteca del proyecto CSG_Biblioteca_tipos», aunque crear los tipos decía «7 ya estaban». En los registros: «regulador …: máxima no cumple», sin tensiones.

## Causa
Comprobada en el código: la búsqueda del proyecto acepta su nombre anterior, pero los tipos se registraban con el nombre real del proyecto y la obra los buscaba con el nombre pedido.

## Comprobación permanente
Los tipos del proyecto biblioteca llevan el nombre con que se pidieron (042:RF-46).

## Prueba
- `tests/test_obras_pf_guion_042.py::test_el_tipo_del_proyecto_biblioteca_se_encuentra_por_el_nombre_pedido`
