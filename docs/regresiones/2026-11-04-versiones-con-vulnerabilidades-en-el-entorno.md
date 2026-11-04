# Las versiones fijadas del entorno traían vulnerabilidades conocidas

## Síntoma
`pip-audit` sobre el núcleo, con las versiones de `constraints-python312-win.txt`, dio el 2026-11-04 48 avisos en 3 paquetes: Pillow 12.3.0 (40, varios de escritura fuera del búfer), pypdf 6.21.2 (7, bucles infinitos y consumo de memoria) y certifi 2026.7.22 (una raíz retirada). pypdf lee el PDF que entrega un solicitante, que el programa no controla.

## Causa
Comprobada con la herramienta. `tools/fijar_entorno.py` fija versiones y lo dice en su cabecera: «no contiene hashes de wheels ni escaneo CVE». Nada miraba los avisos publicados después de fijarlas.

## Comprobación permanente
`requirements-nucleo.lock` usa las versiones corregidas (`config/entrega.json`, `candidato.versiones_de_seguridad`), y la prueba exige que el lock solo se aparte de lo fijado en lo declarado allí. Cada candidato se audita antes de entregarlo (T23). Sin red o con avisos nuevos, la auditoría es de esa fecha: hay que repetirla en cada candidato.

## Prueba
- `tests/test_instalacion_programa.py::test_el_lock_sigue_las_versiones_fijadas`
- `tests/test_instalacion_programa.py::test_limites_con_seguridad`
