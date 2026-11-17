# Spec 102 — Puerta de calidad: ningún commit ni subida con la suite en rojo

Estado: aprobada (2026-11-14: RF-24 a RF-29, H13; 2026-11-15 ampliada por orden del usuario con RF-11 y RF-5 aclarados, T18 a T20: queda T20, la comparación de la suite entera repartida con la de una sola sesión; antes cumplida 2026-11-10: T4 con la suite completa sin omitidas y GitHub Actions en verde) · Fecha: 2026-11-09 · Origen: usuario, 2026-11-09: «debe tener o implementar CI/CD, no quiero ver más
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

- RF-5: CUANDO se sube a la rama principal (`main`), EL SISTEMA correrá la suite completa con todas las variables de datos reales (ver RF-18).
  - Aclaración (2026-11-15, PUERTA-XDIST, encargo de c2 por orden del usuario): CUANDO la puerta corra la suite entera
    (la subida, `--ci`, `--arbol` o un commit que la pide) y estén instalados pytest-xdist y psutil, EL SISTEMA medirá la
    memoria libre al arrancar y la repartirá en N procesos de CPU: N = (libre − `RESERVA_GIB`) / `GIB_POR_PROCESO`, con
    el tope `PROCESOS_MAXIMOS` (`CSG_PUERTA_PROCESOS`) y el de CPU. Con N ≥ 2, lo que no admite paralelo (la GPU por su
    marca `gpu` y los ficheros de `EN_SERIE` de `tests/conftest.py`, marca `serie`) corre en una sesión «serie», una
    prueba tras otra, a la vez que el resto en «reparto» (`-n N−1 --dist loadfile` desde N = 3); después, «a_solas» (lo
    que mide tiempos o el árbol entero) sin nada más. Las tres juntas son la suite entera y el juicio suma sus junit. SI
    no está pytest-xdist, o no hay memoria para dos, ENTONCES N = 1, una sola sesión, la orden de siempre, y lo dice.
    No cambia nada más: el junit, las variables, «0 fallidas, 0 omitidas», el gancho y el pre-push.
- RF-6: EL SISTEMA leerá las variables de datos reales de un fichero local fuera de git, o del entorno.
- RF-7: SI falta una variable de datos reales o su ruta no existe, ENTONCES EL SISTEMA detendrá la subida y la nombrará.
- RF-8: SI alguna prueba falla, ENTONCES EL SISTEMA detendrá la subida y nombrará las pruebas que fallan.
- RF-9: SI alguna prueba se omite, ENTONCES EL SISTEMA detendrá la subida y nombrará cada omitida con su motivo.
- RF-10: CUANDO la suite completa pasa sin omitidas, EL SISTEMA guardará el resultado con la revisión que se probó.
- RF-11: CUANDO se sube una revisión que ya pasó RF-10 con el árbol limpio, EL SISTEMA no volverá a correr la suite.
  - Aclaración (2026-11-15, PUERTA-ESPECULATIVA, encargo de c2 por orden del usuario): vale también para un ÁRBOL. La
    suite entera corrida con `tools/puerta_calidad.py --arbol` fuera de wt_integra, sobre el árbol T del índice
    (`git write-tree`, con el disco igual al índice), con los datos reales, deja su veredicto en
    `.git/puerta_calidad/arbol_<T>.json`, publicado con la escritura atómica única (001:RF-5) y firmado con el sha256 de
    cada junit (copiado al lado), el de la puerta, las variables que vio pytest (las de la puerta y las del fichero
    local, nombre y valor), el entorno (Python, sha256 del lock de dependencias y de los paquetes instalados) y la hora.
    CUANDO el gancho del commit tenga ese mismo árbol en el índice y el veredicto valga, EL SISTEMA no repetirá la
    suite, lo citará en su salida y dará su línea de siempre («Puerta de calidad: N pruebas, 0 fallidas, 0 omitidas.»).
    SI hay cualquier duda (otro árbol, otra puerta, otras variables, otro lock, otro Python u otros paquetes, un junit
    que no cuadra con su sha256 o que releído no da el mismo total, un veredicto con fallidas u omitidas, sin fecha, del
    futuro o de hace más de `HORAS_VEREDICTO_ARBOL` horas, 12 por omisión, `CSG_PUERTA_HORAS_VEREDICTO`), ENTONCES EL
    SISTEMA correrá lo de siempre: la suite entera si el commit la pide. Si el árbol cambia durante la suite, no queda
    veredicto aprobado.
  - Condición (2026-11-15, v2, auditor 0d): la reutilización vale SOLO en la rama de trabajo
    (`trabajo/puerta-por-ramas`) y en la del integrador que se funde en ella por avance rápido
    (`trabajo/integra-capas-suite`), `RAMAS_CON_VEREDICTO_DE_ARBOL`. En `main`, en otra rama o sin rama, el gancho del
    commit corre la suite aunque el veredicto valga; y la subida a `main` (RF-5) nunca consulta un veredicto de árbol:
    «main exige la completa».

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
- RF-18: CUANDO se sube a una rama de trabajo (cualquiera que no sea `main`), EL SISTEMA dejará subir sin la suite
  completa; GitHub Actions correrá allí la sintética (RF-12). La suite completa con los datos reales se exige una vez, al
  integrar en `main`. Usuario (2026-11-10): «cada vez que voy a hacer un trabajo voy a hacer commit, subir a GitHub y
  hacer la suite completa; eso no sería viable». Nada de esto toca la operación comercial: el operador no usa git.
- RF-19: CUANDO la puerta lance las pruebas desde un gancho de git, EL SISTEMA las lanzará sin las variables `GIT_*` que git
  pone al gancho. (2026-11-11: heredadas, el `git worktree add` de las pruebas del asistente usaba el índice de este
  repositorio y fallaba solo dentro de la puerta.)
- RF-20: CUANDO una prueba escriba variables de entorno del proceso o registre el cierre de la web, EL SISTEMA lo restituirá al terminar esa prueba,
  para que ninguna dependa del orden. (2026-11-11: `web.__main__.main` deja `CSG_WEB_HOST` y el puerto; en la puerta, con
  4 749 pruebas en un proceso, la ruta del libro de pérdidas y el cierre del lanzador fallaban y solas pasaban.)
- RF-21: EL SISTEMA correrá en cada commit la prueba de los procedimientos, que citan líneas de `src/`. (2026-11-11: al añadir
  el perfil en `services.py` se movieron cuatro citas y solo lo vio GitHub Actions.)
- RF-22: EL SISTEMA dará a cada prueba su propia guardia de GPU (`CSG_ML_GPU_LOCK`), no la de la máquina. (2026-11-11:
  con un entrenamiento real en marcha, 25 pruebas del oráculo fallaron en la puerta con «GPU ocupada».)
- RF-23: Toda variable `CSG_*` que una prueba nombre al omitirse, y toda la del ejemplo `config/suite_completa.example.json`,
  estará en la lista de la puerta; la puerta pasa a la suite solo las de esa lista. (2026-11-12: `CSG_PF_PYTHON_39`, de la
  spec 103, estaba en el fichero local y no en la lista, y la suite de la 086 T31 habría omitido dos pruebas.)
- RF-24: CUANDO un commit cambia algo de `frontend/`, o se sube a GitHub, la puerta y GitHub Actions pasarán también el lint de
  fronteras del frontend (`npm run lint`); SI no se puede pasar (sin node o sin sus dependencias), ENTONCES el commit se
  detendrá diciendo qué falta (H13, auditoría del 2026-11-14: RF-13 solo pedía el build y las pruebas).
- RF-25: GitHub Actions usará cada acción fijada por el SHA completo de su commit, con la etiqueta de la versión en un
  comentario, y nunca por una etiqueta que se pueda mover (H-CI1, auditoría del 2026-11-14).
- RF-26: EL SISTEMA dará al flujo de GitHub Actions solo permiso de lectura del repositorio (`contents: read`), declarado
  en lo más alto del flujo (H-CI2).
- RF-27: GitHub Actions descargará el repositorio sin guardar sus credenciales en la copia de trabajo (H-CI3).
- RF-28: CUANDO se sube a GitHub o se abre una petición de fusión, GitHub Actions pasará ruff con los errores de sintaxis
  y de nombres sin definir (`E9,F63,F7,F82`) antes de la suite sintética (H-CI4).
- RF-29: MIENTRAS una rama tenga abierta una petición de fusión, GitHub Actions dejará en marcha una sola corrida por
  revisión de esa rama, y la nueva cancelará la anterior (H-CI5: la subida y la petición se corrían dos veces).
- Aclaración de RF-29 (auditor 3e, 2026-11-14): en `main` la corrida nueva NO cancelará la anterior, para que cada commit de `main` conserve su corrida entera como evidencia de la etiqueta.

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
