# Spec 056 — Nombres y mensajes según la fuente: cada fuente con sus propias palabras

Estado: aprobada (2026-11-01) · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01, al convertir
NJA202 (W12882) de Electro Oriente desde su VNR-GIS: «¿por qué aparece IGEA y CYMDIST? Esto no
debería aparecer, la otra empresa no usa esos software; si es universal, nada debería aparecer
como o con esos».

## Contexto y objetivo

La fuente VNR-GIS (spec 023) se traduce por dentro a tablas con la forma de CYMDIST, y los
textos se escribieron para los TXT. Una conversión de Electro Oriente salió el 2026-11-01 con
el proyecto `20261101-063543_IGEA_W12882`, la cabecera del DGS «CYMDIST to DIgSILENT DGS
converter … IGEA», avisos como «0 conservaron Length del TXT», «CYMDIST B1/B0», «Full IGEA line
geometry» o «el RED export no trae REGULATOR SETTING (solo catálogo BD_Equipo)», y la web
titulada «Conversor IGEA/CYMDIST → DGS». Contradice el principio 13 y hace creer al operador
que su VNR-GIS se cargó como TXT.

Ninguna spec trata los textos por fuente. La carpeta de DIgSILENT de cada empresa ya la regula
la spec 005 (RF-2, RF-3) y no entra aquí.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA nombrará cada proyecto que importe en DIgSILENT con la fuente de la que
  viene (TXT, MDB o VNR-GIS) y sin «IGEA» ni «CYMDIST» si no es un TXT de CYMDIST.
- RF-2: EL SISTEMA seguirá reconociendo como suyos los proyectos ya importados con el nombre
  anterior (028:RF-7).
- RF-3: EL SISTEMA escribirá en la cabecera del DGS la fuente de la que viene, sin «CYMDIST» ni
  «IGEA» si no es un TXT de CYMDIST.
- RF-4: EL SISTEMA nombrará en cada aviso e informe los ficheros, tablas o campos de la fuente
  que se cargó, nunca los de otra; lo que esa fuente no puede traer no se avisa con los nombres
  de otra.
- RF-5: EL SISTEMA solo nombrará CYMDIST en la opción de entrada de los TXT y de la .mdb; el
  título de la web es el de la spec 058.
- RF-6: EL SISTEMA tendrá una prueba que falle si una conversión de MDB o de VNR-GIS deja
  «IGEA», «CYMDIST», «TXT», «BD_Equipo» o «RED export» en sus salidas o en el nombre del
  proyecto.

## Fuera de alcance

- La carpeta de DIgSILENT de cada empresa (spec 005).
- El nombre del proyecto, su paquete y su carpeta: los cambia la spec 058 (ConverterSmartGrid).
- Renombrar los proyectos ya importados.

## Relación con otras specs

- Aplica el principio 13 a lo que ve el operador; respeta el reconocimiento por prefijo de
  028:RF-7 y el corpus del asistente (specs 026, 027), que aprende los nombres de proyecto.

## Criterios de finalización

- `grep -rnoE "056:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-6.
- NJA202 convertido e importado por la web sin esas palabras en sus salidas ni en su proyecto.
