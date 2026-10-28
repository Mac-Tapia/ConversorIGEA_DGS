# Plan — Spec 032

Lee: `docs/constitution.md` y `specs/032-caso-base-original-fichas-en-sin-proyecto/spec.md`.

## Contexto técnico

- Conversión: las dos correcciones salen de un único sitio, `reglas.aplicar_reglas`
  (regla 3, `sed_potencia.redimensionar_sobrecargadas`; regla 4,
  `catalog.aplicar_correcciones` con `correcciones=`). La llaman `batch.convert_selection`
  (`_FeederOptions.catalog_corrections`), `batch.convert_group` (red unida y por sistema),
  `web/services.py` (conversión, líneas ~511-590; modelo en memoria, ~830-850 y ~1080; red
  unida, ~1251-1283) y el CLI (`--catalogo`). `batch` lee además `leer_catalogo(catalogo)`
  cuando no le pasan correcciones.
- Completar conductores sin parámetros (RF-3) es `reglas.preparar_dataset` con
  `catalogo=`; ya devuelve `InformeEntrada.completados_catalogo`. Los transformadores de SED
  del catálogo (`leer_trafos`) dan la impedancia que la entrada no trae (CYMDIST no modela
  el transformador): no cambian el kVA y se quedan.
- Calibración en «Sin proyecto»: `tools/ajuste_cabecera_pf.py` (plan JSON de
  `services.py` ~2990-3010). Ya trae `transformadores_sed` del perfil, la propuesta de las
  fijas (`fijas_sobre_su_transformador`, `proponer_transformadores`) y la escritura
  (`implementar_transformadores`), que hoy **rechaza** cualquier variación activa y
  escribe en la red (020:RF-16, RF-17). Variaciones nuevas con `cargas_pf.crear_variacion`
  (nombre libre, etapa que graba, fecha por `fecha_de_etapa_nueva`).
- Casos: `tools/casos_pf.py` decide qué variaciones están activas en «Caso base»,
  «Sin proyecto» y «Con proyecto» (y los de cada año, 025).
- Quién creó cada cosa: `escaneo.PREFIJOS_PROPIOS` (028).
- Web: `frontend/src/components/AjusteCabecera.tsx` y `DemandaMedida.tsx` (resultado del
  ajuste y propuesta de la 020), `frontend/src/api.ts`.
- Carril: la conversión en `engine`; la calibración y la implementación, en el de
  DIgSILENT, como hoy.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Caso base sin correcciones | `src/igea_dgs/reglas.py`: `Reglas.redimensionar_sed=False` en `REGLAS_PROYECTO`, campo nuevo `aplicar_fichas: bool = False`; `aplicar_reglas` aplica `correcciones` solo con `aplicar_fichas`. `batch.py` deja de leer `leer_catalogo` para convertir. `web/services.py` quita `catalog_corrections` y las líneas «SED redimensionada» del Registro | RF-1, RF-2, RF-5, RF-6 |
| B. Completados anotados | `reglas.preparar_dataset`: `completados_catalogo` con fuente y nº de tramos por código; al manifiesto (informe de entrada) y al Registro | RF-3, RF-4 |
| C. Verificación con la entrada | `capacidades.comparar_equipos` ya compara con el DGS aceptado, que ahora es la entrada: prueba que lo fija; 015:RF-38 sin cambios | RF-7, RF-26 |
| D. Fichas en el plan | `catalog.py`: función pura `fichas_para_pf(correcciones) -> dict[codigo, dict[atributo_pf, valor]]` (unidades de DIgSILENT: `sline` en kA, `bline` en µS/km), con la regla de la homopolar de `aplicar_correcciones` extraída a una función común; y `cambios_de_ficha(codigo, actuales, ficha, tramos, km)` → `list[Cambio]` y rechazos (RF-19). `services.py` pone `fichas_conductores` en el plan (catálogo subido o el del proyecto) | RF-14, RF-16, RF-18, RF-19 |
| E. Variación de conductores | `tools/ajuste_cabecera_pf.py`: `fichas_en_sin_proyecto(app, fichas)` antes del primer flujo: reutiliza o crea `Fichas_<proyecto>`; por cada `TypLne` usado con ficha, tipo propio `<tipo>_FICHA` (`AddCopy`, sin tocar el original), reutilizado si coincide y omitido con motivo si difiere; reasigna `typ_id` de sus `ElmLne` con la etapa grabando. Informe por código al resultado del ajuste | RF-8 a RF-17 |
| F. SED sobre el umbral | `src/igea_dgs/trafos_sed.py`: función pura `sed_sobre_umbral(demanda_kva, kva, umbral_pct)` → nivel `sobre_100` / `sobre_umbral`. En el guion, tras el flujo calibrado, la demanda aparente de cada SED (fija o escalada) por `m:Ssum` de su transformador; las fijas conservan su aviso previo al flujo (020:RF-1) | RF-20, RF-21, RF-25, RF-28 |
| G. Variación de SED | `implementar_transformadores`: reutiliza o crea `SED_NTP_<proyecto>` y escribe ahí; solo rechaza si graba una variación **del operador** (fuera de `PREFIJOS_PROPIOS`) | RF-8, RF-12, RF-13, RF-23, RF-24 |
| H. Casos | `tools/casos_pf.py`: `Fichas_*` y `SED_NTP_*` activas en «Sin proyecto», «Con proyecto» y los de cada año; inactivas en «Caso base». `escaneo.PREFIJOS_PROPIOS` con los dos prefijos | RF-27 |
| I. Web | `api.ts`, `AjusteCabecera.tsx`/`DemandaMedida.tsx`: tabla «Conductores con su ficha» (código, parámetro, archivo, ficha, %, tramos, km, fuente; «sin ficha» aparte) y columna de nivel en la propuesta de SED (> 100 % frente a umbral–100 %) | RF-17, RF-22, RF-28 |

## Decisiones

- **Dos variaciones por proyecto (`Fichas_<proyecto>`, `SED_NTP_<proyecto>`)**, por orden
  del usuario, aunque compartan fecha. Descartado: una sola variación del catálogo, porque
  el usuario la pidió por clase de cambio. Si DIgSILENT no deja grabar con tres etapas de
  la misma fecha (SI213, 2026-10-12), `crear_variacion` ya lo comprueba al crear; la
  prueba en DIgSILENT (T9) lo confirma.
- **Tipos propios en vez de editar los `TypLne`.** Los tipos están en la biblioteca y una
  variación no graba sus cambios: editar el tipo cambiaría el «Caso base». Se reasigna el
  `typ_id` de las líneas, que sí graba la etapa. Descartado: editar el tipo dentro de la
  variación.
- **Demanda de las escaladas tras el flujo calibrado.** Su potencia depende del scale0;
  solo el flujo la da. Descartado: kVA × FP del perfil antes del flujo, que no ve el factor.
- **`aplicar_fichas` queda en `Reglas`** para `tools/apply_catalog_to_model.py`, que sirve
  para comparar; ninguna vía de conversión del proyecto lo enciende. Descartado: borrar la
  regla 4, porque ese guion la necesita.
- **Proyectos ya importados**: nada que migrar (fuera de alcance).

## Comprobación contra la constitución

- P1: el DGS sigue siendo determinista; quitar reglas no introduce orden nuevo
  (`TestParallelWorkers`).
- P2: el cambio de conductores es por tipo (`TypLne`) y luego por sus líneas, sin bucles
  de alimentador × tabla.
- P5: las vías siguen pasando por `aplicar_reglas`; el cambio está en `REGLAS_PROYECTO`.
- P13: fichas desde el catálogo y umbral y tablas desde el perfil; sin perfil ni catálogo,
  aviso y nada se cambia.
- P11: toca el modelo: suite con las siete variables.

## Estrategia de pruebas

- Sintéticas sorteadas con `ExportSpec(seed=…)`, en las dos disposiciones: una SED con más
  carga que kVA y un conductor con ficha distinta en el catálogo; el DGS lleva lo de la
  entrada (RF-1, RF-2), web, CLI y red unida dan el mismo DGS (RF-6), el manifiesto no trae
  `sed_redimensionadas` (RF-5), un código sin parámetros se completa y se anota (RF-3, RF-4).
- `catalog.py`: `fichas_para_pf` y `cambios_de_ficha` con valores conocidos, homopolar
  arrastrada, valor no positivo rechazado (RF-14, RF-16, RF-18, RF-19).
- Guion con `fake_pf` (`tests/test_ajuste_cabecera_guion.py`): variaciones creadas y
  reutilizadas, tipos propios, `typ_id` reasignado, tipo original intacto, variación del
  operador grabando (RF-8 a RF-13, RF-23, RF-24); SED escaladas y fijas clasificadas
  (RF-20, RF-28).
- `tests/test_casos_pf*.py`: activas en «Sin/Con proyecto», inactivas en «Caso base»
  (RF-27).
- Datos reales (`IGEA_*`): DGS de los alimentadores reales sin SED redimensionadas.
- Cada prueba cita `032:RF-n`.

## Riesgos

- Pruebas existentes que esperan SED redimensionadas o fichas aplicadas al convertir
  (`tests/test_catalog.py`, `tests/test_puentes.py`, pruebas de lote y web): se cambian
  citando 032, o pasan `aplicar_fichas=True` si prueban la regla en sí.
- «Caso base» de redes como 260924.mdb que dejan de converger: 015:RF-38 escala la demanda;
  se ve en la prueba con datos reales y en DIgSILENT.
- `implementar_transformadores` hoy apaga las variaciones `Central_` para escribir; con la
  suya propia grabando, hay que comprobar en DIgSILENT que lo escrito va a `SED_NTP_` y no
  a la central.
