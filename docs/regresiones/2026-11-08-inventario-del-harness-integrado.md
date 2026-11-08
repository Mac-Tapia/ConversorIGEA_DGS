# Inventario del arnés al integrar su entrega

## Síntoma

La entrega del arnés incorporaba ocho módulos y una herramienta cuya clasificación
e inventario estaban reservados al integrador. Las tres guardas existentes de
capas, índice y catálogo fallaron en el corte combinado.

## Causa

La entrega aislada no incluía los cambios compartidos de pyproject e inventario.
Además, la fusión textual del catálogo generado conservó datos de ambos cortes.

## Comprobación permanente

Registrar cada responsabilidad por su contenido: métricas y contratos puros en
dominio; ejecución en aplicación; E/S y enlaces al registro en adaptadores; CLI
en presentación. Mantener la deuda existente sin excepciones nuevas y regenerar
el catálogo desde la combinación real. La recepción del código no acredita una
campaña ni permite promover un modelo sin sus guardas.

## Prueba

`tests/test_capas.py::test_inventario_real_y_deuda_sin_deriva`

`tests/test_inventario.py::test_el_indice_lista_cada_fichero`

`tests/test_arquitectura_generada.py::test_catalogo_al_dia`
