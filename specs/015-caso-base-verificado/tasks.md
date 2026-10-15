# Tareas — Spec 015

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Sonda en DIgSILENT sobre una copia de un proyecto ya importado, borrada al
      terminar: qué atributos de `ElmLod` guarda el escenario de operación (`plini`,
      `qlini`, `scale0`, `outserv`, `i_scale`) y si una carga escrita con el escenario de
      «Sin proyecto» activo deja igual el «Caso base». (Decisión del plan; RF-19, RF-26)
      Hecho cuando: informe JSON en `output/` y resultado anotado en el plan. Si `i_scale`
      no es dato de operación, se para y se pregunta al usuario.
- [x] T2. `src/igea_dgs/capacidades.py`: capacidades, grupo de conexión y tensión de baja
      del DGS, y su comparación. (RF-6, RF-7, RF-11, RF-32, RF-33)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_capacidades.py` en verde.
- [x] T3. Verificación completa del «Caso base» en `powerfactory_acceptance.py`, también
      con `--existing-project` (que exige `--manifest`): caso «Caso base», conectividad de
      cargas, capacidades, flujo sin remedios, variaciones activas e informe por
      comprobación. (RF-1 a RF-9, RF-12, RF-31 a RF-33)
      Hecho cuando: `pytest -q tests/test_powerfactory_existing_project_acceptance.py tests/test_powerfactory_gate.py` en verde.
- [x] T3b. Corrección del grupo de conexión y de la tensión de baja de los transformadores
      de SED antes del flujo, con copia del tipo si es compartido, e informe de cada
      corrección. (RF-34 a RF-36)
      Hecho cuando: las mismas pruebas de T3 en verde, con un caso de tipo compartido.
- [x] T4. Estado del «Caso base» por alimentador en el vínculo; fuera
      `IDENTIDAD_VERIFICADA_PENDIENTE_CONVERGENCIA` y la promoción tras calibrar.
      (RF-10, RF-13, RF-22)
      Hecho cuando: `pytest -q tests/test_powerfactory_binding.py tests/test_native_project_gate.py` en verde.
- [x] T5. Web: «Verificar el Caso base» (servicio, ruta y paso 1 de la pestaña), con la
      tabla por alimentador y comprobación, repetible. (RF-9, RF-14)
      Hecho cuando: pruebas de la web en verde y `cd frontend && npm run build` sin errores.
- [x] T6. `casos_pf`: `preparar_sin` y `preparar_con`, solo con el «Caso base»
      verificado y sin variaciones en «Sin proyecto». (RF-16 a RF-18, RF-27, RF-28)
      Hecho cuando: `pytest -q tests/test_casos_pf.py` en verde.
- [x] T7. Calibración solo de cargas: sin variación, con el escenario de «Sin proyecto»
      activo, sin comprobaciones de red; los alimentadores sin base verificada se informan
      y los demás se calibran. (RF-13, RF-15, RF-17, RF-19 a RF-21, RF-23 a RF-26, RF-37)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py tests/test_ajuste_cabecera.py` en verde.
- [x] T8. `base_del_ajuste` sin variación y la última calibración guardada en el espacio
      para el cambio manual de la 014. (RF-22, RF-26; 014:RF-10)
      Hecho cuando: `pytest -q tests/test_cargas_pf_web.py tests/test_estudios_pf_web.py` en verde.
- [x] T9. Cargas nuevas: «Con proyecto» con `preparar_con` antes de insertar; variaciones
      solo allí, una por carga. (RF-28, RF-29)
      Hecho cuando: `pytest -q tests/test_cargas_pf_guion_007.py tests/test_cargas_pf_guion.py` en verde.
- [x] T10. Aviso de red cambiada contra la huella del «Caso base» verificado; una
      calibración no lo dispara. (RF-19, RF-30)
      Hecho cuando: una prueba con `015:RF-30` en verde.
- [x] T11. Notas en las specs 006, 011 y 014 sobre los RF que cambia la 015, y revisión de
      las tareas pendientes de la 014; `CODIGO_FUENTE.md` y `docs/MANUAL_COMANDOS.md` al
      día. (Trazabilidad)
      Hecho cuando: `pytest -q tests/test_inventario.py` en verde.
- [x] T14. Convergencia sin bloqueo: si el flujo del «Caso base» no converge, se reduce por
      igual la demanda hasta el mayor factor que converge y se graba en su escenario; con
      «Sin proyecto» creado, solo se avisa; el flujo deja de bloquear. (RF-8, RF-10, RF-38 a RF-40)
      Hecho cuando: `pytest -q tests/test_caso_base_verificado.py` en verde.
- [x] T15. La convergencia solo al importar: verificar un proyecto existente no corre el
      flujo ni cambia cargas; el oráculo antes de importar, citado. (RF-8, RF-39, RF-41)
      Hecho cuando: `pytest -q tests/test_caso_base_verificado.py tests/test_caso_base_web.py tests/test_web_api.py` en verde.
- [x] T16. Fijas con su P y Q y factor 1; escaladas con su P y Q del archivo y un mismo
      ``scale0``; sin el remedio de dependencia de tensión; el doble aplica ``scale0`` en el
      flujo. (RF-42 a RF-45)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera.py tests/test_ajuste_cabecera_guion.py tests/test_casos_pf.py` en verde y la calibración de CA101 desde cero repetida en DIgSILENT.
- [x] T17. Los ajustes del flujo que necesitó la calibración se quedan en «Sin» y «Con
      proyecto» si cuadra; la columna «Alimentador» se resuelve con metadatos sin red; la
      interfaz revisada. (RF-46)
      Hecho cuando: suite en verde y CA101 desde cero con «Sin proyecto» convergiendo en DIgSILENT.
- [x] T18. Validación física de la calibración: cada fija y cada escalada consume en el
      flujo lo escrito; balance de la cabecera; ajuste del flujo nombrado como causa; carga
      sin resultado no verificada. (RF-47 a RF-52)
      Hecho cuando: `pytest -q tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T19. Prueba en DIgSILENT con CA101 de T18: la calibración en «Sin proyecto» cuadra con
      las fijas consumiendo su P y Q, o el informe nombra las cargas y el ajuste del flujo
      que lo impide. (RF-47 a RF-52)
      Hecho cuando: el informe del ajuste real trae `validacion_posterior_nativa.balance`.
      Resultado del 2026-10-15 en `20261014-205212_IGEA_CA101`, con la última calibración
      del espacio (06:50) (`output/spec015/T19_ajuste_CA101.json`; sondas de solo lectura
      `T19_sonda_*.json`): cuadra la cabecera en 5994,9 kW (−0,09 %), pero la validación
      física no pasa: 71 cargas no consumen lo escrito; las 9 fijas escriben 3677,0 kW y
      consumen 2680,5 kW (SE20701, 1582,3 → 980,5 kW a 0,787 pu); causa nombrada
      `iopt_lev=1`. Balance: fijas 2680,5 + escaladas 2730,8 + pérdidas 583,6 = 5994,9 kW.
      `FALLO_VALIDACION_NATIVA`, cargas revertidas, nada grabado. Las 9 fijas están en su
      SED (barra BT de su transformador), con `i_scale=0` y factor 1; las 160 escaladas con
      un mismo factor. Sin `iopt_lev`, «Sin proyecto» no converge con 6 MW de cargas PQ:
      pendiente de decisión del usuario (modelo de la red).
      Sonda sobre una copia (borrada) el mismo día: en una carga desequilibrada (`i_sym=1`)
      DIgSILENT ignora `plini` escrito y lo deriva de la suma de las fases, que son dato de
      la red. La calibración escribe las fases, que se ven también desde el «Caso base»;
      su flujo equilibrado sigue usando el `plini` de su escenario (SE20069: 565,9 kW, el
      del archivo), así que RF-19 se cumple para el flujo equilibrado, no para uno
      desequilibrado. Evitarlo pide una variación o cambiar `i_sym`, los dos fuera de lo
      decidido. La web muestra el balance físico y el fallo de la validación (RF-49, RF-50).
- [x] T20. Escaladas por potencia instalada (P base = kVA × FP) con un mismo factor de
      escala; FP de las escaladas del perfil de empresa (Electro Dunas 0,98) o, sin él, el
      de la máxima; fijas con su EA/ERI; el informe y la web dicen de dónde sale cada uno.
      (RF-44, RF-45, RF-53 a RF-58)
      Hecho cuando: suite de web, front y calibración en verde y la calibración real de CA101.
      Resultado del 2026-10-15 en `20261014-205212_IGEA_CA101`
      (`output/spec015/T20_ajuste_CA101_kva_fp098.json`): cuadra en 5985,4 kW (−0,24 %) en 3
      flujos, sin adaptar el modelo, y la validación física pasa en las 169 cargas: fijas
      3677,0 kW, escaladas 1212,7 kW (factor 0,087 de su kVA), pérdidas 1095,7 kW. Grabado en
      «Sin proyecto» y «Con proyecto»; registrado en el espacio de la web. Pero la red así
      no es creíble: pérdidas del 18 %, 0,635 pu en SE20701 y 3137 kVAR en la cabecera frente
      a 302 medidos. Pendiente del usuario: el modelo físico (tensión de la fuente 1,00 pu,
      dos bancos en la misma barra «Terminal», clientes sobre transformadores pequeños).
- [x] T21. Clientes que piden más que su transformador, avisados; bancos instalados del
      propio proyecto listados en el informe y en la web, sin crear ni tomar nada de otro
      proyecto ni alimentador. (RF-59 a RF-61)
      Hecho cuando: suite de web, front y calibración en verde y una simulación (sin
      escribir) en DIgSILENT con CA101.
      Resultado del 2026-10-15 (simulación sobre `20261014-205212_IGEA_CA101`): los 3 bancos
      de 300 kvar en 10 kV, en servicio, dos en «Terminal» y uno en «Terminal(1)»; avisadas
      SE20859 (509 % en kVA aparentes), SE21082 (236 %), SE20444 (125 %) y SE20426 (120 %,
      FP 0,43); ningún cambio manual, porque la calibración registrada en la web coincide
      con DIgSILENT. 612 pruebas de web, front y calibración en verde.
- [x] T22. Cambio manual del operador, pedido por el usuario el 2026-10-15 (no es código de
      la aplicación): los transformadores de las SED fijas que pedían más que su potencia,
      a la menor potencia normalizada con la máxima ≤ 80 %, con los parámetros de la NTP
      370.400-2013 (Tabla 6 de la especificación de FONAFE, 2017: trifásicos, AT ≤ 17,5 kV):
      SE20859 50 → 400 kVA y SE20444 250 → 400 kVA (Po 968 W, Pc 5550 W, Io 1,84 %, uk 4 %);
      SE21082 100 → 315 kVA y SE20426 200 → 315 kVA (Po 837 W, Pc 4533 W, Io 2,19 %, uk 4 %).
      Tipos propios `TR_400kVA_NTP370400` y `TR_315kVA_NTP370400`, copiados del `TR_315kVA`
      del archivo (grupo Dyn5, 10/0,22 kV), sin tocar los tipos que usan otras SED. En «Sin
      proyecto», en la red, sin variación (se ve también desde el «Caso base», como decidió
      el usuario). Recalibrado (`output/spec015/T22_ajuste_CA101_trafos_ntp.json`): 5987,9 kW
      (−0,20 %), validación física correcta, ninguna fija sobre su transformador, pérdidas
      1050 kW (17,5 %), 0,637 pu en SE20701; registrado en el espacio de la web.
- [ ] T12. Prueba en DIgSILENT con CA101, sobre el proyecto existente y sin datos
      inventados: la verificación lista lo que falla; corregido, pasa; se crea
      «Sin proyecto»; la calibración solo cambia su escenario y el «Caso base» queda igual;
      una inserción crea «Con proyecto» y una variación por carga. (Criterios de finalización)
      Hecho cuando: informe JSON de cada paso en `output/` y resultados anotados aquí.
      Resultado del 2026-10-14, sobre una copia de `20261013-121930_IGEA_CA101` (borrada al
      terminar; informe superado, en `output/_historico/2026-10-14_spec015/`): se verificó el caso «Caso base»
      con la geografía de la ejecución MDB del 13/10. Pasan el GPS de barras (1002 de 1002),
      el trazado de líneas (482 de 482), la conectividad, el diagrama y la capacidad de
      todos los equipos; ningún grupo de conexión ni tensión de baja que corregir. Avisos: 8
      transformadores de 800 kVA donde el archivo da 250 kVA (correcciones del operador), 2
      tramos partidos a mano y los 3 bancos del catálogo. **Bloquea el flujo: no converge**
      (ComLdf 1, divergencia por exceso de carga), y el «Caso base» queda NO_VERIFICADO.
      Desde cero, el mismo día (el usuario pidió no trabajar con el proyecto existente): DGS
      de CA101 de la ejecución MDB del 13/10 importado en `PRUEBA_015_CA101_NUEVO`
      (`output/spec015/T12_importacion_CA101.json`). «Caso base» VERIFICADO: GPS, trazado,
      conectividad, diagrama y capacidades bien, y el flujo converge con las cargas del
      archivo sin reducir nada (3016,2 kW). Falló, aparte, la columna «Alimentador» de las
      cargas (`powerfactory_metadata`, fuera de la 015; el 13/10 sí se asignó). La
      calibración (máxima 6000 kW de L-CA131, `output/spec015/T12_ajuste_CA101.json`) creó
      «Sin proyecto», cuadró a −0,24 % en kW con AVISO_KVAR y escribió 95 cargas en su
      escenario, sin ninguna variación; el «Caso base» sigue con 3016,2 kW y converge.
      Hallazgo: el flujo de «Sin proyecto» con su ComLdf normal no converge (rc 1), porque
      el cuadre necesitó dos remedios (iopt_lev, iopt_pq) que se restituyen al terminar
      (006:RF-16). Pendiente de decisión del usuario.
      Repetida tras T16 (reimportado desde cero; `output/spec015/T12_ajuste_CA101.json`): 6
      SED fijas con su P y Q y 89 escaladas con su P y Q del archivo y un mismo factor de
      escala de 3,67; cuadró a −0,04 % en kW (AVISO_KVAR), sin variaciones. El «Caso base»
      sigue con 3016,2 kW y converge. Sigue el hallazgo: hizo falta el remedio
      «adaptación automática del modelo» (iopt_lev), que se restituye, y «Sin proyecto» no
      converge con su ComLdf normal.
      Tras T17 (reimportado desde cero otra vez): la columna «Alimentador» se asigna (337
      objetos, metadatos sin red); calibración a −0,13 % en kW con los ajustes del flujo
      itrlx=75, iStepAdapt=1 e iopt_lev=1 conservados en «Sin proyecto», que ahora converge
      con su flujo (rc 0); el «Caso base» sigue en 3016,2 kW y converge.
      Proyecto CA101 existente, a pedido del usuario el mismo día (excepción expresa al
      RF-19, con respaldo previo `RESPALDO_CA101_20261014`;
      `output/spec015/T12_correccion_CA101_existente.json`): su «Caso base» no convergía;
      la demanda de sus 168 cargas se redujo por igual al 91,9 % en su escenario
      «Operation Scenario» y converge; «Sin proyecto» converge también.
      Verificado desde la web a las 19:04 del mismo día, sobre ese proyecto y con el DGS de
      CA101 reconvertido de la misma `.mdb` (idéntico byte a byte al del 13/10;
      `output/spec015/T12_caso_base_CA101_existente.json`): «Caso base» VERIFICADO, con el
      GPS, el trazado, la conectividad, el diagrama y las capacidades bien, y solo los avisos
      de los 8 transformadores de 800 kVA; el vínculo del proyecto lo guarda. Los informes
      del 13/10 de CA101 se apartaron a `output/_historico/2026-10-13_ca101/`.
      Pendiente, a cargo del usuario: una inserción de cargas nuevas que cree «Con
      proyecto» con una variación por carga.
- [x] T13. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "015:RF-[0-9]+" tests | sort -u` lista los 46 RF y la suite
      con las variables `IGEA_*` pasa.
