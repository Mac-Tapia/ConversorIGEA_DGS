# Spec 030 — Los años del PIDE en casos y escenarios de DIgSILENT

Estado: pedida por el usuario el 2026-10-28 («para ser más organizados, estos años 0, 4, 8, 12, 16
y 20 en DIgSILENT se crean en carpetas, y de la misma manera en escenarios de operación»; «es
porque habrá casos sin proyecto, con proyecto y con cargas nuevas, e igual para escenarios de
estudio, en cada año propuesto»).
La proyección econométrica con variables exógenas, que la 029 dejó para «la 030», pasa a la 031.

## Por qué

El PIDE (024:RF-51, RF-53) escalaba la demanda de cada año en memoria y la devolvía al terminar:
el proyecto no guardaba nada, y para ver en DIgSILENT la red del año 12 había que rehacerlo a
mano. Con un caso y un escenario por año, ordenados en su carpeta, el operador abre cualquier
año, mira su flujo y sus problemas, y las obras de ese año se prueban en él.

## Requisitos

- RF-1: CUANDO se ejecute el PIDE, EL SISTEMA creará en la carpeta de casos de estudio del
  proyecto una carpeta «PIDE» con una carpeta por año del horizonte («Año 00», «Año 04»…), y en
  cada una los casos «Sin proyecto», «Cargas nuevas» y «Con proyecto», copias de los del proyecto
  (los de su año de medición, si los hay); el que no exista en el proyecto no se crea.
- RF-2: EL SISTEMA creará en la carpeta de escenarios de operación la misma estructura, «PIDE» y
  una carpeta por año, con un escenario por caso con su mismo nombre, y lo dejará activo en él.
- RF-8: EL SISTEMA marcará las copias de cada año con su propio papel, para que no se confundan
  con los casos del proyecto.
- RF-3: EL SISTEMA escribirá en el escenario de cada año la demanda de cada carga escalada con la
  tasa de su alimentador ((1 + tasa)^año, spec 029) o la del sistema.
- RF-4: EL SISTEMA diagnosticará cada año en su «Sin proyecto», con su escenario.
- RF-5: SI ya existen el caso o el escenario de un año de una corrida anterior, ENTONCES EL SISTEMA
  los renovará con la demanda de ahora, sin duplicarlos.
- RF-6: EL SISTEMA no tocará el «Caso base», «Sin proyecto», «Con proyecto» ni sus escenarios, y
  al terminar dejará activo el caso que estaba.
- RF-7: EL SISTEMA dirá en el informe del PIDE el caso y el escenario de cada año.

## Fuera de alcance

- Aplicar en los casos de cada año las obras del PIDE: siguen en «Con proyecto» (024:RF-46, RF-47).
- La proyección econométrica (spec 031).
