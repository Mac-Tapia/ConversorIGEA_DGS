# VNR-GIS — operación y evidencia de producción

## Alcance

`vnr_etl` implementa un flujo auditable que reconstruye lo que falta en vez de negarse:

```text
fuente oficial/archivo/SQLite -> inventario y huellas -> modelo canónico
-> reconstrucción (alimentadores, fuentes, tensión, fases, longitudes, cargas, CRS)
-> catálogo de parámetros para los conductores -> motor igea_dgs
-> DGS transaccional + manifiesto + informe de reconstrucción -> PowerFactory -> ComLdf
```

CLI y API Web usan `vnr_etl.application.VnrApplicationService`. Las puertas A–F se
evalúan siempre y se informan. Impiden exportar solo la procedencia (A), el mapeo y el
perfil de destino verificado (E) y el round-trip (F): no son datos de la red. Lo que
falta para B (CRS), C (topología) o D (eléctrico) se reconstruye (spec 001, RF-17).
`EXPORT_READY` acredita A–F con los datos originales; `EXPORT_RECONSTRUCTED`, un DGS
válido con datos reconstruidos, que detalla `<red>_reconstruccion.json`. Solo una
aceptación real con importación, inventario, conectividad y `ComLdf` acredita G–H.

## Instalación

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-drivers.txt
.\.venv\Scripts\python.exe -m vnr_etl doctor
```

Los drivers de Oracle, PostgreSQL, SQLAlchemy, RAR y la recuperación PDF/OpenCV van en
`requirements-drivers.txt`, aparte del resto, para que uno que no se descargue no
impida instalar lo demás. La ausencia de uno deshabilita solo su adaptador; `doctor`
dice cuáles quedaron operativos. ODBC (`pyodbc`) va en `requirements.txt`, porque la
vía Access del conversor lo necesita.

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

Al exportar, un dato ausente no detiene el proceso: se reconstruye y queda anotado con
su valor original, la regla, el nivel de evidencia y la confianza. Los conductores se
completan primero con el catálogo de parámetros (el del modelo y
`input/catalogo_parametros.xlsx`), después por atributos compatibles, después por
derivación física y, en último lugar, con un perfil provisional; lo que el conductor sí
trae se conserva. Un CRS geográfico se reproyecta a su zona UTM; uno desconocido da un
DGS sin georreferenciación, con las longitudes del modelo. No se crean cargas: una
carga sin red ni coordenadas queda fuera, y el informe lo dice.

## API Web y seguridad

Las rutas de VNR forman parte de la API web única (`igea-dgs-web`), con su misma cola
de trabajos; el lanzador `vnr-etl-web` y su token de sesión se retiraron (spec 001,
RF-11). `vnr-etl web` abre esa misma web.

```powershell
.\.venv\Scripts\igea-dgs-web.exe            # o: python -m vnr_etl web
```

Las cargas usan identificadores
opacos, límite de tamaño, nombre saneado y SHA-256. ZIP rechaza traversal, rutas
absolutas, enlaces simbólicos y expansión excesiva. SQLite abre en `mode=ro` y las
conexiones se cierran explícitamente. Los artefactos solo se sirven por ID de job
y dentro de la raíz autorizada.

Rutas de VNR, todas bajo `/api/vnr`: `doctor`, `companies`, `download`,
`sources/upload`, `sources/inspect`, `database/test`, `database/discover`,
`schema/resolve`, `topology/build`, `validate`, `reconcile`, `export/{target}` y
`artifacts/{job_id}/{index}`. El catálogo oficial es `/api/vnr/publications`
(`?refresh=true` lo actualiza), y el estado de un trabajo, `/api/jobs/{id}`, como el
de cualquier otro.

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
