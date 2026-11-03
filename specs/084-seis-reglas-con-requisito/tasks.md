# Tareas — Spec 084

- [x] T1 Sitio de la SET nueva: distancias, apartar, estado y frase. (RF-1 a RF-7, RF-10)
  Hecho cuando: `pytest -q tests/test_seis_reglas.py -k "distancia or aparta or sitio or calles or retiro or libre or flujos_de_otro"` en verde.
- [x] T2 La web y el guion apartan la SET, y los dos flujos en el punto final, con doble. (RF-8, RF-9, RF-11)
  Hecho cuando: `pytest -q tests/test_seis_reglas.py -k "guion or converge or web"` en verde.
- [x] T3 Ternas subterráneas: configuración, capacidad, oráculo e informe. (RF-12 a RF-18)
  Hecho cuando: `pytest -q tests/test_seis_reglas.py -k "ternas or configuracion or capacidad or fabricante or oraculo or instalacion or aerea"` en verde.
- [x] T4 Bancos: tope y lo más barato que cumple, en máxima y en valle. (RF-19, RF-20)
  Hecho cuando: `pytest -q tests/test_seis_reglas.py -k "tope or maxima"` en verde.
- [x] T5 Pruebas sin DIgSILENT real y asistente sin nombres desconocidos. (RF-21, RF-22, RF-23)
  Hecho cuando: `pytest -q tests/test_seis_reglas.py -k "digsilent_real or aceptacion or nombres"` en verde.
- [x] T6 Borrar solo en el proyecto de la orden, y el inventario de borrados. (RF-24 a RF-27)
  Hecho cuando: `pytest -q tests/test_seis_reglas.py -k "borrar or borra or borrado or deshacer"` en verde.
- [x] T7 Orden de las alternativas, trecho y plano. (RF-28, RF-29, RF-30)
  Hecho cuando: `pytest -q tests/test_seis_reglas.py -k "bancos_y_despues or trecho"` en verde.
- [ ] T8 [DIgSILENT] La SET nueva con `planificacion.sitio_set`, en un proyecto de prueba ya importado de quien tenga el turno, sin datos inventados.
  Hecho cuando: los intentos quedan fuera del trazado y el flujo equilibrado y el desequilibrado corren en el punto final y dejan `iopt_net` como estaba.
- [ ] T9 [DIgSILENT] Una terna más en un tramo de cable con la tabla del fabricante, sobre una copia de un proyecto importado.
  Hecho cuando: `fline` queda en la variación, sale al desactivarla, y `c:loading` usa esa capacidad.
