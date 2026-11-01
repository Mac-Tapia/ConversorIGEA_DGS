# Spec 058 — ConverterSmartGrid: el proyecto sin el nombre de otra empresa

Estado: aprobada (2026-11-01) · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01:
«puedes cambiar el nombre del proyecto como convertersmartgrid»; «el nombre del proyecto, de
la carpeta principal y todo, para dejarlo limpio sin que mencione IGEA; IGEA es un software
de una empresa». Nombres técnicos elegidos por el usuario: `convertersmartgrid` y la sigla `CSG`.

## Contexto y objetivo

El proyecto se llama «Conversor IGEA-DGS» porque nació para los TXT de IGEA/CYMDIST. Hoy
convierte TXT, MDB y VNR-GIS de cualquier distribuidora (principio 13), e IGEA es el producto
de otra empresa: su nombre aparece en la carpeta principal, el paquete Python (`igea_dgs`), los
comandos (`igea-dgs`, `igea-dgs-web`), 52 variables de entorno `IGEA_*`, el título de la web, la
cabecera del DGS, la carpeta por defecto y los proyectos de DIgSILENT, las skills y la
documentación: 511 ficheros y unas 3 165 menciones el 2026-11-01. Esta spec da al proyecto su
nombre propio, ConverterSmartGrid, y deja el repositorio sin menciones de IGEA.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA se presentará como «ConverterSmartGrid» en la web, en la cabecera del DGS,
  en los informes y en la documentación.
- RF-2: EL SISTEMA tendrá su código en el paquete Python `convertersmartgrid`, distribuido con
  ese nombre, con los comandos `convertersmartgrid` y `convertersmartgrid-web`.
- RF-3: EL SISTEMA leerá sus variables de entorno con el prefijo `CSG_` en lugar de `IGEA_`.
- RF-4: EL SISTEMA nombrará cada proyecto nuevo de DIgSILENT con la sigla `CSG` en lugar de
  `IGEA`, sin pasar de 40 caracteres.
- RF-5: DONDE el perfil de empresa no da nombre de carpeta de DIgSILENT, EL SISTEMA usará
  «ConverterSmartGrid» (cambia 005:RF-3).
- RF-6: EL SISTEMA vivirá en la carpeta principal `ConverterSmartGrid`, y la web, el acceso
  directo del escritorio, el entorno `.venv` y los espacios de trabajo guardados seguirán
  funcionando tras el cambio.
- RF-7: EL SISTEMA llamará a sus skills, su lanzador y sus guías con el nombre nuevo.
- RF-8: EL SISTEMA tendrá una prueba que falle si un fichero del repositorio menciona «IGEA»,
  salvo las excepciones de RF-9.
- RF-9: Quedan con su nombre, por ser datos o historia y no del proyecto: el historial de git,
  los ficheros de datos de la distribuidora (fuera de git), los proyectos ya importados en
  DIgSILENT y las citas literales de una fuente que se llama así (por ejemplo, una columna de
  un TXT).
- RF-10: EL SISTEMA dará con los TXT el mismo DGS que antes byte a byte, salvo la cabecera
  (RF-1), y la suite completa pasará sin ninguna omitida.

## Fuera de alcance

- Renombrar los proyectos ya importados en DIgSILENT (nota «no tocar proyectos ya trabajados»).
- Reescribir el historial de git.
- Los mensajes que nombran la fuente equivocada en un VNR-GIS (spec 056).

## Relación con otras specs

- Cambia 005:RF-3 (carpeta por defecto). Completa la spec 056, que deja a cada fuente hablar con
  sus propias palabras; esta quita el nombre de IGEA del proyecto mismo.

## Criterios de finalización

- `grep -rnoE "058:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-10.
- `git grep -i igea` sin resultados fuera de RF-9; la web abierta desde el acceso directo
  «ConverterSmartGrid», y un alimentador importado en DIgSILENT con el nombre nuevo.
