---
name: igea-dgs-spec
description: >-
  Desarrollo guiado por especificaciones (SDD) en el conversor IGEA-DGS. Usar cuando se
  pida crear, revisar o cambiar una spec, un plan o unas tareas en specs/, al empezar
  una funcionalidad o una reorganización que no sea un arreglo de una línea, y al
  validar si una spec está cumplida (requisito RF por requisito RF).
---

# IGEA-DGS Spec (SDD)

Adaptado de `spec-generator` de [mouredev/hello-sdd](https://github.com/mouredev/hello-sdd)
(Apache-2.0), con las fases de plan, tareas y validación y las reglas de este proyecto.

La spec es el contrato: lo que no está en ella no se implementa. Existe porque las
specs de `docs/superpowers/specs/` se escribían y luego se separaban del código: sin
requisitos numerados, ninguna prueba las citaba y ninguna casilla de sus planes llegó a
marcarse (diagnóstico del 2026-10-07).

## Dónde vive cada cosa

```
docs/constitution.md            principios innegociables (léalos siempre primero)
specs/NNN-<nombre-kebab>/
  spec.md                       QUÉ y POR QUÉ, requisitos RF-n en EARS
  plan.md                       CÓMO: módulos, decisiones, pruebas; qué RF cubre cada parte
  tasks.md                      T1…Tn con casillas, RF y «Hecho cuando:»
```

Plantillas en este directorio: `spec-template.md`, `plan-template.md`, `tasks-template.md`.
`NNN` es el siguiente número libre de `specs/`, con tres dígitos.

## Flujo (cada fase espera aprobación explícita antes de la siguiente)

1. **Constitución.** Lea `docs/constitution.md` y las specs previas de `specs/`.
2. **Spec (entrevista).** Sin código. Preguntas de **una en una**, máximo 6, solo las que
   cambien lo que hay que construir: casos límite, errores, alcance. Luego `spec.md`.
3. **Clarificación.** Revise la spec como QA y liste, sin resolver: ambigüedades,
   contradicciones, casos límite ausentes y conflictos con la constitución.
4. **Plan.** `plan.md`: módulos y ficheros reales del repositorio, decisiones con la
   alternativa descartada, estrategia de pruebas (sintéticas sorteadas, las dos
   disposiciones, datos reales si toca el lector). Cada parte dice qué RF cubre.
5. **Tareas.** `tasks.md`: tareas cortas ordenadas por dependencia, cada una con sus RF
   y un «Hecho cuando:» verificable (normalmente, un comando de pytest en verde).
6. **Implementación.** Una tarea cada vez, pruebas primero. Al terminarla: suite en verde,
   marque `- [x]` y **pare**.
7. **Validación.** Recorra la spec RF por RF: qué prueba lo cita y su resultado. Veredicto:
   ¿spec cumplida? Un RF sin prueba es un RF no cumplido.
8. **Cambio.** Un requisito nuevo entra primero en `spec.md` (muestre el diff), después
   en el plan y las tareas, y solo entonces en el código.

## Trazabilidad: las pruebas citan el requisito

Cada prueba que verifica un requisito lo cita en su docstring con la forma
`NNN:RF-n`, para poder buscarlo:

```python
def test_cli_carga_paquete_vnr(tmp_path):
    """001:RF-4 — el CLI acepta un paquete VNR-GIS igual que la web."""
```

Validación rápida de una spec:

```bash
grep -rnoE "001:RF-[0-9]+" tests | sort -u
```

## Reglas de redacción

- La spec dice **QUÉ** y **POR QUÉ**. Stack, ficheros, firmas y algoritmos van en el plan.
  Excepción de este proyecto: en una spec de reorganización, los módulos afectados *son*
  el qué, y se pueden nombrar.
- Un requisito, una frase. Si hace falta un «y» para unir dos comportamientos, son dos.
- Sin adjetivos no medibles («rápido», «robusto»): escriba el umbral o no lo escriba.
- «Fuera de alcance» siempre: es lo que impide que la funcionalidad crezca sola.
- Lo que no se sepa se marca `[NECESITA ACLARACIÓN: pregunta concreta]`. Un hueco visible
  es información; una suposición callada es deuda.
- Nunca un número fijo de alimentadores: «todos los alimentadores de la entrega», no «los 96».
- Español, como el resto del proyecto.

## Notación EARS

| Patrón | Forma | Cuándo |
| --- | --- | --- |
| Ubicuo | EL SISTEMA \<hará\> | siempre cierto |
| Por evento | CUANDO \<disparador\>, EL SISTEMA \<hará\> | responde a algo |
| Estado | MIENTRAS \<estado\>, EL SISTEMA \<hará\> | durante una condición |
| Opcional | DONDE \<característica\>, EL SISTEMA \<hará\> | solo si está presente |
| No deseado | SI \<condición\>, ENTONCES EL SISTEMA \<hará\> | errores y casos límite |

Bien escrito:

> RF-3: SI el CRS de origen no se puede construir, ENTONCES EL SISTEMA rechazará la
> plantilla con un error que nombre el CRS, en vez de dejar las coordenadas vacías.

Mal escrito: ~~«El sistema debe manejar bien las coordenadas y ser rápido.»~~ Sin patrón,
sin criterio verificable, dos ideas y un adjetivo no medible.

## Al revisar una spec existente

No la reescriba: liste, numerado, en cuatro bloques — (1) ambigüedades, (2)
contradicciones, (3) casos límite sin cubrir, (4) conflictos con la constitución. No
proponga soluciones hasta que se las pidan.
