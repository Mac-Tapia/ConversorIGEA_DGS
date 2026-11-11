# Plan — Spec 103

## Módulos

- `src/convertersmartgrid/powerfactory_env.py` (RF-1 a RF-4): `instalaciones()` devuelve cada PowerFactory con su
  versión y sus carpetas de API; `elegir_api(instalacion, interpretes)` aplica RF-2; `pf_python_dir()` y
  `python_for_pf()` pasan a usarlas, con `PF_PYTHON` y la elección guardada (RF-3) delante. Se quita `DEFAULT_PF_PYTHON`.
  El registro de Windows se lee con `winreg`, sin fallar si no hay clave.
- Elección del operador (RF-3): un fichero en la carpeta de datos de la máquina (`runtime_paths`), y la ruta
  `GET/POST /api/powerfactory/instalaciones` en `web/app.py` y `web/services.py`; la píldora de PowerFactory de la web
  abre la lista.
- Mensajes (RF-4): `web/doctor.py`, `tools/check_pf_license.py`, `tools/powerfactory_acceptance.py`.
- Compatibilidad de los guiones (RF-5): una prueba que, para cada guion de `tools/*_pf.py`, comprueba con ruff
  (`target-version = py39`) que no usa sintaxis posterior a 3.9 y que carga sin librerías de terceros salvo `numpy`;
  con un intérprete 3.9 presente (los del instalador), además los importa con él.
- Instalador (RF-6): `config/entrega.json` y `tools/construir_candidato.py` añaden los Python embebidos oficiales de
  python.org con su SHA-256 y `numpy`; `instalador/ConverterSmartGrid.iss` los copia; RF-2 los busca en la carpeta del
  programa.

## Decisiones

- Elegir por intérprete disponible, no por la carpeta más alta (descartado: exigir siempre el Python más nuevo de la API,
  que deja fuera a 2025 con el Python 3.12 del programa).
- Python embebido de python.org en el instalador (descartado: pedir al operador que instale Python, decisión del usuario).

## Pruebas

`tests/test_powerfactory_versiones.py` con árboles de carpetas simulados en `tmp_path` (2021, 2022, 2024, 2025, con y
sin service pack, en otra unidad) e intérpretes simulados; cada prueba cita `103:RF-n`.
