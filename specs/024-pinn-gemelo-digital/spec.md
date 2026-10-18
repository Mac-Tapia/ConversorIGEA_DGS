# Spec 024 — PINN como oráculo y gemelo digital de la red calibrada

Estado: borrador · Fecha: 2026-10-18

## Contexto y objetivo

El usuario, el 2026-10-18: «el PINN debería ser como un oráculo como pandapower; podría hacer
las predicciones de demanda, las reconstrucciones de tramos que faltan y otras deficiencias en
las redes», y «revisar artículos científicos y tesis de maestría y doctorado para aprovechar su
máxima potencia como digital twin».

Hoy el conversor resuelve a mano, caso por caso, tres huecos que una red neuronal informada
por la física (PINN: la red aprende, pero su pérdida castiga violar las leyes del flujo de
potencia) cubre de forma general:

1. **Alimentadores sin medidor.** Quedan con la demanda del archivo (022:RF-53): 15 de 17 en
   Nasca, 4 de 20 en Pisco, 28 de 30 en Ica. Los medidores de barra de SET y los de los demás
   alimentadores sí dicen cuánto entra; falta repartirlo.
2. **Red incompleta o mal asignada.** TM106 sin su red (registrada como TM104), 3 083 huecos
   padre–hijo y 6 islas en la copia de VNR-GIS, alimentadores fuera de servicio con red.
   La reconstrucción por medida (022:RF-57 a RF-63) lo resuelve con reglas; no ve lo que las
   medidas contradicen en el resto de la red.
3. **Una sola instantánea.** Se calibra la máxima (o el instante coincidente de la barra);
   el mes de curvas de cabecera y barra queda sin usar para el comportamiento hora a hora.

La literatura respalda los tres usos, siempre con el flujo físico como restricción y no como
sustituto: estimación de estado con observabilidad limitada y pseudo-medidas (Zamzam y
Sidiropoulos 2019; PINN para redes desequilibradas 2025, más del 90 % menos de error en
corrientes del IEEE 123 con inyecciones enmascaradas), estimación de parámetros de línea y
topología con grafos informados por la física (arXiv 2102.09023, 2102.06349; CIRED 2026,
residuos de estimación para errores de topología en redes rehechas de GIS), y gemelos
digitales con datos que faltan (arXiv 2511.06583). Las experiencias de despliegue avisan de
lo mismo que vemos aquí: la calidad de los datos de entrada (trafos mal cargados, medidores,
topología) es el mayor esfuerzo (Aalborg 2024).

## Usuarios / actores

Ingeniero de planificación desde la web; DIgSILENT como fuente de verdad del flujo; el oráculo
pandapower de la red unida (022:RF-28).

## Historias de usuario

- H1: Como ingeniero quiero una demanda estimada, con su incertidumbre, para cada alimentador
  sin medidor, coherente con la barra de su SET, para calibrar el sistema entero.
- H2: Como ingeniero quiero que se me señalen los tramos que faltan, los mal asignados y los
  datos de equipo imposibles, ordenados por lo que contradicen las medidas.
- H3: Como ingeniero quiero reproducir un día o un mes hora a hora sobre la red calibrada y
  ver dónde se desvía de lo medido (gemelo digital).

## Requisitos funcionales (EARS)

Oráculo PINN

- RF-1: EL SISTEMA tendrá un oráculo PINN por proyecto calibrado que, dadas las inyecciones de
  las SED y la tensión de la fuente, dé las tensiones de las barras y los flujos por los tramos,
  con una pérdida que penalice el residuo de las ecuaciones de potencia nodal de la red.
- RF-2: EL SISTEMA entrenará el oráculo solo con flujos de DIgSILENT de ese proyecto (caso base
  y calibraciones válidas) y con las medidas de cabecera y barra; no saldrán datos de la máquina.
- RF-3: SI el error del oráculo frente a un flujo de DIgSILENT de validación supera el umbral
  del perfil, ENTONCES EL SISTEMA no lo usará y lo dirá; DIgSILENT sigue siendo la referencia.

Demanda sin medidor (pseudo-medidas)

- RF-4: CUANDO un sistema tiene alimentadores sin medidor y su barra de SET sí lo tiene, EL
  SISTEMA estimará la demanda de cada uno en el instante de la barra, con la potencia instalada,
  los clientes fijos y la curva de los medidos, de modo que la suma más las pérdidas del
  oráculo dé lo medido en la barra.
- RF-5: EL SISTEMA dará cada demanda estimada con su intervalo y la marcará como estimada en
  el plan y en el informe, distinta de la medida.

Deficiencias de la red

- RF-6: EL SISTEMA dará, por alimentador, los tramos y nodos donde el residuo físico entre
  medidas y red supera lo esperado, como candidatos a tramo que falta, carga mal asignada o
  parámetro de equipo erróneo, ordenados por su peso en el residuo.
- RF-7: DONDE una reconstrucción por medida (022:RF-57) tenga varias opciones, EL SISTEMA
  podrá ordenarlas por el residuo del oráculo con las curvas del mes, no solo con un instante.

Gemelo digital

- RF-8: EL SISTEMA reproducirá un periodo hora a hora (o cada 15 min, como las curvas) sobre la
  red calibrada con el oráculo, y comparará con las curvas de cabecera y de barra.
- RF-9: SI la desviación entre el gemelo y una medida supera el umbral del perfil, ENTONCES EL
  SISTEMA la señalará con su instante y su alimentador, como posible error de dato o de red.
- RF-10: EL SISTEMA confirmará en DIgSILENT, con su flujo nativo, los instantes que el gemelo
  señale, antes de dar nada por bueno.

## Requisitos no funcionales

- Universal: nada de una empresa; umbrales y tamaños en el perfil.
- Escala: un modelo por proyecto; entrenar no recorre toda la entrega por alimentador.
- Datos: entrenamiento y uso locales; ningún dato de la distribuidora a servicios externos.
- Reproducible: semilla fija; el mismo proyecto y datos dan el mismo oráculo.

## Casos límite

Sistema sin ningún medidor; barra sin medidor (022:RF-42); alimentador fuera de servicio con
red; red con central térmica (021); proyecto sin calibración válida (no se entrena).

## Fuera de alcance

Sustituir a DIgSILENT en estudios (N-1, cortocircuito, confiabilidad siguen con sus módulos
nativos); control en tiempo real; predicción de demanda a futuro (años), que es otra spec.

## Criterios de finalización

Cada RF citado por una prueba; oráculo validado contra DIgSILENT en los sistemas Nasca, Pisco,
Ica y Chincha; demanda estimada de los sin medidor que cuadra la barra; suite sin omitidas.

## Dudas abiertas

- [NECESITA ACLARACIÓN] Biblioteca de aprendizaje: PyTorch (CPU, local) es lo habitual en la
  literatura; ¿se acepta como dependencia nueva del proyecto?
- [NECESITA ACLARACIÓN] Orden de entrega: ¿primero la demanda de los sin medidor (H1), que es
  lo que más falta hoy, o el gemelo hora a hora (H3)?
- [NECESITA ACLARACIÓN] Umbrales por defecto del perfil para RF-3 y RF-9 (error de tensión en
  p.u. y desviación de potencia en %).
