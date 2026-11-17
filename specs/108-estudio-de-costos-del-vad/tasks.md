# Tareas — Spec 108

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Las tareas T1 a T13 son la **iteración 1, el anexo 6 rural**. La T14 (anexo 5 urbano, RF-6) es posterior y no
empieza hasta que la T13 esté cerrada. Ninguna tarea modifica `web/services.py`, `pide_economia.py`,
`adaptadores/entrada/vnr/**` ni `catalog_resolution.py` (son de f9). Ninguna fórmula del TdR se escribe sin haberla
leído: las tareas que la necesitan empiezan por leer el anexo y transcribirlo con su cita (fichero y líneas de la
copia local `output/normativa_pide_20261025/textos/fb5341703a3c….txt`, o la página del PDF oficial).

- [x] T1. Paquete `src/convertersmartgrid/vad/` y registro del estudio: `vad/estudio.py` con `EstudioVad` (empresa
      del perfil, grupo, periodo, versión del TdR y estado), guardado en `<espacio>/vad/<id>/estudio.json`, aparte del
      PIDE y del PIT. Un estudio no lee ni escribe en las carpetas del PIDE. (RF-1)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_estudio.py` en verde, con dos empresas
      sintéticas y una prueba de que crear un estudio VAD no cambia ningún fichero del PIDE.
- [x] T2. Registro normativo. Leer y transcribir en `config/vad/tdr_vad_2026.json` la RCD 174-2025-OS/CD, la
      RCD 033-2026-OS/CD y el índice de anexos del texto modificado (copia local, líneas 142-150), cada entrada con
      acto, anexo, versión, `estado_juridico` (vocabulario del registro común `registro_normativo.py`, 107 T1: vigente_comprobada, modificada, prepublicada, no_verificada…), URL, fichero local, líneas, SHA-256,
      fecha de lectura, moneda e IGV. Leer el anexo 1 y comprobar a qué grupo pertenece cada empresa del caso, porque
      G0 solo lo dedujo de los considerandos. Las entradas del TdR VAD se cargan en el registro normativo común `src/convertersmartgrid/registro_normativo.py` (lo crea la 107 T1; si la 108 va antes, lo crea esta tarea con ese mismo contrato); `vad/` solo lo usa, sin un registro propio (P5). (RF-9,
      RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_normativa.py` en verde. Las pruebas cubren
      un TdR `proyecto` o `pendiente`, un `igv: sin_leer` y una entrada sin cita, y en los tres casos el estudio queda
      `no_conforme`. Un cambio de versión a mitad del estudio lo deja `desactualizado` y nombra lo afectado.
      Avance (2026-11-15, f4/VAD-REQ): las RCD 174-2025 y 033-2026 quedan `vigente_comprobada` con su SHA-256, su
      copia local y su emisión aparte de su publicación (la 174-2025 se publicó el 2025-12-19);
      `config/vad/tdr_vad_2026_requisitos.json` amplía el anexo con las 36 reglas de V11 (6.11) y V12 (6.8.3, 6.13 a
      6.15), cada una con su cita, su carácter y su entregable, y `vad.calidad.indicadores` se amplía sin repetirse
      (`tests/test_vad_requisitos.py`).
- [x] T3. Anexo 2. Leer y transcribir en `config/vad/anexo2_formatos.json` los formatos de información técnica,
      comercial y económica, con cada tabla, campo, unidad y periodo, y su cita. `vad/anexo2.py` con `validar_tablas`
      para el inventario VNR, las tablas técnicas, comerciales y contables y los costos. (RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_anexo2.py` en verde. Una tabla obligatoria
      que falta, un campo vacío y una unidad distinta se informan por tabla y campo, y la tabla de salida no trae
      ningún valor que no estuviera en la entrada.
      Avance (2026-11-15, f4/VAD-A5): según el cotejo de cc (z5) y su transcripción con doble lectura (z5b) del TdR
      vigente (RCD 033-2026, pdf 90-93), el validador admite celdas «no aplica» por fila (si traen dato, aviso, sin
      borrarlo), filas de «grupo» (solo rótulo) y de «total», llamadas a las notas del formato y la forma «larga»
      (A-V-3: un bloque por empresa, sistema y mes; mes que falta, bloque repetido y clave vacía se nombran). El A-V-1
      (44 filas) y el A-V-2 (42, con su estructura propia y BT5C y BT6NR) traen el mapa de celdas grises, los 8 rangos
      del BT5B y las filas de grupo y total; el BT6 va tal cual «Pesión Fija» (sic, errata por Pensión); el A-V-3 deja
      de ser hueco. La (47) del A-VI va en MW.h y la (48) en %. La tabla de equivalencias de códigos entre formatos
      queda en la config como decisión anotada.
      Avance (2026-11-15, f4/VAD-A5 ampliada): con z1 y z7 de cc, desde el vigente (pdf 82-98), ya no queda ningún
      formato sin transcribir: III-1, IV-1 a IV-4, VIII-1/2 e IX-1/2 entran con su fuente (no hay VII-2). El A-I-1
      trae sus 7 filas de grupo y las 4 del desglose del Sub Total BT; el I-2, el II y el VII-1, sus notas literales
      con las llamadas por columna. En el VII-1 la PTU se informa y no suma en el costo reconocible (nota (3) y TdR
      6.14; `costo_reconocible`), y las horas extra y lo cargado a inversiones se avisan como limitaciones del
      formato. Las actividades del IX casan con las demás por rótulo (decisión anotada).
      Avance (2026-11-15, f4/VAD-A5 v3): la inclusión «IX.A12 ⊂ A13» se explica en la config con la cita de las
      páginas de los dos lados (pdf 85, 89, 95, 97 y 98), y validar el IX-1 o el IX-2 avisa «códigos del IX casados
      por rótulo» (aviso, no hueco).
- [ ] T4. Anexo 4. Leer y transcribir en `config/vad/tdr_vad_2026_anexo4.json` la definición del factor de carga,
      de la simultaneidad y de las curvas MT/BT, con su cita. `vad/caracterizacion.py` las calcula con
      `demanda_medida` (`maximas`, `Cabecera`, `curva_de_registros`, `reducir_curva`, `curvas_de_clientes`). Una SED
      sin medición se nombra; solo recibe una curva si el anexo transcrito lo prevé, y con esa cita. (RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_caracterizacion.py` en verde, con curvas
      sintéticas sorteadas cuyos factores se conocen de antemano y con el caso de la SED sin medición.
      Avance (2026-11-15, f4/VAD-CAR T4): `vad/caracterizacion.py` con las 29 reglas del Anexo 4 en
      `config/vad/tdr_vad_2026_anexo4.json` (amplía `tdr-vad-2026-anexo-r033`; no en `anexo4_caracterizacion.json`, para
      que el cargador las sume al acto); pérdidas con √(P²+Q²), FCPP en 18:00-23:00, por opción, agrupación, sistema y
      sector, BT5I como hueco y aviso de la RM de horas de punta; pruebas en `tests/test_vad_caracterizacion.py` y
      `tests/test_vad_caracterizacion_anexo4.py`, pendientes de la corrida de f4.
      Aclaración (2026-11-15, S-107/108): el JSON del Anexo 4 es `config/vad/tdr_vad_2026_anexo4.json`. Un
      `anexo4_caracterizacion.json` aparte con las mismas reglas no se crea: el cargador del registro rechaza una clave
      repetida en el mismo acto (`registro_normativo.cargar_registro`), y serían dos fuentes de la misma norma.
- [ ] T5. Anexo 6, modelo georreferenciado rural. Leer y transcribir en `config/vad/anexo6_rural.json` sus criterios,
      con la cita; ya está leído «Se respetarán las trazas…» (líneas 1981-1990). `vad/modelo_rural.py` con
      `armar_modelo_rural` y `hash_vertices`. Toma las trazas, las longitudes y las SED reales del VNR canónico en
      solo lectura (`models/canonical.py`, `gis/geometry.py`) o de `geography` en la vía TXT o MDB, y la troncal y las
      derivaciones de `troncal.py`. Un tramo sin geometría se nombra y no recibe vértices inventados. La parte urbana
      de un sistema mixto queda «sin modelar (anexo 5 pendiente)». (RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_modelo_rural.py` en verde. Para cada
      semilla y para las dos empresas sintéticas, el hash de los vértices de cada tramo coincide con el del VNR; un
      vértice movido 1e-9 cambia el hash y el modelo lo rechaza; hay casos de BT sin geometría y de sistema mixto, y
      la vía TXT se prueba con las dos disposiciones.
      Avance (2026-11-15, f4/VAD-A6): las 16 reglas del Anexo 6 (cc z16, líneas 6317-6868 del texto 48ea8cf4) en
      `config/vad/anexo6_rural.json`, que amplía `tdr-vad-2026-anexo-r033` sin repetir `vad.anexo6.trazas`; la tabla de
      transformadores normalizados, como interpretación (potencias con costo en el SICODI por ST y tipo de SED, las no
      normalizadas con nota). `vad/modelo_rural.py` (`armar_modelo_rural`, `hash_vertices`, `comprobar_trazas`), capa
      adaptadores; pruebas en `tests/test_vad_modelo_rural.py`, pendientes de la corrida de f4.
- [ ] T6. Dimensionamiento de la empresa modelo con el motor físico: `vad/dimensionamiento.py` adapta el conductor y
      la potencia de transformación, y calcula las pérdidas, con `oraculo.red_pandapower` y `oraculo.validar`, según
      los criterios transcritos en la T5. Ningún vértice cambia. Un conductor sin `rline` o `xline` es un hueco
      nombrado, no 0 Ω. (RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_dimensionamiento.py` en verde. En una red
      sorteada con SED sobredimensionadas, su potencia cambia y el hash de vértices no; y hay un caso con un conductor
      sin impedancia.
      Avance (2026-11-15, f4/VAD-A6 T6): `vad/dimensionamiento.py` (`dimensionar`) sobre el `ModeloRural` de la T5, sin
      tocar su traza: la potencia de cada SED sale de `vad.anexo6.sed` con la tabla de potencias con costo en el SICODI
      (interpretación de f4, con la huella del SICODI y nota en las no normalizadas); el conductor de MT, de la
      corriente del flujo de `oraculo.red_pandapower` y del rango económico que sustenta la empresa, con la sección
      mínima y el Cu de las zonas corrosivas; las pérdidas, de `oraculo.validar` y `informes.factor_de_perdidas`. Un
      conductor sin `rline` o `xline` deja su alimentador sin calcular y nombrado; la BT por tramo, los terceros y las
      secciones equivalentes quedan como huecos o interpretación anotada. Pruebas en `tests/test_vad_dimensionamiento.py`,
      pendientes de la corrida de f4.
- [ ] T7. Costo estándar: `vad/costos.py` valora la red **dimensionada** con el SICODI (`costos_fuentes.leer_sicodi`)
      mediante `valorar_obra` y `metrados.valorar_metrados`, con la fuente, la moneda y el IGV de cada elemento según
      el registro de la T2. `CostoEstandar` solo se construye con un `Dimensionamiento`, y el VNR real va solo como
      columna de referencia. (RF-7, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_costos.py` en verde. Construir un costo
      estándar con el inventario sin dimensionar lanza `VadError`; lo que no cruza con el SICODI queda nombrado y
      fuera del total; cada elemento valorado lleva su fuente; y dos monedas no se suman.
      Avance (2026-11-15, f4/VAD-A6 T7): `vad/costos.py` (`costo_estandar`, `CostoEstandar`) valora la red dimensionada
      de la T6 con el SICODI leído por su huella: los km de cada conductor de la empresa modelo con
      `metrados.valorar_metrados` y cada SED, en sus módulos, con `valorar_obra`; cada elemento lleva la fuente, la moneda
      y el IGV de `vad.igv_costos`; lo no dimensionado o sin costo queda nombrado y fuera del total; los totales van por
      moneda; el VNR real va solo en la columna de referencia. Con el RLGER registrado (`config/vad/ds_018_2020_em_rlger.json`,
      DS 018-2020-EM y DS 003-2026-EM), `ffr` y `avnr_ser` dan el aVNR del SER por régimen (Estado 100 % y mixta con fp),
      con la tasa pasiva del perfil y hueco nombrado sin ella. En la T6: AAAC y ACSR cuentan como Al (interpretación de f4),
      el umbral trifásico es el dato `trifasico_umbral_kVA` de `vad.anexo6.sed` y el flujo es `oraculo.ejecutar`. Pruebas
      en `tests/test_vad_costos.py` y `tests/test_vad_dimensionamiento.py`, pendientes de la corrida de f4.
- [ ] T8. Anexo 7 y balance. Leer y transcribir en `config/vad/anexo7_coym.json` la metodología del COyM técnico, y
      la de las pérdidas estándar y del balance de potencia y energía, con su cita. `vad/coym.py` y `vad/balance.py`
      los calculan por sistema y por tensión, sobre los resultados de la T6. (RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_coym_balance.py` en verde. Con dos empresas
      sintéticas, el balance cierra (entrada = ventas + pérdidas, con la tolerancia decidida: el error admisible de
      la clase del medidor, RM 496-2005-MEM/DM, Tabla N° 01, sustituible por el perfil; el TdR solo dice «coincidirá»)
      en cada sistema y tensión, y un parámetro sin cita deja el resultado `no_conforme`.
      Avance (2026-11-15, f4/VAD-A7): `config/vad/anexo7_coym.json` amplía el TdR registrado con las 24 reglas del
      Anexo 7 y las 17 de los num. 6.9 y 6.10 (6c, b1 y b2), más la remisión del num. 5.12 (errata: remite al numeral 12
      y el CCT es el 11); `config/normativa/rcd_218_2020_manual_costos.json`, el Manual de Costos vigente (RCD
      218-2020-OS/CD, 245-2021-OS/CD y 249-2022-OS/CD, b3), como contraste. `vad/coym.py`: COyM técnico por sistema y
      etapa con el cuadro del registro, costos excluidos y sin contrato, tope salarial, CCT con la tasa diaria efectiva
      (P-4; la proporcional, contraste) y costos compartidos 75/25 con tope del 7,5 % del TdR, que manda para el VAD
      2026-2030, con el aviso frente al Manual vigente, el hueco A7-4 (RM 197-94-EM/VME sin texto) y la base del tope
      P-5 (aVNR del periodo, sustituible). `vad/balance.py`: balance real y adaptado con las fórmulas del A-VI, cierre
      con la diferencia siempre a la vista, demanda máxima de MT y BT y factores de incremento con sus topes y la
      combinación declarada (P-6). v2 (c3): la potencia resultante del balance real sale de
      `vad.balance.potencia_resultante` (cada fila del A-VI con su cita) y el exceso sobre el tope es un hueco
      nombrado (v3: ninguna regla de su ámbito lo asigna; la Nota 2 del Manual es de otro ámbito y solo se avisa). Pruebas en
      `tests/test_vad_coym_balance.py`, pendientes de la corrida de f4.
      Avance (2026-11-15, f4/VAD-FE26): pérdidas estándar del VAD 2026-2030, grupo 1 (RCD 185-2026-OS/CD, vigente del
      2026-11-01 al 2030-10-31, y su IT 607-2026-GRT), en `config/normativa/vad_2026_2030_perdidas.json`: FE y % de 15
      empresas (FE = 1/(1−p)); la 187-2023 y la 223-2023 llevan su vigencia (2023-11-01 a 2027-10-31, la de la 223
      deducida y anotada); `RegistroNormativo.regla_de_empresa` elige la tabla de la fijación que trae a la empresa y
      `regla()` sin empresa lanza si las fijaciones vigentes cubren empresas distintas
      (`tests/test_vad_fe_por_empresa.py`).
- [x] T9. Tablas A y B en Excel con sus fórmulas: localizar en el TdR (anexos 2 y 3) qué son y qué columnas tienen, y
      transcribirlo con la cita. `vad/entregables.py` las escribe con `libro_informe` (`plan_del_libro` y
      `rellenar_con_excel` si hay libro modelo; si no, openpyxl con fórmulas vivas) y las verifica con
      `ERRORES_DE_FORMULA`. Cada celda calculada lleva su fórmula, y cada parámetro, su fuente. (RF-11, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_entregables.py` en verde. El libro se abre
      con openpyxl, ninguna celda calculada es un valor sin fórmula y ninguna da un error de `ERRORES_DE_FORMULA`.
      Hecho (2026-11-15, S-107/108): son los Formatos A y B del anexo 2 (aclaración de RF-11 del 2026-11-15).
      `vad/entregables.py`: `escribir_formatos` (una hoja por formato, prefijo A o B, fórmulas de fila y de columna
      traducidas de las transcritas; «no aplica» (celda sombreada del formato oficial, citada) y hueco (falta el dato)
      son dos estados: el primero se escribe y suma 0, el segundo queda vacío y su fórmula no se escribe; el dato de
      una celda calculada se sustituye por su fórmula y queda en la hoja «Traza» con la celda, el valor y la fórmula) y
      `comprobar_formatos` (cada celda calculada es una fórmula y se evalúa con el intérprete cerrado de
      `vad/formulas.py`). El TdR no publica libro modelo de los formatos: `plan_del_libro` y `rellenar_con_excel` no
      se usan. Evidencia: `D:/csg/PM_IMPL/S107_108/T9T10/`.
- [x] T10. Mapas de densidad y manifiesto de fuentes. Leer y transcribir en `config/vad/anexo9_estructura.json` la
      estructura de archivos del anexo 9, con su cita. Los mapas se reproyectan con `geography.make_transformer` sobre
      una copia. El manifiesto de fuentes lleva, por cada fichero de entrada, su SHA-256, su versión y la entrada del
      registro normativo. (RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_entregables.py` en verde, con la
      estructura de carpetas y nombres del anexo 9 y las huellas del manifiesto recalculadas e iguales.
      Hecho (2026-11-15, S-107/108): `config/vad/anexo9_estructura.json` (amplía `tdr-vad-2026-anexo-r033`): las 8
      entidades con sus 62 campos en orden, con la línea de cada uno (8118-8353), y las 7 tablas de códigos (8355 y
      siguientes; el BT5C repetido de TARIFAS, nombrado). El anexo fija entidades y campos, no carpetas: cada entidad
      va en `<Entidad>.geojson` (`escribir_mapas`, reproyección con `make_transformer` sobre una copia). Manifiesto:
      `manifiesto_fuentes` y `comprobar_manifiesto`. Guion de la transcripción, con su comprobación contra el texto:
      `D:/csg/PM_IMPL/S107_108/T9T10/transcribir_anexo9.py`. Evidencia: `D:/csg/PM_IMPL/S107_108/T9T10/`.
- [x] T11. Observaciones del regulador: `vad/observaciones.py` registra cada observación con su respuesta y la tabla
      o el cálculo al que afecta, en `<espacio>/vad/<id>/observaciones.json`. Una observación que apunta a una tabla
      que no existe se rechaza. (RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_observaciones.py` en verde.
      Hecho (2026-11-15, S-107/108): `vad/observaciones.py` (`registrar_observacion`, `responder`, `pendientes`,
      `cargar_observaciones`); los destinos válidos salen de `vad.tablas_resultados`, de los formatos A y B del anexo 2
      transcrito y de los `usos` del estudio. La cita del numeral 9 (líneas 3496-3497 y 3509-3510) va en el módulo.
      El Informe Definitivo que las usa es la T22. Evidencia: `D:/csg/PM_IMPL/S107_108/T11/`.
- [x] T12. Trabajo en cola, guion y universalidad. `vad/trabajo.py` con `armar_empresa_modelo(ctx, …)` para
      `JobManager.submit(..., lane='engine')`: cancelable entre sistemas, independiente por sistema y con el
      manifiesto escrito siempre, también al cancelar. `tools/vad_estudio.py`, con docstring y `--help` sin
      DIgSILENT. Una fila por fichero nuevo en `CODIGO_FUENTE.md`, con «108». `tests/test_vad_universal.py` falla si
      `src/convertersmartgrid/vad/`, `config/vad/` o `tests/test_vad_*` contienen el nombre, un código, un CRS o un
      periodo de una empresa. (RF-13, RF-1, RF-5, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_trabajo.py tests/test_vad_universal.py` en
      verde, la prueba del inventario de la spec 009 en verde y `.venv/Scripts/python.exe tools/vad_estudio.py --help`
      sale con código 0.
      Hecho (2026-11-15, S-107/108): `vad/trabajo.py` (`armar_empresa_modelo`, `pasos_del_caso`, `leer_caso`) y
      `tools/vad_estudio.py`. Los pasos los da quien llama; el que se lee hoy de ficheros del caso es el del anexo 2, y
      los demás pasos del plan (caracterización, modelo rural, dimensionamiento, costos, COyM y balance) entran con su
      entrada cuando el caso la traiga (T13); un paso sin entrada queda nombrado en el manifiesto. La universalidad
      cazó un periodo escrito en un mensaje de `vad/coym.py` (ahora `coym.para_el_vad`: los periodos de los grupos
      que registra el acto, `vad.grupo.N.periodo`, y su vigencia del registro) y el CRS del perfil de
      una empresa en `tests/test_vad_dimensionamiento.py` y `tests/test_vad_recursos_185.py` (ahora uno sintético).
      Evidencia: `D:/csg/PM_IMPL/S107_108/T12/`.
- [ ] T13. Aceptación de la iteración 1 con el caso de prueba real (grupo 1, sistema típico rural del perfil local):
      el armado corre con `tools/vad_estudio.py` sobre la ruta de `CSG_VAD_CASO`, fuera de git. El nombre de la
      empresa va solo en el perfil local. Un revisor coteja una muestra de celdas de las tablas A y B contra la
      estructura de un estudio publicado de una empresa autorizada, y se comprueba el hash de los vértices del modelo
      rural contra el VNR. Sin DIgSILENT. (RF-5, RF-7, RF-11)
      Hecho cuando: el manifiesto del estudio dice OK en cada sistema, el hash de vértices coincide en todos los
      tramos con geometría y el cotejo del revisor queda anotado en esta tarea, con la ruta de la evidencia.
      BLOQUEADO_POR_DATOS (2026-11-14): no hay caso en `CSG_VAD_CASO`, ni SICODI de la 184-2026 en zip, ni la hoja de
      corriente económica ni los costos unitarios de la empresa, y el cotejo lo hace un revisor. Evidencia y siguiente
      acción: `D:/csg/PM_IMPL/108/T13/BLOQUEO.md`.
- [ ] T14. Anexo 5, modelo geométrico urbano (**posterior a la iteración 1**; empieza cuando la T13 esté cerrada).
      Leer y transcribir en `config/vad/anexo5_urbano.json` el modelo geométrico, con su cita. `vad/modelo_urbano.py`
      elige la red adaptada por densidad de carga según el anexo 5, y la parte urbana de un sistema mixto deja de
      quedar «sin modelar». (RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_modelo_urbano.py` en verde, con dos
      empresas sintéticas, densidades sorteadas y un sistema mixto rural y urbano.
      Avance (2026-11-15, f4/VAD-A5U, las incoherencias del TdR): `config/vad/anexo5_urbano.json` amplía el TdR
      registrado con las 22 reglas del Anexo 5 (cc, z26a y z26b; 105 fórmulas en la sintaxis de `vad/formulas.py`),
      TRI_AREA como fórmula, la tasa «i» (`vad.anexo5.tasa_i`, remisión del cap. 5 al art. 79 de la LCE, líneas
      1347-1350) y los símbolos sin definir (`vad.anexo5.entradas_sin_definir`). `vad/modelo_urbano.py` aplica las
      decisiones de 28: forma cerrada de la ecuación circular R_BT/TRI_AREA/NTRI con residuo ≤ 1e-9 y huecos nombrados;
      lectura (a) del paréntesis de NTRI, con la (b) rechazada; los dos +5 % sumados (×1,10, con el compuesto ×1,1025
      en el aviso); CCT_INICIAL, b, K_CT, cr, Ic y clientes_AT/MT como entradas sin valor por defecto; 1/FRC = Kim del
      Anexo 6 con `pide_economia.frc`; Te con la función de pérdidas común; cp_MT con los factores de 1000 y su prueba de
      unidades. v2 (c3): el residuo sustituye T en las fórmulas transcritas de cada rama; en la MAD la forma de c3 y
      la propia coinciden, y en el resto solo cumple la propia. Pruebas en `tests/test_vad_modelo_urbano.py`, pendientes
      de la corrida de f4. Falta el resto de la T14:
      el enumerador de escenarios por densidad y el sistema mixto.
- [ ] T16. Registro de resultados y cálculo del VAD. Transcribir en `config/vad/tdr_vad_2026_resultados.json`
      (amplía el TdR registrado), con su cita, los conceptos de cada ámbito (LCE y LGER), las variantes de cada
      concepto, las fórmulas del cargo fijo y del VAD de cada nivel, la ponderación a nivel empresa, la tasa de
      actualización, la fórmula del FEE y los parámetros de la fórmula de reajuste. `vad/formulas.py` evalúa una
      fórmula del registro con un intérprete cerrado (solo aritmética, variables y `suma`), y `vad/resultados_vad.py`
      calcula, por sistema y ponderado a nivel empresa, el cargo fijo, el VAD de cada nivel y su variante, el FEE y
      los factores de reajuste, cada valor con la regla que lo dio. Lo que el TdR no da en forma cerrada (la fórmula de
      reajuste) queda como hueco con su cita. (RF-16, RF-9, RF-13)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_resultados.py` en verde. Un caso sintético
      calculado a mano coincide con dos empresas sintéticas; un registro sintético con otras variantes (no `_SER`) da
      sus propias variantes; una variable que falta, una división entre cero y una fórmula fuera del intérprete son
      huecos o errores nombrados, nunca 0; y una regla no obligatoria deja el resultado `no_conforme`.
      Avance (2026-11-15, f4/VAD-FE26): fórmulas de reajuste (8) a (12) de la RCD 185-2026-OS/CD (FAVADMT, FAVADBT,
      FAVADSED, FACF y FACER), sus parámetros, valores base (TC0, IPM0, IPCu0 e IPAl0, diciembre de 2025), coeficientes
      A, B, C y D por empresa y nivel (A+B+C+D = 1) y su aplicación (art. 4), registrados con su cita en
      `config/normativa/vad_2026_2030_perdidas.json`; los coeficientes van por empresa (`regla_de_empresa`).
      Avance (2026-11-15, f4/RN-IMP): la RCD 185-2026-OS/CD lleva en `impugnada` los seis recursos de
      reconsideración de la hoja informativa de Osinergmin (audiencia del 27-11-2026), pendientes de resolución, con
      los conceptos que impugna cada uno y su cita. Solo CVC Energía impugna FE, los de MT (PPMT y PEMT) de su SDT2:
      el aviso va en esas filas (`<clave>.<fila>`), no en BT, y lo que pide queda como dato del recurso; Egepsa los
      excluye y nadie impugna los coeficientes. ESDE Selva va como tercero, con su RUC, sin casarla con ninguna
      empresa. El estudio (`EstudioVad.avisos`, en `estudio.json`) lleva
      el aviso de los conceptos impugnados que usa, sin cambiar su estado: la 185 sigue obligatoria (art. 216.1 del
      TUO de la LPAG). Pruebas en `tests/test_vad_recursos_185.py` (108:RF-9).
- [ ] T17. Incorporación del PIDE (contrato 072 → 108, versión `pide_vad_v1`): `vad/pide_vad.py` lee el PIDE aprobado
      que entrega la 072 (acto de aprobación, periodo, moneda y, por nivel de tensión y año, la inversión, el COyM y la
      demanda adicionales), calcula la anualidad con el factor registrado y el VAD ajustado con la fórmula registrada
      del numeral 7.5. El estudio guarda si la empresa está en el ámbito del FONAFE (`EstudioVad.ambito_fonafe`;
      sin declarar, `None`). La spec 072 no se toca aquí: lo que debe decir va en la entrega de esta tarea. (RF-17,
      RF-16)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_pide.py` en verde. Sin PIDE aprobado (o con
      el ámbito sin declarar, otro periodo u otra moneda) hay aviso y no se incorpora nada; con el PIDE de prueba el
      VAD ajustado coincide con el cálculo a mano.
- [ ] T18. Calidad de servicio: `vad/calidad.py` compara los indicadores calculados de la empresa modelo con los
      límites del registro normativo, por sistema, y nombra el que no cumple. Un indicador sin límite registrado o sin
      valor calculado es un hueco nombrado, no un «cumple». (RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_calidad.py` en verde, con un caso que no
      cumple, uno que cumple y uno con el límite sin registrar. Los límites reales de la NTCSE y la NTCSER quedan
      BLOQUEADOS hasta transcribirlos (`D:/csg/PM_IMPL/108/S3_ENTREGA.md`, bloqueo B2).
      Avance (2026-11-15, f4/VAD-CAL): `vad/calidad.py` sigue el criterio del 6.11 (antes comparaba una media por sistema): SAIFI y SAIDI vigentes de la RCD 074-2004 consolidada con la 177-2012 (mensual por sistema y anual en MT con los filtros del Anexo 3), N y D por cliente (NTCSE) o NIC y DIC por SER (NTCSER), el Cuadro 21 con el % de clientes que exceden N' y D' por semestre y los Cuadros 22 y 23. Límites transcritos de los textos oficiales en las mismas entradas de la NTCSE y la NTCSER, el +30 % del ST 2 (DS 009-99-EM, art. 4) y la RCD 074-2004 como norma nueva; huecos nombrados: RM 163-2011 y curvas de distribución. El bloqueo B2 se levanta con ellos. Inaplicación por DS 013 y 020-2026: tarjeta CAL-DS.
- [ ] T19. Costos de explotación: `vad/costos_explotacion.py` suma por rubro del registro (VNR no eléctrico,
      explotación técnica, comercial, indirectos y adicionales) solo las partidas dimensionadas con su fuente, y lleva
      el costo real en una columna rotulada como referencia. (RF-19)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_costos_explotacion.py` en verde. Un rubro con
      solo el costo real queda «sin dimensionar» y fuera del total; una partida sin fuente se rechaza; dos monedas no se
      suman.
- [ ] T20. Tablas de Resultados: `vad/tablas_resultados.py` escribe en Excel una hoja por tabla que liste el registro
      (numeral 9), con su título, sus filas por sistema eléctrico y el total con fórmulas, más un índice. (Aclaración de
      RF-11; RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_tablas_resultados.py` en verde. Con el
      registro sintético de 16 tablas salen 16 hojas y con uno de 3, tres; una tabla sin datos es un hueco nombrado en
      el índice; ninguna celda da un error de `libro_informe.ERRORES_DE_FORMULA`; un dato de una tabla que el registro
      no lista se rechaza.
- [ ] T21. Informes en Word: `vad/informes.py` escribe el Informe de Resultados Relevantes con los apartados del
      anexo 3 registrado y el Informe del Estudio con la estructura del numeral 9 registrada; cada cifra sale del
      estudio con su origen o queda como hueco nombrado; el PDF integrado se pide a `informe_docx.exportar_pdf` y, si
      no sale, se dice el motivo y el Word queda hecho. (RF-14, RF-15)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_informes.py` en verde. El índice del Word
      coincide con la estructura del registro sintético; un apartado sin contenido es un hueco nombrado; una cifra sin
      origen se rechaza; el PDF sale con un exportador de prueba y su fallo se informa.
- [ ] T22. Informe Definitivo (numeral 9.2): con las observaciones de la T11, `vad/informes.py` arma los documentos
      que liste el registro para el definitivo y el informe de respuestas, cada una con su sustento y la tabla o el
      cálculo que cambió. Empieza cuando la T11 esté integrada. (Aclaración de RF-12; RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_informe_definitivo.py` en verde; una respuesta
      sin sustento o sin la tabla o el cálculo que cambió se rechaza.
- [ ] T23. Registro de la Guía del VNR: `config/normativa/rcd_232_2017.json` con la vigencia del art. 2, la Tabla
      N° 1 y los parámetros del art. 22, la fórmula del art. 17.2 y las instalaciones del art. 16.4, con su cita
      literal; `tools/extraer_anexo6_vnr.py` saca las tablas de equivalencia del Anexo 6 del PDF oficial a
      `config/vnr/anexo6_equivalencias.json` con su huella. (RF-20)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vnr_guia_registro.py` en verde; una tabla que no
      cuadra con el texto oficial se rechaza; el extractor reproduce el JSON byte a byte desde el PDF.
- [ ] T24. Zonificación del art. 22: `vad/vnr_guia.py` arma las cuadrículas UTM de 1000, 500 y 250 m, su densidad con
      la máxima demanda de las SED (FC 0,5 y coincidencia 1,0 para el AP), la zona de la Tabla N° 1, la predominante
      para la aislada y los mapas de MT y BT. (RF-21)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vnr_guia_zonas.py` en verde con dos concesiones
      sintéticas; una cuadrícula de 1000 m con 4 MW queda «Muy Alta» y no se subdivide; una de densidad cero se elimina.
- [ ] T25. Adaptación por sector típico (arts. 23 a 44) con las tablas del Anexo 6: metrado existente y adaptado por
      tramo, con la regla que lo cambió. (RF-22)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vnr_guia_adaptacion.py` en verde; un tramo aéreo
      de AA protegido en zona Media no corrosiva sale en AA desnudo; uno subterráneo de 70 mm² en zona Baja pasa a aéreo.
- [ ] T26. Cálculo del VNR (art. 17.2) con el SICODI de `CSG_SICODI` leído por `costos_fuentes.leer_sicodi`, formatos
      A1, B1, C1 y D1 del Anexo 5, y la anualidad del VNR real con los factores del VAD para la TIR y el contraste
      con la empresa modelo. (RF-23, RF-24)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vnr_guia_calculo.py` en verde; una instalación
      sin costo estándar es un hueco nombrado; la anualidad del VNR real cita sus factores y la huella del SICODI.
- [ ] T27. Altas y bajas del art. 18 entre dos inventarios VNR, con su efecto en el VNR. (RF-25)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vnr_guia_altas_bajas.py` en verde.
- [ ] T28. Estudio VNR desde el inventario VNR-GIS y la web: `vad/vnr_estudio.py` lee cada código VNR del Anexo 2 al
      revés, zonifica con las SED del inventario, adapta, codifica y valoriza; `web/vnr_api.py` lo lanza como trabajo
      del motor con el canonical.json y el SICODI subidos, y la pestaña «Estudio VNR» entrega el libro de formatos.
      (RF-21, RF-22, RF-23, RF-24)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vnr_estudio.py tests/test_vnr_api.py` en verde
      y `npm test` en verde; una SED sin demanda y un código desconocido son huecos nombrados; un fichero que no es un
      inventario o un SICODI se rechaza con 400.
- [ ] T15. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "108:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-25 y la suite está en verde.
