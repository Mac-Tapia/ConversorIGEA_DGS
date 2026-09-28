# Validación de integración web — 2026-09-27

## Resultado

La interfaz única React 19 + FastAPI quedó operativa con las dos alternativas de
entrada que ofrecía la interfaz anterior: tripleta TXT y par MDB de red/catálogo.
La aceptación se ejecutó con archivos reales, no con el generador sintético, para
`NA203`, `NA205`, `PE104` y `CA101`.

Las dos rutas obtuvieron `PASS` en entrada, conversión DGS, completitud, asignación
`Name → Alimentador`, Grid adaptativa, exclusión de Trafomix, maniobras y SED. La
interfaz web real cargó, convirtió 4/4 alimentadores usando dos procesos y mostró la
tabla de cargas filtrada por `Alimentador` en Edge.

La compuerta propietaria también fue ejecutada posteriormente con dos entradas reales:
`AL209` desde `260924.mdb` e `IN111` desde la tripleta `260927_*.txt`. Ambos DGS se
importaron, activaron y convergieron en PowerFactory 2024 mediante una sola sesión API,
con un proyecto dedicado por alimentador para evitar la reindexación acumulativa.

## Entradas custodiadas

| Ruta | Archivo | SHA-256 |
|---|---|---|
| TXT | `RED_030826(1).txt` | `48e34f95e97a15a791d7ccc0f60c83aef1b0761a48e1c58f0cc96f0391f9f8c7` |
| TXT | `CARGA_030826(1).txt` | `5352f4b9c2f0e46508378f4e183831353f36f47c49d46fb0f272c841cc172b91` |
| TXT | `BD_Equipo_V261124 (1)(1).txt` | `5ba9ccb7554803c35035076ff1c74b1b73584b7128cc60f269bb72ed3c698028` |
| MDB | `260924.mdb` | `0107892da4ddd3b0a405efa2dbdca4cce41db64ff1ecd84a912c0171be8faba0` |
| MDB | `BASE JUL25 1.mdb` | `2420211cad6ab8c80352308e903934fa8df5aba45ef1cf2f2be01b350345eb97` |
| TXT | `260927_Carga.txt` | `055fb93b6591b4225d3cb43baffc17aa901206a79d3971320ac5151c6f297f4b` |
| TXT | `260927_Red.txt` | `0b20146261f78b2275f72fa244f92568f579de5ef3e4b2fbb953fc69aa972050` |
| TXT | `260927_Equipo.txt` | `5ba9ccb7554803c35035076ff1c74b1b73584b7128cc60f269bb72ed3c698028` |

TXT y MDB no son la misma instantánea. Por ello cada vía se valida contra su propia
entrada; no se exige igualdad artificial de conteos entre ambas.

## Evidencia por alimentador

| Ruta | Alimentador | SECTION | Cargas origen | ElmLne | ElmLod | SED | Puentes | Trafomix excluidos | Escala u/m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TXT | NA203 | 630 | 120 | 251 | 79 | 79 | 379 | 41 | 2,0785 |
| TXT | NA205 | 810 | 156 | 323 | 106 | 106 | 487 | 50 | 2,0751 |
| TXT | PE104 | 677 | 125 | 263 | 90 | 89 | 414 | 35 | 2,0788 |
| TXT | CA101 | 1261 | 247 | 486 | 169 | 169 | 775 | 78 | 2,0763 |
| MDB | NA203 | 631 | 120 | 252 | 79 | 79 | 379 | 41 | 2,0785 |
| MDB | NA205 | 825 | 159 | 329 | 108 | 108 | 496 | 51 | 2,0751 |
| MDB | PE104 | 219 | 40 | 90 | 29 | 29 | 129 | 11 | 2,0812 |
| MDB | CA101 | 1279 | 251 | 492 | 171 | 171 | 787 | 80 | 2,0763 |

La reconciliación no compara erróneamente `ElmLne == SECTION`: cada SECTION termina
como línea o como puente eléctrico según las reglas aprobadas. Análogamente, las
cargas Trafomix `M…` excluidas se conservan en la auditoría y no se modelan como SED.
En los ocho casos, la lista `completitud.fallos` quedó vacía.

## Comando reproducible

```powershell
python tools\verify_reference_feeders.py `
  --red "D:\ruta\RED.txt" `
  --loads "D:\ruta\CARGA.txt" `
  --equipment "D:\ruta\BD_Equipo.txt" `
  --mdb "D:\ruta\red.mdb" `
  --equipment-mdb "D:\ruta\equipos.mdb" `
  --feeders NA203 NA205 PE104 CA101 `
  --output output\real_validation
```

Resultado observado: `Reference validation: PASS`. Los artefactos locales no
versionados quedan en:

- `output/real_validation/input_alternatives_validation.json`;
- `output/real_validation/txt/reference_feeders_validation.json`;
- `output/real_validation/mdb/reference_feeders_validation.json`;
- una carpeta DGS por alimentador y alternativa.

## Recorrido real de la interfaz

La prueba `tests/test_web_api_real_inputs.py` asigna las rutas mediante la misma API
usada por React, comprueba tamaño y SHA-256, carga el inventario, convierte los cuatro
alimentadores con `workers=2`, exige 4 OK/0 fallos y consulta cargas de cada
alimentador. Resultado: **2 pasaron** (TXT y MDB).

La prueba `frontend/e2e/real-inputs.spec.ts` abre Edge contra FastAPI, verifica el
selector de alternativa, los nombres reales, el texto de escala adaptativa y la tabla
`Name / Grid / Alimentador / SED`. Resultado: **2 pasaron** (TXT y MDB).

Los ensayos sintéticos permanecen como regresiones unitarias reproducibles, pero no
se utilizan como evidencia de esta aceptación real.

## Aceptación real en PowerFactory 2024

Se ejecutó `tools/powerfactory_acceptance.py --batch-file ...` una sola vez. El proceso
obtuvo una sola instancia `Application` y procesó los alimentadores secuencialmente.
No se ejecutaron dos importaciones concurrentes porque PowerFactory mantiene estado
global de proyecto, caso de estudio y escenario.

| Ruta | Alimentador | Proyecto PF | Nodos | Líneas | Cargas | Asignación `Alimentador` | ComLdf | IsLdfValid | Resultado |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| MDB | AL209 | `IGEA_DGS_CONVERTER_AL209` | 402/402 | 252/252 | 74/74 | 75/75, 0 ambiguos | 0 | `true` | PASS |
| TXT | IN111 | `IGEA_DGS_CONVERTER_IN111` | 1549/1549 | 754/754 | 288/288 | 289/289, 0 ambiguos | 0 | `true` | PASS |

Los informes auditables son:

- `output/real_single_project/mdb/AL209_powerfactory_acceptance_batch.json`;
- `output/real_single_project/mdb/AL209_powerfactory_acceptance_batch.txt`;
- `output/real_single_project/txt/IN111_powerfactory_acceptance_batch.json`;
- `output/real_single_project/txt/IN111_powerfactory_acceptance_batch.txt`.

### Actualización masiva real de cargas — 2026-09-28

También se probó el flujo nuevo de Excel/CSV sobre los mismos proyectos dedicados. El
plan se reconstruyó directamente desde `260924.mdb` para AL209 y desde
`260927_Red/Carga/Equipo.txt` para IN111. Se actualizó temporalmente una carga real por
alimentador (`SE20731` y `SE40071`) en +0,1 %, se releyeron P/Q/FP, se exigió
convergencia y finalmente se restauró el snapshot original con una segunda
convergencia.

| Alimentador | Fuente | Proyecto | Aplicación | Restauración | ComLdf final |
|---|---|---|---|---|---|
| AL209 | MDB | `IGEA_DGS_CONVERTER_AL209` | PASS | exacta | `return_code=0`, `ldf_valid=true` |
| IN111 | TXT | `IGEA_DGS_CONVERTER_IN111` | PASS | exacta | `return_code=0`, `ldf_valid=true` |

Resultado ejecutado: `3 passed in 32.11s` en
`tests/test_load_batch_real_powerfactory.py`. Los dos alimentadores compartieron una
sola sesión API. La prueba detectó además que PowerFactory 2024 representa la Data
Extension `p:alimentador` como `STRING_VEC`; el motor acepta el valor unitario
`['AL209']`/`['IN111']`, pero sigue rechazando vectores vacíos o ambiguos.

La ruta React implementa el mismo contrato: plantilla consolidada, carga Excel/CSV,
vista previa filtrable, dry-run obligatorio, aplicación asíncrona serializada en el
carril PowerFactory y enlaces a los siete artefactos de auditoría. La regla de cuatro
ceros incluye `kW`, `kvar`, `kVA` y `FP`: significa **sin datos**; solo
`accion=poner_cero` escribe una carga nula.

Después de la regresión completa se repitió la compuerta real: `3 passed in 41.97s`.
La regresión dio `643 passed, 127 skipped` en Python; React dio `7 passed`, typecheck y
build correctos, y Playwright `2 passed, 2 skipped` (las dos pruebas de entradas reales
son opt-in). Ruff quedó `NOT RUN` porque el entorno no tiene instalado ese módulo.

El lote real duró aproximadamente 58 minutos: unos 24 minutos hasta completar AL209
(incluido el arranque inicial) y unos 34 minutos adicionales para IN111. El cuello de
botella medido es `ComImport`, no la conversión TXT/MDB→DGS. La mejora elimina el
segundo arranque de PowerFactory, pero no promete un porcentaje interno inexistente:
el registro muestra sesión, alimentador, fase y, desde la siguiente ejecución, duración
por alimentador y total.

Se descartó importar repetidamente sobre un único proyecto acumulativo: una sonda
AL107 pequeña superó 19 minutos al reindexar el proyecto que ya contenía AL209. La
arquitectura final conserva una sola sesión/carril API y usa un proyecto dedicado por
alimentador; así cada aceptación es aislada y permanece disponible para inspección.

## Compuertas y límites

- `PASS` solo se emite después de una comprobación ejecutada.
- `SKIP_MISSING_INPUT` nunca se interpreta como aprobación.
- `NOT_RUN_POWERFACTORY` no demuestra importación ni convergencia en DIgSILENT; no se
  usa para AL209 ni IN111 porque ambos conservan JSON/TXT reales de aceptación.
- Los `PASS` de AL209 e IN111 no se extrapolan a otros alimentadores: cada DGS debe
  superar su propia importación, activación, asignación y convergencia.

## Fundamento técnico

La separación por alimentador y la ejecución paralela sin estado mutable compartido
siguen el enfoque de descomposición de modelos eléctricos de gran escala descrito en
la [tesis doctoral de la Université de Liège](https://orbi.uliege.be/handle/2268/183353)
y la evaluación multinúcleo del artículo indexado
[Parallel computing of power flow for complex distribution network with DGs](https://doi.org/10.3233/JIFS-169350).
La escala y legibilidad del unifilar se apoyan en la
[tesis de maestría sobre visualización de redes eléctricas](https://repositorio.comillas.edu/jspui/handle/11531/99738)
y en el artículo indexado sobre
[layout automático de diagramas unifilares](https://doi.org/10.1016/j.epsr.2003.12.005).

La importación dirigida a proyectos PowerFactory y la integración GIS/DGS siguen el
flujo documentado por DIgSILENT en su
[ejemplo de importación DGS](https://faq.digsilent.de/en/faq-reader-powerfactory/how-can-i-import-dynamic-models-via-dgs.html)
y en el documento técnico
[GIS Integration in PowerFactory](https://www.digsilent.de/index.php/en/paper-reader-pf-en/gis-integration.html?_cmsscb=1&cid=17686&file=files%2Fcontent%2FWhitepaper%2FPF%2FPF_Paper_GIS-Integration.pdf).
