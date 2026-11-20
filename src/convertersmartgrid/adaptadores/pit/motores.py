"""Motores del PIT y su matriz de capacidades estudio × motor (107:RF-3, 107:RF-5).

Por qué una matriz. El PIT tiene que poder estudiarse sin licencia de DIgSILENT, pero el cortocircuito y la
confiabilidad de ``ComRel3`` no tienen equivalente abierto en el repositorio. La matriz hace que lo que un motor no
calcula **falte y se diga**, en vez de inventarse; y cada resultado nombra el motor que lo dio.

- ``abierto`` (pandapower, por defecto): flujo, tensión, cargabilidad y N-1; la confiabilidad se reduce a la potencia
  que queda sin servir en cada contingencia, y lo dice.
- ``digsilent`` (si hay licencia y el operador lo pide): todo, por ``tools/pit_pf.py`` en el carril ``powerfactory``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ...dominio.pit import PitError
from ...aplicacion.pit.red_area import RedArea
from .red_pandapower import calcular

__all__ = ['ESTUDIOS', 'MOTORES', 'Capacidad', 'capacidad', 'ejecutar', 'elegir_motor', 'estado_de_trabajo',
           'leer_informe_pf', 'plan_pf']

MOTORES = ('abierto', 'digsilent')
ESTUDIOS = ('flujo', 'tension', 'cargabilidad', 'n_1', 'confiabilidad', 'cortocircuito')
NO_DISPONIBLE = 'no disponible con el motor abierto'


@dataclass(frozen=True)
class Capacidad:
    motor: str
    estudio: str
    alcance: str  # 'completo', 'reducido' o 'no_disponible'
    texto: str

    @property
    def disponible(self) -> bool:
        return self.alcance != 'no_disponible'


_MATRIZ: dict[tuple[str, str], tuple[str, str]] = {
    **{('abierto', e): ('completo', 'pandapower, Newton-Raphson') for e in ('flujo', 'tension', 'cargabilidad', 'n_1')},
    ('abierto', 'confiabilidad'): ('reducido', 'solo la potencia sin servir en cada contingencia; la confiabilidad '
                                               f'de ComRel3 está {NO_DISPONIBLE}'),
    ('abierto', 'cortocircuito'): ('no_disponible', f'cortocircuito {NO_DISPONIBLE}'),
    **{('digsilent', e): ('completo', 'DIgSILENT PowerFactory (ComLdf, ComSimoutage, ComRel3, ComShc)')
       for e in ESTUDIOS},
}


def capacidad(motor: str, estudio: str) -> Capacidad:
    if motor not in MOTORES:
        raise PitError(f'motor {motor!r} desconocido; los motores son {MOTORES}')
    if estudio not in ESTUDIOS:
        raise PitError(f'estudio {estudio!r} desconocido; los estudios son {ESTUDIOS}')
    alcance, texto = _MATRIZ[(motor, estudio)]
    return Capacidad(motor, estudio, alcance, texto)


def elegir_motor(pedido: str | None, licencia: bool) -> str:
    """El abierto por defecto; DIgSILENT solo si se pide y hay licencia (pedirlo sin ella es un error, no un cambio
    callado de motor, porque los dos no dan las mismas cifras)."""
    if pedido in (None, '', 'abierto'):
        return 'abierto'
    if pedido != 'digsilent':
        raise PitError(f'motor {pedido!r} desconocido; los motores son {MOTORES}')
    if not licencia:
        # 107:RF-23: lo que se comprueba es que DIgSILENT esté instalado con el Python que pide; la licencia solo se
        # sabe al conectar y, si falta, lo dice el trabajo con la causa del arnés.
        raise PitError('se pidió DIgSILENT y no está disponible en este equipo: el estudio puede hacerse con el motor '
                       'abierto')
    return 'digsilent'


def estado_de_trabajo(no_convergen: Iterable[str], incompleto: Iterable[str]) -> dict[str, str]:
    """107:RF-24 (amplía 081:RF-17): el ``estado_trabajo`` de un diagnóstico que no salió entero, con su motivo.

    Un diagnóstico con años que no convergen terminaba «done» con ``completo: False``: la cola no lo distinguía de uno
    bueno. Lo que no converge manda sobre lo incompleto; un diagnóstico entero no lleva estado (queda «done»).
    """
    no_convergen, incompleto = list(no_convergen), list(incompleto)
    if no_convergen:
        return {'estado_trabajo': 'no_converge', 'motivo': 'no converge: ' + '; '.join(no_convergen)}
    if incompleto:
        return {'estado_trabajo': 'parcial', 'motivo': 'incompleto: ' + '; '.join(incompleto)}
    return {}


def plan_pf(perfil: Mapping[str, Any], area: Any, anios: Iterable[int], *, proyecto: str | None = None,
            carpeta: str | None = None, casos: Mapping[str, str] | None = None) -> dict[str, Any]:
    """107:RF-23: el plan de ``tools/pit_pf.py`` para el área: su proyecto de transmisión y el caso de cada año.

    Vienen del pedido o del perfil (``pit.digsilent``, o ``pit.digsilent.areas.<área>`` para un área concreta); nada
    se supone: sin proyecto o sin el caso de un año, el error lo dice antes de encolar.
    """
    cfg = dict((perfil.get('pit') or {}).get('digsilent') or {})
    cfg.update(((cfg.pop('areas', None) or {}).get(area.codigo)) or {})
    proyecto = proyecto or cfg.get('proyecto')
    if not proyecto:
        raise PitError('DIgSILENT: falta el proyecto de transmisión del área; indíquelo o declárelo en el perfil de la '
                       'empresa (pit.digsilent.proyecto)')
    todos = {str(k): str(v) for k, v in {**(cfg.get('casos') or {}), **(casos or {})}.items() if v}
    anios = [str(a) for a in anios]
    faltan = [a for a in anios if a not in todos]
    if faltan:
        raise PitError(f'DIgSILENT: falta el caso de estudio de los años {", ".join(faltan)} '
                       '(pit.digsilent.casos: año → caso del proyecto)')
    return {'project': str(proyecto), 'folder': carpeta or cfg.get('carpeta'), 'area': area.codigo,
            'titular': (list(area.titulares) or [''])[0], 'anios': {a: todos[a] for a in anios}}


def leer_informe_pf(informe: Mapping[str, Any], rc: int | None,
                    limites: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """107:RF-23, RF-24: el diagnóstico desde el informe de ``tools/pit_pf.py``, con el motor que lo dio.

    Cada año dice qué estudio hizo DIgSILENT, la tensión y la cargabilidad fuera de límite y los índices de
    confiabilidad; un flujo que no converge o un estudio que no terminó se dicen, nunca se rellenan.
    """
    cmax = (limites.get('cargabilidad_max_pct') or {}).get('valor')
    vmin = (limites.get('tension_min_pu') or {}).get('valor')
    vmax = (limites.get('tension_max_pu') or {}).get('valor')
    anios: dict[str, Any] = {}
    no_convergen: list[str] = []
    incompleto: list[str] = [str(informe['error'])] if informe.get('error') else []
    if rc not in (0, None) and not informe.get('error'):
        incompleto.append(f'el guion de DIgSILENT terminó con el código {rc}')
    for anio, d in sorted((informe.get('anios') or {}).items()):
        if d.get('error'):
            incompleto.append(f'{anio}: {d["error"]}')
            anios[anio] = {'error': d['error']}
            continue
        estudios = {e.get('orden'): e for e in d.get('estudios') or []}
        ldf = estudios.get('ComLdf') or {}
        if 'ComLdf' in estudios and not ldf.get('hecho'):
            no_convergen.append(f'{anio}: el flujo de carga de DIgSILENT no converge (código {ldf.get("return_code")})')
        incompleto += [f'{anio}: {o} no terminó (código {e.get("return_code")})' for o, e in estudios.items()
                       if o != 'ComLdf' and not e.get('hecho')]
        violaciones = []
        for barra, v in sorted((ldf.get('tensiones_pu') or {}).items()):
            if v is not None and vmin is not None and vmax is not None and not vmin <= v <= vmax:
                violaciones.append({'elemento': barra, 'magnitud': 'tension_pu', 'valor': v,
                                    'limite': vmin if v < vmin else vmax})
        for elemento, c in sorted((ldf.get('cargabilidad_pct') or {}).items()):
            if c is not None and cmax is not None and c > cmax:
                violaciones.append({'elemento': elemento, 'magnitud': 'cargabilidad_pct', 'valor': c, 'limite': cmax})
        anios[anio] = {'caso': d.get('caso'), 'estudios': [{'orden': o, 'hecho': bool(e.get('hecho'))}
                                                            for o, e in estudios.items()],
                       'violaciones': violaciones, 'indices': (estudios.get('ComRel3') or {}).get('indices') or {}}
    if not anios and not incompleto:
        incompleto.append('el informe de DIgSILENT no trae ningún año')
    return {'motor': 'digsilent', 'texto': _MATRIZ[('digsilent', 'flujo')][1], 'anios': anios,
            'cambios': list(informe.get('cambios') or ()), 'completo': not (no_convergen or incompleto),
            'avisos': no_convergen + incompleto, **estado_de_trabajo(no_convergen, incompleto)}


def ejecutar(estudio: str, red: RedArea, cargas: Mapping[str, tuple[float, float]], *, motor: str = 'abierto',
             fuera: Iterable[str] = ()) -> dict[str, Any]:
    """Un estudio con un motor; el resultado nombra siempre el motor y su alcance."""
    cap = capacidad(motor, estudio)
    base = {'motor': motor, 'estudio': estudio, 'alcance': cap.alcance, 'texto': cap.texto}
    if not cap.disponible:
        return {**base, 'disponible': False}
    if motor == 'digsilent':
        raise PitError('DIgSILENT corre en su carril con tools/pit_pf.py; aquí solo se leen sus resultados')
    r = calcular(red, cargas, fuera=fuera)
    return {**base, 'disponible': True, 'resultado': r}
