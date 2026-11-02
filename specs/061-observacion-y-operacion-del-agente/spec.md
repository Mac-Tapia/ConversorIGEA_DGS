# Spec 061 — Observación y operación integrada del agente

Estado: cumplida · Fecha: 2026-11-01

## Objetivo y alcance autorizado

El usuario solicita integrar los componentes en el conversor para observar su
funcionamiento y preparar al asistente como monitor y ejecutor de la operación.
Amplía 026/027, consume043/050/060 y conserva sus puertas. Reutiliza API, cola,
WebSocket y orquestador actuales; no crea otro motor eléctrico ni atribuye capacidades
autónomas a modelos sin aceptación.

## Requisitos

- RF-1: CUANDO cambie el estado de un trabajo de la cola, EL SISTEMA conservará su identidad, espacio, carril, progreso, resultado resumido y contexto de fuente fijado al encolarlo.
- RF-2: CUANDO se reabra el monitor, EL SISTEMA mostrará los registros persistidos y distinguirá un trabajo vivo de otro cuyo proceso ya no está observado, sin reejecutarlo automáticamente.
- RF-3: CUANDO el operador observe un espacio, EL SISTEMA limitará sus operaciones a ese espacio y presentará los modelos globales como globales, sin atribuirlos a un proyecto por su nombre.
- RF-4: CUANDO cambien trabajos en la sesión, EL SISTEMA actualizará el monitor mediante los eventos existentes del espacio, sin añadir sondeo periódico del estado.
- RF-5: CUANDO se ejecute o cancele desde el monitor, EL SISTEMA utilizará las rutas, carriles y confirmaciones existentes; la observación no autorizará escrituras nuevas.
- RF-6: SI una etapa del flujo del proyecto devuelve un código de fallo, ENTONCES EL SISTEMA impedirá registrarla como hecha y detendrá las siguientes etapas.
- RF-7: SI cambia la identidad de fuente o de los datos declarados respecto al punto de control del proyecto, ENTONCES EL SISTEMA impedirá reutilizar etapas hechas; al reiniciar explícitamente conservará el punto anterior.
- RF-8: CUANDO se incorpore un informe de aprendizaje local, EL SISTEMA conservará una copia con hash, familia y procedencia explícitas; mostrar evidencia no activará ni promoverá pesos.
- RF-9: CUANDO muestre resultados, EL SISTEMA separará ejecución, entrenamiento, reapertura, promoción y aceptación nativa; ausencia de prueba no se presentará como aceptación.
- RF-10: SI no puede persistir una operación nueva, ENTONCES EL SISTEMA rechazará su encolado sin dejar un trabajo huérfano; si falla durante una operación activa mostrará la observación incompleta.

## Límites

Operación supervisada con el orquestador actual y sus acciones permitidas. El ciclo
automático sincronizado y la promoción conjunta siguen sujetos a050 y a aceptación
real, no se cierran por construir el monitor. No se mezclan fuentes/proyectos ni se
reinicia un servidor con trabajos activos para publicar la interfaz. No se interpretan
JSON de informes como código ni como instrucciones de ejecución.

## Fundamento consultado

La [maestría de Witossek, DLR/Leipzig2025](https://elib.dlr.de/220552/) fundamenta
evaluar el alumno en el dominio frente a maestro y base. El [doctorado de Stiasny,
DTU2023](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/)
fundamenta contrastar modelos físicos con el simulador. [Kreuzberger et al., IEEE
Access2023](https://doi.org/10.1109/ACCESS.2023.3262138) fundamenta orquestación,
registro, observación y ciclo de vida. Las referencias no acreditan resultados locales.
