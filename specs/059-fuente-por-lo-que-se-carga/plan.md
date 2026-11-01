# Plan — Spec 059

1. `identify.py`: `fuente_de(path)` dice si un fichero es TXT de CYMDIST (y cuál), base Access
   (cabecera «Standard Jet DB» / «Standard ACE DB») o paquete VNR-GIS (`validate_vnr_package_file`).
2. `web/workspace.py`: `input_mode` nulo por defecto (RF-1); al cargar, la fuente sale de las
   entradas (RF-2); `missing_inputs` pide la fuente si no hay (RF-1).
3. `web/app.py`: cada casilla y la zona de los TXT comprueban con `fuente_de` que el fichero sea de
   su entrada; el de otra fuente no se asigna y se dice dónde va (RF-3, RF-4).
4. `web/source_runs.py`: sin fuente, error que pide cargarla (RF-7).
5. Frontend: las tres entradas separadas de siempre; `InputMode | null`, así sin fuente ninguna
   aparece marcada (RF-5); clave anterior del navegador migrada (RF-6).
6. Pruebas en `tests/test_fuente_por_lo_que_se_carga.py`; la web, en el navegador real.

Alternativa descartada: dejar `txt` por defecto y solo recuperar el espacio. Volvería a pasar con
cualquier espacio nuevo.
