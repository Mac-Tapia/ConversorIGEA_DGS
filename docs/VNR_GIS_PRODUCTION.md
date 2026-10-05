# VNR-GIS — operación y evidencia de producción

## Alcance

`vnr_etl` implementa un flujo auditable y fail-closed:

```text
fuente oficial/archivo/SQLite -> inventario y huellas -> modelo canónico
-> CRS/snapping/topología -> cobertura eléctrica -> perfil objetivo verificado
-> DGS transaccional + manifiesto -> importación PowerFactory -> ComLdf
```

CLI y API Web usan `vnr_etl.application.VnrApplicationService`; ninguna interfaz
puede evitar las puertas A-F. `EXPORT_READY` acredita A-F. Solo una aceptación
real con importación, inventario, conectividad y `ComLdf` permite acreditar G-H.

## Instalación

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r vnr_requirements.txt
.\.venv\Scripts\python.exe -m vnr_etl doctor
```

Los drivers de Oracle/PostgreSQL/ODBC, RAR y la recuperación PDF/OpenCV son
capacidades opcionales documentadas en `vnr_requirements_optional.txt`. Su ausencia
deshabilita solo el adaptador correspondiente.

## Uso CLI

```powershell
# Descubrimiento oficial y catálogo aditivo
.\.venv\Scripts\python.exe -m vnr_etl search-vnr --latest
.\.venv\Scripts\python.exe -m vnr_etl list-vnr
.\.venv\Scripts\python.exe -m vnr_etl download-vnr PUBLICATION_ID

# Inspección segura: un SQL se analiza, nunca se ejecuta
.\.venv\Scripts\python.exe -m vnr_etl inspect-sql backup.sql

# Inventario y conversión; un CRS ausente se bloquea
.\.venv\Scripts\python.exe -m vnr_etl inventory fuente.gpkg
.\.venv\Scripts\python.exe -m vnr_etl convert fuente.gpkg `
  --company EMPRESA --period latest_available --format json --output output\vnr

# Validación/exportación con el perfil DGS versionado
.\.venv\Scripts\python.exe -m vnr_etl validate output\vnr\canonical.json
.\.venv\Scripts\python.exe -m vnr_etl export-dgs output\vnr\canonical.json
```

La conversión no inventa cargas, fuente/slack, tensión, fases ni parámetros R/X.
Si la fuente pública solo contiene geometría, la ejecución queda en L3 y exige una
fuente empresarial/catálogo aprobado para superar L4.

## API Web y seguridad

```powershell
# Loopback, sin autenticación remota
.\.venv\Scripts\python.exe -m vnr_etl web --host 127.0.0.1 --port 8776

# Exposición de red: token obligatorio
$env:VNR_WEB_TOKEN = '<secreto-aleatorio>'
.\.venv\Scripts\python.exe -m vnr_etl web --host 0.0.0.0 --port 8776
```

Fuera de loopback se exige `X-Session-Token`. Las cargas usan identificadores
opacos, límite de tamaño, nombre saneado y SHA-256. ZIP rechaza traversal, rutas
absolutas, enlaces simbólicos y expansión excesiva. SQLite abre en `mode=ro` y las
conexiones se cierran explícitamente. Los artefactos solo se sirven por ID de job
y dentro de la raíz autorizada.

Rutas principales: `/api/health`, `/api/doctor`, `/api/discovery/refresh`,
`/api/vnr/download`, `/api/sources/upload`, `/api/sources/inspect`,
`/api/database/test`, `/api/database/discover`, `/api/schema/resolve`,
`/api/topology/build`, `/api/validate`, `/api/reconcile`, `/api/export/{target}`,
`/api/jobs/{id}` y `/api/artifacts/{job_id}/{index}`.

## Evidencia ejecutada el 2026-10-05

- Suite focal del módulo: `55 passed, 1 warning`; integración VNR con la interfaz
  principal: `85 passed, 1 warning`. La regresión completa se registra en la entrega.
- Ruff no está instalado en el entorno actual; por tanto, lint queda `NOT_RUN` y no
  se presenta como verificado.
- PowerFactory 2024 real: importación de un proyecto nuevo, conteos esperados =
  reales (2 nodos, 1 línea, 1 carga y 1 fuente), conectividad PASS, coordenadas
  PASS y `ComLdf` convergente con retorno 0.
- Informe: `AUDIT/vnr_acceptance/powerfactory_acceptance_verified.json`.
- El caso de aceptación es sintético y verifica el motor/exportador; no sustituye
  la aceptación de una publicación VNRGIS empresarial concreta.
- Descubrimiento oficial final: la página GRT 2026 produjo tres PDF regulatorios
  del proyecto VNR al 31-12-2025, no un paquete empresarial VNR-GIS completo. La
  conversión real de Electro Dunas permanece `BLOCKED_MISSING_OFFICIAL_PACKAGE`
  hasta obtener y custodiar ese paquete original.

## Fundamento científico y técnico

La arquitectura canónica y validada sigue la tesis doctoral de McMorran sobre CIM,
perfiles y conversión de formatos propietarios
(DOI [10.48730/bvtk-xz74](https://doi.org/10.48730/bvtk-xz74)). La unión de GIS
operacional con análisis eléctrico se apoya en la tesis doctoral de Lu
(DOI [10.48730/40hb-xf18](https://doi.org/10.48730/40hb-xf18)). La validación
automatizada de datos de redes de distribución está respaldada por el artículo
ISPRS (DOI [10.5194/isprs-archives-XLVIII-4-W18-2025-95-2026](https://doi.org/10.5194/isprs-archives-XLVIII-4-W18-2025-95-2026)), y el uso de GIS abierto para
identificación topológica por Liu et al. (DOI
[10.1016/j.ijepes.2024.110395](https://doi.org/10.1016/j.ijepes.2024.110395)).
La procedencia reproducible se alinea con el trabajo de provenance para flujos
geoespaciales (DOI [10.1016/j.cageo.2018.05.001](https://doi.org/10.1016/j.cageo.2018.05.001)).
