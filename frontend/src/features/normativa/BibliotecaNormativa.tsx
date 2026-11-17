import { useCallback, useEffect, useState } from 'react';
import { filtrarNormas, normativa, type Biblioteca, type Reglas } from '../../api/normativa';
import { useApp } from '../../shared/context';
import { FileDrop, Pill, useToast } from '../../shared/ui';

const hoy = () => new Date().toISOString().slice(0, 10);

/**
 * Pestaña «Biblioteca normativa» (107:RF-21): una sola biblioteca para toda empresa, estudio y módulo. Lista cada
 * norma con lo que obliga en la fecha, muestra sus reglas con la cita y admite añadir o actualizar una norma.
 */
export function BibliotecaNormativa() {
  const { run } = useApp();
  const toast = useToast();
  const [fecha, setFecha] = useState(hoy);
  const [texto, setTexto] = useState('');
  const [bib, setBib] = useState<Biblioteca | null>(null);
  const [reglas, setReglas] = useState<Reglas | null>(null);

  const cargar = useCallback(() => {
    void run(() => normativa.listar(fecha)).then((r) => { if (r) setBib(r); });
  }, [run, fecha]);
  useEffect(cargar, [cargar]);

  const subir = (fs: File[]) => {
    const f = fs[0];
    if (!f) return;
    void run(() => normativa.agregar(f)).then((r) => {
      if (!r) return;
      toast('ok', 'Norma añadida', r.actos.join(', '));
      cargar();
    });
  };
  const ver = (acto: string) => { void run(() => normativa.reglas(acto)).then((r) => { if (r) setReglas(r); }); };

  const lista = bib ? filtrarNormas(bib.normas ?? [], texto) : [];
  return (
    <div className="biblioteca-normativa">
      <div className="form-grid">
        <label className="field">
          <span>Fecha</span>
          <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value || hoy())} />
        </label>
        <label className="field">
          <span>Buscar</span>
          <input type="search" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Acto o título" />
        </label>
        <FileDrop entrada="norma" compact accept=".json" onFiles={subir}>Añadir o actualizar una norma (.json)</FileDrop>
      </div>
      {bib && (
        <table className="small" aria-label="Normas de la biblioteca">
          <thead><tr><th>Acto</th><th>Título</th><th>Estado</th><th>Reglas</th><th /></tr></thead>
          <tbody>
            {lista.map((n) => (
              <tr key={n.acto}>
                <td>{n.acto}</td>
                <td>{n.titulo}</td>
                <td>
                  <Pill tone={n.obliga ? 'ok' : 'muted'}>{n.obliga ? 'Obliga' : 'No obliga'}</Pill>
                  {n.sustituida_por_el_usuario && <Pill tone="info">Actualizada</Pill>}
                </td>
                <td>{n.reglas}</td>
                <td>{n.reglas > 0 && <button className="btn btn-sm" onClick={() => ver(n.acto)}>Ver</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {reglas && (
        <section aria-label={`Reglas de ${reglas.acto}`}>
          <h3>{reglas.acto}</h3>
          <ul className="small">
            {(reglas.reglas ?? []).map((r) => (
              <li key={r.clave}>
                <strong>{r.clave}</strong> = {r.valor}{r.unidad && r.unidad !== '-' ? ` ${r.unidad}` : ''}
                {' · '}{r.articulo_o_anexo}{r.pagina ? `, pág. ${r.pagina}` : ''}
                <blockquote>{r.cita_literal}</blockquote>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
