# Tareas — Spec 030

Estado: pedida por el usuario el 2026-10-28.

Plan: en `tools/pide_pf.py`, con `casos_por_anio` (la web lo pide siempre), por cada año: la carpeta
«PIDE/Año NN» en casos y en escenarios; los casos «Sin proyecto», «Cargas nuevas» y «Con proyecto»
que existan, copiados con `AddCopy` y marcados `pide_NN_<rol>`; su escenario, copia del del caso de
origen, activo, con el `scale0` de cada carga por el factor de su alimentador; el diagnóstico en el
«Sin proyecto» del año. Lo anterior del mismo nombre se borra antes (renovar).

- [x] T1. Casos y escenarios por año en `pide_pf.py` y en el plan de la web. (RF-1 a RF-8)
      Hecho cuando: prueba con `fake_pf` en verde (carpetas, tres casos, escenarios con la
      demanda del año, renovación sin duplicar, casos del proyecto intactos).
- [x] T2. PIDE de Chincha en DIgSILENT con sus carpetas por año.
      Hecho cuando: el proyecto tiene «PIDE/Año 00…20» con sus casos y escenarios.
      Hecho el 2026-10-28 en DIgSILENT (mismo PIDE de Chincha, a las 11:56, tras T1): «PIDE/Año 00»
      a «PIDE/Año 20» con su «Sin proyecto» y su escenario cada uno; el proyecto no tenía «Cargas
      nuevas» ni «Con proyecto». Cerrada el 2026-10-29 con esa evidencia.
- [x] T3. Cargas nuevas constantes, con su año de ingreso o fraccionadas por años: columnas del
      libro, plan de la web y potencia acumulada por año en los escenarios del PIDE. (RF-9 a RF-15)
      Hecho cuando: pruebas en verde (lectura de la columna, carga nueva sin escalar, fuera de
      servicio antes de su año y en servicio desde él).
