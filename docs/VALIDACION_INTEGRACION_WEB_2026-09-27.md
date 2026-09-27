# Validación de integración web — 2026-09-27

## Resultado

La interfaz única React 19 + FastAPI está implementada y su recorrido automatizado
cubre Entrada, Opciones, Alimentadores, Resultados, Cargas de SED, SED nuevas,
Catálogo, Sistema completo, JobBar y Registro. La tabla de cargas muestra `Name`,
`Grid` y `Alimentador` por separado; la pertenencia no se deduce del nombre compuesto
de la Grid.

La aceptación con datos reales de `NA203`, `NA205`, `PE104` y `CA101` **no se ejecutó**:
en `referencia/` solo existe `NA205.dgs` (354.386 bytes, SHA-256
`1545b0f6fe32ca5ce91c6cae7218741c3fac7ce19cedf87168b68ea70325056f`). No existe
una tripleta TXT RED/CARGA/BD_Equipo ni una base MDB con la cual regenerar y comparar
los cuatro alimentadores. El reporte deja las cuatro filas como
`SKIP_MISSING_INPUT`; PowerFactory queda `NOT_RUN_POWERFACTORY`. Ninguno equivale a
`PASS`.

La extensión `powerfactory.pyd` de PowerFactory 2024 sí existe en esta máquina, pero
no había un proceso PowerFactory activo ni DGS nuevos generados desde las entradas
fuente. Se repitió el verificador con `--powerfactory`; mantuvo correctamente
`NOT_RUN_POWERFACTORY` porque no existía ningún artefacto regenerado que importar.

## Evidencia reproducible

```bat
python tools\verify_reference_feeders.py ^
  --reference-root referencia ^
  --output output\validation ^
  --feeders NA203 NA205 PE104 CA101
```

Resultado observado:

```text
Reference validation: SKIP_MISSING_INPUT
NA203  SKIP_MISSING_INPUT  NOT_RUN_POWERFACTORY
NA205  SKIP_MISSING_INPUT  NOT_RUN_POWERFACTORY
PE104  SKIP_MISSING_INPUT  NOT_RUN_POWERFACTORY
CA101  SKIP_MISSING_INPUT  NOT_RUN_POWERFACTORY
```

Artefactos locales (no versionados porque `output/` es generado):

- `output/validation/reference_feeders_validation.json`;
- `output/validation/reference_feeders_validation.md`.

El JSON enumera por alimentador las compuertas `input`, `conversion`, `mapping`,
`grid_scale`, `trafomix`, `switches`, `sed` y `powerfactory`. Cuando aparezca una
exportación completa, el mismo comando regenera cada DGS y exige:

- validación y completitud sin errores;
- correspondencia exacta entre filas `ElmLod`/`ElmSym`/`ElmXnet` y metadata
  `Name → Alimentador` ligada al SHA-256 del DGS;
- Grid adaptativa próxima a 2,08 unidades de diagrama por metro;
- cero Trafomix `M…` modelados como SED;
- reconciliación de interruptores de entrada, `StaSwitch` y puentes;
- una `ElmSubstat` y una `ElmTr2` por cada SED conservada;
- aceptación propietaria solo si se solicita `--powerfactory` y realmente termina.

## Puertas locales ejecutadas

- Python 3.12.10.
- Suite Python final: 585 pasaron, 122 omitidas y una advertencia upstream de
  compatibilidad Starlette/httpx.
- Vitest: 5 pruebas pasaron.
- TypeScript y Vite: compilación correcta, 40 módulos.
- Playwright sobre Edge: 1 recorrido integral pasó.
- Auditoría npm de dependencias de producción: 0 vulnerabilidades.
- Node.js 24.15.0 y npm 11.12.1.
- El comando retirado `python -m igea_dgs.cli gui` termina con código 2 y enumera
  solamente `list`, `convert` y `web`.

## Fundamento técnico

La separación por alimentador y la ejecución paralela sin estado mutable compartido
siguen el enfoque de descomposición de modelos eléctricos de gran escala descrito en
la [tesis doctoral de la Université de Liège](https://orbi.uliege.be/handle/2268/183353)
y la evaluación multinúcleo del artículo indexado
[Parallel computing of power flow for complex distribution network with DGs](https://doi.org/10.3233/JIFS-169350).
La escala y legibilidad del unifilar se apoyan en la
[tesis de maestría sobre visualización de redes eléctricas](https://repositorio.comillas.edu/jspui/handle/11531/99738)
y en el artículo indexado sobre
[layout automático de diagramas unifilares](https://doi.org/10.1016/j.epsr.2003.12.005).

## Pendiente para aceptación real

1. Colocar una exportación TXT completa o una MDB única bajo `referencia/` (los datos
   reales permanecen ignorados por Git).
2. Repetir el comando y exigir `PASS` en las siete compuertas no propietarias por cada
   alimentador.
3. Ejecutar con `--powerfactory`, guardar JSON/TXT y capturas de General Load,
   Synchronous Machine y External Grid mostrando `Alimentador` junto a `Grid`.
4. No declarar verificados PE104, CA101 ni la Grid NA203–NA205 hasta completar esos
   pasos con los archivos reales.
