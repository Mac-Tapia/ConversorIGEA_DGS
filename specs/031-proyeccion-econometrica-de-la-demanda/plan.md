# Plan 031 — Proyección para todos los años del PIDE

## Dónde

- `src/convertersmartgrid/adaptadores/proyeccion_anual.py`, nuevo: competición, métricas, elección, emisión y evaluación (RF-2 a RF-9, RF-12 a RF-14). Reutiliza `pronostico_demanda` (dataset, objetivos, métricas, modelos) y `proyeccion_mercado` (métodos anuales y errores contra lo ocurrido), sin duplicarlos.
- `tools/proyeccion_anual.py`, nueva: la orden, con su `--help` y el manual.
- `src/convertersmartgrid/presentacion/web/services.py` y `web/app.py`: el PIDE pronostica primero y pasa la referencia con huella al plan (RF-1); las obras leen la proyección aceptada (RF-11).
- `tools/reentrenar_modelos.py` y `aprendizaje_continuo.py`: N-HiTS, TFT y PatchTST compiten dentro de la etapa `gru` del ciclo común (RF-2, RF-10).

- `proyeccion_anual.py`, sección de exógenas anuales (RF-19 a RF-23): `leer_exogenas_anuales` (CSV, JSON y los libros del lector común, todas las hojas), `exogenas_al_corte` (as-of), `metodo_exogeno` y su paso por `competir`, `medir_formato_01`, `proyectar` y `pronosticar_estudio`. Pruebas en `tests/test_proyeccion_anual_exogenas.py`.

## Decisiones

- La proyección es una capa aparte de la 089: extrapolar en silencio una curva de 28 días a años es lo que 072 prohíbe. Descartado.
- La regla de elección se escribe en la evaluación antes de medir (RF-4).
- La aceptación por orden del operador queda escrita y no oculta el horizonte sin validar (RF-6, RF-7).

- PBI y población (RF-21): elasticidad de la demanda por habitante al PBI por habitante, Δln(D/N) = ε·Δln(PBI/N), con un solo parámetro estimado por mínimos cuadrados sin término independiente y dos cambios de año como mínimo; la población entra con elasticidad 1. Descartado: dos elasticidades libres (PBI y población), porque con 3 a 15 años las dos series casi colineales no se identifican. La ablación es el mismo método con ε = 0 (solo población).
- As-of (RF-20): el corte de un origen mensual es el último día de su mes; el del Formato 01, el 31 de diciembre del año de corte; el de la emisión, el último día del último mes medido, salvo que se pida otro. Una proyección publicada (escenario) antes del corte vale: es lo que se sabía. Una variación porcentual se encadena al nivel anterior ya resuelto; sin él, el año falta.
- Años que faltan en la emisión (RF-22): el ganador exógeno emite hasta el último año con cifras publicadas y lo validado se recorta ahí; después sigue la tasa de largo plazo (RF-16). Si falta el primer año, no se emite con otro método en su nombre: se dice qué falta.
- Horizonte largo (RF-27 a RF-29, 2026-11-20): la memoria de las redes crece con el horizonte en su unidad, no con los lotes. Contados sus parámetros en el dispositivo «meta» (sin memoria real; `D:/csg/PM_IMPL/MEJ16_HORIZONTE/parametros_por_resolucion.jsonl`), con 28 días de contexto: a 15 minutos y un año, TiDE 22,69 GiB, PatchTST 24,37, N-HiTS 4,37, NBEATSx 53,28 (red y Adam); a 15 minutos y 31 días, 1,97, 1,91, 0,70 y 1,51; horaria a un año, TiDE 5,39 y NBEATSx 4,23, que con las activaciones no caben en 8 GiB; diaria a un año (396 días) con 364 de contexto, 0,26, 0,04, 0,10 y 0,14. Las ventanas, con `bytes_ventanas_entrenamiento`: 32 series a 15 minutos y un año piden 23,06 GiB; a 31 días, 3,46 GiB (cabe en la mitad de 7,5 libres); en la diaria, las 650 series del grupo más grande, 3,24 GiB. Por eso: 15 minutos hasta 31 días y la serie diaria por encima. Descartado: la horaria (no cabe) y la energía o la máxima mensual directas (12 puntos por año dan muy pocas ventanas por serie para entrenar una red, y se perdería el día no laborable). La forma de 15 minutos sale del perfil anclado del propio objetivo (el mismo que ya usa el resto de la 089), estirado cada día para respetar la media y la máxima predichas.
- Unidades (RF-22): el PBI en niveles exige el año base de sus precios constantes; nominal se rechaza, porque la inflación no es crecimiento de la demanda; las escalas «miles» y «millones» se convierten; dos años base en la misma serie no se empalman.

## Pruebas

Sintéticas sorteadas: series con tendencia conocida; gana quien debe y, sin mejora, la referencia; `leer_proyeccion_anual` acepta el resultado; ninguna fila negativa; determinismo; el horizonte validado no se infla.
