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
  --mdb "ruta\260924.mdb" `
  --txt-red "ruta\260927_Red.txt" `
  --txt-loads "ruta\260927_Carga.txt" `
  --txt-equipment "ruta\260927_Equipo.txt" `
  --vnr-package "ruta\paquete_vnr_gis.zip" `
  --powerfactory
```

Omita `--powerfactory` para validar hasta DGS. Omita `--vnr-package` cuando no exista:
el resumen lo marcará bloqueado sin reutilizar el MDB o los TXT.

## Lectura de resultados

`acceptance_summary.json` registra por modo:

- archivos originales, tamaños y SHA-256;
- `source_run_id` y fingerprint exclusivos;
- cantidad de alimentadores y selección exacta;
- DGS generados y sus SHA-256;
- nivel de evidencia PowerFactory, proyecto, relectura efectiva, `ComLdf` y rollback.

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
