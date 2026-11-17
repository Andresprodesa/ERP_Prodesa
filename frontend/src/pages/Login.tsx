import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Header } from "../components/Layout";
import { mensajeError } from "../components/ui";

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const destino = (loc.state as { from?: string } | null)?.from ?? "/presupuestos";

  if (user) return <Navigate to={destino} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await login(username.trim(), password);
      nav(destino, { replace: true });
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <Header titulo="ADPRO · Ingreso" />
      <div className="wrap">
        <aside className="side">
          <form onSubmit={onSubmit}>
            <h2><span className="chev">&gt;</span>Iniciar sesión</h2>
            <p className="sub">Usuarios locales del prototipo (en producción: Microsoft Entra ID).</p>
            <label className="lbl" htmlFor="u">Usuario</label>
            <input id="u" type="text" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
            <label className="lbl" htmlFor="p">Contraseña</label>
            <input id="p" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <button className="btn" type="submit" disabled={enviando || !username || !password}>
              {enviando && <span className="spin" />}Ingresar
            </button>
            <p className="hint">Las credenciales de prueba se definen en el .env del backend (ver README).</p>
          </form>
        </aside>
        <main className="main login-main">
          {error && <div className="err">{error}</div>}
          <div className="card intro">
            <p><span className="badge">ADPRO</span>Presupuesto y control de obra de Prodesa.</p>
            <p>
              <b>Maestros</b> (insumos, listas de precios, proyectos, EDT) · <b>APU</b> por ítem ·{" "}
              <b>Presupuestos</b> con versiones BASE / FIC / FIV / CONTROL, AIU y explosión de insumos ·{" "}
              <b>Control</b>: comparativo entre versiones, compromisos, avance mensual y tablero.
            </p>
            <p className="note">Prototipo local con datos sintéticos.</p>
          </div>
        </main>
      </div>
    </>
  );
}
