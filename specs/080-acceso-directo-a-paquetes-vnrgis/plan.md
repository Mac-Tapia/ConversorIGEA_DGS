# Plan — Spec 080

## Módulos

- `src/vnr_etl/discovery/official.py` (RF-1 a RF-10): `PORTAL_VNR`, `paginas_de_ciclos`, ampliación de `parse_official_publications` y de `refresh_official_catalog`, `vigentes_por_empresa`. `_fetch_html` decodifica por los bytes: con `apparent_encoding` esas páginas no se leían bien.
- `src/vnr_etl/discovery/download.py` (RF-18 a RF-24): `preparar_unrar`, comprobación antes de descargar y `extraer_copia_sql`.
- `src/convertersmartgrid/web/app.py` (RF-9, RF-14, RF-18, RF-20): `/api/vnr/publications` añade `vigente`, `empresa` y `portal`; la descarga extrae y asigna.
- `frontend/src/components/InputsPanel.tsx`, `frontend/src/types.ts` (RF-11 a RF-17): `VnrDiscovery` por distribuidora.

## Decisiones

- Se amplía el buscador existente. Descartado: una tabla de URL en la interfaz, que caduca con cada ciclo y va contra VNR-GIS.md D4.
- La vigencia se decide en el servidor, y la interfaz solo la muestra (skill frontend: sin reglas duplicadas).
- La vigencia compara resoluciones por año y número, no por el título de la página: la página «publicación de la resolución de fijación 2025» trae en realidad el proyecto (RCD 154-2026), y la definitiva es otra (RCD 184-2026).
- Solo se extraen `.bak` y `.config` de la carpeta de la copia, escritos por su nombre base. Descartado: extraer todo el paquete, que trae ejecutables y varias decenas de MB que nadie usa.
- El archivo descargado se conserva junto a su manifiesto, como evidencia del SHA-256.

## Pruebas

`tests/test_vnr_accesos_directos.py`: HTML sintético con la forma del portal (filas de dos empresas, tabla escapada, secciones SICODI y mapa), ZIP sintéticos para la extracción y la API con `TestClient`. La web y el portal reales se prueban en el navegador, como pide el skill frontend (T4).
