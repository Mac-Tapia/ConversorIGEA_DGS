# Spec 008 — Pestaña «Cargas en DIgSILENT» en tres pasos

Estado: aprobada (2026-10-10) · Fecha: 2026-10-10 · Origen: uso real con SI213, 2026-10-10

## Contexto y objetivo

El operador trabaja sobre un proyecto que ya está en DIgSILENT, en este orden (usuario,
2026-10-10):

1. Elige el proyecto de DIgSILENT.
2. Calibra: busca la máxima de cabecera de cada alimentador del proyecto (uno o varios),
   sube los clientes importantes como demandas fijas y reparte el resto por kVA hasta
   que la cabecera dé la máxima (spec 006).
3. Verifica que el flujo de carga converge con la red calibrada y, solo entonces,
   integra lo nuevo: demandas en bloque, una carga nueva y cargas nuevas en bloque. Las
   tres son optativas, pero cada una tiene que funcionar cuando se usa.

La pestaña de hoy no sigue ese orden: tiene el paso 2 «Qué aplicar» antes de los
alimentadores, la calibración al final y solo para un alimentador, y la pestaña no se
ve hasta cargar entradas en el espacio, aunque no las use (spec 004, RF-1). Además, el
2026-10-10 «Ajustar SI213 a la máxima» terminó con «el guion terminó con el código 1 sin
dejar informe»: un error inesperado del guion se perdía en el Registro.

## Usuarios / actores

- Ingeniero de planificación que, desde la web, calibra y amplía un proyecto existente
  de DIgSILENT.
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero abrir la pestaña de cargas sin convertir nada, porque trabajo
  sobre un proyecto que ya está en DIgSILENT.
- H2: Como ingeniero quiero calibrar todos los alimentadores del proyecto de una vez,
  para no repetir el ajuste uno a uno.
- H3: Como ingeniero quiero comprobar que la red calibrada converge antes de integrar
  cargas, para no estudiar cargas sobre una red que no resuelve.

## Requisitos funcionales (EARS)

Acceso

- RF-1: EL SISTEMA mostrará la pestaña «Cargas en DIgSILENT» aunque el espacio no tenga
  entradas cargadas.
- RF-2: MIENTRAS el espacio no tenga entradas cargadas, EL SISTEMA ocultará las pestañas
  que las necesitan.

Pasos

- RF-3: EL SISTEMA presentará la pestaña en tres pasos numerados: «1 · Proyecto de
  DIgSILENT», «2 · Alimentadores y calibración» y «3 · Integración de nuevas».

Paso 1 — Proyecto

- RF-4: CUANDO se han leído los proyectos, EL SISTEMA permitirá filtrarlos escribiendo
  parte de su ruta y elegir uno de la lista filtrada.
- RF-5: SI el filtro no deja ningún proyecto, ENTONCES EL SISTEMA dirá que ninguno
  coincide.

Paso 2 — Alimentadores y calibración

- RF-6: CUANDO se elige un proyecto, EL SISTEMA marcará todos sus alimentadores, que el
  operador podrá desmarcar y ordenar.
- RF-7: EL SISTEMA usará los alimentadores marcados para la calibración y para la
  integración.
- RF-8: CUANDO el operador busca los medidores, EL SISTEMA los buscará en el libro de
  medidores para cada alimentador marcado.
- RF-9: SI un alimentador marcado no está en el libro de medidores, ENTONCES EL SISTEMA lo
  dirá con su nombre y dejará escribir su medidor a mano.
- RF-10: EL SISTEMA buscará la máxima de cabecera de todos los medidores elegidos en un
  solo trabajo.
- RF-11: EL SISTEMA cruzará los clientes importantes de los alimentadores marcados.
- RF-12: CUANDO el operador ajusta, EL SISTEMA ajustará uno tras otro, en un solo
  trabajo, cada alimentador marcado que tenga máxima, cada uno en su propia variación.
- RF-13: SI un alimentador tiene más de un medidor con máxima, ENTONCES EL SISTEMA pedirá
  el medidor de su cabecera antes de ajustar.
- RF-14: SI el ajuste de un alimentador falla o no cuadra, ENTONCES EL SISTEMA seguirá
  con el siguiente y lo informará en ese alimentador.
- RF-15: SI el operador cancela el ajuste, ENTONCES EL SISTEMA terminará el alimentador
  en curso y no empezará otro.
- RF-16: EL SISTEMA mostrará el informe del ajuste por alimentador.
- RF-17: SI un guion de DIgSILENT de esta pestaña termina por un error inesperado,
  ENTONCES EL SISTEMA escribirá un informe con el tipo y el mensaje del error, que la web
  mostrará en lugar de «sin dejar informe».

Paso 3 — Integración de nuevas

- RF-18: EL SISTEMA permitirá verificar la convergencia del proyecto, con las variaciones
  que tenga activas, sin escribir en él.
- RF-19: CUANDO termina la verificación, EL SISTEMA informará si el flujo converge, las
  tensiones mínima y máxima y lo que entra por la cabecera de cada alimentador marcado.
- RF-20: MIENTRAS el último flujo del proyecto elegido —verificación, ajuste aplicado o
  integración aplicada— no haya convergido, EL SISTEMA no permitirá aplicar la integración y dirá por qué.
- RF-21: EL SISTEMA permitirá simular la integración aunque la red no esté verificada.
- RF-22: EL SISTEMA presentará la integración en tres partes optativas, en este orden:
  «3.1 Demandas en bloque», «3.2 Una carga nueva» y «3.3 Cargas nuevas en bloque».
- RF-23: EL SISTEMA permitirá revisar y aplicar cualquier combinación no vacía de las tres
  partes.
- RF-24: CUANDO se aplica la integración, EL SISTEMA aplicará en cada alimentador las
  demandas en bloque, después la carga nueva del formulario y después las del libro.

## Casos límite

- Proyecto con un solo alimentador: el paso 2 funciona igual, con uno.
- Proyecto con muchos alimentadores: sin tope fijo; el ajuste los recorre en un trabajo.
- Alimentador sin medidor en el libro ni a mano: no se ajusta y se dice.
- Misma SED en el formulario y en el libro de cargas nuevas: se crea la del formulario y
  la del libro se informa como repetida (spec 004, RF-15).
- Lecturas de proyectos de antes de la spec 005, sin ruta: se filtra por el nombre.

## Fuera de alcance

- Una variación por carga nueva y la base del ajuste (spec 007).
- Importar a DIgSILENT un fichero `.pfd` desde la web.
- Volver a ajustar después de integrar cargas.

## Criterios de finalización

- `grep -rnoE "008:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-24.
- Suite completa en verde, también las pruebas de las specs 004, 006 y 007.
- `npx tsc --noEmit -p .` y `npm run build` en `frontend/` correctos.
- Prueba real en DIgSILENT con un proyecto de dos alimentadores, a cargo del usuario.
