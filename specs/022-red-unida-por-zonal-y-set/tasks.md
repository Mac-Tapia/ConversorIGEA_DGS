# Tareas 022 — Red unida por zonal y SET

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]` y pare.

- [x] T1. `estructura.py`: modelo, lectura del perfil y de Excel, validación de filas, y
      `asignar` con «Sin SET», faltantes y omitidos. (RF-1, RF-2, RF-4, RF-5, RF-19, RF-20,
      RF-25b)
      Hecho cuando: `pytest tests/test_estructura.py` en verde (tablas sorteadas).
- [x] T2. Transcribir la tabla pública a `config/perfiles/electro_dunas.estructura.json` y
      enlazarla desde el perfil de Electro Dunas, con las siglas de cada SET. (RF-3, RF-46)
      Hecho cuando: el perfil carga 4 zonales y todos los alimentadores de la tabla.
- [x] T3. `estructurar` en `combine.py`: barras de SET por tensión, interruptor de cabecera
      cerrado para todos, una fuente por barra. (RF-10 a RF-13, RF-21)
      Hecho cuando: pruebas sintéticas de la red unida estructurada en verde.
- [x] T4. `enlaces.py`: puntos de enlace con sus SET, caminos cerrados (entre SET, entre
      alimentadores, anillos) y qué abrir. (RF-26, RF-27, RF-29 a RF-31, RF-34)
      Hecho cuando: `pytest tests/test_enlaces.py` en verde.
- [x] T5. Oráculo de la red unida: flujo, veredicto por SET y zonal, isla y barra que no
      convergen. (RF-28, RF-32, RF-33)
      Hecho cuando: pruebas del oráculo en verde.
- [x] T6. Escritor DGS: `ElmNet` por zonal, `ElmSubstat` de SET, interruptores de cabecera,
      `ElmFeeder` en su cubículo, coordenadas. (RF-8, RF-9, RF-12, RF-14, RF-17, RF-18,
      RF-18b)
      Hecho cuando: pruebas del DGS en verde y DGS idéntico con `workers=1` y `workers>1`.
- [x] T7. `ElmZone` por sistema eléctrico y `cpZone` en el esquema y el escritor. (RF-15,
      RF-16)
      Hecho cuando: pruebas del esquema y del DGS en verde.
- [x] T8. Lote y CLI: la conversión unida estructurada y su informe. (RF-6, RF-7, RF-25,
      RF-34)
      Hecho cuando: pruebas del lote en verde con las dos disposiciones.
- [x] T9. Guiones: medida en el interruptor de cabecera con barra compartida. (RF-22 a
      RF-24)
      Hecho cuando: pruebas de los guiones con `fake_pf` en verde.
- [x] T9b. Medidores de barra: lectura de las filas «Barra», asignación por siglas y nivel,
      máxima de la barra como suma de sus transformadores, y sus alimentadores calibrados
      con su medidor en esa fecha y hora; central de barra; siglas sin SET
      en barra suelta. (RF-37 a RF-46)
      Hecho cuando: pruebas del lector, del objetivo y del guion con `fake_pf` en verde.
- [x] T10. Web: tabla en Excel por espacio e informe por zonal y SET. (RF-4, RF-25)
      Hecho cuando: pruebas de la API y del front en verde; `npm run build`.
- [x] T10b. Opción propia «por sistema eléctrico» (RF-47 a RF-51): servicio y API aparte de
      unir, botón con el zonal en la web, `--por-sistema` en el CLI, registro de tipo
      «sistema»; unir vuelve a no usar la estructura.
      Hecho cuando: pruebas del lote, la API, el CLI y el front en verde; `npm run build`.
- [x] T11. DIgSILENT: la entrega de Electro Dunas con su estructura, importada como un
      proyecto; zonas, SET, flujo; NA203 + NA205 calibrados juntos en SET 51. (todos)
      Hecho cuando: importa, converge y el ajuste del proyecto cuadra.
      2026-10-18: la entrega de Electro Dunas (93 alimentadores) importada como
      «ELECTRODUNAS_POR_SET_4»: 4 zonales, 19 SET, 20 zonas, 35 fuentes (una por barra y una
      por «Sin SET»: PA219, COH101, SC215), 52 aperturas; el flujo converge y el «Caso base»
      sale verificado, con todos los conteos iguales. Arreglado por el camino: la red del
      zonal en la metadata y en las cargas sin SED, la aceptación con varias redes y el DGS
      en cp1252. Falta el ajuste de NA203 + NA205 en ese proyecto.
      2026-10-18: cerrada con el sistema Nasca desde la base Access («20261018-034959_IGEA_
      SISTEMA_NASCA», 17 alimentadores) calibrado entero desde la web: NA203 9 190,9 kW frente
      a 9 244 (−0,57 %, aviso de kVAR: la red da más que lo medido) y NA205 por zonas
      (1 110,5/1 117,4 kW y 9 043,1/9 114,1 kW), ambos VÁLIDOS en 2 flujos y sin remedios. Por
      el camino: la etapa de «Central_NA205» guardaba 167 cargas que DIgSILENT no borra con la
      variación activa; se limpia desactivada y el reparto se escribe con las centrales
      apagadas.
- [x] T11b. Calibración por sistema eléctrico: el plan del proyecto de tipo «sistema» con
      todos sus alimentadores, los que no tienen medidor dichos y en los mismos flujos; la
      web los propone todos con la máxima por barra. (RF-52 a RF-54)
      Hecho cuando: pruebas de la API y del front en verde; el sistema Nasca calibrado en
      DIgSILENT desde la web.
      2026-10-18: hecho; en Nasca no hay medidor de barra de SET (solo el de la central),
      así que NA203 y NA205 van con su propia máxima (RF-42) y 15 sin medidor, dichos.
      2026-10-18, Pisco y después Ica, cada uno en su proyecto: «…_SISTEMA_PISCO» (20
      alimentadores; 6 barras de SET con medidor y sus alimentadores en el instante
      coincidente) calibra 16 a la vez en 5 flujos, sin remedios, todos VÁLIDOS; AL107 (su
      máxima no tiene kW positivo), CHI201, PI101 y SI114, sin medidor. «…_SISTEMA_ICA» (30)
      calibra IN111 y TA225 en 3 flujos, VÁLIDOS; los otros 28 no tienen medidor en el libro.
      Arreglado: el vínculo reconoce cada alimentador del rótulo de su barra de SET.
- [x] T11c. Un alimentador cuya medida supera lo que su red puede dar no se calibra y se
      dice; los bancos que faltan solo con una primera pasada sin remedios del flujo.
      (RF-55; 021:RF-70)
      Hecho cuando: pruebas de la API y del guion en verde; Chincha calibrado en DIgSILENT.
      2026-10-18: «…_SISTEMA_CHINCHA» (26) calibrado en DIgSILENT por la web con
      `tools/sistema_web.py`: 23 VÁLIDOS en 3 flujos, sin remedios; TM106 reconstruido con
      su medida (3 133 kW) y TM104 con la rama que conserva junto a su cabecera (RF-58b);
      CA103 y TM101 miden 0 en su cabecera y PN208 no tiene medidor: los tres, dichos y con
      la demanda del archivo en los mismos flujos (RF-53).
- [x] T11d. `tools/sistema_web.py`: la cadena de un sistema por la web, que retoma y
      reintenta. (RF-56)
      Hecho cuando: `pytest -q tests/test_sistema_web.py` en verde y Chincha calibrado con ella.
      2026-10-18: «…_SISTEMA_CHINCHA» (26) calibrado en DIgSILENT por la web con
      `tools/sistema_web.py`: 23 VÁLIDOS en 3 flujos, sin remedios; TM106 reconstruido con
      su medida (3 133 kW) y TM104 con la rama que conserva junto a su cabecera (RF-58b);
      CA103 y TM101 miden 0 en su cabecera y PN208 no tiene medidor: los tres, dichos y con
      la demanda del archivo en los mismos flujos (RF-53).
- [x] T11e. Reconstrucción por medida: tramo que falta, punto abierto por la proporción de
      las medidas, medida de barra para el que no tiene medidor; web y herramienta.
      (RF-57 a RF-61)
      Hecho cuando: pruebas de `enlaces`, del lote, de la API y de la herramienta en verde;
      Chincha reconvertido con TM106 y TM101 reconstruidos, importado y calibrado.
      2026-10-18: «…_SISTEMA_CHINCHA» (26) calibrado en DIgSILENT por la web con
      `tools/sistema_web.py`: 23 VÁLIDOS en 3 flujos, sin remedios; TM106 reconstruido con
      su medida (3 133 kW) y TM104 con la rama que conserva junto a su cabecera (RF-58b);
      CA103 y TM101 miden 0 en su cabecera y PN208 no tiene medidor: los tres, dichos y con
      la demanda del archivo en los mismos flujos (RF-53).
- [x] T12. Validación RF por RF e inventario. (todos)
      Hecho cuando: cada RF citado por una prueba y suite completa en verde.
      2026-10-18: los 56 RF citados por al menos una prueba; suite completa con las seis
      variables: 2413 pasan, ninguna omitida.
- [x] T13. Una red por SET en un zonal marcado: marca en la estructura, red de cada barra
      de SET y alimentador, `ElmNet` y diagrama por red, enlaces en la red de menor SET,
      Nasca marcado en el perfil. (RF-64 a RF-68, RF-70)
      Hecho cuando: `pytest -q tests/test_estructura.py tests/test_dgs_por_set.py` en verde
      con una estructura sorteada que divide un zonal y otra que no; DGS idéntico con
      `workers=1` y `workers>1`.
      2026-10-23: en verde con tres semillas; suite completa con las siete variables, 2657
      pasan y 4 fallan por causas ajenas: `referencia/2.-medicioncabecera` y
      `4.-clientesimportantes` pasaron a subcarpetas por año (3 pruebas de datos reales) y
      `DemandaMedida.tsx` tiene cambios sin commit («Cruzando…», 1 prueba del front).
- [x] T14. Sistema Nasca por SET en DIgSILENT: convertido, importado, «Caso base» VERIFICADO
      y calibrado por la web con `tools/sistema_web.py --zonal Nasca`. (RF-65, RF-69)
      Hecho cuando: una red y un diagrama por SET en el proyecto, cada hoja a la medida de
      su SET, y el sistema calibrado como con una red por zonal.
      Hecho: el DGS del sistema Nasca (2026-10-24) trae una red y un diagrama por SET (SET 51 Nasca,
      52 Llipata, 53 Puquio, 55, 56 y COH); importado y calibrado desde la web el 2026-10-28 con
      `tools/sistema_web.py`: 7 válidos y 0 fallos (T19). Que cada hoja quede a la medida de su SET
      sigue en T16. Cerrada el 2026-10-29 con esa evidencia (usuario: no repetir en DIgSILENT lo ya probado).
- [x] T15. SET y alimentadores nuevos: `completar` en la estructura, `cabecera_xy` en el
      inventario, web y CLI con la estructura completada, aviso, Chincha Nueva y PO101 en el
      perfil. (RF-71 a RF-80)
      Hecho cuando: `pytest -q tests/test_estructura.py tests/test_estructura_nuevos.py` en
      verde con entregas sorteadas, y con RED_231026 CN101 a CN201 en Chincha y PA219 en SET
      32 Paracas en la conversión por sistema de la web.
      2026-10-23: 24 en verde, con cinco semillas. RED_231026 (101 alimentadores) por la
      estructura del espacio: ninguno «Sin SET»; CN101 a CN201 en SET CHN Chincha Nueva
      (SE0043), PA219 en SET 32 por sus siglas, SC215 en «SET SC» deducida en Pisco y COH101
      en «SET COH» deducida en Nasca. `igea-dgs convert --por-sistema Chincha`: 27
      alimentadores en 5 SET, la CHN con barras de 10 y 22,9 kV, oráculo converge, 0 errores
      (CN103 no tiene tramos y queda fuera, como todo alimentador sin red).
- [x] T16. Cada diagrama con su origen: gráficos y conectores de cada `IntGrfnet` desplazados
      al margen, la hoja del manifiesto desde (0, 0), y lo que dibujan los guiones situado
      con las barras de su diagrama; línea base de la 001 regenerada. (RF-65)
      Hecho cuando: `pytest -q tests/test_dgs_por_set.py tests/test_diagram_topology_coverage.py
      tests/test_cargas_pf_guion_016.py` en verde, suite completa con las siete variables sin
      omitidas y, en DIgSILENT, la sonda de T14 da cada hoja con todos sus gráficos dentro.
      Cerrada el 2026-10-29: código en ad21bb8b; suite con las siete variables sin omitidas
      (3110); Nasca por SET convertido e importado de nuevo tras la corrección
      (20261029-081235_IGEA_SISTEMA_NASCA) y `tools/hojas_diagrama_pf.py` (T20) da las 6 hojas
      con todos sus gráficos dentro, la 52, la 53 y la 56 en vertical.
- [x] T17. Siglas de una SET con dos grafías: `Estructura.alimentador` y `equivalentes`,
      SET CHN con las siglas CN y CHN en el perfil, medidores del libro por cualquiera de
      las dos en la web. (RF-81)
      Hecho cuando: `pytest -q tests/test_estructura.py` en verde y, con el espacio de
      RED_231026, CN101 a CN201 en SET CHN y CHN101 a CHN201 resueltos al mismo alimentador.
      2026-10-27: en verde; CN103 sigue fuera de la red por no tener tramos.
- [x] T18. Web: «Convertir sistema» y «Convertir SET» con sus desplegables; `sets` en
      `/convert/sistema` y `sets_detalle` en el resumen; la estructura se pide al cargar la
      entrega. (RF-82, RF-83)
      Hecho cuando: `pytest -q tests/test_estructura_nuevos.py tests/test_central_termica_front.py`
      en verde, `npx tsc --noEmit` sin errores y `npm run build` correcto.
      2026-10-27: en verde y compilado.
- [x] T19. Calibración con la barra de 60 kV: `barras_de_calibracion` con `de_alta`, columna
      «SET» del libro, `valor_de_barra_en`, la web lee primero la de 60 kV y después sus
      barras de media en ese instante, un hilo por instante; transformadores T1 a T3 de
      cada medidor; centrales CT en barra o en el tramo de su alimentador, con su campo en
      la web (`/demanda/centrales`); aviso de la barra de 60 kV en otra unidad, nombre
      canónico de las siglas (CHN) desde la carga y el instante de 60 kV con registro en
      todos sus alimentadores. (RF-84 a RF-91)
      Hecho cuando: `pytest -q tests/test_estructura.py tests/test_demanda_medida_web.py` en
      verde (2026-10-27) y, en DIgSILENT, un sistema con medidores de 60 kV calibrado desde
      la web con todos sus alimentadores en el instante de su barra de 60 kV.
      2026-10-28, en DIgSILENT desde la web (`tools/sistema_web.py`, julio de 2026): Nasca 7
      válidos y 0 fallos (SET 51, 52 y 53 en el instante de su barra de 60 kV, la central de
      Nasca en el tramo de NA205); Chincha 26 válidos y 0 fallos con `--transformadores` y
      `--reconstruir TM106 TM104` (CT_PEDREG en la barra de 10 kV, CHN101, CHN102 y CHN201
      con su medidor en el instante de CHNB6T1 con registro en todos).
- [x] T20. Herramienta `tools/hojas_diagrama_pf.py`, de solo lectura, que compara en DIgSILENT
      la hoja de cada `IntGrfnet` con sus gráficos y conectores. (RF-93)
      Hecho cuando: `pytest -q tests/test_hojas_diagrama_pf.py` en verde y, en DIgSILENT, la
      herramienta da todas las hojas de Nasca por SET con sus gráficos dentro.
      Hecho el 2026-10-29: pruebas en verde; en DIgSILENT, Nasca por SET con sus 6 hojas dentro
      (código 0).
- [x] T21. Retro (033, 2026-10-29): RF-41b, RF-41c, RF-62, RF-63, añadidos a la spec como cambio después de
      escribir las tareas e implementados con su prueba sin tarea propia. (RF-41b, RF-41c, RF-62, RF-63)
      Hecho cuando: las pruebas que los citan pasan (pruebas de `tests/test_ajuste_cabecera_web.py`, `tests/test_ajuste_proyecto_guion.py` y `tests/test_demanda_medida_web.py`).
