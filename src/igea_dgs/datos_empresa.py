"""El libro de la empresa con tasas de falla, tiempos y costes (spec 012, RF-6 a RF-18, RF-62 a RF-66).

Sin estas cifras, la confiabilidad, la ubicación de reconectadores y la de condensadores
no se ejecutan: el BD_Equipo trae todas las tasas a cero (``studies._TASAS_FALLA``) y
``ComRel3`` daría SAIFI = SAIDI = ENS = 0, un resultado limpio y sin sentido. El usuario
decidió (2026-10-11) que las da la empresa, de su histórico de interrupciones, y que no
se rellenan con valores típicos.

El libro tiene una hoja por grupo de datos (RF-62). En cada hoja, la fila 1 son los nombres
de las columnas, la fila 2 sus unidades y los datos van desde la fila 3: así la unidad se
lee del propio libro y uno en otra unidad se rechaza (RF-16) en vez de dar fallas mil veces
mayores. Todo se valida aquí, antes de abrir DIgSILENT (plan, «Decisiones»): el operador se
entera de una celda vacía al subir el libro, no cuando el guion ya está en marcha.

Nada de una distribuidora (constitución P13): las clases de elemento son genéricas, la
moneda es la que escriba la empresa y la plantilla sale sin cifras.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

#: Clases de elemento que reconoce el libro (RF-10), con su nombre en la hoja.
CLASES = {
    'linea': 'Línea aérea de media tensión',
    'cable': 'Cable subterráneo de media tensión',
    'transformador': 'Transformador de distribución',
    'barra': 'Barra',
    'interruptor': 'Interruptor',
    'reconectador': 'Reconectador',
    'fusible': 'Fusible',
    'seccionador': 'Seccionador',
}
#: Las que llevan la tasa por kilómetro y año; las demás, por unidad y año (RF-9).
POR_KM = ('linea', 'cable')
#: Las que despejan la falla; el seccionador solo aísla y repone (RF-27).
DESPEJAN = ('interruptor', 'reconectador', 'fusible')

#: Conceptos de la hoja de tiempos (RF-12, RF-13), en minutos.
TIEMPOS = {'localizacion': 'Localización de la falla', 'manual': 'Maniobra manual',
           'telemandada': 'Maniobra telemandada'}
#: Conceptos de la hoja de costes (RF-15).
COSTES = {'energia': 'Energía de pérdidas', 'descuento': 'Tasa de descuento'}


@dataclass(frozen=True)
class Columna:
    clave: str
    titulo: str
    unidad: str
    obligatoria: bool = True
    numero: bool = True


@dataclass(frozen=True)
class Hoja:
    clave: str
    titulo: str
    columnas: tuple[Columna, ...]


#: Las hojas del libro (RF-62), en el orden de la plantilla.
HOJAS = (
    Hoja('tasas', 'Tasas de falla', (
        Columna('clase', 'Clase', '-', numero=False),
        Columna('tipo', 'Tipo del proyecto', '-', obligatoria=False, numero=False),
        Columna('permanente', 'Falla permanente', '1/año; por km en líneas y cables'),
        Columna('transitoria', 'Falla transitoria', '1/año; por km en líneas y cables',
                obligatoria=False),
        Columna('reparacion', 'Tiempo de reparación', 'h'),
    )),
    Hoja('tiempos', 'Tiempos', (
        Columna('concepto', 'Concepto', '-', numero=False),
        Columna('valor', 'Valor', 'min'),
    )),
    Hoja('telemandados', 'Telemandados', (
        Columna('codigo', 'Código del equipo', '-', numero=False),
    )),
    Hoja('bancos', 'Bancos de condensadores', (
        Columna('potencia', 'Potencia por paso', 'kvar'),
        Columna('pasos', 'Pasos', '-'),
        Columna('fases', 'Fases', 'trifásico o monofásico', numero=False),
        Columna('inversion', 'Inversión', 'moneda'),
        Columna('vida', 'Vida útil', 'años'),
    )),
    Hoja('costes', 'Costes', (
        Columna('concepto', 'Concepto', '-', numero=False),
        Columna('valor', 'Valor', '-'),
        Columna('unidad', 'Unidad', '-', numero=False),
    )),
)
POR_CLAVE = {h.clave: h for h in HOJAS}

#: Hojas que necesita cada estudio (RF-63): sin ellas, solo ese estudio queda bloqueado.
NECESITA = {
    'fiabilidad': ('tasas', 'tiempos'),
    'reconectadores': ('tasas', 'tiempos'),
    'condensadores': ('bancos', 'costes'),
}


class DatosEmpresaError(ValueError):
    """Libro que no se puede usar; ``errores`` dice cada hoja, fila y columna (RF-16)."""

    def __init__(self, errores: list[str]):
        self.errores = list(errores)
        super().__init__('El libro de la empresa no se puede usar:\n' + '\n'.join(self.errores))


@dataclass(frozen=True)
class Tasa:
    """Modelo de falla y reparación de una clase o de un tipo (RF-8, RF-11)."""
    clase: str
    permanente: float          # 1/año, o 1/(km·año) en líneas y cables (RF-9)
    transitoria: float | None
    reparacion_h: float
    tipo: str = ''


@dataclass(frozen=True)
class Banco:
    """Un banco de condensadores de la empresa (RF-14) y su coste anual (RF-64)."""
    potencia_kvar: float
    pasos: int
    trifasico: bool
    inversion: float
    vida_anios: float
    coste_anual: float | None      # sin tasa de descuento, no se calcula


@dataclass
class Libro:
    nombre: str = ''
    tasas: dict[str, Tasa] = field(default_factory=dict)
    tasas_por_tipo: dict[str, Tasa] = field(default_factory=dict)
    tiempos_min: dict[str, float] = field(default_factory=dict)
    telemandados: tuple[str, ...] = ()
    bancos: list[Banco] = field(default_factory=list)
    coste_energia_kwh: float | None = None
    moneda: str = ''
    tasa_descuento: float | None = None        # fracción anual (0,12 = 12 %)
    hojas_que_faltan: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def a_dict(self) -> dict[str, Any]:
        """Lo que viaja en el plan del guion y se guarda con el proyecto."""
        return {
            'nombre': self.nombre,
            'tasas': {k: asdict(v) for k, v in sorted(self.tasas.items())},
            'tasas_por_tipo': {k: asdict(v) for k, v in sorted(self.tasas_por_tipo.items())},
            'tiempos_min': dict(self.tiempos_min), 'telemandados': list(self.telemandados),
            'bancos': [asdict(b) for b in self.bancos],
            'coste_energia_kwh': self.coste_energia_kwh, 'moneda': self.moneda,
            'tasa_descuento': self.tasa_descuento,
            'hojas_que_faltan': list(self.hojas_que_faltan), 'avisos': list(self.avisos),
        }

    @classmethod
    def desde_dict(cls, d: Mapping[str, Any]) -> 'Libro':
        return cls(
            nombre=str(d.get('nombre') or ''),
            tasas={k: Tasa(**v) for k, v in (d.get('tasas') or {}).items()},
            tasas_por_tipo={k: Tasa(**v) for k, v in (d.get('tasas_por_tipo') or {}).items()},
            tiempos_min={k: float(v) for k, v in (d.get('tiempos_min') or {}).items()},
            telemandados=tuple(d.get('telemandados') or ()),
            bancos=[Banco(**b) for b in d.get('bancos') or ()],
            coste_energia_kwh=d.get('coste_energia_kwh'), moneda=str(d.get('moneda') or ''),
            tasa_descuento=d.get('tasa_descuento'),
            hojas_que_faltan=list(d.get('hojas_que_faltan') or ()),
            avisos=list(d.get('avisos') or ()))


# --------------------------------------------------------------------------- utilidades
def _norm(texto: Any) -> str:
    """Sin tildes, mayúsculas ni espacios de más: «Línea aérea» = «linea aerea»."""
    s = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().split())


_CLASE_POR_NOMBRE = {_norm(v): k for k, v in CLASES.items()} | {k: k for k in CLASES}
_TIEMPO_POR_NOMBRE = {_norm(v): k for k, v in TIEMPOS.items()}
_COSTE_POR_NOMBRE = {_norm(v): k for k, v in COSTES.items()}


def anualidad(inversion: float, tasa: float, vida_anios: float) -> float:
    """Coste anual de un banco, el que pide DIgSILENT (RF-64): la anualidad de su inversión.

    Con tasa cero, la inversión entre la vida útil (RF-65): la fórmula da 0/0.
    """
    if vida_anios <= 0:
        raise ValueError('la vida útil tiene que ser mayor que cero')
    if tasa == 0:
        return inversion / vida_anios
    f = (1 + tasa) ** vida_anios
    return inversion * tasa * f / (f - 1)


def tasa_para(libro: Libro, clase: str, tipo: str | None = None) -> Tasa | None:
    """La fila del tipo si la hay (RF-11); si no, la de su clase."""
    if tipo and tipo in libro.tasas_por_tipo:
        return libro.tasas_por_tipo[tipo]
    return libro.tasas.get(clase)


def que_falta(libro: Libro | None, estudio: str) -> list[str]:
    """Lo que le falta al libro para un estudio (RF-18, RF-19, RF-63); vacío si nada."""
    if estudio not in NECESITA:
        return []
    if libro is None:
        return ['el libro de la empresa (tasas de falla, tiempos y costes)']
    out = [f'la hoja «{POR_CLAVE[h].titulo}»' for h in NECESITA[estudio]
           if POR_CLAVE[h].titulo in libro.hojas_que_faltan]
    if estudio == 'condensadores':
        if not libro.bancos and POR_CLAVE['bancos'].titulo not in libro.hojas_que_faltan:
            out.append('los bancos de condensadores')
        if libro.coste_energia_kwh is None and POR_CLAVE['costes'].titulo not in libro.hojas_que_faltan:
            out.append(f"el coste de la «{COSTES['energia']}»")
    return out


def clases_que_faltan(libro: Libro, conteo: Mapping[str, int]) -> list[str]:
    """Clases que la red tiene y el libro no, con cuántos elementos (RF-17).

    El conteo que llega es el de los elementos sin fila de tipo (RF-11): una clase cubierta
    entera por filas de tipo no hace falta.
    """
    return [f'{CLASES[c]} ({n} elemento{"s" if n != 1 else ""})'
            for c, n in sorted(conteo.items()) if n and c in CLASES and c not in libro.tasas]


# --------------------------------------------------------------------------- lectura
def _valor(celda: Any) -> Any:
    if isinstance(celda, str):
        celda = celda.strip()
        return celda or None
    return celda


def _numero(texto: Any) -> float | None:
    if isinstance(texto, bool):
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    try:
        return float(str(texto).replace(',', '.'))
    except ValueError:
        return None


def _leer_hoja(ws, hoja: Hoja, errores: list[str]) -> list[tuple[int, dict[str, Any]]]:
    """Filas de datos de una hoja, con su número; los errores de forma, en ``errores``."""
    filas = [tuple(_valor(c) for c in r) for r in ws.iter_rows(values_only=True)]
    titulos = filas[0] if filas else ()
    unidades = filas[1] if len(filas) > 1 else ()
    posicion: dict[str, int] = {}
    for col in hoja.columnas:
        i = next((k for k, t in enumerate(titulos) if _norm(t) == _norm(col.titulo)), None)
        if i is None:
            if col.obligatoria:
                errores.append(f'Hoja «{hoja.titulo}», fila 1: falta la columna «{col.titulo}».')
            continue
        posicion[col.clave] = i
        unidad = unidades[i] if i < len(unidades) else None
        if col.unidad != '-' and _norm(unidad) != _norm(col.unidad):
            errores.append(f'Hoja «{hoja.titulo}», fila 2, columna «{col.titulo}»: la unidad es '
                           f'«{unidad or ""}» y la plantilla pide «{col.unidad}».')
    out = []
    for n, fila in enumerate(filas[2:], start=3):
        if all(v is None for v in fila):
            continue
        datos = {}
        for col in hoja.columnas:
            i = posicion.get(col.clave)
            v = fila[i] if i is not None and i < len(fila) else None
            donde = f'Hoja «{hoja.titulo}», fila {n}, columna «{col.titulo}»'
            if v is None:
                if col.obligatoria:
                    errores.append(f'{donde}: está vacía y es obligatoria.')
                datos[col.clave] = None
                continue
            if col.numero:
                x = _numero(v)
                if x is None or not math.isfinite(x):
                    errores.append(f'{donde}: «{v}» no es un número.')
                    v = None
                elif x < 0:
                    errores.append(f'{donde}: {x:g} es negativo.')
                    v = None
                else:
                    v = x
            datos[col.clave] = v
        out.append((n, datos))
    return out


def _tasas(filas, libro: Libro, errores: list[str]) -> None:
    hoja = POR_CLAVE['tasas'].titulo
    for n, d in filas:
        clase = _CLASE_POR_NOMBRE.get(_norm(d['clase'])) if d['clase'] else None
        if d['clase'] and clase is None:
            errores.append(f'Hoja «{hoja}», fila {n}, columna «Clase»: «{d["clase"]}» no es una '
                           'clase conocida; las que hay son ' + ', '.join(CLASES.values()) + '.')
            continue
        if clase is None or None in (d['permanente'], d['reparacion']):
            continue
        tipo = str(d['tipo'] or '')
        if tipo and clase not in POR_KM:
            errores.append(f'Hoja «{hoja}», fila {n}, columna «Tipo del proyecto»: solo las líneas y '
                           f'los cables llevan fila por tipo, no «{CLASES[clase]}».')
            continue
        tasa = Tasa(clase, d['permanente'], d['transitoria'], d['reparacion'], tipo)
        destino, clave = (libro.tasas_por_tipo, tipo) if tipo else (libro.tasas, clase)
        if clave in destino:
            errores.append(f'Hoja «{hoja}», fila {n}: {"el tipo " + tipo if tipo else CLASES[clase]} '
                           'ya tiene otra fila.')
            continue
        destino[clave] = tasa


def _por_concepto(filas, hoja: str, nombres: Mapping[str, str], errores) -> dict[str, tuple[int, dict]]:
    out = {}
    for n, d in filas:
        clave = nombres.get(_norm(d['concepto'])) if d['concepto'] else None
        if d['concepto'] and clave is None:
            errores.append(f'Hoja «{hoja}», fila {n}, columna «Concepto»: «{d["concepto"]}» no se '
                           'reconoce; los que hay son ' + ', '.join(
                               v for k, v in {**TIEMPOS, **COSTES}.items() if k in nombres.values()) + '.')
        elif clave is not None:
            out[clave] = (n, d)
    return out


def _tiempos(filas, libro: Libro, errores: list[str]) -> None:
    hoja = POR_CLAVE['tiempos'].titulo
    filas_por_concepto = _por_concepto(filas, hoja, _TIEMPO_POR_NOMBRE, errores)
    for clave, (_n, d) in filas_por_concepto.items():
        if d['valor'] is not None:
            libro.tiempos_min[clave] = d['valor']
    for clave in ('localizacion', 'manual'):
        if clave not in filas_por_concepto:          # la que está con el valor vacío ya se dijo
            errores.append(f'Hoja «{hoja}»: falta la fila «{TIEMPOS[clave]}».')


def _bancos(filas, libro: Libro, errores: list[str], tasa: float | None) -> None:
    hoja = POR_CLAVE['bancos'].titulo
    for n, d in filas:
        if None in (d['potencia'], d['pasos'], d['inversion'], d['vida']):
            continue
        fases = _norm(d['fases'])
        if fases not in ('trifasico', 'monofasico'):
            errores.append(f'Hoja «{hoja}», fila {n}, columna «Fases»: «{d["fases"] or ""}» no es '
                           '«trifásico» ni «monofásico».')
            continue
        if d['pasos'] < 1 or d['pasos'] != int(d['pasos']):
            errores.append(f'Hoja «{hoja}», fila {n}, columna «Pasos»: tiene que ser un entero '
                           f'mayor que cero, no {d["pasos"]:g}.')
            continue
        if d['vida'] <= 0 or d['potencia'] <= 0:
            errores.append(f'Hoja «{hoja}», fila {n}: la potencia y la vida útil tienen que ser '
                           'mayores que cero.')
            continue
        coste = anualidad(d['inversion'], tasa, d['vida']) if tasa is not None else None
        libro.bancos.append(Banco(d['potencia'], int(d['pasos']), fases == 'trifasico',
                                  d['inversion'], d['vida'], coste))


def _costes(filas, libro: Libro, errores: list[str]) -> None:
    hoja = POR_CLAVE['costes'].titulo
    filas_por_concepto = _por_concepto(filas, hoja, _COSTE_POR_NOMBRE, errores)
    for clave, (n, d) in filas_por_concepto.items():
        unidad = str(d.get('unidad') or '')
        if d['valor'] is None:
            continue
        if clave == 'energia':
            if not _norm(unidad).endswith('/kwh') or len(unidad) <= 4:
                errores.append(f'Hoja «{hoja}», fila {n}, columna «Unidad»: «{unidad}» no es una moneda '
                               'por kWh («<moneda>/kWh», con la moneda de la empresa).')
                continue
            libro.coste_energia_kwh, libro.moneda = d['valor'], unidad[:-4].strip()
        else:
            if _norm(unidad) != '%':
                errores.append(f'Hoja «{hoja}», fila {n}, columna «Unidad»: la tasa va en «%», no '
                               f'«{unidad}».')
                continue
            libro.tasa_descuento = d['valor'] / 100.0
    if 'descuento' not in filas_por_concepto:
        errores.append(f"Hoja «{hoja}»: falta la fila «{COSTES['descuento']}».")


def leer_libro(ruta: Path | str, nombre: str | None = None) -> Libro:
    """Lee y valida el libro entero; con cualquier error, ``DatosEmpresaError`` con todos."""
    from openpyxl import load_workbook

    ruta = Path(ruta)
    try:
        wb = load_workbook(ruta, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - cualquier cosa que no sea un libro Excel
        raise DatosEmpresaError([f'{ruta.name} no es un libro Excel que se pueda leer: {exc}']) from exc
    libro, errores = Libro(nombre=nombre or ruta.name), []
    try:
        por_titulo = {_norm(n): n for n in wb.sheetnames}
        leidas: dict[str, list] = {}
        for hoja in HOJAS:
            real = por_titulo.get(_norm(hoja.titulo))
            if real is None:
                libro.hojas_que_faltan.append(hoja.titulo)          # RF-63
                continue
            leidas[hoja.clave] = _leer_hoja(wb[real], hoja, errores)
    finally:
        wb.close()
    if 'tasas' in leidas:
        _tasas(leidas['tasas'], libro, errores)
    if 'tiempos' in leidas:
        _tiempos(leidas['tiempos'], libro, errores)
    if 'telemandados' in leidas:
        libro.telemandados = tuple(sorted({str(d['codigo']) for _n, d in leidas['telemandados']
                                           if d['codigo'] is not None}))
        if libro.telemandados and 'telemandada' not in libro.tiempos_min and 'tiempos' in leidas:
            errores.append(f"Hoja «{POR_CLAVE['tiempos'].titulo}»: hay equipos telemandados y falta "
                           f"la fila «{TIEMPOS['telemandada']}».")
    if 'costes' in leidas:
        _costes(leidas['costes'], libro, errores)
    if 'bancos' in leidas:
        _bancos(leidas['bancos'], libro, errores, libro.tasa_descuento)
    if errores:
        raise DatosEmpresaError(errores)
    for titulo in libro.hojas_que_faltan:
        afectados = [e for e, hojas in NECESITA.items()
                     if any(POR_CLAVE[h].titulo == titulo for h in hojas)]
        libro.avisos.append(f'Falta la hoja «{titulo}»'
                            + (': no se podrán ejecutar ' + ', '.join(afectados) if afectados else '')
                            + '.')
    return libro


# --------------------------------------------------------------------------- plantilla
def plantilla(destino: Path | str) -> Path:
    """La plantilla descargable (RF-7): hojas, columnas, unidades y una fila por clase.

    Las filas de ejemplo van sin cifras: una plantilla subida sin rellenar se rechaza por
    sus celdas vacías (RF-16) en vez de pasar con números que nadie dio. La unidad del coste
    de la energía también va vacía: la moneda es la de quien rellena el libro.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    ejemplos = {
        'tasas': [[CLASES[c]] for c in CLASES],
        'tiempos': [[t] for t in TIEMPOS.values()],
        'telemandados': [],
        'bancos': [[None, None, 'trifásico']],
        'costes': [[COSTES['energia'], None, None], [COSTES['descuento'], None, '%']],
    }
    for hoja in HOJAS:
        ws = wb.create_sheet(hoja.titulo)
        ws.append([c.titulo for c in hoja.columnas])
        ws.append([c.unidad for c in hoja.columnas])
        for celda in ws[1]:
            celda.font = Font(bold=True)
        for fila in ejemplos[hoja.clave]:
            ws.append(fila)
        for i, col in enumerate(hoja.columnas):
            ws.column_dimensions[chr(ord('A') + i)].width = max(16, len(col.titulo) + 4, len(col.unidad) + 2)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def resumen(libro: Libro) -> dict[str, Any]:
    """Lo que la web muestra del libro cargado: qué trae y qué no."""
    return {'nombre': libro.nombre, 'clases': [CLASES[c] for c in CLASES if c in libro.tasas],
            'tipos': sorted(libro.tasas_por_tipo), 'telemandados': len(libro.telemandados),
            'bancos': [asdict(b) for b in libro.bancos], 'coste_energia_kwh': libro.coste_energia_kwh,
            'moneda': libro.moneda, 'tasa_descuento': libro.tasa_descuento,
            'hojas_que_faltan': list(libro.hojas_que_faltan), 'avisos': list(libro.avisos)}
