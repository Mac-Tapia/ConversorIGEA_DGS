# Plan — Spec 053

1. `src/convertersmartgrid/catalog.py`: `deducir_conductor` (misma familia por relación de secciones,
   AAAC con su ficha universal, autoportante como el cable XLPE con la resistividad de su
   material, o pendiente) y `ampliar_catalogo` (añade sin tocar, temporal y reemplazo con
   reintentos, un solo escritor).
2. `src/convertersmartgrid/sources/vnr.py`: `ampliar_con_lo_que_falta` tras aplicar el catálogo; si añade,
   se vuelve a aplicar en la misma conversión. El libro del catálogo se cierra al leerlo.
3. Pruebas con un catálogo sintético de la forma del real; después, NJA202 y R205 de Electro
   Oriente por la web.
