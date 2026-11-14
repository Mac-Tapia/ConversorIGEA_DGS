import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { LibrosNuevos } from '../../api/types';
import { useApp } from '../../shared/context';

/** Un mes que repite otro o un libro que no se lee pide algo al operador; lo demás informa. */
export function esAlerta(texto: string): boolean {
  return /repite los valores|no se pudo|incompleto|interrumpida|queda fuera|no reconocido|le falta|no se usa/.test(texto);
}

/** 104:RF-44, RF-47, 089:RF-109: cada aviso dice de qué es; antes todos decían «Libro de demanda reconocido». */
export function tituloDelAviso(tipo: string): string {
  if (tipo === 'dataset') return 'Dataset del pronóstico.';
  if (tipo === 'apartado') return 'Libro de demanda apartado.';
  if (tipo === 'formato') return 'Formato de libro de clientes.';
  return 'Libro de demanda reconocido.';
}

/** 089:RF-110: el aviso de un formato con columnas por confirmar trae su huella y lo que falta. */
export function porConfirmar(ficha: Record<string, unknown> | null | undefined): { huella: string; falta: string[] } | null {
  const huella = typeof ficha?.huella === 'string' ? ficha.huella : '';
  const falta = Array.isArray(ficha?.falta) ? ficha.falta.filter((x): x is string => typeof x === 'string') : [];
  return huella && falta.length ? { huella, falta } : null;
}

const CAMPO_DE_ETIQUETA: Record<string, string> = { 'día': 'dia', hora: 'hora', EA: 'ea', ERI: 'eri', Pot: 'pot' };

/** Una columna por cada campo que falta (su letra, como «K»); se guarda una vez para todos los libros iguales. */
function ConfirmarFormato({ huella, falta, confirmar }: {
  huella: string; falta: string[]; confirmar: (huella: string, columnas: Record<string, string>) => void;
}) {
  const [columnas, setColumnas] = useState<Record<string, string>>({});
  const listas = falta.filter((f) => CAMPO_DE_ETIQUETA[f]);
  const completas = listas.length > 0 && listas.every((f) => (columnas[CAMPO_DE_ETIQUETA[f]] ?? '').trim());
  return (
    <div className="row">
      {listas.map((f) => (
        <label key={f} className="small">
          Columna de {f}{' '}
          <input className="input input-sm" size={3} value={columnas[CAMPO_DE_ETIQUETA[f]] ?? ''}
                 onChange={(e) => setColumnas({ ...columnas, [CAMPO_DE_ETIQUETA[f]]: e.target.value })} />
        </label>
      ))}
      <button className="btn btn-sm" disabled={!completas} onClick={() => confirmar(huella, columnas)}>
        Confirmar formato
      </button>
    </div>
  );
}

interface Fondo { estado?: string; texto?: string | null; por_verificar?: number }
interface Dataset {
  estado?: string; libros_nuevos?: string[]; espera?: string; previsto?: number | null; reposo_min?: number;
}

/**
 * 104:RF-31: el indicador discreto del carril de fondo. Lo de fondo no es un trabajo de la cola: no sale en la barra de
 * trabajos ni desactiva ningún botón (el 2026-11-12, «Cargar / listar alimentadores» quedó desactivado y en cola).
 */
export function textoDelFondo(fondo: Fondo | null | undefined): string | null {
  if (!fondo || !fondo.estado || fondo.estado === 'libre') {
    return fondo?.por_verificar ? `${fondo.por_verificar} libro(s) por verificar en la próxima revisión.` : null;
  }
  return fondo.texto ?? null;
}

/** 104:RF-38: un dataset desactualizado dice cuándo se regenerará. */
export function textoDelDataset(dataset: Dataset | null | undefined, hora: (ts: number) => string): string | null {
  if (!dataset) return null;
  if (dataset.estado === 'regenerando') {
    return 'Regenerando el dataset del pronóstico en segundo plano, sin entrenar; se detiene si lanza un trabajo.';
  }
  if (dataset.estado !== 'desactualizado') return null;
  const n = dataset.libros_nuevos?.length ?? 0;
  const base = `El dataset del pronóstico está desactualizado por ${n} libro(s) nuevo(s)`;
  const reposo = dataset.reposo_min ?? 5;
  if (dataset.espera === 'faltan_fuentes') return `${base}; se regenerará cuando estén la cabecera y los medidores.`;
  if (dataset.espera === 'motor_ocupado') return `${base}; se regenerará cuando el motor lleve ${reposo} min libre.`;
  if (dataset.previsto) return `${base}; se regenerará hacia las ${hora(dataset.previsto)}, tras ${reposo} min sin trabajos.`;
  return `${base}.`;
}

/** Cuántos avisos se ven sin desplegar «ver más»: el resto queda a un clic, no tapa la sección. */
export const A_LA_VISTA = 3;

/** Lo que se ve de un aviso sin desplegarlo. */
export const LARGO_A_LA_VISTA = 200;

/**
 * 104:RF-20: un aviso en una línea y, si es largo, su detalle aparte. «0226clientesImportantes.xlsb: queda fuera del
 * dataset…: 181000485: 288 registro(s)…; 181000546: …» tenía 22 105 caracteres, una entrada por hoja: se ve la primera
 * y «y N más», y cada entrada en el detalle.
 */
export function resumirAviso(texto: string, max = LARGO_A_LA_VISTA): { corto: string; detalle: string[] } {
  if (texto.length <= max) return { corto: texto, detalle: [] };
  const partes = texto.split(/;\s+/).map((p) => p.trim()).filter(Boolean);
  const cortar = (t: string) => (t.length <= max ? t : `${t.slice(0, t.lastIndexOf(' ', max) > max / 2 ? t.lastIndexOf(' ', max) : max)}…`);
  if (partes.length > 1) {
    return { corto: `${cortar(partes[0])} · y ${partes.length - 1} más`, detalle: partes };
  }
  return { corto: cortar(texto), detalle: [texto] };
}

export interface GrupoDeAvisos<A> { tipo: string; titulo: string; alerta: boolean; avisos: A[] }

/** 104:RF-20: los avisos por tipo, primero los que piden atención y después los grupos más grandes. */
export function agruparAvisos<A extends { tipo: string; texto: string }>(avisos: A[]): GrupoDeAvisos<A>[] {
  const grupos = new Map<string, GrupoDeAvisos<A>>();
  for (const a of avisos) {
    const g = grupos.get(a.tipo) ?? { tipo: a.tipo, titulo: tituloDelAviso(a.tipo).replace(/\.$/, ''), alerta: false, avisos: [] };
    g.alerta ||= esAlerta(a.texto);
    g.avisos.push(a);
    grupos.set(a.tipo, g);
  }
  return [...grupos.values()].sort((x, y) => Number(y.alerta) - Number(x.alerta) || y.avisos.length - x.avisos.length);
}

/** 104:RF-20: los recuentos de la cabecera del panel; las alertas lo abren solas, lo informativo no. */
export function resumenDeAvisos(avisos: { texto: string }[]): { alertas: number; informativos: number } {
  const alertas = avisos.filter((a) => esAlerta(a.texto)).length;
  return { alertas, informativos: avisos.length - alertas };
}

/**
 * 104:RF-20, RF-21, RF-22: lo que la web reconoció sola en las carpetas de demanda. Antes había que pulsar
 * «Actualizar índice» y el libro de octubre de 2026 lo revisó una persona a mano.
 *
 * Va en 2.1, junto a los libros, como un panel plegable: en la cabecera de la página daba mala impresión al abrir la web
 * con tres avisos de fondo (usuario, 2026-11-13). Lo que pide atención lo abre; lo informativo queda en los recuentos.
 */
export function AvisosLibros() {
  const { ws, run, librosNuevosSeq } = useApp();
  const [estado, setEstado] = useState<LibrosNuevos | null>(null);
  const leer = useCallback(() => {
    // Sin libros de demanda no hay nada que reconocer; un fallo aquí no tapa la página (se ve en el Registro).
    if (!Object.keys(ws.demanda ?? {}).length) {
      setEstado(null);
      return;
    }
    api.librosNuevos(ws.id).then(setEstado).catch(() => setEstado(null));
  }, [ws.id, ws.demanda]);
  // RF-39: se relee del servidor con cada evento del carril de fondo, que llega por el WebSocket (y se repite al
  // reconectar): el aviso «Regenerando…» no se queda a la vista cuando ya terminó.
  useEffect(() => { leer(); }, [leer, librosNuevosSeq]);

  if (!estado) return null;
  const dataset = estado.dataset as Dataset | null;
  const visto = (id: string) => void run(() => api.librosNuevosVisto(ws.id, id)).then((r) => r && setEstado(r));
  const confirmar = (huella: string, columnas: Record<string, string>) =>
    void run(() => api.demandaConfirmarFormato(ws.id, huella, columnas)).then((r) => r && setEstado(r));
  // RF-1: la misma revisión que la periódica, sin esperar al intervalo; con el motor ocupado espera en el carril.
  const revisar = () => void run(() => api.librosNuevosRevisar(ws.id)).then((r) => r && setEstado(r.estado));
  // RF-35: la primera revisión de un espacio solo toma la foto; la verificación de todos se pide aquí.
  const verificarTodos = () => void run(() => api.librosNuevosVerificarTodos(ws.id)).then((r) => r && setEstado(r.estado));
  const hora = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const ultima = estado.ultima_revision ? hora(estado.ultima_revision) : null;
  const fondo = estado.fondo as Fondo;
  const textoFondo = textoDelFondo(fondo);
  const textoDataset = textoDelDataset(dataset, hora);
  const { alertas, informativos } = resumenDeAvisos(estado.avisos);
  // Lo que pide atención va primero; dentro de cada grupo, lo más reciente arriba.
  const ordenados = [...estado.avisos].sort((a, b) =>
    Number(esAlerta(b.texto)) - Number(esAlerta(a.texto)) || b.cuando - a.cuando);
  const visibles = ordenados;
  const activo = Boolean(fondo?.estado && fondo.estado !== 'libre') || dataset?.estado === 'regenerando';
  return (
    <details className="novedades" open={alertas > 0}>
      <summary className="novedades-cabecera">
        <span className="novedades-titulo">Novedades de los libros</span>
        {alertas > 0 && <span className="badge warn">{alertas} por atender</span>}
        {informativos > 0 && <span className="badge info">{informativos} informativo{informativos > 1 ? 's' : ''}</span>}
        {!estado.avisos.length && <span className="badge ok">al día</span>}
        <span className="muted small novedades-revision">
          {activo && <span className="pulso" aria-hidden="true" />}
          Revisión automática{estado.intervalo_min ? ` cada ${estado.intervalo_min} min` : ' al abrir el espacio'}
          {ultima && ` · última a las ${ultima}`}
        </span>
      </summary>
      <div className="novedades-cuerpo">
        <div className="row">
          <button className="btn btn-sm btn-ghost" onClick={revisar}>Revisar ahora</button>
          <button className="btn btn-sm btn-ghost" onClick={verificarTodos}>Verificar todos ahora</button>
        </div>
        {/* Por tipo y en una línea cada uno: 13 avisos de formato y uno de 22 105 caracteres llenaban la página
            (usuario, 2026-11-14: «no debería estar así, con tanto texto»). El detalle queda a un clic. */}
        {agruparAvisos(visibles).map((g) => (
          <details key={g.tipo} className={`novedad-grupo ${g.alerta ? 'novedad-alerta' : 'novedad-info'}`}
            open={g.alerta && g.avisos.length <= A_LA_VISTA}>
            <summary>
              <strong>{g.titulo}</strong> <span className={`badge ${g.alerta ? 'warn' : 'info'}`}>{g.avisos.length}</span>
              <button className="btn btn-sm btn-ghost novedad-vistos" onClick={(e) => {
                e.preventDefault();
                g.avisos.forEach((a) => visto(a.id));
              }}>Dar por vistos</button>
            </summary>
            <ul className="novedades-lista">
              {g.avisos.map((a) => {
                const pendiente = a.tipo === 'formato' ? porConfirmar(a.ficha) : null;
                const { corto, detalle } = resumirAviso(a.texto);
                return (
                  <li key={a.id} className="novedad" role="status">
                    <div className="novedad-texto">
                      {corto}
                      {detalle.length > 0 && (
                        <details className="novedad-detalle"><summary className="small">ver el detalle ({detalle.length})</summary>
                          <ul className="small">{detalle.map((d, i) => <li key={i}>{d}</li>)}</ul></details>)}
                      {pendiente && <ConfirmarFormato huella={pendiente.huella} falta={pendiente.falta} confirmar={confirmar} />}
                    </div>
                    <div className="novedad-pie">
                      <span className="muted small">{new Date(a.cuando * 1000).toLocaleString([], {
                        day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
                      <button className="btn btn-sm btn-ghost" onClick={() => visto(a.id)}>Visto</button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </details>
        ))}
        {textoFondo && <p className="muted small" role="status" data-fondo={fondo.estado}>{textoFondo}</p>}
        {textoDataset && <p className="muted small" role="status">{textoDataset} No se entrena ningún modelo sin su orden.</p>}
      </div>
    </details>
  );
}
