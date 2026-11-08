import { useApp } from './context';

export function PfWarning() {
  const { pf } = useApp();
  if (!pf || pf.available) return null;
  return (
    <p className="alert alert-warn">
      PowerFactory no está disponible en el servidor ({pf.interpreter_reason}
      {pf.api_version ? `; la API pide Python ${pf.api_version}` : ''}). Puede preparar el plan, pero no aplicarlo.
    </p>
  );
}
