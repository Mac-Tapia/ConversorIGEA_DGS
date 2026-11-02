# Spec 066 — Cada informe con su libro Excel, según el perfil de la empresa

Estado: implementada · Fecha: 2026-11-02 · Origen: petición del usuario, 2026-11-02 («si debe ir del libro,
cada informe debe tener su libro; son datos para la empresa Electro Dunas, solo se usa en informes o estudios
para Electro Dunas»).

El informe modelo de Electro Dunas tiene un libro par (`informeModeloperdidas.xlsx`): su hoja `Informe` arma las
tablas con las hojas de resultados y da el precio de compra. El informe solo leía de él dos hojas: se usó un precio
de 0,1443 S/./kWh sin fuente y el libro dice 0,2307. El libro trae además datos escritos a mano de EMAPICA, que no
deben llegar al libro de otro cliente, como la solicitud de Minera Santa María llegó al informe de INKA (063:RF-48).

## Requisitos

- RF-1: DONDE el perfil de empresa declare el libro del informe, EL SISTEMA dejará junto a cada informe de
  factibilidad un libro Excel relleno a partir del modelo.
- RF-2: DONDE el perfil de empresa no declare el libro del informe, EL SISTEMA no generará libro ni lo señalará como
  hueco.
- RF-3: DONDE el perfil declare la celda del precio de compra, EL SISTEMA lo leerá del libro de pérdidas.
- RF-4: EL SISTEMA tomará del perfil las hojas y las celdas de cada dato.
- RF-5: EL SISTEMA conservará las fórmulas del modelo que el perfil no declare.
- RF-6: EL SISTEMA quitará del libro las hojas, los comentarios, los vínculos externos, las imágenes y los textos del
  caso del modelo que el perfil declare.
- RF-7: SI queda en el libro una palabra que el perfil declara del caso del modelo, o un error de fórmula, ENTONCES
  EL SISTEMA lo avisará nombrando la hoja y la celda.
- RF-8: SI falta un dato del informe, ENTONCES EL SISTEMA dejará vacía su celda y la nombrará entre los huecos del
  libro.
- RF-9: SI Excel no puede generar el libro, ENTONCES EL SISTEMA dirá el motivo y conservará el Word.
- RF-10: SI el importe de pérdidas no reconocidas del libro se separa más de 1 S/. del informe, ENTONCES EL SISTEMA lo
  avisará.
- RF-11: CUANDO el libro se genere, EL SISTEMA lo ofrecerá en la web junto al Word.
- RF-12: DONDE el perfil declare el libro del informe, EL SISTEMA también lo dejará junto a cada informe de estudio.

## Fuera de alcance

- Corregir o regenerar los informes ya entregados.
- Calcular la capacidad de los equipos de salida (cable, TC y troncal): la red exportada no la trae y queda como hueco.
- El estado «Cargas nuevas»: el libro modelo solo tiene los estados actual y proyectado.
