"""Ningún elemento con más fases que su barra, ni con fases que no le llegan (spec 081).

Es la clase entera de fallos, no un caso: acopladores trifásicos en barras monofásicas
impedían todo el flujo, y el mismo día un banco trifásico en una barra de dos fases dio «Error in
load flow data» en toda la calibración de un sistema. Cada uno se arregló por su lado.

Contrato sin DIgSILENT ni fuente: ``Elemento`` y ``Barra`` valen para el modelo común (TXT, MDB
y VNR-GIS) y para lo que el guion lea de un proyecto. No rechaza nada: dice, y lo que se puede
reconstruir se reconstruye y se anota. Lo que llega a cada nodo se calcula aquí, de solo lectura,
aunque 054:RF-9 lo corrija al construir el modelo: una guarda no reutiliza a quien vigila.
"""
from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .model import FeederModel, decode_phase

MAS_FASES = 'mas_fases'
NO_LLEGAN = 'no_llegan'
_MAX_LINEAS = 50


@dataclass(frozen=True)
class Barra:
    nombre: str
    n: int
    letras: str = ''


@dataclass(frozen=True)
class Elemento:
    clase: str                    # acoplador, banco, carga, transformador, tramo o regulador
    nombre: str
    barras: tuple[str, ...]
    n: int
    letras: str = ''


@dataclass(frozen=True)
class Hallazgo:
    tipo: str
    clase: str
    nombre: str
    barra: str
    fases_elemento: str
    fases_barra: str

    def linea(self) -> str:
        if self.tipo == MAS_FASES:
            return (f'{self.clase} {self.nombre}: {self.fases_elemento} fases en la barra {self.barra}, '
                    f'que lleva {self.fases_barra}.')
        return (f'{self.clase} {self.nombre}: fases {self.fases_elemento}; a la barra {self.barra} '
                f'le llegan {self.fases_barra or "ninguna"}.')


@dataclass
class InformeFases:
    hallazgos: list[Hallazgo] = field(default_factory=list)
    reconstruidos: list[str] = field(default_factory=list)

    @property
    def conteo(self) -> dict[str, int]:
        return dict(sorted(Counter(h.clase for h in self.hallazgos).items()))

    def as_dict(self) -> dict[str, Any]:
        return {'total': len(self.hallazgos), 'conteo': self.conteo,
                'lineas': [h.linea() for h in self.hallazgos[:_MAX_LINEAS]],
                'reconstruidos': list(self.reconstruidos)}

    def resumen(self) -> str:
        if not self.hallazgos:
            return 'fases: todos los elementos caben en sus barras.'
        por_clase = ', '.join(f'{n} {clase}' for clase, n in self.conteo.items())
        return f'fases: {len(self.hallazgos)} elemento(s) no cuadran ({por_clase}).'


def comprobar(elementos: Iterable[Elemento], barras: Mapping[str, Barra],
              llegan: Mapping[str, str] | None = None) -> InformeFases:
    """Cada elemento frente a cada barra suya (081:RF-1 a RF-3). Sin parar en ninguno (RF-4)."""
    informe = InformeFases()
    for e in elementos:
        for nombre in e.barras:
            b = barras.get(nombre)
            if b is None:
                continue
            if e.n > b.n:
                informe.hallazgos.append(Hallazgo(MAS_FASES, e.clase, e.nombre, nombre, str(e.n), str(b.n)))
                break
            if not e.letras:
                continue
            referencia = llegan[nombre] if llegan is not None and nombre in llegan else b.letras
            if referencia is not None and b.letras != '' and not set(e.letras) <= set(referencia):
                informe.hallazgos.append(Hallazgo(NO_LLEGAN, e.clase, e.nombre, nombre, e.letras, referencia))
                break
    return informe


def _letras(fase: Any) -> str:
    return decode_phase(fase) or 'ABC'           # 054:RF-5: la fuente no lo dice, trifásico


def _letras_por_nodo(model: FeederModel) -> dict[str, set[str]]:
    # Lo mismo que escribe el DGS en cada barra (054:RF-3): lo que llega a ella, sin los bancos.
    cargas = {(x.section_id, x.device_number): x for x in model.loads}
    fases: dict[str, set[str]] = {}
    for ln in model.lines:
        for n in (ln.from_node, ln.to_node):
            fases.setdefault(n, set()).update(_letras(ln.phase))
    for s in model.seds:
        fases.setdefault(s.node_id, set()).update(_letras(getattr(cargas.get(s.load_key), 'phase', 'ABC')))
    return fases


def fases_que_llegan(model: FeederModel) -> dict[str, str]:
    """Lo que llega a cada nodo desde la fuente: por cada tramo, lo que trae menos lo que él no lleva."""
    vecinos: dict[str, list[tuple[str, str]]] = {}
    for ln in model.lines:
        letras = _letras(ln.phase)
        vecinos.setdefault(ln.from_node, []).append((ln.to_node, letras))
        vecinos.setdefault(ln.to_node, []).append((ln.from_node, letras))
    llegan = {model.source_node: 'ABC'}
    cola = deque([model.source_node])
    while cola:
        n = cola.popleft()
        for otro, letras in sorted(vecinos.get(n, ())):
            if otro not in llegan:
                llegan[otro] = ''.join(f for f in llegan[n] if f in letras)
                cola.append(otro)
    return llegan


def elementos_del_modelo(model: FeederModel) -> tuple[list[Elemento], dict[str, Barra]]:
    """El modelo común en la forma del contrato (081:RF-6): la fuente ya no importa aquí."""
    por_nodo = _letras_por_nodo(model)
    barras = {n: Barra(n, len(f), ''.join(x for x in 'ABC' if x in f)) for n, f in por_nodo.items()}
    cargas = {(x.section_id, x.device_number): x for x in model.loads}
    con_sed = {s.load_key for s in model.seds}
    elementos = [Elemento('tramo', ln.section_id, (ln.from_node, ln.to_node), len(_letras(ln.phase)), _letras(ln.phase))
                 for ln in model.lines]
    for s in model.seds:
        letras = _letras(getattr(cargas.get(s.load_key), 'phase', 'ABC'))
        elementos.append(Elemento('transformador', s.code, (s.node_id,), len(letras), letras))
    for x in model.loads:
        if (x.section_id, x.device_number) not in con_sed:
            letras = _letras(x.phase)
            elementos.append(Elemento('carga', x.display_name or x.device_number, (x.node_id,), len(letras), letras))
    for b in model.capacitors:
        letras = _letras(b.phases)
        elementos.append(Elemento('banco', b.capacitor_id, (b.node_id,), len(letras), letras))
    for c in model.couplers:
        # El DGS le da las comunes de sus dos barras (054:RF-3): vigila que las haya.
        a, z = barras.get(c.node_a), barras.get(c.node_b)
        if a is not None and z is not None:
            letras = ''.join(x for x in a.letras if x in z.letras) or min(a.letras, z.letras, key=len)
            elementos.append(Elemento('acoplador', c.name, (c.node_a, c.node_b), len(letras), letras))
    return elementos, barras


def comprobar_modelo(model: FeederModel) -> InformeFases:
    """Antes de importar (081:RF-1, RF-2): lo que no cuadra, por elemento, en cualquier fuente."""
    elementos, barras = elementos_del_modelo(model)
    return comprobar(elementos, barras, fases_que_llegan(model))


def reconstruir_bancos(model: FeederModel) -> list[str]:
    """Cada banco de la fuente con las fases de su barra, y anotado (081:RF-5); no toca lo que cabe.

    El DGS deduce las fases de cada barra de sus tramos y SED, no de los bancos: un banco
    trifásico sobre un ramal de dos fases salía tal cual, y DIgSILENT no calcula nada de ese proyecto.
    """
    barras = _letras_por_nodo(model)
    lineas: list[str] = []
    for i, banco in enumerate(model.capacitors):
        propias, en_barra = _letras(banco.phases), ''.join(x for x in 'ABC' if x in barras.get(banco.node_id, ()))
        if not en_barra or set(propias) <= set(en_barra):
            continue
        comunes = ''.join(x for x in propias if x in en_barra)
        nuevas = en_barra if len(propias) >= len(en_barra) else (comunes or en_barra[:len(propias)])
        model.capacitors[i] = replace(banco, phases=nuevas)
        lineas.append(f'{model.name}: FASE_RECONSTRUIDA, banco {banco.capacitor_id} en {banco.node_id}: '
                      f'fases {propias} → {nuevas}; conserva su potencia.')
    model.warnings.extend(lineas)
    return lineas


@dataclass(frozen=True)
class Ubicacion:
    barra: str
    n: int
    reubicado: bool = False
    adaptado: bool = False
    nota: str = ''


def ubicar_nuevo(clase: str, nombre: str, n: int, pedida: Barra,
                 cercanas: Sequence[tuple[Barra, float]] = ()) -> Ubicacion:
    """Dónde va un elemento nuevo (081:RF-8, RF-9): nunca se rechaza por sus fases.

    ``cercanas`` son las otras barras de la red con su distancia. La más cercana que lleve sus
    fases; sin ninguna, en la pedida con las fases de esa barra. Lo dice siempre.
    """
    if n <= pedida.n:
        return Ubicacion(pedida.nombre, n)
    aptas = [(d, b.nombre) for b, d in cercanas if b.n >= n]
    if aptas:
        d, destino = min(aptas)
        return Ubicacion(destino, n, reubicado=True,
                         nota=f'{clase} {nombre}: {pedida.nombre} lleva {pedida.n} fase(s) y necesita {n}; '
                              f'va a {destino}, a {d:.0f} m (081:RF-8).')
    return Ubicacion(pedida.nombre, pedida.n, adaptado=True,
                     nota=f'{clase} {nombre}: ninguna barra cercana lleva {n} fases; queda en {pedida.nombre} '
                          f'con {pedida.n} (081:RF-9).')
