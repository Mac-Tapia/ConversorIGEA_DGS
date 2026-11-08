# Plan — Spec 042

Estado: aprobado (2026-10-31)

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| Diseño y ubicación, sin DIgSILENT: potencia de diseño con la tasa de la 029 ponderada por la demanda trasladada, módulos PIT leídos del libro CAPEX con la configuración del perfil y el menor que cubre, centro de carga esperado con sorteos de crecimiento por zona (Weiszfeld sobre Σ P·d), ramas que pasan a la SET nueva | `src/convertersmartgrid/set_nueva.py` (nuevo) | RF-5, RF-7 a RF-9 |
| Perfil: `planificacion.factor_seguridad_set` (1,25) y `planificacion.modulos_pit` (hoja `PyOTx27`, columnas, moneda, escala) | `config/perfiles/electro_dunas.json`, `src/convertersmartgrid/perfil_empresa.py` | RF-7, RF-8 |
| Carga a carga: orden de mayor a menor potencia y búsqueda de cuántas caben con la escalera de la 025, apartando las demás (025:RF-69 por carga) | `src/convertersmartgrid/web/services.py` (`optimizar_con_proyecto`), `tools/obras_pf.py` (`cargas_apartadas` en el plan de la escalera) | RF-1 a RF-4 |
| Obra «SET nueva»: red externa, barra de alta, transformador del módulo, barra de media, una línea por rama hasta su punto de corte y el tramo de corte abierto, en variaciones propias de «Con proyecto»; comprobación de tensiones y acercamiento a las barras que caen | `tools/obras_pf.py` (`construir_set_nueva`), `src/convertersmartgrid/obras_pf.py` (tipo de obra) | RF-6, RF-10, RF-11 |
| Informe por carga y de la SET; botón en el paso de obras | `src/convertersmartgrid/web/services.py`, `src/convertersmartgrid/web/app.py`, `frontend/src/components/EstudiosPF.tsx` | RF-12, RF-13 |
| Sección de un circuito y terna con el conductor del perfil (2026-11-07): `secciones_aptas`, `tipos_de_terna`, `obra_terna` y `doble_con_seccion` en la escalera; la misma terna en la búsqueda del oráculo (`Espacio.de_terna`) y su impedancia con `cambia_tipo`; la obra `terna` con `tipo` y `tipo_cable` opcionales, y la simulación y el guion que cambian el conductor antes de sumar la terna | `src/convertersmartgrid/escalera_optima.py`, `src/convertersmartgrid/optimizacion_oraculo.py`, `src/convertersmartgrid/obras_pf.py`, `tools/obras_pf.py`, `src/convertersmartgrid/web/services.py` | RF-97 a RF-104 |
| `escalera.alternativas` (3 a 6) y `escalera.conductor_terna` en el perfil, el esquema y la guía | `src/convertersmartgrid/escalera_optima.py` (`parametros`), `src/convertersmartgrid/perfil_esquema.py`, `config/perfiles/`, `docs/PERFIL_EMPRESA.md` | RF-105, RF-106 |

Decisiones:

- Cuántas cargas caben se busca por **bisección** sobre la lista ordenada (las k primeras), no
  probando k = 1, 2, 3…: cada prueba es una escalera entera (minutos en DIgSILENT), y con más carga
  nunca es más fácil cumplir. Con 37 cargas son unas 6 escaleras en vez de 37. El resultado es el
  mismo que añadirlas una a una mientras cumpla (RF-1 a RF-3).
- La ubicación es el punto de Weber (mínimo de Σ P·d) por el método de Weiszfeld, promediado sobre
  los sorteos de crecimiento: en cada sorteo, la demanda futura de cada celda de la malla crece con
  probabilidad proporcional a la potencia nueva del bloque en ella. Descartado el simple centro de
  gravedad (Σ P·x / Σ P): minimiza Σ P·d², que premia acercarse a una sola carga grande.
- La SET nueva es una red externa en su barra de alta (usuario): no se modela la línea de 60 kV.
- Las ramas que pasan son, en cada alimentador, el menor subárbol que contiene a las cargas de
  RF-3 sin incluir la cabecera; se corta en el tramo que lo une a lo que se queda (`troncal.aguas_abajo`).
- RF-98: el conductor de la terna es un código del perfil, no un tipo fijo (P13); la escalera busca en la
  biblioteca leída el de ese código, el de la tensión más cercana, y la simulación lo copia a la del
  alimentador. Quién cambia lo decide la simulación con los tipos de DIgSILENT (la misma regla que la
  escalera usa con `inom_a`); `cambia_tipo` de la obra es solo lo que mide el oráculo. Descartado que la
  escalera mande la lista de tramos que cambian: una terna escrita a mano no la tendría.
- RF-102: con el conductor de la terna, sección más terna en el mismo tramo es redundante (≤ 120) o el
  doble circuito de 240 que el usuario no admite; se quitan esas variantes en vez de rehacerlas.

Pruebas: `tests/test_set_nueva.py` con redes y cargas sorteadas (`CSG_SCALE_SEED`); el libro de
módulos sintético con `openpyxl`; la obra con el doble `tests/fake_pf.py`; NA203 + NA205 en
DIgSILENT desde la web.

### Aclaración universal U02 — 2026-11-08

El usuario confirmó que empresas, alimentadores y rutas de ejemplos son muestras. RF-39/RF-50 se aplican con capacidades y par de tensiones elegidos, nunca con valores físicos suplentes de las muestras. Ausencia: omitir solo la alternativa no respaldada con aviso; valor explícito inválido: rechazar antes de operar. Se conservan otros cálculos, costos, tasas y criterios. Pruebas puras y de servicio en tests/test_universalidad_obras.py; registro081 docs/regresiones/2026-11-08-obras-sin-capacidades-de-muestra.md. La validación de dominio nativo sigue separada; no se cierran tareas por estos unitarios.
