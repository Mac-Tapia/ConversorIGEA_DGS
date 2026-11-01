# Plan — Spec 055

1. Fuente VNR-GIS: cada salida con su sistema eléctrico y su SET (código y nombre) en el
   inventario de la carga. TXT y MDB: lo que traigan; si nada, «sin SET».
2. `estructura_del_espacio`: Excel, perfil si cubre algún alimentador cargado, o la de la
   fuente; la web dice el origen.
3. Prueba con Electro Oriente por la web: sus sistemas y SET y la conversión de un sistema.
4. RF-6, RF-7: la empresa de la fuente (VNR-GIS: `empEmpresa`; TXT y MDB: la que diga, si dice)
   frente a la del perfil (`empresa` del perfil o de su perfil base). Si difieren, el espacio
   usa un perfil vacío con la carpeta del nombre de la empresa de la fuente; `perfil_de(ws)` es
   el único punto que lo decide, así que carpeta, CRS, SED de medición y escala lo siguen solos.
