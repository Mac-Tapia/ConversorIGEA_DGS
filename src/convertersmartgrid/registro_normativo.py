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
  usan como referencia y quien las usa lo dice (107:RF-8, 108:RF-10).
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
ESQUEMA = 'registro_normativo_v1'
_FECHA = re.compile(r'\d{4}-\d{2}-\d{2}')


class RegistroError(ValueError):
    """El registro no se puede leer o la regla pedida no existe; el mensaje nombra el fichero o la clave."""


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
    fecha_publicacion: str = ''
    fecha_consulta: str = ''
    sha256: str = ''
    #: Huella de la copia de texto en que se cuentan las líneas de las citas.
    sha256_texto: str = ''
    fichero_local: str = ''
    version: str = ''
    vigencia_desde: str = ''
    vigencia_hasta: str = ''
    modifica: tuple[str, ...] = ()
    modificada_por: tuple[str, ...] = ()
    nota: str = ''
    reglas: tuple[Regla, ...] = ()

    def vigente_en(self, fecha: str | None) -> bool:
        if not fecha:
            return True
        return ((not self.vigencia_desde or self.vigencia_desde <= fecha)
                and (not self.vigencia_hasta or fecha < self.vigencia_hasta))

    def obligatoria_en(self, fecha: str | None) -> bool:
        """Solo obliga la norma comprobada, o la modificada en su versión vigente (107:RF-8)."""
        if self.estado_juridico == 'vigente_comprobada':
            return self.vigente_en(fecha)
        return self.estado_juridico == 'modificada' and bool(self.vigencia_desde) and self.vigente_en(fecha)


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
        datos = {'regla': asdict(self.regla), 'acto': self.norma.acto, 'estado': self.norma.estado_juridico,
                 'version': self.norma.version, 'sha256': self.norma.sha256}
        return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
                              .encode('utf-8')).hexdigest()


def _regla(datos: Mapping[str, Any], origen: str) -> Regla:
    if not isinstance(datos, Mapping) or not str(datos.get('clave') or '').strip() or 'valor' not in datos:
        raise RegistroError(f'{origen}: cada regla necesita «clave» y «valor»: {datos!r}')
    desconocidos = set(datos) - set(Regla.__dataclass_fields__)
    if desconocidos:
        raise RegistroError(f'{origen}: la regla {datos["clave"]} trae campos desconocidos {sorted(desconocidos)}')
    regla = Regla(**{k: v for k, v in datos.items()})
    if regla.igv not in IGV:
        raise RegistroError(f'{origen}: la regla {regla.clave} tiene igv={regla.igv!r}; los válidos son {IGV}')
    _comprobar_factores(regla, origen)
    return regla


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
    for clave in ('fecha_publicacion', 'fecha_consulta', 'vigencia_desde', 'vigencia_hasta'):
        valor = datos.get(clave) or ''
        if valor and not _FECHA.fullmatch(valor):
            raise RegistroError(f'{origen}: {datos["acto"]}.{clave} tiene que ser AAAA-MM-DD, no {valor!r}')
    if datos['estado_juridico'] == 'vigente_comprobada' and not datos.get('sha256'):
        raise RegistroError(f'{origen}: {datos["acto"]} no puede estar «vigente_comprobada» sin la huella del '
                            'texto leído; sin huella es «no_verificada»')
    campos = {k: v for k, v in datos.items() if k in Norma.__dataclass_fields__ and k != 'reglas'}
    for k in ('modifica', 'modificada_por'):
        campos[k] = tuple(campos.get(k) or ())
    reglas = tuple(_regla(r, f'{origen}:{datos["acto"]}') for r in datos.get('reglas') or ())
    return Norma(**campos, reglas=reglas)


@dataclass
class RegistroNormativo:
    normas: dict[str, Norma] = field(default_factory=dict)

    def norma(self, acto: str) -> Norma:
        try:
            return self.normas[acto]
        except KeyError:
            raise RegistroError(f'la norma {acto!r} no está en el registro normativo') from None

    def regla(self, clave: str, fecha: str | date | None = None) -> ReglaVigente:
        """La regla ``clave`` vigente en ``fecha`` (la de vigencia más reciente si hay varias)."""
        dia = fecha.isoformat() if isinstance(fecha, date) else fecha
        candidatas = [(n, r) for n in self.normas.values() for r in n.reglas
                      if r.clave == clave and n.vigente_en(dia)]
        if not candidatas:
            raise RegistroError(f'ninguna norma del registro trae la regla {clave!r}'
                                + (f' vigente el {dia}' if dia else ''))
        norma, regla = max(candidatas, key=lambda par: (par[0].vigencia_desde, par[0].acto))
        return ReglaVigente(regla, norma, norma.obligatoria_en(dia) and regla.citada)

    def instantanea(self) -> str:
        """Huella del registro entero, independiente del orden de los ficheros."""
        datos = {a: asdict(n) for a, n in sorted(self.normas.items())}
        return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
                              .encode('utf-8')).hexdigest()


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
