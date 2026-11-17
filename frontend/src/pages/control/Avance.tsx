import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type EjecucionRegistro } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { SidePanel } from "../../components/Layout";
import { SelectorPresupuesto } from "../../components/Selectores";
import { Cargando, ErrorBox, Kpi, mensajeError, Vacio } from "../../components/ui";
import { cop, copCompacto, decIn, fraccionAPct, pct, pctAFraccion, periodoActual, toNum } from "../../lib/format";

interface Captura {
  valor: string; // valor ejecutado del periodo
  avance: string; // % físico acumulado (humano)
  obs: string;
}

/**
 * Registro mensual de ejecución por ítem.
 * Semántica del contrato: valor ejecutado = lo del periodo; avance físico = ACUMULADO al cierre (0..100 %).
 */
export default function AvancePage() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [pid, setPid] = useState<number | null>(null);
  const [periodo, setPeriodo] = useState(periodoActual());
  const [q, setQ] = useState("");
  const [captura, setCaptura] = useState<Record<number, Captura>>({});
  const [resultado, setResultado] = useState<{ creados: number; actualizados: number; advertencias: string[] } | null>(null);

  const items = useQuery({
    queryKey: ["tablero-items", pid, null, null, "todos"],
    queryFn: () => api.control.tableroItems({ presupuesto_id: pid as number }),
    enabled: pid !== null,
  });
  const ejec = useQuery({
    queryKey: ["ejecucion", pid, periodo],
    queryFn: () => api.control.ejecucion({ presupuesto_id: pid as number, periodo }),
    enabled: pid !== null && /^\d{4}-\d{2}$/.test(periodo),
  });
  const periodos = useQuery({
    queryKey: ["periodos", pid],
    queryFn: () => api.control.periodos(pid as number),
    enabled: pid !== null,
  });

  // Precarga lo ya registrado en el periodo.
  useEffect(() => {
    const m: Record<number, Captura> = {};
    for (const e of ejec.data ?? []) {
      m[e.item_id] = { valor: e.valor_ejecutado, avance: fraccionAPct(e.avance_fisico_pct), obs: e.observacion ?? "" };
    }
    setCaptura(m);
    setResultado(null);
  }, [ejec.data]);

  const filas = useMemo(
    () =>
      (items.data ?? []).filter(
        (f) => f.id !== null && (!q || f.codigo.toLowerCase().includes(q.toLowerCase()) || f.descripcion.toLowerCase().includes(q.toLowerCase())),
      ),
    [items.data, q],
  );

  const registros: EjecucionRegistro[] = Object.entries(captura)
    .filter(([, c]) => c.valor.trim() !== "" || c.avance.trim() !== "")
    .map(([id, c]) => ({
      item_id: Number(id),
      valor_ejecutado: decIn(c.valor) || "0",
      avance_fisico_pct: pctAFraccion(c.avance),
      observacion: c.obs || null,
    }));
  const totalPeriodo = registros.reduce((s, r) => s + toNum(r.valor_ejecutado), 0);

  const guardar = useMutation({
    mutationFn: () => api.control.guardarEjecucion({ presupuesto_id: pid as number, periodo, registros }),
    onSuccess: (r) => {
      setResultado(r);
      qc.invalidateQueries({ queryKey: ["ejecucion", pid] });
      qc.invalidateQueries({ queryKey: ["periodos", pid] });
      qc.invalidateQueries({ queryKey: ["tablero"] });
      qc.invalidateQueries({ queryKey: ["tablero-items"] });
    },
  });

  const set = (id: number, campo: keyof Captura, v: string) =>
    setCaptura((c) => ({ ...c, [id]: { ...(c[id] ?? { valor: "", avance: "", obs: "" }), [campo]: v } }));

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Registro de avance</h2>
        <p className="sub">Valor ejecutado del mes y % de avance físico acumulado por ítem.</p>
        <SelectorPresupuesto label="Presupuesto" value={pid} onChange={setPid} />
        <label className="lbl">Periodo</label>
        <input type="month" value={periodo} onChange={(e) => setPeriodo(e.target.value)} />
        {!!periodos.data?.length && (
          <>
            <label className="lbl">Periodos con registro</label>
            <div className="prs">
              {periodos.data.map((p) => (
                <span key={p} className={p === periodo ? "w" : ""} onClick={() => setPeriodo(p)} role="button">
                  {p}
                </span>
              ))}
            </div>
            <hr className="sep" />
          </>
        )}
        {puede.control ? (
          <>
            <button className="btn" type="button" disabled={!pid || registros.length === 0 || guardar.isPending} onClick={() => guardar.mutate()}>
              {guardar.isPending && <span className="spin" />}💾 Guardar avance ({registros.length})
            </button>
            <p className="hint">Se guarda por ítem y periodo (si ya existe, se actualiza).</p>
          </>
        ) : (
          <p className="sub">Tu rol solo permite consultar.</p>
        )}
      </SidePanel>

      {pid === null ? (
        <div className="card intro"><p><span className="badge">CONTROL</span>Selecciona un presupuesto.</p></div>
      ) : (
        <>
          <div className="kpis">
            <Kpi k={`Ejecutado ${periodo}`} v={copCompacto(totalPeriodo)} s={cop(totalPeriodo)} />
            <Kpi k="Ítems con registro" v={registros.length} s={`de ${filas.length} ítems`} tono="b" />
          </div>
          <ErrorBox error={items.error ?? ejec.error ?? guardar.error} />
          {resultado && (
            <div className="tdesc">
              Guardado: <b>{resultado.creados}</b> nuevos, <b>{resultado.actualizados}</b> actualizados.
              {resultado.advertencias.length > 0 && <> ⚠ {resultado.advertencias.join(" · ")}</>}
            </div>
          )}
          {guardar.isError && <p className="note">{mensajeError(guardar.error)}</p>}
          <div className="card">
            <h3>Ítems del presupuesto de control <span className="tag">periodo {periodo}</span></h3>
            <div className="toolbar mt0">
              <input type="text" placeholder="Filtrar ítems…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {items.isLoading || ejec.isLoading ? (
              <Cargando />
            ) : filas.length === 0 ? (
              <Vacio>Sin ítems (¿el presupuesto tiene una versión aprobada?).</Vacio>
            ) : (
              <div className="tw">
                <table>
                  <thead>
                    <tr>
                      <th>Ítem</th><th>Descripción</th><th>Presupuestado</th><th>Ejecutado acum.</th><th>Avance actual</th>
                      <th>Vr. ejecutado del periodo</th><th>% avance acumulado</th><th>Observación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas.map((f) => {
                      const id = f.id as number;
                      const c = captura[id];
                      const nuevoAv = c?.avance ? toNum(c.avance.replace(",", ".")) / 100 : null;
                      const baja = nuevoAv !== null && f.avance_fisico_pct !== null && nuevoAv < toNum(f.avance_fisico_pct);
                      return (
                        <tr key={id} className={baja ? "par" : c ? "sel" : ""}>
                          <td>{f.codigo}</td>
                          <td>{f.descripcion}</td>
                          <td className="n">{cop(f.presupuestado)}</td>
                          <td className="n">{cop(f.ejecutado)}</td>
                          <td className="n">{pct(f.avance_fisico_pct)}</td>
                          <td className="n">
                            <input className="in" disabled={!puede.control} value={c?.valor ?? ""} onChange={(e) => set(id, "valor", e.target.value)} />
                          </td>
                          <td className="n">
                            <input className="in" disabled={!puede.control} value={c?.avance ?? ""} onChange={(e) => set(id, "avance", e.target.value)} />
                          </td>
                          <td>
                            <input className="in" disabled={!puede.control} value={c?.obs ?? ""} onChange={(e) => set(id, "obs", e.target.value)} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="note">Filas amarillas: el avance digitado es menor que el acumulado actual (el sistema lo advertirá).</p>
          </div>
        </>
      )}
    </>
  );
}
