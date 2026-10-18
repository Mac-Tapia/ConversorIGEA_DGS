# Tareas 022 — Red unida por zonal y SET

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]` y pare.

- [x] T1. `estructura.py`: modelo, lectura del perfil y de Excel, validación de filas, y
      `asignar` con «Sin SET», faltantes y omitidos. (RF-1, RF-2, RF-4, RF-5, RF-19, RF-20,
      RF-25b)
      Hecho cuando: `pytest tests/test_estructura.py` en verde (tablas sorteadas).
- [x] T2. Transcribir la tabla pública a `config/perfiles/electro_dunas.estructura.json` y
      enlazarla desde el perfil de Electro Dunas, con las siglas de cada SET. (RF-3, RF-46)
      Hecho cuando: el perfil carga 4 zonales y todos los alimentadores de la tabla.
- [ ] T3. `estructurar` en `combine.py`: barras de SET por tensión, interruptor de cabecera
      cerrado para todos, una fuente por barra. (RF-10 a RF-13, RF-21)
      Hecho cuando: pruebas sintéticas de la red unida estructurada en verde.
- [ ] T4. `enlaces.py`: puntos de enlace con sus SET, caminos cerrados (entre SET, entre
      alimentadores, anillos) y qué abrir. (RF-26, RF-27, RF-29 a RF-31, RF-34)
      Hecho cuando: `pytest tests/test_enlaces.py` en verde.
- [ ] T5. Oráculo de la red unida: flujo, veredicto por SET y zonal, isla y barra que no
      convergen. (RF-28, RF-32, RF-33)
      Hecho cuando: pruebas del oráculo en verde.
- [ ] T6. Escritor DGS: `ElmNet` por zonal, `ElmSubstat` de SET, interruptores de cabecera,
      `ElmFeeder` en su cubículo, coordenadas. (RF-8, RF-9, RF-12, RF-14, RF-17, RF-18,
      RF-18b)
      Hecho cuando: pruebas del DGS en verde y DGS idéntico con `workers=1` y `workers>1`.
- [ ] T7. `ElmZone` por sistema eléctrico y `cpZone` en el esquema y el escritor. (RF-15,
      RF-16)
      Hecho cuando: pruebas del esquema y del DGS en verde.
- [ ] T8. Lote y CLI: la conversión unida estructurada y su informe. (RF-6, RF-7, RF-25,
      RF-34)
      Hecho cuando: pruebas del lote en verde con las dos disposiciones.
- [ ] T9. Guiones: medida en el interruptor de cabecera con barra compartida. (RF-22 a
      RF-24)
      Hecho cuando: pruebas de los guiones con `fake_pf` en verde.
- [ ] T9b. Medidores de barra: lectura de las filas «Barra», asignación por siglas y nivel,
      objetivo por barra como máxima de la suma de sus transformadores, y cuadre por barra
      en el ajuste del proyecto con un factor por barra; central de barra; siglas sin SET
      en barra suelta. (RF-37 a RF-46)
      Hecho cuando: pruebas del lector, del objetivo y del guion con `fake_pf` en verde.
- [ ] T10. Web: tabla en Excel por espacio e informe por zonal y SET. (RF-4, RF-25)
      Hecho cuando: pruebas de la API y del front en verde; `npm run build`.
- [ ] T11. DIgSILENT: la entrega de Electro Dunas con su estructura, importada como un
      proyecto; zonas, SET, flujo; NA203 + NA205 calibrados juntos en SET 51. (todos)
      Hecho cuando: importa, converge y el ajuste del proyecto cuadra.
- [ ] T12. Validación RF por RF e inventario. (todos)
      Hecho cuando: cada RF citado por una prueba y suite completa en verde.
