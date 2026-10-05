# Aceptación de producción: MDB, TXT y VNR-GIS

## Objetivo y criterio de evidencia

Este procedimiento ejecuta cada fuente en un espacio independiente, conserva sus
originales con SHA-256 y solo acredita PowerFactory cuando el sidecar, el DGS y la
ejecución activa comparten `source_run_id`, modo y fingerprint. Un PDF regulatorio
no es un paquete GIS. Si falta el paquete VNR completo, el resultado correcto es
`BLOCKED_MISSING_OFFICIAL_PACKAGE`.

La separación responde al principio de trazabilidad de modelos CIM/GIS estudiado por
McMorran (tesis doctoral, <https://doi.org/10.48730/bvtk-xz74>) y al modelado de redes
de distribución desde GIS de Özdamar (tesis de maestría,
<https://open.metu.edu.tr/handle/11511/44535>). La verificación de topología y
parámetros sigue la evidencia indexada de IET GTD
(<https://doi.org/10.1049/gtd2.12634>) y la integración GIS-simulador descrita por
Valverde et al. (<https://doi.org/10.1049/iet-gtd.2016.1560>).

## Precondiciones

- Python 3.12 y dependencias del proyecto instaladas.
- Para MDB: driver Microsoft Access de 64 bits y `pyodbc`.
- Para PowerFactory real: PowerFactory 2024/API Python 3.12 disponible.
- Un paquete VNR-GIS contiene capas de red, fuente, cargas y catálogo eléctrico; no
  se acepta una resolución PDF ni un archivo fabricado para completar evidencia.

## Ejecución

```powershell
python tools\accept_three_sources.py `
  --audit-dir AUDIT\three_source_YYYYMMDD_HHMMSS `
  --feeder IN111 `
  --company "EMPRESA_EJEMPLO" `
  --period 2026 `
  --source-crs EPSG:32718 `
  --mdb "ruta\260924.mdb" `
  --txt-red "ruta\260927_Red.txt" `
  --txt-loads "ruta\260927_Carga.txt" `
  --txt-equipment "ruta\260927_Equipo.txt" `
  --vnr-package "ruta\paquete_vnr_gis.zip" `
  --powerfactory
```

Omita `--powerfactory` para validar hasta DGS. Omita `--vnr-package` cuando no exista:
el resumen lo marcará bloqueado sin reutilizar el MDB o los TXT.

`--feeder` se puede repetir para uno o varios alimentadores; `--all-feeders` procesa
todo el inventario. La reconstrucción está activa por defecto. Sus controles son
`--minimum-catalog-confidence`, `--topology-snap-tolerance`,
`--provisional-nominal-voltage-kv`, `--no-catalog-matches` y
`--no-engineering-assumptions`. `--no-reconstruct` existe solo para comparar el
flujo estricto anterior y deja bloqueado cualquier alimentador incompleto.

## Lectura de resultados

`acceptance_summary.json` registra por modo:

- archivos originales, tamaños y SHA-256;
- `source_run_id` y fingerprint exclusivos;
- cantidad de alimentadores y selección exacta;
- DGS generados y sus SHA-256;
- hashes de originales antes/después y `originals_unchanged=true`;
- informe de reconstrucción, selección, decisiones, coincidencias de catálogo,
  supuestos y SHA-256 canónico;
- nivel de evidencia PowerFactory, proyecto, relectura efectiva, `ComLdf` y rollback.

Las clases finales son `CONVERGED_ORIGINAL`, `CONVERGED_RECONSTRUCTED`,
`CONVERGED_WITH_ASSUMPTIONS`, `NEEDS_OPERATOR_REVIEW`, `NOT_CONVERGED` y
`REJECTED_STALE_EVIDENCE`. Reducir, escalar o desconectar carga siempre produce
`NEEDS_OPERATOR_REVIEW`, aunque `ComLdf` converja.

Estados de éxito: `DGS_READY` o `POWERFACTORY_VERIFIED`. Estados como
`SKIP_MISSING_INPUT`, `SKIP_FEEDER_NOT_PRESENT`, `BLOCKED_FEEDER_NOT_READY` y
`BLOCKED_MISSING_OFFICIAL_PACKAGE` son límites de evidencia, no aprobaciones.

## Controles posteriores

1. Compruebe que los tres `source_run_id` sean distintos.
2. Abra cada manifiesto y confirme que solo contiene slots de su modo.
3. Compare el SHA-256 del DGS con su sidecar.
4. Para PowerFactory, exija `VERIFIED_BEFORE_MUTATION`, relectura del atributo
   `p:alimentador`, `ComLdf` válido y estado explícito de rollback.
5. Conserve toda la carpeta `AUDIT/three_source_*`; no copie resultados entre modos.

## Matriz de cumplimiento del diseño (secciones 2–14)

| Sección | Evidencia verificable |
|---|---|
| 2. Invariantes | `test_three_source_acceptance.py`: runs separados; `validate_summary`: slots y hashes sin mezcla. |
| 3. Arquitectura | Adaptadores TXT/MDB/VNR → dataset canónico → copia reconstruida → DGS; manifiestos por workspace. |
| 4. Empresa/periodo | Campos web y argumentos `--company`/`--period`; prueba genérica `UTILITY_X`. |
| 5. Topología | `test_reconstruction_topology.py` y aceptación genérica con nodos ausentes. |
| 6. Equipos/catálogos | `test_catalog_resolution.py`; jerarquía original/fabricante/global/supuesto con procedencia. |
| 7. SED/cargas | Suites `test_sed_loads.py` y `test_sed_create.py`; el lote de cargas se acepta por separado. |
| 8. Convergencia | `test_reconstruction_powerfactory.py`; relectura, `ComLdf`, intervenciones y rollback. |
| 9. Estados | Contrato UI/servicio: original, reconstruido, supuesto y revisión. |
| 10. Web | `test_web_reconstruction_ui_contract.py` y build Vite de producción. |
| 11. Carga masiva | Plan de lotes; no se acredita hasta completar sus pruebas y aceptación real. |
| 12. API | Diagnóstico/reconstrucción y sidecars ligados a `source_run_id` y hash. |
| 13. Pruebas | Suite, build y aceptación controlada distinguen fake, DGS y PowerFactory real. |
| 14. Producción | Cero fallos, originales intactos y evidencia real por fuente; una fuente ausente queda bloqueada. |

## Base científica y límites

La reconstrucción no convierte un dato supuesto en original. La trazabilidad de
intercambio de modelos se apoya en la tesis doctoral de McMorran; la construcción
GIS/flujo en la tesis de maestría de Özdamar; y la integración GIS-simulador en
Valverde et al. Para redes con datos incompletos se conserva explícitamente la
incertidumbre, coherente con la tesis doctoral sobre datos limitados de Strathclyde
(<https://stax.strath.ac.uk/concern/theses/1r66j1947>) y con los métodos indexados
de estimación conjunta de topología/parámetros
(<https://ieeexplore.ieee.org/document/9781319/>). Ninguna de esas fuentes justifica
inventar un paquete VNR-GIS oficial inexistente: ese caso permanece bloqueado.
