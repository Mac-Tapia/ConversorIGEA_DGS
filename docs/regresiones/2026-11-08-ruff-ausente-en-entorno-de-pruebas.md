# La guarda de nombres no encontraba su analizador

Spec 081: preparar las dependencias de la verificación de desarrollo.

## Síntoma

`test_ningun_nombre_sin_definir` falla porque su proceso hijo responde
`No module named ruff`. No es un hallazgo F821 producido por el analizador:
Ruff no llega a ejecutarse en el intérprete de pytest.

## Causa

La prueba invoca Ruff con `sys.executable -m ruff`, pero el extra `dev` no lo
declaraba. Disponer de un ejecutable Ruff en otro entorno no satisface ese
contrato ni demuestra que la prueba haya verificado los nombres del programa.

## Comprobación permanente

Se agrega `ruff>=0.16.9,<0.17` al extra de desarrollo, conservando los requisitos
previos, y se explica el intérprete compartido con pytest en el README. La
guarda F821 no cambia: no se añaden excepciones, no se silencian retornos y
no se busca otro ejecutable como sustitución. No cambia el núcleo ni el
complemento de capacidades, que excluyen dependencias de desarrollo.

## Prueba

- `tests/test_nombres_definidos.py::test_ningun_nombre_sin_definir`

El diagnóstico rojo existente está en `p25_nombres_definidos_20261108`. Su
contraste estático externo sobre la revisión congelada no se presenta como
pase de esta prueba. Declarar la dependencia tampoco instala Ruff: la prueba
se revalida en el entorno preparado por el integrador al terminar su puerta
congelada, sin alterar esa puerta durante su ejecución.

La versión se consulta en [PyPI oficial](https://pypi.org/project/ruff/0.16.9/).
La [maestría de Eriksson y Mosaddegh](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf),
el [doctorado de Strandberg](https://www.es.mdu.se/publications/6347-Automated_System_Level_Software_Testing_of_Industrial_Networked_Embedded_Systems)
y el [artículo indexado de Shahin, Ali Babar y Zhu](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/)
fundamentan explicitar herramientas, feedback y contexto de prueba. Son
fuentes primarias consultadas en la web; no certifican la aceptación nativa,
científica ni comercial de este producto.
