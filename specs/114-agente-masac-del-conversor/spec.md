# Spec 114 — Agente MASAC que aprende a operar el conversor

Estado: aprobada (por el usuario el 2026-11-27: «sí, apruebo la spec 114 de MASAC») · Fecha: 2026-11-26 · Origen: órdenes del usuario del 2026-11-26 («el MADRL debería expandirse y ser
MASAC»; «debería aprender a controlar el conversor, el RAG, los modelos, los algoritmos, DIgSILENT y el motor abierto»;
«debería aprender a hacer todos los estudios, todos los módulos»; «Dec-POMDP, CTDE, MARLlib»; «hay más de 20 empresas
distribuidoras con dataset en los archivos VNR»). Amplía la 074 (piloto MADRL en obras), que pasa a ser su fase 1.

## Contexto y objetivo

Un sistema multiagente que aprende, de las corridas reales y de miles de escenarios, a tomar las decisiones del
conversor: qué módulo y qué estudio toca, qué motor (oráculo, motor abierto, DIgSILENT), qué algoritmo y con qué
parámetros, qué consultar al RAG y las decisiones eléctricas (bancos, taps, transferencias, obras, calibración). El
asistente (LLM, 070) sigue siendo la interfaz; el agente propone y, solo donde lo haya demostrado, actúa.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA formulará cada tarea como un Dec-POMDP con agentes en tres niveles de la red, como pidió el usuario
  el 2026-11-26 (el usuario pidió agentes de alimentador, de SET y de sistema eléctrico): uno por alimentador, uno por
  SET que coordina sus alimentadores y uno por sistema eléctrico que coordina sus SET, sus líneas de 60 kV y sus
  centrales; por encima, el director y uno por módulo. Cada agente tendrá su observación parcial, acciones continuas y
  discretas, y la recompensa será conjunta.
- RF-2: EL SISTEMA entrenará con CTDE: un crítico central por nivel (alimentador, SET, sistema) que ve el estado global al
  entrenar y actores locales que deciden solo con su observación; el agente de un nivel recibe del superior su consigna
  (límites de transferencia, tensión en barra) y le devuelve su estado.
- RF-13: EL SISTEMA formará los agentes desde la estructura de la propia fuente (055): un sistema con N SET y M
  alimentadores tendrá un agente de sistema, N de SET y M de alimentador, sin tamaños fijos (la red tiene 10, 50 o 200
  alimentadores).
- RF-3: EL SISTEMA usará MASAC (Soft Actor-Critic multiagente) como algoritmo principal, con BenchMARL sobre TorchRL; y
  podrá comparar en los mismos entornos con MAPPO y MADDPG de MARLlib en un entorno aparte (Python 3.9), sin que MARLlib
  entre en el `.venv` del conversor (Python 3.12).
- RF-4: EL SISTEMA ofrecerá cada módulo como entorno PettingZoo (`ParallelEnv`) cuyos pasos se evalúan con el oráculo
  PINN y el motor abierto; DIgSILENT quedará fuera del bucle de entrenamiento y solo confirmará propuestas finales.
- RF-5: EL SISTEMA construirá los escenarios desde los paquetes VNR-GIS públicos de las distribuidoras (080), cada red en
  su entorno sin mezclar fuentes ni empresas, con demanda generada desde las curvas medidas propias como patrón
  (crecimientos y cargas nuevas sorteados), y validará con los datos medidos reales.
- RF-6: EL SISTEMA aprenderá por currículo de módulos (fase 1 obras, luego calibración, cargas nuevas y factibilidad,
  estudios, modelos, RAG y por último el director), primero fuera de línea con las corridas registradas de la web.
- RF-7: MIENTRAS un módulo no haya pasado sus puertas, EL SISTEMA solo lo usará en modo sombra: propone junto a la regla
  actual, sin aplicar, y mide quién acierta.
- RF-8: CUANDO un módulo del agente iguale o mejore al método actual en los mismos casos (obras: NSGA-II con el oráculo) y
  DIgSILENT confirme su propuesta, EL SISTEMA podrá dejarlo actuar en ese módulo.
- RF-9: EL SISTEMA nunca dejará que el agente borre ni pise trabajo del operador; escribir en DIgSILENT solo en
  variaciones o proyectos de prueba, o en uno real con la confirmación del operador.
- RF-10: La recompensa incluirá: resultado válido (calibración, convergencia, norma CNE en máxima y valle), pérdidas,
  costo de obra, tiempo y uso de DIgSILENT, y una penalización fuerte por toda acción que el operador deshaga.
- RF-11: EL SISTEMA registrará cada decisión del agente con su observación, su acción, su recompensa y quién la
  confirmó, como experiencia para el siguiente entrenamiento.
- RF-12: EL SISTEMA entrenará por el circuito de la 113 (Colab, candidatos y puertas locales) y activará cada política con
  el gobierno de modelos (043), con vuelta atrás.

Añadido el 2026-11-27, al implementar la primera tanda (T1, T3 y T4), por lo que la spec no definía:

- RF-14: MIENTRAS BenchMARL no admita la versión de TorchRL que necesita el PyTorch del conversor, EL SISTEMA entrenará
  MASAC con su propia implementación en PyTorch, con la formulación de BenchMARL (SAC discreto con temperatura
  automática, actor compartido por nivel y crítico central por nivel), y cada modelo guardado lo dirá. (El 2026-11-27,
  BenchMARL 1.5.2, la última publicada, fija `torchrl<0.12`; esa TorchRL fija `tensordict<0.12` y no convive con la
  0.14 que pide torch 2.14.1, y con la 0.14 BenchMARL no importa porque falta `SyncDataCollector`.)
- RF-15: DONDE PettingZoo no esté instalado, EL SISTEMA ofrecerá el entorno con la misma API de `ParallelEnv` y los
  mismos espacios, para que proponer y probar no dependan de las bibliotecas del entrenamiento.
- RF-16: SI la fuente no trae la estructura de un alimentador, ENTONCES EL SISTEMA deducirá su SET de la red (las
  barras entre la fuente y su cabecera, unidas sin líneas) y su sistema eléctrico de la fuente que lo alimenta.
- RF-17: EL SISTEMA solo ofrecerá una transferencia en una maniobra abierta (interruptor o seccionador) entre dos
  alimentadores, abriendo a la vez otra maniobra cerrada del alimentador que cede, para que la red siga radial.
- RF-18: SI una toma no declara su paso y sus límites, o una fuente el paso de su consigna, ENTONCES EL SISTEMA no
  ofrecerá esa acción, sin suponerlos.
- Aclaración de RF-9: un elemento que el operador cambió (marcado como suyo en la red, o en la lista de protegidos)
  no se ofrece al agente como acción.
- RF-19: MIENTRAS un módulo esté en modo sombra, EL SISTEMA dará por acertada la propuesta que deja la red en norma en máxima y en valle; entre
  dos que lo hagan, la de menor costo; y a igual costo, la de menos pérdidas.
- RF-20: SI un agente recibe una acción fuera de su máscara, ENTONCES EL SISTEMA la tomará como «no hacer nada» y lo
  dirá en la información del paso.

Añadido el 2026-11-27, con la parte web de la T4 (orden del usuario: «haz también la parte web de MASAC»):

- RF-21: SI al pedir una propuesta desde la web no hay ninguna política guardada, o la guardada es de otros huecos de
  acción, ENTONCES EL SISTEMA entrenará una en CPU con la red del proyecto antes de proponer, y lo dirá en el trabajo.
- RF-22: CUANDO el operador confirme o deshaga una propuesta desde la web, EL SISTEMA lo anotará en el registro de
  experiencia, sin aplicar nada en DIgSILENT.
- RF-23: SI una propuesta ya está confirmada o deshecha, ENTONCES EL SISTEMA no la dejará decidir otra vez.

## Requisitos no funcionales

- Decisiones explicables: cada propuesta dice qué eligió, por qué (valores del crítico, alternativas) y qué la confirmó.
- Sin dependencia de MARLlib en producción; el agente funciona sin GPU con su política ya entrenada.

## Casos límite

- Pocas corridas reales de un módulo: se queda en modo sombra (RF-7).
- Recompensa que premia obras desproporcionadas: las puertas frente al método actual y la confirmación lo detectan.
- Red de una distribuidora sin demanda medida: escenarios generados, nunca como validación final.

## Fuera de alcance

Que el agente sustituya el criterio del ingeniero en lo que se entrega a Osinergmin o al cliente; actuar sin puertas.
