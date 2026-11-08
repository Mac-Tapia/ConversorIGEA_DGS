"""050:RF-2/3: productor de la vista PINN congelada; no inicializa ni escribe SQLite."""
from __future__ import annotations
import json
from .buffer import Consulta
from .episode import leer_episodio, episodio_a_dict

def muestras_aprendizaje(instantanea: dict, referencias: dict) -> list:
    """050:RF-2/3: relee objetos inmutables y reproduce el reparto PINN sin escribir SQLite."""
    from ..contratos_aprendizaje import CicloBloqueado, crear_observacion_id, muestra_de_registro, ruta_de
    from .oraculo import muestras_y_particiones

    episodios = []
    for ruta in sorted((ruta_de(instantanea, 'twin') / 'objetos').glob('*/*.json')):
        e = leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))
        if ruta.stem != e.episode_id:
            raise CicloBloqueado('episodio congelado con identidad distinta del nombre')
        if e.clase.value in ('accepted', 'counterfactual') and e.nativo.get('reopen_verified') is not True:
            raise CicloBloqueado('episodio sin reapertura nativa comprobada')
        episodios.append(e)

    class LecturaCongelada:
        def consultar(self, consulta):
            if consulta != Consulta():
                raise CicloBloqueado('el productor solo admite la consulta común del ciclo')
            return episodios

    muestras, ids, grupos = muestras_y_particiones(LecturaCongelada(), Consulta())
    identidad = {id(m): i for m, i in zip(muestras, ids, strict=True)}
    por_id = {e.episode_id: e for e in episodios}
    nombres = {'validacion': 'seleccion'}
    resultado = []
    for parte, ms in grupos.items():
        for m in ms:
            e = por_id[identidad[id(m)]]
            muestra = muestra_de_registro(instantanea, referencias, 'twin',
                e.episode_id, episodio_a_dict(e), familia='pinn',
                particion=nombres.get(parte, parte), origen='simulado_nativo', etiqueta='motor_nativo')
            referencia = referencias['twin'][e.episode_id]
            if muestra.observacion_id != crear_observacion_id(muestra.contexto,
                    referencia['fuente_hash'], e.episode_id, e.creado):
                raise CicloBloqueado('la referencia no corresponde a la observación fuente del episodio')
            resultado.append(muestra)
    return resultado
