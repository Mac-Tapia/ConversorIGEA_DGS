"""DIgSILENT simulado para probar ``tools/cargas_pf.py`` sin PowerFactory (spec 004).

Imita lo justo de la API: árbol de objetos con ``CreateObject``/``GetContents``,
alimentadores con ``GetObjs``, variaciones con ``NewStage`` y la etapa que graba,
escenario activo y ``ComLdf``. Las cargas reproducen la regla que motivó RF-9: en modo
P–cos φ los datos son P y cos φ, y escribir S recalcula P desde el cos φ anterior.
Cada escritura queda anotada con la etapa que grababa y el escenario activo, para
comprobar que todo fue a la variación nueva.

Para la spec 006 (ajuste a la máxima de cabecera), con ``proyecto(bt=True)`` cada SED
tiene su barra de baja, con el transformador entre la de media y ella y la carga
colgada de ella, y el ``ElmFeeder`` apunta al cubículo de su cabecera. Con
``proyecto(flujo=True)`` el ``ComLdf`` es :class:`FlujoConPerdidas`: calcula lo que entra
por cada cabecera con pérdidas cuadráticas y deja de converger por encima de un
límite, que suben los ajustes del flujo que DIgSILENT usa para converger.

Para la spec 005 imita además las carpetas del usuario (``IntFolder``), ``Move``,
``Delete``, la activación de proyectos y ``ComImport``, que crea el proyecto en la raíz
del usuario como DIgSILENT. ``App.fallar_mover`` hace que ``Move`` devuelva error, el caso
que RF-9 no puede dejar con el proyecto en la raíz.

Para la spec 007 (una variación por carga nueva), las variaciones se activan y se
desactivan, y lo que se creó con la etapa de una variación inactiva sale de la red: no
aparece en ``GetContents``, ``GetObjs`` ni ``GetCalcRelevantObjects``, como en
DIgSILENT. El alimentador encuentra lo nuevo por conexión desde sus barras (cubículos),
porque en DIgSILENT pertenecer a un alimentador es topológico: así el flujo de la
cabecera ve la carga nueva solo mientras su variación está activa.

Para la spec 011 (tres casos de estudio), las variaciones activas, la etapa que graba y
el escenario son **de cada caso** (:class:`Caso`), como en DIgSILENT: activar otro caso
cambia qué red se ve. ``app.variaciones_activas``, ``app.grabando`` y ``app.escenario``
siguen existiendo y apuntan al caso activo, así que las pruebas de antes no cambian.
Imita además ``AddCopy`` y ``PasteCopy`` (copias independientes del original, que es lo
que la spec exige de los tipos), la biblioteca global, y ``Open``/``Close``/``IsClosed``
de los interruptores.

Para la spec 012 imita ``ComRel3``, ``ComOpri``, ``ComHostcap``, ``ComPvcurves``,
``ComCapo`` y ``SetSelect`` como se comportaron en DIgSILENT 2024 sobre una copia de un
proyecto real (2026-10-12), con los nombres reales de sus variables de resultado. Con
``app.atributos_en_variacion`` los atributos escritos mientras graba una etapa son de su
variación y desactivarla los devuelve, como en DIgSILENT; y al activar otro caso se ven
solo los de las variaciones activas en él (spec 011, T12: obras activas en un solo caso).

Para el escenario de operación (spec 006, RF-27): con ``app.escenario_manda``, la
potencia de una carga es dato de operación, como en DIgSILENT. Con un escenario activo
se escribe en él y, si la guarda, se lee de él, no de la carga ni de su variación. SI213
(2026-10-12) cuadró a 1.622 kW con el escenario apagado y, al restaurarlo, la cabecera
volvió a los 229 kW que el escenario guardaba. ``Escenario.fotografiar`` guarda las
cargas que haya, como un escenario creado sobre la red importada.
"""
from __future__ import annotations

import math


_NO_SE_COPIA = frozenset({'_app', '_clase', '_padre', '_hijos', '_estado',
                          'loc_name', 'etapa_creacion'})


class Obj:
    def __init__(self, app, clase, nombre, padre=None, **attrs):
        object.__setattr__(self, '_app', app)
        object.__setattr__(self, '_clase', clase)
        object.__setattr__(self, '_padre', padre)
        object.__setattr__(self, '_hijos', [])
        object.__setattr__(self, 'loc_name', nombre)
        object.__setattr__(self, 'etapa_creacion', app.grabando if app else None)
        for k, v in attrs.items():
            object.__setattr__(self, k, v)

    def __setattr__(self, name, value):
        app = self._app
        if app is not None and name != 'loc_name':
            app.escrituras.append((self, name, value, app.grabando, app.escenario))
            etapa = app.grabando
            # Spec 012: en DIgSILENT un atributo escrito mientras graba una etapa es de esa
            # variación, y desactivarla lo devuelve a su valor. Opcional: las pruebas de
            # las specs anteriores dan por hecho que el valor se queda.
            if app.atributos_en_variacion and etapa is not None and self.etapa_creacion is not etapa:
                cambios = etapa._padre.__dict__.setdefault('_cambios', [])
                cambios.append((self, name, getattr(self, name, None), value))
            _registrar_en_etapa(etapa, self, name, value)
        object.__setattr__(self, name, value)

    # ----------------------------------------------------------- árbol
    def GetClassName(self):
        return self._clase

    def GetParent(self):
        return self._padre

    def GetFullName(self):
        return (self._padre.GetFullName() + '\\' if self._padre else '') + f'{self.loc_name}.{self._clase}'

    def CreateObject(self, clase, nombre):
        hijo = _CLASES.get(clase, Obj)(self._app, clase, nombre, self)
        self._hijos.append(hijo)
        self._app.creados.append(hijo)
        etapa = self._app.grabando if self._app is not None else None
        if etapa is not None and _es_de_red(hijo):
            etapa._creados.append(hijo)
        return hijo

    # ----------------------------------------------------------- spec 011
    def _copia(self, padre, nombre):
        """Copia independiente de este objeto y de sus hijos, colgada de ``padre``."""
        nuevo = type(self)(self._app, self._clase, nombre, padre)
        for k, v in vars(self).items():
            # Los datos propios de una clase (P y cos φ de una carga) se copian; el
            # árbol, el estado del caso y la etapa de creación son del objeto nuevo.
            if k in _NO_SE_COPIA:
                continue
            object.__setattr__(nuevo, k, list(v) if isinstance(v, list) else v)
        for h in self._hijos:
            nuevo._hijos.append(h._copia(nuevo, h.loc_name))
        return nuevo

    def AddCopy(self, obj, *partes):
        """Como la API: con partes de nombre, el nombre nuevo es su concatenación."""
        nuevo = obj._copia(self, ''.join(str(p) for p in partes) if partes else obj.loc_name)
        self._hijos.append(nuevo)
        self._app.creados.append(nuevo)
        return nuevo

    def PasteCopy(self, obj, _reset=0):
        """Copia desde otro proyecto: devuelve ``(error, nuevo)`` como la API."""
        return 0, self.AddCopy(obj)

    @property
    def en_red(self) -> bool:
        """Elementos de red creados en una variación inactiva no existen (spec 007)."""
        etapa = self.etapa_creacion
        if etapa is None or not self._clase.startswith(('Elm', 'Sta')):
            return True
        return etapa._padre in self._app.variaciones_activas

    def GetContents(self, patron='*', recursivo=0):
        clase = patron.split('.', 1)[1] if '.' in patron else None
        out = []
        for h in self._hijos:
            if not h.en_red:
                continue
            if clase is None or h._clase == clase:
                out.append(h)
            if recursivo:
                # Al recorrer el proyecto no se entra en lo grabado por una etapa: en este
                # doble es también ``GetCalcRelevantObjects``, y las copias de etapa no son
                # red (las obras de la 011 tomaban la copia del tramo por el tramo).
                out.extend(Obj.GetContents(h, patron, 1) if isinstance(h, Etapa)
                           else h.GetContents(patron, 1))
        return out

    def GetAttributeLength(self, _name):
        return 20

    def SetAttribute(self, name, value):
        setattr(self, name, value)

    def GetAttribute(self, name):
        # Solo el prefijo: «m:Psum:bus1» lleva otro «m:» dentro.
        return getattr(self, 'm_' + name[2:] if name.startswith('m:') else name)

    def HasResults(self):
        return hasattr(self, 'm_u')

    def HasAttribute(self, name):
        return hasattr(self, name)

    # ----------------------------------------------------------- spec 006
    def GetConnectedElements(self, *_a):
        """De una barra: lo conectado a sus cubículos."""
        return [c.obj_id for c in self._hijos if c._clase == 'StaCubic' and getattr(c, 'obj_id', None)]

    @property
    def cterm(self):
        """De un cubículo: su barra."""
        return self._padre

    def Activate(self, *_a):
        if self._clase == 'IntPrj' and self._app is not None:
            self._app.activo = self
        # Como ``IntSstage.Activate(1)`` en DIgSILENT: la etapa pasa a ser la que graba
        # (spec 011, T15c: la transferencia devuelve la que grababa antes de su cálculo).
        if self._clase == 'IntSstage' and self._app is not None and not self._empatada():
            self._app.grabando = self
        return 0

    def _empatada(self) -> bool:
        """Otra variación activa tiene una etapa de la misma fecha que esta.

        Manual de PF 2024, 16.5: con varias etapas activas de la misma fecha sigue grabando
        la que ya grababa. SI213 (2026-10-12) tenía tres ajustes activos así y la etapa del
        cuarto no llegó a grabar, ni con ``Activate(1)``.
        """
        app = self._app
        mia = getattr(self, 'tAcTime', 0)
        return any(getattr(s, 'tAcTime', 0) == mia
                   for v in app.variaciones_activas if v is not self._padre
                   for s in v.GetContents('*.IntSstage'))

    def Deactivate(self, *_a):
        if self._clase == 'IntPrj' and self._app is not None and self._app.activo is self:
            self._app.activo = None
        return 0

    # ----------------------------------------------------------- spec 005
    def Move(self, obj):
        """Lleva ``obj`` a esta carpeta: 0 si lo movió, como la API."""
        if self._app is not None and self._app.fallar_mover:
            return 1
        obj._padre._hijos.remove(obj)
        self._hijos.append(obj)
        object.__setattr__(obj, '_padre', self)
        if self._app is not None:
            self._app.movidos.append((obj, self))
        return 0

    def Delete(self):
        self._padre._hijos.remove(self)
        if self._app is not None:
            self._app.borrados.append(self)
            if self._app.activo is self:
                self._app.activo = None
        return 0


class Importacion(Obj):
    """``ComImport``: con ``iopt_prj=0`` crea un proyecto nuevo en la raíz del usuario."""

    def SetAttributes(self, valores):
        nombres = self._app.transferencia.get('ComImport', [])
        for nombre, valor in zip(nombres, valores):
            object.__setattr__(self, nombre, valor)

    def Execute(self):
        app = self._app
        if app.fallar_importacion:
            return 1
        nombre = getattr(self, 'targname', None)
        if not nombre or any(p.loc_name == nombre for p in app.usuario.GetContents('*.IntPrj')):
            return 1      # DIgSILENT no crea un segundo proyecto con el mismo nombre
        app.importados.append(nuevo_proyecto(app, app.usuario, nombre,
                                             alimentadores=app.alimentadores_al_importar))
        return 0


#: Lo que de una carga guarda el escenario de operación con ``app.escenario_manda``.
_DATOS_DE_OPERACION = ('_p', '_q', '_cos', '_s')


class Carga(Obj):
    """ElmLod con P y cos φ como datos en modo PC (y P, Q en PQ)."""

    def _op(self, nombre):
        """Dato de operación: el del escenario activo si lo guarda (``escenario_manda``)."""
        esc = self._escenario_que_manda()
        datos = esc._datos.get(id(self)) if esc is not None else None
        return datos[nombre] if datos is not None else object.__getattribute__(self, nombre)

    def _fijar(self, nombre, valor):
        esc = self._escenario_que_manda()
        if esc is None:
            object.__setattr__(self, nombre, valor)
            return
        datos = esc._datos.setdefault(id(self), {k: object.__getattribute__(self, k)
                                                 for k in _DATOS_DE_OPERACION})
        datos[nombre] = valor

    def _escenario_que_manda(self):
        app = self._app
        if app is None or not app.escenario_manda:
            return None
        return app.escenario

    def __init__(self, app, clase, nombre, padre=None, **attrs):
        object.__setattr__(self, '_p', 0.0)
        object.__setattr__(self, '_q', 0.0)
        object.__setattr__(self, '_cos', 1.0)
        object.__setattr__(self, '_s', 1.0)
        attrs.setdefault('mode_inp', 'PC')
        attrs.setdefault('i_sym', 0)
        attrs.setdefault('pf_recap', 0)
        super().__init__(app, clase, nombre, padre, **attrs)

    def __setattr__(self, name, value):
        if name == 'scale0':
            # Factor de escala: dato de operación, como en DIgSILENT (sonda T1 de la 015).
            if self._app is not None:
                self._app.escrituras.append((self, name, value, self._app.grabando,
                                             self._app.escenario))
            self._fijar('_s', float(value))
            return
        if name in ('plini', 'qlini', 'slini', 'coslini'):
            if self._app is not None:
                self._app.escrituras.append((self, name, value, self._app.grabando,
                                             self._app.escenario))
            modo = self.mode_inp
            if self._app is not None and self._escenario_que_manda() is None:
                # Con el escenario mandando, el dato va al escenario y no a la etapa.
                _registrar_en_etapa(self._app.grabando, self, name, value)
            if name == 'plini':
                self._fijar('_p', float(value))
            elif name == 'coslini':
                self._fijar('_cos', float(value))
            elif name == 'qlini':
                if modo == 'PQ':
                    self._fijar('_q', float(value))
                else:     # en PC la Q es derivada: escribirla mueve el cos φ
                    p = self._op('_p')
                    s = math.hypot(p, float(value))
                    self._fijar('_cos', abs(p) / s if s else 1.0)
            elif name == 'slini':
                # El fallo documentado: en PC, S recalcula P con el cos φ que hubiera.
                self._fijar('_p', float(value) * self._op('_cos'))
            return
        super().__setattr__(name, value)

    @property
    def plini(self):
        return self._op('_p')

    @property
    def scale0(self):
        return self._op('_s')

    @property
    def coslini(self):
        if self.mode_inp == 'PQ':
            p, q = self._op('_p'), self._op('_q')
            s = math.hypot(p, q)
            return abs(p) / s if s else 1.0
        return self._op('_cos')

    @property
    def qlini(self):
        if self.mode_inp == 'PQ':
            return self._op('_q')
        cos = self._op('_cos')
        q = abs(self._op('_p')) * math.tan(math.acos(min(1.0, max(0.0, cos))))
        return -q if self.pf_recap else q

    @property
    def slini(self):
        return math.hypot(self.plini, self.qlini)


def _es_de_red(obj) -> bool:
    return obj._clase.startswith(('Elm', 'Sta'))


def _registrar_en_etapa(etapa, obj, nombre, valor) -> None:
    """Lo escrito en un elemento de red mientras ``etapa`` graba queda en ella (spec 014).

    En DIgSILENT una etapa guarda, de cada objeto que ya existía, su copia con los
    valores escritos; leerla da lo que grabó el ajuste aunque después mande otro valor.
    """
    if etapa is None or not _es_de_red(obj) or any(o is obj for o in etapa._creados):
        return
    delta = etapa._deltas.get(id(obj))
    if delta is None:
        delta = etapa._deltas[id(obj)] = Delta(etapa, obj)
    delta._attrs[nombre] = valor


class Delta:
    """Copia de un objeto dentro de una etapa: sus valores grabados y el resto del original."""

    def __init__(self, etapa, obj):
        self.__dict__.update(_etapa=etapa, _obj=obj, _attrs={}, loc_name=obj.loc_name)

    def __getattr__(self, nombre):
        attrs = self.__dict__['_attrs']
        if nombre in attrs:
            return attrs[nombre]
        obj = self.__dict__['_obj']
        if nombre == 'qlini' and isinstance(obj, Carga) and obj.mode_inp != 'PQ' and (
                'plini' in attrs or 'coslini' in attrs):
            # En modo PC la Q de la copia sale de su P y su cos φ, no de la carga de ahora.
            p = attrs.get('plini', obj.plini)
            cos = min(1.0, max(0.0, attrs.get('coslini', obj.coslini)))
            return abs(p) * math.tan(math.acos(cos))
        return getattr(obj, nombre)

    def GetClassName(self):
        return self._obj._clase

    def GetParent(self):
        return self._etapa

    def GetFullName(self):
        return self._etapa.GetFullName() + '\\' + f'{self.loc_name}.{self._obj._clase}'

    def GetAttribute(self, nombre):
        return self._attrs[nombre] if nombre in self._attrs else self._obj.GetAttribute(nombre)


class Etapa(Obj):
    """``IntSstage``: lista los objetos que creó y las copias de los que cambió (spec 014)."""

    def __init__(self, app, clase, nombre, padre=None, **attrs):
        super().__init__(app, clase, nombre, padre, **attrs)
        object.__setattr__(self, '_creados', [])
        object.__setattr__(self, '_deltas', {})

    def GetContents(self, patron='*', recursivo=0):
        # Con ``recursivo`` también lo creado dentro de lo creado: en DIgSILENT la carga
        # nueva de la 007 cuelga de su ElmSubstat, que es lo que guarda la etapa.
        clase = patron.split('.', 1)[1] if '.' in patron else None
        propios = list(self._creados) + list(self._deltas.values())
        return (super().GetContents(patron, recursivo)
                + [o for o in propios if clase is None or o.GetClassName() == clase])


class Variacion(Obj):
    def NewStage(self, nombre, _instante, activar):
        etapa = self.CreateObject('IntSstage', nombre)
        etapa.tAcTime = _instante
        if activar:
            # Como DIgSILENT (IN111 + TA225, 2026-10-15): activar la etapa nueva lleva la hora
            # del caso de estudio a su fecha.
            caso = getattr(self._app, 'caso', None)
            if caso is not None:
                caso.iStudyTime = _instante
            self.Activate()
            if not etapa._empatada():
                self._app.grabando = etapa
        return 0

    def Activate(self, *_a):
        if self not in self._app.variaciones_activas:
            self._app.variaciones_activas.append(self)
            # En el orden en que se crearon, no en el de activarlas: ``crear_variacion``
            # aparta y reactiva las demás para que grabe la nueva, y dos obras sobre el
            # mismo tramo se reaplicarían al revés.
            self._app.variaciones_activas.sort(
                key=lambda v: v._padre._hijos.index(v) if v._padre is not None else 0)
            for obj, nombre, _antes, despues in self.__dict__.get('_cambios', []):
                object.__setattr__(obj, nombre, despues)
        return 0

    def Deactivate(self, *_a):
        app = self._app
        if self in app.variaciones_activas:
            app.variaciones_activas.remove(self)
            for obj, nombre, antes, _despues in reversed(self.__dict__.get('_cambios', [])):
                object.__setattr__(obj, nombre, antes)
        if app.grabando is not None and app.grabando._padre is self:
            app.grabando = None
        return 0

    def Delete(self):
        self.Deactivate()
        return super().Delete()


class Caso(Obj):
    """``IntCase`` con sus propias variaciones activas, etapa que graba y escenario."""

    def __init__(self, app, clase, nombre, padre=None, **attrs):
        super().__init__(app, clase, nombre, padre, **attrs)
        object.__setattr__(self, '_estado', _Estado())

    def _copia(self, padre, nombre):
        nuevo = super()._copia(padre, nombre)
        # Copiar un caso copia qué variaciones tiene activas y su escenario, no la etapa.
        nuevo._estado.variaciones = list(self._estado.variaciones)
        nuevo._estado.escenario = self._estado.escenario
        return nuevo

    def Activate(self, *_a):
        # Con ``atributos_en_variacion``, lo que graba una variación solo se ve en los casos
        # donde está activa: al cambiar de caso se deshace lo de las que dejan de estarlo y
        # se aplica lo de las que pasan a estarlo (spec 011, T12: una obra activa solo en
        # «Con proyecto» no puede verse en «Sin proyecto»).
        app = self._app
        antes = list(app.variaciones_activas)
        despues = self._estado.variaciones
        for v in reversed([v for v in antes if v not in despues]):
            for obj, nombre, previo, _nuevo in reversed(v.__dict__.get('_cambios', [])):
                object.__setattr__(obj, nombre, previo)
        app.caso = self
        for v in despues:
            if v not in antes:
                for obj, nombre, _previo, nuevo in v.__dict__.get('_cambios', []):
                    object.__setattr__(obj, nombre, nuevo)
        return 0

    def Deactivate(self, *_a):
        if self._app.caso is self:
            self._app.caso = None
        return 0


class Interruptor(Obj):
    """``StaSwitch`` o ``ElmCoup``: el estado es ``on_off`` (1 cerrado)."""

    def Open(self):
        self.on_off = 0
        return 0

    def Close(self):
        self.on_off = 1
        return 0

    def IsClosed(self):
        return int(getattr(self, 'on_off', 1) == 1)


class Contingencias(Obj):
    """``ComSimoutage``: cuenta sus ejecuciones; sus contingencias son sus ``ComOutage``."""

    def Execute(self):
        self._app.n1_ejecuciones += 1
        return 0


class Contingencia(Obj):
    """``ComOutage`` con su traza: durante ella, sus elementos están fuera del cálculo.

    La traza imita el estado posterior a la falta: el flujo del doble se ejecuta con los
    elementos de la contingencia marcados en ``app.en_falta``, y ``StopTrace`` los devuelve.
    Tiene dos pasos, para que un guion que no recorra la traza hasta el final se note.
    """

    def SetObjs(self, objs):
        object.__setattr__(self, 'objs', list(objs))
        return 0

    def StartTrace(self):
        app = self._app
        app.trazas.append(self)
        app.en_falta = set(id(o) for o in self.objs)
        object.__setattr__(self, 'paso', 0)
        app.ldf.Execute()
        return 0

    def ContinueTrace(self):
        if self.paso >= 1:
            return 1
        object.__setattr__(self, 'paso', self.paso + 1)
        self._app.ldf.Execute()
        return 0

    def StopTrace(self, *_a):
        self._app.en_falta = set()
        self._app.trazas_cerradas.append(self)
        return 0


class _Estado:
    """Lo que en DIgSILENT es de cada caso de estudio."""

    def __init__(self):
        self.variaciones = []
        self.grabando = None
        self.escenario = None


class Alimentador(Obj):
    def __init__(self, app, nombre, padre):
        super().__init__(app, 'ElmFeeder', nombre, padre)
        object.__setattr__(self, '_objs', [])

    def GetObjs(self, clase):
        return [o for o in self._objs + self._nuevos() if o._clase == clase and o.en_red]

    def _nuevos(self) -> list:
        """Lo creado después de montar la red y conectado a sus barras por cubículos."""
        app = self._app
        nuevos = [o for o in app.creados if o.etapa_creacion is not None and o.en_red]
        if not nuevos:
            return []
        def abierto(cub) -> bool:
            # Como en DIgSILENT, el alimentador termina en un interruptor abierto (spec 016:
            # el enlace nuevo queda abierto y no mete las barras del otro alimentador).
            return any(getattr(s, 'on_off', 1) == 0 for s in cub.GetContents('*.StaSwitch'))

        cubiculos: dict[int, list] = {}
        for c in (o for o in app.creados if o._clase == 'StaCubic' and o.en_red):
            if getattr(c, 'obj_id', None) is not None and not abierto(c):
                cubiculos.setdefault(id(c.obj_id), []).append(c)
        vistos = {id(o) for o in self._objs}
        pendientes = [o for o in self._objs if o._clase == 'ElmTerm']
        out = []
        while pendientes:
            barra = pendientes.pop()
            for cub in barra.GetContents('*.StaCubic'):
                elem = getattr(cub, 'obj_id', None)
                if elem is None or id(elem) in vistos or elem.etapa_creacion is None or abierto(cub):
                    continue
                vistos.add(id(elem))
                out.append(elem)
                for otro in cubiculos.get(id(elem), []):
                    term = otro._padre
                    if id(term) not in vistos:
                        vistos.add(id(term))
                        out.append(term)
                        pendientes.append(term)
        return out


class Escenario(Obj):
    """``IntScenario``. Con ``app.escenario_manda`` guarda la potencia de las cargas."""

    def __init__(self, app, clase, nombre, padre=None, **attrs):
        super().__init__(app, clase, nombre, padre, **attrs)
        object.__setattr__(self, '_datos', {})
        object.__setattr__(self, 'guardados', 0)

    def _copia(self, padre, nombre):
        # Una copia del escenario lleva sus propios datos: cambiar uno no toca el otro.
        nuevo = super()._copia(padre, nombre)
        object.__setattr__(nuevo, '_datos', {k: dict(v) for k, v in self._datos.items()})
        object.__setattr__(nuevo, 'guardados', 0)
        return nuevo

    def fotografiar(self):
        """Guarda la potencia de todas las cargas del proyecto, como al crearlo."""
        for c in self._app.proyecto.GetContents('*.ElmLod', 1):
            self._datos[id(c)] = {k: object.__getattribute__(c, k) for k in _DATOS_DE_OPERACION}

    def Save(self):
        object.__setattr__(self, 'guardados', self.guardados + 1)
        return 0

    def Deactivate(self, *_a):
        self._app.escenario = None
        return 0

    def Activate(self, *_a):
        self._app.escenario = self
        return 0


class Orden(Obj):
    """Orden de cálculo. ``efecto(app, orden)``, si lo hay, imita lo que hace al ejecutarse
    (abrir un interruptor, crear una variación, escribir en la ventana de salida)."""

    def __init__(self, app, nombre, rc=0, clase='ComLdf', efecto=None):
        super().__init__(app, clase, nombre)
        object.__setattr__(self, 'rc', rc)
        object.__setattr__(self, 'efecto', efecto)
        object.__setattr__(self, 'ejecuciones', 0)

    def Execute(self):
        object.__setattr__(self, 'ejecuciones', self.ejecuciones + 1)
        if self.efecto is not None:
            self.efecto(self._app, self)
        return self.rc


class Ventana:
    """Ventana de salida: lo que las órdenes escriben en ``app.salida``."""

    def __init__(self, app):
        self._app = app

    def Clear(self):
        self._app.salida.clear()

    def GetContent(self):
        return list(self._app.salida)


class FlujoConPerdidas(Orden):
    """``ComLdf`` que calcula la cabecera de cada alimentador (spec 006).

    Lo que entra por la cabecera es la suma de sus cargas más ``rp·S²`` y ``rq·S²`` de
    pérdidas (S en MVA), menos ``cables`` Mvar. Si la carga del alimentador pasa de
    ``limite`` MW no converge; cada ajuste del flujo distinto de su valor inicial lo
    sube en ``por_ajuste`` MW, como ayudan en DIgSILENT a converger.
    """

    INICIALES = {'itrlx': 25, 'iStepAdapt': 0, 'iopt_lev': 0, 'iopt_pq': 0}

    def __init__(self, app, rp=0.02, rq=0.04, cables=0.0, limite=math.inf, por_ajuste=0.0):
        super().__init__(app, 'ComLdf')
        for k, v in self.INICIALES.items():
            object.__setattr__(self, k, v)
        for k, v in dict(rp=rp, rq=rq, cables=cables, limite=limite, por_ajuste=por_ajuste,
                         ejecuciones=0).items():
            object.__setattr__(self, k, v)

    def limite_efectivo(self):
        return self.limite + self.por_ajuste * sum(
            getattr(self, k) != v for k, v in self.INICIALES.items())

    def Execute(self):
        object.__setattr__(self, 'ejecuciones', self.ejecuciones + 1)
        app = self._app
        alims = app.proyecto.GetContents('*.ElmFeeder', 1)
        if getattr(self, 'iopt_fls', 0):
            # Escalado por alimentador (spec 011, RF-20): mueve las cargas escalables. Lo
            # imita para que una prueba note si un estudio lo deja encendido.
            for alim in alims:
                for c in alim.GetObjs('ElmLod'):
                    if getattr(c, 'i_scale', 1):
                        c.plini = c.plini * 1.1
        for alim in alims:
            cub = getattr(alim, 'obj_id', None)
            if cub is None:
                continue
            cargas = [o for o in alim.GetObjs('ElmLod') if not getattr(o, 'outserv', 0)]
            # Lo que consumen: lo escrito por su factor de escala (015:RF-44).
            p = sum(c.plini * c.scale0 for c in cargas)
            q = sum(c.qlini * c.scale0 for c in cargas)
            if p > self.limite_efectivo():
                app.ldf_valido = False
                for o in app.proyecto.GetContents('*.ElmTerm', 1):
                    if hasattr(o, 'm_u'):
                        object.__delattr__(o, 'm_u')
                return 1
            s2 = p * p + q * q
            # Consumo efectivo de cada carga y banco, como «m:Psum:bus1» de DIgSILENT: las
            # pérdidas del informe son cabecera menos esto (017:RF-15).
            # ``consumo_relativo`` imita una carga dependiente de la tensión, que consume en
            # terminal menos de lo escrito (006:RF-41).
            for c in cargas:
                rel = float(getattr(c, 'consumo_relativo', 1.0))
                object.__setattr__(c, 'm_Psum:bus1', c.plini * c.scale0 * rel)
                object.__setattr__(c, 'm_Qsum:bus1', c.qlini * c.scale0 * rel)
            for sh in alim.GetObjs('ElmShnt'):
                object.__setattr__(sh, 'm_Psum:bus1', 0.0)
                object.__setattr__(sh, 'm_Qsum:bus1', -float(getattr(sh, 'qcapn', 0.0) or 0.0))
            rama, lado = cub.obj_id, cub.obj_bus + 1
            object.__setattr__(rama, f'm_Psum:bus{lado}', p + self.rp * s2)
            object.__setattr__(rama, f'm_Qsum:bus{lado}', q + self.rq * s2 - self.cables)
            for i, b in enumerate(alim.GetObjs('ElmTerm')):
                object.__setattr__(b, 'm_u', 1.0 - 0.01 * i * p)
            for tr in alim.GetObjs('ElmTr2'):
                carga = next((c for c in cargas if c.loc_name == tr.loc_name.removeprefix('TR_')), None)
                s = math.hypot(carga.plini, carga.qlini) if carga else 0.0
                object.__setattr__(tr, 'c:loading', 100.0 * s / tr.typ_id.strn)
        app.ldf_valido = True
        return 0


# --------------------------------------------------------------------------- spec 012
# Lo que imitan estas clases lo dio DIgSILENT 2024 en las sondas del 2026-10-12 sobre una
# copia de un proyecto real (plan de la spec 012, «Lo que confirmó DIgSILENT»). Los
# números son sintéticos: sirven para que una prueba note un guion equivocado, no para
# validar el cálculo de DIgSILENT.

def _num(x: float) -> str:
    """Como la ventana de salida de DIgSILENT en la configuración regional del usuario."""
    return f'{x:.2f}'.replace('.', ',')


def _dice(app, *lineas):
    app.salida.extend(lineas)


class Seleccion(Obj):
    """``SetSelect``: un conjunto de referencias."""

    def AddRef(self, objs):
        lista = self.__dict__.setdefault('_refs', [])
        for o in (objs if isinstance(objs, (list, tuple)) else [objs]):
            if o not in lista:
                lista.append(o)
        return 0

    def All(self):
        return list(self.__dict__.get('_refs', []))

    def Clear(self):
        self.__dict__['_refs'] = []
        return 0


def _barras_de(alim) -> set[int]:
    return {id(b) for b in alim.GetObjs('ElmTerm')}


def _protegido(app, alim) -> bool:
    """¿Hay un interruptor automático con protección, cerrado, en el alimentador?

    Sin él, ``ComRel3`` no despeja ninguna falla de línea («No protection devices to
    clear the faults»): es lo que pasó con el DGS del conversor, que une la red externa
    al primer tramo sin interruptor (spec 012, RF-69).
    """
    barras = _barras_de(alim)
    for sw in app.proyecto.GetContents('*.StaSwitch', 1) + app.proyecto.GetContents('*.ElmCoup', 1):
        if (getattr(sw, 'aUsage', '') == 'cbk' and getattr(sw, 'rel_hasProt', 0)
                and getattr(sw, 'on_off', 1) == 1):
            padre = sw.GetParent()
            if sw in alim.GetObjs(sw.GetClassName()) or (
                    padre is not None and padre._clase == 'StaCubic' and id(padre._padre) in barras):
                return True
    return False


def _modelo(elem):
    sto = getattr(elem, 'pStoch', None)
    if sto is None:
        return 0.0, 0.0
    return float(getattr(sto, 'DnFr', 0.0)), float(getattr(sto, 'RepMu', 0.0))


class Fiabilidad(Obj):
    """``ComRel3`` de una red radial: cada falla de línea interrumpe todo el alimentador
    durante su reparación, y la de un transformador, solo su carga (``TR_<carga>``).

    Deja los resultados con los nombres reales: por carga ``c:LPIF``, ``c:LPIT``,
    ``c:ACIF``, ``c:ACIT``, ``c:TCIF``, ``c:TCIT``, ``c:LPENS`` (MWh/a); por alimentador
    ``c:SAIFI``, ``c:SAIDI``, ``c:CAIDI``, ``c:ENS``, ``c:MAIFI``; por elemento ``c:C_ENS``,
    ``c:CpENS`` y ``c:C_SAIDI``. Un alimentador con ``sin_tension`` da ceros, como uno con
    la fuente fuera de servicio (RF-71).
    """

    def Execute(self):
        app = self._app
        app.rel_ejecuciones += 1
        _dice(app, 'info - Reliability calculation started')
        sin_despeje = []
        for alim in app.proyecto.GetContents('*.ElmFeeder', 1):
            cargas = alim.GetObjs('ElmLod')
            lineas = alim.GetObjs('ElmLne')
            trafos = {tr.loc_name.removeprefix('TR_'): tr for tr in alim.GetObjs('ElmTr2')}
            con_tension = not getattr(alim, 'sin_tension', 0)
            protegido = _protegido(app, alim)
            if not protegido:
                sin_despeje.extend(lineas)
            lam_l = sum(_modelo(l)[0] * float(getattr(l, 'dline', 1.0)) for l in lineas) if protegido else 0.0
            u_l = sum(_modelo(l)[0] * float(getattr(l, 'dline', 1.0)) * _modelo(l)[1]
                      for l in lineas) if protegido else 0.0
            n_tot = tcif_tot = tcit_tot = ens_tot = 0.0
            p_tot = sum(c.plini for c in cargas)
            for c in cargas:
                lam_t, r_t = _modelo(trafos[c.loc_name]) if c.loc_name in trafos else (0.0, 0.0)
                lpif = (lam_l + lam_t) if con_tension else 0.0
                lpit = (u_l + lam_t * r_t) if con_tension else 0.0
                n = int(getattr(c, 'NrCust', 1) or 1)
                valores = {'c:LPIF': lpif, 'c:LPIT': lpit, 'c:ACIF': lpif, 'c:ACIT': lpit,
                           'c:TCIF': lpif * n, 'c:TCIT': lpit * n, 'c:LPENS': c.plini * lpit,
                           'c:AID': lpit / lpif if lpif else 0.0}
                for k, v in valores.items():
                    object.__setattr__(c, k, v)
                n_tot += n
                tcif_tot += lpif * n
                tcit_tot += lpit * n
                ens_tot += c.plini * lpit
            saifi = tcif_tot / n_tot if n_tot else 0.0
            saidi = tcit_tot / n_tot if n_tot else 0.0
            for k, v in {'c:SAIFI': saifi, 'c:SAIDI': saidi, 'c:CAIDI': saidi / saifi if saifi else 0.0,
                         'c:ENS': ens_tot, 'c:MAIFI': 0.0}.items():
                object.__setattr__(alim, k, v)
            for l in lineas:
                lam, r = _modelo(l)
                u = lam * float(getattr(l, 'dline', 1.0)) * r if (protegido and con_tension) else 0.0
                object.__setattr__(l, 'c:C_ENS', u * p_tot)
                object.__setattr__(l, 'c:CpENS', 100.0 * u * p_tot / ens_tot if ens_tot else 0.0)
                object.__setattr__(l, 'c:C_SAIDI', u)
            for nombre, tr in trafos.items():
                lam, r = _modelo(tr)
                carga = next((c for c in cargas if c.loc_name == nombre), None)
                ens = lam * r * carga.plini if (carga is not None and con_tension) else 0.0
                object.__setattr__(tr, 'c:C_ENS', ens)
                object.__setattr__(tr, 'c:CpENS', 100.0 * ens / ens_tot if ens_tot else 0.0)
        if sin_despeje:
            _dice(app, 'err  - No protection devices to clear the faults of the following '
                       'contingencies were found:',
                  *(f'err  - Contingency: {l.loc_name} (Faulted elements: {l.loc_name})'
                    for l in sin_despeje))
        _dice(app, 'info - Reliability calculation finished')
        return 0


class Reconectadores(Obj):
    """``ComOpri``. Candidatos: interruptores automáticos con protección (``locations=1``)
    o todos los automáticos (``locations=0``), sin los de ``excludedSwts`` ni, con
    ``exclCableProt``, los que tienen ``protege_cable``. Elige los de mayor ``mejora_ens``
    (sintético, MWh/a). Con ``recResults=2`` crea y activa su variación y graba en ella
    ``rel_hasRecl`` y ``reclAttempts``; **cambia la hora de estudio del caso**, como hizo
    DIgSILENT en la sonda (RF-60).
    """

    def Execute(self):
        app = self._app
        app.rel_ejecuciones += 1
        excluidos = {id(o) for o in (self.excludedSwts.All() if getattr(self, 'excludedSwts', None) else [])}
        por_alim = {}
        for alim in app.proyecto.GetContents('*.ElmFeeder', 1):
            for sw in alim.GetObjs('StaSwitch') + alim.GetObjs('ElmCoup'):
                if getattr(sw, 'aUsage', '') != 'cbk' or id(sw) in excluidos:
                    continue
                if getattr(self, 'locations', 1) == 1 and not getattr(sw, 'rel_hasProt', 0):
                    continue
                if getattr(self, 'exclCableProt', 1) and getattr(sw, 'protege_cable', 0):
                    continue
                por_alim.setdefault(alim.loc_name, []).append(sw)
        if not por_alim:
            _dice(app, 'err  - No candidates could be found for the optimisation.',
                  'err  - Optimal Recloser Placement failed.')
            return 1
        elegidos = []
        for lista in por_alim.values():
            lista = sorted((s for s in lista if getattr(s, 'mejora_ens', 0) > 0),
                           key=lambda s: -s.mejora_ens)
            elegidos.extend(lista[:int(getattr(self, 'maxNrPerFeeder', 3))])
        elegidos = sorted(elegidos, key=lambda s: -s.mejora_ens)[:int(getattr(self, 'nrOfRecl', 3))]
        antes = sum(getattr(a, 'c:ENS', 0.0) for a in app.proyecto.GetContents('*.ElmFeeder', 1))
        if not elegidos:
            _dice(app, 'info - No suitable locations for placing reclosers could be identified.')
            return 0
        despues = max(0.0, antes - sum(s.mejora_ens for s in elegidos))
        _dice(app, f'info - The following locations for placing reclosers were determined: '
                   f'({len(elegidos)} objects)',
              f'info - The ENS is reduced by {_num(antes - despues)} MWh/a (Before: '
              f'{_num(antes)} MWh/a, After: {_num(despues)} MWh/a).')
        caso = app.caso
        if caso is not None:
            caso.iStudyTime = getattr(caso, 'iStudyTime', 0) + 3600
        if getattr(self, 'recResults', 0) == 2:
            var = app.carpetas['scheme'].CreateObject('IntScheme', self.variationName)
            var.NewStage(self.variationName, 0, 1)
        if getattr(self, 'recResults', 0) in (1, 2):
            for sw in elegidos:
                sw.rel_hasRecl = 1
                sw.reclAttempts = int(getattr(self, 'maxNrAttempts', 3))
        return 0


class Alojamiento(Obj):
    """``ComHostcap``. ``CalcMaxHostedPower(barra)`` → ``[código, P, Q, elemento]``.

    ``objective`` 0 es generación distribuida y 1 carga nueva. En carga, una barra sin
    carga conectada da ``[1, 0, 0, None]`` («No relevant loads connected», RF-72). Las
    respuestas se pueden fijar en ``app.alojamiento[(objetivo, barra)]``.
    """

    def CalcMaxHostedPower(self, barra):
        app = self._app
        if getattr(app.ldf, 'iopt_fls', 0):
            _dice(app, "err  - Please disable 'Feeder Load Scaling' option.")
            return [0, 0.0, 0.0, None]
        objetivo = int(getattr(self, 'objective', 0))
        fijo = app.alojamiento.get((objetivo, barra.loc_name))
        if fijo is not None:
            return list(fijo)
        alim = next((a for a in app.proyecto.GetContents('*.ElmFeeder', 1)
                     if id(barra) in _barras_de(a)), None)
        lineas = alim.GetObjs('ElmLne') if alim else []
        limita = lineas[0] if lineas else None
        if objetivo == 1:
            con_carga = any(getattr(c, 'obj_id', None) is not None
                            and c.obj_id._clase in ('ElmLod', 'ElmTr2')
                            for c in barra.GetContents('*.StaCubic'))
            if not con_carga:
                _dice(app, 'err  - No relevant loads connected to the selected terminal(s). '
                           'Calculation not possible.')
                return [1, 0.0, 0.0, None]
            return [2, 2.0, 0.0, limita]
        orden = [b.loc_name for b in alim.GetObjs('ElmTerm')] if alim else []
        i = orden.index(barra.loc_name) if barra.loc_name in orden else 0
        return [2, round(10.0 / (1 + i), 4), 0.0, limita]


class CurvasPV(Obj):
    """``ComPvcurves``: escribe el resumen en la ventana de salida, con coma decimal, y
    deja las demandas como estaban. La demanda crítica es la inicial por ``app.pv_factor``;
    la barra crítica, la última del alimentador de la primera carga escalada."""

    def Execute(self):
        app = self._app
        if getattr(self, 'calcCont', 0) and not app.licencia_pv_contingencias:
            _dice(app, "err  - No licence available to execute PV Curves Calculation with "
                       "'Consider contingencies' option.")
            return 1
        if getattr(self, 'frLoads', 0) == 1 and getattr(self, 'pSel_Load', None) is not None:
            cargas = self.pSel_Load.All()
        else:
            cargas = app.proyecto.GetContents('*.ElmLod', 1)
        cargas = [c for c in cargas if c.plini]
        inicial = sum(c.plini for c in cargas)
        critica = inicial * app.pv_factor
        alim = next((a for a in app.proyecto.GetContents('*.ElmFeeder', 1)
                     if cargas and cargas[0] in a.GetObjs('ElmLod')), None)
        barra = alim.GetObjs('ElmTerm')[-1].loc_name if alim else '?'
        _dice(app, 'info - PV Curves calculation started.',
              f'info - Scaling {len(cargas)} load(s).',
              f'info - Initial scalable demand for this case: {_num(inicial)} MW '
              f'(total demand of the system: {_num(inicial)} MW).',
              f'info - Total critical demand of the scaled loads: {_num(critica)} MW.',
              'info - - Contingency              Critical bus               Critical scalable demand -',
              f'info -  Base Case                {barra:<26} {_num(critica):>14}',
              'info - PV Curves calculation finished.')
        return 0


class Condensadores(Obj):
    """``ComCapo``: con ``iopt_con=1`` instala un ``ElmShnt`` por cada propuesta de
    ``app.capo_propuestas`` (``(barra, fila de bancos, pasos)``), en la etapa que grabe;
    ``TotalLossCost()`` da ``app.capo_coste`` antes de ejecutar y después de instalar."""

    def Execute(self):
        app = self._app
        object.__setattr__(self, '_ejecutado', True)
        if getattr(app.ldf, 'iopt_fls', 0):
            _dice(app, 'err  - Please turn off feeder load scaling in load flow command.')
            return 1
        if getattr(self, 'feeder', None) is None:
            _dice(app, 'err  - Please select feeder to be optimised!')
            return 1
        _dice(app, 'Optimal Capacitor Placement')
        if not getattr(self, 'iopt_con', 0):
            return 0
        barras = {b.loc_name: b for b in self.feeder.GetObjs('ElmTerm')}
        qstep = list(getattr(self, 'shntqstep', []))
        for k, (barra, fila, pasos) in enumerate(app.capo_propuestas):
            b = barras.get(barra)
            if b is None:
                continue
            sh = b.GetParent().CreateObject('ElmShnt', f'Shunt/Filter({k}) {k + 1}')
            cub = b.CreateObject('StaCubic', f'c_{sh.loc_name}')
            cub.obj_id = sh
            sh.bus1 = cub
            sh.qcapn, sh.ncapx, sh.ncapa = qstep[fila], pasos, pasos
            sh.ushnm = getattr(b, 'uknom', 0.0)
        return 0

    def TotalLossCost(self):
        antes, despues = self._app.capo_coste
        return despues if self.__dict__.get('_ejecutado') else antes


class Guion(Obj):
    """``ComDpl`` o ``ComPython`` del operador (spec 011, RF-27 a RF-30).

    Los parámetros de entrada son los vectores ``IntName``, ``IntType`` (``int``,
    ``double``, ``string``) e ``IntExpr`` (el valor, como texto), y los objetos externos
    ``obj_name``/``obj_id``, como en ``datascheme.db`` de PF 2024. ``SetInputParameter*``
    devuelve 1 si el parámetro no existe o es de otro tipo, como la API. ``efecto(app,
    guion)`` imita lo que hace el guion; ``rc`` es lo que devuelve ``Execute``.
    """

    def _pon(self, nombre, tipo, valor):
        nombres = list(getattr(self, 'IntName', []))
        if nombre not in nombres or list(self.IntType)[nombres.index(nombre)] != tipo:
            return 1
        expr = list(getattr(self, 'IntExpr', []))
        expr[nombres.index(nombre)] = str(valor)
        self.IntExpr = expr
        return 0

    def SetInputParameterInt(self, nombre, valor):
        return self._pon(nombre, 'int', int(valor))

    def SetInputParameterDouble(self, nombre, valor):
        return self._pon(nombre, 'double', float(valor))

    def SetInputParameterString(self, nombre, valor):
        return self._pon(nombre, 'string', str(valor))

    def SetExternalObject(self, nombre, obj):
        nombres = list(getattr(self, 'obj_name', []))
        if nombre not in nombres:
            return 1
        objs = list(getattr(self, 'obj_id', [None] * len(nombres)))
        objs[nombres.index(nombre)] = obj
        self.obj_id = objs
        return 0

    def Execute(self):
        object.__setattr__(self, 'ejecuciones', getattr(self, 'ejecuciones', 0) + 1)
        efecto = getattr(self, 'efecto', None)
        if efecto is not None:
            efecto(self._app, self)
        return getattr(self, 'rc', 0)


_CLASES = {'ElmLod': Carga, 'IntScheme': Variacion, 'IntSstage': Etapa, 'ComImport': Importacion,
           'IntCase': Caso, 'IntScenario': Escenario,
           'StaSwitch': Interruptor, 'ElmCoup': Interruptor,
           'ComSimoutage': Contingencias, 'ComOutage': Contingencia,
           'SetSelect': Seleccion, 'ComRel3': Fiabilidad, 'ComOpri': Reconectadores,
           'ComHostcap': Alojamiento, 'ComPvcurves': CurvasPV, 'ComCapo': Condensadores,
           'ComDpl': Guion, 'ComPython': Guion}


class App:
    def __init__(self):
        self.escrituras, self.creados = [], []
        # Sin caso activo, el estado es el de la aplicación (los dobles de antes).
        self._sin_caso = _Estado()
        self.caso = None
        self.usuario = Obj(self, 'IntUser', 'usuario')
        self.carpetas = {}
        self.biblioteca_global = Obj(self, 'IntPrjfolder', 'Library')
        self.ldf = None
        self.ldf_valido = True
        self.proyecto = None
        # spec 011: órdenes del caso distintas del flujo, y la ventana de salida
        self.ordenes = {}
        self.salida = []
        self.n1_ejecuciones = 0
        self.trazas, self.trazas_cerradas = [], []
        self.en_falta = set()
        # spec 012
        self.atributos_en_variacion = False
        # spec 006, RF-27: el escenario activo manda sobre la potencia de las cargas.
        self.escenario_manda = False
        self.rel_ejecuciones = 0
        self.alojamiento = {}
        self.pv_factor = 2.7
        self.licencia_pv_contingencias = True
        self.capo_propuestas = []
        self.capo_coste = (100.0, 90.0)
        # spec 005
        self.activo = None
        self.transferencia = {}
        self.movidos, self.borrados, self.importados = [], [], []
        self.fallar_mover = False
        self.fallar_importacion = False
        self.alimentadores_al_importar = ('F1',)

    # ----------------------------------------------------------- spec 011
    @property
    def _estado(self) -> _Estado:
        caso = self.caso
        return caso._estado if isinstance(caso, Caso) else self._sin_caso

    @property
    def variaciones_activas(self):
        return self._estado.variaciones

    @variaciones_activas.setter
    def variaciones_activas(self, valor):
        self._estado.variaciones = valor

    @property
    def grabando(self):
        return self._estado.grabando

    @grabando.setter
    def grabando(self, valor):
        self._estado.grabando = valor

    @property
    def escenario(self):
        return self._estado.escenario

    @escenario.setter
    def escenario(self, valor):
        self._estado.escenario = valor

    def GetGlobalLibrary(self, _clase=''):
        return self.biblioteca_global

    def GetLocalLibrary(self, _clase=''):
        return self.carpetas.get('equip')

    def GetCurrentUser(self):
        return self.usuario

    def GetActiveStudyCase(self):
        return self.caso

    def GetProjectFolder(self, nombre, crear=0):
        """Como la API: con ``crear=1`` crea la carpeta del proyecto si no existe."""
        if nombre not in self.carpetas and crear and self.proyecto is not None:
            self.carpetas[nombre] = self.proyecto.CreateObject('IntPrjfolder', nombre)
        return self.carpetas.get(nombre)

    def GetActiveScenario(self):
        return self.escenario

    def GetRecordingStage(self):
        return self.grabando

    def GetFromStudyCase(self, nombre):
        return self.ldf if nombre == 'ComLdf' else self.ordenes.get(nombre)

    def GetOutputWindow(self):
        return Ventana(self)

    def IsLdfValid(self):
        return self.ldf_valido

    def GetCalcRelevantObjects(self, patron):
        return self.proyecto.GetContents(patron, 1) if self.proyecto else []

    # ----------------------------------------------------------- spec 016
    def SplitLine(self, linea, percent=50, createSwitchSide0=0, createSwitchSide1=0,
                  graphicSplit=0):
        """Como en DIgSILENT 2024 (sonda del 2026-10-14 sobre IN111_TA225, T1 de la 016).

        La línea conserva el nombre y va de su ``bus1`` a la barra nueva, con ``percent`` %
        de la longitud; la copia, ``<nombre>(1)``, va de la barra al otro extremo. Las dos
        conservan tipo, ternas y estado, y las dos se quedan el trazado **entero**. La barra
        nueva se llama ``Terminal``, con la tensión del tramo y **sin GPS**. Todo es de la
        variación que graba: desactivarla devuelve la línea entera.
        """
        if createSwitchSide0:
            raise NotImplementedError('la sonda de la 016 no probó el interruptor del lado 0')
        cubs = [c for c in self.proyecto.GetContents('*.StaCubic', 1)
                if getattr(c, 'obj_id', None) is linea]
        lados = {getattr(c, 'obj_bus', 0): c for c in cubs}
        if (linea is None or linea._clase != 'ElmLne' or not 0 < percent < 100
                or set(lados) != {0, 1}):
            return 0
        red = linea._padre
        ocupados = {h.loc_name for h in red._hijos}
        nombre, n = 'Terminal', 0
        while nombre in ocupados:
            n += 1
            nombre = f'Terminal({n})'
        barra = red.CreateObject('ElmTerm', nombre)
        barra.uknom = getattr(lados[0].cterm, 'uknom', None)
        barra.GPSlat, barra.GPSlon = 0.0, 0.0
        copia = red.CreateObject('ElmLne', f'{linea.loc_name}(1)')
        for k in ('typ_id', 'nlnum', 'outserv'):
            setattr(copia, k, getattr(linea, k, None))
        largo = getattr(linea, 'dline', 0.0) or 0.0
        copia.dline = largo * (100 - percent) / 100
        copia.GPScoords = [list(p) for p in (getattr(linea, 'GPScoords', None) or [])]
        cerca = barra.CreateObject('StaCubic', 'Cub_1')
        cerca.obj_id, cerca.obj_bus = linea, 1
        lejos = barra.CreateObject('StaCubic', 'Cub_0')
        lejos.obj_id, lejos.obj_bus = copia, 0
        if createSwitchSide1:
            sw = lejos.CreateObject('StaSwitch', 'Switch')
            sw.on_off = 1
        # El cubículo del otro extremo pasa a la copia y la línea se acorta. Son cambios de
        # objetos que ya existían: se devuelven al desactivar la variación aunque el doble
        # no tenga ``atributos_en_variacion``, porque DIgSILENT siempre lo hace.
        for obj, k, valor in ((lados[1], 'obj_id', copia), (linea, 'dline', largo * percent / 100)):
            etapa = self.grabando
            if etapa is not None:
                etapa._padre.__dict__.setdefault('_cambios', []).append(
                    (obj, k, getattr(obj, k, None), valor))
                _registrar_en_etapa(etapa, obj, k, valor)
            self.escrituras.append((obj, k, valor, etapa, self.escenario))
            object.__setattr__(obj, k, valor)
        return barra

    # ----------------------------------------------------------- spec 007
    def GetActiveNetworkVariations(self):
        return list(self.variaciones_activas)

    # ----------------------------------------------------------- spec 005
    def DefineTransferAttributes(self, clase, atributos):
        self.transferencia[clase] = [a.strip() for a in atributos.split(',')]

    def GetActiveProject(self):
        return self.activo

    def ActivateProject(self, nombre):
        """Como la API: por nombre, solo entre los proyectos de la raíz del usuario."""
        for prj in self.usuario.GetContents('*.IntPrj'):
            if prj.loc_name == nombre:
                return prj.Activate()
        return 1


def variacion_del_operador(app, nombre: str, cambios) -> Variacion:
    """Variación activa con cambios hechos a mano por el operador (spec 014).

    ``cambios`` son ``(objeto, atributo, valor)``. Imita a CA101 (2026-10-14): el
    operador cambió el tipo de cuatro transformadores y quedaron en la etapa que grababa.
    """
    previa = app.grabando
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage(f'Etapa_{nombre}', getattr(app.caso, 'iStudyTime', 0), 1)
    etapa = next(s for s in v.GetContents('*.IntSstage'))
    app.grabando = etapa          # el operador graba a mano aunque haya empate de fecha
    for obj, atributo, valor in cambios:
        setattr(obj, atributo, valor)
    app.grabando = previa
    return v


def nuevo_proyecto(app, padre, nombre, *, alimentadores=('F1',), con_datos_de_red=True):
    """Proyecto con la estructura de uno importado desde DGS (spec 005).

    ``Network Model / Network Data / Red / <alimentador>``, más casos de estudio y una
    biblioteca. ``con_datos_de_red=False`` imita un proyecto hecho a mano: la red cuelga
    del proyecto sin carpetas de modelo de red.
    """
    prj = Obj(app, 'IntPrj', nombre, padre)
    padre._hijos.append(prj)
    if con_datos_de_red:
        modelo = prj.CreateObject('IntPrjfolder', 'Network Model')
        modelo.iopt_typ = 'netmod'
        datos = modelo.CreateObject('IntPrjfolder', 'Network Data')
        datos.iopt_typ = 'netdat'
        red = datos.CreateObject('ElmNet', 'Red')
    else:
        red = prj.CreateObject('ElmNet', 'Red')
    for f in alimentadores:
        alim = Alimentador(app, f, red)
        red._hijos.append(alim)
    casos = prj.CreateObject('IntPrjfolder', 'Study Cases')
    casos.iopt_typ = 'study'
    casos.CreateObject('IntCase', 'Caso')
    biblioteca = prj.CreateObject('IntPrjfolder', 'Library')
    biblioteca.iopt_typ = 'lib'
    return prj


def proyecto(nombre='P', *, alimentadores=('F1', 'F2'), cargas_por_alim=3, escenario=False,
             con_gps=True, con_trafos=True, frnom=60.0, bt=False, flujo=False, kva=None):
    """Proyecto con N alimentadores; cada uno con una cadena de barras, líneas y SED.

    Barras ``<F>_B0..Bn`` en línea recta (unos 100 m entre barras), líneas ``<F>_L<i>``
    del tipo ``AAAC_<F>``, y SED ``<F>_S<i>`` con su ``ElmTr2`` y su ``ElmLod``.

    ``bt``: barra de baja por SED, cubículos del transformador y de la carga, y cabecera
    del alimentador (spec 006). ``kva``: función ``(alimentador, i) -> kVA`` del
    transformador de cada SED, para sortearlo; por defecto 100. ``flujo``: el ``ComLdf``
    es :class:`FlujoConPerdidas`.
    """
    app = App()
    prj = Obj(app, 'IntPrj', nombre, app.usuario)
    app.usuario._hijos.append(prj)
    app.proyecto = prj
    equip = prj.CreateObject('IntPrjfolder', 'Equipment')
    scheme = prj.CreateObject('IntPrjfolder', 'Variations')
    estudio = prj.CreateObject('IntPrjfolder', 'Study Cases')
    app.caso = estudio.CreateObject('IntCase', 'Caso')
    app.caso.iStudyTime = 1_760_000_000
    app.carpetas = {'equip': equip, 'scheme': scheme, 'study': estudio}
    app.ldf = FlujoConPerdidas(app) if flujo else Orden(app, 'ComLdf')
    red = prj.CreateObject('ElmNet', 'Red')
    red.frnom = frnom
    grf = prj.CreateObject('IntGrfnet', 'Diagrama')
    for k, f in enumerate(alimentadores):
        alim = Alimentador(app, f, red)
        red._hijos.append(alim)
        tipo = equip.CreateObject('TypLne', f'AAAC_{f}')
        tipo.rline, tipo.xline = 0.5, 0.4
        tr_tipo = equip.CreateObject('TypTr2', f'TR100_{f}')
        tr_tipo.strn, tr_tipo.utrn_h, tr_tipo.utrn_l = 0.1, 10.0, 0.38
        tr_tipo.uktr, tr_tipo.tr2cn_h, tr_tipo.tr2cn_l, tr_tipo.nt2ag, tr_tipo.pcutr = 4.5, 'D', 'YN', 11, 1.5
        barras = []
        for i in range(cargas_por_alim + 1):
            b = red.CreateObject('ElmTerm', f'{f}_B{i}')
            b.uknom = 10.0
            if con_gps:
                b.GPSlat, b.GPSlon = -14.0 - 0.01 * k, -75.7 + 0.001 * i
            else:
                b.GPSlat, b.GPSlon = 0.0, 0.0
            barras.append(b)
            alim._objs.append(b)
            g = grf.CreateObject('IntGrf', f'g_{b.loc_name}')
            g.pDataObj, g.sSymNam = b, 'PointTerm'
            g.rCenterX, g.rCenterY, g.rSizeX, g.rSizeY = 10.0 * i, 100.0 * k, 1.0, 1.0
        for i in range(1, len(barras)):
            ln = red.CreateObject('ElmLne', f'{f}_L{i}')
            # Como en DIgSILENT, toda línea tiene sus ternas (1 por defecto) y su
            # «fuera de servicio» (0): sin los atributos, desactivar la variación de una
            # terna más, o restituir un tramo abierto por la transferencia, los dejaba en None.
            ln.typ_id, ln.nlnum, ln.outserv = tipo, 1, 0
            # Spec 016: longitud (km) y trazado, que dan la troncal y el punto de conexión.
            ln.dline = 1.0          # el km que ya suponía la confiabilidad (spec 012)
            ln.GPScoords = ([[barras[i - 1].GPSlat, barras[i - 1].GPSlon],
                             [barras[i].GPSlat, barras[i].GPSlon]] if con_gps else [])
            for lado, b in ((0, barras[i - 1]), (1, barras[i])):
                cub = b.CreateObject('StaCubic', f'c{lado}_{ln.loc_name}')
                cub.obj_id, cub.obj_bus = ln, lado
            alim._objs.append(ln)
        for i in range(1, len(barras)):
            sub = red.CreateObject('ElmSubstat', f'{f}_S{i}')
            carga = sub.CreateObject('ElmLod', f'{f}_S{i}')
            carga.plini, carga.coslini = 0.05, 0.95
            alim._objs.extend([sub, carga])
            if con_trafos:
                tr = sub.CreateObject('ElmTr2', f'TR_{f}_S{i}')
                tr.typ_id = tr_tipo
                if kva is not None:
                    tr.typ_id = equip.CreateObject('TypTr2', f'TR{i}_{f}')
                    tr.typ_id.strn = kva(f, i) / 1000.0
                alim._objs.append(tr)
                if bt:
                    baja = sub.CreateObject('ElmTerm', f'{f}_S{i}_BT')
                    baja.uknom = 0.38
                    for nombre_cub, barra, attr in (('hv', barras[i], 'bushv'), ('lv', baja, 'buslv')):
                        cub = barra.CreateObject('StaCubic', f'{nombre_cub}_{tr.loc_name}')
                        cub.obj_id = tr
                        setattr(tr, attr, cub)
            if bt:
                baja = next((o for o in sub.GetContents('*.ElmTerm')), None) or barras[i]
                cub = baja.CreateObject('StaCubic', f'c_{carga.loc_name}')
                cub.obj_id = carga
                carga.bus1 = cub
        if bt:
            alim.obj_id = next(c for c in barras[0].GetContents('*.StaCubic')
                               if c.obj_id.loc_name == f'{f}_L1')
            alim.iorient = 0          # hacia la rama: lo que entra en ella es del alimentador
    if escenario:
        carpeta = prj.CreateObject('IntPrjfolder', 'Operation Scenarios')
        app.carpetas['scen'] = carpeta
        app.escenario = Escenario(app, 'IntScenario', 'Operador', carpeta)
        carpeta._hijos.append(app.escenario)
    app.escrituras.clear()
    app.creados.clear()
    return app
