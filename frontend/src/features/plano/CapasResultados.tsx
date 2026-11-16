import type { CapasPlano, ComparacionPlano } from '../../api/plano';
import { textoValor } from './logicaPlano';
import { TEXTOS } from './textosPlano';

const MAGNITUD: Record<string, string> = { tension: 'Tensión', corriente: 'Corriente', cargabilidad: 'Cargabilidad', estado: 'Estado' };

/** 111:RF-10, RF-13, RF-18: cada capa con su unidad, su umbral, el caso y el motor; un incumplimiento lleva icono y
 * texto, no solo color. Los umbrales y las bandas los da el servidor. */
export function CapasResultados({ capas, onElegir }: { capas: CapasPlano; onElegir: (codigo: string) => void }) {
  if (!capas.pintable) {
    return <div className="alert alert-warn" role="status"><p>{capas.motivo}</p>
      {capas.mensajes.length > 0 && <ul className="lista-compacta">{capas.mensajes.slice(0, 5).map((m) => <li key={m}>{m}</li>)}</ul>}</div>;
  }
  return (
    <div>
      <p><b>{TEXTOS.caso}</b> {capas.caso} · {capas.motor_texto} · umbral {capas.origen_umbral}</p>
      {Object.entries(capas.capas).map(([clave, capa]) => {
        const l = capa.leyenda;
        const umbral = l.umbral ? Object.entries(l.umbral).map(([k, v]) => `${k} ${textoValor(v)}`).join(' · ') : '';
        const malos = capa.elementos.filter((e) => e.incumple);
        return (
          <section key={clave} aria-label={l.magnitud}>
            <h4>{l.magnitud}{l.unidad ? ` (${l.unidad})` : ''}</h4>
            <p className="muted">{umbral ? `Umbral: ${umbral} · ` : ''}{l.motor_texto}</p>
            {malos.length > 0 && (
              <ul className="lista-compacta">
                {malos.slice(0, 50).map((e) => (
                  <li key={e.codigo}>
                    <span className="icono-alerta" role="img" aria-label={TEXTOS.incumple}>!</span>{' '}
                    <button type="button" className="link" onClick={() => onElegir(e.codigo)}>{e.codigo}</button>: {e.incumple?.texto}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

/** 111:RF-12, RF-19: dos casos por elemento; si los motores son distintos, se dice junto a la diferencia. */
export function Comparacion({ comparacion, onElegir }: { comparacion: ComparacionPlano; onElegir: (codigo: string) => void }) {
  const c = comparacion;
  if (!c.comparable) return <p className="alert alert-warn" role="status">{c.motivo}</p>;
  const distintos = c.elementos.filter((e) => e.diferencia !== 0 || e.solo_en !== null);
  return (
    <div>
      {c.aviso_motores && <p className="alert alert-warn" role="status">{c.aviso_motores}</p>}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>{TEXTOS.codigo}</th><th>Magnitud</th><th className="num">{c.casos[0]?.caso ?? TEXTOS.casoA}</th>
            <th className="num">{c.casos[1]?.caso ?? TEXTOS.casoB}</th><th className="num">Diferencia</th></tr></thead>
          <tbody>
            {distintos.slice(0, 200).map((e) => (
              <tr key={`${e.magnitud}|${e.codigo}`}>
                <td><button type="button" className="link" onClick={() => onElegir(e.codigo)}>{e.codigo}</button></td>
                <td>{MAGNITUD[e.magnitud] ?? e.magnitud}</td>
                <td className="num">{textoValor(e.a)}</td><td className="num">{textoValor(e.b)}</td>
                <td className="num">{textoValor(e.diferencia)}{c.aviso_motores ? ' *' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
