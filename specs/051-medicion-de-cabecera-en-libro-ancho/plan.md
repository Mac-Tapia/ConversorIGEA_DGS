# Plan — Spec 051

1. `src/convertersmartgrid/cabecera_ancha.py`: lectura del libro ancho (cabecera con fecha y códigos,
   magnitud por la hoja, instante de dos columnas, «CAPACITIVA», código repetido), de las
   máximas mensuales (MW o kW, sin hora ni reactiva) y escritura en el formato que ya lee
   `demanda_medida` (un libro por año con una hoja por código y el de medidores). Reutiliza
   `_abrir`, `_filas`, `clave_codigo`, `normalizar` y `numero` de `demanda_medida`.
2. `tools/cabecera_ancha.py`: la herramienta, con `NOMBRE_EN_DIGSILENT=CODIGO`.
3. Real: los perfiles 2024 de la sede Amazonas–Cajamarca de Electro Oriente para NJA202, y
   las máximas de Iquitos para R205 (R5); calibración por la web en un espacio propio, sin
   mezclar con Electro Dunas.
