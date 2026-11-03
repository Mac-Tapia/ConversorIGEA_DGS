# El gemelo con un sistema entero rechazaba cualquier sistema cuyas maniobras tuvieran variantes de demanda

## Síntoma
`entrenar` con `sistema` respondía «familia compartida entre particiones (060:RF-2)» y no entrenaba, aunque el sistema
tuviera episodios de sobra. Reproducido con datos sintéticos al cerrar la spec 044; no consta que un operador llegara a verlo.

## Causa
`curva.reparto_del_sistema` repartía por la huella de cada episodio (027:RF-68), y las variantes de demanda de una misma
maniobra comparten familia: caían a los dos lados de una partición. La comprobación de 060:RF-2 hacía bien en rechazarlo,
así que con ese reparto solo se podía entrenar un sistema en que cada familia tuviera un único episodio.

## Comprobación permanente
El reparto por sistema se hace por la huella de la familia, igual que `particionar`, y las cuatro particiones de la PINN
pasan por `particionar_registros` con la familia como grupo de custodia: ningún reparto futuro puede separar hermanos sin
que la promoción se bloquee, y lo que queda es la cuota que falte de verdad.

## Prueba
- `tests/test_calibracion_independiente.py::test_con_sistema_los_hermanos_no_cruzan_particiones`
- `tests/test_calibracion_independiente.py::test_entrenar_con_sistema_ya_no_choca_con_sus_hermanos`
- `tests/test_evaluacion_modelos.py::test_custodia_rechaza_familia_hermana_entre_particiones`
