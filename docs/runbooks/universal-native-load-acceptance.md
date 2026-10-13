# Aceptación universal de carga en PowerFactory

## Resultado que acredita

Este procedimiento cierra cada fuente oficial —TXT, MDB o VNR-GIS— con el mismo
recorrido: adaptador → contrato canónico → DGS → importación y relectura nativa →
ajuste de P/Q → `ComLdf` → estudio. No existe un algoritmo alternativo por formato.

El resultado aceptado es `NATIVE_LOAD_VERIFIED`. `DGS_READY` solo acredita el archivo
DGS; una ejecución de PowerFactory sin medición de cabecera, medidor o estudio queda
`BLOQUEADO_DATOS` y no se presenta como aceptación de carga.

La arquitectura común sigue la interoperabilidad CIM desarrollada por McMorran en su
tesis doctoral (<https://stax.strath.ac.uk/concern/theses/cc08hf706>) y el modelado de
redes desde GIS y datos operativos investigado por Lu en su tesis doctoral
(<https://pureportal.strath.ac.uk/en/studentTheses/predicting-power-distribution-network-characteristics-and-load-pr/>)
y Tefera en su tesis de maestría
(<https://etd.aau.edu.et/items/56fa0725-26f3-4436-b102-7f00fd4ffa6b>). La verificación
previa de topología y parámetros se apoya en el artículo indexado IEEE TIM, DOI
10.1109/TIM.2022.3175043 (<https://ieeexplore.ieee.org/document/9781319/>).

## Entradas

- Los paquetes oficiales de cada modalidad disponible.
- Un alimentador y su medidor de cabecera mediante `--feeder` y
  `--meter ALIMENTADOR=MEDIDOR`.
- El libro o carpeta de medición mediante `--cabecera`.
- Juntos, `--suministros` y `--clientes`, cuando existen clientes importantes. El libro
  de clientes debe demostrar el mismo mes natural que la máxima.
- PowerFactory y su intérprete Python cuando se usa `--powerfactory`.

No se sustituye una fuente oficial ausente. Sin paquete VNR-GIS, el estado correcto es
`BLOCKED_MISSING_OFFICIAL_PACKAGE`.

## Ejecución

```powershell
python tools\accept_three_sources.py `
  --audit-dir AUDIT\native_load_YYYYMMDD_HHMMSS `
  --feeder CA101 `
  --meter CA101=L-CA131 `
  --cabecera "ruta\medicion_cabecera" `
  --suministros "ruta\suministros.xlsx" `
  --clientes "ruta\clientes_2026-04.xlsx" `
  --txt-red "ruta\RED.txt" `
  --txt-loads "ruta\CARGA.txt" `
  --txt-equipment "ruta\EQUIPOS.txt" `
  --mdb "ruta\red.mdb" `
  --vnr-package "ruta\paquete_vnr.zip" `
  --study-key flujo `
  --powerfactory
```

`--feeder`, `--meter` y `--study-key` se pueden repetir. Sin libros de clientes se
permite el reparto por kVA y se conserva el aviso; no se inventan clientes fijos.

## Evidencia por modalidad

`acceptance_summary.json` usa el esquema
`igea-dgs-three-source-native-load-v1` y contiene:

- hash de la auditoría canónica, archivos fuente y DGS;
- bancos esperados y releídos, potencia, nodo y correcciones antes/después;
- conteo escrito y releído del atributo `p:alimentador`;
- vínculo entre ejecución fuente y proyecto nativo;
- periodo de máxima, periodo y fingerprint del libro de clientes;
- SED fijas y escaladas, derivación P=`Pot` y Q=`Pot×ERI/EA`;
- relectura nativa de P, Q, FP, `outserv` e `i_scale`;
- objetivo y resultado P/Q de cabecera;
- validez de `ComLdf`, tensiones, cargabilidad y violaciones físicas.

## Reglas no bloqueantes

- `AVISO_KVAR` conserva diferencia firmada, relativa y tolerancia con
  `bloquea=false`. El kW convergente dentro de tolerancia es el criterio de cuadre.
- Una diferencia de banco se corrige al valor de origen; solo si falta capacidad se
  usa el catálogo operativo: 300 kVAr en 10 kV y 450 kVAr en 22,9 kV. El informe debe
  indicar el nodo y los valores anterior, aplicado y releído.
- `AVISO_PERSISTENCIA_CORREGIDA` y `AVISO_PERSISTENCIA_NO_CORREGIDA` informan bancos y
  no detienen conversión, ajuste ni estudio.

`BLOQUEADO_PERSISTENCIA` se reserva para una escritura o relectura nativa requerida que
no queda demostrada; no se usa por una diferencia reactiva de banco o cabecera.

## Niveles de comprobación

1. Salida del comando: prueba que el proceso terminó.
2. Guardado: prueba que PowerFactory aceptó la operación.
3. Reapertura/relectura: prueba los valores efectivos del objeto nativo.
4. `ComLdf`: prueba convergencia con la red ya cargada.
5. Aceptación física: prueba tensiones, cargabilidad y ausencia de violaciones.

Un test automatizado o un guion falso no reemplaza los niveles 2–5. Una modalidad no
ejecutada queda explícitamente pendiente; nunca hereda la evidencia de otra.
