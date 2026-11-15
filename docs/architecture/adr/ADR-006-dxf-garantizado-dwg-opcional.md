# ADR-006 · Planos y unifilares en DXF garantizado; el DWG, solo si hay convertidor

- Estado: pendiente
- Fecha: 2026-11-14
- Specs: spec 107, spec 072
- Elementos C4: cadWriter, oda, planning, pit, workspaceStore
- Evidencia: `pyproject.toml::dep:ezdxf`
- Pendiente en: 107 T23 (Aclaración de 107:RF-15, en `wt_107_00d3`) y 072 (planos A3 y Gantt), con `ezdxf` como dependencia obligatoria que añade el integrador

## Contexto

Los expedientes de planeamiento (PIT y PIDE) piden planos y unifilares «compatibles con AutoCAD». El conversor no
tiene hoy ningún escritor de CAD: `mapa_informe` hace imágenes. El DWG es un formato cerrado que solo se escribe
con un convertidor externo con licencia propia; el DXF es abierto, lo abre AutoCAD y lo escribe `ezdxf` (MIT,
Python puro). El usuario ordenó el 2026-11-14 decidir «como ingeniero de planeamiento»; e6 propuso DXF más DWG
opcional y el auditor 7e lo aceptó con condiciones.

## Decisión

- El DXF es la entrega garantizada de planos y unifilares, y `ezdxf` es dependencia obligatoria, no un extra: sin
  ella el expediente quedaría incompleto.
- El DWG se añade solo si se detecta un convertidor (por la configuración o por el PATH); nunca se distribuye ni se
  busca en una ruta fija.
- Sin convertidor, o si falla, la entrega queda completa con el DXF, el manifiesto dice cómo obtener el DWG y nunca
  sale un DWG vacío.

## Alternativa descartada

DWG como formato principal. Exigiría distribuir o comprar un convertidor con licencia, haría depender la entrega de
un programa ajeno y no ganaría nada para el ente: AutoCAD abre el DXF.

## Consecuencias

- La TO-BE añade el contenedor `cadWriter` y el sistema externo `oda`; los planos dejan de ser solo imágenes.
- Cuando `ezdxf` entre en `[project].dependencies`, la prueba de arquitectura marcará este ADR como desfasado y se
  pasará a vigente en el mismo cambio, con la evidencia del escritor.

## Contratos afectados

`pyproject.toml` (dependencia obligatoria nueva), el manifiesto del expediente PIT y PIDE (lista de planos, formato
y aviso del DWG) y los ficheros DXF y DWG del expediente.

## Vuelta atrás

Quitar la dependencia y el escritor DXF: los expedientes vuelven a llevar solo imágenes. El DWG opcional no deja
nada que deshacer, porque nunca es requisito.
