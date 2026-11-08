# Las pruebas Node fallaban en la copia de portabilidad

Spec 065 RF-9: las mismas pruebas ligeras desde rutas ordinarias y con espacios y eñe.

## Síntoma

`test_las_pruebas_del_frontend_dan_lo_mismo_con_y_sin_espacios` falla aislada:
Node informa `ERR_MODULE_NOT_FOUND` para `scripts/fronteras.mjs`. El módulo de
fronteras no llega a ejecutar sus casos; no demuestra un fallo de una ruta con
espacios ni de la arquitectura del código entregado.

## Causa

La fixture copiaba `src`, pruebas ligeras y `package.json`. La prueba nueva de
fronteras importa el comprobador canónico desde `scripts` y este lee el
`tsconfig.json` del proyecto. Esas dependencias propias no estaban en la copia.
El fallo se producía también en la ruta sin espacios.

## Comprobación permanente

La preparación copia el comprobador real y su configuración, junto con los
archivos que ya copiaba. Mantiene la misma selección de pruebas ligeras y su
comparación de retornos y recuentos no vacíos. No crea fachadas, no cambia
aserciones Node ni toma código fuente del checkout original durante el ensayo.
Solo las dependencias de terceros se comparten mediante el enlace existente.

Cada hijo recibe un directorio propio para sus fixtures de fronteras, dentro
de la raíz temporal ensayada. Se conservan stdout/stderr como bytes y se
decodifican para el diagnóstico. `finally` retira únicamente el enlace a
dependencias creado en cada copia, sin modificar el destino compartido.

## Prueba

- `tests/test_frontend_rutas.py::test_las_pruebas_del_frontend_dan_lo_mismo_con_y_sin_espacios`
- `tests/test_frontend_rutas.py::test_ninguna_prueba_ni_guion_del_frontend_usa_la_ruta_sin_decodificar`

La reproducción roja, el resultado verde y los logs de ambas rutas están en
`D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/p25_g2_fallos_tempranos_20261108/`.
Ambas rutas ejecutan los mismos 74 casos ligeros, sin fallos ni omisiones.
La prueba de compilación pesada conserva su exclusión preexistente y su
criterio independiente. No se ejecutan instalación, compilación de producción
ni motores nativos; estos pases no acreditan la entrega comercial completa.

La [tesis de maestría de Eriksson y Mosaddegh](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf)
sustenta el feedback de pruebas reproducibles; la [tesis doctoral de Strandberg](https://www.es.mdu.se/publications/6347-Automated_System_Level_Software_Testing_of_Industrial_Networked_Embedded_Systems)
fundamenta comprobar el contexto de ejecución; la [revisión indexada de Shahin,
Ali Babar y Zhu en IEEE Access](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/)
contextualiza estas comprobaciones en integración y entrega. Son fuentes
primarias consultadas en la web, no certificación de este programa.
