# Spec 102 — Puerta de calidad: ningún commit ni subida con la suite en rojo

Estado: aprobada · Fecha: 2026-11-09 · Origen: usuario, 2026-11-09: «debe tener o implementar CI/CD, no quiero ver más
fallas repetitivas; esas cosas ya se habían superado, pero veo que sigue fallando».

## Contexto y objetivo

El 2026-11-08 dos commits (`0764411e` y `c64ec087`) entraron en `main` con tres pruebas en rojo: el plan de la 013 citaba
un documento que no existe, la T12 de la 065 se retiró sin ajustar su prueba y el aprendizaje del gemelo leía una carpeta
que su prueba no tenía. Nada lo impedía: el repositorio no tenía CI y los ganchos de `.githooks/` solo regeneraban el
catálogo de la arquitectura (spec 090). El objetivo es que un commit no entre con pruebas en rojo, que una subida no salga
sin la suite completa en verde y sin omitidas, y que GitHub repita en cada subida la parte que puede correr allí.

## Usuarios / actores

Toda persona o agente que haga commit o suba `main` desde un clon con los ganchos activos, y GitHub Actions.

## Requisitos funcionales (EARS)

Antes del commit

- RF-1: CUANDO se hace un commit, EL SISTEMA correrá las pruebas de gobierno del repositorio: inventario, trazabilidad y
  estado de las specs, y auditoría de raíz.
- RF-2: CUANDO se hace un commit, EL SISTEMA correrá también las pruebas de los ficheros de prueba del commit y las que
  nombran un módulo de `src/` o una herramienta de `tools/` del commit.
- RF-3: SI alguna prueba de RF-1 o RF-2 falla, ENTONCES EL SISTEMA detendrá el commit y nombrará las pruebas que fallan.
- RF-4: CUANDO el commit solo trae ficheros que no son de código ni de specs, EL SISTEMA correrá solo las pruebas de RF-1.

Antes de subir

- RF-5: CUANDO se sube una rama, EL SISTEMA correrá la suite completa con todas las variables de datos reales.
- RF-6: EL SISTEMA leerá las variables de datos reales de un fichero local fuera de git, o del entorno.
- RF-7: SI falta una variable de datos reales o su ruta no existe, ENTONCES EL SISTEMA detendrá la subida y la nombrará.
- RF-8: SI alguna prueba falla, ENTONCES EL SISTEMA detendrá la subida y nombrará las pruebas que fallan.
- RF-9: SI alguna prueba se omite, ENTONCES EL SISTEMA detendrá la subida y nombrará cada omitida con su motivo.
- RF-10: CUANDO la suite completa pasa sin omitidas, EL SISTEMA guardará el resultado con la revisión que se probó.
- RF-11: CUANDO se sube una revisión que ya pasó RF-10 con el árbol limpio, EL SISTEMA no volverá a correr la suite.

En GitHub

- RF-12: CUANDO se sube a GitHub o se abre una petición de fusión, GitHub Actions correrá la suite sintética en Windows con
  Python 3.12.
- RF-13: CUANDO se sube a GitHub o se abre una petición de fusión, GitHub Actions construirá el frontend y correrá sus
  pruebas.
- RF-14: SI una prueba sintética falla en GitHub, ENTONCES el flujo de GitHub quedará en rojo.
- RF-15: EL SISTEMA no llevará a GitHub ningún dato de la distribuidora ni el fichero de variables de RF-6. Las pruebas de
  datos reales solo corren en RF-5.

Instalación

- RF-16: EL SISTEMA dejará los ganchos activos con la misma orden que ya los instala (090:RF-11).
- RF-17: GitHub Actions correrá la suite sintética en un entorno como el de desarrollo: un `.venv`, `requirements.txt`, el
  extra `ml`, las herramientas del frontend e Ipopt oficial comprobado por su SHA-256 (048 T3b). SI allí una prueba falla porque no hay GPU CUDA (`SinGPU`), ENTONCES quedará
  omitida con ese motivo; cualquier otro fallo seguirá en rojo, y en la máquina de desarrollo esa regla no se activa.
  (2026-11-10: el primer flujo instalaba solo `requirements.txt` y 71 pruebas fallaban solo en GitHub.)

## Requisitos no funcionales

- Universal: el fichero de variables no supone ninguna empresa (constitución P13); su ejemplo usa rutas genéricas.
- El catálogo de la arquitectura se sigue regenerando antes de las pruebas del commit (090:RF-11).

## Casos límite

- Un commit de fusión sin cambios de código: solo RF-1.
- El fichero de variables trae una ruta que ya no existe: RF-7.
- SQL Server parado: la prueba de VNR-GIS se omite y RF-9 detiene la subida.

## Fuera de alcance

- Desplegar la web o publicar instaladores (la versión 1.0 es de la 086).
- Correr DIgSILENT desde la puerta: sus aceptaciones siguen en `tools/aceptacion_nativa.py` (084:RF-21).

## Criterios de finalización

Cada RF citado por una prueba (`grep -rnoE "102:RF-[0-9]+" tests`), los ganchos activos en este clon, una subida que
pasa la puerta completa y el flujo de GitHub en verde.
