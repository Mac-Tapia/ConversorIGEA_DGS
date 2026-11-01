# Spec 038 — Pertenencia de las SED en la fuente y notas de actualización

Estado: cumplida · solicitada el 2026-10-29 y verificada el 2026-10-31.

## Motivo

El libro de suministros puede conservar un radial anterior al de la fuente cargada.
Filtrar por ese radial antes de contrastar la SED omite clientes del plan correcto.
El usuario pide usar el TXT y mostrar una nota en la web. Aclara que los planos de
la distribuidora previos a la exportación están fuera del alcance y no se deben modificar.

## Requisitos

- RF-1: CUANDO una SED cruzada tiene un único alimentador propietario en la fuente cargada, EL SISTEMA usará ese propietario antes de filtrar los clientes por alimentador.
- RF-2: EL SISTEMA conservará el radial del libro y explicará en la web cada discrepancia con la fuente.
- RF-3: CUANDO una SED aparece en más de un alimentador de la fuente, EL SISTEMA la separará del cruce como asignación ambigua.
- RF-4: SI una SED no aparece en la fuente o no hay fuente cargada, ENTONCES EL SISTEMA conservará el radial del libro sin inventar un propietario.
- RF-5: EL SISTEMA aplicará la misma asignación a la tabla con máximas, a la tabla sin máximas y al plan de calibración.
- RF-6: DONDE el libro de suministros trae una nota de asignación, EL SISTEMA la mostrará con el cliente y la conservará en su exportación.
- RF-7: EL SISTEMA indicará en la nota de la web que la pertenencia se toma de la fuente exportada cargada y que los planos previos de la distribuidora quedan fuera del alcance del conversor.
- RF-8: SI un cliente del alcance del ajuste tiene una asignación ambigua en la fuente, ENTONCES EL SISTEMA rechazará el plan antes de escribir en DIgSILENT y nombrará la SED afectada.

## Fuera de alcance

- Cambiar capacidades, centrales, bancos o conexiones nativas para corregir un radial comercial.
- Sumar SED con sufijos distintos o elegir un propietario cuando hay varios.
- Modificar o regenerar los planos de la distribuidora previos a exportar TXT, MDB o VNR-GIS.
- Reemplazar las pertenencias de una reconstrucción explícita del proyecto (022:RF-63).

## Fundamento consultado en la web

La comparación de fuentes antes de dimensionar es una decisión de ingeniería de esta
spec, apoyada en el tratamiento de datos de carga y topología de estas publicaciones;
ninguna acredita las capacidades reales de las SED de esta entrega.

- Singh, U. (2010), tesis MS, *Load Estimation for Distribution Feeder Monitoring & Management*, NC State: https://repository.lib.ncsu.edu/items/a3fd70d6-6f1a-43cf-a853-bb07191b8e75
- Cao, Z. (2020), tesis doctoral, *Data Driven State Estimation in Distribution Systems*, UCLA: https://escholarship.org/uc/item/2p33m7wg
- Dalavi, F., Golshan, M. E. H., y Hatziargyriou, N. D. (2024), *A review on topology identification methods and applications in distribution networks*, Electric Power Systems Research 234, 110538: https://doi.org/10.1016/j.epsr.2024.110538

La revista figura en Scopus y SCIE en el registro bibliotecario de Forschungszentrum
Jülich: https://juser.fz-juelich.de/record/88590
