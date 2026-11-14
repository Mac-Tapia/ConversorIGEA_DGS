# Spec 112 — Datasets de referencia anonimizados y benchmarks reproducibles

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-22 y BP-21, y orden del usuario del 2026-11-14:
«haz nuevos spec». G0: `D:/csg/G0_PLAN_MAESTRO/C/C_FILAS_BP.md` (BP-22: solo existe la anonimización del paquete de
soporte).

## Contexto y objetivo
La tesis y la evaluación necesitan comparar métodos con datos que se puedan compartir. Los datos reales de la
distribuidora no se publican (constitución, principio 9). G0 encontró que solo existe la anonimización del paquete de
soporte (`web/soporte.py:66-77@51895566`) y que no hay cohortes por empresa. Esta spec genera, desde los datos reales y
solo en local:
- benchmarks sintéticos o desidentificados con su manifiesto;
- protocolos de evaluación por cohortes de empresa y de tiempo.

Así los resultados se pueden reproducir sin revelar nada de la empresa.

## Usuarios / actores
- El investigador o la tesis.
- La evaluación de los modelos (089, 045 y 069).
- El revisor externo.

## Historias de usuario
- H1: Como investigador, quiero un paquete de redes y series desidentificadas, con su manifiesto y sus métricas de
  referencia, que pueda compartir sin datos de la empresa.
- H2: Como evaluador, quiero evaluar cada modelo con cohortes separadas por empresa y por tiempo.

## Requisitos funcionales (EARS)
- RF-1: CUANDO el operador genere un benchmark, EL SISTEMA lo creará en local desde los datos reales, sin enviarlos
  a ningún servicio externo.
- RF-2: EL SISTEMA reemplazará en el benchmark los identificadores, los nombres, las coordenadas absolutas y los
  códigos de cliente por valores sin relación recuperable con los originales.
- RF-3: EL SISTEMA conservará en el benchmark la topología, las fases, las impedancias y la forma de las series que
  hacen falta para que el estudio dé el mismo resultado dentro de la tolerancia declarada.
- RF-4: SI un control de reidentificación encuentra algún identificador, coordenada o patrón original, ENTONCES EL
  SISTEMA no emitirá el benchmark y dirá qué lo delató.
- RF-5: EL SISTEMA guardará con cada benchmark su manifiesto: la huella del origen (sin revelarlo), la versión del
  generador, la semilla, las transformaciones, la tolerancia y las métricas de referencia.
- RF-6: CUANDO se evalúe un modelo, EL SISTEMA podrá separar las cohortes por empresa (dejando una fuera) y por
  tiempo, sin que un mismo alimentador ni un mismo cliente caiga en dos particiones.
- RF-7: EL SISTEMA guardará el conjunto de prueba sellado antes de la selección del modelo, y su huella no cambiará
  después.
- RF-8: EL SISTEMA publicará también los resultados negativos de cada evaluación.
- RF-9: SI solo hay datos de una empresa, ENTONCES EL SISTEMA dirá en el informe que la generalización entre empresas
  no está demostrada.
- RF-10: EL SISTEMA no incluirá nunca en el benchmark el texto de los libros, de los informes ni de los documentos de
  la empresa.
- RF-11: DONDE el origen tenga un dataset de pronóstico de demanda (089), EL SISTEMA incluirá en el benchmark sus series
  desidentificadas, con las métricas de referencia de los métodos de base calculadas en el original y en el benchmark.

## Requisitos no funcionales
- Reproducible: con la misma semilla y el mismo origen sale el mismo benchmark, byte a byte.
- Universal: sirve para cualquier empresa.

## Casos límite
- Una red con un solo alimentador.
- Coordenadas que delatan la ciudad.
- Una serie con patrón único, como una carga industrial.
- Un cliente que aparece en dos alimentadores por una transferencia.

## Fuera de alcance
- Publicar en un repositorio público: la decisión y la acción son del usuario.
- Garantizar la privacidad diferencial formal.

## Criterios de finalización
Cada RF citado por una prueba (`grep "112:RF-"`). Hay una prueba de reidentificación negativa (un benchmark con
fugas plantadas se rechaza). El estudio sobre el benchmark reproduce el original dentro de la tolerancia en al menos
dos redes.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario (`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 5).
- Tolerancia de reproducción (RF-3): la de la spec del estudio correspondiente. Si el estudio no declara ninguna, 0,005
  p.u. en tensión y un 1 % en corriente (carga de líneas y transformadores). Para las series, la diferencia relativa de
  WAPE y MASE de cada método de base no pasa del 1 %. La tolerancia usada queda en el manifiesto (RF-5).
- Hay benchmark de redes y también de series de demanda: entra como RF-11.
