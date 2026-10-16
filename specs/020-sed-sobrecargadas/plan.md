# Plan 020 — SED fijas sobrecargadas: aviso y transformadores nuevos

Spec: `specs/020-sed-sobrecargadas/spec.md` (aprobada el 2026-10-16).

## Decisiones

1. **La propuesta se calcula en el guion del ajuste, no en la web.** El guion ya tiene las
   SED fijas, su demanda y los transformadores de DIgSILENT (tensión primaria, unidades en
   paralelo, cuántos hay en la SED). Calcularla en la web obligaría a mandar todo eso o a
   leer DIgSILENT otra vez. *Descartado:* un guion de propuesta aparte (otro viaje al
   motor y la misma lectura dos veces).
2. **La regla de dimensionado es pura y vive en `src/igea_dgs/trafos_sed.py`.** Recibe la
   demanda en kVA, la tensión primaria y las tablas del perfil, y devuelve la potencia, las
   unidades y la ficha. Se prueba sin DIgSILENT. El guion solo la llama (P5: una
   responsabilidad, un sitio). *No se reutiliza* `sed_potencia.redimensionar_sobrecargadas`
   (regla de la conversión, `reglas.py`): actúa sobre el modelo con la carga del archivo,
   cubre el 100 % y solo cambia el kVA, sin ficha; aquí la demanda es la de los clientes
   fijos, el umbral es el del perfil y el tipo lleva sus pérdidas y su uk.
3. **Implementar y recalibrar en una sola ejecución del guion del ajuste.** El servicio
   copia el plan del ajuste con `transformadores` (las SED marcadas y su propuesta) y
   lanza `ajuste_cabecera_pf.py` en modo aplicar. El guion cambia los transformadores en
   «Sin proyecto» y sigue con la calibración de siempre. Así RF-25 (mismo trabajo, mismo
   plan) no necesita una cola de dos órdenes, y la cancelación entre el cambio y la
   calibración (RF-27) es el punto de cancelación que ya existe. *Descartado:* un guion
   `trafos_sed_pf.py` más una segunda orden del ajuste: dos informes que unir y un estado
   intermedio que la web tendría que conocer.
4. **Las tablas van en el perfil de empresa** (P13), en `calibracion.transformadores_sed`:
   `umbral_carga_pct` y `tablas` con `norma`, `kv_min`, `kv_max` (primaria, con `kv_min`
   excluido) y `fichas` por kVA, `[po_w, pc_w, io_pct, uk_pct]`. Electro Dunas: las Tablas 6
   y 7 de FONAFE 2017 (NTP 370.400-2013). La lectura y la validación (RF-29 a RF-31) van en
   `perfil_empresa.py`, al lado de `factor_potencia_cargas`.
5. **Nombre del tipo propio:** `TR_<kVA>kVA_<norma corta>_<AT>-<BT V>V_<grupo>`, por ejemplo
   `TR_630kVA_NTP370400_22.9-220V_DYN5`, el mismo que se usó en PA217 (015, T26), para
   reutilizar los tipos ya creados (RF-21). La norma corta se lee del perfil (`codigo`).

## Partes

### A. Perfil (RF-29, RF-30, RF-31; requisito no funcional P13)

- `config/perfiles/electro_dunas.json`: `calibracion.transformadores_sed` con las dos
  tablas y el umbral del 80 %, y su `_comentario` con la fuente.
- `src/igea_dgs/perfil_empresa.py`: `transformadores_sed(datos) -> dict | None`, que
  devuelve las tablas válidas y los avisos de las filas descartadas (fila y perfil).
- Pruebas: `tests/test_perfil_empresa.py`.

### B. Regla de dimensionado (RF-6, RF-7, RF-8, RF-11)

- `src/igea_dgs/trafos_sed.py`: `tabla_para(tablas, kv_primaria)` y
  `proponer(kva_carga, kv_primaria, tablas, umbral) -> dict` (potencia, unidades, ficha,
  tabla, carga prevista, o el motivo de que no haya propuesta).
- Pruebas: `tests/test_trafos_sed.py`, con los cuatro casos de PA217 y potencias sorteadas.
  La propiedad que se comprueba: la carga prevista nunca supera el umbral y con una unidad
  menos, o con la potencia anterior de la tabla, sí lo superaría.

### C. Detección y propuesta en el guion (RF-1, RF-2, RF-4, RF-5, RF-9, RF-10, RF-12)

- `tools/ajuste_cabecera_pf.py`: `kva_en_pf` ya cuenta `ntnum` (015, T26; RF-2).
  `fijas_sobre_su_transformador` añade por SED los transformadores (nombre, tipo, tensión
  primaria y de baja, grupo, unidades) y, con las tablas del plan, la propuesta de B.
  Informe: `fijas_sobre_su_transformador` (lo de hoy, más la propuesta) y
  `fichas_transformador_sed` (norma y umbral, o el aviso de RF-10).
- El aviso de VALIDACION_FISICA y el de no converger nombran la sobrecarga como causa
  probable (RF-4), sobre lo que ya hace `aviso_consumo_fisico`.
- Pruebas: `tests/test_ajuste_cabecera_guion.py` con `fake_pf`.

### D. Cambio de transformadores en «Sin proyecto» (RF-16 a RF-24, RF-26, RF-27, RF-32)

- `tools/ajuste_cabecera_pf.py`: `implementar_transformadores(app, sin, cambios)`, que se
  llama en `_ejecutar` con «Sin proyecto» activo y antes de la calibración, si el plan trae
  `transformadores`.
  - Comprueba que no hay variación activa ni etapa grabando (RF-17). Si las hay, no cambia
    nada y termina con error.
  - Por SED: un solo transformador (RF-12). Tipo propio creado o reutilizado (RF-19, RF-21,
    RF-22) con `AddCopy` del tipo actual. Asigna `typ_id` y `ntnum` (RF-23). Nunca escribe
    en un tipo existente (RF-20).
  - Informa por SED antes y después (RF-24) en `informe['transformadores_implementados']`.
- Después de la calibración (RF-26): ninguna fija > 100 % y cada SED cambiada ≤ umbral. Si
  la calibración no es válida o no converge (RF-32), `status` de fallo y un aviso que dice
  qué sigue fallando. Los transformadores no se tocan.
- Si se cancela entre el cambio y la calibración (RF-27), el informe dice que los
  transformadores quedaron y falta calibrar.
- `tests/fake_pf.py`: lo que haga falta (`ntnum`, `AddCopy` de `TypTr2` en su carpeta).
- Pruebas: `tests/test_ajuste_cabecera_guion.py`.

### E. Web: servicio y API (RF-15, RF-25, RF-28)

- `src/igea_dgs/web/services.py`: `ajuste_plan` pone en el plan las tablas del perfil;
  `ajuste_transformadores(ws, ctx, token, seds)` copia el plan con `transformadores` (la
  propuesta de las SED pedidas, tomada del último informe del ajuste de ese plan) y lo
  ejecuta como el aplicar de siempre, con `_guardar_calibracion` si sale válida (RF-28).
- `src/igea_dgs/web/app.py`: `POST /api/workspaces/{wid}/demanda/ajuste/{token}/transformadores`
  con `{sed: [...]}`, trabajo `ajuste_transformadores` en el carril de DIgSILENT (P7).
- Pruebas: `tests/test_ajuste_cabecera_web.py`.

### F. Front (RF-3, RF-4, RF-9, RF-13, RF-14)

- `frontend/src/components/AjusteCabecera.tsx`: el aviso de sobrecarga pasa al principio
  del resultado. Tabla de la propuesta con una casilla por SED (todas marcadas), el botón
  «Implementar transformadores» (desactivado sin casillas) y el resultado de
  `transformadores_implementados`.
- `frontend/src/types.ts` y `frontend/src/api.ts`: tipos y `ajusteTransformadores`.
- Pruebas: `tests/test_ajuste_cabecera_web.py` (contrato) y `npm run build`.

### G. Índice y documentación

- `CODIGO_FUENTE.md`: `src/igea_dgs/trafos_sed.py` con la spec 020 (`test_inventario`).
- `CLAUDE.md`: fila de la 020 en la tabla de specs.
- `specs/015-caso-base-verificado/spec.md`: nota en «Fuera de alcance» que remite a la 020.

## Estrategia de pruebas

Sintéticas con `fake_pf` y potencias sorteadas: la regla de B no tiene números de PA217
fijados salvo como caso con nombre. Nada toca el lector, así que no hacen falta las dos
disposiciones de export. Prueba final en DIgSILENT desde la web con PA217: en el proyecto
`20261016-094237_IGEA_PA217` los transformadores ya están cambiados (015, T26). Para la
prueba de punta a punta hace falta un proyecto con SED fijas sobrecargadas, recién
importado: PA217 importado otra vez desde la web.
