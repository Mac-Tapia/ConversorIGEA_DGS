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
- [ ] T12. Validación RF por RF e inventario. (todos)
      Hecho cuando: cada RF citado por una prueba y suite completa en verde.
