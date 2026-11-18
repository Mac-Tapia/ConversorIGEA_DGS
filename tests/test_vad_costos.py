"""Spec 108 T7 — costo estándar de la empresa modelo con el SICODI, y el aVNR del SER (108:RF-7, 108:RF-9).

La red sale del generador de la T6 (``test_vad_dimensionamiento``), con sus dos empresas sintéticas y sus semillas; los
conductores se renombran con códigos de costo sintéticos en la forma del VNR (código + letra de tensión). El SICODI es
un zip sintético con ``Instalacion.txt``, escrito en ``tmp_path`` con el formato que lee ``costos_fuentes.leer_sicodi``,
y se firma tal como llega (el zip y su miembro); el libro xlsx sintético solo se firma, porque ``leer_sicodi`` no lo lee.
Nada de datos reales ni códigos de una empresa. El registro es el de ``config/vad``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import math
import zipfile
from pathlib import Path

import pytest
from test_vad_dimensionamiento import (
    CONDUCTORES,
    EMPRESAS,
    NO_NORMALIZADAS,
    POTENCIAS,
    RANGOS,
    SECTORES,
    SEMILLAS,
    SUSTENTO,
    TIPOS,
    _entradas,
    _vnr,
)

from convertersmartgrid.aplicacion.costos_fuentes import leer_sicodi
from convertersmartgrid.dominio import registro_normativo as rn
from convertersmartgrid.dominio.registro_normativo import RegistroNormativo, cargar_registro
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.adaptadores.vad.costos import (
    CostoEstandar,
    TasaPasiva,
    avnr_ser,
    costo_estandar,
    ffr,
    firmar_sicodi,
    leer_sicodi_del_periodo,
)
from convertersmartgrid.adaptadores.vad.dimensionamiento import (
    RangoEconomico,
    TablaTransformadores,
    dimensionar,
)
from convertersmartgrid.adaptadores.vad.modelo_rural import armar_modelo_rural

pytest.importorskip('pandapower')

VAD = Path(__file__).resolve().parents[1] / 'config' / 'vad'
#: La tasa del VAD remite a la del art. 79 de la LCE (UNA-TASA), que está en el registro de normas.
NORMATIVA = VAD.parent / 'normativa'
#: Letra de tensión sintética de los códigos de costo (la forma del VNR: código + letra).
LETRA = 'G'
ESTRUCTURA = 'E_SINT'
#: Código de costo de cada conductor sintético de la T6, en la forma del VNR.
CODIGO = {c[0]: f'XS{n:02d}{int(c[2]):03d}{LETRA}' for n, c in enumerate(CONDUCTORES)}
#: (tipo de SED, kVA de una unidad) → código de costo sintético.
CODIGO_SED = {(t, p): f'XT{m}{int(p * 10):05d}{LETRA}' for m, t in enumerate(TIPOS) for p in POTENCIAS}
CABECERA = ('SECTOR TIPICO', 'GRUPO', 'FAMILIA', 'COD COSTINVER', 'COD TEN NOMI', 'DSC TEN NOMI', 'COD SECUNDARIO',
            'DSC SECUNDARIO', 'NOMBRE', 'COSTO MAT', 'COSTO STOCK', 'COSTO MO', 'COSTO TRANS', 'COSTO OBRA',
            'COSTO GASTOS GNRAL', 'COSTO INGENIERIA', 'COSTO INTERCALARIO', 'TOTAL')
FUENTE = {'resolucion': 'RES-SINT-001', 'anio': 2026, 'url': 'https://ejemplo.invalid/sicodi-sintetico',
          'fecha_descarga': '2026-11-15'}


def _precio(codigo: str, sector: str) -> float:
    """Un costo sintético distinto por código y por sector, para que un cruce equivocado se note."""
    return 1000.0 + int(hashlib.sha256(f'{codigo}|{sector}'.encode()).hexdigest()[:6], 16) % 9000


def _sicodi(carpeta: Path, nombre: str, *, sin: frozenset[str] = frozenset()) -> Path:
    """Zip sintético con Instalacion.txt: los conductores (familia RED) y las SED de todos los sectores."""
    filas = ['\t'.join(CABECERA)]
    codigos = [(c, 'RED MT SINTETICA') for c in CODIGO.values()] + [(c, 'SED SINTETICA') for c in CODIGO_SED.values()]
    for sector in SECTORES:
        for codigo, familia in codigos:
            if codigo in sin:
                continue
            total = _precio(codigo, sector)
            filas.append('\t'.join((sector, 'G1', familia, codigo[:-1], codigo[-1], 'TENSION SINT', ESTRUCTURA,
                                    'ESTRUCTURA SINT', f'NOMBRE {codigo}', *(['1.0'] * 8), f'{total!r}')))
    ruta = carpeta / f'{nombre}.zip'
    texto = '\n'.join(filas).encode()
    # Bytes deterministas: la fecha del miembro es fija (si no, zipfile pone la del reloj, a 2 s), así que la huella
    # depende solo del contenido. Un nombre ya escrito no se reescribe: si ya existe, ha de tener el mismo contenido,
    # y _RUTAS no puede quedar apuntando a un fichero que ya no es el que dio la tabla (VAD-BASE-FIX).
    if ruta.exists():
        with zipfile.ZipFile(ruta) as z:
            assert z.read(MIEMBRO) == texto, f'{ruta.name} ya existe con otro contenido'
    else:
        with zipfile.ZipFile(ruta, 'x') as z:
            z.writestr(zipfile.ZipInfo(MIEMBRO, date_time=FECHA_ZIP), texto)
    _RUTAS[hashlib.sha256(ruta.read_bytes()).hexdigest()] = ruta
    return ruta


#: Huella del zip sintético → su ruta, para firmarlo tal como llega en ``_costear``.
_RUTAS: dict[str, Path] = {}
#: El miembro del zip sintético y su fecha fija: sin ella, los bytes (y la huella) del zip dependen del reloj.
MIEMBRO = 'sicodi/Instalacion.txt'
FECHA_ZIP = (2026, 1, 1, 0, 0, 0)


def _leer(ruta: Path, moneda: str = 'USD'):
    return leer_sicodi(ruta, moneda=moneda, **FUENTE)


@pytest.fixture(scope='module')
def registro() -> RegistroNormativo:
    return cargar_registro(VAD, NORMATIVA)


@pytest.fixture(scope='module')
def carpeta(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp('sicodi')


_CASOS: dict = {}


def _caso(registro, carpeta, semilla, empresa, **cambios):
    """(vnr, dimensionamiento, entradas, ruta del SICODI): el dimensionamiento de la T6 con los códigos de costo."""
    clave = (semilla, empresa, tuple(sorted(cambios)))
    if clave in _CASOS:
        return _CASOS[clave]
    vnr = _vnr(semilla, empresa)
    for s in vnr.sections:
        s.conductor_code = CODIGO[s.conductor_code]
    for c in vnr.conductor_types:
        c.conductor_code = CODIGO[c.conductor_code]
    ruta = _sicodi(carpeta, f'completo_{semilla}_{empresa}')
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    entradas = {**_entradas(vnr, semilla),
                'rangos': [RangoEconomico(CODIGO[c], a, b, SUSTENTO) for c, a, b in RANGOS],
                'tabla': TablaTransformadores({(s, t): POTENCIAS for s in SECTORES for t in TIPOS}, huella,
                                              NO_NORMALIZADAS), **cambios}
    modelo = armar_modelo_rural(vnr, registro=registro)
    dim = dimensionar(modelo, registro=registro, **entradas)
    _CASOS[clave] = (vnr, dim, entradas, ruta)
    return _CASOS[clave]


def _costear(dim, entradas, tabla, registro, **cambios):
    """Valora con ``tabla``, firmada tal como llegó (el zip y su miembro) y con las huellas que declara el periodo."""
    firma = cambios['firma_sicodi'] if 'firma_sicodi' in cambios else firmar_sicodi(_RUTAS[tabla.fuente.huella])
    argumentos = {'sicodi': tabla, 'huella_sicodi': tabla.fuente.huella, 'firma_sicodi': firma,
                  'huella_miembro': firma.huella_miembro, 'registro': registro,
                  'sector_de': entradas['sector_de'], 'estructura_de': {a: ESTRUCTURA for a in entradas['sector_de']},
                  'tipo_de_sed': entradas['tipo_de_sed'], 'codigo_sed': CODIGO_SED, **cambios}
    return costo_estandar(dim, **argumentos)


def test_sin_dimensionar_no_hay_costo_estandar(registro, carpeta):
    """108:RF-7 — construir un costo estándar con el inventario sin dimensionar (el VNR o el modelo rural) lanza
    VadError, y también un CostoEstandar armado a mano sin su Dimensionamiento o sin su huella."""
    vnr, dim, entradas, ruta = _caso(registro, carpeta, SEMILLAS[0], EMPRESAS[0])
    tabla = _leer(ruta)
    for inventario in (vnr, dim.modelo):
        with pytest.raises(VadError, match='Dimensionamiento'):
            _costear(inventario, entradas, tabla, registro)
    with pytest.raises(VadError, match='huella'):
        _costear(dataclasses.replace(dim, huella=''), entradas, tabla, registro)
    with pytest.raises(VadError, match='Dimensionamiento'):
        CostoEstandar(dim.modelo, 'a' * 64, (), (), (), (), 'USD', 'excluido', {})
    with pytest.raises(VadError, match='huella'):
        CostoEstandar(dim, 'b' * 64, (), (), (), (), 'USD', 'excluido', {})


@pytest.mark.parametrize('empresa', EMPRESAS)
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_cada_elemento_valorado_lleva_su_fuente(registro, carpeta, semilla, empresa):
    """108:RF-7, 108:RF-9 — cada elemento valorado de la red dimensionada lleva la fuente del SICODI, la moneda y el IGV
    de vad.igv_costos; su costo es metrado × costo unitario del SICODI, y el VNR real solo va en la referencia."""
    _, dim, entradas, ruta = _caso(registro, carpeta, semilla, empresa)
    tabla = _leer(ruta)
    costo = _costear(dim, entradas, tabla, registro)
    igv = registro.regla('vad.igv_costos')
    assert costo.estandar and costo.referencia
    assert {e.clase for e in costo.estandar} == {'conductor_mt', 'sed'}
    for e in costo.estandar + costo.referencia:
        assert e.fuente['huella'] == tabla.fuente.huella and e.fuente['resolucion'] == FUENTE['resolucion'], e
        assert e.fuente['url'] == FUENTE['url'] and e.fuente['fecha_descarga'] == FUENTE['fecha_descarga'], e
        assert e.moneda == igv.regla.moneda == 'USD' and e.igv == igv.regla.igv == 'excluido', e
        assert e.criterio['regla'] == 'vad.igv_costos' and e.criterio['huella'] == igv.huella(), e
        assert e.criterio['estado_juridico'] == igv.estado and 'líneas' in e.criterio['cita'], e
        sector = entradas['sector_de'][e.alimentador]
        assert math.isclose(e.costo_unitario, _precio(e.codigo, sector), rel_tol=1e-12), e
        assert math.isclose(e.costo, e.cantidad * e.costo_unitario, rel_tol=1e-12), e

    largo = {t.tramo: t.longitud_m for t in dim.modelo.tramos}
    km: dict = {}
    for t in dim.tramos:
        if t.conductor_modelo is not None:
            clave = (t.alimentador, t.conductor_modelo)
            km[clave] = km.get(clave, 0.0) + largo[t.tramo] / 1000.0
    conductores = {(e.alimentador, e.codigo): e for e in costo.estandar if e.clase == 'conductor_mt'}
    assert set(conductores) == set(km)
    for clave, e in conductores.items():
        assert e.unidad == 'km' and math.isclose(e.cantidad, km[clave], rel_tol=1e-12), clave
    seds = {e.elemento: e for e in costo.estandar if e.clase == 'sed'}
    dimensionadas = {s.sed: s for s in dim.sed if s.kva_modelo is not None}
    assert set(seds) == set(dimensionadas)
    for sed, e in seds.items():
        s = dimensionadas[sed]
        assert e.codigo == CODIGO_SED[(entradas['tipo_de_sed'][sed], s.kva_modelo / s.modulos)], sed
        assert e.cantidad == s.modulos, sed

    referencia_sed = {e.elemento: e for e in costo.referencia if e.clase == 'sed'}
    for s in dim.sed:
        assert referencia_sed[s.sed].codigo == CODIGO_SED[(entradas['tipo_de_sed'][s.sed], s.kva_real)], s.sed
        if s.cambia:
            assert seds[s.sed].codigo != referencia_sed[s.sed].codigo, s.sed
    total = sum(e.costo for e in costo.estandar)
    assert costo.total_por_moneda == {'USD': pytest.approx(total, rel=1e-12)}
    assert costo.total_estandar == pytest.approx(total, rel=1e-12)
    referencia = sum(e.costo for e in costo.referencia)
    assert costo.referencia_por_moneda == {'USD': pytest.approx(referencia, rel=1e-12)}
    diferencia, motivo = costo.diferencia
    assert diferencia == pytest.approx(total - referencia, rel=1e-9, abs=1e-6) and not motivo
    assert not costo.huecos and costo.huella and len(costo.huella) == 64
    assert costo.huella_dimensionamiento == dim.huella


def test_lo_que_no_cruza_con_el_sicodi_queda_nombrado_y_fuera_del_total(registro, carpeta):
    """108:RF-7 — un conductor y una SED de la red dimensionada sin costo en el SICODI quedan nombrados con su motivo
    y fuera del total; un tramo sin dimensionar no se valora con su conductor real."""
    _, dim, entradas, ruta = _caso(registro, carpeta, SEMILLAS[1], EMPRESAS[0])
    completo = _costear(dim, entradas, _leer(ruta), registro)
    assert {e.clase for e in completo.estandar} == {'conductor_mt', 'sed'}
    conductor = min(e.codigo for e in completo.estandar if e.clase == 'conductor_mt')
    sed = min((e for e in completo.estandar if e.clase == 'sed'), key=lambda e: e.elemento)
    faltan = frozenset({conductor, sed.codigo})
    tabla = _leer(_sicodi(carpeta, 'sin_dos', sin=faltan))
    costo = _costear(dim, entradas, tabla, registro)
    assert not any(e.codigo in faltan for e in costo.estandar)
    nombrados = {x.codigo for x in costo.sin_costo}
    assert faltan <= nombrados
    for x in costo.sin_costo:
        if x.codigo in faltan and not x.motivo.startswith('no dimensionado'):
            assert x.motivo and x.codigo[:-1] in x.motivo, x
    assert any(x.elemento == sed.elemento and x.clase == 'sed' for x in costo.sin_costo)
    total = sum(e.costo for e in costo.estandar)
    assert costo.total_por_moneda == {'USD': pytest.approx(total, rel=1e-12)}
    perdido = sum(e.costo for e in completo.estandar if e.codigo in faltan)
    assert perdido > 0 and completo.total_estandar - costo.total_estandar == pytest.approx(perdido, rel=1e-9)
    assert not costo.completo

    sin_rangos = _caso(registro, carpeta, SEMILLAS[1], EMPRESAS[0], rangos=[])[1:3]
    costo = _costear(sin_rangos[0], sin_rangos[1], _leer(ruta), registro)
    assert not any(e.clase == 'conductor_mt' for e in costo.estandar)
    no_dimensionados = {x.elemento for x in costo.sin_costo if 'no dimensionado' in x.motivo}
    assert no_dimensionados == {t.tramo for t in sin_rangos[0].tramos}
    assert any(e.clase == 'conductor_mt' for e in costo.referencia)


def test_dos_monedas_no_se_suman(registro, carpeta):
    """108:RF-9 — el estándar y la referencia en monedas distintas no se suman ni se restan; un SICODI en otra moneda
    que la del anexo se nombra, no se convierte, y el total en la moneda del anexo no existe."""
    _, dim, entradas, ruta = _caso(registro, carpeta, SEMILLAS[0], EMPRESAS[1])
    usd, pen = _leer(ruta, 'USD'), _leer(_sicodi(carpeta, 'otra_moneda'), 'PEN')
    costo = _costear(dim, entradas, usd, registro, sicodi_referencia=pen)
    assert set(costo.total_por_moneda) == {'USD'} and set(costo.referencia_por_moneda) == {'PEN'}
    assert all(e.moneda == 'PEN' for e in costo.referencia) and all(e.moneda == 'USD' for e in costo.estandar)
    diferencia, motivo = costo.diferencia
    assert diferencia is None and 'PEN' in motivo and 'USD' in motivo
    assert costo.total_estandar == pytest.approx(sum(e.costo for e in costo.estandar), rel=1e-12)
    assert any('PEN' in h and 'USD' in h and 'referencia' in h for h in costo.huecos)

    costo = _costear(dim, entradas, pen, registro, huella_sicodi=pen.fuente.huella)
    assert set(costo.total_por_moneda) == {'PEN'} and costo.total_estandar is None
    assert any('PEN' in h and 'USD' in h and 'estándar' in h for h in costo.huecos)
    assert costo.diferencia[0] is None and not costo.completo


def test_el_sicodi_se_lee_por_su_huella(registro, carpeta):
    """108:RF-9 — el SICODI que no tiene la huella que declara el periodo no valora nada, y uno distinto del que dio la
    tabla de transformadores de la T6 se nombra."""
    _, dim, entradas, ruta = _caso(registro, carpeta, SEMILLAS[0], EMPRESAS[0])
    tabla = _leer(ruta)
    with pytest.raises(VadError, match='huella'):
        _costear(dim, entradas, tabla, registro, huella_sicodi='0' * 64)
    otro = _leer(_sicodi(carpeta, 'otro_periodo', sin=frozenset({next(iter(CODIGO_SED.values()))})))
    costo = _costear(dim, entradas, otro, registro)
    assert any(tabla.fuente.huella in h and otro.fuente.huella in h for h in costo.huecos)
    assert not costo.completo


def test_la_huella_del_sicodi_es_la_del_fichero_tal_como_llega(registro, carpeta, tmp_path):
    """108:RF-9 — el SICODI en zip se firma tal como llega y, además, su miembro Instalacion.txt: el mismo miembro
    vuelto a comprimir cambia la huella del zip y no la del miembro; un miembro cambiado da VadError aunque se vuelva a
    declarar el zip, y también si el periodo no declara la huella del miembro o la tabla no sale del fichero firmado."""
    _, dim, entradas, ruta = _caso(registro, carpeta, SEMILLAS[0], EMPRESAS[0])
    with zipfile.ZipFile(ruta) as z:
        contenido = z.read('sicodi/Instalacion.txt')
    firma = firmar_sicodi(ruta)
    assert firma.formato == 'zip' and firma.huella == hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert firma.miembro == 'sicodi/Instalacion.txt' and firma.huella_miembro == hashlib.sha256(contenido).hexdigest()
    recomprimido = tmp_path / 'recomprimido.zip'
    with zipfile.ZipFile(recomprimido, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('otra_carpeta/Instalacion.txt', contenido)
    otra = firmar_sicodi(recomprimido)
    assert otra.huella != firma.huella and otra.huella_miembro == firma.huella_miembro
    tabla = _leer(ruta)
    assert _costear(dim, entradas, tabla, registro).estandar
    with pytest.raises(VadError, match='Instalacion.txt'):
        _costear(dim, entradas, tabla, registro, huella_miembro=None)
    mutado = tmp_path / 'mutado.zip'
    with zipfile.ZipFile(mutado, 'w') as z:
        z.writestr('sicodi/Instalacion.txt', contenido.replace(b'\t1.0\t', b'\t1.5\t', 1))
    firma_mutada, tabla_mutada = firmar_sicodi(mutado), _leer(mutado)
    assert firma_mutada.huella_miembro != firma.huella_miembro
    with pytest.raises(VadError, match='miembro'):
        _costear(dim, entradas, tabla_mutada, registro, firma_sicodi=firma_mutada, huella_sicodi=firma_mutada.huella,
                 huella_miembro=firma.huella_miembro)
    with pytest.raises(VadError, match='no sale de ese fichero'):
        _costear(dim, entradas, tabla_mutada, registro, firma_sicodi=firma, huella_sicodi=firma.huella)
    leida, firma_leida, huecos = leer_sicodi_del_periodo(ruta, huella_sicodi=firma.huella,
                                                         huella_miembro=firma.huella_miembro, moneda='USD', **FUENTE)
    assert leida is not None and leida.fuente.huella == firma.huella and firma_leida == firma and huecos == ()
    with pytest.raises(VadError, match='miembro'):
        leer_sicodi_del_periodo(mutado, huella_sicodi=firma_mutada.huella, huella_miembro=firma.huella_miembro,
                                moneda='USD', **FUENTE)


def test_un_sicodi_en_libro_xlsx_es_un_hueco_nombrado(tmp_path):
    """108:RF-9 — un SICODI que llega como libro xlsx (el RR VAD de la referencia es un xlsx) se firma entero, sin
    miembro, y se comprueba con lo que declara el periodo; como costos_fuentes.leer_sicodi solo lee el zip, no hay tabla
    y el hueco lo nombra. Un zip sin Instalacion.txt o un fichero que no es zip ni libro se rechazan. El cruce (tipo de
    SED, kVA) → código del SICODI es una entrada sin valor por defecto."""
    openpyxl = pytest.importorskip('openpyxl')
    libro = tmp_path / 'sicodi_sintetico.xlsx'
    wb = openpyxl.Workbook()
    wb.active.title = 'Costos sinteticos'
    wb.active.append(list(CABECERA))
    wb.active.append(['ST-SINT', 'G1', 'RED MT SINTETICA', 'XS00', 'G', 'TENSION SINT', ESTRUCTURA, 'ESTRUCTURA SINT',
                      'NOMBRE XS00G', *([1.0] * 8), 1234.5])
    wb.save(libro)
    firma = firmar_sicodi(libro)
    assert firma.formato == 'xlsx' and firma.huella == hashlib.sha256(libro.read_bytes()).hexdigest()
    assert not firma.miembro and not firma.huella_miembro
    tabla, firma_leida, huecos = leer_sicodi_del_periodo(libro, huella_sicodi=firma.huella, moneda='USD', **FUENTE)
    assert tabla is None and firma_leida == firma and len(huecos) == 1
    assert 'xlsx' in huecos[0] and 'leer_sicodi' in huecos[0] and firma.huella in huecos[0]
    with pytest.raises(VadError, match='huella'):
        leer_sicodi_del_periodo(libro, huella_sicodi='0' * 64, moneda='USD', **FUENTE)
    with pytest.raises(VadError, match='miembro'):
        leer_sicodi_del_periodo(libro, huella_sicodi=firma.huella, huella_miembro='a' * 64, moneda='USD', **FUENTE)
    sin_miembro = tmp_path / 'sin_miembro.zip'
    with zipfile.ZipFile(sin_miembro, 'w') as z:
        z.writestr('sicodi/Armado.txt', 'x')
    with pytest.raises(VadError, match='Instalacion.txt'):
        firmar_sicodi(sin_miembro)
    texto = tmp_path / 'Instalacion.txt'
    texto.write_text('\t'.join(CABECERA), encoding='utf-8')
    with pytest.raises(VadError, match='zip'):
        firmar_sicodi(texto)
    codigo_sed = inspect.signature(costo_estandar).parameters['codigo_sed']
    assert codigo_sed.kind is inspect.Parameter.KEYWORD_ONLY and codigo_sed.default is inspect.Parameter.empty


def _sin(registro: RegistroNormativo, clave: str) -> RegistroNormativo:
    return RegistroNormativo({a: dataclasses.replace(n, reglas=tuple(r for r in n.reglas if r.clave != clave))
                              for a, n in registro.normas.items()})


def test_sin_la_regla_del_igv_no_se_valora(registro, carpeta):
    """108:RF-9 — la moneda y el IGV salen de vad.igv_costos: sin esa regla, no hay costo estándar."""
    _, dim, entradas, ruta = _caso(registro, carpeta, SEMILLAS[0], EMPRESAS[0])
    with pytest.raises(VadError, match=r'vad\.igv_costos'):
        _costear(dim, entradas, _leer(ruta), _sin(registro, 'vad.igv_costos'))


def test_ffr_del_rlger_reproduce_el_libro(registro):
    """108:RF-9 — FFR = FAC(tasa pasiva, 30) / FRC(12 %, 30), del registro (RLGER, DCF Décima Primera): con la tasa
    pasiva de 1,97 % da 0,199494 a 6 decimales. La tasa activa es la del art. 79 de la LCE, a la que remite
    ``vad.tasa_actualizacion`` (UNA-TASA)."""
    assert round(ffr(0.0197, registro=registro), 6) == 0.199494
    formula = registro.regla('vad.ser.ffr.formula')
    assert formula.norma.acto == 'DS 018-2020-EM' and formula.obligatoria
    assert formula.regla.valor['vida_util_anios'] == 30
    i, n = 0.0453, 30
    assert hasattr(rn, 'regla_remitida'), 'el registro no resuelve la remisión de vad.tasa_actualizacion'
    activa = rn.regla_remitida(registro, 'vad.tasa_actualizacion').valor
    esperado = (i / ((1 + i) ** n - 1)) / (activa * (1 + activa) ** n / ((1 + activa) ** n - 1))
    assert math.isclose(ffr(i, registro=registro), esperado, rel_tol=1e-12)
    with pytest.raises(VadError, match=r'vad\.ser\.ffr\.formula'):
        ffr(0.0197, registro=_sin(registro, 'vad.ser.ffr.formula'))
    with pytest.raises(VadError, match='fracción'):
        ffr(1.97, registro=registro)


def test_avnr_del_ser_por_regimen(registro, carpeta):
    """108:RF-9 — aVNR del SER: con el 100 % del Estado, aVNR × FFR (art. 37.2 b); mixta, fp × aVNR + (1 − fp) × aVNR ×
    FFR (art. 37.3); sin la tasa pasiva del perfil, hueco nombrado y sin total."""
    _, dim, entradas, ruta = _caso(registro, carpeta, SEMILLAS[2], EMPRESAS[1])
    costo = _costear(dim, entradas, _leer(ruta), registro)
    assert costo.total_estandar is not None and costo.total_estandar > 0
    tasa = TasaPasiva(0.0197, '2025-12-31', 'reporte SBS sintético')
    factor_anualidad = registro.regla('vad.frc').regla.valor
    factor = ffr(tasa.valor, registro=registro)
    avnr = costo.total_estandar * factor_anualidad

    estado = avnr_ser(costo, fp=0.0, registro=registro, tasa_pasiva=tasa)
    assert estado.regla == 'vad.ser.avnr.inversion_estado_100' and estado.ffr == pytest.approx(factor, rel=1e-12)
    assert estado.avnr == pytest.approx(avnr, rel=1e-5)
    assert estado.total == pytest.approx(estado.avnr * factor, rel=1e-12)
    assert 'DS 018-2020-EM' in estado.criterios['vad.ser.avnr.inversion_estado_100']['cita']

    fp = 0.37
    mixta = avnr_ser(costo, fp=fp, registro=registro, tasa_pasiva=tasa)
    assert mixta.regla == 'vad.ser.avnr.inversion_mixta'
    assert mixta.retribucion == pytest.approx(fp * mixta.avnr, rel=1e-12)
    assert mixta.reposicion == pytest.approx((1 - fp) * mixta.avnr * factor, rel=1e-12)
    assert mixta.total == pytest.approx(fp * mixta.avnr + (1 - fp) * mixta.avnr * factor, rel=1e-12)
    assert estado.total < mixta.total < mixta.avnr

    sin_tasa = avnr_ser(costo, fp=fp, registro=registro, tasa_pasiva=None)
    assert sin_tasa.ffr is None and sin_tasa.total is None and sin_tasa.avnr == pytest.approx(mixta.avnr)
    assert any('tasa pasiva' in h for h in sin_tasa.huecos)
    with pytest.raises(VadError, match='fp'):
        avnr_ser(costo, fp=1.5, registro=registro, tasa_pasiva=tasa)
    with pytest.raises(VadError, match='VNR real'):
        avnr_ser(dim, fp=0.0, registro=registro, tasa_pasiva=tasa)
    with pytest.raises(VadError, match='fecha'):
        TasaPasiva(0.0197, '', 'reporte SBS sintético')
