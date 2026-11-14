# Tareas — Spec 108

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

Las tareas T1 a T13 son la **iteración 1, el anexo 6 rural**. La T14 (anexo 5 urbano, RF-6) es posterior y no
empieza hasta que la T13 esté cerrada. Ninguna tarea modifica `web/services.py`, `pide_economia.py`,
`adaptadores/entrada/vnr/**` ni `catalog_resolution.py` (son de f9). Ninguna fórmula del TdR se escribe sin haberla
leído: las tareas que la necesitan empiezan por leer el anexo y transcribirlo con su cita (fichero y líneas de la
copia local `output/normativa_pide_20261025/textos/fb5341703a3c….txt`, o la página del PDF oficial).

- [ ] T1. Paquete `src/convertersmartgrid/vad/` y registro del estudio: `vad/estudio.py` con `EstudioVad` (empresa
      del perfil, grupo, periodo, versión del TdR y estado), guardado en `<espacio>/vad/<id>/estudio.json`, aparte del
      PIDE y del PIT. Un estudio no lee ni escribe en las carpetas del PIDE. (RF-1)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_estudio.py` en verde, con dos empresas
      sintéticas y una prueba de que crear un estudio VAD no cambia ningún fichero del PIDE.
- [ ] T2. Registro normativo. Leer y transcribir en `config/vad/tdr_vad_2026.json` la RCD 174-2025-OS/CD, la
      RCD 033-2026-OS/CD y el índice de anexos del texto modificado (copia local, líneas 142-150), cada entrada con
      acto, anexo, versión, `estado_juridico` (vocabulario del registro común `registro_normativo.py`, 107 T1: vigente_comprobada, modificada, prepublicada, no_verificada…), URL, fichero local, líneas, SHA-256,
      fecha de lectura, moneda e IGV. Leer el anexo 1 y comprobar a qué grupo pertenece cada empresa del caso, porque
      G0 solo lo dedujo de los considerandos. Las entradas del TdR VAD se cargan en el registro normativo común `src/convertersmartgrid/registro_normativo.py` (lo crea la 107 T1; si la 108 va antes, lo crea esta tarea con ese mismo contrato); `vad/` solo lo usa, sin un registro propio (P5). (RF-9,
      RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_normativa.py` en verde. Las pruebas cubren
      un TdR `proyecto` o `pendiente`, un `igv: sin_leer` y una entrada sin cita, y en los tres casos el estudio queda
      `no_conforme`. Un cambio de versión a mitad del estudio lo deja `desactualizado` y nombra lo afectado.
- [ ] T3. Anexo 2. Leer y transcribir en `config/vad/anexo2_formatos.json` los formatos de información técnica,
      comercial y económica, con cada tabla, campo, unidad y periodo, y su cita. `vad/anexo2.py` con `validar_tablas`
      para el inventario VNR, las tablas técnicas, comerciales y contables y los costos. (RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_anexo2.py` en verde. Una tabla obligatoria
      que falta, un campo vacío y una unidad distinta se informan por tabla y campo, y la tabla de salida no trae
      ningún valor que no estuviera en la entrada.
- [ ] T4. Anexo 4. Leer y transcribir en `config/vad/anexo4_caracterizacion.json` la definición del factor de carga,
      de la simultaneidad y de las curvas MT/BT, con su cita. `vad/caracterizacion.py` las calcula con
      `demanda_medida` (`maximas`, `Cabecera`, `curva_de_registros`, `reducir_curva`, `curvas_de_clientes`). Una SED
      sin medición se nombra; solo recibe una curva si el anexo transcrito lo prevé, y con esa cita. (RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_caracterizacion.py` en verde, con curvas
      sintéticas sorteadas cuyos factores se conocen de antemano y con el caso de la SED sin medición.
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
- [ ] T6. Dimensionamiento de la empresa modelo con el motor físico: `vad/dimensionamiento.py` adapta el conductor y
      la potencia de transformación, y calcula las pérdidas, con `oraculo.red_pandapower` y `oraculo.validar`, según
      los criterios transcritos en la T5. Ningún vértice cambia. Un conductor sin `rline` o `xline` es un hueco
      nombrado, no 0 Ω. (RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_dimensionamiento.py` en verde. En una red
      sorteada con SED sobredimensionadas, su potencia cambia y el hash de vértices no; y hay un caso con un conductor
      sin impedancia.
- [ ] T7. Costo estándar: `vad/costos.py` valora la red **dimensionada** con el SICODI (`costos_fuentes.leer_sicodi`)
      mediante `valorar_obra` y `metrados.valorar_metrados`, con la fuente, la moneda y el IGV de cada elemento según
      el registro de la T2. `CostoEstandar` solo se construye con un `Dimensionamiento`, y el VNR real va solo como
      columna de referencia. (RF-7, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_costos.py` en verde. Construir un costo
      estándar con el inventario sin dimensionar lanza `VadError`; lo que no cruza con el SICODI queda nombrado y
      fuera del total; cada elemento valorado lleva su fuente; y dos monedas no se suman.
- [ ] T8. Anexo 7 y balance. Leer y transcribir en `config/vad/anexo7_coym.json` la metodología del COyM técnico, y
      la de las pérdidas estándar y del balance de potencia y energía, con su cita. `vad/coym.py` y `vad/balance.py`
      los calculan por sistema y por tensión, sobre los resultados de la T6. (RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_coym_balance.py` en verde. Con dos empresas
      sintéticas, el balance cierra (entrada = ventas + pérdidas, con la tolerancia transcrita) en cada sistema y
      tensión, y un parámetro sin cita deja el resultado `no_conforme`.
- [ ] T9. Tablas A y B en Excel con sus fórmulas: localizar en el TdR (anexos 2 y 3) qué son y qué columnas tienen, y
      transcribirlo con la cita. `vad/entregables.py` las escribe con `libro_informe` (`plan_del_libro` y
      `rellenar_con_excel` si hay libro modelo; si no, openpyxl con fórmulas vivas) y las verifica con
      `ERRORES_DE_FORMULA`. Cada celda calculada lleva su fórmula, y cada parámetro, su fuente. (RF-11, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_entregables.py` en verde. El libro se abre
      con openpyxl, ninguna celda calculada es un valor sin fórmula y ninguna da un error de `ERRORES_DE_FORMULA`.
- [ ] T10. Mapas de densidad y manifiesto de fuentes. Leer y transcribir en `config/vad/anexo9_estructura.json` la
      estructura de archivos del anexo 9, con su cita. Los mapas se reproyectan con `geography.make_transformer` sobre
      una copia. El manifiesto de fuentes lleva, por cada fichero de entrada, su SHA-256, su versión y la entrada del
      registro normativo. (RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_entregables.py` en verde, con la
      estructura de carpetas y nombres del anexo 9 y las huellas del manifiesto recalculadas e iguales.
- [ ] T11. Observaciones del regulador: `vad/observaciones.py` registra cada observación con su respuesta y la tabla
      o el cálculo al que afecta, en `<espacio>/vad/<id>/observaciones.json`. Una observación que apunta a una tabla
      que no existe se rechaza. (RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_observaciones.py` en verde.
- [ ] T12. Trabajo en cola, guion y universalidad. `vad/trabajo.py` con `armar_empresa_modelo(ctx, …)` para
      `JobManager.submit(..., lane='engine')`: cancelable entre sistemas, independiente por sistema y con el
      manifiesto escrito siempre, también al cancelar. `tools/vad_estudio.py`, con docstring y `--help` sin
      DIgSILENT. Una fila por fichero nuevo en `CODIGO_FUENTE.md`, con «108». `tests/test_vad_universal.py` falla si
      `src/convertersmartgrid/vad/`, `config/vad/` o `tests/test_vad_*` contienen el nombre, un código, un CRS o un
      periodo de una empresa. (RF-13, RF-1, RF-5, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_trabajo.py tests/test_vad_universal.py` en
      verde, la prueba del inventario de la spec 009 en verde y `.venv/Scripts/python.exe tools/vad_estudio.py --help`
      sale con código 0.
- [ ] T13. Aceptación de la iteración 1 con el caso de prueba real (grupo 1, sistema típico rural del perfil local):
      el armado corre con `tools/vad_estudio.py` sobre la ruta de `CSG_VAD_CASO`, fuera de git. El nombre de la
      empresa va solo en el perfil local. Un revisor coteja una muestra de celdas de las tablas A y B contra la
      estructura de un estudio publicado de una empresa autorizada, y se comprueba el hash de los vértices del modelo
      rural contra el VNR. Sin DIgSILENT. (RF-5, RF-7, RF-11)
      Hecho cuando: el manifiesto del estudio dice OK en cada sistema, el hash de vértices coincide en todos los
      tramos con geometría y el cotejo del revisor queda anotado en esta tarea, con la ruta de la evidencia.
- [ ] T14. Anexo 5, modelo geométrico urbano (**posterior a la iteración 1**; empieza cuando la T13 esté cerrada).
      Leer y transcribir en `config/vad/anexo5_urbano.json` el modelo geométrico, con su cita. `vad/modelo_urbano.py`
      elige la red adaptada por densidad de carga según el anexo 5, y la parte urbana de un sistema mixto deja de
      quedar «sin modelar». (RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_vad_modelo_urbano.py` en verde, con dos
      empresas sintéticas, densidades sorteadas y un sistema mixto rural y urbano.
- [ ] T15. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "108:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-13 y la suite está en verde.
