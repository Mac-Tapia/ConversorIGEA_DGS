# Spec 074 — Piloto MADRL en obras: medir antes de aprender

Estado: aprobada · Fecha: 2026-11-02 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-02, pidió un marco de aprendizaje profundo multiagente con atención o híbrido, que reutilice GitHub y
aprenda políticas y penalidades, y recordó el mismo día que seguía pendiente. La revisión de ese día no halló MADRL público para
planificar obras, y podría no superar a NSGA-II ni a la escalera. Este piloto se limita a las obras de «Con proyecto» y a una
pregunta: ¿supera el aprendizaje a lo que ya existe, en alimentadores que no vio?

Por eso el orden es medir, y solo después aprender: un entorno que reproduzca a DIgSILENT, los controles sin aprendizaje y una
puerta que decida si el aprendizaje sigue.

## Requisitos funcionales

### Entorno

- RF-1: EL SISTEMA dará un entorno con un agente por zona de la red, deducida de sus fuentes, con pasos simultáneos, recompensa
  común y sin modificar el grafo de entrada.
- RF-2: EL SISTEMA limitará lo que puede elegir cada agente con una máscara: sin problemas en su zona, ninguna obra; con ellos,
  bancos antes que terna.
- RF-3: SI una obra no tiene metrado o costo declarado, ENTONCES EL SISTEMA no la ofrecerá, sin suponerlos.
- RF-4: EL SISTEMA calculará la recompensa con el costo y con penalidades por violación, cuyos multiplicadores de Lagrange se
  aprenden; el agente no aprenderá la función de recompensa. Terminar fuera de norma costará más que todas las obras, y se cobrará
  una vez, al terminar.

### Medida

- RF-5: EL SISTEMA medirá la escalera y NSGA-II sobre las mismas obras y la misma red que verá el aprendizaje.
- RF-6: EL SISTEMA solo dará por bueno el aprendizaje si, en alimentadores no vistos, deja el 100 % en norma con un costo no peor
  que NSGA-II; solo cuentan las redes que la referencia deja en norma (usuario, 2026-11-02).
- RF-7: SI el entorno no reproduce lo que midió DIgSILENT en una red, en tensión o en la peor rama, ENTONCES EL SISTEMA no la usará
  en el piloto.
- RF-8: EL SISTEMA capturará en el grafo las unidades en paralelo de cada transformador y el largo de cada tramo.

### Sistema eléctrico

- RF-11: EL SISTEMA tendrá un agente por cada alimentador de un sistema eléctrico, deducido de su cabecera en la red (usuario,
  2026-11-02: «NSGA-II debes ampliarlo para todos los alimentadores necesarios para un sistema eléctrico; para eso también se
  debe entrenar»).
- RF-12: EL SISTEMA optimizará con NSGA-II todos los alimentadores del sistema, cada uno con su camino a la fuente, y medirá lo
  elegido junto en el sistema entero.

### Aprendizaje

- RF-9: EL SISTEMA entrenará con TorchRL, PyTorch Geometric con GATv2 y crítico central, con MaskablePPO como control, por un turno
  de GPU y sin dependencias nuevas en el `.venv` que comparten las demás sesiones hasta verificarlas.
- RF-10: EL SISTEMA no aplicará por su cuenta ninguna obra aprendida: se confirma en DIgSILENT por la ruta de la spec 011.

## Fuera de alcance

Todo el flujo del conversor: solo las obras de «Con proyecto». Sincronizar los modelos entre sí, que es de la spec 050.
La limitación de bancos por valle, de la 073; cuando exista, se añade a la máscara.

## Requisitos no funcionales

Universal: los límites y costos se declaran y las zonas salen de la red. Sin DIgSILENT ni GPU para medir los controles.
