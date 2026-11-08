# Los procedimientos apuntaban a líneas desplazadas

Spec 077 RF-3: citas verificables de los procedimientos del asistente.

## Síntoma

Cuatro procedimientos fallan su comprobación de citas: once referencias a
líneas del backend quedaron fuera del margen permitido, aunque sus anclas
literales siguen presentes en el código actual.

## Causa

Los cambios del backend desplazaron endpoints, funciones y constantes sin
actualizar las referencias numéricas de esos Markdown. No había cambiado
el texto de las anclas ni el contexto operativo al que apuntaban.

## Comprobación permanente

Se actualizan solo los once números de línea de los cuatro procedimientos.
Se cotejan las anclas literales con la fuente y el contexto de función o
definición. Una constante con dos apariciones se enlaza a su definición,
conservando la intención de la cita. Instrucciones, anclas, rutas y RF no
cambian. El parser, su margen y sus aserciones permanecen intactos.

## Prueba

- `tests/test_procedimientos.py::test_cada_cita_casa_con_su_linea`
- `tests/test_procedimientos.py::test_cada_rf_citado_esta_definido`

La evidencia roja, propuestas y comparación de texto se conserva bajo
`p25_g2_binding_fixtures_20261108/doccites`. Si la integración vuelve a mover
el backend, debe revalidar estas citas contra su revisión final. No se cambian
corpus o referencias históricas de otras specs ni se acredita ejecución nativa.

La [maestría de Eriksson y Mosaddegh](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf),
el [doctorado de Strandberg](https://www.es.mdu.se/publications/6347-Automated_System_Level_Software_Testing_of_Industrial_Networked_Embedded_Systems)
y el [artículo indexado de Shahin, Ali Babar y Zhu](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/)
sustentan conservar contexto y feedback verificable. Son fuentes primarias
consultadas en la web, no certificación de este producto.
