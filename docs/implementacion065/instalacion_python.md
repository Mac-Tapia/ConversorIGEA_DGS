# Instalación Python — M5/M10 de la spec 065

El manifiesto de producto sigue siendo `requirements.txt`. El archivo
`constraints-python312-win.txt` limita las versiones de su cierre transitivo para
CPython 3.12 de 64 bits en Windows AMD64; no introduce otra selección de paquetes.
El entorno fuente del 2 de noviembre de 2026 usa CPython **3.12.10**, Windows 11
build 26200 y pip 26.2.1. Otros sistemas, arquitecturas y versiones menores de Python
no están verificados por esta evidencia. Los marcadores del constraints hacen que
sus pins solo se apliquen al destino declarado.

## Generación y contrato

```powershell
python -B tools/fijar_entorno.py --requirements requirements.txt --salida constraints-python312-win.txt
```

Ejecutar con el entorno fuente verificado. La herramienta parte de requirements y
de las dependencias del editable local declaradas en `pyproject.toml`, recorre
`Requires-Dist`, evalúa marcadores y acumula extras hasta cerrar el grafo. Por
ejemplo, incluye las dependencias de `uvicorn[standard]` que corresponden a Windows,
y excluye `uvloop` cuando su marcador no corresponde a ese sistema.

No exporta `pip freeze` del entorno completo: Torch/CUDA, adaptadores ML, drivers
optativos y sus dependencias ajenas al cierre principal quedan fuera. Rechaza
paquetes ausentes, versiones incompatibles, versiones locales y dependencias con
URL directa o `direct_url.json`: convertir un wheel local o una instalación VCS en
un simple `nombre==versión` perdería su procedencia. El editable del producto se
resuelve desde el candidato actual y no desde un checkout instalado diferente.

La salida es determinista: orden canónico y sin timestamps, rutas privadas ni datos
de la distribuidora. Las pruebas `tests/test_fijar_entorno.py` cubren cierre,
marcadores, extras transitivos y activados posteriormente, faltantes, versiones,
fuentes ambiguas y determinismo (065:RF-15, RF-24).

## Instalación

```powershell
py -3.12 -m venv <raiz-externa>/venv-limpio
<raiz-externa>/venv-limpio/Scripts/python.exe -B -m pip install -r requirements.txt -c constraints-python312-win.txt
<raiz-externa>/venv-limpio/Scripts/python.exe -B -m pip check
```

Verificar `python --version` y la arquitectura antes de instalar. La instalación
principal conserva `-e .`; setuptools crea metadatos editables durante el build.
Para una verificación sin escrituras en el repositorio se usa una **copia externa
del código actual**, incluidos archivos nuevos de producto, con manifiesto SHA256.
Se excluyen originales, datos reales, output, entornos, worktrees, node_modules y
Git. Los metadatos editables quedan en esa copia. No se instala en el entorno
compartido ni se modifican herramientas globales. Caché pip y TEMP/TMP se fijan a
raíces externas para esta ejecución.

Los extras opcionales se instalan con el mismo constraints, por ejemplo
`pip install -e '.[web]' -c constraints-python312-win.txt`; el lock principal no
fija dependencias que solamente pertenezcan a otros extras. `requirements-drivers.txt`
y `[ml]` mantienen su alcance separado. PowerFactory y los drivers ODBC del sistema
no los suministra pip. El diagnóstico consulta imports y enumera drivers sin abrir
bases de datos ni reclamar aceptación eléctrica.

## Alcance de la evidencia

Este es un **lock de versiones obtenido de metadatos instalados**, no un lock de
artefactos con hashes ni una garantía de builds binariamente idénticos. El backend
de build aislado (`setuptools`, `wheel`) y pip no están fijados por los constraints
de runtime; la ejecución conserva sus registros. Una futura garantía de artefactos
requiere seleccionar y archivar wheels con hashes y fijar también el build.
`pip check` comprueba compatibilidad de dependencias instaladas; no es un escaneo
CVE ni certifica la corrección de las bibliotecas.

Los registros, informe pip con URLs/hashes de descargas, inventario y manifiesto
del candidato se conservan bajo el directorio externo
`implementacion065/instalacion` de la auditoría del 2026-11-02. Su entrega distingue
instalación principal, comprobación por capacidades, smoke TXT y regresión final.
La suite completa y la aceptación del candidato integrado corresponden al
integrador de M10. No se sustituye esa verificación con pruebas de esta herramienta.

La comprobación externa del 2026-11-02 instaló 64 distribuciones del cierre y el
editable del producto con pip 25.0.1, sin Torch/CUDA. `pip check`, CLI `--help`,
enumeración ODBC sin conectar y regeneración idéntica del constraints terminaron
con código 0. Las diez capacidades del diagnóstico declararon sus imports y
drivers disponibles. Pasaron 25 pruebas enfocadas en el entorno nuevo (16 del
generador y nueve del runtime). El smoke TXT convirtió un alimentador con perfil
explícito, sin fallos, conservando los SHA256 de las tres entradas. Estas pruebas
corresponden a la copia identificada por su manifiesto, previa a la estabilización
final del árbol integrado; no acreditan regresión completa, HTTP, ML ni ejecución
en PowerFactory.

## Justificación y fuentes consultadas en la web

La selección explícita de dependencias, la procedencia y el alcance de la ejecución
aplican principios de reproducibilidad; las siguientes fuentes fundamentan la
decisión y no certifican este producto:

- Lagnöhed, F. (2024). *Integration of Reproducibility Verification with Diffoscope
  in GNU Make*. Tesis de maestría, Linköping University. Distingue la verificación
  de artefactos del simple éxito de una compilación y fundamenta separar los pins
  de metadatos de la identidad binaria.
  [Repositorio universitario](https://www.diva-portal.org/smash/get/diva2:1877032/FULLTEXT01.pdf).
- Dolstra, E. (2006). *The Purely Functional Software Deployment Model*. Tesis
  doctoral, Universiteit Utrecht. Fundamenta describir el cierre de dependencias
  y las entradas de construcción para controlar despliegues reproducibles.
  [Texto del autor](https://edolstra.github.io/pubs/phd-thesis.pdf).
- Krafczyk, M. S., Shi, A., Bhaskar, A., Marinov, D., y Stodden, V. (2021).
  *Learning from reproducing computational results: introducing three principles
  and the Reproduction Package*. Philosophical Transactions of the Royal Society A,
  379(2197), 20200069. Fundamenta transparencia, facilidad de reejecución y
  determinismo. La ficha institucional enlaza su registro Scopus.
  [DOI](https://doi.org/10.1098/rsta.2020.0069),
  [ficha institucional e indexación](https://experts.illinois.edu/en/publications/learning-from-reproducing-computational-results-introducing-three/).

El comportamiento técnico se contrasta con las fuentes primarias:
[constraints de pip](https://pip.pypa.io/en/stable/user_guide/#constraints-files),
[instalaciones repetibles](https://pip.pypa.io/en/stable/topics/repeatable-installs/),
[hashes de artefactos](https://pip.pypa.io/en/stable/topics/secure-installs/),
[marcadores de packaging](https://packaging.pypa.io/en/stable/markers.html) y
[contrato de pip check](https://pip.pypa.io/en/stable/cli/pip_check/).
