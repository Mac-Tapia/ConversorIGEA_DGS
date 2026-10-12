import { useState, type FormEvent } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import type {
  AlimentadorLeido, ClaseObra, ClaseTipo, Obra, ObraFila, ObrasBibliotecas, ObrasResultado, TipoFicha, TipoRef,
} from '../types';

/** Los casos donde se puede activar una obra; el «Caso base» nunca (spec 011, RF-58). */
export const CASOS_OBRA = ['Sin proyecto', 'Con proyecto'] as const;

const CLASES: { clase: ClaseObra; label: string; tipo?: ClaseTipo }[] = [
  { clase: 'condensador', label: 'Banco de condensadores' },
  { clase: 'reconectador', label: 'Reconectador', tipo: 'TypRecl' },
  { clase: 'regulador', label: 'Regulador de tensión', tipo: 'TypVoltreg' },
  { clase: 'seccion', label: 'Cambio de sección (troncal)', tipo: 'TypLne' },
  { clase: 'terna', label: 'Una terna más (troncal)' },
  { clase: 'tension', label: 'Cambio de nivel de tensión del alimentador' },
];
const ETIQUETA = Object.fromEntries(CLASES.map((c) => [c.clase, c.label])) as Record<ClaseObra, string>;
const ORIGEN: Record<string, string> = { proyecto: 'proyecto', global: 'biblioteca global', otro: 'otro proyecto' };

/** Número del formulario, o nada; las reglas las aplica el servidor (obras_pf.validar_obra). */
const num = (v: string): number | undefined => {
  const t = v.trim().replace(',', '.');
  return t === '' ? undefined : Number(t);
};

const claveTipo = (t: TipoFicha) => `${t.origen}|${t.proyecto}|${t.nombre}`;

/**
 * 4.1 · Obras de mejora (spec 011, RF-56 a RF-95).
 *
 * El operador define cada obra en un formulario (RF-70), eligiendo barras, tramos y tipos
 * que lee DIgSILENT (RF-88 a RF-94); las obras quedan en el espacio hasta aplicarlas
 * (RF-95), y se simulan antes sin escribir en el proyecto (RF-69).
 */
export function ObrasPF({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, run, startJob, active, jobs, refresh } = useApp();
  const [otro, setOtro] = useState('');
  const [clase, setClase] = useState<ClaseObra>('condensador');
  const [alim, setAlim] = useState('');
  const [casos, setCasos] = useState<string[]>(['Con proyecto']);
  const [v, setV] = useState<Record<string, string>>({});
  const [tramos, setTramos] = useState<string[]>([]);
  const [tipo, setTipo] = useState('');
  const pfBusy = Boolean(active.powerfactory);
  const todos = Object.values(jobs);

  const lectura = todos.filter((j) => j.kind === 'obras_bibliotecas' && j.status === 'done'
    && j.result?.informe).pop();
  const leido = (lectura?.result?.informe ?? null) as ObrasBibliotecas | null;
  const ultima = todos.filter((j) => (j.kind === 'obras_simular' || j.kind === 'obras_aplicar') && j.result).pop();
  const resultado = (ultima?.result ?? null) as ObrasResultado | null;

  const alimentador = alim || feeders[0] || '';
  const red: AlimentadorLeido | undefined = leido?.alimentadores?.[alimentador];
  const claseTipo = CLASES.find((c) => c.clase === clase)?.tipo;
  // RF-89 a RF-91: los tipos de la clase que pide la obra, de las tres bibliotecas.
  const tipos = (leido?.tipos ?? []).filter((t) => t.clase === claseTipo);
  const guardadas = ws.obras ?? [];
  const cuerpo = { project, feeders, otro_proyecto: otro.trim() };

  const set = (k: string) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  const alternar = (xs: string[], x: string) => (xs.includes(x) ? xs.filter((y) => y !== x) : [...xs, x]);

  const anadir = async (e: FormEvent) => {
    e.preventDefault();
    const elegido = tipos.find((t) => claveTipo(t) === tipo);
    const ref: TipoRef | undefined = elegido
      ? { nombre: elegido.nombre, clase: elegido.clase, origen: elegido.origen, proyecto: elegido.proyecto }
      : undefined;
    const obra: Obra = {
      clase, alimentador, casos,
      barra: v.barra, tramo: v.tramo, tramos: tramos.length ? tramos : undefined,
      q_kvar: num(v.q_kvar ?? ''), escalones: num(v.escalones ?? ''), consigna_pu: num(v.consigna_pu ?? ''),
      rango_pct: num(v.rango_pct ?? ''), pasos: num(v.pasos ?? ''), kv_destino: num(v.kv_destino ?? ''), tipo: ref,
    };
    const r = await run(() => api.obraAnadir(ws.id, obra));
    if (r) {
      setV({});
      setTramos([]);
      setTipo('');
      await refresh();
    }
  };
  const quitar = async (id: string) => {
    await run(() => api.obraQuitar(ws.id, id));
    await refresh();
  };

  const campo = (k: string, label: string, ayuda?: string) => (
    <label className="field">
      <span>{label}</span>
      <input value={v[k] ?? ''} inputMode="decimal" onChange={set(k)} />
      {ayuda && <small className="muted">{ayuda}</small>}
    </label>
  );
  const lista = (k: 'barra' | 'tramo', label: string, opciones: string[]) => (
    <label className="field">
      <span>{label}</span>
      {opciones.length ? (
        <select value={v[k] ?? ''} onChange={set(k)}>
          <option value="">— elija —</option>
          {opciones.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : <input value={v[k] ?? ''} onChange={set(k)} placeholder="lea antes el proyecto" />}
    </label>
  );

  return (
    <div>
      <p className="muted">Cada obra va en su <strong>propia variación</strong>, activa solo en los casos que elija; nunca en
        el «Caso base». Ninguna obra cambia un tipo del proyecto: si necesita otros datos, usa una copia.</p>
      <div className="row">
        <label className="field">
          <span>Otro proyecto como origen de tipos (opcional)</span>
          <input value={otro} placeholder="carpeta/proyecto" onChange={(e) => setOtro(e.target.value)} />
        </label>
        <button className="btn" disabled={pfBusy || !project || !feeders.length}
          onClick={() => startJob(() => api.obrasBibliotecas(ws.id, cuerpo))}
          title="Barras, tramos y tipos de línea, transformador, regulador y reconectador; no escribe nada">
          {leido ? 'Volver a leer barras, tramos y tipos' : 'Leer barras, tramos y tipos de DIgSILENT'}
        </button>
      </div>
      {(leido?.avisos ?? []).map((a) => <p key={a} className="alert alert-warn">{a}</p>)}

      <form className="form-grid" onSubmit={anadir}>
        <label className="field">
          <span>Obra</span>
          <select value={clase} onChange={(e) => { setClase(e.target.value as ClaseObra); setTipo(''); }}>
            {CLASES.map((c) => <option key={c.clase} value={c.clase}>{c.label}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Alimentador</span>
          <select value={alimentador} onChange={(e) => { setAlim(e.target.value); setTramos([]); }}>
            {feeders.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <div className="field span-2">
          <span>Activa en</span>
          <div className="chips">
            {CASOS_OBRA.map((c) => (
              <button key={c} type="button" className={`chip ${casos.includes(c) ? 'on' : ''}`}
                onClick={() => setCasos((xs) => alternar(xs, c))}>{c}</button>
            ))}
          </div>
        </div>

        {clase === 'condensador' && <>
          {lista('barra', 'Barra', (red?.barras ?? []).map((b) => b.nombre))}
          {campo('q_kvar', 'Potencia reactiva total (kvar)')}
          {campo('escalones', 'Número de escalones')}
          {campo('consigna_pu', 'Consigna de tensión (p.u.)', 'En blanco: fijo, con todos los escalones.')}
        </>}
        {(clase === 'reconectador' || clase === 'regulador') &&
          lista('tramo', 'Tramo (se pone al principio, del lado de la cabecera)', (red?.tramos ?? []).map((t) => t.nombre))}
        {clase === 'regulador' && <>
          {campo('consigna_pu', 'Consigna de tensión (p.u.)')}
          {campo('rango_pct', 'Rango de regulación (± %)')}
          {campo('pasos', 'Pasos a cada lado de la toma central', 'Por ejemplo 16 para ±16 pasos.')}
        </>}
        {(clase === 'seccion' || clase === 'terna') && (
          <div className="field span-2">
            <span>Tramos ({tramos.length ? `${tramos.length} elegidos` : 'ninguno: toda la troncal'})</span>
            <div className="chips">
              {(red?.tramos ?? []).map((t) => (
                <button key={t.nombre} type="button" className={`chip ${tramos.includes(t.nombre) ? 'on' : ''}`}
                  title={`${t.tipo ?? 'sin tipo'} · ${t.nlnum} terna(s)`} onClick={() => setTramos((xs) => alternar(xs, t.nombre))}>
                  {t.nombre}
                </button>
              ))}
            </div>
          </div>
        )}
        {clase === 'tension' &&
          campo('kv_destino', `Tensión nueva (kV)${red?.kv ? `; hoy ${red.kv} kV` : ''}`,
            'Se migra el alimentador entero desde su cabecera, sin subestación nueva.')}
        {claseTipo && (
          <label className="field span-2">
            <span>Tipo{clase === 'reconectador' ? ' de reenganche (opcional)' : ''}</span>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">— elija —</option>
              {tipos.map((t) => (
                <option key={claveTipo(t)} value={claveTipo(t)}>
                  {t.nombre} · {t.resumen || 'sin datos'} · {ORIGEN[t.origen]}{t.proyecto ? ` ${t.proyecto}` : ''}
                </option>
              ))}
            </select>
            <small className="muted">Un tipo de la biblioteca global o de otro proyecto se copia al proyecto.</small>
          </label>
        )}
        <div className="row span-2">
          <button className="btn btn-primary" type="submit" disabled={!alimentador || !casos.length}>Añadir obra</button>
          {!casos.length && <small className="muted">Elija al menos un caso.</small>}
        </div>
      </form>

      <h5>Obras definidas ({guardadas.length})</h5>
      {guardadas.length === 0 ? <p className="muted">Todavía ninguna.</p> : (
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>Obra</th><th>Alimentador</th><th>Casos</th><th>Detalle</th><th /></tr></thead>
            <tbody>{guardadas.map((o) => (
              <tr key={o.id}>
                <td className="strong">{ETIQUETA[o.clase]}</td><td>{o.alimentador}</td>
                <td className="small">{o.casos.join(', ')}</td>
                <td className="small">{[o.barra, o.tramo, o.tramos?.join(', '), o.tipo?.nombre,
                  o.kv_destino != null ? `${o.kv_destino} kV` : ''].filter(Boolean).join(' · ')}</td>
                <td><button className="btn btn-sm btn-ghost" onClick={() => quitar(o.id)}>Quitar</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <div className="row">
        <button className="btn" disabled={pfBusy || !guardadas.length}
          onClick={() => startJob(() => api.obrasSimular(ws.id, cuerpo))}
          title="Dice por obra su variación, lo que cambiaría y los tipos que copiaría; no escribe nada">
          Simular las obras
        </button>
        <button className="btn btn-pf" disabled={pfBusy || !guardadas.length}
          onClick={() => startJob(() => api.obrasAplicar(ws.id, cuerpo))}>
          Aplicar las obras
        </button>
      </div>
      {resultado && <ResultadoObras r={resultado} />}
    </div>
  );
}

function ResultadoObras({ r }: { r: ObrasResultado }) {
  const inf = r.informe;
  const simular = inf.modo === 'simular';
  const difs = inf.comprobacion?.diferencias ?? [];
  return (
    <div className="alert">
      <p><strong>{simular ? 'Simulación' : 'Aplicación'} de las obras</strong>
        {simular ? ': nada se ha escrito en el proyecto.' : ''}</p>
      {inf.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {!simular && inf.comprobacion && (difs.length
        ? <p className="alert alert-error">«Sin proyecto» cambió en alimentadores sin obras: vea los avisos.</p>
        : <p className="muted">«Sin proyecto» sigue igual en los alimentadores sin obras.</p>)}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Obra</th><th>Variación</th><th>Activa en</th><th>Cambios</th><th>Tipos copiados</th></tr></thead>
          <tbody>{inf.obras.map((o) => <FilaObra key={o.obra} o={o} simular={simular} />)}</tbody>
        </table>
      </div>
    </div>
  );
}

function FilaObra({ o, simular }: { o: ObraFila; simular: boolean }) {
  const flujo = Object.entries(o.flujo ?? {});
  return (
    <tr>
      <td className="strong">{ETIQUETA[o.clase]} · {o.alimentador}
        {o.error && <div className="badge err">{o.error}</div>}
        {o.avisos.map((a) => <div key={a} className="muted small">{a}</div>)}</td>
      <td className="mono small">{o.variacion || '—'}</td>
      <td className="small">{simular ? o.casos.join(', ') : flujo.length ? flujo.map(([c, f]) => (
        <div key={c}>{c}: {f.converge ? 'converge' : <span className="badge err">no converge, inactiva</span>}</div>
      )) : '—'}</td>
      <td className="small">{o.elementos.length}{o.elementos.length > 0 && (
        <details><summary>ver</summary><ul>{o.elementos.slice(0, 200).map((e) => (
          <li key={`${e.clase}-${e.elemento}`}>{e.elemento} ({e.clase}): {e.cambio}</li>))}</ul></details>)}</td>
      <td className="small">{o.tipos.map((t) => `${t.nombre}${t.reutiliza ? ' (ya estaba)' : ''}`).join(', ') || '—'}</td>
    </tr>
  );
}
