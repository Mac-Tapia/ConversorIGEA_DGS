"""Registro normativo común de las specs 107 (PIT) y 108 (VAD): cada norma con su estado y sus reglas citadas.

Por qué existe. G0 (2026-11-14) encontró que el conversor citaba los TdR del VAD solo en comentarios, y que el
PIDE trataba como norma un texto que es un proyecto de 2017. Un número normativo sin su acto, su estado jurídico
y su cita no se puede revisar ni actualizar. Aquí cada **norma** lleva acto, título, URL, fechas, huella del texto
leído, estado jurídico, vigencia y sus relaciones (``modifica`` / ``modificada_por``); y cada **regla** lleva
clave, valor, unidad, artículo o anexo, página o líneas de la copia local y la cita literal.

Contrato (107 plan, parte A; 108 plan, «Registro normativo y estado jurídico»):

* Estados: ``vigente_comprobada`` (texto leído y vigente), ``modificada`` (vigente en la versión que se cita),
  ``prepublicada`` (proyecto), ``no_verificada`` (sin texto leído o sin huella) y ``derogada``.
* :meth:`RegistroNormativo.regla` devuelve la regla con su estado y si es **obligatoria**: solo lo es la de una
  norma ``vigente_comprobada``, o ``modificada`` dentro de su vigencia, y siempre que tenga cita. Las demás se
  usan como referencia y quien las usa lo dice (107:RF-8, 108:RF-10). Si varias normas vigentes a la vez traen la
  clave sin que la más reciente modifique a las demás, no elige: lanza :class:`ReglaAmbigua` (RN-AMB).
* Cada regla puede declarar su ``caracter`` (obligatoria, criterio o referencia), su ``aplicacion``, su
  ``entregable`` y, en un cuadro, las ``cita_lineas`` de su título; cada norma, su ``fecha_emision`` aparte de la
  ``fecha_publicacion`` (108, VAD-REQ). Vacíos no cambian ninguna huella.
* :meth:`RegistroNormativo.reglas_vigentes` devuelve todas las vigentes de una clave, sin las modificadas: la consulta
  de las normas que se suman (las modificaciones del PIT de cada área); :meth:`RegistroNormativo.regla_de_empresa`,
  la de una empresa en una clave que va por empresa.
* Una norma con recursos de reconsideración los lleva en ``impugnada``: por recurrente, su nombre literal, su RUC si
  se conoce, si es empresa de la norma o tercero, los conceptos que impugna (cada uno con su cita y con lo que
  ``afecta``), la fuente y su estado. El recurso no suspende la norma (art. 216.1 del TUO de la LPAG): sigue
  obligatoria, y :meth:`RegistroNormativo.avisos_de_recurso` da el aviso SOLO de lo impugnado (RN-IMP).
* :meth:`RegistroNormativo.instantanea` es la huella del registro entero; el expediente o el estudio la fija al
  empezar para que una modificatoria publicada a mitad no cambie cifras sin que nadie lo decida.

Los datos viven en JSON (``config/normativa/`` y, para el VAD, ``config/vad/``), nunca en el código (P13). Un
fichero trae ``normas`` o amplía con ``reglas`` una norma ya registrada (``amplia``): así cada anexo transcrito
va en su fichero sin repetir los datos de la norma.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

ESTADOS = ('vigente_comprobada', 'modificada', 'prepublicada', 'no_verificada', 'derogada')
#: Cómo trata el IGV una cifra monetaria. ``sin_leer``: el anexo que lo dice no se ha leído todavía.
IGV = ('incluido', 'excluido', 'sin_leer', 'no_aplica')
#: Qué es una regla para el TdR: ``obligatoria`` (debe estar), ``criterio`` (método que fija) o ``referencia``
#: (orienta, no limita). Vacío en las reglas transcritas antes de VAD-REQ, que no lo declaraban.
CARACTERES = ('obligatoria', 'criterio', 'referencia')
#: Campos descriptivos añadidos con VAD-REQ (108). Vacíos no entran en la huella: una regla o una norma sin ellos
#: conserva la huella que tenía, y un expediente fijado antes no se ve desactualizado por un cambio de código.
_REGLA_DESCRIPTIVOS = ('caracter', 'aplicacion', 'entregable', 'cita_lineas')
_NORMA_DESCRIPTIVOS = ('fecha_emision',)
ESQUEMA = 'registro_normativo_v1'
_FECHA = re.compile(r'\d{4}-\d{2}-\d{2}')
#: Estado de un recurso contra una norma. Mientras está pendiente la norma sigue obligatoria (216.1 del TUO de la LPAG).
ESTADOS_RECURSO = ('pendiente de resolución', 'resuelto')
#: ``empresa_norma``: una de las empresas de la norma (su ``empresa`` es el nombre de sus tablas); ``tercero``: no lo
#: es y no se casa con ninguna (su aviso va a toda empresa de la norma, en los conceptos que impugna).
CONDICIONES_RECURRENTE = ('empresa_norma', 'tercero')
_SHA = re.compile(r'[0-9a-f]{64}')


class RegistroError(ValueError):
    """El registro no se puede leer o la regla pedida no existe; el mensaje nombra el fichero o la clave."""


class ReglaAmbigua(RegistroError):
    """Varias normas vigentes a la vez traen la clave y la más reciente no las modifica a todas: elegir una ocultaría
    las demás (RN-AMB, 107:RF-7). El mensaje nombra las normas y dice qué usar: ``reglas_vigentes`` o
    ``regla_de_empresa``."""


@dataclass(frozen=True)
class Regla:
    clave: str
    valor: Any
    unidad: str = ''
    articulo_o_anexo: str = ''
    pagina: str = ''
    cita_literal: str = ''
    #: Líneas de la copia local de texto en que se lee la cita («1981-1990»).
    lineas: str = ''
    moneda: str | None = None
    igv: str = 'no_aplica'
    #: Cómo se lee la cita cuando el texto no da una fórmula cerrada; vacío si es literal.
    interpretacion: str = ''
    #: Uno de :data:`CARACTERES`, o vacío si la transcripción no lo declara.
    caracter: str = ''
    #: Qué tiene que comprobar el conversor con la regla.
    aplicacion: str = ''
    #: Entregable del TdR al que pertenece («V11», «V12»…).
    entregable: str = ''
    #: En un cuadro, las líneas de su introducción y título, que son la cita; ``lineas`` abarca el cuadro entero.
    cita_lineas: str = ''
    #: Lo que queda por comprobar de la regla (``descripcion`` y, si se sabe, ``id``, ``responsable`` y ``fecha``):
    #: quien la usa lo dice en un aviso (aclaración de 107:RF-8). Vacío si no queda nada pendiente.
    pendientes: tuple[Mapping[str, str], ...] = ()
    #: La comprobación de que la regla sigue vigente: ``fecha``, ``resultado``, ``responsable`` y sus ``fuentes``
    #: (cada una con ``documento`` y ``url``; si las tiene, ``sha256``, ``consolidado_hasta`` y ``cita``). ``None`` si
    #: no se ha hecho (aclaración de 107:RF-8).
    verificacion: Mapping[str, Any] | None = None

    @property
    def citada(self) -> bool:
        """Una regla sin cita literal, o sin página ni líneas, no se puede revisar: no es obligatoria."""
        return bool(self.cita_literal.strip()) and bool(self.pagina.strip() or self.lineas.strip())


@dataclass(frozen=True)
class Norma:
    acto: str
    titulo: str
    estado_juridico: str
    url: str = ''
    #: Fecha que firma la resolución («Lima, …»); la publicación en El Peruano puede ser posterior.
    fecha_emision: str = ''
    fecha_publicacion: str = ''
    fecha_consulta: str = ''
    sha256: str = ''
    #: Huella de la copia de texto en que se cuentan las líneas de las citas.
    sha256_texto: str = ''
    fichero_local: str = ''
    version: str = ''
    vigencia_desde: str = ''
    #: El ÚLTIMO día de vigencia, incluido (RN-VIG).
    vigencia_hasta: str = ''
    #: Por qué termina ahí si la norma no lo dice: «fin deducido: …», con su cita (orden de 28). Vacío = lo dice ella.
    vigencia_hasta_motivo: str = ''
    #: Si no está vacío, la norma es SOLO DE REFERENCIA, por ese motivo: aunque esté vigente no obliga (p. ej. una
    #: tabla superada que se conserva para comparar; VAD-FE26, orden de 28).
    solo_referencia: str = ''
    modifica: tuple[str, ...] = ()
    modificada_por: tuple[str, ...] = ()
    nota: str = ''
    reglas: tuple[Regla, ...] = ()
    #: Recursos de reconsideración contra la norma, uno por recurrente (RN-IMP); vacío si no hay ninguno.
    impugnada: tuple[Mapping[str, Any], ...] = ()

    def vigente_en(self, fecha: str | None) -> bool:
        """De ``vigencia_desde`` a ``vigencia_hasta``, los dos días incluidos; de un instante cuenta su fecha."""
        if not fecha:
            return True
        dia = str(fecha)[:10]
        return ((not self.vigencia_desde or self.vigencia_desde <= dia)
                and (not self.vigencia_hasta or dia <= self.vigencia_hasta))

    def obligatoria_en(self, fecha: str | None) -> bool:
        """Solo obliga la norma comprobada, o la modificada en su versión vigente (107:RF-8); nunca la que es solo de
        referencia."""
        if self.solo_referencia:
            return False
        if self.estado_juridico == 'vigente_comprobada':
            return self.vigente_en(fecha)
        return self.estado_juridico == 'modificada' and bool(self.vigencia_desde) and self.vigente_en(fecha)


@dataclass(frozen=True)
class AvisoRecurso:
    """Un concepto impugnado que usa quien consulta, o un recurso de alcance no determinado (``concepto`` vacío)."""

    acto: str
    recurrente: str
    ruc: str
    condicion: str
    concepto: str
    cita: str
    afecta_a: tuple[str, ...]
    estado: str

    def texto(self) -> str:
        if not self.concepto:
            return (f'recurso de {self.recurrente} con alcance no determinado ({self.estado}) contra {self.acto}: '
                    f'{self.cita}')
        quien = self.recurrente + (f' (RUC {self.ruc})' if self.ruc else '') + (
            ', tercero' if self.condicion == 'tercero' else '')
        return (f'recurso de reconsideración de {quien} contra {self.acto} ({self.estado}): impugna '
                f'«{self.concepto}» ({self.cita}); afecta a: {", ".join(self.afecta_a)}')


@dataclass(frozen=True)
class ReglaVigente:
    """Una regla tal como la ve quien la usa: con su norma, su estado y si obliga."""

    regla: Regla
    norma: Norma
    obligatoria: bool

    @property
    def estado(self) -> str:
        return self.norma.estado_juridico

    def huella(self) -> str:
        """Cambia si cambia la regla, el estado de su norma o la versión: lo que deja un estudio desactualizado."""
        datos = {'regla': _sin_vacios(asdict(self.regla), _REGLA_DESCRIPTIVOS), 'acto': self.norma.acto, 'estado': self.norma.estado_juridico,
                 'version': self.norma.version, 'sha256': self.norma.sha256}
        return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
                              .encode('utf-8')).hexdigest()


def _sin_vacios(datos: dict[str, Any], campos: Iterable[str]) -> dict[str, Any]:
    """``datos`` sin los ``campos`` descriptivos que vienen vacíos (ver :data:`_REGLA_DESCRIPTIVOS`)."""
    return {k: v for k, v in datos.items() if not (k in campos and v == '')}


def _norma_para_huella(norma: Norma) -> dict[str, Any]:
    datos = _sin_vacios(asdict(norma), _NORMA_DESCRIPTIVOS)
    datos['reglas'] = [_sin_vacios(r, _REGLA_DESCRIPTIVOS) for r in datos['reglas']]
    return datos


def _regla(datos: Mapping[str, Any], origen: str) -> Regla:
    if not isinstance(datos, Mapping) or not str(datos.get('clave') or '').strip() or 'valor' not in datos:
        raise RegistroError(f'{origen}: cada regla necesita «clave» y «valor»: {datos!r}')
    desconocidos = set(datos) - set(Regla.__dataclass_fields__)
    if desconocidos:
        raise RegistroError(f'{origen}: la regla {datos["clave"]} trae campos desconocidos {sorted(desconocidos)}')
    campos = dict(datos)
    if 'pendientes' in campos:
        campos['pendientes'] = _pendientes(campos['pendientes'], f'{origen}: la regla {datos["clave"]}')
    if campos.get('verificacion') is not None:
        _verificacion(campos['verificacion'], f'{origen}: la regla {datos["clave"]}')
    regla = Regla(**campos)
    if regla.igv not in IGV:
        raise RegistroError(f'{origen}: la regla {regla.clave} tiene igv={regla.igv!r}; los válidos son {IGV}')
    if regla.caracter and regla.caracter not in CARACTERES:
        raise RegistroError(f'{origen}: la regla {regla.clave} tiene caracter={regla.caracter!r}; los válidos son '
                            f'{CARACTERES}')
    _comprobar_factores(regla, origen)
    return regla


_CAMPOS_PENDIENTE = ('id', 'descripcion', 'responsable', 'fecha')


def _pendientes(lista: Any, donde: str) -> tuple[dict[str, str], ...]:
    """Cada pendiente, un objeto con su ``descripcion``: un pendiente sin decir qué falta no se puede cerrar."""
    if not isinstance(lista, (list, tuple)):
        raise RegistroError(f'{donde}: «pendientes» tiene que ser una lista, no {lista!r}')
    salida = []
    for p in lista:
        if not isinstance(p, Mapping) or not str(p.get('descripcion') or '').strip():
            raise RegistroError(f'{donde}: cada pendiente necesita su «descripcion»: {p!r}')
        desconocidos = sorted(set(p) - set(_CAMPOS_PENDIENTE))
        if desconocidos:
            raise RegistroError(f'{donde}: el pendiente trae campos desconocidos {desconocidos}')
        salida.append({k: str(p[k]) for k in _CAMPOS_PENDIENTE if k in p})
    return tuple(salida)


def _verificacion(v: Any, donde: str) -> None:
    """Una verificación dice cuándo se hizo, qué resultó y con qué fuentes: sin eso no se puede revisar."""
    if not isinstance(v, Mapping):
        raise RegistroError(f'{donde}: «verificacion» tiene que ser un objeto, no {v!r}')
    for clave in ('fecha', 'resultado'):
        if not str(v.get(clave) or '').strip():
            raise RegistroError(f'{donde}: la verificación necesita «{clave}»')
    if not _FECHA.fullmatch(str(v['fecha'])):
        raise RegistroError(f'{donde}: la fecha de la verificación tiene que ser AAAA-MM-DD, no {v["fecha"]!r}')
    fuentes = v.get('fuentes')
    if not isinstance(fuentes, (list, tuple)) or not fuentes or any(
            not isinstance(f, Mapping) or not str(f.get('documento') or '').strip()
            or not str(f.get('url') or '').strip() for f in fuentes):
        raise RegistroError(f'{donde}: la verificación necesita sus «fuentes», cada una con «documento» y «url»')


#: |FE − 1/(1−p)| admisible: el FE viene con 4 decimales y el porcentaje con 2 (redondeo de los dos).
TOLERANCIA_FE = 1.5e-4


def _comprobar_factores(regla: Regla, origen: str) -> None:
    """Toda tabla de factores de expansión (``empresas`` → ``fe``, y ``porcentaje`` si lo trae) se comprueba fila a
    fila: cada FE ≥ 1 y, si hay porcentaje p, FE = 1/(1−p) dentro del redondeo. Atrapa la tabla desplazada al
    transcribir (etiqueta de una fila con los valores de la siguiente) y el porcentaje mal leído; falla nombrándolos."""
    valor = regla.valor
    if not isinstance(valor, Mapping) or not isinstance(valor.get('empresas'), Mapping):
        return
    for empresa, fila in valor['empresas'].items():
        if not isinstance(fila, Mapping) or not isinstance(fila.get('fe'), Mapping):
            continue
        porcentajes = fila.get('porcentaje') or {}
        for clave, fe in fila['fe'].items():
            donde = f'{origen}: {regla.clave}, {empresa}, fila {clave}'
            if isinstance(fe, bool) or not isinstance(fe, (int, float)) or fe < 1:
                raise RegistroError(f'{donde}: el factor de expansión {fe!r} tiene que ser un número ≥ 1')
            if clave not in porcentajes:
                continue
            p = porcentajes[clave]
            if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p < 100:
                raise RegistroError(f'{donde}: el porcentaje {p!r} tiene que estar entre 0 y 100')
            esperado = 1 / (1 - p / 100)
            if abs(fe - esperado) > TOLERANCIA_FE:
                raise RegistroError(f'{donde}: FE {fe} no es 1/(1−{p} %) = {esperado:.4f}; ¿tabla desplazada o '
                                    'porcentaje mal leído?')


def _norma(datos: Mapping[str, Any], origen: str) -> Norma:
    for clave in ('acto', 'titulo', 'estado_juridico'):
        if not str(datos.get(clave) or '').strip():
            raise RegistroError(f'{origen}: la norma necesita «{clave}»: {datos.get("acto")!r}')
    if datos['estado_juridico'] not in ESTADOS:
        raise RegistroError(f'{origen}: {datos["acto"]} tiene estado {datos["estado_juridico"]!r}; '
                            f'los válidos son {ESTADOS}')
    for clave in ('fecha_emision', 'fecha_publicacion', 'fecha_consulta', 'vigencia_desde', 'vigencia_hasta'):
        valor = datos.get(clave) or ''
        if valor and not _FECHA.fullmatch(valor):
            raise RegistroError(f'{origen}: {datos["acto"]}.{clave} tiene que ser AAAA-MM-DD, no {valor!r}')
    emision, publicacion = datos.get('fecha_emision') or '', datos.get('fecha_publicacion') or ''
    if emision and publicacion and emision > publicacion:
        raise RegistroError(f'{origen}: {datos["acto"]} tiene fecha_emision {emision} posterior a su '
                            f'fecha_publicacion {publicacion}')
    if datos['estado_juridico'] == 'vigente_comprobada' and not datos.get('sha256'):
        raise RegistroError(f'{origen}: {datos["acto"]} no puede estar «vigente_comprobada» sin la huella del '
                            'texto leído; sin huella es «no_verificada»')
    campos = {k: v for k, v in datos.items() if k in Norma.__dataclass_fields__ and k != 'reglas'}
    for k in ('modifica', 'modificada_por'):
        campos[k] = tuple(campos.get(k) or ())
    reglas = tuple(_regla(r, f'{origen}:{datos["acto"]}') for r in datos.get('reglas') or ())
    campos['impugnada'] = tuple(_recurso(r, f'{origen}:{datos["acto"]}') for r in campos.get('impugnada') or ())
    return Norma(**campos, reglas=reglas)


def _recurso(datos: Any, origen: str) -> Mapping[str, Any]:
    """Un recurrente de ``impugnada``, comprobado: lo que no se puede revisar no entra (RN-IMP)."""
    if not isinstance(datos, Mapping) or not str(datos.get('recurrente') or '').strip():
        raise RegistroError(f'{origen}: cada recurso de «impugnada» necesita «recurrente»: {datos!r}')
    quien = f'{origen}: el recurso de {datos["recurrente"]}'
    if datos.get('condicion') not in CONDICIONES_RECURRENTE:
        raise RegistroError(f'{quien} tiene condicion={datos.get("condicion")!r}; las válidas son '
                            f'{CONDICIONES_RECURRENTE}')
    if (datos['condicion'] == 'empresa_norma') != bool(str(datos.get('empresa') or '').strip()):
        raise RegistroError(f'{quien}: «empresa» (el nombre en las tablas de la norma) va solo y siempre con '
                            '«empresa_norma»; a un tercero no se le casa con ninguna empresa')
    if datos.get('estado') not in ESTADOS_RECURSO:
        raise RegistroError(f'{quien} tiene estado {datos.get("estado")!r}; los válidos son {ESTADOS_RECURSO}')
    fuente = datos.get('fuente')
    if (not isinstance(fuente, Mapping) or not str(fuente.get('documento') or '').strip()
            or not _SHA.fullmatch(str(fuente.get('sha256') or ''))):
        raise RegistroError(f'{quien} necesita «fuente» con «documento» y su «sha256»')
    conceptos = datos.get('conceptos') or ()
    for c in conceptos:
        afecta = c.get('afecta') if isinstance(c, Mapping) else None
        if (not isinstance(afecta, list) or not afecta or not all(isinstance(a, str) and a for a in afecta)
                or not str(c.get('concepto') or '').strip() or not str(c.get('cita') or '').strip()):
            raise RegistroError(f'{quien}: cada concepto necesita «concepto», «cita» y «afecta» (lista no vacía): '
                                f'{c!r}')
    sin_alcance = datos.get('alcance_no_determinado') or ()
    for e in sin_alcance:
        if (not isinstance(e, Mapping) or not str(e.get('escrito') or '').strip()
                or not str(e.get('motivo') or '').strip()):
            raise RegistroError(f'{quien}: cada alcance no determinado necesita «escrito» y «motivo»: {e!r}')
    if not conceptos and not sin_alcance:
        raise RegistroError(f'{quien} no dice qué impugna: o «conceptos» o «alcance_no_determinado»')
    return dict(datos)


def _clave_uso(texto: str) -> str:
    return ' '.join(str(texto).split()).casefold()


def _afecta_a(afecta: str, usos: set[str], claves: set[str]) -> bool:
    """Si lo usado toca la entrada ``afecta``: ella misma o, si es ``<clave>.<fila>`` de una regla de la norma, la
    regla entera."""
    if _clave_uso(afecta) in usos:
        return True
    base, _, fila = afecta.rpartition('.')
    return bool(fila) and base in claves and _clave_uso(base) in usos


def _dia(fecha: str | date | None) -> str | None:
    return fecha.isoformat() if isinstance(fecha, date) else fecha


def _empresas(regla: Regla) -> frozenset[str] | None:
    """Las empresas de una regla que va por empresa (``valor['empresas']``); None si no va por empresa."""
    valor = regla.valor
    if isinstance(valor, Mapping) and isinstance(valor.get('empresas'), Mapping):
        return frozenset(valor['empresas'])
    return None


def _se_solapan(a: Norma, b: Norma) -> bool:
    """Si las vigencias de las dos normas tienen algún día en común (una fecha vacía es un extremo abierto)."""
    return ((not a.vigencia_hasta or not b.vigencia_desde or b.vigencia_desde <= a.vigencia_hasta)
            and (not b.vigencia_hasta or not a.vigencia_desde or a.vigencia_desde <= b.vigencia_hasta))


def _mas_reciente(par: tuple[Norma, Regla]) -> tuple[str, str]:
    return par[0].vigencia_desde, par[0].acto


@dataclass
class RegistroNormativo:
    normas: dict[str, Norma] = field(default_factory=dict)

    def norma(self, acto: str) -> Norma:
        try:
            return self.normas[acto]
        except KeyError:
            raise RegistroError(f'la norma {acto!r} no está en el registro normativo') from None

    def _candidatas(self, clave: str, dia: str | None) -> list[tuple[Norma, Regla]]:
        return [(n, r) for n in self.normas.values() for r in n.reglas if r.clave == clave and n.vigente_en(dia)]

    def _modificadas_por(self, acto: str) -> set[str]:
        """Los actos que ``acto`` modifica, directa o encadenadamente; vale el enlace escrito en cualquiera de los dos
        lados (``modifica`` de la que modifica o ``modificada_por`` de la modificada)."""
        hijos: dict[str, set[str]] = {}
        for n in self.normas.values():
            for m in n.modifica:
                hijos.setdefault(n.acto, set()).add(m)
            for m in n.modificada_por:
                hijos.setdefault(m, set()).add(n.acto)
        vistos: set[str] = set()
        pila = [acto]
        while pila:
            for m in hijos.get(pila.pop(), ()):
                if m not in vistos:
                    vistos.add(m)
                    pila.append(m)
        vistos.discard(acto)
        return vistos

    def _no_encadenadas(self, candidatas: list[tuple[Norma, Regla]]) -> tuple[tuple[Norma, Regla], list]:
        """(la más reciente, las vigentes a la vez que ella que esa no modifica ni directa ni encadenadamente)."""
        norma, regla = max(candidatas, key=_mas_reciente)
        cubiertas = self._modificadas_por(norma.acto)
        resto = [(n, r) for n, r in candidatas
                 if n.acto != norma.acto and n.acto not in cubiertas and _se_solapan(n, norma)]
        return (norma, regla), resto

    def regla(self, clave: str, fecha: str | date | None = None) -> ReglaVigente:
        """La regla ``clave`` vigente en ``fecha``: la de vigencia más reciente si modifica a las demás.

        Si varias normas vigentes a la vez traen la clave y la más reciente no modifica, directa ni encadenadamente,
        a todas las demás, son normas que se SUMAN: devolver una ocultaría las otras en silencio (RN-AMB: las
        modificaciones del PIT por área). Lanza :class:`ReglaAmbigua`, que las nombra y remite a
        :meth:`reglas_vigentes`. Sin fecha cuentan todas las del registro, salvo las que ya no rigen cuando empieza la
        más reciente (una RM de horas punta sucede a la anterior sin solaparse).

        Una clave que va por empresa (``valor['empresas']``) es el mismo caso: si la más reciente no trae a todas las
        empresas de las otras, elegirla dejaría sin tabla a las de la otra fijación (VAD-FE26: el grupo 2 de la
        223-2023 frente al grupo 1 de la 185-2026), y el error pide :meth:`regla_de_empresa`. Si las trae a todas,
        cada empresa tiene su fijación más reciente en ella y se devuelve, igual que lo haría ``regla_de_empresa``.
        """
        dia = _dia(fecha)
        candidatas = self._candidatas(clave, dia)
        if not candidatas:
            raise RegistroError(f'ninguna norma del registro trae la regla {clave!r}'
                                + (f' vigente el {dia}' if dia else ''))
        (norma, regla), resto = self._no_encadenadas(candidatas)
        empresas = _empresas(regla)
        if empresas is not None or any(_empresas(r) is not None for _, r in resto):
            sin_cubrir = [(n, r) for n, r in resto
                          if empresas is None or _empresas(r) is None or not _empresas(r) <= empresas]
            if sin_cubrir:
                actos = ', '.join(sorted(n.acto for n, _ in [(norma, regla), *sin_cubrir]))
                raise ReglaAmbigua(f'la clave {clave!r} va por empresa y {actos} la traen'
                                   + (f' el {dia}' if dia else '')
                                   + ' para empresas distintas; use regla_de_empresa(clave, empresa, fecha)')
        elif resto:
            actos = ', '.join(sorted(n.acto for n, _ in [(norma, regla), *resto]))
            raise ReglaAmbigua(f'la clave {clave!r} es ambigua' + (f' el {dia}' if dia else '')
                               + f': la traen {actos}, vigentes a la vez, y {norma.acto} no modifica a las demás; '
                               'use reglas_vigentes(clave, fecha) para tenerlas todas, o regla_de_empresa(clave, '
                               'empresa, fecha) si va por empresa')
        return ReglaVigente(regla, norma, norma.obligatoria_en(dia) and regla.citada)

    def reglas_vigentes(self, clave: str, fecha: str | date | None = None) -> tuple[ReglaVigente, ...]:
        """TODAS las reglas ``clave`` vigentes en ``fecha``, cada una con su norma, ordenadas por ``vigencia_desde``
        (y acto), sin las de normas que otra vigente modifica, directa o encadenadamente (RN-AMB, 107:RF-7, 107:RF-8).
        Es la consulta de las normas que se suman, como las modificaciones del PIT de cada área. Sin fecha, todas las
        del registro. Si ninguna trae la clave, RegistroError que la nombra."""
        dia = _dia(fecha)
        candidatas = self._candidatas(clave, dia)
        if not candidatas:
            raise RegistroError(f'ninguna norma del registro trae la regla {clave!r}'
                                + (f' vigente el {dia}' if dia else ''))
        modificadas = {m for n, _ in candidatas for m in self._modificadas_por(n.acto)}
        return tuple(ReglaVigente(r, n, n.obligatoria_en(dia) and r.citada)
                     for n, r in sorted(candidatas, key=_mas_reciente) if n.acto not in modificadas)

    def empresas_de(self, clave: str) -> tuple[str, ...]:
        """Las empresas que trae ``clave`` en cualquiera de sus normas; vacío si la clave no va por empresa."""
        return tuple(sorted({e for n in self.normas.values() for r in n.reglas if r.clave == clave
                             for e in (_empresas(r) or ())}))

    def regla_de_empresa(self, clave: str, empresa: str, fecha: str | date | None = None) -> ReglaVigente:
        """La regla ``clave`` vigente en ``fecha`` cuya tabla ``valor['empresas']`` trae a ``empresa`` (107:RF-7,
        108:RF-8, 108:RF-13). Si varias la traen, la de vigencia más reciente; si ninguna, RegistroError que nombra
        la empresa, la clave y la fecha. A qué fijación pertenece cada empresa lo dice el registro, nunca el código."""
        dia = _dia(fecha)
        candidatas = [(n, r) for n, r in self._candidatas(clave, dia) if empresa in (_empresas(r) or ())]
        if not candidatas:
            raise RegistroError(f'ninguna norma del registro trae la regla {clave!r} para la empresa {empresa!r}'
                                + (f' vigente el {dia}' if dia else ''))
        norma, regla = max(candidatas, key=_mas_reciente)
        return ReglaVigente(regla, norma, norma.obligatoria_en(dia) and regla.citada)

    def avisos_de_recurso(self, empresa: str, usados: Iterable[str],
                          fecha: str | date | None = None) -> tuple[AvisoRecurso, ...]:
        """Los avisos de recurso que tocan a ``empresa`` en lo que ``usados`` nombra (RN-IMP, 107:RF-8, 108:RF-9).

        ``usados`` son las claves del registro y los conceptos (tablas o cálculos) que usa quien consulta; un concepto
        impugnado da aviso solo si alguna de sus entradas ``afecta`` está entre ellos (sin distinguir mayúsculas ni
        espacios). Una entrada ``<clave>.<fila>`` (``vad.perdidas.factores_expansion.PPMT``) es una fila de una regla de
        la norma: la avisa quien usa esa fila o la regla entera, y no quien usa otra fila (el FE de BT). Así una tabla o
        una fila que el recurso no impugna no lleva aviso aunque la empresa haya recurrido. El
        recurso de una empresa de la norma toca solo a esa empresa; el de un tercero, a toda empresa de las tablas de
        la norma. Un escrito de alcance no determinado da el aviso genérico de su recurrente, como hueco nombrado. La
        norma no deja de obligar por esto: el recurso no suspende su ejecución."""
        dia = _dia(fecha)
        usos = {_clave_uso(u) for u in usados}
        avisos: list[AvisoRecurso] = []
        for norma in sorted(self.normas.values(), key=lambda n: n.acto):
            if not norma.impugnada or not norma.vigente_en(dia):
                continue
            empresas = {e for r in norma.reglas for e in (_empresas(r) or ())}
            claves = {r.clave for r in norma.reglas}
            for rec in norma.impugnada:
                if rec['condicion'] == 'empresa_norma' and rec['empresa'] != empresa:
                    continue
                if rec['condicion'] == 'tercero' and empresas and empresa not in empresas:
                    continue
                datos = (norma.acto, rec['recurrente'], str(rec.get('ruc') or ''), rec['condicion'])
                for c in rec.get('conceptos') or ():
                    afectados = tuple(a for a in c['afecta'] if _afecta_a(a, usos, claves))
                    if afectados:
                        avisos.append(AvisoRecurso(*datos, c['concepto'], c['cita'], afectados, rec['estado']))
                for e in rec.get('alcance_no_determinado') or ():
                    avisos.append(AvisoRecurso(*datos, '', f'{e["escrito"]}: {e["motivo"]}', (), rec['estado']))
        return tuple(avisos)

    def instantanea(self) -> str:
        """Huella del registro entero, independiente del orden de los ficheros."""
        datos = {a: _norma_para_huella(n) for a, n in sorted(self.normas.items())}
        return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
                              .encode('utf-8')).hexdigest()


# ------------------------------------------------------------------------------------ remisiones «mismas_que»
#: Remisiones encadenadas que se siguen como máximo: una cadena más larga es un error de transcripción.
_MAX_REMISIONES = 4


@dataclass(frozen=True)
class ReglaRemitida:
    """Una regla tal como la usa quien lee su valor (el VAD, el PIDE o el PIT): la pedida (``remision``) y la que da
    su valor (``principal``; la misma si no remite a otra)."""

    remision: ReglaVigente
    principal: ReglaVigente

    @property
    def valor(self) -> Any:
        return self.principal.regla.valor

    @property
    def obligatoria(self) -> bool:
        """Obliga solo si obligan la remisión (su cita) y la principal (el valor)."""
        return self.remision.obligatoria and self.principal.obligatoria

    def huella(self) -> str:
        """La de la regla o, si remite, la de la remisión junto con la de la principal: cambia si cambia cualquiera."""
        if self.principal is self.remision:
            return self.remision.huella()
        return hashlib.sha256(f'{self.remision.huella()}>{self.principal.huella()}'.encode('ascii')).hexdigest()


def remite_a(valor: Any) -> str | None:
    """La clave a la que remite un valor ``{"mismas_que": "<clave>", …}``; None si es un valor propio.

    Remite un ``mismas_que`` que es UNA clave (texto). Los demás datos que lo acompañen son de la remisión, no del valor
    (la vida útil de ``vad.anexo5.tasa_i``) y se leen en :attr:`ReglaRemitida.remision`. Una LISTA de claves
    (las equivalencias de las fórmulas de pérdidas) es informativa: es el valor propio de la regla y no remite."""
    if isinstance(valor, Mapping) and isinstance(valor.get('mismas_que'), str):
        return valor['mismas_que'].strip()
    return None


def regla_remitida(registro: RegistroNormativo, clave: str, fecha: str | None = None) -> ReglaRemitida:
    """La regla ``clave`` vigente en ``fecha`` y la que da su valor, siguiendo sus remisiones ``mismas_que`` (UNA-TASA,
    107:RF-7, 108:RF-9). Es el ÚNICO sitio que resuelve una remisión: lo usan el PIDE del VAD (``vad.pide_vad``), el
    aVNR del SER (``vad.costos``), el contraste del capital de trabajo (``vad.coym``) y la tasa «i» del Anexo 5
    (``vad.modelo_urbano``, que remite a ``vad.tasa_actualizacion``, que a su vez remite a ``pit.tasa_actualizacion``). La principal se busca en la misma fecha. Una remisión vacía, a una clave que no está, circular
    o más larga que :data:`_MAX_REMISIONES` lanza :class:`RegistroError`, que la nombra."""
    pedida = registro.regla(clave, fecha)
    actual, vistas = pedida, [clave]
    while (destino := remite_a(actual.regla.valor)) is not None:
        if not destino or destino in vistas or len(vistas) > _MAX_REMISIONES:
            raise RegistroError(f'la regla {clave!r} remite en cadena a {" → ".join([*vistas, destino])}: '
                                'remisión vacía, circular o demasiado larga')
        try:
            actual = registro.regla(destino, fecha)
        except RegistroError as exc:
            raise RegistroError(f'la regla {clave!r} remite a {destino!r}, que no está: {exc}') from exc
        vistas.append(destino)
    return ReglaRemitida(pedida, actual)


def _ficheros(rutas: Iterable[Path | str]) -> list[tuple[Path, bool]]:
    """(fichero, si vino de una carpeta). En una carpeta conviven otras transcripciones (formatos del anexo 2,
    estructura del anexo 9) que no son normas: se saltan; un fichero nombrado que no es del registro, no."""
    out: list[tuple[Path, bool]] = []
    for ruta in map(Path, rutas):
        if ruta.is_dir():
            out.extend((f, True) for f in sorted(ruta.glob('*.json')))
        elif ruta.is_file():
            out.append((ruta, False))
        else:
            raise RegistroError(f'no existe el fichero o la carpeta del registro normativo: {ruta}')
    return out


def cargar_registro(*rutas: Path | str) -> RegistroNormativo:
    """Lee los ficheros (o las carpetas de ficheros) del registro. Primero las normas, luego las ampliaciones."""
    leidos = []
    for f, de_carpeta in _ficheros(rutas):
        try:
            datos = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistroError(f'{f}: no se puede leer ({exc})') from exc
        if not isinstance(datos, dict) or datos.get('esquema') != ESQUEMA:
            if de_carpeta:
                continue
            raise RegistroError(f'{f}: no es un fichero del registro ({ESQUEMA})')
        leidos.append((f, datos))
    registro = RegistroNormativo()
    for f, datos in leidos:
        for n in datos.get('normas') or ():
            norma = _norma(n, str(f))
            if norma.acto in registro.normas:
                raise RegistroError(f'{f}: la norma {norma.acto} está registrada dos veces')
            registro.normas[norma.acto] = norma
    for f, datos in leidos:
        if not datos.get('amplia'):
            continue
        base = registro.norma(datos['amplia'])
        nuevas = tuple(_regla(r, f'{f}:{base.acto}') for r in datos.get('reglas') or ())
        registro.normas[base.acto] = Norma(**{**{k: getattr(base, k) for k in Norma.__dataclass_fields__},
                                              'reglas': base.reglas + nuevas})
    for norma in registro.normas.values():
        claves = [r.clave for r in norma.reglas]
        repetidas = sorted({c for c in claves if claves.count(c) > 1})
        if repetidas:
            raise RegistroError(f'{norma.acto}: reglas repetidas {repetidas}')
    return registro
