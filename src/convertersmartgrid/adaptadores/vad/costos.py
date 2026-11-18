"""Costo estándar de la empresa modelo: la red DIMENSIONADA valorada con el SICODI del periodo (spec 108, RF-7, RF-9).

El Anexo 6 adapta el equipamiento sobre la traza real y «finalmente, se valorizan todas las unidades transformadoras
MT/BT» (``vad.anexo6.sed``). Este módulo valora lo que dimensionó la T6, y nada más:

- **Conductor de MT**: los km de cada conductor de la empresa modelo (``TramoDimensionado.conductor_modelo``), con la
  longitud real del tramo, por alimentador, con ``metrados.metrados_de_lineas`` y ``metrados.valorar_metrados``.
- **Transformación**: cada SED con su potencia de la empresa modelo, en módulos si la regla los pide, con
  ``costos_fuentes.valorar_obra``. El código de costo de cada (tipo de SED, kVA) lo da ``codigo_sed``: el SICODI
  no trae una tabla con ese cruce y no se deduce del texto del nombre.
- **SICODI** leído con ``costos_fuentes.leer_sicodi`` y **por su huella**, nunca con una versión fija. Se firma el
  fichero TAL COMO LLEGA (:func:`firmar_sicodi`): zip o libro (xlsx). Si es zip, se firma además el miembro que se lee
  (``Instalacion.txt``), porque el mismo contenido vuelto a comprimir cambia la huella del zip y no la del miembro, y
  un miembro cambiado tiene que notarse aunque alguien vuelva a declarar el zip. El periodo declara las dos huellas;
  la tabla tiene que salir del fichero firmado. Un SICODI en libro (el RR VAD de la referencia es un xlsx) se firma, pero
  ``leer_sicodi`` (072) solo lee el zip: queda como hueco nombrado (:func:`leer_sicodi_del_periodo`).

Cada elemento valorado lleva su **fuente** (resolución, año, huella, URL y fecha de descarga del SICODI), su **moneda**
y el **IGV** que dice el registro (``vad.igv_costos``: «Las cifras monetarias de las inversiones y costos no deberán
incluir IGV»), con la cita, la huella y el estado jurídico de esa regla (RF-9).

**Regla VNR real ≠ empresa modelo** (RF-7): :class:`CostoEstandar` solo se construye con un
:class:`~.dimensionamiento.Dimensionamiento` con su huella. El VNR real (los conductores y las potencias reales,
valorados igual) va solo en la columna ``referencia`` y nunca entra en el total estándar. Lo que no cruza con el
SICODI, o no se dimensionó, queda nombrado en ``sin_costo`` y fuera del total. **Dos monedas no se suman**: los totales
van por moneda, y la diferencia con la referencia solo se da en una misma moneda.

**aVNR de un SER** (:func:`avnr_ser`, RLGER, DS 018-2020-EM, que el DS 003-2026-EM no toca en estos artículos):
aVNR = VNR estándar × FRC (``vad.tasa_actualizacion`` y la vida útil de ``vad.ser.ffr.formula``, contrastado con
``vad.frc``). Con el 100 % de aportes del Estado, aVNR × FFR (art. 37.2 b, ``vad.ser.avnr.inversion_estado_100``); con
inversión mixta, fp × aVNR + (1 − fp) × aVNR × FFR (art. 37.3, ``vad.ser.avnr.inversion_mixta``). El FFR
(:func:`ffr`, DCF Décima Primera, ``vad.ser.ffr.formula``) = FAC(tasa pasiva, 30) / FRC(12 %, 30), con FAC el factor
de fondo de amortización i/((1+i)^n − 1): el texto no escribe la fórmula del «factor de reposición», y esa lectura (de
c3) es la interpretación registrada en la regla y la que reproduce el libro del Anexo 15 (0,199494 con 1,97 %). La
tasa pasiva de la SBS y el fp son ENTRADAS del perfil del periodo, sin valor por defecto: sin la tasa no hay FFR, y se
nombra el hueco. La tasa activa sale del registro.
"""
from __future__ import annotations

import hashlib
import json
import math
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ...aplicacion.costos_fuentes import (
    CostosError,
    TablaCostos,
    exigir_ambito,
    leer_sicodi,
    valorar_obra,
)
from ...aplicacion.metrados import metrados_de_lineas, valorar_metrados
from ...aplicacion.pide_economia import frc
from ...dominio.registro_normativo import RegistroError, RegistroNormativo, ReglaRemitida, ReglaVigente, regla_remitida
from ...dominio.util import sha256_file
from ...aplicacion.vad import VadError
from .dimensionamiento import Dimensionamiento

#: La regla del registro (T2) con la moneda y el IGV de las inversiones y costos del estudio.
REGLA_IGV = 'vad.igv_costos'
#: Lo que la regla puede decir del IGV para que el costo sea conforme; ``sin_leer`` o ``no_aplica`` no valen.
IGV_LEIDO = ('excluido', 'incluido')
CONDUCTOR = 'conductor_mt'
SED = 'sed'
_AMBITO = 'distribucion'


@dataclass(frozen=True)
class ElementoCosteado:
    """Un elemento valorado: metrado × costo unitario del SICODI, con su fuente, su moneda y su IGV (108:RF-9)."""

    elemento: str
    clase: str
    """:data:`CONDUCTOR` (km de un código en un alimentador) o :data:`SED` (una SED)."""
    alimentador: str
    codigo: str
    cantidad: float
    unidad: str
    costo_unitario: float
    costo: float
    moneda: str
    igv: str
    fuente: Mapping[str, Any]
    criterio: Mapping[str, Any]
    nombre: str = ''


@dataclass(frozen=True)
class SinCosto:
    """Un elemento que no se valora: se nombra con su motivo y no entra en ningún total (072:RF-16)."""

    elemento: str
    clase: str
    alimentador: str
    codigo: str
    motivo: str


def _por_moneda(elementos: Sequence[ElementoCosteado]) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in elementos:
        out[e.moneda] = out.get(e.moneda, 0.0) + e.costo
    return dict(sorted(out.items()))


@dataclass(frozen=True)
class CostoEstandar:
    """El costo estándar de la empresa modelo, con el VNR real solo como referencia (108:RF-7, RF-9)."""

    dimensionamiento: Dimensionamiento
    huella_dimensionamiento: str
    estandar: tuple[ElementoCosteado, ...]
    sin_costo: tuple[SinCosto, ...]
    referencia: tuple[ElementoCosteado, ...]
    """«VNR real (referencia)»: la red real valorada igual; nunca suma en el estándar."""
    referencia_sin_costo: tuple[SinCosto, ...]
    moneda_anexo: str
    igv_anexo: str
    criterio: Mapping[str, Any]
    huecos: tuple[str, ...] = ()
    huella: str = ''
    notas: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        # RF-7: el costo estándar no sale nunca del inventario sin dimensionar.
        if not isinstance(self.dimensionamiento, Dimensionamiento):
            raise VadError(f'el costo estándar solo se construye con un Dimensionamiento, no con '
                           f'{type(self.dimensionamiento).__name__}: el VNR real no es la empresa modelo')
        if not self.dimensionamiento.huella or self.huella_dimensionamiento != self.dimensionamiento.huella:
            raise VadError('el costo estándar tiene que llevar la huella del dimensionamiento del que sale')

    @property
    def total_por_moneda(self) -> dict[str, float]:
        """Moneda → total estándar. Dos monedas no se suman: sumarlas exigiría un tipo de cambio no declarado."""
        return _por_moneda(self.estandar)

    @property
    def referencia_por_moneda(self) -> dict[str, float]:
        return _por_moneda(self.referencia)

    @property
    def total_estandar(self) -> float | None:
        """El total en la moneda del anexo; ``None`` si falta esa moneda o hay elementos en otra."""
        totales = self.total_por_moneda
        if not self.moneda_anexo or set(totales) - {self.moneda_anexo}:
            return None
        return totales.get(self.moneda_anexo, 0.0)

    @property
    def diferencia(self) -> tuple[float | None, str]:
        """(estándar − referencia, motivo): solo en una misma moneda, la del anexo."""
        ref = self.referencia_por_moneda
        if self.total_estandar is None:
            return None, f'el estándar no está solo en {self.moneda_anexo or "(sin moneda del anexo)"}'
        if set(ref) - {self.moneda_anexo}:
            return None, (f'la referencia está en {", ".join(sorted(ref))} y el estándar en {self.moneda_anexo}: '
                          f'dos monedas no se restan')
        return self.total_estandar - ref.get(self.moneda_anexo, 0.0), ''

    @property
    def completo(self) -> bool:
        """Falso si algo no se valoró o no se dimensionó: el estudio no se emite como completo."""
        return not (self.sin_costo or self.huecos) and self.dimensionamiento.completo


@dataclass(frozen=True)
class _Linea:
    """Lo que ``metrados_de_lineas`` lee de una línea: el tramo, su código de costo, su largo y si es aéreo."""

    section_id: str
    source_type_code: str
    length_m: float
    overhead: bool = True
    """El modelo rural no distingue aéreo de subterráneo: se valora con la estructura declarada del alimentador."""


def _fuente(tabla: TablaCostos) -> dict[str, Any]:
    f = tabla.fuente
    return {'nombre': f.nombre, 'ambito': f.ambito, 'resolucion': f.resolucion, 'anio': f.anio, 'moneda': f.moneda,
            'url': f.url, 'fecha_descarga': f.fecha_descarga, 'huella': f.huella, 'factor': f.factor,
            'sustento_factor': f.sustento_factor}


def _ambito(tabla: TablaCostos, papel: str) -> None:
    try:
        exigir_ambito(tabla, _AMBITO)
    except CostosError as exc:
        raise VadError(f'{papel}: {exc}; la red de distribución se valora con el SICODI') from exc


def _valorar(conductores: Sequence[tuple[str, str, str, float | None]], seds: Sequence[tuple[str, str, str, int]],
             tabla: TablaCostos, *, sector_de: Mapping[str, str], estructura_de: Mapping[str, str], igv: str,
             criterio: Mapping[str, Any]) -> tuple[list[ElementoCosteado], list[SinCosto]]:
    """Valora (alimentador, tramo, código, m) y (alimentador, SED, código, cantidad) con ``tabla``, por alimentador."""
    fuente = _fuente(tabla)
    valorados: list[ElementoCosteado] = []
    sin_costo: list[SinCosto] = []
    alimentadores = sorted({c[0] for c in conductores} | {s[0] for s in seds})
    for alim in alimentadores:
        sector, estructura = str(sector_de.get(alim) or ''), str(estructura_de.get(alim) or '')
        lineas = []
        for _a, tramo, codigo, largo in (c for c in conductores if c[0] == alim):
            if largo is None:
                sin_costo.append(SinCosto(tramo, CONDUCTOR, alim, codigo, 'sin longitud: sin metrado no hay costo'))
            else:
                lineas.append(_Linea(tramo, codigo, float(largo)))
        metrado = metrados_de_lineas(lineas)
        sin_costo.extend(SinCosto(t, CONDUCTOR, alim, '', 'tramo sin código de conductor') for t in metrado['sin_codigo'])
        if metrado['por_codigo']:
            v = valorar_metrados(metrado['por_codigo'], tabla, sector=sector, estructura=estructura)
            for x in v['valorados']:
                valorados.append(ElementoCosteado(
                    f'{alim} · {x["codigo"]} ({metrado["por_codigo"][x["codigo"]]["tramos"]} tramos)', CONDUCTOR,
                    alim, x['codigo'], x['km'], 'km', x['costo_por_km'], x['costo'], v['moneda'], igv, fuente,
                    criterio, x['nombre']))
            sin_costo.extend(SinCosto(f'{alim} · {x["codigo"]}', CONDUCTOR, alim, x['codigo'], x['motivo'])
                             for x in v['sin_costo'])
        elementos = [{'elemento': sed, 'ambito': _AMBITO, 'codigo': codigo, 'cantidad': cantidad, 'sector': sector,
                      'estructura': estructura} for _a, sed, codigo, cantidad in (s for s in seds if s[0] == alim)]
        if elementos:
            r = valorar_obra(elementos, {_AMBITO: tabla})
            valorados.extend(ElementoCosteado(x['elemento'], SED, alim, x['codigo'], x['cantidad'], 'u',
                                              x['costo_unitario'], x['costo'], x['moneda'], igv, fuente, criterio,
                                              x['nombre']) for x in r['valorados'])
            sin_costo.extend(SinCosto(x['elemento'], SED, alim, x['codigo'], x['motivo']) for x in r['sin_costo'])
    return valorados, sin_costo


def _criterio(registro: RegistroNormativo, fecha: str | None) -> tuple[dict[str, Any], str, str, list[str]]:
    try:
        rv = registro.regla(REGLA_IGV, fecha)
    except RegistroError as exc:
        raise VadError(f'el costo estándar toma la moneda y el IGV de la regla {REGLA_IGV}: {exc}') from exc
    r = rv.regla
    huecos = []
    moneda = str(r.moneda or '').strip()
    if not moneda:
        huecos.append(f'la regla {REGLA_IGV} no dice la moneda de las inversiones')
    if r.igv not in IGV_LEIDO:
        huecos.append(f'la regla {REGLA_IGV} tiene el IGV «{r.igv}»: sin leerlo en el anexo, el costo no es conforme')
    criterio = {'regla': REGLA_IGV, 'cita': f'{rv.norma.acto}, {r.articulo_o_anexo}, {r.pagina}, líneas {r.lineas}',
                'huella': rv.huella(), 'estado_juridico': rv.estado, 'version': rv.norma.version, 'moneda': moneda,
                'igv': r.igv}
    return criterio, moneda, r.igv, huecos


# ------------------------------------------------------------------------------- huella del SICODI tal como llega

#: El miembro del zip del SICODI que lee ``costos_fuentes.leer_sicodi`` (el primero con ese nombre, en cualquier
#: carpeta del zip, en el orden del zip: el mismo criterio que el lector).
MIEMBRO_SICODI = 'Instalacion.txt'
#: Lo que distingue un libro OOXML (xlsx, xlsm o xlsb) de un zip cualquiera: su libro dentro del paquete.
_LIBRO_OOXML = ('xl/workbook.xml', 'xl/workbook.bin')
FORMATOS_SICODI = ('zip', 'xlsx')


@dataclass(frozen=True)
class FirmaSicodi:
    """La huella del SICODI tal como llega (108:RF-9): ``formato`` (``zip`` o ``xlsx``, por su contenido, no por el
    nombre), ``huella`` del fichero entero y, en un zip, el ``miembro`` leído y su ``huella_miembro``."""

    formato: str
    huella: str
    miembro: str = ''
    huella_miembro: str = ''


def firmar_sicodi(ruta: Path | str) -> FirmaSicodi:
    """Firma el SICODI tal como llega. Un zip con ``Instalacion.txt`` se firma entero y, además, el miembro; un libro
    OOXML se firma entero. Otra cosa (un zip sin el miembro, un .xls binario, un texto) lanza VadError que lo dice."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise VadError(f'no existe el SICODI {ruta}')
    huella = sha256_file(ruta)
    if not zipfile.is_zipfile(ruta):
        raise VadError(f'{ruta.name}: el SICODI llega como zip (con {MIEMBRO_SICODI}) o como libro xlsx; este no es '
                       'ninguno de los dos')
    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
        if any(n in nombres for n in _LIBRO_OOXML):
            return FirmaSicodi('xlsx', huella)
        miembro = next((n for n in nombres if n.rsplit('/', 1)[-1] == MIEMBRO_SICODI), None)
        if miembro is None:
            raise VadError(f'{ruta.name}: el zip del SICODI no trae {MIEMBRO_SICODI}')
        digest = hashlib.sha256()
        with z.open(miembro) as f:
            for bloque in iter(lambda: f.read(1 << 20), b''):
                digest.update(bloque)
    return FirmaSicodi('zip', huella, miembro, digest.hexdigest())


def _exigir_firma(firma: FirmaSicodi, tabla: TablaCostos | None, *, huella_sicodi: str,
                  huella_miembro: str | None) -> None:
    """La firma es la que declara el periodo, la del fichero y, en un zip, la del miembro; y la tabla sale de él."""
    if not isinstance(firma, FirmaSicodi) or firma.formato not in FORMATOS_SICODI:
        raise VadError('el SICODI se lee por su huella: falta su firma (firmar_sicodi) tal como llega')
    if not str(huella_sicodi or '').strip() or firma.huella != huella_sicodi:
        raise VadError(f'el SICODI se lee por su huella: el fichero ({firma.formato}) tiene {firma.huella} y el '
                       f'periodo declara {huella_sicodi or "(ninguna)"}')
    if firma.formato == 'zip':
        if not str(huella_miembro or '').strip():
            raise VadError(f'el SICODI llega en zip y el periodo no declara la huella de su miembro {MIEMBRO_SICODI}: '
                           'sin ella, un miembro cambiado no se nota')
        if firma.huella_miembro != huella_miembro:
            raise VadError(f'el miembro {firma.miembro} del SICODI tiene la huella {firma.huella_miembro} y el periodo '
                           f'declara {huella_miembro}: el {MIEMBRO_SICODI} no es el del periodo')
    elif huella_miembro:
        raise VadError(f'el SICODI llega en {firma.formato}, que no tiene miembro {MIEMBRO_SICODI}: el periodo declara '
                       f'una huella de miembro ({huella_miembro}) de otro fichero')
    if tabla is not None and tabla.fuente.huella != firma.huella:
        raise VadError(f'la tabla del SICODI tiene la huella {tabla.fuente.huella} y el fichero firmado {firma.huella}: '
                       'no sale de ese fichero')


def leer_sicodi_del_periodo(ruta: Path | str, *, huella_sicodi: str, huella_miembro: str | None = None,
                            resolucion: str, anio: int, moneda: str, url: str, fecha_descarga: str,
                            factor: float | None = None, sustento_factor: str | None = None,
                            ) -> tuple[TablaCostos | None, FirmaSicodi, tuple[str, ...]]:
    """(tabla, firma, huecos): firma el SICODI tal como llega, lo comprueba con lo que declara el periodo y, si es
    zip, lo lee con ``costos_fuentes.leer_sicodi``. Un libro xlsx se firma y se comprueba, pero no se lee: la tabla es
    None y el hueco lo nombra (``leer_sicodi`` es de la 072 y solo lee el zip)."""
    firma = firmar_sicodi(ruta)
    _exigir_firma(firma, None, huella_sicodi=huella_sicodi, huella_miembro=huella_miembro)
    if firma.formato == 'xlsx':
        hueco = (f'el SICODI del periodo llega como libro xlsx ({Path(ruta).name}, huella {firma.huella}): '
                 'costos_fuentes.leer_sicodi solo lee el zip con Instalacion.txt; sin su lector del libro '
                 'no hay tabla de costos y no se valora nada')
        return None, firma, (hueco,)
    try:
        tabla = leer_sicodi(ruta, resolucion=resolucion, anio=anio, moneda=moneda, url=url,
                            fecha_descarga=fecha_descarga, factor=factor, sustento_factor=sustento_factor)
    except CostosError as exc:
        raise VadError(f'SICODI del periodo: {exc}') from exc
    _exigir_firma(firma, tabla, huella_sicodi=huella_sicodi, huella_miembro=huella_miembro)
    return tabla, firma, ()


def costo_estandar(dimensionamiento: Dimensionamiento, *, sicodi: TablaCostos, huella_sicodi: str,
                   firma_sicodi: FirmaSicodi, registro: RegistroNormativo, sector_de: Mapping[str, str],
                   estructura_de: Mapping[str, str], tipo_de_sed: Mapping[str, str],
                   codigo_sed: Mapping[tuple[str, float], str], huella_miembro: str | None = None,
                   sicodi_referencia: TablaCostos | None = None, fecha: str | None = None) -> CostoEstandar:
    """Valora la red dimensionada con el SICODI del periodo, y la real solo como referencia (108:RF-7, RF-9).

    ``sicodi``: la tabla de ``costos_fuentes.leer_sicodi``; ``firma_sicodi``: la de :func:`firmar_sicodi` sobre el
    fichero tal como llega; ``huella_sicodi`` y, si es zip, ``huella_miembro`` (la de ``Instalacion.txt``): las que
    declara el periodo. Si no casan, o la tabla no sale del fichero firmado, no se valora (VadError).
    ``sector_de`` y ``estructura_de``: el sector típico y la estructura del SICODI de cada
    alimentador. ``tipo_de_sed``: el tipo de cada SED, el mismo de la tabla de transformadores de la T6.
    ``codigo_sed``: (tipo de SED, kVA de una unidad) → código de costo del SICODI con su letra de tensión (la forma
    del VNR, ``AA03503G``). ``sicodi_referencia``: si el VNR real se valora con otra tabla; por defecto, ``sicodi``.
    """
    if not isinstance(dimensionamiento, Dimensionamiento):
        raise VadError(f'el costo estándar solo se construye con un Dimensionamiento, no con '
                       f'{type(dimensionamiento).__name__}: el inventario sin dimensionar es el VNR real')
    dim = dimensionamiento
    if not dim.huella:
        raise VadError('el dimensionamiento no tiene huella: sin ella no se sabe qué red se valora')
    trazas = {t.tramo: t.huella for t in dim.modelo.tramos}
    cambiados = sorted(t.tramo for t in dim.tramos if trazas.get(t.tramo) != t.huella)
    if cambiados:
        raise VadError(f'{len(cambiados)} tramo(s) dimensionados no tienen la huella del modelo rural: '
                       f'{", ".join(cambiados[:20])}')
    _ambito(sicodi, 'el SICODI del costo estándar')
    _exigir_firma(firma_sicodi, sicodi, huella_sicodi=huella_sicodi, huella_miembro=huella_miembro)
    referencia_tabla = sicodi if sicodi_referencia is None else sicodi_referencia
    _ambito(referencia_tabla, 'el SICODI de la referencia')
    criterio, moneda, igv, huecos = _criterio(registro, fecha)
    notas: list[str] = []
    if dim.tabla_huella and dim.tabla_huella != sicodi.fuente.huella:
        huecos.append(f'la tabla de transformadores de la T6 salió del SICODI de huella {dim.tabla_huella} y se valora '
                      f'con el de huella {sicodi.fuente.huella}: potencias y costos de dos fuentes')
    for tabla, papel in ((sicodi, 'estándar'), (referencia_tabla, 'referencia')):
        if moneda and tabla.fuente.moneda != moneda:
            huecos.append(f'el SICODI de la columna {papel} está en {tabla.fuente.moneda} y {REGLA_IGV} pide {moneda}: '
                          f'no se convierte (sería un tipo de cambio no declarado)')

    largo = {t.tramo: t.longitud_m for t in dim.modelo.tramos}
    sin_costo: list[SinCosto] = []
    ref_sin_costo: list[SinCosto] = []
    conductores_m, conductores_r = [], []
    for t in dim.tramos:
        if t.conductor_real:
            conductores_r.append((t.alimentador, t.tramo, t.conductor_real, largo.get(t.tramo)))
        else:
            ref_sin_costo.append(SinCosto(t.tramo, CONDUCTOR, t.alimentador, '', 'la fuente no da su conductor'))
        if t.conductor_modelo is None:
            sin_costo.append(SinCosto(t.tramo, CONDUCTOR, t.alimentador, t.conductor_real,
                                      f'no dimensionado ({t.nota or "sin conductor de la empresa modelo"}): el '
                                      f'costo del conductor real no es costo estándar'))
        else:
            conductores_m.append((t.alimentador, t.tramo, t.conductor_modelo, largo.get(t.tramo)))
    seds_m, seds_r = [], []
    for s in dim.sed:
        tipo = str(tipo_de_sed.get(s.sed) or '')
        for kva, cantidad, destino, faltan, papel in (
                (None if s.kva_modelo is None else s.kva_modelo / max(s.modulos, 1), max(s.modulos, 1), seds_m,
                 sin_costo, 'de la empresa modelo'),
                (s.kva_real, 1, seds_r, ref_sin_costo, 'real')):
            if kva is None:
                motivo = (f'sin potencia {papel}' + (f' ({s.nota})' if s.nota and papel != 'real' else '')
                          + ('' if papel == 'real' else ': no se dimensionó'))
                faltan.append(SinCosto(s.sed, SED, s.alimentador, '', motivo))
            elif not tipo:
                faltan.append(SinCosto(s.sed, SED, s.alimentador, '', 'sin tipo de SED'))
            elif (tipo, float(kva)) not in codigo_sed:
                faltan.append(SinCosto(s.sed, SED, s.alimentador, '',
                                       f'sin código de costo para ({tipo}, {float(kva):g} kVA) en codigo_sed'))
            else:
                destino.append((s.alimentador, s.sed, codigo_sed[(tipo, float(kva))], cantidad))
    try:
        estandar, faltan_m = _valorar(conductores_m, seds_m, sicodi, sector_de=sector_de, estructura_de=estructura_de,
                                      igv=igv, criterio=criterio)
        referencia, faltan_r = _valorar(conductores_r, seds_r, referencia_tabla, sector_de=sector_de,
                                        estructura_de=estructura_de, igv=igv, criterio=criterio)
    except CostosError as exc:
        raise VadError(f'costo estándar: {exc}') from exc
    sin_costo.extend(faltan_m)
    ref_sin_costo.extend(faltan_r)
    bt = sum(1 for t in dim.modelo.tramos if t.nivel == 'BT')
    if bt:
        notas.append(f'BT: {bt} tramo(s) sin dimensionar en la T6; no se valoran en ninguna columna')
    contenido = {'dimensionamiento': dim.huella, 'sicodi': sicodi.fuente.huella,
                 'sicodi_firma': asdict(firma_sicodi),
                 'referencia_sicodi': referencia_tabla.fuente.huella, 'criterio': criterio,
                 'estandar': [asdict(e) for e in estandar], 'sin_costo': [asdict(x) for x in sin_costo],
                 'referencia': [asdict(e) for e in referencia], 'huecos': huecos}
    huella = hashlib.sha256(json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=str)
                            .encode('utf-8')).hexdigest()
    return CostoEstandar(dim, dim.huella, tuple(estandar), tuple(sin_costo), tuple(referencia), tuple(ref_sin_costo),
                         moneda, igv, criterio, tuple(huecos), huella, tuple(notas))


# ------------------------------------------------------------------------------------------- aVNR de un SER (RLGER)

REGLA_FFR = 'vad.ser.ffr.formula'
REGLA_ESTADO_100 = 'vad.ser.avnr.inversion_estado_100'
REGLA_MIXTA = 'vad.ser.avnr.inversion_mixta'
REGLA_TASA_ACTIVA = 'vad.tasa_actualizacion'
REGLA_FRC = 'vad.frc'


@dataclass(frozen=True)
class TasaPasiva:
    """La tasa pasiva de mercado de la SBS (efectiva anual, moneda nacional), entrada del perfil del periodo.

    ``valor`` en fracción (0,0197 es el 1,97 %). ``fecha``: el «último día hábil del año anterior a la fijación»
    (DCF Décima Primera del RLGER), en ISO. ``fuente``: de dónde sale (el reporte de la SBS). Sin valor por defecto.
    """

    valor: float
    fecha: str
    fuente: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.valor) or not 0.0 <= self.valor < 1.0:
            raise VadError(f'la tasa pasiva {self.valor!r} va en fracción efectiva anual (0,0197 es el 1,97 %)')
        try:
            date.fromisoformat(str(self.fecha))
        except ValueError as exc:
            raise VadError(f'la tasa pasiva tiene que decir su fecha en ISO (AAAA-MM-DD): {self.fecha!r}') from exc
        if not str(self.fuente or '').strip():
            raise VadError('la tasa pasiva tiene que decir su fuente (el reporte de la SBS)')


def _regla_ser(registro: RegistroNormativo, clave: str, fecha: str | None) -> ReglaVigente:
    try:
        return registro.regla(clave, fecha)
    except RegistroError as exc:
        raise VadError(f'el aVNR del SER se apoya en la regla {clave}: {exc}') from exc


def _tasa_activa(registro: RegistroNormativo, fecha: str | None) -> ReglaRemitida:
    """La tasa activa: ``vad.tasa_actualizacion`` remite a la del art. 79 de la LCE (UNA-TASA); la remisión la sigue el
    registro (:func:`~convertersmartgrid.dominio.registro_normativo.regla_remitida`), no este módulo."""
    try:
        return regla_remitida(registro, REGLA_TASA_ACTIVA, fecha)
    except RegistroError as exc:
        raise VadError(f'el aVNR del SER se apoya en la regla {REGLA_TASA_ACTIVA}: {exc}') from exc


def _cita(rv: ReglaVigente) -> dict[str, str]:
    r = rv.regla
    return {'cita': f'{rv.norma.acto}, {r.articulo_o_anexo}, {r.pagina}, líneas {r.lineas}', 'huella': rv.huella(),
            'estado_juridico': rv.estado}


def _factores(registro: RegistroNormativo, fecha: str | None) -> tuple[int, float, dict[str, dict[str, str]]]:
    """(vida útil, FRC, citas): el FRC de la LCE con la tasa activa del registro, contrastado con ``vad.frc``."""
    formula = _regla_ser(registro, REGLA_FFR, fecha)
    activa = _tasa_activa(registro, fecha)
    registrado = _regla_ser(registro, REGLA_FRC, fecha)
    valor = formula.regla.valor
    if not isinstance(valor, Mapping) or 'vida_util_anios' not in valor:
        raise VadError(f'la regla {REGLA_FFR} no da la vida útil en años (vida_util_anios)')
    vida = int(valor['vida_util_anios'])
    tasa = activa.valor
    if isinstance(tasa, bool) or not isinstance(tasa, (int, float)) or not math.isfinite(tasa):
        raise VadError(f'la tasa de {REGLA_TASA_ACTIVA} ({tasa!r}) no es un número')
    tasa = float(tasa)
    factor = frc(tasa, vida)
    if round(factor, 6) != round(float(registrado.regla.valor), 6):
        raise VadError(f'el FRC de {REGLA_TASA_ACTIVA} ({tasa:g}) y {vida} años es {factor:.6f} y {REGLA_FRC} registra '
                       f'{registrado.regla.valor}: el registro se contradice')
    citas = {c: _cita(v) for c, v in ((REGLA_FFR, formula), (REGLA_TASA_ACTIVA, activa.remision),
                                       (REGLA_FRC, registrado))}
    if activa.principal is not activa.remision:     # la remisión cita el TdR; el valor, la norma a la que remite
        citas[activa.principal.regla.clave] = _cita(activa.principal)
    return vida, factor, citas


def ffr(tasa_pasiva: float, *, registro: RegistroNormativo, fecha: str | None = None) -> float:
    """El factor del fondo de reposición del VNR de un SER: FAC(tasa pasiva, n) / FRC(tasa activa, n).

    DCF Décima Primera del RLGER (``vad.ser.ffr.formula``): «El factor del fondo de reposición aplicable al VNR
    resulta de dividir el factor de reposición sobre el factor de la anualidad del VNR». FAC = i/((1+i)^n − 1), el
    factor de fondo de amortización (interpretación registrada en la regla); n y la tasa activa salen del registro.
    ``tasa_pasiva`` en fracción efectiva anual. Con 1,97 % y 12 % a 30 años da 0,199494.
    """
    if not math.isfinite(tasa_pasiva) or not 0.0 <= tasa_pasiva < 1.0:
        raise VadError(f'la tasa pasiva {tasa_pasiva!r} va en fracción efectiva anual (0,0197 es el 1,97 %)')
    vida, factor_anualidad, _citas = _factores(registro, fecha)
    # FAC = i/((1+i)^n − 1) = FRC(i, n) − i (con i = 0, 1/n): sale de la única fórmula del FRC (UNA-TASA).
    fondo = frc(tasa_pasiva, vida) - tasa_pasiva
    return fondo / factor_anualidad


@dataclass(frozen=True)
class AvnrSer:
    """La anualidad del VNR estándar de un SER según su régimen de inversión (RLGER, art. 37.2 b y 37.3)."""

    moneda: str
    vnr: float | None
    frc: float
    avnr: float | None
    fp: float
    """Proporción de las inversiones de otras entidades (37.2 a): 0 es el 100 % del Estado; la da el perfil."""
    ffr: float | None
    retribucion: float | None
    """aVNR × fp."""
    reposicion: float | None
    """aVNR × (1 − fp) × FFR."""
    total: float | None
    """retribución + reposición (sin el OyM, que va aparte); ``None`` si falta el VNR o el FFR."""
    regla: str
    criterios: Mapping[str, Mapping[str, str]]
    tasa_pasiva: TasaPasiva | None
    huecos: tuple[str, ...] = ()


def avnr_ser(costo: CostoEstandar, *, fp: float, registro: RegistroNormativo, tasa_pasiva: TasaPasiva | None,
             fecha: str | None = None) -> AvnrSer:
    """aVNR del SER por régimen: Estado 100 % (fp = 0), aVNR × FFR; mixta, fp × aVNR + (1 − fp) × aVNR × FFR.

    ``fp`` es la proporción de inversiones de otras entidades, del perfil (sin valor por defecto). ``tasa_pasiva``,
    la de la SBS del perfil del periodo: sin ella, y con fp < 1, el FFR y el total quedan como hueco nombrado.
    """
    if not isinstance(costo, CostoEstandar):
        raise VadError('el aVNR del SER sale del costo estándar de la empresa modelo, no del VNR real')
    if not math.isfinite(fp) or not 0.0 <= fp <= 1.0:
        raise VadError(f'el factor de proporción fp={fp!r} va de 0 (100 % del Estado) a 1')
    regla = REGLA_ESTADO_100 if fp == 0 else REGLA_MIXTA
    _vida, factor_anualidad, criterios = _factores(registro, fecha)
    criterios[regla] = _cita(_regla_ser(registro, regla, fecha))
    huecos: list[str] = []
    vnr = costo.total_estandar
    if vnr is None:
        valorado = ', '.join(f'{t:,.2f} {m}' for m, t in costo.total_por_moneda.items()) or 'nada valorado'
        huecos.append(f'sin VNR estándar en {costo.moneda_anexo or "la moneda del anexo"} ({valorado})')
    elif not costo.completo:
        huecos.append(f'el VNR estándar no está completo ({len(costo.sin_costo)} elemento(s) sin costo, '
                      f'{len(costo.huecos)} hueco(s) del costo y {len(costo.dimensionamiento.huecos)} del '
                      f'dimensionamiento): el aVNR tampoco')
    avnr = None if vnr is None else vnr * factor_anualidad
    factor = None
    if fp < 1.0:
        if tasa_pasiva is None:
            huecos.append(f'sin la tasa pasiva de la SBS (entrada del perfil del periodo, con su fecha) no hay FFR '
                          f'({REGLA_FFR}): el aVNR del SER no se calcula')
        else:
            factor = ffr(tasa_pasiva.valor, registro=registro, fecha=fecha)
    retribucion = None if avnr is None else avnr * fp
    if fp == 1.0:
        reposicion = None if avnr is None else 0.0
    else:
        reposicion = None if avnr is None or factor is None else avnr * (1.0 - fp) * factor
    total = None if retribucion is None or reposicion is None else retribucion + reposicion
    return AvnrSer(costo.moneda_anexo, vnr, factor_anualidad, avnr, fp, factor, retribucion, reposicion, total, regla,
                   dict(sorted(criterios.items())), tasa_pasiva, tuple(huecos))


@dataclass(frozen=True)
class AnualidadVnrReal:
    """La anualidad del VNR de las instalaciones REALES adaptadas (Guía del VNR, RCD 232-2017) con los mismos factores
    del VAD (108:RF-24): entrada de la TIR de la empresa (arts. 70 y 71 de la LCE) y contraste con la empresa modelo.
    No es el aVNR del VAD, que sale siempre del costo estándar de la empresa modelo (:func:`avnr_ser`)."""

    vnr: float | None
    vida_util_anios: int
    factor_anualidad: float
    anualidad: float | None
    criterios: Mapping[str, Mapping[str, str]]
    huella_costos: str
    huecos: tuple[str, ...]


def anualidad_vnr_real(resultado, *, registro: RegistroNormativo, fecha: str | None = None) -> AnualidadVnrReal:
    """``resultado`` es un :class:`~convertersmartgrid.aplicacion.vad.vnr_guia.ResultadoVnr`; sin total (huecos), sin anualidad."""
    from ...aplicacion.vad.vnr_guia import ResultadoVnr
    if not isinstance(resultado, ResultadoVnr):
        raise VadError('la anualidad del VNR real sale de un cálculo de la Guía del VNR (vnr_guia.calcular_vnr)')
    vida, factor, criterios = _factores(registro, fecha)
    huecos = tuple(f'{x.item.codigo}: {x.motivo}' for x in resultado.huecos)
    vnr = resultado.total
    return AnualidadVnrReal(vnr, vida, factor, None if vnr is None else vnr * factor, dict(sorted(criterios.items())),
                            resultado.huella_costos, huecos)
