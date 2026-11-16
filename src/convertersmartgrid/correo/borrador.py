"""El borrador del correo de un informe y su firma (spec 110, parte A del plan).

Lo que el operador ve en la ventana (cuenta, para, cc, cco, asunto, cuerpo, adjuntos o enlace) se guarda en el servidor
como un ``Borrador`` y se resume en una **firma** SHA-256. «Confirmar y enviar» manda esa firma, y el trabajo de envío
vuelve a leer cada adjunto del disco y a recalcularla: si no coincide, el correo no sale y la ventana pide revisarlo
(110:RF-4, RF-5). Es el principio de ``GobiernoEquipo.confirmar`` del asistente (firma del plan más huellas de
entrada), sin copiar su código. Sin esto, un adjunto regenerado entre la vista previa y el clic, o un destinatario
cambiado por otra petición, saldría sin que el operador lo viera.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..archivo_informes import huella_fichero
from ..identify import DESCONOCIDO, FUENTE_MDB, FUENTE_TXT, FUENTE_VNR, fuente_de, identificar
from . import PROVEEDORES

#: Versión del formato de la firma: si cambia lo que cubre, una firma vieja deja de valer en vez de coincidir por azar.
VERSION_FIRMA = 1

#: Una dirección en su forma simple ``local@dominio.tld``. Sin nombres visibles, comentarios ni comillas: ningún
#: espacio, coma, punto y coma ni salto de línea, que es por donde se cuela otra cabecera (``\r\nBcc:``).
_PROHIBIDOS = r'\s@,;<>"()\[\]\\:'
_DIRECCION = re.compile(rf'^[^{_PROHIBIDOS}]+@[^{_PROHIBIDOS}.]+(\.[^{_PROHIBIDOS}.]+)+$')


class BorradorInvalido(ValueError):
    """Lo que pidió la ventana no se puede preparar como correo; el mensaje lo lee el operador."""


class ConfirmacionAnulada(RuntimeError):
    """El borrador o un adjunto cambió desde la vista previa: la confirmación no vale (110:RF-4)."""


@dataclass(frozen=True)
class Adjunto:
    nombre: str
    ruta: str
    tamano: int
    sha256: str


def adjunto_de(ruta: Path | str) -> Adjunto:
    """El adjunto tal como está ahora en el disco: su ruta resuelta, su tamaño y su huella."""
    ruta = Path(ruta).resolve()
    if not ruta.is_file():
        raise BorradorInvalido(f'El adjunto {ruta.name} no existe.')
    comprobar_adjunto(ruta)  # 110:RF-11: ninguna vía de adjuntar se salta la lista negra
    return Adjunto(nombre=ruta.name, ruta=str(ruta), tamano=ruta.stat().st_size, sha256=huella_fichero(ruta))


def normalizar_direccion(texto: str) -> str:
    """Sin espacios alrededor y en minúsculas; una dirección imposible no llega al borrador."""
    direccion = str(texto).strip().lower()
    if not _DIRECCION.match(direccion):
        raise BorradorInvalido(f'La dirección «{direccion}» no es válida.')
    return direccion


def _direcciones(lista: Iterable[str], ya: set[str]) -> tuple[str, ...]:
    salida = []
    for texto in lista or ():
        direccion = normalizar_direccion(texto)
        if direccion not in ya:
            ya.add(direccion)
            salida.append(direccion)
    return tuple(salida)


@dataclass(frozen=True)
class Borrador:
    cuenta: str
    proveedor: str
    para: tuple[str, ...]
    cc: tuple[str, ...] = ()
    cco: tuple[str, ...] = ()
    asunto: str = ''
    cuerpo: str = ''
    adjuntos: tuple[Adjunto, ...] = ()
    enlace: str | None = None
    #: Datos que la ventana muestra junto al borrador y que no se firman (avisos, validez del estudio...).
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def _firmado(self) -> dict[str, Any]:
        return {'version': VERSION_FIRMA, 'cuenta': self.cuenta, 'proveedor': self.proveedor,
                'para': list(self.para), 'cc': list(self.cc), 'cco': list(self.cco), 'asunto': self.asunto,
                'cuerpo': self.cuerpo, 'enlace': self.enlace,
                'adjuntos': [[a.ruta, a.tamano, a.sha256] for a in self.adjuntos]}

    def firma(self) -> str:
        """SHA-256 de todo lo que el operador ve y confirma, en una forma canónica."""
        canon = json.dumps(self._firmado(), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canon.encode('utf-8')).hexdigest()

    def destinatarios(self) -> tuple[str, ...]:
        return self.para + self.cc + self.cco

    def como_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos['extra'] = dict(self.extra)
        return datos

    @classmethod
    def desde_dict(cls, datos: Mapping[str, Any]) -> 'Borrador':
        return cls(cuenta=datos['cuenta'], proveedor=datos['proveedor'], para=tuple(datos['para']),
                   cc=tuple(datos.get('cc') or ()), cco=tuple(datos.get('cco') or ()),
                   asunto=datos.get('asunto') or '', cuerpo=datos.get('cuerpo') or '',
                   adjuntos=tuple(Adjunto(**a) for a in datos.get('adjuntos') or ()),
                   enlace=datos.get('enlace'), extra=dict(datos.get('extra') or {}))


def _enlace(texto: str | None) -> str | None:
    """110:RF-10: el enlace al expediente, solo ``https://`` y sin espacios ni saltos (nada de cabeceras escondidas)."""
    enlace = (texto or '').strip()
    if not enlace:
        return None
    if not enlace.lower().startswith('https://') or any(c.isspace() for c in enlace) or len(enlace) > 2048:
        raise BorradorInvalido('El enlace al expediente tiene que ser una dirección https:// sin espacios.')
    return enlace


def crear_borrador(*, cuenta: str, proveedor: str, para: Iterable[str], cc: Iterable[str] = (),
                   cco: Iterable[str] = (), asunto: str = '', cuerpo: str = '',
                   adjuntos: Iterable[Path | str] = (), enlace: str | None = None,
                   extra: Mapping[str, Any] | None = None) -> Borrador:
    """El borrador de lo que pidió la ventana (110:RF-1), con cada adjunto leído ahora del disco."""
    if proveedor not in PROVEEDORES:
        raise BorradorInvalido(f'Proveedor de correo no admitido: {proveedor}.')
    if '\r' in asunto or '\n' in asunto:
        raise BorradorInvalido('El asunto no puede tener saltos de línea.')
    ya: set[str] = set()
    a_para = _direcciones(para, ya)
    if not a_para:
        raise BorradorInvalido('Falta al menos un destinatario.')
    a_cc = _direcciones(cc, ya)
    a_cco = _direcciones(cco, ya)
    enlace = _enlace(enlace)
    if enlace and adjuntos:
        raise BorradorInvalido('Elija adjuntos o enlace, no los dos.')
    return Borrador(cuenta=normalizar_direccion(cuenta), proveedor=proveedor, para=a_para, cc=a_cc, cco=a_cco,
                    asunto=asunto.strip(), cuerpo=cuerpo, adjuntos=tuple(adjunto_de(r) for r in adjuntos),
                    enlace=enlace, extra=dict(extra or {}))


def comprobar_firma(borrador: Borrador, firma: str) -> None:
    """Vuelve a leer cada adjunto y compara la firma que vio el operador; si algo cambió, anula (110:RF-4, RF-5)."""
    if not hmac.compare_digest(borrador.firma(), str(firma)):
        raise ConfirmacionAnulada('El correo cambió desde la vista previa: revise otra vez antes de enviarlo.')
    for adjunto in borrador.adjuntos:
        ruta = Path(adjunto.ruta)
        try:
            ahora = adjunto_de(ruta)
        except BorradorInvalido:
            raise ConfirmacionAnulada(f'El adjunto {adjunto.nombre} ya no está: revise otra vez.') from None
        if (ahora.tamano, ahora.sha256) != (adjunto.tamano, adjunto.sha256):
            raise ConfirmacionAnulada(f'El adjunto {adjunto.nombre} cambió desde la vista previa: revise otra vez.')


# ------------------------------------------------------------------ adjuntos admitidos (110:RF-3) y prohibidos (RF-11)
#: Solo informes: Word, PDF y el libro Excel. Lo demás no sale, se llame como se llame.
EXTENSIONES = ('.docx', '.pdf', '.xlsx')
#: La parte principal que tiene que traer cada formato de Office: un Excel con extensión .docx tampoco vale.
_PARTE_OOXML = {'.docx': 'word/document.xml', '.xlsx': 'xl/workbook.xml'}
#: Lo que delata una credencial escrita en un fichero (un ``.env``, el JSON de un cliente OAuth, una clave privada).
_CREDENCIALES = (b'refresh_token', b'client_secret', b'access_token', b'private_key', b'-----begin ', b'password=',
                 b'api_key')
#: Cuánto se mira de un PDF o de cada parte de un Office: lo justo para reconocerlo sin leer cientos de megas.
_BYTES_A_MIRAR = 4 << 20


class AdjuntoProhibido(BorradorInvalido):
    """El fichero no es un informe que se pueda enviar: datos crudos, un comprimido o una credencial (110:RF-11)."""


def _credencial(datos: bytes) -> bool:
    bajo = datos.lower()
    return any(m in bajo for m in _CREDENCIALES)


def _comprobar_datos_crudos(ruta: Path) -> None:
    """Lo que el conversor reconoce como una fuente de la distribuidora, con su propio reconocedor (P5)."""
    fuente = fuente_de(ruta)
    if fuente.fuente == FUENTE_MDB:
        raise AdjuntoProhibido(f'{ruta.name} es una base Access de la distribuidora: no se envía.')
    if fuente.fuente == FUENTE_TXT or identificar(ruta).tipo != DESCONOCIDO:
        raise AdjuntoProhibido(f'{ruta.name} es un TXT de CYMDIST de la distribuidora: no se envía.')
    if fuente.fuente == FUENTE_VNR:
        raise AdjuntoProhibido(f'{ruta.name} es un paquete VNR-GIS de la distribuidora: no se envía.')


def comprobar_adjunto(ruta: Path | str) -> None:
    """Solo pasa un Word, un PDF o un Excel de verdad, sin datos crudos, comprimidos ni credenciales (110:RF-11).

    Se mira el contenido y no el nombre: un TXT, una MDB, un paquete VNR, un ZIP o un ``.env`` renombrados a ``.pdf``
    se rechazan igual. Un Word y un Excel son ZIP por dentro, así que se exige su estructura de Office y se rechaza
    cualquier objeto incrustado (``*/embeddings/*``), por donde podría viajar una base entera.
    """
    ruta = Path(ruta)
    extension = ruta.suffix.lower()
    if extension not in EXTENSIONES:
        raise AdjuntoProhibido(f'{ruta.name}: solo se adjuntan informes en Word, PDF o Excel.')
    if not ruta.is_file():
        raise AdjuntoProhibido(f'El adjunto {ruta.name} no existe.')
    _comprobar_datos_crudos(ruta)
    with ruta.open('rb') as fh:
        cabecera = fh.read(_BYTES_A_MIRAR)
    if extension == '.pdf':
        if not cabecera.startswith(b'%PDF-'):
            raise AdjuntoProhibido(f'{ruta.name} no es un PDF.')
        if _credencial(cabecera):
            raise AdjuntoProhibido(f'{ruta.name} parece llevar una credencial escrita: no se envía.')
        return
    try:
        with zipfile.ZipFile(ruta) as z:
            nombres = set(z.namelist())
            if '[Content_Types].xml' not in nombres or _PARTE_OOXML[extension] not in nombres:
                raise AdjuntoProhibido(f'{ruta.name} no es un documento de Office válido.')
            if any('/embeddings/' in n for n in nombres):
                raise AdjuntoProhibido(f'{ruta.name} lleva un fichero incrustado: no se envía.')
            for info in z.infolist():
                if info.filename.lower().endswith(('.xml', '.rels')):
                    with z.open(info) as parte:
                        if _credencial(parte.read(_BYTES_A_MIRAR)):
                            raise AdjuntoProhibido(f'{ruta.name} parece llevar una credencial escrita: no se envía.')
    except zipfile.BadZipFile:
        raise AdjuntoProhibido(f'{ruta.name} no es un documento de Office válido.') from None


def resumen_del_informe(out_dir: Path | str, informe: str) -> tuple[Path, dict[str, Any]]:
    """El Word publicado en la salida del espacio y su resumen ``.json``: los dos juntos son un informe cerrado.

    ``informe_docx._guardar`` publica el Word y su ``.json`` a la vez; un Word sin su resumen es un informe antiguo o
    a medio escribir, y no se adjunta como cerrado (riesgo del plan de la 110).
    """
    out = Path(out_dir).resolve()
    if Path(informe).name != informe or not informe.lower().endswith('.docx'):
        raise BorradorInvalido(f'«{informe}» no es un informe de la salida del espacio.')
    docx = out / informe
    if not docx.is_file():
        raise BorradorInvalido(f'El informe {informe} no está en la salida del espacio.')
    try:
        resumen = json.loads(docx.with_suffix('.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise BorradorInvalido(f'El informe {informe} no está cerrado: le falta su resumen .json.') from None
    if not isinstance(resumen, dict):
        raise BorradorInvalido(f'El informe {informe} no está cerrado: su resumen .json no se entiende.')
    return docx, resumen


def adjuntos_del_informe(out_dir: Path | str, informe: str, *, proyecto: str | None = None,
                         escenario: str | None = None, informes_en_curso: bool = False,
                         elegidos: Iterable[str] = ('docx', 'pdf', 'xlsx')) -> list[Path]:
    """Los ficheros de un informe cerrado que se pueden adjuntar, ya comprobados (110:RF-3, RF-11).

    El Word y, si están al lado con el mismo nombre, su PDF (``exportar_pdf``) y su libro (``generar_libro``). El
    proyecto y el escenario que dice el resumen tienen que ser los de la ventana; mientras un trabajo de informes
    corre en el espacio, el informe puede cambiar y no se adjunta.
    """
    if informes_en_curso:
        raise BorradorInvalido('Hay un trabajo de informes en curso en este espacio: espere a que termine.')
    docx, resumen = resumen_del_informe(out_dir, informe)
    for clave, pedido, rotulo in ((('project', 'proyecto'), proyecto, 'proyecto'),
                                  (('escenario',), escenario, 'escenario')):
        declarado = next((resumen[k] for k in clave if resumen.get(k) not in (None, '')), None)
        if pedido is not None and declarado is not None and str(declarado) != str(pedido):
            raise BorradorInvalido(f'El informe {informe} es del {rotulo} «{declarado}», no del «{pedido}» de la '
                                   'ventana.')
    elegidos = {e.lower().lstrip('.') for e in elegidos}
    rutas = [docx.with_suffix(ext) for ext in EXTENSIONES if ext.lstrip('.') in elegidos]
    rutas = [r for r in rutas if r == docx or r.is_file()]
    for ruta in rutas:
        comprobar_adjunto(ruta)
    return rutas




# ------------------------------------------------------------------ validez del estudio (110:RF-12)
#: Lo que debe traer el resumen de cada tipo de informe para que su dictamen se pueda leer.
_DICTAMEN = {
    'factibilidad': lambda r: isinstance(r.get('factible'), bool),
    'estudio': lambda r: isinstance(r.get('cumplen'), dict) and 'recomendada' in r,
    'resumen_estudios': lambda r: bool(r.get('conclusiones')),
}
#: Las marcas con que el conversor dice que un resultado no vale como estudio (el oráculo, el ciclo de aprendizaje).
_MARCAS = ('fuera_de_dominio', 'bloqueado', 'no_terminado')
AVISO_NO_VALIDO = 'No es válido como estudio'


def _marca(valor: Any, profundidad: int = 0) -> str | None:
    if profundidad > 6:
        return None
    if isinstance(valor, Mapping):
        for clave in _MARCAS:
            if valor.get(clave):
                return clave
        if valor.get('estado') in ('bloqueado', 'no_terminado'):
            return str(valor['estado'])
        valores = valor.values()
    elif isinstance(valor, (list, tuple)):
        valores = valor
    else:
        return None
    for hijo in valores:
        encontrada = _marca(hijo, profundidad + 1)
        if encontrada:
            return encontrada
    return None


def validez_del_estudio(resumen: Mapping[str, Any] | None) -> dict[str, Any]:
    """Si el informe sale de un estudio válido, y si no, por qué (110:RF-12).

    Un estudio con ``error``, sin terminar, bloqueado o fuera del dominio de los modelos, o un resumen sin dictamen
    legible, no se presenta como un estudio válido: la ventana lo dice y el cuerpo propuesto también.
    """
    if not isinstance(resumen, Mapping):
        return {'valido': False, 'motivo': 'el informe no tiene su resumen: no se puede saber qué dictaminó'}
    if resumen.get('error'):
        return {'valido': False, 'motivo': f'el estudio terminó con error: {resumen["error"]}'}
    marca = _marca(resumen)
    if marca:
        motivo = {'fuera_de_dominio': 'el resultado está fuera del dominio de los modelos',
                  'bloqueado': 'el estudio quedó bloqueado',
                  'no_terminado': 'el estudio no terminó'}[marca]
        return {'valido': False, 'motivo': motivo}
    legible = _DICTAMEN.get(str(resumen.get('tipo')))
    if legible is None or not legible(resumen):
        return {'valido': False, 'motivo': 'el resumen del informe no trae un dictamen legible'}
    return {'valido': True, 'motivo': ''}


def cuerpo_propuesto(asunto: str, validez: Mapping[str, Any]) -> str:
    """El cuerpo inicial de la ventana, editable; si el estudio no vale, lo dice antes que nada (110:RF-12)."""
    lineas = []
    if not validez.get('valido'):
        lineas += [f'{AVISO_NO_VALIDO}: {validez.get("motivo")}.', '']
    lineas += ['Buenos días:', '', f'Le enviamos el informe «{asunto}».' if asunto else 'Le enviamos el informe.',
               '', 'Saludos cordiales.']
    return '\n'.join(lineas) + '\n'




# ------------------------------------------------------------------ contactos habituales (110:RF-14)
#: Hasta cuántas letras de diferencia una dirección se toma por una habitual mal escrita (plan, parte E).
DISTANCIA_PARECIDA = 2


def _distancia(a: str, b: str) -> int:
    """Distancia de edición (Levenshtein); las partes de una dirección son cortas."""
    if a == b:
        return 0
    previa = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previa[j] + 1, actual[j - 1] + 1, previa[j - 1] + (ca != cb)))
        previa = actual
    return previa[-1]


def _parecida(direccion: str, habituales: Iterable[str]) -> str | None:
    local, _, dominio = direccion.partition('@')
    candidatas = []
    for otra in habituales:
        o_local, _, o_dominio = otra.partition('@')
        if o_dominio == dominio:
            d = _distancia(local, o_local)
        elif o_local == local:
            d = _distancia(dominio, o_dominio)
        else:
            continue
        if 0 < d <= DISTANCIA_PARECIDA:
            candidatas.append((d, otra))
    return min(candidatas)[1] if candidatas else None


def avisos_de_contactos(borrador: Borrador, habituales: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Un aviso junto a cada dirección que no es habitual en el espacio, con la parecida si la hay (110:RF-14).

    No hay libreta cerrada (decisión 2 de la spec): vale cualquier dirección, y el aviso no impide enviar.
    """
    habituales = set(habituales)
    avisos = {}
    for direccion in borrador.destinatarios():
        if direccion in habituales:
            continue
        sugerencia = _parecida(direccion, habituales)
        aviso = 'No es un contacto habitual de este espacio.'
        if sugerencia:
            aviso += f' ¿Quería decir {sugerencia}?'
        avisos[direccion] = {'aviso': aviso, 'sugerencia': sugerencia}
    return avisos
