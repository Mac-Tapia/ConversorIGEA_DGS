# `input/` — catálogo de parámetros eléctricos

Aquí vive `catalogo_parametros.xlsx`, la tabla con los parámetros eléctricos de todos
los elementos que usan los alimentadores: conductores aéreos, cables subterráneos,
transformadores de SED, condensadores y reguladores.

No está versionado. Se deriva del export de la distribuidora y lleva sus códigos de
conductor y su kilometraje, así que se genera en cada instalación:

```bat
python tools\build_input_catalog.py --red RED.txt --cargas CARGA.txt --equipos BD_Equipo.txt
```

o desde la interfaz, con **«Parámetros → Generar catálogo y auditar»**.

## Para qué sirve

El catálogo de equipos que viene en el TXT es lo único que fija la impedancia de cada
tramo, y normalmente nadie lo contrasta con la ficha del conductor que de verdad está
colgado. Cuando una fila está mal, el error se propaga en silencio a todos los tramos
de ese tipo, en todos los alimentadores, y sale por el otro lado como una pérdida
técnica o una caída de tensión que nadie cuestiona porque «viene del sistema».

La tabla pone lado a lado lo que dice el modelo y lo que dice la ficha, con la
diferencia calculada y la fuente citada.

## Cómo se completa

1. Escriba el valor de la ficha de su proveedor en la columna `*_ficha_*`.
2. Ponga `ficha` en la columna `estado` de esa fila.
3. Cárguela con **«Aplicar catálogo corregido»** y vuelva a convertir.

Una fila marcada `por_confirmar` no corrige nada aunque tenga un número escrito: es la
salvaguarda que impide que un valor provisional entre en el modelo como si viniera de
fabricante.

La hoja `parametros_por_elemento` dice, para cada parámetro, **qué ficha hay que pedir
y qué estudio se estropea sin ella**. Es la lista de la compra para el departamento
técnico.

Detalle completo en [`docs/MANUAL_COMANDOS.md`](../docs/MANUAL_COMANDOS.md), § 7.bis.
