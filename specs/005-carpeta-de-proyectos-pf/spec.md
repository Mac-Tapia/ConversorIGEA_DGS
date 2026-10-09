# Spec 005 — Carpeta de proyectos importados en DIgSILENT

Estado: aprobada (2026-10-09) · Fecha: 2026-10-09 · Origen: prueba manual de «Leer proyectos de DIgSILENT» del 2026-10-09

## Contexto y objetivo

Cada DGS importado crea un proyecto suelto en la raíz del usuario de DIgSILENT, junto a
los proyectos hechos a mano y a los de otros trabajos. «Leer proyectos de DIgSILENT»
(spec 004, RF-2) recorre todos esos proyectos y, dentro de cada uno, busca los
alimentadores en todo su árbol: casos de estudio, variaciones, resultados y bibliotecas.
En la prueba del 2026-10-09 la lectura seguía en marcha a los seis minutos, con 3,7 GB de
memoria, y el botón quedó gris todo ese tiempo sin que el operador supiera por qué. El
usuario propone guardar los proyectos importados desde DGS en una carpeta propia de
DIgSILENT y leer solo esa carpeta: la lista muestra lo que el conversor importó, y
DIgSILENT no tiene que abrir proyectos ajenos.

## Usuarios / actores

- Ingeniero de planificación que importa DGS desde la web o con los guiones de `tools/`,
  y que luego elige un proyecto en la pestaña «Cargas en DIgSILENT».
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero que cada DGS que importo quede en una misma carpeta de
  DIgSILENT, para tener separados los proyectos del conversor de los demás.
- H2: Como ingeniero quiero que «Leer proyectos» liste solo los proyectos de esa carpeta,
  para elegir entre los míos sin esperar a que DIgSILENT abra todos los demás.

## Requisitos funcionales (EARS)

Carpeta

- RF-1: EL SISTEMA guardará los proyectos importados desde DGS en una carpeta de
  proyectos del usuario actual de DIgSILENT, que se llama carpeta de importación.
- RF-2: EL SISTEMA tomará el nombre de la carpeta de importación del perfil de empresa.
- RF-3: DONDE el perfil de empresa no da nombre de carpeta, EL SISTEMA usará el nombre
  «Conversor IGEA-DGS».
- RF-4: SI el nombre de la carpeta está vacío, supera 40 caracteres o lleva un carácter que
  DIgSILENT no admite en un nombre, ENTONCES EL SISTEMA rechazará el perfil con un error
  que nombre el valor, antes de abrir DIgSILENT.

Importación

- RF-5: CUANDO se importa un DGS y la carpeta de importación no existe, EL SISTEMA la
  creará en la raíz del usuario actual antes de importar.
- RF-6: CUANDO se importa un DGS, EL SISTEMA creará el proyecto dentro de la carpeta de
  importación, no en la raíz del usuario.
- RF-7: SI en la carpeta de importación ya hay un proyecto con el nombre pedido,
  ENTONCES EL SISTEMA importará con el primer nombre libre de la forma `<nombre>_2`,
  `<nombre>_3`…, y avisará en el informe del nombre que usó.
- RF-8: EL SISTEMA no borrará, sobrescribirá ni moverá un proyecto existente al importar.
- RF-9: SI el proyecto no se puede crear dentro de la carpeta, ENTONCES EL SISTEMA fallará
  esa importación con un error que nombre la carpeta, sin dejar el proyecto en la raíz.
- RF-10: EL SISTEMA aplicará RF-5 a RF-9 a toda importación de DGS, desde la web y desde los
  guiones de `tools/`.

Lectura de proyectos (sustituye a la spec 004, RF-2)

- RF-11: CUANDO el operador lee los proyectos, EL SISTEMA listará solo los proyectos de la
  carpeta de importación y de sus subcarpetas, y de cada uno, sus alimentadores.
- RF-12: EL SISTEMA mostrará cada proyecto de una subcarpeta con su ruta relativa a la
  carpeta de importación, por ejemplo «2026-10 / SI213».
- RF-13: EL SISTEMA buscará proyectos en las subcarpetas sin entrar en el contenido de
  ningún proyecto.
- RF-14: SI la carpeta de importación no existe, ENTONCES EL SISTEMA devolverá la lista
  vacía con un aviso que nombre la carpeta y diga que se crea al importar el primer DGS.
- RF-15: EL SISTEMA no creará ni modificará nada en DIgSILENT al leer los proyectos.
- RF-16: EL SISTEMA identificará el proyecto elegido por su ruta dentro de la carpeta de
  importación, de modo que dos proyectos con el mismo nombre en subcarpetas distintas
  sean dos opciones distintas.

Alimentadores de un proyecto

- RF-17: EL SISTEMA buscará los alimentadores de un proyecto solo en sus datos de red.
- RF-18: SI un proyecto no tiene datos de red reconocibles, ENTONCES EL SISTEMA buscará los
  alimentadores en todo el proyecto, como antes, y lo anotará en el registro del trabajo.
- RF-19: EL SISTEMA dará para cada proyecto la misma lista de alimentadores que la búsqueda
  en todo el proyecto, cuando el proyecto tiene datos de red.

Proyectos anteriores

- RF-20: EL SISTEMA dejará donde están los proyectos importados antes de esta spec.

## Requisitos no funcionales

- Idioma y estilo de la constitución (P10).
- La carpeta de importación es una convención de empresa: ningún nombre de una empresa
  concreta en el código ni como valor por defecto (P13).
- PowerFactory, en el carril `powerfactory` y como trabajo en cola (P7).
- Sin número fijo de proyectos ni de alimentadores en código ni en pruebas (P2).

## Casos límite

- Carpeta de importación vacía: lista vacía, sin aviso de carpeta inexistente.
- Carpeta con subcarpetas vacías o anidadas en varios niveles.
- Dos proyectos con el mismo nombre en subcarpetas distintas (RF-16).
- Un proyecto dañado o que no se puede leer: se lista sin alimentadores y se anota, como
  hoy; no tumba la lista.
- Una entidad que no es carpeta de proyectos con el nombre de la carpeta de importación
  en la raíz del usuario.
- Varias importaciones seguidas con el mismo nombre de proyecto (RF-7).
- Proyecto hecho a mano que el operador mueve a la carpeta, sin `ElmFeeder` (RF-18 y la
  regla de la spec 004 de mostrar sus `ElmNet`).

## Fuera de alcance

- Mover, copiar o borrar proyectos ya existentes, también los anteriores a esta spec.
- Listar proyectos fuera de la carpeta de importación.
- Elegir la carpeta en cada importación o lectura desde la web.
- Carpetas de otros usuarios de DIgSILENT o compartidas.
- Otros cambios en la pestaña «Cargas en DIgSILENT» que no sean mostrar e identificar el
  proyecto por su ruta (RF-12, RF-16).

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "005:RF-[0-9]+" tests | sort -u`).
- Suite en verde. Las pruebas usan un doble de la API de PowerFactory; la prueba en
  DIgSILENT real la hace el usuario a mano: importar dos DGS, uno con nombre repetido, y
  leer los proyectos.
- La spec 004, RF-2, remite a esta spec.

## Dudas abiertas

- Resuelta el 2026-10-09: el perfil de Electro Dunas lleva «sistemaeletricoELD», tal como
  lo escribió el usuario; corregir la grafía es cambiar el perfil, no el código.
- [NECESITA ACLARACIÓN: ¿el perfil de empresa de la web es hoy el sitio donde va el
  nombre, o debe esperar al perfil de empresa de la spec 002, RF-31? Se resuelve en el
  plan.]
