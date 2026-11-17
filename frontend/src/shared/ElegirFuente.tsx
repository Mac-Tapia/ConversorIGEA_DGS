import { useEffect, useState } from 'react';
import { fuentes, type Fuente } from '../api/fuentes';
import { useApp } from './context';
import { FileDrop } from './ui';

/**
 * 109:RF-25: el libro de una clase (SICODI, PIT, VAD…) que ya cargó la empresa del espacio, o subir otro. La vigente
 * va elegida de entrada; una subida queda para todos los módulos. `onElegir` recibe la fuente elegida o el fichero.
 */
export function ElegirFuente({ clase, etiqueta, accept, disabled, onElegir }: {
  clase: string;
  etiqueta: string;
  accept: string;
  disabled?: boolean;
  onElegir: (f: Fuente | File | null) => void;
}) {
  const { ws, run } = useApp();
  const [lista, setLista] = useState<Fuente[]>([]);
  const [elegida, setElegida] = useState<string>('');
  const [subida, setSubida] = useState<File | null>(null);

  useEffect(() => {
    let vivo = true;
    void run(() => fuentes.listar(ws.id, clase)).then((r) => {
      if (!vivo || !r) return;
      setLista(r.fuentes);
      const vigente = r.fuentes.filter((f) => f.vigente).sort((a, b) => b.registrada.localeCompare(a.registrada))[0];
      if (vigente) { setElegida(vigente.id); onElegir(vigente); }
    });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.id, clase]);

  return (
    <div className="field">
      <span>{etiqueta}</span>
      {lista.length > 0 && (
        <select aria-label={`${etiqueta}: de la empresa`} value={subida ? '' : elegida} disabled={disabled}
          onChange={(e) => {
            const f = lista.find((x) => x.id === e.target.value) ?? null;
            setElegida(e.target.value); setSubida(null); onElegir(f);
          }}>
          {subida && <option value="">{subida.name} (nuevo)</option>}
          {lista.map((f) => (
            <option key={f.id} value={f.id}>{f.nombre}{f.periodo ? ` · ${f.periodo}` : ''}{f.vigente ? ' · vigente' : ''}</option>
          ))}
        </select>
      )}
      <FileDrop entrada={`fuente-${clase}`} compact accept={accept} disabled={disabled}
        onFiles={(fs) => { const f = fs[0] ?? null; setSubida(f); onElegir(f); }}>
        {subida ? subida.name : lista.length ? 'O suba otro libro' : 'Suelte o elija el libro'}
      </FileDrop>
    </div>
  );
}
