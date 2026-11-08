# La prueba de importación rechazaba su propia fuente

Specs 081 RF-16 y 078 RF-19: fixture de importación y clasificación del resultado.

## Síntoma

`test_importacion_limpio_no_dice_ok` falla aislada con
`SOURCE_SELECTION_CHANGED`, antes de ejecutar el guion de prueba. La fuente
declarada por el helper no coincide con la selección del espacio de trabajo.

## Causa

El helper compartido `_importar` fijaba manualmente identidad, dataset y una
instantánea incompleta mediante `SimpleNamespace`, dejando la modalidad sin
seleccionar. Esa construcción anterior al contrato de selección custodiada
carecía también de su token. La guarda de producción rechazaba correctamente
el estado; no era un fallo de la clasificación eléctrica.

## Comprobación permanente

El helper usa archivos TXT sintéticos y los productores reales `set_input`,
`load_dataset` y `convert`, con un solo trabajador. Manifiesto, sidecar,
instantánea y recibo provienen de esa carga y conversión; el informe y vínculo
del guion falso usan la misma identidad. Se conserva el doble de la frontera
nativa y las aserciones existentes sobre clasificación, convergencia y cargas
sin servir. No se modifica ninguna guarda o servicio de producción.

Un control verifica tokens/recibo e identidad común de los artefactos. Tres
negativas cambian modalidad, generación o sidecar y exigen su bloqueo antes
del guion. No basta obtener un error cualquiera ni una clasificación falsa.

## Prueba

- `tests/test_comprobacion_flujo.py::test_importacion_limpio_no_dice_ok`
- `tests/test_senales_de_convergencia.py::test_fixture_importacion_custodia_la_fuente_convertida`
- `tests/test_senales_de_convergencia.py::test_fixture_importacion_cambiada_bloquea_antes_del_guion`
- `tests/test_senales_de_convergencia.py::test_importacion_que_no_calcula_no_dice_ok`

El fallo aislado y las cuatro regresiones nuevas rojas se conservan en
`D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/p25_g2_fallos_tempranos_20261108/`.
La carga y conversión son CPU sobre archivos sintéticos; el guion escribe un
informe de prueba. Esto no ejecuta PowerFactory ni acredita convergencia,
persistencia, licencia o aceptación eléctrica real. La puerta integral y las
aceptaciones nativas mantienen sus criterios y evidencias independientes.

La [tesis de maestría de Eriksson y Mosaddegh](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf)
sustenta conservar feedback identificable; la [tesis doctoral de Strandberg](https://www.es.mdu.se/publications/6347-Automated_System_Level_Software_Testing_of_Industrial_Networked_Embedded_Systems)
fundamenta separar contexto de ejecución y fallo reproducido; la [revisión
indexada de Shahin, Ali Babar y Zhu en IEEE Access](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/)
contextualiza estas comprobaciones en integración y entrega. Fuentes primarias
consultadas en la web: justifican el método, no certifican este producto.
