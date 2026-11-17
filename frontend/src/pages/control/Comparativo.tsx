import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, type ComparativoFila, type NivelComparativo } from "../../api/client";
import { SidePanel } from "../../components/Layout";
import { SelectorPresupuesto, SelectorVersion } from "../../components/Selectores";
import { Cargando, ErrorBox, Kpi, PillComparativo, Vacio } from "../../components/ui";
import { claseVariacion, cop, copCompacto, num, pct, toNum } from "../../lib/format";

const NIVELES: { k: NivelComparativo; t: string; d: string }[] = [
  { k: "capitulo", t: "Capítulo", d: "resumen" },
  { k: "item", t: "Ítem", d: "EDT" },
  { k: "insumo", t: "Insumo", d: "explosión" },
];

type Orden = "codigo" | "impacto";

function Signo({ v, fmt }: { v: string | null; fmt: (x: string) => string }) {
  if (v === null || v === undefined) return <>—</>;
  const n = toNum(v);
  return <span className={claseVariacion(n)}>{n > 0 ? "+" : ""}{fmt(v)}</span>;
}

export default function ComparativoPage() {
  const [params] = useSearchParams();
  const comparadaInicial = params.get("comparada") ? Number(params.get("comparada")) : null;

  const [pBase, setPBase] = useState<number | null>(null);
  const [vBase, setVBase] = useState<number | null>(null);
  const [pComp, setPComp] = useState<number | null>(null);
  const [vComp, setVComp] = useState<number | null>(comparadaInicial);
  const [nivel, setNivel] = useState<NivelComparativo>("item");
  const [soloDif, setSoloDif] = useState(true);
  const [orden, setOrden] = useState<Orden>("impacto");
  const [consulta, setConsulta] = useState<{ b: number; c: number; n: NivelComparativo } | null>(null);
  const [errExp, setErrExp] = useState<unknown>(null);

  // Si llega ?comparada=ID, ubica su presupuesto y propone como base la versión origen o la anterior.
  const vIni = useQuery({
    queryKey: ["version", comparadaInicial],
    queryFn: () => api.presupuestos.version(comparadaInicial as number),
    enabled: comparadaInicial !== null,
  });
  const detIni = useQuery({
    queryKey: ["presupuesto", vIni.data?.presupuesto_id],
    queryFn: () => api.presupuestos.detalle(vIni.data!.presupuesto_id),
    enabled: !!vIni.data,
  });
  useEffect(() => {
    const v = vIni.data;
    const d = detIni.data;
    if (!v || !d) return;
    setPComp(v.presupuesto_id);
    setPBase(v.presupuesto_id);
    const anterior = v.version_origen_id ?? d.versiones.filter((x) => x.numero < v.numero).pop()?.id ?? null;
    setVBase(anterior);
  }, [vIni.data, detIni.data]);

  const comp = useQuery({
    queryKey: ["comparativo", consulta],
    queryFn: () => api.control.comparativo(consulta!.b, consulta!.c, consulta!.n),
    enabled: consulta !== null,
  });
  const c = comp.data;

  const filas = useMemo(() => {
    let f: ComparativoFila[] = c?.filas ?? [];
    if (soloDif) f = f.filter((x) => x.estado !== "IGUAL");
    f = [...f].sort((a, b) =>
      orden === "impacto" ? Math.abs(toNum(b.impacto)) - Math.abs(toNum(a.impacto)) : a.codigo.localeCompare(b.codigo),
    );
    return f;
  }, [c, soloDif, orden]);

  const cuenta = (e: string) => c?.filas.filter((f) => f.estado === e).length ?? 0;
  const esInsumo = c?.nivel === "insumo";
  const impactoTotal = toNum(c?.totales.impacto);

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Comparativo de versiones</h2>
        <p className="sub">Base vs comparada (pueden ser de presupuestos distintos, p. ej. FIC vs FIV).</p>
        <SelectorPresupuesto label="Presupuesto base" value={pBase} onChange={(id) => { setPBase(id); setVBase(null); }} />
        <SelectorVersion presupuestoId={pBase} value={vBase} onChange={(id) => setVBase(id)} vacio="Versión base…" />
        <SelectorPresupuesto label="Presupuesto comparado" value={pComp} onChange={(id) => { setPComp(id); setVComp(null); }} />
        <SelectorVersion presupuestoId={pComp} value={vComp} onChange={(id) => setVComp(id)} vacio="Versión comparada…" />
        <label className="lbl">Nivel de detalle</label>
        <div className="modo m3">
          {NIVELES.map((n) => (
            <button key={n.k} type="button" className={nivel === n.k ? "on" : ""} onClick={() => setNivel(n.k)}>
              {n.t}<small>{n.d}</small>
            </button>
          ))}
        </div>
        <label className="chk">
          <input type="checkbox" checked={soloDif} onChange={(e) => setSoloDif(e.target.checked)} /> Mostrar solo diferencias
        </label>
        <button
          className="btn"
          type="button"
          disabled={!vBase || !vComp || vBase === vComp}
          onClick={() => setConsulta({ b: vBase!, c: vComp!, n: nivel })}
        >
          ⚖ Comparar
        </button>
        <p className="hint">{!vBase || !vComp ? "Elige las dos versiones." : vBase === vComp ? "Las versiones deben ser distintas." : "Listo para comparar."}</p>
      </SidePanel>

      {consulta === null ? (
        <div className="card intro">
          <p><span className="badge">CONTROL</span>Elige versión base y comparada en el panel izquierdo.</p>
          <p className="note">
            Diferencia unitaria = unitario comparado − unitario base · Impacto = total comparado − total base · Variación % = impacto / total base.
            En rojo lo que sube (sobrecosto), en verde lo que baja (ahorro).
          </p>
        </div>
      ) : (
        <>
          <ErrorBox error={comp.error ?? errExp} />
          {comp.isLoading && <Cargando texto="Comparando versiones…" />}
          {c && (
            <>
              <div className="kpis">
                <Kpi k={`Base · v${c.version_base.numero} ${c.version_base.tipo}`} v={copCompacto(c.totales.total_base)} s={cop(c.totales.total_base)} tono="b" />
                <Kpi k={`Comparada · v${c.version_comparada.numero} ${c.version_comparada.tipo}`} v={copCompacto(c.totales.total_comparado)} s={cop(c.totales.total_comparado)} tono="b" />
                <Kpi
                  k="Impacto"
                  v={`${impactoTotal > 0 ? "+" : ""}${copCompacto(c.totales.impacto)}`}
                  s={c.totales.variacion_pct !== null ? `${pct(c.totales.variacion_pct, 2)} frente a la base` : "base en cero"}
                  tono={impactoTotal > 0 ? "r" : impactoTotal < 0 ? "g" : "b"}
                />
                <Kpi k="Cambios" v={c.filas.length - cuenta("IGUAL")} s={`${cuenta("MODIFICADO")} mod · ${cuenta("NUEVO")} nuevos · ${cuenta("ELIMINADO")} eliminados`} />
              </div>

              <div className="card">
                <h3>
                  {c.version_base.nombre} → {c.version_comparada.nombre}
                  <span className="tag">nivel {c.nivel} · {filas.length} filas</span>
                </h3>
                <div className="toolbar mt0">
                  <select value={orden} onChange={(e) => setOrden(e.target.value as Orden)}>
                    <option value="impacto">Ordenar por impacto (mayor primero)</option>
                    <option value="codigo">Ordenar por código</option>
                  </select>
                  <span className="sp" />
                  <button
                    className="btn-s gh"
                    type="button"
                    onClick={() => api.control.excel.comparativo(consulta.b, consulta.c, consulta.n).catch(setErrExp)}
                  >
                    📤 Exportar comparativo
                  </button>
                </div>
                {filas.length === 0 ? (
                  <Vacio>{soloDif ? "No hay diferencias entre las versiones." : "Sin filas."}</Vacio>
                ) : (
                  <div className="tw">
                    <table>
                      <thead>
                        <tr>
                          <th>Código</th><th>Descripción</th>
                          {esInsumo && <th>Tipo</th>}
                          <th>Und</th>
                          <th>Cant. base</th><th>Cant. comp.</th>
                          <th>Unit. base</th><th>Unit. comp.</th><th>Dif. unitaria</th>
                          <th>Total base</th><th>Total comp.</th><th>Impacto</th><th>Var. %</th><th>Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filas.map((f) => (
                          <tr key={`${f.clave_id}-${f.codigo}`} className={f.estado === "MODIFICADO" ? "par" : ""}>
                            <td>{f.codigo}</td>
                            <td>{f.descripcion}</td>
                            {esInsumo && <td className="c">{f.tipo}</td>}
                            <td className="c">{f.unidad_codigo ?? ""}</td>
                            <td className="n">{num(f.cantidad_base, 2)}</td>
                            <td className="n">{num(f.cantidad_comparada, 2)}</td>
                            <td className="n">{cop(f.unitario_base)}</td>
                            <td className="n">{cop(f.unitario_comparado)}</td>
                            <td className="n"><Signo v={f.diferencia_unitaria} fmt={cop} /></td>
                            <td className="n">{cop(f.total_base)}</td>
                            <td className="n">{cop(f.total_comparado)}</td>
                            <td className="n"><Signo v={f.impacto} fmt={cop} /></td>
                            <td className="n"><Signo v={f.variacion_pct} fmt={(x) => pct(x, 1)} /></td>
                            <td className="c"><PillComparativo estado={f.estado} /></td>
                          </tr>
                        ))}
                        <tr className="tot">
                          <td colSpan={esInsumo ? 9 : 8}>Total</td>
                          <td className="n">{cop(c.totales.total_base)}</td>
                          <td className="n">{cop(c.totales.total_comparado)}</td>
                          <td className="n"><Signo v={c.totales.impacto} fmt={cop} /></td>
                          <td className="n"><Signo v={c.totales.variacion_pct} fmt={(x) => pct(x, 2)} /></td>
                          <td />
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="note">Filas amarillas = modificadas. Rojo = sobrecosto; verde = ahorro.</p>
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
