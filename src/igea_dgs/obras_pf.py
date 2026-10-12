"""Lo que las obras de mejora de la spec 011 deciden sin DIgSILENT.

El guion ``tools/obras_pf.py`` lee del proyecto las barras, los tramos, la troncal y los
tipos de cada alimentador, y aplica las obras. Aquí está lo que no necesita
PowerFactory, para probarlo con redes sorteadas:

- el modelo de cada obra y su validación al definirla en el formulario (RF-56, RF-58);
- el nombre de la variación de cada obra, sin repetir uno que ya exista (RF-56);
- el nombre de la copia de un tipo, con el sufijo de tensión del conversor (RF-61);
- cuándo dos tipos son el mismo, para reutilizar una copia o no (RF-62, RF-63);
- el plan de la simulación: por obra, los elementos que cambiaría, los tipos que
  copiaría y su variación, sin escribir nada (RF-69).

Por qué se copian los tipos y nunca se editan (RF-59): DIgSILENT no graba los tipos en
las variaciones. Cambiar ``uline`` de un ``TypLne`` compartido para migrar un
alimentador lo cambiaría también en «Sin proyecto» y en los demás alimentadores. La
copia es un objeto nuevo que solo usa quien la variación de la obra se lo asigna.

Ninguna tensión está fijada aquí (RF-85, P13): la de origen es la que se lee del
alimentador y la de destino la que da el operador.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .estudios_pf import CASO_BASE, CON_PROYECTO, SIN_PROYECTO
from .naming import feeder_short_name, nombre_con_tension, sufijo_tension

#: DIgSILENT no admite más en ``loc_name``.
LARGO_MAXIMO = 40
#: Media banda de tensión del banco que regula y del regulador, en p.u. alrededor de la
#: consigna: la misma que el DGS da a los cambiadores de toma (``dgs.py``, 0,99 a 1,01).
#: Sin banda, DIgSILENT movería escalones y tomas en cada iteración sin asentarse.
BANDA_TENSION_PU = 0.01
#: Casos en que se puede activar una obra; el «Caso base» nunca (RF-58).
CASOS = (SIN_PROYECTO, CON_PROYECTO)
CLASES = ('condensador', 'reconectador', 'regulador', 'seccion', 'terna', 'tension')
#: Clase de tipo que pide cada obra (RF-89). Banco y terna no tienen tipo; la migración
#: copia los que ya usa el alimentador.
CLASE_DE_TIPO = {'reconectador': 'TypRecl', 'regulador': 'TypVoltreg', 'seccion': 'TypLne'}
#: De dónde puede venir un tipo (RF-89 a RF-91).
ORIGENES = ('proyecto', 'global', 'otro')

#: Datos que se leen de cada tipo y que deciden si dos son el mismo (RF-62). Son los del
#: esquema DGS de PF (``schemas/pf21_dgs_1_8_4.json``) más la sección ``qurs``: con menos,
#: dos conductores de la misma tensión y corriente pero distinta resistencia pasarían
#: por iguales y una obra reutilizaría el que no es. ``TypRecl`` no está en el esquema
#: y sus datos son de protecciones, que esta iteración no estudia (RF-74): se compara
#: solo por nombre.
ATRIBUTOS_TIPO = {
    'TypLne': ('uline', 'sline', 'InomAir', 'qurs', 'cohl_', 'rline', 'xline', 'rline0',
               'xline0', 'bline', 'bline0', 'Ithr', 'tmax', 'rtemp', 'systp', 'nlnph',
               'nneutral', 'frnom'),
    'TypTr2': ('strn', 'frnom', 'utrn_h', 'utrn_l', 'uktr', 'pcutr', 'uk0tr', 'ur0tr',
               'tr2cn_h', 'tr2cn_l', 'nt2ag', 'curmg', 'pfe', 'nt2ph', 'zx0hl_n', 'itapch',
               'tap_side', 'dutap', 'phitr', 'nntap0', 'ntpmn', 'ntpmx'),
    'TypVoltreg': ('type', 'config', 'frnom', 'Un', 'In', 'pcReg', 'nntap0', 'ntapmin',
                   'ntapmax', 'uk', 'pcu'),
    'TypRecl': (),
}
#: Lo que se muestra junto a cada tipo para elegirlo (RF-94), con su unidad. En
#: ``TypLne``, ``sline`` es la corriente nominal en kA y ``qurs`` la sección.
RESUMEN_TIPO = {
    'TypLne': (('uline', 'kV'), ('sline', 'kA'), ('qurs', 'mm²')),
    'TypTr2': (('strn', 'MVA'), ('utrn_h', 'kV'), ('utrn_l', 'kV')),
    'TypVoltreg': (('Un', 'kV'), ('In', 'kA'), ('pcReg', '%'), ('ntapmax', 'pasos')),
    'TypRecl': (),
}


class ObrasError(ValueError):
    """Obra que no se puede definir o aplicar; el mensaje es para el operador."""


# --------------------------------------------------------------------------- modelo
@dataclass(frozen=True)
class TipoRef:
    """El tipo que elige el operador en una de las tres bibliotecas."""

    nombre: str
    clase: str
    origen: str = 'proyecto'
    proyecto: str = ''
    """Solo con ``origen='otro'``: el proyecto de DIgSILENT de donde se trae (RF-91)."""


@dataclass(frozen=True)
class Tipo:
    """Un tipo leído de una biblioteca, con los datos que lo distinguen."""

    nombre: str
    clase: str
    datos: Mapping[str, Any]
    origen: str = 'proyecto'
    proyecto: str = ''


@dataclass(frozen=True)
class Tramo:
    nombre: str
    tipo: str
    nlnum: int = 1


@dataclass(frozen=True)
class RedAlimentador:
    """Lo que el guion lee de un alimentador en el proyecto."""

    alimentador: str
    kv: float
    """Tensión de la cabecera: la de origen de una migración (RF-85)."""
    barras: Mapping[str, float]
    """Barra → ``uknom`` en kV; las de baja de las SED también están."""
    tramos: Mapping[str, Tramo]
    troncal: tuple[str, ...] = ()
    """Tramos de la troncal que da el estudio de troncal (RF-44)."""
    trafos: Mapping[str, str] = field(default_factory=dict)
    """Transformador de SED → nombre de su ``TypTr2``."""
    condensadores: Mapping[str, float | None] = field(default_factory=dict)
    """Banco → ``ushnm`` en kV: la migración cambia solo los de media (RF-84)."""
    reguladores: Mapping[str, str] = field(default_factory=dict)
    """Regulador → nombre de su ``TypVoltreg``."""
    cabecera_compartida_con: tuple[str, ...] = ()
    """Alimentadores que comparten la barra de cabecera o la fuente (RF-102)."""


@dataclass(frozen=True)
class Obra:
    """Una obra como la define el operador. Solo lleva los campos de su clase."""

    clase: str
    alimentador: str
    casos: tuple[str, ...]
    barra: str = ''
    tramo: str = ''
    tramos: tuple[str, ...] = ()
    q_kvar: float | None = None
    escalones: int | None = None
    consigna_pu: float | None = None
    rango_pct: float | None = None
    pasos: int | None = None
    """Pasos a cada lado de la toma central del regulador (``ntapmax`` = −``ntapmin``)."""
    tipo: TipoRef | None = None
    kv_destino: float | None = None

    def a_dict(self) -> dict[str, Any]:
        """Lo que se guarda en el espacio de trabajo; ``validar_obra`` lo reconstruye."""
        out = {}
        for clave, valor in asdict(self).items():
            if valor is None or valor == '' or valor == ():
                continue
            out[clave] = list(valor) if isinstance(valor, tuple) else valor
        return out


# --------------------------------------------------------------------------- validación
def _numero(datos: Mapping, clave: str, que: str, *, entero: bool = False,
            requerido: bool = True) -> float | int | None:
    valor = datos.get(clave)
    if valor is None or valor == '':
        if requerido:
            raise ObrasError(f'Falta {que}.')
        return None
    try:
        if isinstance(valor, bool):
            raise ValueError
        numero = float(valor)
    except (TypeError, ValueError):
        raise ObrasError(f'{que[0].upper()}{que[1:]} tiene que ser un número: {valor!r}.') from None
    if not math.isfinite(numero) or numero <= 0 or (entero and numero != int(numero)):
        clase = 'un entero positivo' if entero else 'un número positivo'
        raise ObrasError(f'{que[0].upper()}{que[1:]} tiene que ser {clase}: {valor!r}.')
    return int(numero) if entero else numero


def _texto(datos: Mapping, clave: str, que: str) -> str:
    valor = str(datos.get(clave) or '').strip()
    if not valor:
        raise ObrasError(f'Falta {que}.')
    return valor


def _casos(valor: Any) -> tuple[str, ...]:
    pedidos = [valor] if isinstance(valor, str) else list(valor or [])
    if not pedidos:
        raise ObrasError(f'Elija al menos un caso para la obra: {" o ".join(CASOS)}.')
    if CASO_BASE in pedidos:
        raise ObrasError(f'Una obra no se activa nunca en el «{CASO_BASE}»: es la red de '
                         f'referencia, sin calibrar.')
    malos = sorted(set(pedidos) - set(CASOS))
    if malos:
        raise ObrasError(f'No es un caso de obras: {", ".join(map(repr, malos))}; '
                         f'los que hay son {" y ".join(CASOS)}.')
    return tuple(c for c in CASOS if c in pedidos)


def _tipo_ref(valor: Any, clase_obra: str, *, requerido: bool) -> TipoRef | None:
    clase = CLASE_DE_TIPO[clase_obra]
    if not valor:
        if requerido:
            raise ObrasError(f'Falta el tipo ({clase}) de la obra {clase_obra}.')
        return None
    if isinstance(valor, TipoRef):
        valor = asdict(valor)
    nombre = str(valor.get('nombre') or '').strip()
    if not nombre:
        raise ObrasError(f'Falta el nombre del tipo ({clase}) de la obra {clase_obra}.')
    if valor.get('clase', clase) != clase:
        raise ObrasError(f'El tipo de una obra {clase_obra} tiene que ser {clase}, '
                         f'no {valor.get("clase")}.')
    origen = valor.get('origen') or 'proyecto'
    if origen not in ORIGENES:
        raise ObrasError(f'Origen de tipo desconocido: {origen!r}; los que hay son '
                         f'{", ".join(ORIGENES)}.')
    proyecto = str(valor.get('proyecto') or '').strip()
    if origen == 'otro' and not proyecto:
        raise ObrasError(f'Falta el proyecto de DIgSILENT de donde se trae el tipo {nombre!r}.')
    return TipoRef(nombre, clase, origen, proyecto if origen == 'otro' else '')


def _lista(valor: Any) -> tuple[str, ...]:
    if isinstance(valor, str):
        valor = [valor]
    vistos = []
    for v in valor or []:
        v = str(v).strip()
        if v and v not in vistos:
            vistos.append(v)
    return tuple(vistos)


def validar_obra(datos: Mapping[str, Any]) -> Obra:
    """La obra del formulario o del espacio de trabajo, o un error que dice qué falta.

    Solo comprueba la obra en sí. Que su barra, tramo o tipo existan en el proyecto lo
    dice ``plan_simulacion``, con lo leído de DIgSILENT.
    """
    clase = str(datos.get('clase') or '').strip()
    if clase not in CLASES:
        raise ObrasError(f'No hay obras de la clase {clase!r}; las que hay son '
                         f'{", ".join(CLASES)}.')
    comunes: dict[str, Any] = {
        'clase': clase,
        'alimentador': _texto(datos, 'alimentador', 'el alimentador de la obra'),
        'casos': _casos(datos.get('casos'))}
    if clase == 'condensador':
        return Obra(**comunes, barra=_texto(datos, 'barra', 'la barra del banco'),
                    q_kvar=_numero(datos, 'q_kvar', 'la potencia reactiva del banco (kvar)'),
                    escalones=_numero(datos, 'escalones', 'el número de escalones', entero=True),
                    consigna_pu=_numero(datos, 'consigna_pu', 'la consigna de tensión (p.u.)',
                                        requerido=False))
    if clase == 'reconectador':
        return Obra(**comunes, tramo=_texto(datos, 'tramo', 'el tramo del reconectador'),
                    tipo=_tipo_ref(datos.get('tipo'), clase, requerido=False))
    if clase == 'regulador':
        return Obra(**comunes, tramo=_texto(datos, 'tramo', 'el tramo del regulador'),
                    consigna_pu=_numero(datos, 'consigna_pu', 'la consigna de tensión (p.u.)'),
                    rango_pct=_numero(datos, 'rango_pct', 'el rango de regulación (%)'),
                    pasos=_numero(datos, 'pasos', 'el número de pasos', entero=True),
                    tipo=_tipo_ref(datos.get('tipo'), clase, requerido=True))
    if clase == 'seccion':
        return Obra(**comunes, tramos=_lista(datos.get('tramos')),
                    tipo=_tipo_ref(datos.get('tipo'), clase, requerido=True))
    if clase == 'terna':
        return Obra(**comunes, tramos=_lista(datos.get('tramos')))
    return Obra(**comunes, kv_destino=_numero(datos, 'kv_destino',
                                              'la tensión de destino (kV)'))


# --------------------------------------------------------------------------- nombres
def nombre_pf(texto: str) -> str:
    """Solo letras, dígitos, ``_`` y ``-``: DIgSILENT no acepta ``.`` ni ``/`` en un nombre."""
    return re.sub(r'[^A-Za-z0-9_\-]', '_', texto)[:LARGO_MAXIMO]


def nombre_libre(base: str, ocupados: Iterable[str]) -> str:
    """``base`` o el primero libre de ``base_2``, ``base_3``… sin pasar de 40 caracteres.

    Sin distinguir mayúsculas, porque DIgSILENT tampoco las distingue al buscar por nombre.
    """
    base = nombre_pf(base)
    usados = {o.lower() for o in ocupados}
    candidato, n = base, 1
    while candidato.lower() in usados:
        n += 1
        sufijo = f'_{n}'
        candidato = base[:LARGO_MAXIMO - len(sufijo)] + sufijo
    return candidato


#: Prefijo de las variaciones de las obras: el informe de los estudios lista por él las
#: obras activas en cada caso (RF-68).
PREFIJO_VARIACION = 'Obra_'


def nombre_variacion(obra: Obra, ocupadas: Iterable[str]) -> str:
    """La obra y el alimentador, sin repetir ninguna variación del proyecto (RF-56)."""
    return nombre_libre(f'{PREFIJO_VARIACION}{obra.clase}_{feeder_short_name(obra.alimentador)}',
                        ocupadas)


def nombre_copia(original: str, *, kv: float | None = None, kv_origen: float | None = None,
                 cambio: str = '') -> str:
    """Nombre de la copia de un tipo: el del original y el cambio (RF-61).

    La tensión lleva el sufijo del conversor (``naming``), para que el mismo conductor a
    22,9 kV se llame igual lo cree el DGS o una obra. Si el original ya lleva el sufijo
    de su tensión (un DGS de red unida), se cambia en vez de acumular otro:
    ``AAAC_70_10kV`` pasa a ``AAAC_70_22_9kV``, no a ``AAAC_70_10kV_22_9kV``.
    """
    base = original
    if kv_origen is not None:
        viejo = '_' + sufijo_tension(kv_origen)
        if base.lower().endswith(viejo.lower()):
            base = base[:-len(viejo)]
    if kv is not None:
        cola = '_' + sufijo_tension(kv)
        nombre = nombre_con_tension(base, kv)
    else:
        cola = f'_{cambio}'
        nombre = base + cola
    nombre = re.sub(r'[^A-Za-z0-9_\-]', '_', nombre)
    if len(nombre) > LARGO_MAXIMO:
        nombre = nombre[:LARGO_MAXIMO - len(cola)] + nombre[-len(cola):]
    return nombre


# --------------------------------------------------------------------------- tipos
def resumen_tipo(clase: str, datos: Mapping[str, Any]) -> str:
    """``22.9 kV · 0.21 kA · 70 mm²``: los datos que deciden la elección (RF-94).

    Un dato que el tipo no tiene no se muestra, en vez de mostrarse como 0.
    """
    partes = []
    for atributo, unidad in RESUMEN_TIPO.get(clase, ()):
        valor = datos.get(atributo)
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            partes.append(f'{valor:g} {unidad}')
    return ' · '.join(partes)


def mismos_datos(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Dos tipos son el mismo si tienen los mismos datos.

    Los números se comparan con tolerancia relativa de 1e-9: DIgSILENT guarda en doble
    precisión y una lectura puede no devolver el mismo último bit que se escribió.
    """
    if set(a) != set(b):
        return False
    for clave, x in a.items():
        y = b[clave]
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) \
                and not isinstance(x, bool) and not isinstance(y, bool):
            if not math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-9):
                return False
        elif x != y:
            return False
    return True


def resolver_copia(nombre: str, clase: str, datos: Mapping[str, Any],
                   proyecto: Mapping[str, Tipo]) -> tuple[str, bool, str]:
    """Nombre de la copia, si se reutiliza una que ya está y el aviso para el operador.

    Con el mismo nombre y los mismos datos se reutiliza (RF-62). Con el mismo nombre y
    otros datos no se toca: la copia toma el siguiente nombre libre y se dice (RF-63).
    """
    indice = {(t.clase, t.nombre.lower()): t for t in proyecto.values()}
    candidato, n = nombre, 1
    while True:
        existente = indice.get((clase, candidato.lower()))
        if existente is None or mismos_datos(existente.datos, datos):
            aviso = '' if candidato == nombre else (
                f'Ya hay un tipo {nombre!r} ({clase}) con otros datos: la copia se llama '
                f'{candidato!r}.')
            return candidato, existente is not None, aviso
        n += 1
        sufijo = f'_{n}'
        candidato = nombre[:LARGO_MAXIMO - len(sufijo)] + sufijo


# --------------------------------------------------------------------------- simulación
@dataclass
class _Estado:
    """Cómo queda un alimentador con las obras planificadas antes, en su orden."""

    kv: float
    barras: dict[str, float]
    tipo_tramo: dict[str, str]
    nlnum: dict[str, int]
    trafos: dict[str, str]

    @classmethod
    def de(cls, red: RedAlimentador) -> '_Estado':
        return cls(red.kv, dict(red.barras), {k: t.tipo for k, t in red.tramos.items()},
                   {k: t.nlnum for k, t in red.tramos.items()}, dict(red.trafos))

    def copia(self) -> '_Estado':
        return _Estado(self.kv, dict(self.barras), dict(self.tipo_tramo), dict(self.nlnum),
                       dict(self.trafos))


class _Plan:
    """Una obra que se planifica: lo que cambiaría, sin tocar el estado hasta acabar bien."""

    def __init__(self, obra: Obra, red: RedAlimentador, estado: _Estado,
                 proyecto: dict[str, Tipo], ajenos: Mapping[tuple, Tipo]):
        self.obra, self.red = obra, red
        self.estado = estado.copia()
        self.proyecto = dict(proyecto)
        self.ajenos = ajenos
        self.elementos: list[dict[str, str]] = []
        self.tipos: list[dict[str, Any]] = []
        self.avisos: list[str] = []
        self.extra: dict[str, Any] = {}
        self._copiados: dict[tuple[str, str], str] = {}

    # Lo que se lee
    def tramo(self, nombre: str) -> str:
        if nombre not in self.estado.tipo_tramo:
            raise ObrasError(f'El tramo {nombre!r} no es del alimentador {self.red.alimentador}.')
        return nombre

    def tramos(self) -> list[str]:
        """Los que indica el operador o, si no indica ninguno, la troncal (RF-78, RF-80)."""
        pedidos = list(self.obra.tramos) or list(self.red.troncal)
        if not pedidos:
            raise ObrasError(f'No se leyó la troncal del alimentador {self.red.alimentador}: '
                             f'indique los tramos.')
        return [self.tramo(t) for t in pedidos]

    def traer(self, ref: TipoRef) -> Tipo:
        if ref.origen == 'proyecto':
            tipo = next((t for t in self.proyecto.values()
                         if t.clase == ref.clase and t.nombre.lower() == ref.nombre.lower()), None)
        else:
            tipo = self.ajenos.get((ref.origen, ref.proyecto.lower(), ref.clase, ref.nombre.lower()))
        if tipo is None:
            donde = {'proyecto': 'del proyecto', 'global': 'global de DIgSILENT',
                     'otro': f'del proyecto {ref.proyecto!r}'}[ref.origen]
            raise ObrasError(f'No está el tipo {ref.nombre!r} ({ref.clase}) en la biblioteca {donde}.')
        return tipo

    # Lo que se cambia
    def elemento(self, nombre: str, clase: str, cambio: str, tipo: str = '') -> None:
        """Un elemento que cambia; ``tipo``, el que se le asigna si cambia de tipo."""
        fila = {'elemento': nombre, 'clase': clase, 'cambio': cambio}
        if tipo:
            fila['tipo'] = tipo
        self.elementos.append(fila)

    def con_datos(self, base: Tipo, datos: Mapping[str, Any], nombre: str) -> str:
        """El tipo que tendrá el elemento: el mismo si ya sirve, o una copia (RF-59, RF-60).

        Un tipo de otra biblioteca siempre se copia al proyecto (RF-92). Una obra que
        necesita la misma copia dos veces (la migración, un tipo por original, RF-99) la
        lista una vez.
        """
        if base.origen == 'proyecto' and mismos_datos(base.datos, datos):
            return base.nombre
        clave = (base.clase, base.nombre)
        if clave in self._copiados:
            return self._copiados[clave]
        final, reutiliza, aviso = resolver_copia(nombre, base.clase, datos, self.proyecto)
        if aviso:
            self.avisos.append(aviso)
        self.tipos.append({'nombre': final, 'clase': base.clase, 'desde': base.nombre,
                           'origen': base.origen, 'proyecto': base.proyecto,
                           'reutiliza': reutiliza, 'datos': dict(datos)})
        self.proyecto[final] = Tipo(final, base.clase, dict(datos))
        self._copiados[clave] = final
        return final

    def fila(self) -> dict[str, Any]:
        return {'elementos': self.elementos, 'tipos': self.tipos, 'avisos': self.avisos,
                **self.extra}


def _condensador(p: _Plan) -> None:
    o = p.obra
    if o.barra not in p.estado.barras:
        raise ObrasError(f'La barra {o.barra!r} no es del alimentador {o.alimentador}.')
    modo = (f'regulando {o.consigna_pu:g} p.u. por escalones' if o.consigna_pu
            else 'fijo, con todos los escalones conectados')
    p.elemento(f'Banco en {o.barra}', 'ElmShnt',
               f'nuevo: {o.q_kvar:g} kvar en {o.escalones} escalones a '
               f'{p.estado.barras[o.barra]:g} kV, {modo}')


def _reconectador(p: _Plan) -> None:
    o = p.obra
    tramo = p.tramo(o.tramo)
    p.elemento(f'Reconectador en {tramo}', 'StaSwitch',
               'nuevo, cerrado, al principio del tramo, con protección y reenganche')
    rele = 'nuevo, en el cubículo del interruptor, con un bloque de reenganche'
    if o.tipo:
        base = p.traer(o.tipo)
        p.extra['tipo'] = p.con_datos(base, base.datos, base.nombre)
        rele += f" de tipo {p.extra['tipo']}"
    p.elemento(f'Relé de {tramo}', 'ElmRelay', rele)
    p.avisos.append('El reconectador no cambia el flujo de carga ni los estudios de esta '
                    'iteración: su efecto está en la fiabilidad y las protecciones.')


def _regulador(p: _Plan) -> None:
    o = p.obra
    tramo = p.tramo(o.tramo)
    base = p.traer(o.tipo)
    # Los pasos son a cada lado de la toma central (usuario, 2026-10-12), como el rango de
    # ``pcReg``, que DIgSILENT da en «+/-»: la toma neutra es la 0.
    datos = {**base.datos, 'Un': p.estado.kv, 'pcReg': o.rango_pct,
             'ntapmax': o.pasos, 'ntapmin': -o.pasos, 'nntap0': 0}
    tipo = p.con_datos(base, datos, nombre_copia(base.nombre, cambio=f'{o.rango_pct:g}pct_{o.pasos}p'))
    p.extra['tipo'] = tipo
    p.elemento(f'{tramo}_REG', 'ElmTerm', f'nueva, a {p.estado.kv:g} kV, entre el regulador y el tramo')
    p.elemento(f'Cubículo de {tramo}', 'StaCubic', f'pasa a la barra {tramo}_REG')
    p.elemento(f'Regulador en {tramo}', 'ElmVoltreg',
               f'nuevo, {tipo}, consigna {o.consigna_pu:g} p.u., ±{o.pasos} pasos, {o.rango_pct:g} %')


def _seccion(p: _Plan) -> None:
    o = p.obra
    base = p.traer(o.tipo)
    kv = p.estado.kv
    # Un tipo a otra tensión se copia a la del alimentador (RF-79): ``uline`` decide la
    # tensión nominal de la línea en DIgSILENT.
    otra = base.datos.get('uline')
    nombre = (base.nombre if otra is not None and math.isclose(otra, kv)
              else nombre_copia(base.nombre, kv=kv, kv_origen=otra))
    tipo = p.con_datos(base, {**base.datos, 'uline': kv}, nombre)
    p.extra['tipo'] = tipo
    troncal = set(p.red.troncal)
    if not troncal:
        p.avisos.append('No se leyó la troncal del alimentador: no se comprueba si los tramos '
                        'son de ella.')
    for tramo in p.tramos():
        if troncal and tramo not in troncal:                       # RF-87
            p.avisos.append(f'El tramo {tramo} no es de la troncal: se cambia igual.')
        antes = p.estado.tipo_tramo[tramo]
        if antes == tipo:
            p.avisos.append(f'El tramo {tramo} ya tiene el tipo {tipo}.')
            continue
        p.elemento(tramo, 'ElmLne', f'typ_id {antes} → {tipo}')
        p.estado.tipo_tramo[tramo] = tipo


def _terna(p: _Plan) -> None:
    for tramo in p.tramos():
        n = p.estado.nlnum[tramo]
        p.elemento(tramo, 'ElmLne', f'nlnum {n} → {n + 1}')
        p.estado.nlnum[tramo] = n + 1


def _tension(p: _Plan) -> None:
    o, red, estado = p.obra, p.red, p.estado
    if red.cabecera_compartida_con:
        raise ObrasError(
            f'La barra de cabecera o la fuente de {o.alimentador} alimentan también a '
            f'{", ".join(red.cabecera_compartida_con)}: no se migra.')
    origen, destino = estado.kv, o.kv_destino
    if math.isclose(origen, destino):
        raise ObrasError(f'El alimentador {o.alimentador} ya está a {origen:g} kV.')
    p.extra.update(kv_origen=origen, kv_destino=destino)

    # Las barras de media son las que están a la tensión de origen (RF-85); las de baja
    # de las SED tienen otra y no se tocan.
    for barra in sorted(b for b, v in estado.barras.items() if math.isclose(v, origen)):
        p.elemento(barra, 'ElmTerm', f'uknom {origen:g} → {destino:g} kV')
        estado.barras[barra] = destino

    def tipo_del_proyecto(clase: str, nombre: str, donde: str) -> Tipo:
        try:
            return p.traer(TipoRef(nombre, clase))
        except ObrasError:
            raise ObrasError(f'Falta en la biblioteca del proyecto el tipo {nombre!r} ({clase}) '
                             f'de {donde}.') from None

    for tramo in sorted(estado.tipo_tramo):
        base = tipo_del_proyecto('TypLne', estado.tipo_tramo[tramo], f'el tramo {tramo}')
        nuevo = p.con_datos(base, {**base.datos, 'uline': destino},
                            nombre_copia(base.nombre, kv=destino, kv_origen=origen))
        p.elemento(tramo, 'ElmLne', f'typ_id {base.nombre} → {nuevo}', nuevo)
        estado.tipo_tramo[tramo] = nuevo
    # En las SED cambia solo la alta: la baja y la potencia quedan (RF-83, RF-103).
    for trafo in sorted(estado.trafos):
        base = tipo_del_proyecto('TypTr2', estado.trafos[trafo], f'la SED {trafo}')
        nuevo = p.con_datos(base, {**base.datos, 'utrn_h': destino},
                            nombre_copia(base.nombre, kv=destino, kv_origen=origen))
        p.elemento(trafo, 'ElmTr2', f'typ_id {base.nombre} → {nuevo}', nuevo)
        estado.trafos[trafo] = nuevo
    # Los condensadores y reguladores de media pasan a la tensión nueva (RF-84); un banco
    # de baja en una SED tiene otra tensión y se queda.
    for nombre, kv in sorted(red.condensadores.items()):
        if kv is not None and math.isclose(kv, origen):
            p.elemento(nombre, 'ElmShnt', f'ushnm {origen:g} → {destino:g} kV')
    for nombre, tipo in sorted(red.reguladores.items()):
        base = tipo_del_proyecto('TypVoltreg', tipo, f'el regulador {nombre}')
        nuevo = p.con_datos(base, {**base.datos, 'Un': destino},
                            nombre_copia(base.nombre, kv=destino, kv_origen=origen))
        p.elemento(nombre, 'ElmVoltreg', f'typ_id {base.nombre} → {nuevo}', nuevo)
    p.avisos.append(f'La fuente de la cabecera conserva su consigna en p.u., ahora sobre '
                    f'{destino:g} kV.')
    estado.kv = destino


_PLANES = {'condensador': _condensador, 'reconectador': _reconectador, 'regulador': _regulador,
           'seccion': _seccion, 'terna': _terna, 'tension': _tension}


def plan_simulacion(obras: Iterable[Obra], redes: Mapping[str, RedAlimentador],
                    tipos: Iterable[Tipo], *, variaciones: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Por obra, lo que haría al aplicarse, sin escribir en el proyecto (RF-69).

    Las obras se planifican en el orden en que llegan: dos obras sobre el mismo tramo
    (sección y terna) se suman, y una copia que planifica una obra la reutiliza la
    siguiente (RF-62). Una obra que no se puede aplicar lleva su ``error`` y no cuenta
    para las demás.
    """
    tipos = list(tipos)
    proyecto = {t.nombre: t for t in tipos if t.origen == 'proyecto'}
    ajenos = {(t.origen, t.proyecto.lower(), t.clase, t.nombre.lower()): t
              for t in tipos if t.origen != 'proyecto'}
    ocupadas = list(variaciones)
    estados: dict[str, _Estado] = {}
    out = []
    for i, obra in enumerate(obras, 1):
        fila: dict[str, Any] = {'obra': i, 'clase': obra.clase, 'alimentador': obra.alimentador,
                                'casos': list(obra.casos), 'variacion': '', 'elementos': [],
                                'tipos': [], 'avisos': [], 'error': ''}
        red = redes.get(obra.alimentador)
        if red is None:
            fila['error'] = f'El alimentador {obra.alimentador!r} no está en el proyecto leído.'
            out.append(fila)
            continue
        estado = estados.setdefault(obra.alimentador, _Estado.de(red))
        plan = _Plan(obra, red, estado, proyecto, ajenos)
        try:
            _PLANES[obra.clase](plan)
        except ObrasError as exc:
            fila['error'] = str(exc)
            out.append(fila)
            continue
        estados[obra.alimentador] = plan.estado
        proyecto = plan.proyecto
        fila['variacion'] = nombre_variacion(obra, ocupadas)
        ocupadas.append(fila['variacion'])
        fila.update(plan.fila())
        out.append(fila)
    return out


# --------------------------------------------------------------------------- aplicar
def tipo_de_ficha(ficha: Mapping[str, Any]) -> Tipo:
    """Un tipo como lo lista ``tools/obras_pf.py --bibliotecas``."""
    return Tipo(ficha['nombre'], ficha['clase'], dict(ficha.get('datos') or {}),
                ficha.get('origen') or 'proyecto', ficha.get('proyecto') or '')


def red_de_lectura(alimentador: str, leido: Mapping[str, Any], *,
                   troncal: Iterable[str] = ()) -> RedAlimentador:
    """Un alimentador como lo lee ``tools/obras_pf.py --bibliotecas`` (RF-88).

    Un alimentador sin tensión de cabecera leída no se puede migrar ni dar tensión a
    un tipo copiado: es un error, no un 0 que haría pasar la migración por buena.
    """
    kv = leido.get('kv')
    if not isinstance(kv, (int, float)) or kv <= 0:
        raise ObrasError(f'No se leyó la tensión del alimentador {alimentador}.')
    return RedAlimentador(
        alimentador=alimentador, kv=float(kv),
        barras={b['nombre']: b['kv'] for b in leido.get('barras') or []
                if isinstance(b.get('kv'), (int, float))},
        tramos={t['nombre']: Tramo(t['nombre'], t.get('tipo') or '', int(t.get('nlnum') or 1))
                for t in leido.get('tramos') or []},
        troncal=tuple(troncal),
        trafos={t['nombre']: t.get('tipo') or '' for t in leido.get('trafos') or []},
        condensadores={c['nombre']: c.get('kv') for c in leido.get('condensadores') or []},
        reguladores={r['nombre']: r.get('tipo') or '' for r in leido.get('reguladores') or []},
        cabecera_compartida_con=tuple(leido.get('cabecera_compartida_con') or ()))


#: Diferencia que la comprobación de «Sin proyecto» tolera (RF-64): la red es la misma, así
#: que solo cabe el ruido del Newton entre dos flujos, muy por debajo de estos valores.
TOLERANCIA_KW = 0.01
TOLERANCIA_PU = 1e-5


def diferencias_sin_proyecto(antes: Mapping[str, Any], despues: Mapping[str, Any],
                             feeders: Iterable[str]) -> list[dict[str, Any]]:
    """Los alimentadores cuya cabecera o tensión mínima cambió en «Sin proyecto» (RF-64, RF-65).

    ``antes`` y ``despues`` son medidas por alimentador (``cabecera`` con ``kw`` y ``kvar``,
    y ``vm_min``), como las de ``medir_estado`` de ``tools/cargas_pf.py``. Solo se miran
    los ``feeders`` dados: los que no tienen obras activas en ese caso. Un cambio allí
    quiere decir que una obra tocó algo compartido, como un tipo.
    """
    out = []
    for feeder in sorted(feeders):
        a, d = antes.get(feeder) or {}, despues.get(feeder) or {}
        pares = [('cabecera_kw', (a.get('cabecera') or {}).get('kw'),
                  (d.get('cabecera') or {}).get('kw'), TOLERANCIA_KW),
                 ('cabecera_kvar', (a.get('cabecera') or {}).get('kvar'),
                  (d.get('cabecera') or {}).get('kvar'), TOLERANCIA_KW),
                 ('vm_min', a.get('vm_min'), d.get('vm_min'), TOLERANCIA_PU)]
        for medida, x, y, tolerancia in pares:
            if x is None and y is None:
                continue
            if x is None or y is None or abs(x - y) > tolerancia:
                out.append({'alimentador': feeder, 'medida': medida, 'antes': x, 'despues': y})
    return out
