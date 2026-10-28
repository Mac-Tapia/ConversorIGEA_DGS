# Arquitectura C4 Interactiva Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear un modelo Structurizr C4 y una visualizacion local interactiva donde el flujo real del proyecto se reproduzca mediante flechas animadas.

**Architecture:** `workspace.dsl` conserva el modelo C4 y el fragmento HTML versionado conserva su representacion interactiva. Ambos se contrastan mediante pruebas de rutas, secuencias y destinos; el generador crea los entregables ignorados de `output/` desde la fuente HTML rastreada.

**Tech Stack:** Structurizr DSL, HTML, CSS, JavaScript y SVG nativos.

**Spec:** `docs/superpowers/specs/2026-10-25-arquitectura-c4-interactiva-design.md`

## Global Constraints

- No incorporar dependencias runtime ni servicios externos.
- Mantener PowerFactory fuera del proceso del motor; representarlo como proceso nativo.
- No presentar preflight, HTTP 200 o DGS valido como aceptacion nativa.
- Usar rutas y endpoints observados en el repositorio.
- Respetar `prefers-reduced-motion` y navegacion por teclado.

## Review Focus

- Navegador sin servidor en `127.0.0.1:8765`: mostrar el enlace sin afirmar disponibilidad.
- Ruta local no abrible desde navegador: copiarla, no navegarla.
- Movimiento reducido: completar pasos sin transicion animada.
- Vista estrecha: reemplazar el SVG por una lista legible.
- Fin del flujo: detener reproduccion sin bucle automatico.

---

### Task 1: Modelo Structurizr

**Files:**
- Create: `docs/architecture/workspace.dsl`

**Interfaces:**
- Consumes: modulos, endpoints y artefactos actuales del repositorio.
- Produces: vistas `SystemContext`, `Containers`, `Conversion`, `PowerFactory`, `Inteligencia` y `Deployment`.

- [x] Escribir el modelo, relaciones, estilos, URLs y vistas dinamicas.
- [x] Validar sintaxis con Structurizr consolidado en Docker.
- [x] Confirmar relaciones y enlaces contra codigo y rutas del repositorio.

### Task 2: Visualizacion interactiva

**Files:**
- Create: `docs/architecture/arquitectura-interactiva-c4.html`
- Generate: `output/arquitectura/index.html`

**Interfaces:**
- Consumes: las seis vistas y relaciones definidas en Task 1.
- Produces: controles `play`, `pause`, `next`, `reset`, `speed`, seleccion de vista y panel de detalle.

- [x] Crear el fragmento HTML y el SVG accesible.
- [x] Implementar reproduccion finita y particula de flujo por relacion.
- [x] Implementar seleccion de cajas/flechas y acceso directo/copiar.
- [x] Implementar alternativa estrecha y movimiento reducido.

### Task 3: Verificacion y entrega

**Files:**
- Verify: `docs/architecture/workspace.dsl`
- Verify: `docs/architecture/arquitectura-interactiva-c4.html`
- Generate/verify: `output/arquitectura/index.html`

**Interfaces:**
- Consumes: artefactos de Tasks 1 y 2.
- Produces: evidencia de sintaxis, interaccion, render y tamano.

- [x] Generar el standalone desde la fuente rastreada.
- [x] Probar controles, ciclo finito y seleccion mediante navegador automatizado.
- [x] Verificar layouts de escritorio y 320 px sin desbordamiento.
- [x] Verificar ausencia de errores de consola y tamano menor de 1 MB.
