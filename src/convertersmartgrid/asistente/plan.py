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
from ..edicion import tarea_fuera_de_alcance
from .sinteticos import SUBTIPOS_ESTUDIO, normalizar
from .tareas import EFECTOS, TAREAS, requiere_confirmacion


#: 084:RF-25: los verbos de una orden de borrar. «borra la escalera de X» activaba la frase literal de la
#: escalera y lanzaba justo la obra que se quería quitar.
_PIDE_BORRAR = re.compile(r'\b(?:borr(?:a|ar|e|en|ame)|elimin(?:a|ar|e|en)|suprim(?:e|ir|a|an)|quit(?:a|ar|e|en)|'
                          r'limpi(?:a|ar|e|en))\b')


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
    #: 067:RF-9, RF-10: lo que el operador debe saber de quién interpretó la orden.
    avisos: list[str] = field(default_factory=list)
    #: 085:RF-32: con un modelo provisional, también los trabajos de solo lectura esperan al operador.
    solo_con_confirmacion: bool = False

    @property
    def listo(self) -> bool:
        return self.tarea is not None and not self.faltan

    @property
    def espera_confirmacion(self) -> bool:
        """Lo que no se lanza sin el operador: lo que escribe, lo que usa la licencia o sale a la red (086:RF-24)
        y, con un modelo provisional, todo trabajo (085:RF-31, RF-32)."""
        return (self.escribe or requiere_confirmacion(self.tarea)
                or (self.solo_con_confirmacion and self.modo != 'consulta'))

    def publico(self) -> dict:
        return {**asdict(self), 'listo': self.listo, 'espera_confirmacion': self.espera_confirmacion,
                'efectos': list(EFECTOS.get(self.tarea or '', ())),             # 086:RF-23
                'descripcion': TAREAS[self.tarea].descripcion if self.tarea else ''}


#: 078:RF-29: las tareas cuyo destino puede ser un grupo ya convertido. Sin tarea nueva: el catálogo hasta la
#: 069 entra en la huella de la prueba histórica (069:RF-13).
_IMPORTAN_GRUPO = ('flujo',)


def aviso_sin_transformer(motivo: str, modelo: str) -> str:
    """El Transformer no cargó y el operador lo lee (067:RF-9, RF-10): sin GPU se seguía con Ollama
    sin decirlo, y una orden mal entendida parecía un fallo del Transformer."""
    respondio = (f'Esta orden la interpretó {modelo}.' if modelo not in ('', 'ninguno') else
                 'Ollama tampoco la entendió o no está en marcha: no respondió ninguno, así que no se adivina.')
    return f'El Transformer de órdenes no está disponible: {motivo} {respondio}'


def _clave(s: str) -> str:
    return re.sub(r'[\s_\-]+', '', normalizar(s))


def _otro_numero(a: str, b: str) -> bool:
    """¿Los dos nombres llevan números del mismo largo y distintos? Entonces son dos entidades (047:RF-2).

    AB102 y AB101 se parecen un 80 %: «convierte AB102» daba un plan listo sobre AB101, sin una duda, cuando AB102
    era de otra fuente. Un dígito omitido sí es una errata (``ab10`` → AB101) y se sigue reconociendo.
    """
    na, nb = re.findall(r'\d+', a), re.findall(r'\d+', b)
    return len(na) == len(nb) and any(len(x) == len(y) and x != y for x, y in zip(na, nb))


def parecido(valor: str, opciones: Sequence[str], corte: float = 0.8) -> str | None:
    """La opción que es el valor (sin mayúsculas, tildes ni separadores) o se le parece."""
    por_clave = {_clave(o): o for o in opciones}
    k = _clave(valor)
    if k in por_clave:
        return por_clave[k]
    cerca = difflib.get_close_matches(k, list(por_clave), n=len(por_clave), cutoff=corte) if por_clave else []
    return next((por_clave[c] for c in cerca if not _otro_numero(k, c)), None)


def _nombrados(texto: str, opciones: Sequence[str]) -> list[str]:
    """Las opciones que el texto nombra tal cual (como palabra), en el orden en que aparecen."""
    t = normalizar(texto)
    hallados = []
    for o in opciones:
        m = re.search(rf'(?<![\w]){re.escape(normalizar(o))}(?![\w])', t)
        if m:
            hallados.append((m.start(), o))
    return [o for _p, o in sorted(hallados)]


def trozos_lista(valor: str) -> list[str]:
    return [p.strip() for p in re.split(r',|;|\s+y\s+|\s+e\s+|\s+', valor) if p.strip()]


def _patron_grupo(grupo: str) -> str:
    """El nombre de un grupo en el texto, con cualquier separador; ``SISTEMA_X`` también «sistema eléctrico x»."""
    partes = [re.escape(p) for p in re.split(r'[\s_\-]+', normalizar(grupo)) if p]
    if partes and partes[0] == 'sistema':
        partes[0] = r'sistema(?:\s+electrico)?'
    return r'(?<!\w)' + r'[\s_\-]+'.join(partes) + r'(?!\w)'


def _grupo_nombrado(valores: list[str], texto: str, grupos: Sequence[str]) -> str | None:
    """El grupo ya convertido que nombra la orden; el más largo si uno contiene a otro (078:RF-30)."""
    t = normalizar(texto)
    hallados = [g for g in grupos if re.search(_patron_grupo(g), t)]
    if hallados:
        return max(hallados, key=len)
    return next((o for v in valores if (o := parecido(v, grupos, 0.9))), None)


def _falta_convertir(texto: str, grupos: Sequence[str], opciones: Sequence[str]) -> str | None:
    """Lo que falta si la orden de importar nombra un sistema o una SET sin DGS, en vez de pedir alimentadores (078:RF-32)."""
    m = re.search(r'(?<!\w)(?:sistema|set)(?:\s+electrico)?[\s_\-]+(?!(?:de|del|la|el|los|en)\b)[\w\-]+', normalizar(texto))
    if m is None or _nombrados(texto, opciones):
        return None
    nombre = texto[m.start():m.end()]
    hay = f" Los ya convertidos: {', '.join(grupos)}." if grupos else ''
    return f'«{nombre}» aún no está convertido en este espacio: conviértalo antes de importarlo.{hay}'


def resolver(interp: Interpretacion, vocab: Mapping[str, Sequence[str]], *, grupos: Sequence[str] = ()) -> Plan:
    """El plan con los datos contrastados, lo que falta y por qué se decidió cada cosa.

    ``grupos`` son los ya convertidos del espacio, solo para lo que los importa: van aparte del
    vocabulario para no mover la huella del corpus (078:RF-35, 070:RF-72).
    """
    plan = Plan(uuid.uuid4().hex[:12], interp.texto, interp.tarea, False, '', interpretado_por=interp.modelo,
                confianza=interp.confianza, alternativas=list(interp.alternativas))
    if interp.consultados:
        plan.razonamiento.append(f"Consulté: {', '.join(interp.consultados)}.")
    if interp.tarea not in TAREAS:
        plan.tarea = None
        dudas = ', '.join(f'{t} ({c:.0%})' for t, c in interp.alternativas[:3])
        plan.faltan.append('la tarea: no entendí la orden con suficiente confianza'
                           + (f'; ¿quiso decir {dudas}?' if dudas else ''))
        return plan
    if tarea_fuera_de_alcance(interp.tarea):
        # 086:RF-16: va en las dudas y no en lo que falta: no hay dato que dar, y el plan no se puede confirmar.
        plan.tarea = None
        plan.dudas.append('Esa orden es de una función que no forma parte de esta versión del programa.')
        return plan
    tarea = TAREAS[interp.tarea]
    plan.escribe, plan.modo = tarea.escribe, tarea.modo
    if tarea.escribe and _PIDE_BORRAR.search(normalizar(interp.texto)):
        # Protege datos reales: esta sí se detiene. El asistente no tiene ninguna orden de borrar.
        plan.tarea = None
        plan.faltan.append('El asistente no borra en DIgSILENT: esa orden se da en DIgSILENT, en su proyecto '
                           '(084:RF-25).')
        return plan
    quien = ('el Transformer propio' if interp.modelo == 'transformer' else
             'la frase literal del catálogo' if interp.modelo == 'catalogo' else
             'la forma de la pregunta, que nombra un fichero o una ruta de la API (077:RF-74)' if interp.modelo == 'forma'
             else f'el modelo local {interp.modelo}')
    plan.razonamiento.append(f'Entendí «{tarea.descripcion}» con {quien} (confianza {interp.confianza:.0%})'
                             + (f': {interp.razon}' if interp.razon else '.'))
    for d in tarea.datos:
        valores = [x['valor'] for x in interp.datos.get(d.tipo) or []]
        if d.tipo == 'alimentadores' and tarea.nombre in _IMPORTAN_GRUPO:
            # 078:RF-29, RF-31: la plantilla dice «importa {alimentadores}» y la web importa un grupo por su
            # nombre, pero el contraste solo miraba la fuente: «importa <grupo>» pedía alimentadores.
            grupo = _grupo_nombrado(valores, interp.texto, grupos)
            if grupo is not None:
                plan.datos[d.nombre] = [grupo]
                plan.razonamiento.append(f'destino: {grupo}, ya convertido en este espacio; se importa su DGS.')
                continue
            falta = _falta_convertir(interp.texto, grupos, list(vocab.get(d.tipo) or []))
            if falta is not None:
                plan.faltan.append(falta)
                continue
        valor = _resolver_dato(d.tipo, valores, interp.texto, vocab, plan)
        if valor not in (None, [], ''):
            plan.datos[d.nombre] = valor
            # 047:RF-2: la SET faltaba aquí, y sin fuente «convierte la SET X» salía listo con un nombre sin comprobar.
            if plan.escribe and d.tipo in ('alimentadores', 'proyecto', 'sistema', 'set') and not vocab.get(d.tipo):
                plan.faltan.append(f'contexto vinculado de {d.tipo}: cargar o leer su fuente antes de ejecutar')
        elif d.obligatorio:
            plan.faltan.append(f'{d.nombre}: {d.descripcion}')
    if plan.escribe:
        plan.razonamiento.append('Esta tarea escribe en DIgSILENT o en disco: espera su confirmación (RF-8).')
    elif requiere_confirmacion(tarea.nombre):
        plan.razonamiento.append('Esta tarea usa la licencia de DIgSILENT o sale a la red: espera su confirmación.')
    return plan


def _alimentadores(valores: list[str], texto: str, opciones: list[str], plan: Plan) -> list[str]:
    crudos = [p for v in valores for p in trozos_lista(v)]
    if any(normalizar(p) in ('todos', 'todo', 'todos los alimentadores') for p in crudos) or (not crudos and re.search(
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
        dentro = _nombrados(v, opciones)
        if dentro:
            # 078:RF-33: el modelo marcó de más («electrico X a DGS»); X existe y no hay nada que dudar.
            plan.razonamiento.append(f'{tipo}: «{v}» → {dentro[0]} (nombrado en lo marcado).')
            return dentro[0]
        plan.dudas.append(f'«{v}» no es un {tipo} que la web conozca.')
    nombrados = _nombrados(texto, opciones)
    if nombrados:
        plan.razonamiento.append(f'{tipo}: tomado del texto: {nombrados[0]}.')
        return nombrados[0]
    if tipo == 'proyecto' and len(opciones) == 1 and not valores:
        plan.razonamiento.append(f'proyecto: el único que conoce la web, {opciones[0]}.')
        return opciones[0]
    return None


def _resolver_dato(tipo: str, valores: list[str], texto: str, vocab: Mapping[str, Sequence[str]],
                   plan: Plan) -> Any:
    opciones = list(vocab.get(tipo) or [])
    if tipo == 'alimentadores':
        return _alimentadores(valores, texto, opciones, plan)
    if tipo in ('proyecto', 'sistema', 'set'):
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
    if tipo == 'alcance':
        crudo = normalizar(' '.join(valores))
        return next((a for a in ('alimentadores', 'set', 'sistema') if a in crudo), None)
    if tipo == 'estudio':
        return valores[0] if valores else next(iter(_nombrados(texto, opciones)), None)
    if tipo == 'anio':
        p = periodo_de(' '.join(valores)) if valores else periodo_de(texto)
        return p[:4] if p else None
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
        if m:
            return m.group(1).upper()
        # 070:RF-29: una carga nueva aún no tiene SED: se la llama por su nombre («conecta MINERA de 800 kW»).
        m = re.search(r'\b(?:carga nueva|carga|cliente|conect[ae]r?)\s+(?!(?:de|del|en|la|el|una|sola|nueva|esta)\b)([\w.-]+)',
                      normalizar(texto))
        if m:
            nombre = texto[m.start(1):m.end(1)].upper()
            plan.razonamiento.append(f'carga: {nombre}, tomada del texto.')
            return nombre
        return None
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
