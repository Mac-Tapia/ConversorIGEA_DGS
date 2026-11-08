import {
  createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode,
} from 'react';

// ---------------------------------------------------------------- avisos (toasts)

type Tone = 'info' | 'ok' | 'warn' | 'error';
interface Toast { id: number; tone: Tone; title: string; body?: string }

const ToastCtx = createContext<(tone: Tone, title: string, body?: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((tone: Tone, title: string, body?: string) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, tone, title, body }]);
    window.setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), tone === 'error' ? 12000 : 6000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            <strong>{t.title}</strong>
            {t.body && <p>{t.body}</p>}
            <button className="toast-close" aria-label="Cerrar"
              onClick={() => setItems((prev) => prev.filter((x) => x.id !== t.id))}>×</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

// ---------------------------------------------------------------- diálogo modal

export function Modal({
  title, children, onClose, actions, wide,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  actions?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  return (
    <dialog ref={ref} className={`modal ${wide ? 'modal-wide' : ''}`} onClose={onClose}
      onCancel={(e) => { e.preventDefault(); onClose(); }}>
      <header className="modal-head">
        <h2>{title}</h2>
        <button className="icon-btn" aria-label="Cerrar" onClick={onClose}>×</button>
      </header>
      <div className="modal-body">{children}</div>
      {actions && <footer className="modal-actions">{actions}</footer>}
    </dialog>
  );
}

/** Confirmación con promesa: `if (await confirm(...))`. */
interface ConfirmReq { title: string; body: ReactNode; ok: string; danger?: boolean; resolve: (v: boolean) => void }
const ConfirmCtx = createContext<(title: string, body: ReactNode, ok?: string, danger?: boolean) => Promise<boolean>>(
  async () => false,
);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [req, setReq] = useState<ConfirmReq | null>(null);
  const ask = useCallback((title: string, body: ReactNode, ok = 'Continuar', danger = false) =>
    new Promise<boolean>((resolve) => setReq({ title, body, ok, danger, resolve })), []);
  const close = (v: boolean) => {
    req?.resolve(v);
    setReq(null);
  };
  return (
    <ConfirmCtx.Provider value={ask}>
      {children}
      {req && (
        <Modal title={req.title} onClose={() => close(false)} actions={<>
          <button className="btn" onClick={() => close(false)}>Cancelar</button>
          <button className={`btn ${req.danger ? 'btn-danger' : 'btn-primary'}`} autoFocus
            onClick={() => close(true)}>{req.ok}</button>
        </>}>
          {req.body}
        </Modal>
      )}
    </ConfirmCtx.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmCtx);

// ---------------------------------------------------------------- ficheros

export function FileDrop({
  onFiles, accept, multiple, children, disabled, compact,
}: {
  onFiles: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  children: ReactNode;
  disabled?: boolean;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      className={`drop ${over ? 'drop-over' : ''} ${disabled ? 'drop-disabled' : ''} ${compact ? 'drop-compact' : ''}`}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onClick={() => !disabled && input.current?.click()}
      onKeyDown={(e) => { if (!disabled && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); input.current?.click(); } }}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (disabled) return;
        const files = Array.from(e.dataTransfer.files);
        if (files.length) onFiles(multiple ? files : files.slice(0, 1));
      }}
    >
      {children}
      <input ref={input} type="file" hidden accept={accept} multiple={multiple}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = '';
          if (files.length) onFiles(files);
        }} />
    </div>
  );
}

export function Pill({ tone, children, title }: { tone: 'ok' | 'warn' | 'error' | 'muted' | 'info'; children: ReactNode; title?: string }) {
  return <span className={`pill pill-${tone}`} title={title}>{children}</span>;
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: 'warn' | 'error' | 'ok' }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ''}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

export function Toggle({ label, checked, onChange, disabled, hint }: {
  label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; hint?: string;
}) {
  return (
    <label className={`toggle ${disabled ? 'toggle-disabled' : ''}`} title={hint}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track" aria-hidden><span className="toggle-thumb" /></span>
      <span>{label}</span>
    </label>
  );
}
