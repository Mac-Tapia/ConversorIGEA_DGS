"""Del texto interpretado al plan que se ejecuta (spec 026, RF-4, RF-6, RF-7, RF-8).

Cada dato se contrasta con lo que existe: alimentadores de la fuente cargada, proyectos
de DIgSILENT que la web conoce, sistemas de la estructura, ficheros del servidor. Un
nombre con una errata se reconoce por parecido (``in11`` → IN111); uno que no existe no
llega al plan, se dice. Si el modelo no marcó un dato pero el texto nombra uno que
existe, se toma de ahí. Cada decisión queda en el razonamiento que ve el operador.
"""
from __future__ import annotations

import difflib
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .interprete import Interpretacion, numero_de, periodo_de
from .sinteticos import SUBTIPOS_ESTUDIO, normalizar
from .tareas import TAREAS


@dataclass
class Plan:
    id: str
    texto: str
    tarea: str | None
    escribe: bool
    modo: str
    datos: dict[str, Any] = field(default_factory=dict)
    faltan: list[str] = field(default_factory=list)
    dudas: list[str] = field(default_factory=list)
    razonamiento: list[str] = field(default_factory=list)
    interpretado_por: str = ''
    confianza: float = 0.0
    alternativas: list[tuple[str, float]] = field(default_factory=list)

    @property
    def listo(self) -> bool:
        return self.tarea is not None and not self.faltan

    def publico(self) -> dict:
        return {**asdict(self), 'listo': self.listo,
                'descripcion': TAREAS[self.tarea].descripcion if self.tarea else ''}


def _clave(s: str) -> str:
    return re.sub(r'[\s_\-]+', '', normalizar(s))


def parecido(valor: str, opciones: Sequence[str], corte: float = 0.8) -> str | None:
    """La opción que es el valor (sin mayúsculas, tildes ni separadores) o se le parece."""
    por_clave = {_clave(o): o for o in opciones}
    k = _clave(valor)
    if k in por_clave:
        return por_clave[k]
    cerca = difflib.get_close_matches(k, list(por_clave), n=1, cutoff=corte)
    return por_clave[cerca[0]] if cerca else None


def _nombrados(texto: str, opciones: Sequence[str]) -> list[str]:
    """Las opciones que el texto nombra tal cual (como palabra), en el orden en que aparecen."""
    t = normalizar(texto)
    hallados = []
    for o in opciones:
        m = re.search(rf'(?<![\w]){re.escape(normalizar(o))}(?![\w])', t)
        if m:
            hallados.append((m.start(), o))
    return [o for _p, o in sorted(hallados)]


def _trozos_lista(valor: str) -> list[str]:
    return [p.strip() for p in re.split(r',|;|\s+y\s+|\s+e\s+|\s+', valor) if p.strip()]


def resolver(interp: Interpretacion, vocab: Mapping[str, Sequence[str]]) -> Plan:
    """El plan con los datos contrastados, lo que falta y por qué se decidió cada cosa."""
    plan = Plan(uuid.uuid4().hex[:12], interp.texto, interp.tarea, False, '', interpretado_por=interp.modelo,
                confianza=interp.confianza, alternativas=list(interp.alternativas))
    if interp.consultados:
        plan.razonamiento.append(f"Consulté: {', '.join(interp.consultados)}.")
    if interp.tarea is None:
        dudas = ', '.join(f'{t} ({c:.0%})' for t, c in interp.alternativas[:3])
        plan.faltan.append('la tarea: no entendí la orden con suficiente confianza'
                           + (f'; ¿quiso decir {dudas}?' if dudas else ''))
        return plan
    tarea = TAREAS[interp.tarea]
    plan.escribe, plan.modo = tarea.escribe, tarea.modo
    quien = 'el Transformer propio' if interp.modelo == 'transformer' else f'el modelo local {interp.modelo}'
    plan.razonamiento.append(f'Entendí «{tarea.descripcion}» con {quien} (confianza {interp.confianza:.0%})'
                             + (f': {interp.razon}' if interp.razon else '.'))
    for d in tarea.datos:
        valores = [x['valor'] for x in interp.datos.get(d.tipo) or []]
        valor = _resolver_dato(d.tipo, valores, interp.texto, vocab, plan)
        if valor not in (None, [], ''):
            plan.datos[d.nombre] = valor
        elif d.obligatorio:
            plan.faltan.append(f'{d.nombre}: {d.descripcion}')
    if plan.escribe:
        plan.razonamiento.append('Esta tarea escribe en DIgSILENT o en disco: espera su confirmación (RF-8).')
    return plan


def _alimentadores(valores: list[str], texto: str, opciones: list[str], plan: Plan) -> list[str]:
    crudos = [p for v in valores for p in _trozos_lista(v)]
    if any(normalizar(p) in ('todos', 'todo') for p in crudos) or (not crudos and re.search(
            r'\btodos los alimentadores\b', normalizar(texto))):
        if opciones:
            plan.razonamiento.append(f'alimentadores: «todos» → los {len(opciones)} de la fuente cargada.')
            return list(opciones)
        return ['todos']
    elegidos: list[str] = []
    for p in crudos:
        if normalizar(p) in ('los', 'alimentadores', 'alimentador'):
            continue
        o = parecido(p, opciones) if opciones else p.upper()
        if o is None:
            plan.dudas.append(f'«{p}» no es un alimentador de la fuente cargada: no entra.')
        elif o not in elegidos:
            elegidos.append(o)
    if not elegidos and opciones:
        elegidos = _nombrados(texto, opciones)
        if elegidos:
            plan.razonamiento.append(f"alimentadores: tomados del texto: {', '.join(elegidos)}.")
            return elegidos
    if elegidos:
        origen = 'de la fuente cargada' if opciones else 'sin poder comprobarlos: no hay fuente cargada'
        plan.razonamiento.append(f"alimentadores: {', '.join(valores)} → {', '.join(elegidos)} ({origen}).")
    return elegidos


def _nombre(tipo: str, valores: list[str], texto: str, opciones: list[str], plan: Plan) -> str | None:
    for v in valores:
        o = parecido(v, opciones, 0.75) if opciones else None
        if o is not None:
            plan.razonamiento.append(f'{tipo}: «{v}» → {o} (de lo que conoce la web).')
            return o
        if not opciones:
            consejo = 'lea los proyectos de DIgSILENT' if tipo == 'proyecto' else 'cargue la fuente'
            plan.dudas.append(f'{tipo} «{v}» sin comprobar: la web no conoce ninguno ({consejo}).')
            return v
        plan.dudas.append(f'«{v}» no es un {tipo} que la web conozca.')
    nombrados = _nombrados(texto, opciones)
    if nombrados:
        plan.razonamiento.append(f'{tipo}: tomado del texto: {nombrados[0]}.')
        return nombrados[0]
    if tipo == 'proyecto' and len(opciones) == 1:
        plan.razonamiento.append(f'proyecto: el único que conoce la web, {opciones[0]}.')
        return opciones[0]
    return None


def _resolver_dato(tipo: str, valores: list[str], texto: str, vocab: Mapping[str, Sequence[str]],
                   plan: Plan) -> Any:
    opciones = list(vocab.get(tipo) or [])
    if tipo == 'alimentadores':
        return _alimentadores(valores, texto, opciones, plan)
    if tipo in ('proyecto', 'sistema'):
        return _nombre(tipo, valores, texto, opciones, plan)
    if tipo == 'periodo':
        p = periodo_de(' '.join(valores)) if valores else periodo_de(texto)
        if p is None:
            return None
        conocidos = list(vocab.get('periodos') or [])
        if conocidos and not any(c.startswith(p) or p.startswith(c) for c in conocidos):
            plan.dudas.append(f'No hay libros de demanda de {p}: los hay de {", ".join(sorted(conocidos)[-6:])}.')
        plan.razonamiento.append(f'periodo: {p}.')
        return p
    if tipo == 'numero':
        return numero_de(' '.join(valores)) if valores else numero_de(texto)
    if tipo == 'ruta':
        if not valores:
            return None
        if not Path(valores[0]).exists():
            plan.dudas.append(f'La ruta {valores[0]} no existe en el servidor.')
            return None
        return valores[0]
    if tipo == 'sed':
        if valores:
            return valores[0].upper()
        m = re.search(r'\bsed\s+([A-Za-z]*\d{3,})', texto, re.IGNORECASE)
        return m.group(1).upper() if m else None
    if tipo == 'subtipo':
        lista = list(vocab.get('subtipo') or SUBTIPOS_ESTUDIO)
        for v in valores:
            o = parecido(v, lista, 0.6)
            if o:
                return o
        return next((s for s in lista if normalizar(s) in normalizar(texto)), None)
    if tipo == 'texto':
        return valores[0] if valores else texto
    return valores[0] if valores else None
