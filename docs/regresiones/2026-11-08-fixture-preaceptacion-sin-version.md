# Manifiesto de prueba sin versión en la preaceptación

Spec 065 RF-21; diagnóstico de la puerta G2 sobre
`c6ec7fb8e4b6499128d01e829d5716f4e8d53ccf`.

## Síntoma y causa

`test_control_sellado_no_certifica_fisica` falla aislada porque la fixture
`caso` crea un manifiesto sin `version`. El lector canónico exige el entero
`1` y lo rechaza correctamente. El rechazo del esquema también hacía pasar
varias negativas sin alcanzar la manipulación que pretendían comprobar.

## Corrección y regresión

Solo cambia la fixture de `tests/test_aceptar_dominio.py`: declara `version: 1`.
Las negativas de fuente modificada, replay con otro run, vínculo alterado y
slot repetido comprueban ahora su motivo concreto. Cuatro casos adicionales
parten de una fixture válida y retiran o alteran la versión: ausente,
booleano, futura y texto siguen bloqueados. La preaceptación continúa sin
aceptación eléctrica y sin operaciones nativas. No cambia código de producto,
firmas, sellos, umbrales ni reglas físicas.

El caso original produjo un fallo aislado. Con las aserciones reforzadas y
antes de corregir la fixture, el módulo produjo 9 fallos y 8 pases; después,
17 pases. Son ejecuciones CPU sobre archivos sintéticos custodiados, sin
motor nativo. No acreditan licencia, persistencia ni aceptación del dominio.

El segundo identificador provisional de G2,
`tests/test_ajuste_cabecera_guion.py::test_cancelar`, pasó aislado y con sus
31 predecesores del mismo módulo (32 pases, con `fake_pf`). No se modifica:
esa comprobación no determina qué caso corresponde al marcador de la puerta
global, cuyo JUnit final aún no estaba disponible.

Evidencia externa:
`D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/p25_g2_fallos_tempranos_20261108/`.

## Fundamento del método y límites

La [tesis de maestría de Eriksson y Mosaddegh](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf)
sustenta mantener feedback identificable de las comprobaciones; la
[tesis doctoral de Strandberg](https://www.es.mdu.se/publications/6347-Automated_System_Level_Software_Testing_of_Industrial_Networked_Embedded_Systems)
motiva separar reproducción aislada, secuencia y contexto al analizar fallos;
la [revisión de Shahin, Ali Babar y Zhu en IEEE Access](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/)
contextualiza el feedback automatizado en integración y entrega. Son fuentes
primarias consultadas en la web; justifican el método, no certifican este
producto ni convierten estas pruebas enfocadas en una puerta integral verde.
