# Tareas 098

- [x] T1. Reconocer las zonas transferidas por el operador y qué abrir y cerrar en cada una, en una pasada por clase.
      (RF-1, RF-2, RF-8, RF-15)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "sentidos or estado or toca or nuevas or abiertos"` en verde.
- [x] T2. Calibrar y recalibrar con la red de la fuente: desactivar, comprobar, restituir antes de guardar y en el
      `finally`, con el registro en disco y el informe. (RF-3, RF-4, RF-5, RF-6, RF-7, RF-8, RF-10)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py tests/test_ajuste_proyecto_guion.py tests/test_ajuste_cabecera_guion.py` en verde.
- [x] T3. El escaneo dice lo que está en un alimentador por una transferencia desde otro. (RF-9)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k escaneo` y `pytest -q tests/test_escaneo.py` en verde.
- [x] T4. La web lleva al plan los tramos y los abiertos del DGS aceptado y la fecha de la importación. (RF-14)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k web` en verde.
- [x] T5. Las transferencias y los traslados de la escalera, solo donde hay maniobra, que la migración abre con su
      apertura anotada. (RF-11, RF-12, RF-13)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "maniobra or seccionador"` y
      `pytest -q tests/test_obras_integrales.py tests/test_obras_aperturas.py` en verde.
- [x] T7. Comparar la red con el DGS aceptado rama por rama: particiones, enlaces nuevos del operador y el registro
      por nombre completo; la fecha de la importación por el sello del proyecto. (RF-14, RF-16, RF-17, RF-18, RF-19)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "particiones or acopladores or frente or web"` en
      verde, con la configuración de CA101 y CHN102 que dieron las sondas del 2026-11-07.
- [x] T8. Transferir por el enlace que ya existe: su lectura, la obra «maniobra» que abre y cierra con su registro,
      el oráculo que la juzga y la combina con los bancos, el orden antes del nivel y el informe; y las barras sin GPS.
      (RF-20 a RF-27)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "gps or enlace or bancos or filtra or maniobra or reabre or nivel or evaluar_la"`
      y `pytest -q tests/test_obras_integrales.py tests/test_optimizacion_oraculo.py tests/test_obras_aperturas.py` en verde.
- [x] T9. Lo de la T6 de «Con proyecto»: la variante no aplicada, la escalera del alimentador sin cargas que viola
      límites y el oráculo corregido con lo medido por DIgSILENT. (RF-28, RF-29, RF-30)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "aplicada or cambio or bajas or sin_cargas or corrige"`
      y `pytest -q tests/test_obras_pf_guion.py tests/test_optimizacion_oraculo.py` en verde.
- [x] T10. Las obras de varios caminos juntas, la medida reutilizada solo si es segura, el regulador que regula, la
      sección y la terna con costo y lo que no aguanta, detrás. (RF-31 a RF-35)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "caminos or misma_red or regulador_activa or capex"`
      y `pytest -q tests/test_escalera_optima.py tests/test_obras_pf_guion.py` en verde.
- [x] T11. Lo de la revisión de b83dc156: el ajuste del flujo en el caso de la obra, anotado en disco y devuelto
      aunque la creación se corte, con las otras tomas fijas mientras se mide; la huella con el contenido de la red; las
      ya medidas que cuentan para parar sin abrir DIgSILENT; el alcance de cada una que cumple; la terna con su
      factor; las dos elecciones, de corto y de largo plazo; y la obra elegida con la regla anterior, retirada con lo
      que hizo y medida de nuevo. (RF-32, RF-34 a RF-37)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "plazo or horizonte or regla or retirada or flujo or corta or ya_medidas or reutiliza or caminos or ramas or capex"`
      y `pytest -q tests/test_escalera_optima.py tests/test_obras_pf_guion.py tests/test_obras_aperturas.py tests/test_informes_planeamiento.py` en verde.
- [x] T12. Lo de la segunda revisión de efaf2901: solo la obra de la escalera se compara y se retira (por nombres
      exactos, con su origen guardado), la sustitución atómica con la vieja fuera de la medida y repuesta si falla, el
      ajuste de tomas compartido entre reguladores, el escenario guardado solo si cambió, las restituciones una a una,
      las tomas de tres devanados y reguladores ajenos en un lote, la huella con el tipo y la operación, el intervalo en
      que hace falta la de largo plazo y los bancos ampliados, y el factor de la terna positivo. (RF-32, RF-34 a RF-37)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "escalera or nombradas or cuesta_menos or repone or conserva or reguladores or huella or alcance or ampliados or factor"`
      y `pytest -q tests/test_obras_pf_guion_042.py tests/test_informe_factibilidad_un_paso.py tests/test_obras_integrales.py` en verde.
- [x] T13. Lo de la tercera revisión de 9ff6f3f1: la sustitución sin borrar antes de tiempo (la vieja medida como una
      variante más, la nueva primero, la vieja borrada al final o vuelta activa, el diario en disco y la recuperación),
      la vieja que no cumple que no resuelve, la evidencia de la escalera para lo aplicado sin origen, el ajuste de
      tomas original por caso, la huella del paso de evaluar con la revisión y las pérdidas, la huella de la red de los
      alimentadores en estudio y las rondas de conjunto con la misma sustitución. (RF-34, RF-36)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "sustitu or falla or incompleto or cortada or apartada or dudosa or ultima_obra or escalera or cuesta_menos"`
      y `pytest -q tests/test_obras_integrales.py tests/test_informe_factibilidad_un_paso.py tests/test_obras_pf_guion_042.py` en verde.
- [x] T14. Lo de la cuarta revisión de 0c5b29f6: la nueva comprobada con los casos de año, la evidencia por la misma
      obra aplicada, solo hacia delante tras comprobar la nueva, la operación guardada en el escenario y en el diario,
      el borrado con guarda y por nombres anotados, el ajuste de tomas de las obras antiguas, lo especial de la corrida
      que no es resto, la vieja medida sin su operación y los menores. (RF-34, RF-36)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "delante or escenario or corta_dentro or nueva_creada or borran or antigua or especial or sin_su_operacion or reactiva or pendientes or no_aplicada_no_es"`
      y `pytest -q tests/test_casos_por_anio.py tests/test_seis_reglas.py` en verde.
- [x] T15. La mitad «(n)» de un tramo partido por una carga nueva es el tramo entero al grabar la obra. (RF-38)
      Hecho cuando: `pytest -q tests/test_obras_pf.py -k mitad` en verde.
- [x] T16. Solo el año 0 en este estudio: la de corto plazo llega al año del periodo (4, o el del perfil), el año
      en que vuelve a fallar con el oráculo y confirmado en DIgSILENT en ese año y el anterior, en el informe y la web,
      sin ninguna obra futura; más módulos de banco mientras mejoran, y ningún enlace entre tensiones distintas.
      (RF-37, RF-39 a RF-42)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "periodo or vuelve_a_fallar or biseccion or tensiones_distintas or pide"`
      y `pytest -q tests/test_valle.py -k "bancos_suben or todos_los_modulos" tests/test_escalera_optima.py` en verde.
- [x] T17. La transferencia del operador como alternativa de la escalera en «Con proyecto» (deshecha allí, con su
      corte y los otros, juzgada en los dos y con su fila en el informe), y el que la recibe probando otro corte de la
      misma antes que bancos u obras de línea. (RF-10, RF-43, RF-44)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "alternativa or resuelve or punto_de_corte or otro_corte or corte_del_operador"`
      en verde.
- [x] T18. El orden fijo de los escalones sin saltos (bancos, sección, terna, transferencia; después nivel y
      regulador; la obra integral al final), con su registro por escalón y sin el corte de 087:RF-40. (RF-45)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k "escalon or orden_fijo"` y
      `pytest -q tests/test_escalera_optima.py tests/test_obras_integrales.py` en verde.
- [x] T19. Todos los escalones evaluados y la más barata que cumple. (RF-46)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k barata` en verde.
- [x] T20. La transferencia del operador y la del enlace existente se miden siempre. (RF-47)
      Hecho cuando: `pytest -q tests/test_transferencia_operador.py -k operador` en verde.
- [ ] T6. [DIgSILENT] Recalibrar por la web el proyecto `20261105-124711_CSG_TXT_CA101_CHN102` (mes 2026-07) y correr
      «Con proyecto». (RF-3, RF-5, RF-7, RF-10, RF-11, RF-17, RF-18, RF-21 a RF-26, RF-28 a RF-37)
      Primera corrida (2026-11-07, main 0b130251 + 4d9c230f): siguió con -1 271,2 kW; dos zonas sin tocar porque la
      lectura no veía las particiones ni el acoplador nuevo; de ahí la T7.
      Hecho cuando: la recalibración cuadra sin pérdidas negativas, su informe dice que la transferencia de CA101 a
      CHN102 se desactivó (se abre «Breaker/Switch(1)» y se cierra «Breaker/Switch») y se restituyó con la comprobación en verde, la transferencia sigue en «Sin proyecto» y en
      «Con proyecto» como la dejó el operador, y las transferencias que proponga la escalera salen de barras con
      maniobra; en «Con proyecto», la escalera de CA101 prueba la transferencia por el enlace existente con CHN102 (sola
      o con bancos) antes del paso a 22,9 kV, y el registro dice cuántas juzgó el oráculo y cuántas confirmó DIgSILENT;
      CHN102 lleva su escalera; el registro da el desvío del oráculo frente a DIgSILENT, y una variante sin aplicar
      sale como «no aplicada», no como «no cumple»; CA101 prueba y elige una obra que junta sus dos caminos, sin
      volver a medir lo ya medido con la misma red; el paso a 22,9 kV de CHN102 (aplicado antes de guardar su origen,
      con su elección guardada en el espacio 2131c6bc8b924e63) se mide como la vieja y se cambia por la de corto plazo
      solo si cuesta menos, primero la nueva y después borrada la vieja, con la de largo plazo planteada y el
      intervalo en que hace falta.
