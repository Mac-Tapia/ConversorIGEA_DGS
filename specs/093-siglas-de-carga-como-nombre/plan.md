# Plan 093 — La sigla de la carga como nombre

## Dónde

- `src/convertersmartgrid/cargas_pf.py`: alias `siglasdecarga`, `siglas` y `sigla` → `sigla`; en
  `leer_hoja_nuevas`, el nombre es la SED, si no la sigla y, si no, la descripción (RF-1, RF-2); `CargaNueva` guarda
  la descripción en `descripcion` y `a_dict` la lleva al plan (RF-3).

## Decisión

- Un campo propio `sigla`, no un alias de `SED`: una «SED» de la fila es una existente (040, aclaración de RF-3) y
  la sigla nombra una carga que todavía no existe. Descartado: mapear la sigla a `SED`, que la haría pasar por las
  reglas de ampliación de una SED existente.

## Pruebas

- `tests/test_cargas_pf.py`: libro con «SIGLAS DE CARGA» y «DESCRIPCION» → `sed` es la sigla y `descripcion` el
  cliente; sin sigla, la descripción; el plan lleva la descripción.
