# Spec 107 — Plan de Inversiones en Transmisión (PIT) del sistema secundario y complementario

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-17, y orden del usuario del 2026-11-14:
«haz nuevos spec» para las brechas sin spec. G0: `D:/csg/G0_PLAN_MAESTRO/D/D_FILAS_BP.md`.

## Contexto y objetivo
El conversor estudia alimentadores de media tensión y arma el PIDE de distribución (072), pero no tiene nada para el PIT.
El PIT es el plan de inversiones de los sistemas secundario y complementario de transmisión (SST/SCT), que fija
Osinergmin por área de demanda: la norma de tarifas y compensaciones (RCD 217-2013-OS/CD) y el PIT 2025–2029 (RCD
112-2024 y 149-2024, con sus modificatorias). G0 comprobó que «PIT» solo aparece en el código como catálogo de módulos
del libro CAPEX (`set_nueva.py:113-140@51895566`). El PIT comparte con el PIDE la red, los motores, los costos y los
informes, pero **no** su método, su horizonte ni sus formatos. Esta spec crea el producto PIT separado y reutiliza lo
común.

## Usuarios / actores
- Ingeniero de planificación de transmisión de la concesionaria, desde la web.
- Revisor regulatorio que reproduce el expediente.

## Historias de usuario
- H1: Como planificador de transmisión, quiero diagnosticar las SET, los transformadores de potencia y las líneas de
  60 kV y superiores de un área de demanda para cada año del horizonte, y así saber qué elemento incumple y cuándo.
- H2: Como planificador, quiero comparar alternativas de transmisión mutuamente excluyentes por inversión, COyM,
  pérdidas y confiabilidad, para proponer el programa del área.
- H3: Como revisor, quiero que cada cifra del expediente cite la norma, la versión vigente, la fuente y el cálculo que
  la produjo.

## Requisitos funcionales (EARS)
- RF-1: EL SISTEMA tratará el PIT como un estudio distinto del PIDE: su norma, su horizonte, sus formatos y su
  registro se guardan aparte, aunque compartan la red y los costos.
- RF-2: CUANDO el operador elija un área de demanda y un periodo, EL SISTEMA reunirá las SET, los transformadores de
  potencia, las celdas, las líneas y la compensación de ese ámbito desde las fuentes ya importadas, sin mezclar áreas.
- RF-3: CUANDO se pida el diagnóstico, EL SISTEMA calculará para cada año del horizonte la cargabilidad, la tensión y
  el estado ante la contingencia de cada elemento, con la demanda proyectada del área.
- RF-4: SI un elemento necesario para el diagnóstico no tiene sus parámetros, ENTONCES EL SISTEMA lo listará con el
  dato que falta y no dará el diagnóstico de ese elemento como completo.
- RF-5: CUANDO el operador defina alternativas, EL SISTEMA evaluará cada una por inversión, COyM, pérdidas y
  confiabilidad, con la misma demanda y el mismo motor.
- RF-6: EL SISTEMA programará cada elemento por año de puesta en servicio, titular y área, con las bajas y los
  reemplazos.
- RF-7: EL SISTEMA guardará en el expediente, por cada regla aplicada, la norma, el artículo o anexo, su estado
  jurídico (vigente comprobada, modificada, prepublicada o no verificada) y su fecha de vigencia.
- RF-8: SI una regla está prepublicada o no verificada, ENTONCES EL SISTEMA no la usará como obligatoria y lo dirá
  en el expediente.
- RF-9: CUANDO se emita el expediente, EL SISTEMA generará los cuadros del periodo y del área aplicables, con la
  traza de cada celda a su fuente y a su cálculo.
- RF-10: EL SISTEMA registrará cada observación del regulador con su respuesta y el elemento, el caso o el cálculo
  al que afecta.
- RF-11: EL SISTEMA no tendrá ningún valor de un área, de una empresa ni de un periodo en el código: van en el
  perfil o en el registro normativo (P13).

## Requisitos no funcionales
- Universal: cualquier área de demanda y titular. Las pruebas usan al menos dos perfiles sintéticos.
- Determinismo: el mismo caso, con la misma norma y los mismos costos, da el mismo expediente.
- El diagnóstico de varios años es un trabajo en cola, cancelable (P7).

## Casos límite
- Un área con un solo titular y otra con varios.
- Una modificatoria publicada después de iniciar el expediente.
- Un elemento compartido entre dos áreas.
- Un año sin demanda proyectada.

## Fuera de alcance
- Fijar tarifas o peajes.
- La dinámica RMS y los transitorios EMT.
- Presentar el expediente al regulador: la presentación la hace la empresa.
- Declarar el expediente «aprobado por Osinergmin».

## Criterios de finalización
Cada RF citado por una prueba (`grep "107:RF-"`). Se reproduce un cuadro de un PIT publicado, autorizado por la
empresa, fila por fila, con sus diferencias explicadas. Un revisor independiente coteja una muestra de celdas.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario (`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 3):
- Primer caso real: el área de demanda de Electro Dunas. El número de área y el titular van en su perfil, nunca en el
  código (P13); es un caso de prueba, no el diseño.
- Motor: el abierto (pandapower) por defecto y DIgSILENT si hay licencia, con la misma matriz de capacidades. Lo que un
  motor no puede calcular se dice, y cada resultado nombra el motor que lo dio. El PIT usa el modelo de transmisión del
  área, no el de MT.
- RCD 199-2026: entra en el registro normativo como no verificada y sin reglas hasta que se pueda leer y transcribir
  (tarea T3 de `tasks.md`); mientras tanto no se usa como obligatoria (RF-8).
