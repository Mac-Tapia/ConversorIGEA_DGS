"""Recompensas, penalizaciones y memoria de reflexiones del asistente (spec 027, T15 y T16).

Cada orden deja su señal (RF-35): confirmada, +1; corregida, −1 para la interpretación del
modelo y la corregida como ejemplo positivo; rechazada, −1; ejecución fallida, −1 para la
acción, con su error. Cada corrección forma un par de preferencia, rechazada frente a
corregida, para un ajuste DPO (Rafailov et al., 2023) dentro de RF-21 (RF-36). Un fallo o una
corrección deja una nota que vuelve como contexto cuando llega una orden parecida, sin tocar
pesos (Reflexion, Shinn et al., 2023; RF-37), y Ollama recibe además las k órdenes confirmadas
más parecidas como ejemplos (RF-39).
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ...dominio.sesion_web import depurar_secretos
from ...dominio.util import publicar_duradero
from . import almacen
from .sinteticos import normalizar

#: Valor de cada señal (RF-35).
VALOR = {'confirmada': 1, 'corregida': -1, 'rechazada': -1, 'fallida': -1}


def anotar(senal: str, *, plan: str, texto: str, tarea: str | None, datos: Mapping[str, Any] | None = None,
           modelo: str | None = None, error: str | None = None) -> dict[str, Any]:
    """La señal de una orden (RF-35)."""
    if senal not in VALOR:
        raise ValueError(f'señal desconocida: {senal}')
    return almacen.anotar('senales', {'senal': senal, 'valor': VALOR[senal], 'plan': plan, 'texto': texto,
                                      'tarea': tarea, 'datos': dict(datos or {}), 'modelo': modelo,
                                      'error': error})


def par_de_preferencia(texto: str, rechazada: Mapping[str, Any], elegida: Mapping[str, Any]) -> dict[str, Any]:
    """Un par «rechazada frente a corregida» para DPO (RF-36)."""
    return almacen.anotar('preferencias', {'texto': texto, 'rechazada': dict(rechazada), 'elegida': dict(elegida)})


def reflexion(texto: str, tarea: str | None, causa: str, correccion: str) -> dict[str, Any]:
    """Una nota con la causa y la corrección, para la próxima orden parecida (RF-37)."""
    return almacen.anotar('reflexiones', {'texto': texto, 'tarea': tarea, 'causa': causa, 'correccion': correccion})


def _trigramas(texto: str) -> set[str]:
    t = f'  {normalizar(texto)}  '
    return {t[i:i + 3] for i in range(len(t) - 2)}


def parecido(a: str, b: str) -> float:
    """Jaccard de trigramas de caracteres: robusto a erratas, sin modelo."""
    x, y = _trigramas(a), _trigramas(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def _mas_parecidas(texto: str, filas: list[dict], k: int, minimo: float) -> list[dict]:
    puntuadas = sorted(((parecido(texto, f.get('texto') or ''), i, f) for i, f in enumerate(filas)),
                       key=lambda x: (-x[0], -x[1]))
    return [f for p, _i, f in puntuadas[:k] if p >= minimo]


def contexto_para(texto: str, *, k: int = 5, minimo: float = 0.3,
                  memoria: MemoriaConversacion | None = None) -> list[str]:
    """Lo que se le da a Ollama con la orden: las k confirmadas más parecidas (RF-39), las notas
    de fallos o correcciones de órdenes parecidas (RF-37) y, con la memoria del espacio, los
    recuerdos parecidos de conversaciones anteriores (RF-74) y los últimos turnos (RF-73)."""
    out = []
    for f in _mas_parecidas(texto, [e for e in almacen.leer('ejemplos') if e.get('origen') == 'confirmado'],
                            k, minimo):
        out.append(f"Ejemplo confirmado: «{f['texto']}» → tarea {f['tarea']}")
    for f in _mas_parecidas(texto, almacen.leer('reflexiones'), 3, minimo):
        out.append(f"Nota de una orden parecida («{f['texto']}»): {f['causa']}; {f['correccion']}")
    if memoria is not None:
        out.extend(memoria.contexto(texto, minimo=minimo))
    return out


# --- 027:RF-73 a RF-76: memoria a largo plazo, por espacio ------------------------------------------------------
#
# Cada orden se interpretaba sola: «y ahora con el otro alimentador» no sabía de qué alimentador se hablaba. Cada
# espacio guarda su conversación en su carpeta (``<espacio>/asistente_memoria/conversacion.jsonl``, fuera de git y de
# los registros globales del asistente): un turno por orden, con su tarea, sus datos sencillos y la respuesta de una
# consulta. La orden siguiente recibe los últimos turnos y los recuerdos parecidos de conversaciones anteriores
# (Reflexion y memoria episódica por recuperación: Shinn et al., 2023; Park et al., «Generative Agents», UIST 2023).

#: Carpeta de la memoria dentro del espacio (027:RF-73).
CARPETA_MEMORIA = 'asistente_memoria'
#: Topes por defecto (027:RF-76): turnos recientes, recuerdos y filas del fichero antes de compactar.
TOPES_MEMORIA = {'turnos': ('CSG_ASISTENTE_MEMORIA_TURNOS', 6), 'recuerdos': ('CSG_ASISTENTE_MEMORIA_RECUERDOS', 3),
                 'filas': ('CSG_ASISTENTE_MEMORIA_FILAS', 500)}
#: Lo que cabe de un texto en el contexto del intérprete: la orden entera llega hasta 2000 caracteres.
_TEXTO_EN_CONTEXTO = 300
_cerrojo_memoria = threading.Lock()


def topes_memoria() -> dict[str, int]:
    """Los topes vigentes (027:RF-76): la variable si es un entero, el de defecto si no; nunca menos de 1."""
    out = {}
    for clave, (variable, defecto) in TOPES_MEMORIA.items():
        try:
            valor = int(os.environ.get(variable, '').strip() or defecto)
        except ValueError:
            valor = defecto
        out[clave] = max(1, valor)
    return out


def _dato_sencillo(valor: Any) -> Any:
    if isinstance(valor, bool) or isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, str):
        return depurar_secretos(valor)[:120] if valor.strip() else None
    if isinstance(valor, (list, tuple)):
        xs = [depurar_secretos(x)[:120] if isinstance(x, str) else x for x in valor[:10]
              if isinstance(x, (str, int, float)) and not isinstance(x, bool)]
        return xs or None
    return None


def _datos_sencillos(datos: Mapping[str, Any] | None) -> dict[str, Any]:
    """Textos, números y listas cortas de textos o números: lo que sirve para una referencia («el otro
    alimentador»); objetos, nulos y vacíos no se guardan (027:RF-73)."""
    out = {}
    for k, v in (datos or {}).items():
        if str(k).startswith('_'):
            continue
        s = _dato_sencillo(v)
        if s is not None:
            out[str(k)] = s
    return out


def _en_palabras(datos: Mapping[str, Any]) -> str:
    if not datos:
        return ''
    partes = [f"{k}={'/'.join(map(str, v)) if isinstance(v, list) else v}" for k, v in datos.items()]
    return '; datos: ' + ', '.join(partes)


class MemoriaConversacion:
    """La conversación de un espacio con el asistente (027:RF-73 a RF-76).

    Un JSONL de eventos: ``turno`` (una orden), ``correccion`` (el operador corrigió el plan de un turno) y
    ``olvido`` (el operador la borró). Cada evento se añade con ``fsync``, como los registros del asistente; una
    línea rota por un corte se salta. Al pasar del tope de filas, o al olvidar, el fichero se rehace de forma atómica
    con lo vigente: lo olvidado deja de estar en el disco y el olvido queda como evento con su fecha.
    """

    def __init__(self, raiz: Path):
        self.ruta = Path(raiz) / CARPETA_MEMORIA / 'conversacion.jsonl'

    def _filas(self) -> list[dict[str, Any]]:
        if not self.ruta.is_file():
            return []
        filas = []
        for linea in self.ruta.read_text(encoding='utf-8').splitlines():
            try:
                f = json.loads(linea)
            except ValueError:
                continue
            if isinstance(f, dict):
                filas.append(f)
        return filas

    @staticmethod
    def _desde_el_olvido(filas: list[dict]) -> tuple[dict | None, list[dict]]:
        ultimo = max((i for i, f in enumerate(filas) if f.get('evento') == 'olvido'), default=None)
        if ultimo is None:
            return None, filas
        return filas[ultimo], filas[ultimo + 1:]

    def _reescribir(self, filas: list[dict]) -> None:
        contenido = ''.join(json.dumps(f, ensure_ascii=False, default=str) + '\n' for f in filas)
        publicar_duradero(self.ruta, contenido)                                        # 001:RF-5

    def _anadir(self, fila: dict[str, Any]) -> dict[str, Any]:
        fila = {'fecha': almacen.ahora(), **fila}
        with _cerrojo_memoria:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            # Una línea cortada por un corte de luz no lleva su salto: sin este, el turno nuevo se le pegaría y se
            # perderían los dos.
            cortada = False
            if self.ruta.is_file() and self.ruta.stat().st_size:
                with open(self.ruta, 'rb') as f:
                    f.seek(-1, os.SEEK_END)
                    cortada = f.read(1) != b'\n'
            with open(self.ruta, 'a', encoding='utf-8') as f:
                f.write(('\n' if cortada else '') + json.dumps(fila, ensure_ascii=False, default=str) + '\n')
                f.flush()
                os.fsync(f.fileno())
            filas = self._filas()
            tope = topes_memoria()['filas']
            if len(filas) > tope:
                # 027:RF-76: lo vigente desde el último olvido, los más recientes; el olvido sigue como evento.
                olvido, vigentes = self._desde_el_olvido(filas)
                cabeza = [olvido] if olvido else []
                self._reescribir(cabeza + vigentes[-(tope - len(cabeza)):] if tope > len(cabeza) else cabeza)
        return fila

    def recordar(self, *, plan: str, texto: str, tarea: str | None, datos: Mapping[str, Any] | None = None,
                 respuesta: str | None = None) -> dict[str, Any]:
        """Un turno: la orden (sin credenciales), su tarea, sus datos sencillos y la respuesta de una consulta."""
        fila = {'evento': 'turno', 'plan': str(plan), 'texto': depurar_secretos(str(texto or ''))[:2000],
                'tarea': tarea, 'datos': _datos_sencillos(datos)}
        if respuesta:
            fila['respuesta'] = depurar_secretos(str(respuesta))[:_TEXTO_EN_CONTEXTO]
        return self._anadir(fila)

    def corregir(self, *, plan: str, nuevo: str, tarea: str | None, datos: Mapping[str, Any] | None = None) -> dict:
        """El operador corrigió el plan de un turno: se recuerda lo corregido, no lo que se entendió."""
        return self._anadir({'evento': 'correccion', 'plan': str(plan), 'nuevo': str(nuevo), 'tarea': tarea,
                             'datos': _datos_sencillos(datos)})

    def turnos(self) -> list[dict[str, Any]]:
        """Los turnos vigentes, del más antiguo al más reciente, con las correcciones aplicadas."""
        _olvido, filas = self._desde_el_olvido(self._filas())
        # En el orden en que se dijeron: una corrección cambia el turno donde está, no lo mueve al final.
        por_plan: dict[str, dict] = {}
        alias: dict[str, str] = {}
        for f in filas:
            if f.get('evento') == 'turno':
                clave = str(f.get('plan'))
                por_plan[clave] = {k: f.get(k) for k in ('fecha', 'plan', 'texto', 'tarea', 'datos', 'respuesta')
                                   if f.get(k) is not None}
                alias[clave] = clave
            elif f.get('evento') == 'correccion' and str(f.get('plan')) in alias:
                clave = alias[str(f.get('plan'))]
                if clave in por_plan:
                    por_plan[clave].update({'plan': f.get('nuevo'), 'tarea': f.get('tarea'),
                                            'datos': f.get('datos') or {}})
                    alias[str(f.get('nuevo'))] = clave
        return list(por_plan.values())

    def olvidar(self) -> dict[str, Any]:
        """027:RF-75: la conversación del espacio se borra del disco; queda el olvido con su fecha."""
        with _cerrojo_memoria:
            olvidados = len(self.turnos())
            fila = {'fecha': almacen.ahora(), 'evento': 'olvido', 'olvidados': olvidados}
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self._reescribir([fila])
        return {'olvidados': olvidados, 'fecha': fila['fecha']}

    def publico(self) -> dict[str, Any]:
        """Lo que enseña la web: los turnos vigentes y los topes (027:RF-75)."""
        return {'turnos': self.turnos(), 'topes': topes_memoria()}

    def contexto(self, texto: str, *, minimo: float = 0.3) -> list[str]:
        """Los recuerdos parecidos de lo que ya salió de la ventana (027:RF-74) y los últimos turnos (027:RF-73)."""
        topes = topes_memoria()
        turnos = self.turnos()
        recientes, viejos = turnos[-topes['turnos']:], turnos[:-topes['turnos']]
        out = []
        for t in sorted(_mas_parecidas(texto, viejos, topes['recuerdos'], minimo), key=lambda t: str(t.get('fecha'))):
            out.append(f"Recuerdo de una conversación anterior de este espacio: «{t['texto'][:_TEXTO_EN_CONTEXTO]}»"
                       f" → tarea {t.get('tarea') or 'ninguna'}{_en_palabras(t.get('datos') or {})}")
        for t in recientes:
            respuesta = f"; respuesta: {t['respuesta']}" if t.get('respuesta') else ''
            out.append(f"Turno anterior de esta conversación: «{t['texto'][:_TEXTO_EN_CONTEXTO]}»"
                       f" → tarea {t.get('tarea') or 'ninguna'}{_en_palabras(t.get('datos') or {})}{respuesta}")
        return out


def resumen() -> dict[str, dict[str, int]]:
    """Recompensas y penalizaciones acumuladas por tarea (RF-35)."""
    out: dict[str, dict[str, int]] = {}
    for f in almacen.leer('senales'):
        d = out.setdefault(f.get('tarea') or '—', {'recompensas': 0, 'penalizaciones': 0, **dict.fromkeys(VALOR, 0)})
        d[f['senal']] += 1
        d['recompensas' if f['valor'] > 0 else 'penalizaciones'] += 1
    return out


#: Tasa de error máxima de lo que se interpreta sin preguntar (027:RF-38).
ERROR_MAX = 0.02
#: Órdenes reales de una tarea con las que se calibra su umbral; con menos, el de siempre.
MIN_POR_TAREA = 10


def calibrar_umbrales(filas: Sequence[tuple[str, float, bool]], error_max: float = ERROR_MAX,
                      minimo: int = MIN_POR_TAREA) -> dict[str, float]:
    """Por tarea, el menor umbral de confianza con el que lo interpretado sin preguntar no se
    equivoca más que ``error_max`` (027:RF-38). ``filas``: (tarea, confianza, acertó)."""
    por_tarea: dict[str, list[tuple[float, bool]]] = {}
    for tarea, conf, ok in filas:
        por_tarea.setdefault(tarea, []).append((float(conf), bool(ok)))
    out = {}
    for tarea, xs in por_tarea.items():
        if len(xs) < minimo:
            continue
        xs.sort(key=lambda x: -x[0])
        mejor, errores = None, 0
        for i, (conf, ok) in enumerate(xs, 1):
            errores += not ok
            # Solo se corta entre confianzas distintas: un umbral deja pasar a todas las iguales.
            if i >= minimo and errores / i <= error_max and (i == len(xs) or xs[i][0] < conf):
                mejor = conf
        if mejor is not None:
            out[tarea] = mejor
    return out


def filas_reales() -> list[tuple[str, float, bool]]:
    """Cada orden real con su confianza y si el operador la dio por buena (confirmada) o no
    (corregida o rechazada); las fallidas son de la acción, no de la interpretación."""
    senal = {f['plan']: f['senal'] for f in almacen.leer('senales') if f.get('senal') != 'fallida'}
    out = []
    for o in almacen.leer('ordenes'):
        s = senal.get(o.get('plan'))
        if s and o.get('tarea') and o.get('confianza') is not None:
            out.append((o['tarea'], float(o['confianza']), s == 'confirmada'))
    return out


def calibrar_y_guardar() -> dict[str, float]:
    """Calibra los umbrales con las órdenes reales y los guarda para el intérprete (RF-38)."""
    umbrales = calibrar_umbrales(filas_reales())
    almacen.guardar_json('umbrales', umbrales)
    return umbrales
