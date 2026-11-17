import { Fragment, useEffect, useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, TIPOS_INSUMO, type LineaOut, type TipoInsumo, type VersionOut } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { SidePanel } from "../../components/Layout";
import { ancho, Cargando, ErrorBox, Kpi, mensajeError, PillEstado, Vacio } from "../../components/ui";
import { cop, copCompacto, decIn, fecha, fraccionAPct, num, pct, pctAFraccion, toNum } from "../../lib/format";

type Tab = "resumen" | "lineas" | "explosion" | "aiu";

// ---------------------------------------------------------------------------
// Resumen por capítulo + AIU
// ---------------------------------------------------------------------------
function TabResumen({ versionId }: { versionId: number }) {
  const resumen = useQuery({ queryKey: ["resumen", versionId], queryFn: () => api.presupuestos.resumen(versionId) });
  const r = resumen.data;
  if (resumen.error) return <ErrorBox error={resumen.error} />;
  if (!r) return <Cargando />;
  const maxCap = Math.max(0, ...r.capitulos.map((c) => toNum(c.valor)));
  return (
    <>
      <h3 className="mt0">Totales por capítulo</h3>
      {r.capitulos.length === 0 ? (
        <Vacio>Sin líneas.</Vacio>
      ) : (
        <div className="bars">
          {r.capitulos.map((c) => (
            <div className="bar" key={c.capitulo_id}>
              <div className="nm" title={c.descripcion}>{c.codigo} · {c.descripcion}</div>
              <div className="tr"><div className="f1" style={{ width: ancho(toNum(c.valor), maxCap) }} /></div>
              <div className="vv">{cop(c.valor)} · {pct(c.participacion_pct)}</div>
            </div>
          ))}
        </div>
      )}
      <div className="tw">
        <table>
          <thead>
            <tr><th>Capítulo</th><th>Descripción</th><th>Líneas</th><th>Valor</th><th>Participación</th></tr>
          </thead>
          <tbody>
            {r.capitulos.map((c) => (
              <tr key={c.capitulo_id}>
                <td>{c.codigo}</td>
                <td>{c.descripcion}</td>
                <td className="n">{c.num_lineas}</td>
                <td className="n">{cop(c.valor)}</td>
                <td className="n">{pct(c.participacion_pct)}</td>
              </tr>
            ))}
            <tr className="tot">
              <td colSpan={2}>Costo directo</td>
              <td className="n">{r.num_lineas}</td>
              <td className="n">{cop(r.costo_directo)}</td>
              <td className="n">100,0 %</td>
            </tr>
            <tr>
              <td colSpan={3}>Administración ({pct(r.administracion_pct, 2)})</td>
              <td className="n">{cop(r.administracion)}</td>
              <td />
            </tr>
            <tr>
              <td colSpan={3}>Imprevistos ({pct(r.imprevistos_pct, 2)})</td>
              <td className="n">{cop(r.imprevistos)}</td>
              <td />
            </tr>
            <tr>
              <td colSpan={3}>Utilidad ({pct(r.utilidad_pct, 2)})</td>
              <td className="n">{cop(r.utilidad)}</td>
              <td />
            </tr>
            <tr>
              <td colSpan={3}>IVA sobre utilidad ({pct(r.iva_utilidad_pct, 2)})</td>
              <td className="n">{cop(r.iva_utilidad)}</td>
              <td />
            </tr>
            <tr className="tot">
              <td colSpan={3}>Total presupuesto (CD + AIU + IVA s/U)</td>
              <td className="n">{cop(r.total)}</td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>
      {r.lineas_sin_precio > 0 && <p className="note">⚠ {r.lineas_sin_precio} línea(s) con insumos sin precio vigente.</p>}
    </>
  );
}

// ---------------------------------------------------------------------------
// Líneas agrupadas por capítulo
// ---------------------------------------------------------------------------
function FilaLinea(props: { l: LineaOut; editable: boolean; sel: boolean; onSel: () => void; versionId: number }) {
  const { l, editable, versionId } = props;
  const qc = useQueryClient();
  const [cant, setCant] = useState(l.cantidad);
  useEffect(() => setCant(l.cantidad), [l.cantidad]);
  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["lineas", versionId] });
    qc.invalidateQueries({ queryKey: ["resumen", versionId] });
    qc.invalidateQueries({ queryKey: ["explosion", versionId] });
    qc.invalidateQueries({ queryKey: ["version", versionId] });
  };
  const actualizar = useMutation({
    mutationFn: (cantidad: string) => api.presupuestos.actualizarLinea(versionId, l.id, { cantidad }),
    onSuccess: invalidar,
  });
  const eliminar = useMutation({ mutationFn: () => api.presupuestos.eliminarLinea(versionId, l.id), onSuccess: invalidar });
  const err = actualizar.error ?? eliminar.error;
  return (
    <tr className={props.sel ? "sel" : l.insumos_sin_precio > 0 ? "par" : ""} onClick={props.onSel}>
      <td>{l.item_codigo}</td>
      <td>
        {l.item_descripcion}
        {err ? <div className="pos">{mensajeError(err)}</div> : null}
      </td>
      <td className="c">{l.unidad_codigo}</td>
      <td className="n">
        {editable ? (
          <input
            className="in"
            value={cant}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => setCant(e.target.value)}
            onBlur={() => {
              const v = decIn(cant);
              if (v && toNum(v) !== toNum(l.cantidad)) actualizar.mutate(v);
            }}
          />
        ) : (
          num(l.cantidad, 4)
        )}
      </td>
      <td className="n">{cop(l.valor_unitario)}</td>
      <td className="n">{cop(l.valor_total)}</td>
      <td className="c">{l.origen_unitario}</td>
      {editable && (
        <td className="c">
          <button
            className="btn-s gh"
            type="button"
            title="Eliminar línea"
            disabled={eliminar.isPending}
            onClick={(e) => {
              e.stopPropagation();
              if (window.confirm(`¿Eliminar la línea ${l.item_codigo}?`)) eliminar.mutate();
            }}
          >
            🗑
          </button>
        </td>
      )}
    </tr>
  );
}

function TabLineas({ version }: { version: VersionOut }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<LineaOut | null>(null);
  const lineas = useQuery({
    queryKey: ["lineas", version.id, q],
    queryFn: () => api.presupuestos.lineas(version.id, { q }),
    placeholderData: keepPreviousData,
  });
  const insumos = useQuery({
    queryKey: ["linea-insumos", version.id, sel?.id],
    queryFn: () => api.presupuestos.insumosLinea(version.id, sel!.id),
    enabled: !!sel,
  });
  const grupos = useMemo(() => {
    const m = new Map<number | null, { codigo: string; descripcion: string; lineas: LineaOut[]; total: number }>();
    for (const l of lineas.data ?? []) {
      const g = m.get(l.capitulo_id) ?? {
        codigo: l.capitulo_codigo ?? "SIN-CAPITULO",
        descripcion: l.capitulo_descripcion ?? "Ítems sin capítulo",
        lineas: [],
        total: 0,
      };
      g.lineas.push(l);
      g.total += toNum(l.valor_total);
      m.set(l.capitulo_id, g);
    }
    return [...m.values()].sort((a, b) => a.codigo.localeCompare(b.codigo));
  }, [lineas.data]);
  const totalGeneral = grupos.reduce((s, g) => s + g.total, 0);
  const editable = version.editable;
  const cols = editable ? 8 : 7;

  return (
    <>
      <div className="toolbar mt0">
        <input type="text" placeholder="Filtrar por código o descripción…" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="sp" />
        <span className="note">{editable ? "Edita la cantidad y sal del campo para guardar." : "Versión inmutable (solo lectura)."}</span>
      </div>
      <ErrorBox error={lineas.error} />
      {lineas.isLoading ? (
        <Cargando />
      ) : grupos.length === 0 ? (
        <Vacio>Sin líneas.</Vacio>
      ) : (
        <div className="tw">
          <table>
            <thead>
              <tr>
                <th>Ítem</th><th>Descripción</th><th>Und</th><th>Cantidad</th><th>Vr. unitario</th><th>Vr. total</th><th>Origen</th>
                {editable && <th />}
              </tr>
            </thead>
            <tbody>
              {grupos.map((g) => (
                <Fragment key={g.codigo}>
                  <tr className="tot">
                    <td>{g.codigo}</td>
                    <td colSpan={4}>{g.descripcion}</td>
                    <td className="n">{cop(g.total)}</td>
                    <td colSpan={cols - 6} />
                  </tr>
                  {g.lineas.map((l) => (
                    <FilaLinea key={l.id} l={l} editable={editable} versionId={version.id} sel={sel?.id === l.id} onSel={() => setSel(l)} />
                  ))}
                </Fragment>
              ))}
              <tr className="tot">
                <td colSpan={5}>Costo directo</td>
                <td className="n">{cop(totalGeneral)}</td>
                <td colSpan={cols - 6} />
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {sel && (
        <div className="det">
          <div className="dh">
            <b>{sel.item_codigo} · {sel.item_descripcion}</b>
            <span className="m">{num(sel.cantidad)} {sel.unidad_codigo} × {cop(sel.valor_unitario)} · origen {sel.origen_unitario}</span>
            {sel.origen_unitario === "APU" && <Link className="btn-s gh" to={`/apu/item/${sel.item_id}`}>🧮 APU</Link>}
            <button className="x" type="button" onClick={() => setSel(null)}>✕ cerrar</button>
          </div>
          <h4>Snapshot de insumos de la línea</h4>
          <ErrorBox error={insumos.error} />
          {insumos.isLoading ? (
            <Cargando />
          ) : !insumos.data?.length ? (
            <Vacio>Línea sin desglose de insumos (valor manual o importado).</Vacio>
          ) : (
            <div className="tw">
              <table>
                <thead>
                  <tr><th>Insumo</th><th>Und</th><th>Tipo</th><th>Cant. unit.</th><th>% Desp.</th><th>Precio</th><th>Cant. total</th><th>Vr. total</th></tr>
                </thead>
                <tbody>
                  {insumos.data.map((i) => (
                    <tr key={i.insumo_id} className={i.precio_faltante ? "par" : ""}>
                      <td>{i.insumo_codigo} · {i.insumo_descripcion}</td>
                      <td className="c">{i.unidad_codigo}</td>
                      <td className="c">{i.tipo}</td>
                      <td className="n">{num(i.cantidad_unitaria, 6)}</td>
                      <td className="n">{pct(i.desperdicio_pct)}</td>
                      <td className="n">{cop(i.precio_unitario)}</td>
                      <td className="n">{num(i.cantidad_total, 2)}</td>
                      <td className="n">{cop(i.valor_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Explosión de insumos
// ---------------------------------------------------------------------------
function TabExplosion({ versionId }: { versionId: number }) {
  const [tipo, setTipo] = useState<TipoInsumo | "">("");
  const [q, setQ] = useState("");
  const [errExp, setErrExp] = useState<unknown>(null);
  const exp = useQuery({
    queryKey: ["explosion", versionId, tipo],
    queryFn: () => api.presupuestos.explosion(versionId, tipo),
    placeholderData: keepPreviousData,
  });
  const e = exp.data;
  const filas = (e?.filas ?? []).filter(
    (f) => !q || f.insumo_codigo.toLowerCase().includes(q.toLowerCase()) || f.insumo_descripcion.toLowerCase().includes(q.toLowerCase()),
  );
  const maxTipo = Math.max(0, ...(e?.por_tipo ?? []).map((t) => toNum(t.valor_total)));
  return (
    <>
      <div className="toolbar mt0">
        <select value={tipo} onChange={(ev) => setTipo(ev.target.value as TipoInsumo | "")}>
          <option value="">Todos los tipos</option>
          {TIPOS_INSUMO.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <input type="text" placeholder="Buscar insumo…" value={q} onChange={(ev) => setQ(ev.target.value)} />
        <span className="sp" />
        <button
          className="btn-s gh"
          type="button"
          onClick={() => api.control.excel.explosion(versionId).catch(setErrExp)}
        >
          📤 Exportar explosión
        </button>
      </div>
      <ErrorBox error={exp.error ?? errExp} />
      {!e ? (
        <Cargando />
      ) : (
        <>
          <div className="kpis">
            <Kpi k="Total insumos" v={copCompacto(e.total_insumos)} s={cop(e.total_insumos)} />
            <Kpi k="Sin desglose" v={copCompacto(e.valor_sin_desglose)} s="líneas manuales / importadas" tono="b" />
            <Kpi k="Total (cuadra con CD)" v={copCompacto(e.total)} s={`${e.filas.length} insumos`} tono="b" />
          </div>
          {e.por_tipo.length > 0 && (
            <div className="bars">
              {e.por_tipo.map((t) => (
                <div className="bar" key={t.tipo}>
                  <div className="nm">{t.tipo}</div>
                  <div className="tr"><div className="f1" style={{ width: ancho(toNum(t.valor_total), maxTipo) }} /></div>
                  <div className="vv">{cop(t.valor_total)} · {pct(t.participacion_pct)}</div>
                </div>
              ))}
            </div>
          )}
          {filas.length === 0 ? (
            <Vacio>Sin insumos.</Vacio>
          ) : (
            <div className="tw">
              <table>
                <thead>
                  <tr><th>Código</th><th>Insumo</th><th>Und</th><th>Tipo</th><th>Cantidad total</th><th>Precio prom.</th><th>Valor total</th><th>Part.</th></tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.insumo_id}>
                      <td>{f.insumo_codigo}</td>
                      <td>{f.insumo_descripcion}</td>
                      <td className="c">{f.unidad_codigo}</td>
                      <td className="c">{f.tipo}</td>
                      <td className="n">{num(f.cantidad_total, 2)}</td>
                      <td className="n">{cop(f.precio_unitario)}</td>
                      <td className="n">{cop(f.valor_total)}</td>
                      <td className="n">{pct(f.participacion_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Configuración AIU
// ---------------------------------------------------------------------------
function TabAiu({ version }: { version: VersionOut }) {
  const qc = useQueryClient();
  const inicial = () => ({
    nombre: version.nombre,
    fecha_precios: version.fecha_precios,
    adm: fraccionAPct(version.administracion_pct),
    imp: fraccionAPct(version.imprevistos_pct),
    uti: fraccionAPct(version.utilidad_pct),
    iva: fraccionAPct(version.iva_utilidad_pct),
  });
  const [f, setF] = useState(inicial);
  useEffect(() => setF(inicial()), [version]); // eslint-disable-line react-hooks/exhaustive-deps
  const guardar = useMutation({
    mutationFn: () =>
      api.presupuestos.actualizarVersion(version.id, {
        nombre: f.nombre,
        fecha_precios: f.fecha_precios,
        administracion_pct: pctAFraccion(f.adm),
        imprevistos_pct: pctAFraccion(f.imp),
        utilidad_pct: pctAFraccion(f.uti),
        iva_utilidad_pct: pctAFraccion(f.iva),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["version", version.id] });
      qc.invalidateQueries({ queryKey: ["resumen", version.id] });
    },
  });
  const dis = !version.editable;
  return (
    <>
      <p className="tdesc">
        <b>AIU</b>: Administración, Imprevistos y Utilidad se calculan sobre el costo directo; el IVA se liquida sobre la
        utilidad. Cambiar la fecha de precios no recalcula: usa <b>Recalcular</b> en el panel izquierdo.
      </p>
      <ErrorBox error={guardar.error} />
      <div className="frm">
        <div><label>Nombre</label><input disabled={dis} value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></div>
        <div><label>Fecha de precios</label><input type="date" disabled={dis} value={f.fecha_precios} onChange={(e) => setF({ ...f, fecha_precios: e.target.value })} /></div>
        <div><label>Administración %</label><input disabled={dis} value={f.adm} onChange={(e) => setF({ ...f, adm: e.target.value })} /></div>
        <div><label>Imprevistos %</label><input disabled={dis} value={f.imp} onChange={(e) => setF({ ...f, imp: e.target.value })} /></div>
        <div><label>Utilidad %</label><input disabled={dis} value={f.uti} onChange={(e) => setF({ ...f, uti: e.target.value })} /></div>
        <div><label>IVA sobre utilidad %</label><input disabled={dis} value={f.iva} onChange={(e) => setF({ ...f, iva: e.target.value })} /></div>
      </div>
      {!dis && (
        <button className="btn-s" type="button" disabled={guardar.isPending} onClick={() => guardar.mutate()}>
          💾 Guardar configuración
        </button>
      )}
      {guardar.isSuccess && <span className="note"> Guardado.</span>}
    </>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------
export default function VersionPage() {
  const { versionId } = useParams();
  const vid = Number(versionId);
  const navigate = useNavigate();
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("resumen");
  const [qItem, setQItem] = useState("");
  const [itemSel, setItemSel] = useState<{ id: number; codigo: string; descripcion: string; unidad: string | null; tiene_apu: boolean } | null>(null);
  const [cantidad, setCantidad] = useState("");
  const [vrManual, setVrManual] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [errAccion, setErrAccion] = useState<unknown>(null);

  const version = useQuery({ queryKey: ["version", vid], queryFn: () => api.presupuestos.version(vid) });
  const v = version.data;
  const presupuesto = useQuery({
    queryKey: ["presupuesto", v?.presupuesto_id],
    queryFn: () => api.presupuestos.detalle(v!.presupuesto_id),
    enabled: !!v,
  });
  const resumen = useQuery({ queryKey: ["resumen", vid], queryFn: () => api.presupuestos.resumen(vid), enabled: !!v });
  const items = useQuery({
    queryKey: ["edt-items", qItem],
    queryFn: () => api.maestros.edt({ nivel: "ITEM", q: qItem, activo: true, limit: 15 }),
    enabled: !!v?.editable && qItem.trim().length >= 2,
  });

  const invalidarTodo = () => {
    for (const k of ["version", "lineas", "resumen", "explosion"]) qc.invalidateQueries({ queryKey: [k, vid] });
    qc.invalidateQueries({ queryKey: ["presupuesto"] });
  };

  const agregar = useMutation({
    mutationFn: () =>
      api.presupuestos.crearLinea(vid, {
        item_id: itemSel!.id,
        cantidad: decIn(cantidad),
        valor_unitario: vrManual.trim() ? decIn(vrManual) : undefined,
      }),
    onSuccess: (l) => {
      invalidarTodo();
      setMsg(`Línea ${l.item_codigo} agregada (${cop(l.valor_total)}).`);
      setItemSel(null);
      setCantidad("");
      setVrManual("");
      setQItem("");
    },
  });

  const accion = useMutation({
    mutationFn: async (a: "recalcular" | "aprobar" | "cerrar") => {
      if (a === "recalcular") {
        const r = await api.presupuestos.recalcular(vid);
        return `Recalculadas ${r.lineas_recalculadas} líneas · CD ${cop(r.total_costo_directo)}${
          r.insumos_sin_precio.length ? ` · ${r.insumos_sin_precio.length} insumos sin precio` : ""
        }`;
      }
      if (a === "aprobar") {
        await api.presupuestos.aprobar(vid);
        return "Versión aprobada: totales y precios congelados.";
      }
      await api.presupuestos.cerrar(vid);
      return "Versión cerrada.";
    },
    onMutate: () => {
      setErrAccion(null);
      setMsg(null);
    },
    onSuccess: (m) => {
      setMsg(m);
      invalidarTodo();
    },
    onError: setErrAccion,
  });

  const exportar = (fn: () => Promise<void>) => fn().catch(setErrAccion);

  if (version.error) return <ErrorBox error={version.error} />;
  if (!v) return <Cargando />;
  const r = resumen.data;

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Versión {v.numero} · {v.tipo}</h2>
        <p className="sub">
          {presupuesto.data ? `${presupuesto.data.proyecto_codigo} · ${presupuesto.data.codigo}` : "…"} · precios a {fecha(v.fecha_precios)} ({v.ciudad_precios_codigo})
        </p>

        {v.editable && puede.presupuesto ? (
          <>
            <label className="lbl">Agregar línea · buscar ítem EDT</label>
            <input type="text" placeholder="Código o descripción (mín. 2 letras)" value={qItem} onChange={(e) => setQItem(e.target.value)} />
            {items.data && !itemSel && (
              <ul className="lst">
                {items.data.items.map((it) => (
                  <li
                    key={it.id}
                    onClick={() =>
                      setItemSel({ id: it.id, codigo: it.codigo, descripcion: it.descripcion, unidad: it.unidad_codigo, tiene_apu: it.tiene_apu })
                    }
                  >
                    {it.codigo} · {it.descripcion}
                    <small>{it.unidad_codigo} · {it.tiene_apu ? "con APU" : "sin APU (requiere valor manual)"}</small>
                  </li>
                ))}
                {items.data.items.length === 0 && <li>Sin ítems</li>}
              </ul>
            )}
            {itemSel && (
              <ul className="lst">
                <li className="on" onClick={() => setItemSel(null)}>
                  {itemSel.codigo} · {itemSel.descripcion}
                  <small>{itemSel.unidad} · clic para cambiar</small>
                </li>
              </ul>
            )}
            <div className="row2">
              <input type="text" placeholder={`Cantidad${itemSel?.unidad ? ` (${itemSel.unidad})` : ""}`} value={cantidad} onChange={(e) => setCantidad(e.target.value)} />
              <input type="text" placeholder={itemSel && !itemSel.tiene_apu ? "Vr. unitario" : "Vr. unit. (opcional)"} value={vrManual} onChange={(e) => setVrManual(e.target.value)} />
            </div>
            <button
              className="btn"
              type="button"
              disabled={agregar.isPending || !itemSel || !cantidad || (!itemSel.tiene_apu && !vrManual)}
              onClick={() => agregar.mutate()}
            >
              {agregar.isPending && <span className="spin" />}+ Agregar línea
            </button>
            <p className="hint">Sin valor unitario se valoriza con el APU del ítem a la fecha y ciudad de la versión.</p>
            {agregar.error && <p className="hint">⚠ {mensajeError(agregar.error)}</p>}
            <hr className="sep" />
          </>
        ) : (
          <p className="sub">{v.editable ? "Solo lectura para tu rol." : "Versión inmutable: aprobada el " + fecha(v.aprobado_at) + (v.aprobado_por ? ` por ${v.aprobado_por}` : "") + "."}</p>
        )}
      </SidePanel>

      <div className="toolbar mt0">
        <Link className="btn-s gh" to={`/presupuestos/${v.presupuesto_id}`}>◀ Versiones del presupuesto</Link>
        <span className="sp" />
        {v.editable && puede.presupuesto && (
          <button className="btn-s gh" type="button" disabled={accion.isPending} onClick={() => accion.mutate("recalcular")}>
            ↻ Recalcular precios
          </button>
        )}
        {v.estado === "BORRADOR" && puede.aprobacion && (
          <button
            className="btn-s gh"
            type="button"
            disabled={accion.isPending || v.num_lineas === 0}
            onClick={() => window.confirm("¿Aprobar esta versión? Quedará inmutable.") && accion.mutate("aprobar")}
          >
            ✔ Aprobar
          </button>
        )}
        {v.estado === "APROBADO" && puede.aprobacion && (
          <button className="btn-s gh" type="button" disabled={accion.isPending} onClick={() => window.confirm("¿Cerrar esta versión?") && accion.mutate("cerrar")}>
            🔒 Cerrar
          </button>
        )}
        {puede.presupuesto && (
          <button className="btn-s gh" type="button" onClick={() => navigate(`/presupuestos/${v.presupuesto_id}`)}>⧉ Copiar…</button>
        )}
        <button className="btn-s gh" type="button" onClick={() => exportar(() => api.control.excel.presupuesto(vid))}>📤 Excel presupuesto</button>
        <button className="btn-s gh" type="button" onClick={() => navigate(`/control/comparativo?comparada=${vid}`)}>⚖ Comparar</button>
      </div>

      {msg && <p className="tdesc">{msg}</p>}
      <ErrorBox error={errAccion} />

      <div className="kpis">
        <Kpi k="Estado" v={<PillEstado estado={v.estado} />} s={`${v.nombre}`} tono="b" />
        <Kpi k="Costo directo" v={copCompacto(r?.costo_directo ?? v.total_costo_directo)} s={cop(r?.costo_directo ?? v.total_costo_directo)} />
        <Kpi k="AIU + IVA s/U" v={copCompacto(r ? toNum(r.total) - toNum(r.costo_directo) : null)} s={r ? `A ${pct(r.administracion_pct)} · I ${pct(r.imprevistos_pct)} · U ${pct(r.utilidad_pct)}` : ""} tono="b" />
        <Kpi k="Total presupuesto" v={copCompacto(r?.total ?? v.total_presupuesto)} s={cop(r?.total ?? v.total_presupuesto)} tono="g" />
      </div>

      <div className="card">
        <div className="tabs">
          {(
            [
              ["resumen", "Resumen por capítulo"],
              ["lineas", `Líneas (${v.num_lineas})`],
              ["explosion", "Explosión de insumos"],
              ["aiu", "AIU y configuración"],
            ] as [Tab, string][]
          ).map(([k, t]) => (
            <button key={k} type="button" className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
              {t}
            </button>
          ))}
        </div>
        <div className="tabpane on">
          <div className="toolbar" />
          {tab === "resumen" && <TabResumen versionId={vid} />}
          {tab === "lineas" && <TabLineas version={v} />}
          {tab === "explosion" && <TabExplosion versionId={vid} />}
          {tab === "aiu" && <TabAiu version={v} />}
        </div>
      </div>
    </>
  );
}
