# Spec 103 — DIgSILENT de cualquier versión instalada

Estado: cumplida (2026-11-11: T1 a T7, candidato rc4 en la QA) · Fecha: 2026-11-11 · Origen: usuario, 2026-11-11: «la versión de DIgSILENT no debe ser limitativa:
debería conectarse a cualquier DIgSILENT que exista instalado, cualquiera que sea el del usuario».

## Contexto y objetivo

El conversor se probó con PowerFactory 2024 y quedó atado a esa versión: `powerfactory_env.DEFAULT_PF_PYTHON` apunta a
`PowerFactory 2024\Python\3.12` y gana aunque haya otra más nueva; entre las carpetas `Python\3.x` elige la más alta y
luego exige ese intérprete, de modo que una versión con API para 3.13 no carga con el Python 3.12 del programa; solo mira
`C:\Program Files\DIgSILENT`; y el diagnóstico pide «PowerFactory 2024 con su Python 3.12». La API de cada versión es una
extensión compilada para varias versiones de CPython (PowerFactory 2024 trae 3.8 a 3.12; las de 2021 y 2022, hasta 3.9 y
3.10), y solo carga en la misma versión. El DGS ya se escribe con el esquema de PowerFactory 2021 (`pf21_dgs_1_8_4`,
formato 7.0), que las versiones posteriores importan.

El objetivo es que el conversor encuentre la versión de PowerFactory que tenga el usuario, desde la 2021, y conecte con
ella sin que el operador instale nada ni toque variables.

Decisiones del usuario (2026-11-11): versión mínima 2021; con varias instaladas, la más nueva que funcione, elegible en la
web; el instalador comercial trae los intérpretes de Python que piden las versiones soportadas.

## Usuarios / actores

El operador de la web, el diagnóstico (`csg.cmd doctor`), los guiones de `tools/` que corren con el Python de PowerFactory
y el instalador comercial (spec 086).

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA encontrará todas las instalaciones de PowerFactory: las carpetas `DIgSILENT\PowerFactory *` de
  `Program Files` en cada unidad y las que registra Windows, con su versión (año y, si lo hay, service pack) y las carpetas
  `Python\3.x` que traen `powerfactory.pyd`.
- RF-2: PARA cada instalación, EL SISTEMA elegirá la carpeta de la API cuyo Python tenga intérprete: primero el del
  programa; luego los que trae el instalador (RF-6); luego los de la máquina (`CSG_PF_INTERPRETER`, el lanzador `py`, las
  rutas habituales). Nunca elegirá una carpeta sin intérprete si otra de la misma instalación lo tiene.
- RF-3: EL SISTEMA usará por defecto la instalación más nueva que funcione; `PF_PYTHON` sigue fijando una carpeta a mano.
  La web mostrará las instalaciones encontradas, dejará elegir otra y la recordará en la máquina, fuera de git.
- RF-4: Ningún mensaje, ruta por defecto ni diagnóstico nombrará una versión fija de PowerFactory o de Python; dirá las
  instalaciones encontradas y, si ninguna sirve, qué intérprete falta para cuál.
- RF-5: Los guiones de `tools/` que corren con el Python de PowerFactory, y lo que importan del conversor, cargarán con el
  Python más antiguo soportado (3.9) y solo con la biblioteca estándar y `numpy`.
- RF-6: El instalador comercial traerá los intérpretes de Python embebidos que piden las versiones soportadas y no
  coinciden con el del programa (3.9, 3.10 y 3.11), con `numpy`, verificados con su SHA-256.
- RF-7: CUANDO no haya ninguna instalación que funcione, EL SISTEMA seguirá convirtiendo a DGS y lo dirá; nada de la
  conversión depende de DIgSILENT.

## Requisitos no funcionales

- Universal (constitución P13): ninguna versión, unidad ni carpeta se supone; todo sale de lo instalado.
- Las pruebas simulan instalaciones con su árbol de carpetas; la aceptación real se hace con la que haya en la máquina.

## Fuera de alcance

Versiones anteriores a 2021; Linux; diferencias de comportamiento de la API entre versiones que no se manifiesten al
cargar (se tratan en la spec de cada guion cuando aparezcan en una corrida real).

## Criterios de aceptación

- Con una instalación simulada de 2021 (Python 3.9), 2022 (3.10), 2024 (3.8 a 3.12) y 2025 (3.10 a 3.13), el conversor
  elige la carpeta que encaja con un intérprete disponible, y por defecto la más nueva.
- Con la PowerFactory instalada en esta máquina, la web y el diagnóstico la encuentran sin variables.
