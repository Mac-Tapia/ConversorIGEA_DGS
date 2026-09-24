"""Unión de todos los alimentadores en una sola red.

Las tres reglas que estas pruebas fijan, por orden de gravedad si se rompen:

1. **Nunca se fusionan dos tensiones.** Un nodo con el mismo identificador a 10 kV y a
   22,9 kV son dos nodos. Fusionarlos pondría un cortocircuito franco entre niveles y
   el flujo de potencia daría cualquier cosa sin avisar.
2. **Las áreas sin fuente salen de servicio, no se borran.** PowerFactory resuelve
   todas las áreas aisladas en un mismo sistema de Newton; un área sin referencia de
   tensión estanca el solver de toda la red. Medido: con 13 alimentadores «Newton
   algorithm stagnated → No convergence». Pero los elementos siguen en el modelo,
   porque se pidió que todo se dibuje.
3. **La identidad de cada alimentador sobrevive a la unión.** Una fuente y un
   ``ElmFeeder`` por alimentador; si se pierden, deja de poder distinguirse quién
   alimenta qué dentro de la red común.
"""

from __future__ import annotations

import pytest

from igea_dgs.combine import (
    CombinedInfo,
    combine_models,
    type_key_for,
    unsupplied_nodes,
)
from igea_dgs.model import FeederModel, Line, LineType, Load, Node, Sed


def _tipo(code: str = 'AA12003D', tabla: str = 'LINE') -> LineType:
    return LineType(f'{tabla}:{code}', code, tabla, 0.28, 0.7, 0.43, 1.3, 3.7, 3.7, 340.0)


def _alimentador(
    nombre: str, kv: float, nodos: list[str], *, fuente: str | None = None,
    con_carga: str | None = None, sueltos: tuple[str, str] | None = None,
) -> FeederModel:
    """Cadena de nodos; ``sueltos`` añade un tramo desconectado de la fuente."""
    tipo = _tipo()
    todos = list(nodos) + (list(sueltos) if sueltos else [])
    nodes = {n: Node(n, float(i) * 100.0, 0.0) for i, n in enumerate(todos)}
    lines = [
        Line(f'{nombre}_SEC{i}', a, b, 'ABC', tipo.key, tipo.code, 100.0, True)
        for i, (a, b) in enumerate(zip(nodos, nodos[1:]))
    ]
    if sueltos:
        lines.append(Line(f'{nombre}_ISLA', sueltos[0], sueltos[1], 'ABC',
                          tipo.key, tipo.code, 100.0, True))
    loads, seds = [], []
    if con_carga:
        loads.append(Load(f'{nombre}_SECL', 'D1', 'C', '1', con_carga, 0.05, 0.01,
                          0.95, 50.0, 0.0, 'ABC', sed_code=f'SE_{nombre}',
                          display_name=f'SE_{nombre}'))
        seds.append(Sed(f'SE_{nombre}', f'SE_{nombre}', con_carga, 100.0,
                        f'{nombre}_SECL', 'D1', (f'{nombre}_SECL', 'D1')))
    return FeederModel(
        name=nombre, network_id=f'NET_{nombre}', nominal_kv=kv,
        source_node=fuente or nodos[0], nodes=nodes, lines=lines, loads=loads,
        devices=[], line_types={tipo.key: tipo}, seds=seds,
    )


class TestNoSeFusionanTensiones:
    """Lo más grave que podría hacer mal esta función."""

    def test_un_nodo_a_dos_tensiones_se_separa(self):
        a = _alimentador('A', 10.0, ['N1', 'COMPARTIDO'])
        b = _alimentador('B', 22.9, ['N9', 'COMPARTIDO'])
        modelo, informe = combine_models([a, b])
        assert informe.voltage_conflicts == 1
        assert 'COMPARTIDO' not in modelo.nodes, 'no debe quedar el nombre ambiguo'
        separados = [n for n in modelo.nodes if n.startswith('COMPARTIDO')]
        assert len(separados) == 2, separados

    def test_cada_separado_conserva_su_tension(self):
        a = _alimentador('A', 10.0, ['N1', 'COMPARTIDO'])
        b = _alimentador('B', 22.9, ['N9', 'COMPARTIDO'])
        modelo, _ = combine_models([a, b])
        info: CombinedInfo = modelo.combined
        tensiones = {info.node_kv[n] for n in modelo.nodes if n.startswith('COMPARTIDO')}
        assert tensiones == {10.0, 22.9}

    def test_el_aviso_explica_por_que_no_se_fusiona(self):
        a = _alimentador('A', 10.0, ['N1', 'X'])
        b = _alimentador('B', 22.9, ['N9', 'X'])
        _modelo, informe = combine_models([a, b])
        aviso = next(w for w in informe.warnings if 'X' in w)
        assert 'cortocircuito' in aviso
        assert '10 kV' in aviso and '22.9 kV' in aviso

    def test_un_nodo_compartido_a_la_MISMA_tension_es_un_enlace(self):
        """Ese es el punto de enlace, y es justo lo que la unión aporta."""
        a = _alimentador('A', 10.0, ['N1', 'ENLACE'])
        b = _alimentador('B', 10.0, ['N9', 'ENLACE'])
        modelo, informe = combine_models([a, b])
        assert informe.tie_nodes == 1
        assert modelo.combined.tie_nodes['ENLACE'] == ['A', 'B']


class TestAreasSinFuente:
    def test_lo_no_alcanzable_se_marca_fuera_de_servicio(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        modelo, informe = combine_models([a])
        assert modelo.combined.de_energised == {'S1', 'S2'}
        assert informe.de_energised_nodes == 2
        assert informe.de_energised_lines == 1

    def test_no_se_borra_nada(self):
        """Se pidió que todo se dibuje: fuera de servicio no es borrado."""
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        modelo, _ = combine_models([a])
        assert {'S1', 'S2'} <= set(modelo.nodes)
        assert any(l.section_id == 'A_ISLA' for l in modelo.lines)

    def test_se_puede_desactivar(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        modelo, informe = combine_models([a], de_energise_islands=False)
        assert modelo.combined.de_energised == set()
        assert informe.de_energised_nodes == 0

    def test_la_busqueda_parte_de_TODAS_las_fuentes(self):
        """Con una sola fuente, 95 alimentadores parecerían islas."""
        a = _alimentador('A', 10.0, ['A1', 'A2'])
        b = _alimentador('B', 10.0, ['B1', 'B2'])
        modelo, informe = combine_models([a, b])
        assert informe.de_energised_nodes == 0, 'ningún alimentador está aislado'
        assert unsupplied_nodes(modelo, ['A1']) == {'B1', 'B2'}, (
            'partiendo de una sola fuente, el otro alimentador sí sale aislado'
        )

    def test_el_aviso_cita_el_manual_y_dice_que_no_se_borra(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        _modelo, informe = combine_models([a])
        aviso = next(w for w in informe.warnings if 'fuera de servicio' in w.lower()
                     or 'FUERA DE SERVICIO' in w)
        assert '24.6.3' in aviso
        assert 'dibuj' in aviso

    def test_cuenta_la_potencia_atrapada(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        # Una carga colgada del tramo suelto.
        a.loads.append(Load('A_SECI', 'D9', 'C', '1', 'S2', 0.02, 0.005, 0.95,
                            20.0, 0.0, 'ABC'))
        _modelo, informe = combine_models([a])
        assert informe.de_energised_loads == 1
        assert informe.de_energised_kw == pytest.approx(20.0)


class TestTiposPorTension:
    def test_el_mismo_conductor_a_dos_tensiones_da_dos_tipos(self):
        """TypLne lleva uline, así que son dos tipos distintos en PowerFactory."""
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        modelo, informe = combine_models([a, b])
        assert informe.line_types_in == 1
        assert informe.line_types_out == 2
        assert set(modelo.combined.type_kv.values()) == {10.0, 22.9}

    def test_cada_tramo_apunta_a_un_tipo_que_existe(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        modelo, _ = combine_models([a, b])
        for linea in modelo.lines:
            assert linea.type_key in modelo.line_types, linea.section_id

    def test_la_clave_conserva_el_prefijo_que_distingue_aereo_de_cable(self):
        """El escritor usa LINE:/CABLE: para cohl_; perderlo cambiaría el tipo."""
        assert type_key_for('LINE:AA12003D', 22.9).startswith('LINE:')
        assert type_key_for('CABLE:N212003D', 10.0).startswith('CABLE:')

    def test_el_tipo_conserva_su_codigo_original(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        modelo, _ = combine_models([a])
        assert {t.code for t in modelo.line_types.values()} == {'AA12003D'}


class TestIdentidadDeCadaAlimentador:
    def test_hay_una_fuente_por_alimentador(self):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(5)]
        modelo, _ = combine_models(modelos)
        assert len(modelo.combined.feeders) == 5
        assert {f.name for f in modelo.combined.feeders} == {f'F{i}' for i in range(5)}

    def test_la_fuente_apunta_a_un_nodo_que_existe(self):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(4)]
        modelo, _ = combine_models(modelos)
        for ref in modelo.combined.feeders:
            assert ref.source_node in modelo.nodes, ref.name

    def test_la_fuente_sigue_al_nodo_renombrado_por_conflicto(self):
        a = _alimentador('A', 10.0, ['CHOQUE', 'N2'])
        b = _alimentador('B', 22.9, ['CHOQUE', 'M2'])
        modelo, _ = combine_models([a, b])
        for ref in modelo.combined.feeders:
            assert ref.source_node in modelo.nodes, ref.name

    def test_no_se_pierde_ni_se_duplica_ningun_tramo(self):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b', f'{i}c'])
                   for i in range(6)]
        modelo, informe = combine_models(modelos)
        ids = [l.section_id for l in modelo.lines]
        assert len(ids) == len(set(ids)), 'tramos duplicados'
        assert informe.lines == sum(len(m.lines) for m in modelos)

    def test_un_nodo_sin_coordenadas_toma_las_del_otro_alimentador(self):
        """Solo aplica cuando los nodos se fusionan de verdad."""
        a = _alimentador('A', 10.0, ['N1', 'ENLACE'])
        b = _alimentador('B', 10.0, ['M1', 'ENLACE'])
        a.nodes['ENLACE'] = Node('ENLACE', None, None)
        modelo, _ = combine_models([a, b], tie_mode='merge')
        assert modelo.nodes['ENLACE'].x is not None


class TestEscrituraDelDgs:
    def _escribir(self, modelos, tmp_path):
        from igea_dgs.dgs import write_dgs

        modelo, informe = combine_models(modelos)
        destino = tmp_path / 'sistema.dgs'
        write_dgs(modelo, destino)
        return modelo, informe, destino.read_text(encoding='latin-1')

    def _filas(self, texto: str, tabla: str) -> list[tuple[list[str], list[str]]]:
        """Filas de una tabla del DGS, con su cabecera ya alineada.

        La cabecera empieza por ``$$ElmTerm;FID;...`` y las filas por ``FID;...``, así
        que los índices están desplazados en uno. Alinearlos aquí evita leer la columna
        de al lado y creerse el resultado.
        """
        filas: list[tuple[list[str], list[str]]] = []
        actual, cab = None, []
        for linea in texto.splitlines():
            if linea.startswith('$$'):
                actual = linea[2:].split(';')[0]
                cab = [c.strip() for c in linea.split(';')][1:]
            elif actual == tabla and linea.strip():
                filas.append(([c.strip() for c in linea.split(';')], cab))
        return filas

    def test_una_sola_red(self, tmp_path):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(4)]
        _m, _i, texto = self._escribir(modelos, tmp_path)
        assert len(self._filas(texto, 'ElmNet')) == 1, 'debe ser UNA sola grid'

    def test_una_fuente_y_un_elmfeeder_por_alimentador(self, tmp_path):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(4)]
        _m, _i, texto = self._escribir(modelos, tmp_path)
        assert len(self._filas(texto, 'ElmXnet')) == 4
        assert len(self._filas(texto, 'ElmFeeder')) == 4

    def test_cada_nodo_lleva_SU_tension(self, tmp_path):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        _m, _i, texto = self._escribir([a, b], tmp_path)
        tensiones = {}
        for campos, cab in self._filas(texto, 'ElmTerm'):
            i_n, i_u = cab.index('loc_name(a:40)'), cab.index('uknom(r)')
            tensiones[campos[i_n]] = float(campos[i_u])
        assert tensiones['N1'] == pytest.approx(10.0)
        assert tensiones['M1'] == pytest.approx(22.9)

    def test_los_nodos_sin_fuente_salen_fuera_de_servicio(self, tmp_path):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        _m, _i, texto = self._escribir([a], tmp_path)
        estado = {}
        for campos, cab in self._filas(texto, 'ElmTerm'):
            i_n, i_o = cab.index('loc_name(a:40)'), cab.index('outserv(i)')
            estado[campos[i_n]] = campos[i_o]
        assert estado['S1'] == '1' and estado['S2'] == '1'
        assert estado['N1'] == '0' and estado['N2'] == '0'

    def test_los_tipos_por_tension_tienen_nombres_distintos(self, tmp_path):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        _m, _i, texto = self._escribir([a, b], tmp_path)
        nombres = []
        for campos, cab in self._filas(texto, 'TypLne'):
            nombres.append(campos[cab.index('loc_name(a:40)')])
        assert len(nombres) == len(set(nombres)), f'nombres repetidos: {nombres}'
        assert len(nombres) == 2

    def test_un_solo_alimentador_escribe_igual_que_antes(self, tmp_path):
        """La unión no debe cambiar el DGS de un alimentador suelto."""
        from igea_dgs.dgs import write_dgs

        suelto = _alimentador('A', 10.0, ['N1', 'N2'], con_carga='N2')
        directo = tmp_path / 'directo.dgs'
        write_dgs(suelto, directo)
        filas_directo = self._filas(directo.read_text(encoding='latin-1'), 'ElmTerm')

        combinado, _ = combine_models([_alimentador('A', 10.0, ['N1', 'N2'],
                                                    con_carga='N2')])
        unido = tmp_path / 'unido.dgs'
        write_dgs(combinado, unido)
        filas_unido = self._filas(unido.read_text(encoding='latin-1'), 'ElmTerm')
        assert len(filas_directo) == len(filas_unido)


class TestExportReal:
    def test_los_96_alimentadores_se_unen(self, ds):
        from igea_dgs.combine import build_combined

        modelo, informe = build_combined(ds, include_geography=False)
        assert informe.feeders > 1
        assert informe.nodes_out <= informe.nodes_in
        # Cada tramo apunta a un tipo y a nodos que existen: si esto falla, el DGS
        # sale con referencias colgando y PowerFactory lo rechaza en la importación.
        for linea in modelo.lines:
            assert linea.type_key in modelo.line_types
            assert linea.from_node in modelo.nodes
            assert linea.to_node in modelo.nodes
        for ref in modelo.combined.feeders:
            assert ref.source_node in modelo.nodes

    def test_ninguna_carga_activa_queda_sin_camino_a_una_fuente(self, ds):
        """Lo que hacía estancar el Newton de toda la red."""
        from igea_dgs.combine import build_combined

        modelo, _ = build_combined(ds, include_geography=False)
        apagados = modelo.combined.de_energised
        vivas = [c for c in modelo.loads if c.node_id not in apagados]
        sin_camino = unsupplied_nodes(modelo, (f.source_node for f in modelo.combined.feeders))
        assert not [c for c in vivas if c.node_id in sin_camino]


class TestEnlacesNormalmenteAbiertos:
    """La red real es radial y los alimentadores se enlazan con interruptores abiertos.

    Fusionar los nodos compartidos dejaba todos esos enlaces cerrados: la red pasaba a
    ser mallada, se perdía la radialidad y cada alimentador dejaba de poder estudiarse
    por separado. Además, sin puntos de apertura declarados no hay nada que optimizar
    para ``ComTieopt`` (manual §41.6).
    """

    def _par(self):
        return (_alimentador('A', 10.0, ['A1', 'ENLACE']),
                _alimentador('B', 10.0, ['B1', 'ENLACE']))

    def test_cada_alimentador_conserva_su_propio_nodo(self):
        modelo, _ = combine_models(self._par())
        assert 'ENLACE@A' in modelo.nodes
        assert 'ENLACE@B' in modelo.nodes
        assert 'ENLACE' not in modelo.nodes

    def test_se_crea_un_interruptor_de_enlace(self):
        modelo, informe = combine_models(self._par())
        assert informe.tie_switches == 1
        enlace = modelo.combined.ties[0]
        assert {enlace.feeder_a, enlace.feeder_b} == {'A', 'B'}
        assert enlace.original_node == 'ENLACE'

    def test_el_nombre_dice_que_es_un_enlace_y_entre_quienes(self):
        modelo, _ = combine_models(self._par())
        nombre = modelo.combined.ties[0].name
        assert nombre.startswith('TIE_')
        assert 'A' in nombre and 'B' in nombre
        assert len(nombre) <= 40, 'loc_name de PowerFactory se trunca en 40'

    def test_la_radialidad_se_conserva(self):
        """Con el enlace abierto, cada alimentador sigue siendo un árbol."""
        modelo, _ = combine_models(self._par())
        # Un árbol con N nodos tiene N-1 aristas; dos árboles, N-2.
        assert len(modelo.lines) == len(modelo.nodes) - 2

    def test_tres_alimentadores_en_un_nodo_dan_dos_interruptores(self):
        """Encadenados: cerrar uno basta para transferir entre dos."""
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', 'ENLACE']) for i in range(3)]
        _modelo, informe = combine_models(modelos)
        assert informe.tie_switches == 2

    def test_en_modo_merge_no_hay_interruptores(self):
        modelo, informe = combine_models(self._par(), tie_mode='merge')
        assert informe.tie_switches == 0
        assert 'ENLACE' in modelo.nodes

    def test_el_dgs_escribe_el_interruptor_ABIERTO(self, tmp_path):
        from igea_dgs.dgs import write_dgs

        modelo, _ = combine_models(self._par())
        destino = tmp_path / 'enlaces.dgs'
        write_dgs(modelo, destino)
        texto = destino.read_text(encoding='latin-1')

        cab, filas = [], []
        actual = None
        for linea in texto.splitlines():
            if linea.startswith('$$'):
                actual = linea[2:].split(';')[0]
                if actual == 'ElmCoup':
                    cab = [c.strip() for c in linea.split(';')][1:]
            elif actual == 'ElmCoup' and linea.strip():
                filas.append([c.strip() for c in linea.split(';')])

        tie = [f for f in filas if f[cab.index('loc_name(a:40)')].startswith('TIE_')]
        assert len(tie) == 1, f'debe haber un ElmCoup de enlace: {filas}'
        assert tie[0][cab.index('on_off(i)')] == '0', 'el enlace debe salir ABIERTO'

    def test_el_interruptor_tiene_un_cubiculo_a_cada_lado(self, tmp_path):
        from igea_dgs.dgs import write_dgs

        modelo, _ = combine_models(self._par())
        destino = tmp_path / 'enlaces.dgs'
        write_dgs(modelo, destino)
        texto = destino.read_text(encoding='latin-1')
        cubs = [l for l in texto.splitlines() if 'Cub1_TIE_' in l or 'Cub2_TIE_' in l]
        assert len(cubs) == 2, cubs


class TestEnlacesEnElExportReal:
    def test_los_enlaces_reales_salen_abiertos(self, ds):
        from igea_dgs.combine import build_combined

        modelo, informe = build_combined(ds, include_geography=False)
        if not informe.tie_switches:
            pytest.skip('el export cargado no tiene enlaces entre alimentadores')
        # Cada enlace une nodos de dos alimentadores distintos, y ambos existen.
        for enlace in modelo.combined.ties:
            assert enlace.feeder_a != enlace.feeder_b
            assert enlace.node_a in modelo.nodes
            assert enlace.node_b in modelo.nodes
            assert enlace.node_a != enlace.node_b

    def test_ningun_alimentador_queda_conectado_a_otro(self, ds):
        """La prueba que importa: con los enlaces abiertos, cada uno es su propia isla.

        Es lo que hace que un alimentador converja dentro de la red unida igual que
        converge en su DGS individual.
        """
        import collections

        from igea_dgs.combine import build_combined

        modelo, _ = build_combined(ds, include_geography=False)
        info = modelo.combined
        ady = collections.defaultdict(list)
        for linea in modelo.lines:
            ady[linea.from_node].append(linea.to_node)
            ady[linea.to_node].append(linea.from_node)

        for ref in info.feeders:
            vistos = {ref.source_node}
            pila = [ref.source_node]
            while pila:
                n = pila.pop()
                for v in ady.get(n, ()):
                    if v not in vistos:
                        vistos.add(v)
                        pila.append(v)
            otras = {f for n in vistos for f in info.feeder_of_node.get(n, ())}
            assert otras <= {ref.name}, (
                f'{ref.name} alcanza por líneas a {sorted(otras - {ref.name})}: '
                'el enlace no quedó abierto'
            )


class TestConflictoDeTensionNoSeEnlaza:
    """Un interruptor entre 10 kV y 22,9 kV no es un enlace: es un error esperando."""

    def test_no_se_crea_interruptor_entre_tensiones_distintas(self):
        a = _alimentador('A', 10.0, ['A1', 'CHOQUE'])
        b = _alimentador('B', 22.9, ['B1', 'CHOQUE'])
        modelo, informe = combine_models([a, b])
        assert informe.voltage_conflicts == 1
        assert informe.tie_switches == 0, (
            'los nodos con conflicto de tensión quedan separados y sin unir'
        )

    def test_ningun_enlace_une_tensiones_distintas(self):
        """Invariante que debe cumplirse siempre, no solo en el caso simple."""
        modelos = [
            _alimentador('A', 10.0, ['A1', 'CHOQUE', 'X']),
            _alimentador('B', 22.9, ['B1', 'CHOQUE']),
            _alimentador('C', 10.0, ['C1', 'X']),
        ]
        modelo, informe = combine_models(modelos)
        info = modelo.combined
        for enlace in info.ties:
            assert info.node_kv[enlace.node_a] == info.node_kv[enlace.node_b], enlace
        # El enlace legítimo A–C a 10 kV sí debe existir.
        assert informe.tie_switches == 1
