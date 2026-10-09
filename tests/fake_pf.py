"""DIgSILENT simulado para probar ``tools/cargas_pf.py`` sin PowerFactory (spec 004).

Imita lo justo de la API: árbol de objetos con ``CreateObject``/``GetContents``,
alimentadores con ``GetObjs``, variaciones con ``NewStage`` y la etapa que graba,
escenario activo y ``ComLdf``. Las cargas reproducen la regla que motivó RF-9: en modo
P–cos φ los datos son P y cos φ, y escribir S recalcula P desde el cos φ anterior.
Cada escritura queda anotada con la etapa que grababa y el escenario activo, para
comprobar que todo fue a la variación nueva.
"""
from __future__ import annotations

import math


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
        if self._app is not None and name != 'loc_name':
            self._app.escrituras.append((self, name, value, self._app.grabando,
                                         self._app.escenario))
        object.__setattr__(self, name, value)

    # ----------------------------------------------------------- árbol
    def GetClassName(self):
        return self._clase

    def GetParent(self):
        return self._padre

    def GetFullName(self):
        return (self._padre.GetFullName() + '\\' if self._padre else '') + f'{self.loc_name}.{self._clase}'

    def CreateObject(self, clase, nombre):
        cls = {'ElmLod': Carga, 'IntScheme': Variacion}.get(clase, Obj)
        hijo = cls(self._app, clase, nombre, self)
        self._hijos.append(hijo)
        self._app.creados.append(hijo)
        return hijo

    def GetContents(self, patron='*', recursivo=0):
        clase = patron.split('.', 1)[1] if '.' in patron else None
        out = []
        for h in self._hijos:
            if clase is None or h._clase == clase:
                out.append(h)
            if recursivo:
                out.extend(h.GetContents(patron, 1))
        return out

    def GetAttributeLength(self, _name):
        return 20

    def SetAttribute(self, name, value):
        setattr(self, name, value)

    def GetAttribute(self, name):
        return getattr(self, name.replace('m:', 'm_'))

    def HasResults(self):
        return hasattr(self, 'm_u')

    def Activate(self, *_a):
        return 0


class Carga(Obj):
    """ElmLod con P y cos φ como datos en modo PC (y P, Q en PQ)."""

    def __init__(self, app, clase, nombre, padre=None, **attrs):
        object.__setattr__(self, '_p', 0.0)
        object.__setattr__(self, '_q', 0.0)
        object.__setattr__(self, '_cos', 1.0)
        attrs.setdefault('mode_inp', 'PC')
        attrs.setdefault('i_sym', 0)
        attrs.setdefault('pf_recap', 0)
        super().__init__(app, clase, nombre, padre, **attrs)

    def __setattr__(self, name, value):
        if name in ('plini', 'qlini', 'slini', 'coslini'):
            if self._app is not None:
                self._app.escrituras.append((self, name, value, self._app.grabando,
                                             self._app.escenario))
            modo = self.mode_inp
            if name == 'plini':
                object.__setattr__(self, '_p', float(value))
            elif name == 'coslini':
                object.__setattr__(self, '_cos', float(value))
            elif name == 'qlini':
                if modo == 'PQ':
                    object.__setattr__(self, '_q', float(value))
                else:     # en PC la Q es derivada: escribirla mueve el cos φ
                    s = math.hypot(self._p, float(value))
                    object.__setattr__(self, '_cos', abs(self._p) / s if s else 1.0)
            elif name == 'slini':
                # El fallo documentado: en PC, S recalcula P con el cos φ que hubiera.
                object.__setattr__(self, '_p', float(value) * self._cos)
            return
        super().__setattr__(name, value)

    @property
    def plini(self):
        return self._p

    @property
    def coslini(self):
        if self.mode_inp == 'PQ':
            s = math.hypot(self._p, self._q)
            return abs(self._p) / s if s else 1.0
        return self._cos

    @property
    def qlini(self):
        if self.mode_inp == 'PQ':
            return self._q
        q = abs(self._p) * math.tan(math.acos(min(1.0, max(0.0, self._cos))))
        return -q if self.pf_recap else q

    @property
    def slini(self):
        return math.hypot(self.plini, self.qlini)


class Variacion(Obj):
    def NewStage(self, nombre, _instante, activar):
        etapa = self.CreateObject('IntSstage', nombre)
        if activar:
            self._app.variaciones_activas.append(self)
            self._app.grabando = etapa
        return 0


class Alimentador(Obj):
    def __init__(self, app, nombre, padre):
        super().__init__(app, 'ElmFeeder', nombre, padre)
        object.__setattr__(self, '_objs', [])

    def GetObjs(self, clase):
        return [o for o in self._objs if o._clase == clase]


class Escenario(Obj):
    def Deactivate(self, *_a):
        self._app.escenario = None
        return 0

    def Activate(self, *_a):
        self._app.escenario = self
        return 0


class Orden(Obj):
    def __init__(self, app, nombre, rc=0):
        super().__init__(app, 'ComLdf', nombre)
        object.__setattr__(self, 'rc', rc)

    def Execute(self):
        return self.rc


class App:
    def __init__(self):
        self.escrituras, self.creados = [], []
        self.grabando = None
        self.escenario = None
        self.variaciones_activas = []
        self.usuario = Obj(None, 'IntUser', 'usuario')
        object.__setattr__(self.usuario, '_app', None)
        self.carpetas = {}
        self.caso = None
        self.ldf = None
        self.ldf_valido = True
        self.proyecto = None

    def GetCurrentUser(self):
        return self.usuario

    def GetActiveStudyCase(self):
        return self.caso

    def GetProjectFolder(self, nombre):
        return self.carpetas.get(nombre)

    def GetActiveScenario(self):
        return self.escenario

    def GetRecordingStage(self):
        return self.grabando

    def GetFromStudyCase(self, nombre):
        return self.ldf if nombre == 'ComLdf' else None

    def IsLdfValid(self):
        return self.ldf_valido

    def GetCalcRelevantObjects(self, patron):
        return self.proyecto.GetContents(patron, 1) if self.proyecto else []


def proyecto(nombre='P', *, alimentadores=('F1', 'F2'), cargas_por_alim=3, escenario=False,
             con_gps=True, con_trafos=True, frnom=60.0):
    """Proyecto con N alimentadores; cada uno con una cadena de barras, líneas y SED.

    Barras ``<F>_B0..Bn`` en línea recta (unos 100 m entre barras), líneas ``<F>_L<i>``
    del tipo ``AAAC_<F>``, y SED ``<F>_S<i>`` con su ``ElmTr2`` y su ``ElmLod``.
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
    app.ldf = Orden(app, 'ComLdf')
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
            ln.typ_id = tipo
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
                alim._objs.append(tr)
    if escenario:
        carpeta = prj.CreateObject('IntPrjfolder', 'Operation Scenarios')
        app.escenario = Escenario(app, 'IntScenario', 'Operador', carpeta)
    app.escrituras.clear()
    app.creados.clear()
    return app
