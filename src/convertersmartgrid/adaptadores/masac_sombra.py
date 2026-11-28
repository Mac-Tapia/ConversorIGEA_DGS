"""Registro de experiencia y modo sombra del agente MASAC (spec 114, T4).

Mientras un módulo del agente no pase sus puertas, el agente no actúa: propone junto a la regla que usa hoy el
conversor (la escalera de la 074), no aplica nada y se mide quién acierta (114:RF-7). Cada decisión queda registrada con
lo que vio, lo que eligió, su recompensa y quién la confirmó, para el siguiente entrenamiento (114:RF-11); una que el
operador deshace vuelve al entorno como castigo (114:RF-10).

Nunca pisa trabajo del operador: los elementos que él cambió no se ofrecen, la propuesta se calcula sobre una copia y
solo se escribe en DIgSILENT en una variación, en un proyecto de prueba o con su confirmación (114:RF-9).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .madrl_obras import EntornoObras, control_escalera, control_nsga2_sistema, zonas_por_alimentador
from .madrl_puerta import PREFIJO_PRUEBA, huella_grafo
from .masac_entorno import EntornoAgente, ParametrosAgente
from .masac_politica import MASAC

#: Quién puede confirmar o deshacer: el operador, o DIgSILENT al confirmar la propuesta final.
QUIENES = ('operador', 'digsilent')


class SombraError(ValueError):
    """Una escritura o un registro que el agente no puede hacer."""


class RegistroExperiencia:
    """Las decisiones del agente en un JSONL: solo se añade, nunca se reescribe (114:RF-11).

    Una confirmación o una deshecha es una línea nueva que apunta a su decisión; leer las junta. Reescribir el fichero
    para cambiar un estado perdería lo registrado si dos procesos escriben a la vez.
    """

    NOMBRE = 'experiencia.jsonl'

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self.ruta = self.carpeta / self.NOMBRE

    def _anadir(self, fila: Mapping[str, Any]) -> None:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        with self.ruta.open('a', encoding='utf-8') as f:
            f.write(json.dumps(fila, ensure_ascii=False, default=_a_json) + '\n')

    def registrar(self, *, modulo: str, agente: str, observacion: Any, accion: Mapping[str, Any], recompensa: float,
                  explicacion: str, alternativas: Iterable[Mapping[str, Any]] = (), modo: str = 'sombra',
                  propuesta: str = '', contexto: Mapping[str, Any] | None = None) -> str:
        ident = uuid.uuid4().hex
        self._anadir({'evento': 'decision', 'id': ident, 'fecha': _ahora(), **dict(contexto or {}),
                      'modulo': modulo, 'agente': agente,
                      'observacion': observacion, 'accion': dict(accion), 'recompensa': float(recompensa),
                      'explicacion': explicacion, 'alternativas': list(alternativas), 'modo': modo,
                      'propuesta': propuesta, 'aplicada': False})
        return ident

    def registrar_sombra(self, resumen: Mapping[str, Any]) -> None:
        """La comparación de una propuesta con la regla actual: con ella se mide quién acierta (114:RF-7)."""
        self._anadir({'evento': 'sombra', 'fecha': _ahora(), **resumen})

    def _cambiar(self, ident: str, evento: str, quien: str) -> None:
        if quien not in QUIENES:
            raise SombraError(f'Solo confirma o deshace el operador o DIgSILENT, no {quien!r}.')
        if ident not in {d['id'] for d in self.decisiones()}:
            raise SombraError(f'No hay ninguna decisión {ident!r} en el registro.')
        self._anadir({'evento': evento, 'id': ident, 'quien': quien, 'fecha': _ahora()})

    def confirmar(self, ident: str, quien: str) -> None:
        self._cambiar(ident, 'confirmacion', quien)

    def deshacer(self, ident: str, quien: str = 'operador') -> None:
        self._cambiar(ident, 'deshecha', quien)

    def filas(self) -> list[dict[str, Any]]:
        if not self.ruta.is_file():
            return []
        return [json.loads(x) for x in self.ruta.read_text(encoding='utf-8').splitlines() if x.strip()]

    def decisiones(self) -> list[dict[str, Any]]:
        """Cada decisión con su estado y quién la confirmó o deshizo: la experiencia del siguiente entrenamiento."""
        filas = self.filas()
        por_id = {f['id']: {**f, 'estado': 'propuesta', 'confirmo': None}
                  for f in filas if f.get('evento') == 'decision'}
        for f in filas:
            d = por_id.get(f.get('id'))
            if d is None:
                continue
            if f['evento'] == 'confirmacion':
                d['estado'], d['confirmo'] = 'confirmada', f['quien']
            elif f['evento'] == 'deshecha':
                d['estado'], d['confirmo'] = 'deshecha', f['quien']
        return list(por_id.values())

    def deshechas(self) -> set[tuple[str, str, str]]:
        """Lo que el operador deshizo, para castigarlo en el entorno (114:RF-10)."""
        return {(d['agente'], d['accion']['tipo'], d['accion']['elemento'])
                for d in self.decisiones() if d['estado'] == 'deshecha'}

    def aciertos(self, **filtro: Any) -> dict[str, int]:
        """Cuántas veces acertó el agente, la regla actual o ninguno más que el otro (114:RF-7).

        ``filtro`` (por ejemplo ``proyecto=``) limita a las propuestas con ese contexto.
        """
        cuenta = {'agente': 0, 'regla': 0, 'empate': 0}
        for f in self.filas():
            if f.get('evento') == 'sombra' and all(f.get(k) == v for k, v in filtro.items()):
                cuenta[f['acierta']] += 1
        return cuenta

    def propuestas(self, **filtro: Any) -> list[dict[str, Any]]:
        """Cada propuesta en sombra con sus decisiones y su estado, de la más reciente a la más antigua."""
        decisiones: dict[str, list[dict[str, Any]]] = {}
        for d in self.decisiones():
            decisiones.setdefault(d.get('propuesta') or '', []).append(d)
        salida = [{**f, 'decisiones': decisiones.get(f.get('propuesta'), [])} for f in self.filas()
                  if f.get('evento') == 'sombra' and all(f.get(k) == v for k, v in filtro.items())]
        return salida[::-1]

    def decision(self, ident: str) -> dict[str, Any]:
        d = next((d for d in self.decisiones() if d['id'] == ident), None)
        if d is None:
            raise SombraError(f'No hay ninguna decisión {ident!r} en el registro.')
        return d


def _num(x: float) -> str:
    # Con el punto decimal de la web (es-PE), que muestra esta explicación junto a sus propias cifras.
    return f'{x:.2f}'


def _ahora() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _a_json(x: Any) -> Any:
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, np.generic):
        return x.item()
    raise TypeError(f'no se puede registrar {type(x).__name__}')


def modo_del_modulo(modulo: str, puertas: Mapping[str, bool] | None) -> str:
    """«sombra» mientras el módulo no pase sus puertas; las puertas las decide la T5 frente a NSGA-II (114:RF-7)."""
    return 'actua' if (puertas or {}).get(modulo) is True else 'sombra'


def exigir_destino(proyecto: str, *, variacion: bool = False, confirmado_por_operador: bool = False) -> str:
    """Dónde puede escribir el agente en DIgSILENT: una variación, un proyecto de prueba o uno real confirmado (114:RF-9)."""
    proyecto = str(proyecto or '').strip()
    if not proyecto:
        raise SombraError('Falta el proyecto de DIgSILENT.')
    if variacion or proyecto.startswith(PREFIJO_PRUEBA) or confirmado_por_operador:
        return proyecto
    raise SombraError(f'El agente no escribe en {proyecto!r}: solo en una variación, en un proyecto de prueba '
                      f'(«{PREFIJO_PRUEBA}…») o con la confirmación del operador.')


def clave_de_acierto(r: Mapping[str, Any]) -> tuple[int, float, float]:
    """En norma en máxima y en valle primero; luego menos costo; a igual costo, menos pérdidas (114:RF-19)."""
    costo = float(r.get('costo') or 0.0) + float(r.get('costo_maniobras') or 0.0)
    return (0 if r.get('en_norma') else 1, round(costo, 6), float(r.get('perdidas_mw') or 0.0))


def quien_acierta(agente: Mapping[str, Any], regla: Mapping[str, Any]) -> str:
    a, b = clave_de_acierto(agente), clave_de_acierto(regla)
    return 'agente' if a < b else 'regla' if b < a else 'empate'


def describir(accion: Mapping[str, Any]) -> str:
    """La acción con las palabras del operador."""
    tipo, elemento = accion.get('tipo'), accion.get('elemento')
    if tipo == 'banco':
        return f'un banco de condensadores en {elemento}'
    if tipo == 'terna':
        return f'una terna en paralelo en {elemento}'
    if tipo in ('toma+', 'toma-'):
        return f'{"subir" if tipo == "toma+" else "bajar"} una posición la toma de {elemento}'
    if tipo in ('consigna+', 'consigna-'):
        return f'{"subir" if tipo == "consigna+" else "bajar"} la tensión de consigna de {elemento}'
    if tipo == 'transferencia':
        cerrar, abrir = str(elemento).split('|')
        return f'transferir carga cerrando {cerrar} y abriendo {abrir}'
    return 'no hacer nada'


def medir_obras(entorno: EntornoAgente, base: EntornoObras, r: Mapping[str, Any]) -> dict[str, Any]:
    """Lo que dejó un control de la 074 (escalera, NSGA-II o su PPO) medido con la medida del agente, máxima y valle."""
    bancos: dict[str, float] = {}
    for a, hechas in base.hechas.items():
        for i in hechas:
            x = base.acciones[a][i]
            if x.tipo == 'banco':
                bancos[x.elemento] = bancos.get(x.elemento, 0.0) + entorno.p.obras.banco_mvar
    e = entorno.medir(base.grafo, bancos)
    return {'control': r['control'], 'en_norma': e.en_norma, 'en_norma_maxima': e.maxima.en_norma,
            'en_norma_valle': None if e.valle is None else e.valle.en_norma, 'costo': r['costo'], 'costo_maniobras': 0.0,
            'vm_min': e.maxima.vm_min, 'perdidas_mw': e.perdidas_mw, 'obras': r['obras']}


def _regla_actual(entorno: EntornoAgente, regla: str) -> dict[str, Any]:
    """La regla de hoy (la escalera o NSGA-II de la 074) sobre una copia de la red."""
    base = EntornoObras(entorno.original, zonas_por_alimentador(entorno.original), entorno.p.obras)
    r = control_escalera(base) if regla == 'escalera' else control_nsga2_sistema(base)
    return {**medir_obras(entorno, base, r), 'control': regla}


def proponer_en_sombra(grafo: Mapping[str, Any], p: ParametrosAgente, politica: MASAC, *, registro: RegistroExperiencia | None = None,
                       modulo: str = 'obras', regla: str = 'escalera', puertas: Mapping[str, bool] | None = None,
                       estructura: Any = None, evaluador: Any = None, protegidos: Iterable[str] = (),
                       contexto: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Lo que propone el agente junto a la regla actual, sin aplicar nada, con la explicación de cada decisión.

    La red de entrada no cambia: si su huella cambiara, la propuesta no vale (114:RF-9). Las acciones que el operador ya
    deshizo, leídas del registro, cuestan caro en el entorno (114:RF-10).
    """
    huella = huella_grafo(grafo)
    deshechas = registro.deshechas() if registro else set()
    entorno = EntornoAgente(grafo, p, estructura=estructura, evaluador=evaluador, protegidos=protegidos, deshechas=deshechas)
    obs, _info = entorno.reset()
    if entorno.dimensiones() != politica.dims:
        raise SombraError(f'La política se entrenó con otros huecos de acción {politica.dims} que los de esta red '
                          f'{entorno.dimensiones()}: use los mismos parámetros del entrenamiento.')
    ident = uuid.uuid4().hex
    decisiones: list[dict[str, Any]] = []
    while entorno.agents:
        estado = entorno.state()
        acciones = {}
        por_que = {}
        for a in entorno.agents:
            nivel = entorno.estructura[a].nivel
            o, m = obs[a]['observation'], obs[a]['action_mask']
            acciones[a] = politica.actuar(nivel, o, m, deterministico=True)
            por_que[a] = politica.explicar(nivel, o, m, estado)
        huecos = {a: entorno.huecos[a] for a in acciones}
        vistas = {a: {'observation': obs[a]['observation'], 'action_mask': obs[a]['action_mask']} for a in acciones}
        obs, recompensas, *_ = entorno.step(acciones)
        hechas = entorno.historial[-1]['acciones']
        for a, i in acciones.items():
            if i == 0 or a not in hechas:
                continue
            tipo, elemento = hechas[a]
            accion = {'indice': i, 'tipo': tipo, 'elemento': elemento}
            alternativas = [{**f, 'descripcion': describir(_hueco(huecos[a], f['accion']))} for f in por_que[a][:3]]
            elegida = next((f for f in por_que[a] if f['accion'] == i), {'probabilidad': 0.0, 'valor': 0.0})
            otra = next((f for f in alternativas if f['accion'] != i), None)
            texto = (f'Propone {describir(accion)}: probabilidad {_num(elegida["probabilidad"])} y valor del crítico '
                     f'{_num(elegida["valor"])}' + (f'; la siguiente era {otra["descripcion"]} ({_num(otra["valor"])})' if otra else '')
                     + '.')
            d = {'agente': a, 'accion': accion, 'recompensa': float(recompensas[a]), 'explicacion': texto,
                 'alternativas': alternativas, 'confirmo': None}
            if registro is not None:
                d['id'] = registro.registrar(modulo=modulo, agente=a, observacion=vistas[a],
                                             accion=accion, recompensa=d['recompensa'], explicacion=texto,
                                             alternativas=alternativas, propuesta=ident, contexto=contexto)
            decisiones.append(d)
    if huella_grafo(grafo) != huella:
        raise SombraError('La red del operador cambió al proponer: la propuesta no vale.')
    del_agente = entorno.resultado('agente')
    de_la_regla = _regla_actual(entorno, regla)
    acierta = quien_acierta(del_agente, de_la_regla)
    salida = {'propuesta': ident, 'modulo': modulo, 'modo': modo_del_modulo(modulo, puertas), 'aplicada': False,
              'agente': del_agente, 'regla': de_la_regla, 'acierta': acierta, 'decisiones': decisiones}
    if registro is not None:
        registro.registrar_sombra({**dict(contexto or {}), 'propuesta': ident, 'modulo': modulo, 'acierta': acierta,
                                   'agente': del_agente, 'regla': de_la_regla})
    return salida


def _hueco(huecos, indice: int) -> dict[str, Any]:
    x = huecos[indice]
    return {'tipo': x.tipo, 'elemento': x.elemento} if x is not None else {'tipo': 'nada', 'elemento': ''}
