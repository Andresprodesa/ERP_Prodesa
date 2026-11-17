import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CompromisoCreate, type TableroFila, type TipoCompromiso } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { SidePanel } from "../../components/Layout";
import { SelectorPresupuesto, SelectorVersion } from "../../components/Selectores";
import { ancho, Cargando, ErrorBox, Kpi, mensajeError, Vacio } from "../../components/ui";
import { cop, copCompacto, decIn, fecha, hoyISO, pct, toNum } from "../../lib/format";

const TIPOS_COMPROMISO: TipoCompromiso[] = ["ORDEN_COMPRA", "CONTRATO", "ORDEN_SERVICIO"];

function FilasTablero(props: { filas: TableroFila[]; onClick?: (f: TableroFila) => void; selId?: number | null; total?: TableroFila }) {
  return (
    <div className="tw">
      <table>
        <thead>
          <tr>
            <th>Código</th><th>Descripción</th><th>Presupuestado</th><th>Comprometido</th><th>% Comp.</th>
            <th>Ejecutado</th><th>% Ejec.</th><th>Por comprometer</th><th>Saldo</th><th>Avance físico</th>
          </tr>
        </thead>
        <tbody>
          {props.filas.map((f) => (
            <tr
              key={`${f.id}-${f.codigo}`}
              className={props.selId === f.id ? "sel" : toNum(f.saldo) < 0 || toNum(f.por_comprometer) < 0 ? "par" : ""}
              onClick={() => props.onClick?.(f)}
            >
              <td>{f.codigo}</td>
              <td>{f.descripcion}</td>
              <td className="n">{cop(f.presupuestado)}</td>
              <td className="n">{cop(f.comprometido)}</td>
              <td className="n">{pct(f.pct_comprometido)}</td>
              <td className="n">{cop(f.ejecutado)}</td>
              <td className="n">{pct(f.pct_ejecutado)}</td>
              <td className={`n ${toNum(f.por_comprometer) < 0 ? "pos" : ""}`}>{cop(f.por_comprometer)}</td>
              <td className={`n ${toNum(f.saldo) < 0 ? "pos" : ""}`}>{cop(f.saldo)}</td>
              <td className="n">{pct(f.avance_fisico_pct)}</td>
            </tr>
          ))}
          {props.total && (
            <tr className="tot">
              <td colSpan={2}>Total</td>
              <td className="n">{cop(props.total.presupuestado)}</td>
              <td className="n">{cop(props.total.comprometido)}</td>
              <td className="n">{pct(props.total.pct_comprometido)}</td>
              <td className="n">{cop(props.total.ejecutado)}</td>
              <td className="n">{pct(props.total.pct_ejecutado)}</td>
              <td className="n">{cop(props.total.por_comprometer)}</td>
              <td className="n">{cop(props.total.saldo)}</td>
              <td className="n">{pct(props.total.avance_fisico_pct)}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Compromisos del presupuesto: listado + registro simplificado (una o varias líneas contra ítems). */
function Compromisos({ presupuestoId, items }: { presupuestoId: number; items: TableroFila[] }) {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [form, setForm] = useState({ tipo: "ORDEN_COMPRA" as TipoCompromiso, numero: "", fecha: hoyISO(), tercero: "", descripcion: "" });
  const [lineas, setLineas] = useState([{ item_id: "", cantidad: "1", valor_unitario: "" }]);
  const [advertencias, setAdvertencias] = useState<string[]>([]);

  const lista = useQuery({
    queryKey: ["compromisos", presupuestoId],
    queryFn: () => api.control.compromisos({ presupuesto_id: presupuestoId, limit: 200 }),
  });
  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["compromisos", presupuestoId] });
    qc.invalidateQueries({ queryKey: ["tablero"] });
    qc.invalidateQueries({ queryKey: ["tablero-items"] });
  };
  const crear = useMutation({
    mutationFn: () => {
      const body: CompromisoCreate = {
        presupuesto_id: presupuestoId,
        ...form,
        descripcion: form.descripcion || null,
        lineas: lineas
          .filter((l) => l.item_id && l.valor_unitario)
          .map((l) => ({ item_id: Number(l.item_id), cantidad: decIn(l.cantidad), valor_unitario: decIn(l.valor_unitario) })),
      };
      return api.control.crearCompromiso(body);
    },
    onSuccess: (c) => {
      setAdvertencias(c.advertencias);
      setForm({ ...form, numero: "", tercero: "", descripcion: "" });
      setLineas([{ item_id: "", cantidad: "1", valor_unitario: "" }]);
      invalidar();
    },
  });
  const estado = useMutation({
    mutationFn: (a: { id: number; tipo: "anular" | "liquidar" }) =>
      a.tipo === "anular" ? api.control.anularCompromiso(a.id, "Anulado desde el tablero") : api.control.liquidarCompromiso(a.id),
    onSuccess: invalidar,
  });

  return (
    <div className="card">
      <h3>Compromisos <span className="tag">órdenes y contratos contra ítems del presupuesto de control</span></h3>
      <ErrorBox error={lista.error ?? estado.error} />
      {lista.isLoading ? (
        <Cargando />
      ) : !lista.data?.items.length ? (
        <Vacio>Sin compromisos registrados.</Vacio>
      ) : (
        <div className="tw">
          <table>
            <thead>
              <tr><th>Tipo</th><th>Número</th><th>Fecha</th><th>Tercero</th><th>Descripción</th><th>Líneas</th><th>Valor</th><th>Estado</th><th /></tr>
            </thead>
            <tbody>
              {lista.data.items.map((c) => (
                <tr key={c.id}>
                  <td>{c.tipo}</td>
                  <td>{c.numero}</td>
                  <td className="c">{fecha(c.fecha)}</td>
                  <td>{c.tercero}</td>
                  <td>{c.descripcion}</td>
                  <td className="n">{c.num_lineas}</td>
                  <td className="n">{cop(c.valor_total)}</td>
                  <td className="c">
                    <span className={`pill ${c.estado === "VIGENTE" ? "ok" : c.estado === "ANULADO" ? "no" : "rv"}`}>{c.estado}</span>
                  </td>
                  <td>
                    {puede.control && c.estado === "VIGENTE" && (
                      <div className="acciones">
                        <button className="btn-s gh" type="button" onClick={() => window.confirm(`¿Liquidar ${c.numero}?`) && estado.mutate({ id: c.id, tipo: "liquidar" })}>
                          Liquidar
                        </button>
                        <button className="btn-s gh" type="button" onClick={() => window.confirm(`¿Anular ${c.numero}? Dejará de sumar en el tablero.`) && estado.mutate({ id: c.id, tipo: "anular" })}>
                          Anular
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {puede.control && (
        <div className="det">
          <div className="dh"><b>Registrar compromiso</b><span className="m">tercero con nombre ficticio (datos de prueba)</span></div>
          <ErrorBox error={crear.error} />
          {advertencias.length > 0 && <div className="tdesc">⚠ {advertencias.join(" · ")}</div>}
          <div className="frm">
            <div>
              <label>Tipo</label>
              <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as TipoCompromiso })}>
                {TIPOS_COMPROMISO.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div><label>Número</label><input value={form.numero} onChange={(e) => setForm({ ...form, numero: e.target.value })} /></div>
            <div><label>Fecha</label><input type="date" value={form.fecha} onChange={(e) => setForm({ ...form, fecha: e.target.value })} /></div>
            <div><label>Tercero</label><input placeholder="Proveedor Demo S.A.S." value={form.tercero} onChange={(e) => setForm({ ...form, tercero: e.target.value })} /></div>
            <div><label>Descripción</label><input value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} /></div>
          </div>
          {lineas.map((l, i) => (
            <div className="frm" key={i}>
              <div>
                <label>Ítem</label>
                <select value={l.item_id} onChange={(e) => setLineas(lineas.map((x, j) => (j === i ? { ...x, item_id: e.target.value } : x)))}>
                  <option value="">Selecciona ítem…</option>
                  {items.map((it) => (
                    <option key={`${it.id}`} value={it.id ?? ""}>{it.codigo} · {it.descripcion}</option>
                  ))}
                </select>
              </div>
              <div><label>Cantidad</label><input value={l.cantidad} onChange={(e) => setLineas(lineas.map((x, j) => (j === i ? { ...x, cantidad: e.target.value } : x)))} /></div>
              <div><label>Valor unitario</label><input value={l.valor_unitario} onChange={(e) => setLineas(lineas.map((x, j) => (j === i ? { ...x, valor_unitario: e.target.value } : x)))} /></div>
            </div>
          ))}
          <div className="acciones">
            <button className="btn-s gh" type="button" onClick={() => setLineas([...lineas, { item_id: "", cantidad: "1", valor_unitario: "" }])}>+ Línea</button>
            <button
              className="btn-s"
              type="button"
              disabled={crear.isPending || !form.numero || !form.tercero || !lineas.some((l) => l.item_id && l.valor_unitario)}
              onClick={() => crear.mutate()}
            >
              Registrar compromiso
            </button>
          </div>
          {crear.isError && <p className="note">{mensajeError(crear.error)}</p>}
        </div>
      )}
    </div>
  );
}

export default function TableroPage() {
  const [pid, setPid] = useState<number | null>(null);
  const [vid, setVid] = useState<number | null>(null);
  const [periodo, setPeriodo] = useState("");
  const [capSel, setCapSel] = useState<TableroFila | null>(null);

  const tablero = useQuery({
    queryKey: ["tablero", pid, vid, periodo],
    queryFn: () => api.control.tablero({ presupuesto_id: pid as number, version_id: vid ?? undefined, periodo_hasta: periodo || undefined }),
    enabled: pid !== null,
  });
  const itemsCap = useQuery({
    queryKey: ["tablero-items", pid, vid, periodo, capSel?.id],
    queryFn: () =>
      api.control.tableroItems({
        presupuesto_id: pid as number,
        version_id: vid ?? undefined,
        capitulo_id: capSel?.id ?? undefined,
        periodo_hasta: periodo || undefined,
      }),
    enabled: pid !== null && !!capSel,
  });
  const todosItems = useQuery({
    queryKey: ["tablero-items", pid, vid, periodo, "todos"],
    queryFn: () => api.control.tableroItems({ presupuesto_id: pid as number, version_id: vid ?? undefined }),
    enabled: pid !== null && !!tablero.data,
  });

  const t = tablero.data;
  const max = Math.max(0, ...(t?.capitulos ?? []).map((c) => Math.max(toNum(c.presupuestado), toNum(c.comprometido), toNum(c.ejecutado))));
  const maxSerie = Math.max(0, ...(t?.serie_mensual ?? []).map((s) => toNum(s.ejecutado_acumulado)));
  const saldo = toNum(t?.totales.saldo);

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Tablero de control</h2>
        <p className="sub">Presupuestado vs comprometido vs ejecutado por capítulo (costo directo, sin AIU).</p>
        <SelectorPresupuesto
          label="Presupuesto"
          value={pid}
          onChange={(id) => {
            setPid(id);
            setVid(null);
            setCapSel(null);
          }}
        />
        <label className="lbl">Versión de control</label>
        <SelectorVersion presupuestoId={pid} value={vid} onChange={(id) => setVid(id)} soloAprobadas vacio="Automática (última CONTROL aprobada)" />
        <label className="lbl">Ejecución hasta el periodo</label>
        <input type="month" value={periodo} onChange={(e) => setPeriodo(e.target.value)} />
        <p className="hint">Vacío = toda la ejecución registrada.</p>
      </SidePanel>

      {pid === null ? (
        <div className="card intro"><p><span className="badge">CONTROL</span>Selecciona un presupuesto.</p></div>
      ) : (
        <>
          <ErrorBox error={tablero.error} />
          {tablero.isLoading && <Cargando />}
          {t && (
            <>
              <div className="kpis">
                <Kpi k="Presupuestado" v={copCompacto(t.totales.presupuestado)} s={`v${t.version.numero} ${t.version.tipo} · ${t.version.nombre}`} tono="b" />
                <Kpi k="Comprometido" v={copCompacto(t.totales.comprometido)} s={`${pct(t.totales.pct_comprometido)} del presupuesto`} />
                <Kpi k="Ejecutado" v={copCompacto(t.totales.ejecutado)} s={`${pct(t.totales.pct_ejecutado)} · hasta ${t.periodo_hasta ?? "hoy"}`} />
                <Kpi k="Saldo" v={copCompacto(t.totales.saldo)} s="presupuestado − ejecutado" tono={saldo < 0 ? "r" : "g"} />
                <Kpi k="Avance físico" v={pct(t.totales.avance_fisico_pct)} s="ponderado por valor" tono="b" />
              </div>

              <div className="card">
                <h3>Por capítulo <span className="tag">clic en un capítulo para ver sus ítems</span></h3>
                <div className="leg">
                  <span><i className="s1" />Presupuestado</span>
                  <span><i className="s2" />Comprometido</span>
                  <span><i className="s3" />Ejecutado</span>
                </div>
                {t.capitulos.length === 0 ? (
                  <Vacio>Sin capítulos.</Vacio>
                ) : (
                  <div className="bars">
                    {t.capitulos.map((c) => (
                      <div className="bar" key={`${c.id}-${c.codigo}`} title={`${c.codigo} ${c.descripcion}`}>
                        <div className="nm">{c.codigo} · {c.descripcion}</div>
                        <div className="tr">
                          <div className="f1 ppto" style={{ width: ancho(toNum(c.presupuestado), max) }} />
                          <div className="f2" style={{ width: ancho(toNum(c.comprometido), max) }} />
                          <div className="f3" style={{ width: ancho(toNum(c.ejecutado), max) }} />
                        </div>
                        <div className="vv">{pct(c.pct_ejecutado)} ejec.</div>
                      </div>
                    ))}
                  </div>
                )}
                <FilasTablero filas={t.capitulos} total={t.totales} selId={capSel?.id} onClick={(f) => setCapSel(capSel?.id === f.id ? null : f)} />
                <p className="note">Filas amarillas: comprometido o ejecutado por encima de lo presupuestado.</p>

                {capSel && (
                  <div className="det">
                    <div className="dh">
                      <b>{capSel.codigo} · {capSel.descripcion}</b>
                      <span className="m">detalle por ítem</span>
                      <button className="x" type="button" onClick={() => setCapSel(null)}>✕ cerrar</button>
                    </div>
                    <ErrorBox error={itemsCap.error} />
                    {itemsCap.isLoading ? <Cargando /> : <FilasTablero filas={itemsCap.data ?? []} />}
                  </div>
                )}
              </div>

              <div className="card">
                <h3>Ejecución mensual</h3>
                {t.serie_mensual.length === 0 ? (
                  <Vacio>Aún no hay ejecución registrada.</Vacio>
                ) : (
                  <div className="bars">
                    {t.serie_mensual.map((s) => (
                      <div className="bar" key={s.periodo}>
                        <div className="nm">{s.periodo} · {cop(s.ejecutado)}</div>
                        <div className="tr">
                          <div className="f1" style={{ width: ancho(toNum(s.ejecutado_acumulado), maxSerie) }} />
                          <div className="f2" style={{ width: ancho(toNum(s.ejecutado), maxSerie) }} />
                        </div>
                        <div className="vv">{copCompacto(s.ejecutado_acumulado)} acum.</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <Compromisos presupuestoId={pid} items={todosItems.data ?? []} />
            </>
          )}
        </>
      )}
    </>
  );
}
