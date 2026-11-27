# Spec 114 — Agente MASAC que aprende a operar el conversor

Estado: borrador · Fecha: 2026-11-26 · Origen: órdenes del usuario del 2026-11-26 («el MADRL debería expandirse y ser
MASAC»; «debería aprender a controlar el conversor, el RAG, los modelos, los algoritmos, DIgSILENT y el motor abierto»;
«debería aprender a hacer todos los estudios, todos los módulos»; «Dec-POMDP, CTDE, MARLlib»; «hay más de 20 empresas
distribuidoras con dataset en los archivos VNR»). Amplía la 074 (piloto MADRL en obras), que pasa a ser su fase 1.

## Contexto y objetivo

Un sistema multiagente que aprende, de las corridas reales y de miles de escenarios, a tomar las decisiones del
conversor: qué módulo y qué estudio toca, qué motor (oráculo, motor abierto, DIgSILENT), qué algoritmo y con qué
parámetros, qué consultar al RAG y las decisiones eléctricas (bancos, taps, transferencias, obras, calibración). El
asistente (LLM, 070) sigue siendo la interfaz; el agente propone y, solo donde lo haya demostrado, actúa.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA formulará cada tarea como un Dec-POMDP: agentes (director, uno por módulo y uno por alimentador o
  SET), observación parcial de cada uno, acciones continuas y discretas y una recompensa conjunta.
- RF-2: EL SISTEMA entrenará con CTDE: un crítico central por nivel que ve el estado global al entrenar y actores locales
  que deciden solo con su observación.
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

## Requisitos no funcionales

- Decisiones explicables: cada propuesta dice qué eligió, por qué (valores del crítico, alternativas) y qué la confirmó.
- Sin dependencia de MARLlib en producción; el agente funciona sin GPU con su política ya entrenada.

## Casos límite

- Pocas corridas reales de un módulo: se queda en modo sombra (RF-7).
- Recompensa que premia obras desproporcionadas: las puertas frente al método actual y la confirmación lo detectan.
- Red de una distribuidora sin demanda medida: escenarios generados, nunca como validación final.

## Fuera de alcance

Que el agente sustituya el criterio del ingeniero en lo que se entrega a Osinergmin o al cliente; actuar sin puertas.
