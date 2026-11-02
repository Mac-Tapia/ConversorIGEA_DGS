# Verificación reproducible del candidato — M10

`tools/verificar_candidato.py` cubre el registro y la regresión de 065:RF-1,
065:RF-20, 065:RF-21 y 065:RF-24. Reutiliza `tools/trazabilidad_candidato.py`;
no modifica sus contratos, estados de specs ni casillas de tareas. Integrador:
root. Superficie del implementador: esta guía, la herramienta y
`tests/test_verificar_candidato.py`.

La evidencia de instalación reproducible, frontend/build y arranque aislado se
ejecuta y conserva por separado. Un resultado `regresion_aprobada` no cierra M10,
no certifica un flujo nativo de PowerFactory y no acredita calidad científica.

## Uso

La ayuda solo importa la biblioteca estándar y funciona incluso con `python -I -S`:

```powershell
python -B tools/verificar_candidato.py --help
```

Preparar, sin ejecutar pytest:

```powershell
python -B tools/verificar_candidato.py --output-dir <raiz-externa-de-evidencia>
```

Ejecutar una fase core explícita, con el Python 3.12 elegido para el candidato:

```powershell
python -B tools/verificar_candidato.py --python <python-3.12> `
  --output-dir <raiz-externa-de-evidencia> --ejecutar `
  --prueba tests/test_verificar_candidato.py `
  --prueba tests/test_trazabilidad_candidato.py
```

Sin `--prueba`, el objetivo es `tests`. Una fase core puede registrar `skip` o
`xfail`, conservándolos como exclusiones; no se anuncia como suite completa.
Para exigir la suite completa:

```powershell
python -B tools/verificar_candidato.py --python <python-3.12> `
  --output-dir <raiz-externa-de-evidencia> --ejecutar --suite-completa `
  --red <red.txt> --cargas <cargas.txt> --equipos <equipos.txt> `
  --mdb <red.mdb> --equipos-mdb <equipos.mdb> `
  --demanda-dir <carpeta-demanda> --vnr-bak <respaldo.bak> `
  --solicitud-pdf <solicitud.pdf> --solicitud-dir <carpeta-solicitudes>
```

Cada parámetro admite como alternativa su variable existente, sin descubrimiento
automático ni rutas corporativas predeterminadas:

| Parámetro | Variable | Tipo validado |
| --- | --- | --- |
| `--red` | `CSG_RED` | archivo |
| `--cargas` | `CSG_LOADS` | archivo |
| `--equipos` | `CSG_EQUIPMENT` | archivo |
| `--mdb` | `CSG_MDB` | archivo |
| `--equipos-mdb` | `CSG_EQUIPMENT_MDB` | archivo |
| `--demanda-dir` | `CSG_DEMANDA_DIR` | directorio |
| `--vnr-bak` | `CSG_VNR_BAK` | archivo |
| `--solicitud-pdf` | `CSG_SOLICITUD_PDF` | archivo |
| `--solicitud-dir` | `CSG_SOLICITUD_DIR` | directorio |

`--suite-completa` exige las nueve entradas, valida existencia y tipo antes de
crear salidas y rechaza `--prueba`. La presencia de los nueve paths no demuestra
que SQL Server, Access, OCR o las demás dependencias estén operativos: esos fallos
quedan en el proceso pytest y su evidencia. Las fuentes TXT, MDB y VNR siguen
siendo pruebas independientes; el runner no las combina en una conversión.

## Contrato de ejecución y evidencia

La salida debe estar fuera del checkout candidato, del principal y sus
worktrees, y fuera de los directorios de datos seleccionados. Cada invocación
crea un subdirectorio UTC/UUID nuevo. No borra ni reutiliza intentos previos.
`--basetemp` recibe un descendiente UUID que no existía: pytest puede limpiar su
propio basetemp, por eso nunca se le entrega una carpeta compartida o durable.

El comando es una lista de argumentos, sin shell:

```text
<python> -B -m pytest -q -rs -p no:cacheprovider
  --junitxml <ejecucion>/junit.xml --basetemp <ejecucion>/pytest_<uuid> <seleccion>
```

El proceso hijo usa el candidato como `cwd`, elimina variables `GIT_*`,
`PYTEST_*`, `PYTHONPATH` y `PYTHONHOME` heredadas y recibe
`PYTHONDONTWRITEBYTECODE=1`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` y
raíces externas de runtime, temporales y cachés. No vuelca el entorno completo
ni secretos. La selección de fuentes y sus rutas se conserva solo en la
evidencia externa local.

Archivos por ejecución:

| Artefacto | Contenido |
| --- | --- |
| `registro.json` | alcance, estado, revisión, comando por argumentos, errores, contadores/casos y pendientes |
| `source_inputs_before.json`, `source_inputs_after.json` | hashes SHA-256 por archivo del candidato canónico |
| `data_inputs_before.json`, `data_inputs_after.json` | inventario de las entradas seleccionadas antes/después |
| `runtime.json` | intérprete real, versión, plataforma y versiones de distribuciones instaladas |
| `stdout.log`, `stderr.log`, `junit.xml` | salidas originales del subprocess, sin reemplazar fallos |
| `manifiesto_ejecucion.json` | identidad del candidato, comando, revisión, SHA del JUnit y hashes anterior/posterior; solo con JUnit válido |
| `matriz/trazabilidad.json`, `.csv`, `manifest.json` | matriz generada por el helper canónico y hashes de su evidencia |

La preparación conserva registro, inventarios anteriores y matriz sin inventar
JUnit, runtime comprobado o ejecución. El estado `preparado` no es aprobación.
La selección del hash de código es exactamente `hash_candidato(Path)`, que
incluye archivos nuevos de las superficies declaradas. HEAD por sí solo no
identifica un árbol con cambios. Los hashes se capturan antes y después de
pytest y se comprueban nuevamente tras generar la matriz.

Por defecto el inventario de datos guarda tamaño y `mtime_ns` por archivo,
incluidos los descendientes de los dos directorios. Se identifica como
`metadata_no_criptografica`: no prueba igualdad de contenido si otro proceso
restaura tamaño y fechas. `--hash-datos` añade SHA-256 por streaming de todos
los archivos antes y después. Implica leer los bytes dos veces y puede ser
costoso para respaldos de varios GB; debe elegirse explícitamente. Ningún modo
es un snapshot físico ni impide que un tercero modifique y restaure entradas
entre las dos observaciones.

La herramienta devuelve código distinto de cero si falla pytest, falta o es
incoherente el JUnit, cambia el candidato, cambia el inventario de datos o la
matriz rechaza sus referencias. En modo completo también falla con cualquier
`skip` o `xfail`. El XML conserva los mensajes y distingue `pass`, `fail`,
`error`, `skip` y `xfail`; un XPASS no estricto no se distingue de pass en el
JUnit de pytest. Las aceptaciones eléctricas y científicas permanecen pendientes.
El sondeo de hashes no evita modificaciones restauradas entre observaciones;
el integrador debe fijar el candidato y detener las escrituras concurrentes
antes de la ejecución de cierre.

## Pruebas y alcance

`tests/test_verificar_candidato.py` prueba ayuda sin site-packages, preparación
sin ejecutar código, validaciones previas, JUnit positivo/negativo, omisiones,
preservación de intentos, inventario de datos y subprocess reales de pytest en
un candidato mínimo. Una de esas pruebas cambia deliberadamente un archivo
del candidato mínimo mientras pytest se ejecuta: el runner debe rechazarlo
aunque la prueba hija pase. Otras preservan fallos, skips y xfails reales. No
simulan motores nativos ni ejecutan SQL, entrenamiento o servidores.

La regresión completa del proyecto queda a cargo del integrador después de
fijar el candidato y las nueve rutas. No se ejecutó como parte de la entrega
de esta herramienta; el estado de la spec sigue siendo el declarado por root.

## Fundamento y fuentes verificadas en web (2026-11-02)

La tesis de maestría de [Jan Thomas (2017), RWTH Aachen](https://swc-rwth.de/theses/software-architecture-conformance-analysis-large-scale-industrial-case-study/)
compara conformidad estática y comportamiento observable. La tesis doctoral de
[Lakshitha de Silva (2014), University of St Andrews](https://research-repository.st-andrews.ac.uk/handle/10023/5220)
estudia el seguimiento de conformidad en ejecución. El artículo de revista de
[Li, Liang, Soliman y Avgeriou (2022), *Understanding software architecture erosion: A systematic mapping study*](https://doi.org/10.1002/smr.2423)
reúne evidencia sobre deriva, detección y sus límites. Sustentan conservar la
identidad del código y la evidencia de comportamiento; no validan este runner
ni sustituyen las aceptaciones del dominio.

El contrato operativo se apoya en la documentación oficial de
[JUnit y salida de pytest](https://docs.pytest.org/en/stable/how-to/output.html),
[temporales y basetemp de pytest](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
y [subprocess de Python 3.12](https://docs.python.org/3.12/library/subprocess.html).
Las versiones instaladas se conservan en `runtime.json`, sin inferirlas de la
documentación web de la versión estable.
