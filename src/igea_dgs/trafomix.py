"""Trafomix: equipos de medición en media tensión que la base registra como SED.

En IGEA/CYMDIST el medidor de un cliente de media tensión (el «trafomix»: conjunto de
transformadores de tensión y de corriente para medir) aparece como una SED más, con
código que empieza por ``M`` —``M41608`` mide a la subestación particular
``SE41608``—. No es una subestación de distribución: no transforma a baja tensión.
Modelarlo como SED añade un transformador que no existe y un triángulo en el
diagrama por cada punto de medida.

En la entrega 260922 son 1.374 de 7.282 «SED», y **todas con 0 kW**: la demanda está
en la SED que miden. Por eso se excluyen enteras: ni SED, ni transformador, ni la
carga de 0 kW. El tramo de red en el que están se conserva.

Si algún trafomix trajera carga, esa carga **no se pierde**: queda como carga de
media tensión en su nodo, sin transformador, y se avisa.

El fusible que llevaba al trafomix se queda sin destino: su barra no tiene nada más. En
NA203 + NA205 (260924.mdb) eso dejaba 88 barras muertas con su ``ElmCoup``, como
EQ_1080_320414 hacia M50226. No se escriben ni el fusible ni la barra, y el informe los
nombra (spec 021, RF-7 y RF-8); la auditoría de completitud los descuenta (RF-9).

El código ``M…`` es una convención de Electro Dunas, no de CYMDIST: otra empresa puede
tener SED reales que empiecen por ``M``. El patrón sale del perfil de empresa
(``patron_sed_medicion``, spec 002 RF-33); sin patrón no se excluye ninguna SED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import FeederModel



def es_trafomix(codigo: str, patron: str | None) -> bool:
    """¿Es ``codigo`` una SED de medición según el patrón del perfil? Sin patrón, nunca."""
    if not patron:
        return False
    return bool(re.search(patron, (codigo or '').strip()))


@dataclass
class InformeTrafomix:
    patron: str = ''
    excluidos: int = 0
    cargas_nulas_quitadas: int = 0
    cargas_conservadas_mt: list[str] = field(default_factory=list)
    maniobras_quitadas: list[str] = field(default_factory=list)

    def texto(self) -> str:
        t = (f'Trafomix (medición MT, patrón {self.patron}): {self.excluidos} excluidos como SED; '
             f'{self.cargas_nulas_quitadas} cargas de 0 kW quitadas.')
        if self.cargas_conservadas_mt:
            t += (f' {len(self.cargas_conservadas_mt)} traían carga y se conservan como '
                  f'carga de MT: {", ".join(self.cargas_conservadas_mt[:8])}.')
        if self.maniobras_quitadas:
            t += (f' {len(self.maniobras_quitadas)} maniobras que solo llevaban a un trafomix '
                  f'quitadas con su barra: {", ".join(self.maniobras_quitadas)}.')
        return t


def excluir_trafomix(model: FeederModel, patron: str | None) -> InformeTrafomix:
    """Quita del modelo, en el sitio, las SED cuyo código cumple ``patron``."""
    informe = InformeTrafomix(patron=patron or '')
    if not patron:
        return informe
    claves_quitar: set[tuple[str, str]] = set()
    barras_trafomix: set[str] = set()
    quedan = []
    for sed in model.seds:
        if not es_trafomix(sed.code, patron):
            quedan.append(sed)
            continue
        informe.excluidos += 1
        claves_quitar.add(sed.load_key)
        barras_trafomix.add(sed.node_id)
    model.seds = quedan

    cargas = []
    for carga in model.loads:
        clave = (carga.section_id, carga.device_number)
        if clave not in claves_quitar:
            cargas.append(carga)
        elif abs(carga.p_mw) < 1e-9 and abs(carga.q_mvar) < 1e-9:
            informe.cargas_nulas_quitadas += 1
        else:
            cargas.append(carga)
            informe.cargas_conservadas_mt.append(carga.sed_code or carga.device_number)
    model.loads = cargas
    informe.maniobras_quitadas = _quitar_maniobras_sin_destino(model, barras_trafomix)
    if informe.excluidos:
        model.warnings.append(informe.texto())
    return informe


def _quitar_maniobras_sin_destino(model: FeederModel, barras: set[str]) -> list[str]:
    """``ElmCoup`` que solo llevan a la barra de un trafomix excluido: se quitan con ella.

    La barra tiene que quedarse sin nada más (ni línea, ni carga, ni SED, ni banco, ni la
    fuente, ni otra maniobra): con una carga de MT conservada, el fusible sigue llevando a
    algo y se queda. Devuelve los nombres quitados, en el orden de ``model.couplers``.
    """
    if not barras:
        return []
    uso: dict[str, int] = {}

    def usar(n: str | None) -> None:
        if n in barras:
            uso[n] = uso.get(n, 0) + 1

    for ln in model.lines:
        usar(ln.from_node)
        usar(ln.to_node)
    for x in (*model.loads, *model.seds, *model.capacitors):
        usar(getattr(x, 'node_id', None))
    for c in model.couplers:
        usar(c.node_a)
        usar(c.node_b)
    usar(model.source_node)
    quitados, quedan, muertas = [], [], set()
    for c in model.couplers:
        muerta = next((n for n in (c.node_a, c.node_b) if n in barras and uso.get(n) == 1), None)
        if muerta is None:
            quedan.append(c)
            continue
        quitados.append(c.eq_number or c.name)
        muertas.add(muerta)
    model.couplers = quedan
    model.nodes = {k: v for k, v in model.nodes.items() if k not in muertas}
    return quitados
