# Plan — Spec 023

## Lo que mostró la copia real (2026-10-18)

`ELDU_VNR_24_APR.bak` (SQL Server 2022, 819 MB) restaurada en `.\SQLEXPRESS`: 75 tablas del
modelo VNR-GIS del regulador, iguales para toda concesionaria. Las que usa la conversión:

| Concepto | Tabla | Campos |
| --- | --- | --- |
| Empresa y CRS | `empEmpresa` | `CodEmpresa`, `Datum`, `ZonaUTM` |
| Sistema eléctrico | `empSistemaElectrico` | `CodSisElectrico`, `Nombre`, `CodSectorTipico` |
| SET | `CentroTransformacion` | `CodSet`, `Nombre`, `UTMEste`, `UTMNorte` |
| Alimentador | `mtSalida` | `CodSalidaMT`, `CodSet`, `CodSisElectrico`, `CodTenNomi`, `EtiquetaSalida` |
| Tramo MT | `mtTramo` | `CodTramoMT`, `CodSalidaMT`, `CodTramoMTPadre`, `Longitud`, `CodNorma`, `CodTenNomi`, `EstadoVnr` |
| Geometría del tramo | `verTramoMT` | `CodTramoMT`, `SecVertice`, `UTMEste`, `UTMNorte` |
| SED | `Sed` | `CodSed`, `CodSalidaMT`, `PotInstalada`, `MaxDemTotal`, `UTMEste`, `UTMNorte` |
| Unión tramo–SED | `mtNodoEnlace` | `CodNodoMT`, `CodTramoMT`, `CodSed`, `UTMEste`, `UTMNorte` |
| Maniobras | `mtEquipo` | `CodEqp`, `CodTramoMT`, `CodTipoEquipoProteccion`, `CodEstadoOperacion` |

La geometría no viene como `geometry` de SQL Server sino por vértices con UTM (RF-8).

## Módulos

- `src/vnr_etl/connectors/sqlserver_vnr.py` (nuevo), restauración — huella del `.bak`,
  `RESTORE FILELISTONLY`, restauración con `WITH MOVE` en la carpeta de datos del propio
  motor (su cuenta de servicio siempre puede escribir) con nombre `IGEA_VNR_<huella>`,
  reutiliza si existe (RF-3, RF-4);
  error claro sin motor (RF-5); conexión de solo lectura (RF-6). Lee `ConfigBD.config` si
  está (RF-2). Motor configurable (`IGEA_SQLSERVER`).
- `src/vnr_etl/connectors/sqlserver_vnr.py`, lectura semántica por campos (RF-7):
  busca la tabla de tramos por `CodTramoMT`+`CodSalidaMT`, la de vértices por
  `CodTramoMT`+`SecVertice`, etc., con los alias de `discovery/schema.py`; arma el
  `CanonicalModel` de un alimentador: nodos por los extremos de la geometría y la
  relación padre–hijo, tramos con longitud y norma, SED como cargas con su potencia
  instalada y su punto de unión, maniobras, fuente en la SET. CRS de `empEmpresa`
  (`Datum`+`ZonaUTM` → EPSG) o del perfil (RF-8).
- `src/igea_dgs/sources/vnr.py`: acepta `.bak` como `vnr_package` y lo manda por el lector
  nuevo; lo demás por el puente de siempre (RF-1, RF-9).
- Web y CLI: la casilla y `--vnr-package` aceptan `.bak` (RF-1).

## Decisiones

- Restaurar con SQL Server, no leer el formato del `.bak`: es la vía documentada; leerlo a
  mano no es viable y los lectores comerciales suben datos o son cerrados.
- Nodos por geometría y padre, no por `mtNodoEnlace` solo: `mtNodoEnlace` trae 10 008 nodos
  frente a 15 304 tramos; los extremos de los vértices dan la conectividad completa y el
  padre la confirma.

## Pruebas

- Sintéticas sin SQL Server: un doble del cursor que devuelve las tablas del esquema;
  RF-2, RF-5, RF-7, RF-8 y el modelo canónico de un alimentador.
- Reales con `IGEA_VNR_BAK` (como las `IGEA_*`): restaurar, convertir un alimentador,
  validar e importar en DIgSILENT.
