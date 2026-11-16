"""Observaciones del regulador al expediente del PIT, con su respuesta y lo que afectan (107:RF-10).

Cada observación nombra un elemento de la red, un caso del diagnóstico o una celda de un cuadro, y queda enlazada con
la traza de esa celda en el expediente: quien responde ve de dónde salió la cifra observada. Una referencia que el
expediente no conoce es un error, no una observación suelta, porque una respuesta sin su objeto no se puede revisar.
El fichero se escribe con claves ordenadas, para que el mismo registro dé el mismo fichero (determinismo).

La forma del documento de respuestas (``documento_absolucion``) es la que Osinergmin pide en el oficio de
observaciones (IT 438-2024-GRT, sección 4, pág. 25): observaciones generales y específicas, las generales primero, y
las respuestas «con la misma organización y secuencia» en que se formularon, cada una con el lugar corregido del
Estudio. Cada observación deja además el sitio de la evaluación del regulador («Análisis» y «Conclusión», como en el
Anexo A del IT 599-2026-GRT), vacío hasta que se registre.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..util import publicar_duradero  # 001:RF-5 (H14): escritura atómica y duradera, con los mismos bytes
from . import PitError

__all__ = ['AFECTA', 'CAMPOS_HUECO', 'CONCLUSIONES', 'LUGAR_NO_INDICADO', 'ORDEN_REAGRUPADO', 'TIPOS_OBSERVACION',
           'Observacion', 'absolucion', 'documento_absolucion',
           'escribir_absolucion', 'escribir_documento_absolucion', 'escribir_observaciones', 'leer_observaciones',
           'registrar']

AFECTA = ('elemento', 'caso', 'celda')
_FECHA = re.compile(r'\d{4}-\d{2}-\d{2}')
_SHA256 = re.compile(r'[0-9a-f]{64}')
#: Las dos clases de observación del oficio, en el orden en que se responden (las generales tienen jerarquía).
TIPOS_OBSERVACION = ('general', 'especifica')
_TITULOS = {'general': 'Observaciones generales', 'especifica': 'Observaciones específicas'}
#: Las conclusiones con que el regulador califica cada respuesta (IT 599-2026-GRT, Anexo A).
CONCLUSIONES = ('subsanada', 'parcialmente subsanada', 'no subsanada')
#: Lo que dice el documento sobre su orden: el del oficio, reagrupado con las generales primero.
ORDEN_REAGRUPADO = 'orden del oficio reagrupado: generales primero'
#: Lo que se escribe cuando una respuesta no cita el lugar corregido del Estudio (no se inventa).
LUGAR_NO_INDICADO = 'no indicado'
#: Los campos de cada hueco del documento, fijos para que otro documento (el expediente) los pueda leer.
CAMPOS_HUECO = ('documento', 'oficio', 'numero', 'tipo', 'falta', 'texto')


@dataclass(frozen=True)
class Observacion:
    numero: str
    fecha: str
    texto: str
    afecta: str
    referencia: str
    respuesta: str = ''
    #: La traza de la celda observada, o el elemento o el caso tal como están en el expediente.
    enlace: Mapping[str, Any] = field(default_factory=dict)


def registrar(datos: Iterable[Mapping[str, Any]], referencias: Mapping[str, Mapping[str, Any]]) -> list[Observacion]:
    """Valida cada observación contra lo que hay en el expediente (``referencias``: tipo → id → su traza o datos)."""
    out, numeros = [], set()
    for d in datos:
        numero = str(d.get('numero') or '').strip()
        origen = f'observación {numero or "sin número"}'
        if not numero:
            raise PitError(f'{origen}: cada observación lleva su número')
        if numero in numeros:
            raise PitError(f'{origen}: número repetido')
        numeros.add(numero)
        if not _FECHA.fullmatch(str(d.get('fecha') or '')):
            raise PitError(f'{origen}: la fecha tiene que ser AAAA-MM-DD, no {d.get("fecha")!r}')
        if not str(d.get('texto') or '').strip():
            raise PitError(f'{origen}: sin texto')
        afecta, ref = str(d.get('afecta') or ''), str(d.get('referencia') or '')
        if afecta not in AFECTA:
            raise PitError(f'{origen}: «afecta» tiene que ser uno de {AFECTA}, no {afecta!r}')
        conocidas = referencias.get(afecta) or {}
        if ref not in conocidas:
            raise PitError(f'{origen}: el expediente no tiene {afecta} {ref!r}; la observación no se puede enlazar')
        out.append(Observacion(numero, str(d['fecha']), str(d['texto']), afecta, ref,
                               str(d.get('respuesta') or ''), dict(conocidas[ref] or {})))
    return sorted(out, key=lambda o: (o.fecha, o.numero))


def escribir_observaciones(ruta: Path | str, observaciones: Iterable[Observacion]) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = [asdict(o) for o in observaciones]
    # En bytes: con LF como antes (newline='\n'); un str pasaría por la traducción de fin de línea de Windows.
    publicar_duradero(ruta, (json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return ruta


def leer_observaciones(ruta: Path | str, referencias: Mapping[str, Mapping[str, Any]]) -> list[Observacion]:
    datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    return registrar([{k: v for k, v in d.items() if k != 'enlace'} for d in datos], referencias)


def _huella(datos: Any) -> str:
    return hashlib.sha256(json.dumps(datos, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def absolucion(datos: Iterable[Mapping[str, Any]], antes: Mapping[str, Mapping[str, Any]],
               despues: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """El documento de absolución (aclaración de 107:RF-10): cada observación con su objeto y su respuesta, y la traza
    de lo que cambió en el expediente por ella.

    ``antes`` son las referencias del expediente observado (con ellas se validan las observaciones, como en
    ``registrar``) y ``despues`` las del expediente que responde. Por cada objeto observado se compara su traza:
    ``cambiado`` (con las dos trazas y sus huellas), ``sin_cambios`` (y se dice) o ``retirado`` (ya no está). Una
    observación sin respuesta no se absuelve: es un error que la nombra.
    """
    out = []
    for o in registrar(datos, antes):
        if not o.respuesta.strip():
            raise PitError(f'observación {o.numero}: sin respuesta no hay absolución')
        previa = dict(o.enlace)
        nueva = (despues.get(o.afecta) or {}).get(o.referencia)
        if nueva is None:
            cambio = {'estado': 'retirado', 'antes': previa, 'despues': None, 'huella_antes': _huella(previa),
                      'huella_despues': None,
                      'texto': f'{o.afecta} {o.referencia} ya no está en el expediente que responde'}
        else:
            nueva = dict(nueva)
            igual = _huella(previa) == _huella(nueva)
            cambio = {'estado': 'sin_cambios' if igual else 'cambiado', 'antes': previa, 'despues': nueva,
                      'huella_antes': _huella(previa), 'huella_despues': _huella(nueva),
                      'texto': (f'{o.afecta} {o.referencia}: sin cambios en el expediente' if igual
                                else f'{o.afecta} {o.referencia}: cambió en el expediente que responde')}
        out.append({'numero': o.numero, 'fecha': o.fecha, 'texto': o.texto, 'afecta': o.afecta,
                    'referencia': o.referencia, 'respuesta': o.respuesta, 'cambio': cambio})
    return out


def escribir_absolucion(ruta: Path | str, datos: Iterable[Mapping[str, Any]], antes: Mapping[str, Mapping[str, Any]],
                        despues: Mapping[str, Mapping[str, Any]]) -> Path:
    """La absolución en JSON con claves ordenadas: el mismo registro da el mismo fichero (determinismo)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    publicar_duradero(ruta, (json.dumps(absolucion(datos, antes, despues), ensure_ascii=False, indent=1,
                                        sort_keys=True) + '\n').encode('utf-8'))
    return ruta


def _lugar(numero: str, c: Mapping[str, Any], huellas: Mapping[str, str]) -> dict[str, Any]:
    """Un lugar corregido del Estudio: su sección, o su fichero y su celda, con la huella del fichero si se conoce."""
    origen = f'observación {numero}'
    seccion, fichero = str(c.get('seccion') or '').strip(), str(c.get('fichero') or '').strip()
    celda = str(c.get('celda') or '').strip()
    if not seccion and not fichero:
        raise PitError(f'{origen}: el lugar corregido nombra su sección del Estudio o su fichero')
    if celda and not fichero:
        raise PitError(f'{origen}: la celda {celda!r} va con el fichero que la contiene')
    huella = str(c.get('huella') or '').strip().lower() or None
    if huella is not None and not _SHA256.fullmatch(huella):
        raise PitError(f'{origen}: la huella de {fichero or seccion!r} tiene que ser un SHA-256, no {huella!r}')
    conocida = huellas.get(fichero) if fichero else None
    if conocida is not None:
        conocida = str(conocida).lower()
        if huella is not None and huella != conocida:
            raise PitError(f'{origen}: la huella citada de {fichero!r} no es la del fichero del Estudio corregido')
        huella = conocida
    return {'seccion': seccion or None, 'fichero': fichero or None, 'celda': celda or None, 'huella': huella}


def documento_absolucion(oficio: Mapping[str, Any], respuestas: Iterable[Mapping[str, Any]],
                         huellas: Mapping[str, str] | None = None) -> dict[str, Any]:
    """El documento de respuestas a las observaciones con la forma que pide el regulador (107:RF-10).

    ``oficio`` trae su referencia (``referencia``, opcional) y sus ``observaciones``, cada una con su ``numero``
    literal, su ``tipo`` (uno de ``TIPOS_OBSERVACION``) y su ``texto``, en la secuencia del oficio. ``respuestas``
    trae, por número, la ``respuesta`` y sus ``correcciones`` (lugares del Estudio corregido: ``seccion``, o
    ``fichero`` y ``celda``, con ``huella`` opcional). ``huellas`` (fichero -> SHA-256) son las del Estudio corregido:
    completan la huella de cada fichero citado y rechazan la que no coincide.

    El documento conserva la numeración y la secuencia del oficio, con las generales primero: si el oficio las
    intercala, se reagrupan, y ``orden`` lo dice (``criterio`` = ``ORDEN_REAGRUPADO``) con la lista ``movidas`` (vacía
    si ninguna cambió de sitio); cada observación guarda su número, la referencia del oficio y su ``posicion_oficio``.
    Una observación sin respuesta, o sin lugar corregido (``lugar_corregido`` = «no indicado»), queda como hueco
    nombrado con los campos de ``CAMPOS_HUECO`` (nunca se inventa), y una respuesta a una observación que el oficio no
    tiene es un error. Cada observación lleva su evaluación vacía (``analisis`` y ``conclusion``).
    """
    huellas = dict(huellas or {})
    lista = list(oficio.get('observaciones') or [])
    if not lista:
        raise PitError('el oficio no trae observaciones: no hay absolución que formar')
    referencia = str(oficio.get('referencia') or '').strip() or None
    por_numero: dict[str, dict[str, Any]] = {}
    for posicion, d in enumerate(lista, start=1):
        numero = str(d.get('numero') or '').strip()
        origen = f'observación {numero or "sin número"}'
        if not numero:
            raise PitError(f'{origen}: cada observación del oficio lleva su número')
        if numero in por_numero:
            raise PitError(f'{origen}: número repetido en el oficio')
        tipo = str(d.get('tipo') or '')
        if tipo not in TIPOS_OBSERVACION:
            raise PitError(f'{origen}: el tipo tiene que ser uno de {TIPOS_OBSERVACION}, no {tipo!r}')
        if not str(d.get('texto') or '').strip():
            raise PitError(f'{origen}: sin texto')
        por_numero[numero] = {'numero': numero, 'tipo': tipo, 'texto': str(d['texto']), 'posicion_oficio': posicion}
    dadas: dict[str, Mapping[str, Any]] = {}
    for r in respuestas:
        numero = str(r.get('numero') or '').strip()
        if numero not in por_numero:
            raise PitError(f'respuesta a la observación {numero or "sin número"}: el oficio no la tiene')
        if numero in dadas:
            raise PitError(f'observación {numero}: dos respuestas')
        dadas[numero] = r
    secciones, huecos = [], []
    for tipo in TIPOS_OBSERVACION:
        filas = []
        for o in (v for v in por_numero.values() if v['tipo'] == tipo):
            r = dadas.get(o['numero']) or {}
            respuesta = str(r.get('respuesta') or '').strip() or None
            correcciones = [_lugar(o['numero'], c, huellas) for c in (r.get('correcciones') or [])]
            if respuesta is None:
                huecos.append(_hueco(referencia, o, 'respuesta', f'observación {o["numero"]}: sin respuesta'))
            if not correcciones:
                huecos.append(_hueco(referencia, o, 'lugar corregido',
                                     f'observación {o["numero"]}: lugar corregido: {LUGAR_NO_INDICADO}'))
            filas.append({**o, 'oficio': referencia, 'respuesta': respuesta, 'correcciones': correcciones,
                          'lugar_corregido': '; '.join(map(_describir_lugar, correcciones)) or LUGAR_NO_INDICADO,
                          'evaluacion': {'analisis': '', 'conclusion': ''}})
        if filas:
            secciones.append({'tipo': tipo, 'titulo': _TITULOS[tipo], 'observaciones': filas})
    # Reagrupar con las generales primero: se dice y se nombra lo que se movió respecto del oficio (veredicto de 28).
    movidas = [{'numero': o['numero'], 'posicion_oficio': o['posicion_oficio'], 'posicion_documento': i}
               for i, o in enumerate((o for s in secciones for o in s['observaciones']), start=1)
               if o['posicion_oficio'] != i]
    return {'oficio': referencia, 'secciones': secciones,
            'orden': {'criterio': ORDEN_REAGRUPADO, 'movidas': movidas},
            'huecos': huecos, 'conclusiones_admitidas': list(CONCLUSIONES)}


def _describir_lugar(c: Mapping[str, Any]) -> str:
    """El lugar corregido tal como se cita: la sección, o el fichero con su celda."""
    if c.get('fichero'):
        return f'{c["fichero"]} {c["celda"]}' if c.get('celda') else str(c['fichero'])
    return str(c['seccion'])


def _hueco(referencia: str | None, o: Mapping[str, Any], falta: str, texto: str) -> dict[str, Any]:
    """Un hueco del documento con los campos de ``CAMPOS_HUECO``, para que otro documento lo pueda leer."""
    return {'documento': 'absolucion', 'oficio': referencia, 'numero': o['numero'], 'tipo': o['tipo'],
            'falta': falta, 'texto': texto}


def escribir_documento_absolucion(ruta: Path | str, oficio: Mapping[str, Any], respuestas: Iterable[Mapping[str, Any]],
                                  huellas: Mapping[str, str] | None = None) -> Path:
    """El documento de respuestas en JSON con claves ordenadas: el mismo registro da el mismo fichero."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    doc = documento_absolucion(oficio, respuestas, huellas)
    # 001:RF-5: escritura atómica y duradera; en bytes, con LF como antes (newline='\n').
    publicar_duradero(ruta, (json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return ruta
