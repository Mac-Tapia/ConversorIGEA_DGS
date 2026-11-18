# ADR-001 · Monolito modular por capas, con puertos y adaptadores

- Estado: vigente
- Fecha: 2026-11-14
- Specs: 002:RF-1, 002:RF-2, 002:RF-3, 002:RF-4, 002:RF-7
- Elementos C4: conversor, api, engine, dgs, nativeRunner, jobs
- Tareas: 002 T6
- Evidencia: `tools/arquitectura.py::CAPAS`, `tools/arquitectura.py::BORDE_Y_DRIVERS`, `src/convertersmartgrid/puertos/__init__.py::LectorDeRed`, `src/convertersmartgrid/puertos/__init__.py::EscritorDeRed`, `src/convertersmartgrid/puertos/__init__.py::Estudio`, `pyproject.toml~[tool.convertersmartgrid.capas]`

## Contexto

El conversor corre en la máquina del operador: un proceso web local, procesos hijos para el motor y un intérprete
aparte para DIgSILENT, que solo admite un proceso con su motor. La spec 002 ya fija cinco capas (dominio, puertos,
aplicación, adaptadores y presentación) y los puertos de lectura, escritura y estudio. El Plan Maestro V1 (§30.3)
propone como hipótesis un monolito modular hexagonal y prohíbe empezar por microservicios, Kubernetes, Redis o un
bus distribuido sin un caso cuantificado.

## Decisión

Se mantiene un único paquete `convertersmartgrid` desplegado como un monolito modular. Las fronteras son de
dependencias, no de procesos: la tabla de capas de `pyproject.toml` asigna cada módulo, `tools/arquitectura.py`
prohíbe subir de capa, los ciclos y los accesos privados, y los motores y lectores entran por los puertos de
`puertos.py`. Un proceso aparte solo se justifica por un recurso (el motor de DIgSILENT, la GPU), nunca por
organización del código.

## Alternativa descartada

Microservicios por contexto (fuentes, motor, estudios, planeamiento) con un bus de eventos. Se descarta: no hay
multiusuario centralizado que lo pida, el motor es CPU pura que ya escala con procesos (spec 034, RF-16), y cada
frontera de red añade serialización, versiones y fallos parciales que el operador local no puede diagnosticar.

## Consecuencias

- Cambiar de sitio un módulo es mover un fichero y una fila de la tabla, con la prueba de capas en verde.
- La deuda de capas está a la vista en `docs/implementacion065/deuda_arquitectura.json`; una excepción retirada
  también hace fallar la prueba, así que la deuda solo baja.
- Si algún día hay multiusuario, la frontera para separar procesos ya está trazada por los puertos.

## Contratos afectados

Ninguno externo: la API REST, el CLI y el DGS no cambian. Internos: la tabla `[tool.convertersmartgrid.capas]`
de `pyproject.toml` y el registro de deuda de capas.

## Vuelta atrás

No hay nada que deshacer: es el estado actual. Separar un servicio en el futuro se haría con un ADR nuevo que
sustituya a este, con su caso medido.
