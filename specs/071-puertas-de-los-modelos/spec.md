# Spec 071 — Puertas de los modelos antes de entrenar: PINN en su red, un puntero, sin autoentrenamiento y una guardia de GPU

Estado: aprobada · Fecha: 2026-11-02 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-02: «antes de entrenar o implementar debemos saber si está correctamente implementado»; y
«primero haz en orden de 1 a 7 antes de entrenar». La auditoría de esa fecha, sobre main d5a9fa5a, halló que la PINN en
uso (`20261028-114528-e6f5`) dio MAE 0,0024 p.u. en una sola red de 4 944 nodos, mientras un candidato probado en otra red
dio 0,308 p.u.; y `fuera_de_dominio` solo mira rangos y número de nodos, no de qué red se trata. Sus puertas tampoco
comparan con la física ni con el modelo en uso. Esta spec cubre la parte de esa lista que no pertenece a `asistente/` ni al
pronóstico, según el reparto acordado entre sesiones (integrador de 065/070).

## Usuarios / actores

Ingeniero de planificación que optimiza obras desde la web; quien reentrena el gemelo; las demás sesiones que comparten GPU.

## Requisitos funcionales (EARS)

- RF-1: CUANDO se entrene la PINN, EL SISTEMA guardará en su dominio las huellas `red_de` de todas las redes de sus
  particiones, incluida la de prueba, que es donde se demostró su error.
- RF-2: SI la red consultada no está en las redes del modelo, o el modelo no las declara, ENTONCES EL SISTEMA la dará por
  fuera de dominio y decidirá el flujo físico (052:RF-17).
- RF-3: SI en la misma prueba el candidato no mejora al flujo físico, ENTONCES EL SISTEMA no lo promoverá y lo dirá.
- RF-4: SI en la misma prueba el candidato empeora al modelo en uso más allá de `tolerancia_dorados`, ENTONCES EL SISTEMA no
  lo promoverá y lo dirá.
- RF-5: CUANDO el monitor lea una PINN promovida cuya versión sea la del puntero en uso, EL SISTEMA la mostrará como
  promovida y en uso, sin anularla por falta de `active.json`.
- RF-6: MIENTRAS `CSG_AUTOENTRENAMIENTO` no valga `1`, la vigilancia no lanzará entrenamientos ni anunciará que se
  reentrena; sus demás funciones seguirán.
- RF-7: CUANDO `tools/digital_twin_entrenar.py` vaya a entrenar, EL SISTEMA tomará el turno de GPU común; SI está ocupado,
  ENTONCES no entrenará, escribirá el motivo en su informe y terminará con código 1.
- RF-8: `tools/llm_destilar.py` tomará el turno con `turno_gpu`, respetando `CSG_ML_GPU_LOCK` y la guardia heredada.

## Requisitos no funcionales

Sin respaldo a CPU. Nada de lo anterior toca el flujo de conversión ni los DGS.

## Casos límite

Un modelo anterior a esta spec no declara redes: pasa a física sin borrar sus pesos ni su puntero. Una red con obras que
añaden nodos tiene otra huella: decide la física, y DIgSILENT confirma (052:RF-5).

## Fuera de alcance

`asistente/`, `modelos_en_uso`, datasets, GRU, embeddings y `ORDEN_MODELOS`, que son de la sesión integradora y del pronóstico.
Que `Medida` combine tensión de la PINN y corrientes físicas (`optimizacion_oraculo.py`), a revisar cuando un modelo vuelva
a estar en dominio. Entrenar: esta spec no entrena nada.

## Criterios de finalización

Cada RF citado por una prueba, y suite completa sin omitidas.
