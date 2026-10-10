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
        cls = {'ElmLod': Carga, 'IntScheme': Variacion, 'ComImport': Importacion}.get(clase, Obj)
        hijo = cls(self._app, clase, nombre, self)
        self._hijos.append(hijo)
        self._app.creados.append(hijo)
        return hijo

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
                out.extend(h.GetContents(patron, 1))
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
        return 0

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
            self.Activate()
            self._app.grabando = etapa
        return 0

    def Activate(self, *_a):
        if self not in self._app.variaciones_activas:
            self._app.variaciones_activas.append(self)
        return 0

    def Deactivate(self, *_a):
        app = self._app
        if self in app.variaciones_activas:
            app.variaciones_activas.remove(self)
        if app.grabando is not None and app.grabando._padre is self:
            app.grabando = None
        return 0


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
        cubiculos: dict[int, list] = {}
        for c in (o for o in app.creados if o._clase == 'StaCubic' and o.en_red):
            if getattr(c, 'obj_id', None) is not None:
                cubiculos.setdefault(id(c.obj_id), []).append(c)
        vistos = {id(o) for o in self._objs}
        pendientes = [o for o in self._objs if o._clase == 'ElmTerm']
        out = []
        while pendientes:
            barra = pendientes.pop()
            for cub in barra.GetContents('*.StaCubic'):
                elem = getattr(cub, 'obj_id', None)
                if elem is None or id(elem) in vistos or elem.etapa_creacion is None:
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
        for alim in alims:
            cub = getattr(alim, 'obj_id', None)
            if cub is None:
                continue
            cargas = [o for o in alim.GetObjs('ElmLod') if not getattr(o, 'outserv', 0)]
            p = sum(c.plini for c in cargas)
            q = sum(c.qlini for c in cargas)
            if p > self.limite_efectivo():
                app.ldf_valido = False
                for o in app.proyecto.GetContents('*.ElmTerm', 1):
                    if hasattr(o, 'm_u'):
                        object.__delattr__(o, 'm_u')
                return 1
            s2 = p * p + q * q
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


class App:
    def __init__(self):
        self.escrituras, self.creados = [], []
        self.grabando = None
        self.escenario = None
        self.variaciones_activas = []
        self.usuario = Obj(self, 'IntUser', 'usuario')
        self.carpetas = {}
        self.caso = None
        self.ldf = None
        self.ldf_valido = True
        self.proyecto = None
        # spec 005
        self.activo = None
        self.transferencia = {}
        self.movidos, self.borrados, self.importados = [], [], []
        self.fallar_mover = False
        self.fallar_importacion = False
        self.alimentadores_al_importar = ('F1',)

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
        app.escenario = Escenario(app, 'IntScenario', 'Operador', carpeta)
    app.escrituras.clear()
    app.creados.clear()
    return app
