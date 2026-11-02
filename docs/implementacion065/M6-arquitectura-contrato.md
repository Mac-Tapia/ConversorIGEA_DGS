# M6: conformidad estática y contrato público

Responsable: implementador_arquitectura; integración: root. Rama
`codex/mejoras-auditoria-integral`, base `f5c9c89d`. Requisitos 065 RF-16 y RF-17;
avance de 002 T2/T10, sin cerrar la spec 002 ni su migración.

## Guarda de arquitectura

`tools/arquitectura.py` analiza cada Python de `src/`, incluidos paquetes,
subpaquetes, imports dentro de funciones y `TYPE_CHECKING`, sin importarlos.
La clasificación explícita está en `[tool.convertersmartgrid.capas.modulos]` de
`pyproject.toml`. Un fichero nuevo sin clasificación o una clasificación de un
fichero retirado falla. Se prohíben en dominio FastAPI, Tkinter, PowerFactory y
los drivers de base de datos enumerados en la guarda.

El análisis resuelve imports relativos y absolutos, accesos privados directos y
mediante alias de módulo, y aristas de componentes fuertemente conexas mediante
Tarjan. Cada arista cíclica tiene su identificador; una excepción de un ciclo no
autoriza otra arista entre los mismos componentes. Los imports dinámicos con
destinos literales reconocidos también entran; los destinos calculados y las
dependencias que solo aparecen en runtime requieren revisión adicional.

La medición inicial completa de M6 abarcó 207 módulos: 37 aristas de capa,
24 aristas cíclicas y 36 accesos privados. Son deuda pendiente, identificada en
`deuda_arquitectura.json`, y no resultados de conformidad. La tabla clasifica la
responsabilidad prevista; no mueve módulos ni presenta adaptadores como dominio
para ocultar imports. Las utilidades estándar `util`/`runtime_paths` y los datos
puros `sources.snapshot` se clasifican en dominio; el contrato de control previo
que combina modelos se clasifica en aplicación.

La guarda carece de opción para aceptar o regenerar excepciones. Cada violación
nueva falla, y cada excepción que ya no existe también falla hasta retirarla del
registro. Cambiar deliberadamente la política o añadir dispensas exige revisión
del integrador; un analizador no puede proteger su propia configuración de una
edición autorizada. La revisión debe comparar el diff de esta política y no
aprobar su crecimiento como un arreglo de pruebas.

Comprobación: `python -B tools/arquitectura.py --json` y
`python -B -m pytest -q tests/test_capas.py -p no:cacheprovider`.

## Contrato API y consumo de tipos

`web/api_contract.py` declara los sobres reales de trabajo, salud, opciones y
espacio de trabajo, incluidos entradas, inventario, auditoría de fuente, grupos,
vínculos, obras y demanda. Los envoltorios fijos rechazan campos sin contrato.
Los diagnósticos extensibles conservan sus claves JSON, y el resultado de un
trabajo y la relectura nativa admiten el contenido específico de cada operación.
Este contenido variable no sustituye los campos fijos de los sobres.

La API valida estos modelos mediante `response_model`; los campos opcionales
ausentes se conservan ausentes mediante `response_model_exclude_unset=True`.
La selección tipada incluye las admisiones de trabajos, su consulta/cancelación,
salud y las rutas de espacio asignadas por el integrador. Las otras respuestas
históricas, los tipos de resultados específicos y la migración completa de
`WorkspaceState` continúan pendientes de 002 T10.

`tools/generar_contrato_api.py` obtiene `create_app(...).openapi()` sobre un
almacén aislado sin arrancar el servidor ni sus motores. Invoca exclusivamente el
generador instalado por el lock de `frontend/`, ordena el esquema y añade su
SHA-256 completo al archivo `frontend/src/api/esquema.ts`. `--check` compara sin
reescribir. Los temporales usan la política externa de 065 y se retiran al acabar.
No se usa una instantánea OpenAPI escrita a mano.

Los tipos `Options`, `Health` y el sobre de `Job` de `frontend/src/types.ts` son
alias del contrato generado. El parámetro de tipo de `Job` conserva la salida
polimórfica existente según `kind`; el resto del trabajo deriva de OpenAPI.

Comprobación: `python -B tools/generar_contrato_api.py --check`,
`python -B -m pytest -q tests/test_contrato_api.py -p no:cacheprovider`, y
`npm run typecheck` desde `frontend/`. Regeneración deliberada:
`python -B tools/generar_contrato_api.py`, después de `npm ci` en `frontend/`.

## Dependencia y evidencia

Se verificó Node 24.15.0 y npm 11.12.1. `openapi-typescript` está fijado en 6.7.6,
con `undici` 6.29.1 limitado a su árbol mediante `overrides`. La documentación
oficial de 6.x confirma soporte de OpenAPI 3.0 y 3.1. La versión 7.13.0 introducía
el aviso de `minimatch` a través de Redocly; sustituir esa dependencia por su
major 11 rompía la API invocada por Redocly. La rama 6.7.6 sin el override también
tenía avisos de `undici` y su parser multipart. La combinación fijada se instaló,
generó tipos, superó typecheck y dio cero vulnerabilidades en la consulta npm.
Los intentos y avisos originales se conservaron; no se ejecutó `npm audit fix`.

Evidencia externa:
`D:/converter/auditorias/ConversorIGEA_DGS_20261102/implementacion065/arquitectura/`.
Las pruebas negativas cubren capas arbitrarias, ciclos nuevos, privados directos
y por alias, driver prohibido, dispensas retiradas y deriva deliberada del
contrato. La regresión integrada, instalación y aceptación eléctrica/científica
son puertas distintas, a cargo de M10 y de las specs de dominio respectivas.

## Fundamento consultado en la web el 2026-11-02

- Thomas, J. (2017). *Software Architecture Conformance Analysis – A Large-Scale
  Industrial Case Study*. Tesis de maestría, RWTH Aachen. Estudia comprobación
  estática y de comportamiento; justifica medir deriva y declarar el alcance de
  cada técnica. [Registro institucional](https://swc-rwth.de/theses/software-architecture-conformance-analysis-large-scale-industrial-case-study/).
- de Silva, L. R. (2014). *Towards controlling software architecture erosion
  through runtime conformance monitoring*. Tesis doctoral, University of
  St Andrews. Fundamenta mantener las comprobaciones dinámicas separadas de las
  estáticas. [Repositorio institucional](https://research-repository.st-andrews.ac.uk/handle/10023/5220).
- Li, R., Liang, P., Soliman, M., y Avgeriou, P. (2022). Understanding software
  architecture erosion: A systematic mapping study. *Journal of Software:
  Evolution and Process, 34*(3), e2423. Revisión de 73 estudios sobre causas,
  consecuencias y contramedidas. [DOI](https://doi.org/10.1002/smr.2423),
  [registro primario](https://research.rug.nl/en/publications/understanding-software-architecture-erosion-a-systematic-mapping-/).
- [FastAPI: modelos de respuesta](https://fastapi.tiangolo.com/tutorial/response-model/)
  y [openapi-typescript 6.x](https://openapi-ts.dev/6.x/introduction): contratos
  tipados, validación y generación. Son documentación técnica, no evidencia de
  aceptación eléctrica ni evaluación científica del producto.

La literatura respalda la metodología de conformidad y control de deriva; las
pruebas y artefactos locales son la evidencia de esta implementación concreta.
