# Spec 072 — PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio

Estado: aprobada · Fecha: 2026-11-02 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-02: «el PIDE en su metodología y criterios tiene dos entregables: un PIDE y otro planeamiento de
largo plazo; para esto hemos implementado los pronósticos, se traslada caso por caso de estudio por años; lo que todo se
hizo es un caso de año cero o caso base». Sobre el año: «sí se presenta en año 2027; recuerda que esto no debe ser fijo
porque se presenta cada 4 años». Sobre los costos: «el VNR y SICODI, como los módulos aprobados para PIT, son públicos;
están en la página de Osinergmin de cada empresa».

Hoy el conversor diagnostica por años y da una propuesta parcial de obras, pero no genera ninguno de los dos entregables.
La referencia son los entregables de Electro Oriente: `PIDE 2026` (4.1 largo plazo y 4.2 PIDE, año 0 = 2025) y `PIDE 2021`
(informes sucesivos). Sus cifras son referencia de forma y contenido, no verdad: tienen incoherencias propias (103
proyectos en ALT1 y 81 hojas de evaluación; años 02-07 frente a los 04-07 de la norma).

La norma de partida es RM 428-2017-MEM/DM, que `config/pide_universal_2017.json` marca como prepublicación: su vigencia se
confirma antes de citarla como obligatoria en un entregable.

## Usuarios / actores

Ingeniero de planificación de cualquier distribuidora, desde la web; el asistente, por las mismas rutas.

## Requisitos funcionales (EARS)

### Estudio y años

- RF-1: CUANDO se cree un estudio, EL SISTEMA pedirá el año de presentación y calculará de él el año 00 como el anterior a la
  presentación (art. 7.2). Ningún año irá escrito en el código: la presentación se repite cada 4 años.
- RF-2: EL SISTEMA calculará desde el año 00 los años de largo plazo (04, 08, 12, 16, 20; arts. 5.1, 9) y los de detalle del
  PIDE (04 a 07; art. 11.2), con el horizonte en la configuración de la metodología.
- RF-3: SI la medición que calibró el caso base no es del año 00, ENTONCES EL SISTEMA lo dirá y seguirá (030:RF-12).
- RF-4: EL SISTEMA generará los dos entregables desde un mismo estudio: el PIDE consume el largo plazo, no lo vuelve a calcular
  (arts. 5.1, 6.1).

### Fuentes de costos

- RF-5: EL SISTEMA leerá los costos por un único contrato de fuente, con adaptadores para SICODI (distribución), módulos
  estándar (transmisión, PIT) y libro CAPEX; cada costo declarará fuente, resolución, año, moneda y sector típico.
- RF-6: EL SISTEMA valorará las obras de distribución con SICODI y las de transmisión con módulos estándar, sin mezclarlos
  en un mismo elemento.
- RF-7: CUANDO valore un tramo, EL SISTEMA cruzará código de costo, tensión, estructura y sector típico; SI no cruza,
  ENTONCES lo nombrará y no le atribuirá un costo.
- RF-8: EL SISTEMA no aplicará factores sobre los costos oficiales salvo que el estudio declare el factor y su sustento.
- RF-9: EL SISTEMA guardará de cada fuente pública la URL de Osinergmin, su fecha de descarga y su huella, y usará el VNR
  aprobado de la empresa según su propia resolución de fijación.

### Mercado y años

- RF-10: EL SISTEMA proyectará la demanda anual con el método que gane contra lo ocurrido; la tasa de 029 será la referencia
  que debe superar. La spec 046 es de corto plazo y no alcanza estos horizontes; las variables exógenas son de la 031.
- RF-11: DONDE haya entregables históricos con datos, EL SISTEMA medirá el pronóstico contra lo ocurrido, sin mirar el futuro.
- RF-12: EL SISTEMA trasladará cada caso de estudio a cada año (030) y acumulará en cada año las obras de los anteriores.

### Entregables

- RF-13: EL SISTEMA generará el informe de largo plazo con mercado, diagnóstico, alternativas, técnico-económico, plan de obras
  y los formatos F01 a F07.
- RF-14: EL SISTEMA generará el informe PIDE con alternativas, evaluación con y sin proyecto, VAN, TIR, costo anual, priorización
  y los formatos F08 a F15.
- RF-21: EL SISTEMA generará los entregables por módulos, un documento ligero por cada uno y con sus tablas y formatos del anexo,
  siguiendo su artículo paso a paso: del plan, el diagnóstico y la formulación de alternativas; del PIDE, la formulación en su
  periodo, la evaluación técnica, la económica, la priorización y selección, y la propuesta (usuario, 2026-11-02: «para que sea
  ligero los informes se haga por módulos y entregables»).
- RF-15: EL SISTEMA generará metrados desde la red de cada proyecto; sin metrado no habrá costo supuesto.
- RF-16: SI un dato del entregable falta, ENTONCES EL SISTEMA dejará el hueco nombrado, sin inventarlo.
- RF-17: EL SISTEMA tomará de un perfil de empresa todo lo propio de cada distribuidora; una fuente no alimenta a otra.

### Asistente

- RF-18: EL SISTEMA dará al asistente herramientas para ejecutar cada paso del estudio por las mismas rutas que la web, con
  plan y confirmación.
- RF-19: EL SISTEMA podrá usar los entregables de Electro Oriente para entrenar al asistente, con revisión humana, solo para
  redactar y dar formato, nunca como verdad eléctrica. Cambia 027:RF-47 por orden del usuario del 2026-11-02, a la propuesta
  «¿autorizas usar los resultados de ELOR para entrenar, con revisión humana?»: «has la 3 y 4 según lo recomendado».

### Casos de prueba

- RF-20: EL SISTEMA tratará los nombres de empresas, clientes y proyectos de ejemplos, pruebas y documentos como casos de prueba
  del conversor, no como valores por defecto (usuario, 2026-11-02: «etiqueta como de prueba del conversor»).

## Requisitos no funcionales

Universal: cualquier distribuidora y número de alimentadores. Determinismo del DGS intacto. Los datos descargados quedan fuera
de git.

## Casos límite

Una empresa sin VNR fijado en el último proceso usa el de su última resolución y lo dice. Una red con códigos sin costo
sigue con el hueco nombrado. Un año base distinto del año medido se avisa.

## Fuera de alcance

El piloto MADRL. La tensión en valle en la elección de obras es de la spec 073. No se reproduce el consultor: los entregables
históricos son referencia.

## Criterios de finalización

Cada RF con su prueba, una aceptación real de los dos entregables en una empresa, y suite completa sin omitidas.
