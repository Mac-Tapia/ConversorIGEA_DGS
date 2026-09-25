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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import FeederModel

#: Código de SED de un trafomix: una M y cifras (``M41608``, ``M50174``).
PATRON_TRAFOMIX = re.compile(r'^M\d+(?:-\d+)?$', re.IGNORECASE)


def es_trafomix(codigo: str) -> bool:
    return bool(PATRON_TRAFOMIX.match((codigo or '').strip()))


@dataclass
class InformeTrafomix:
    excluidos: int = 0
    cargas_nulas_quitadas: int = 0
    cargas_conservadas_mt: list[str] = field(default_factory=list)

    def texto(self) -> str:
        t = (f'Trafomix (medición MT, códigos M…): {self.excluidos} excluidos como SED; '
             f'{self.cargas_nulas_quitadas} cargas de 0 kW quitadas.')
        if self.cargas_conservadas_mt:
            t += (f' {len(self.cargas_conservadas_mt)} traían carga y se conservan como '
                  f'carga de MT: {", ".join(self.cargas_conservadas_mt[:8])}.')
        return t


def excluir_trafomix(model: FeederModel) -> InformeTrafomix:
    """Quita del modelo, en el sitio, las SED que son trafomix."""
    informe = InformeTrafomix()
    claves_quitar: set[tuple[str, str]] = set()
    quedan = []
    for sed in model.seds:
        if not es_trafomix(sed.code):
            quedan.append(sed)
            continue
        informe.excluidos += 1
        claves_quitar.add(sed.load_key)
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
    if informe.excluidos:
        model.warnings.append(informe.texto())
    return informe
