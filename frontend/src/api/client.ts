/**
 * Cliente API tipado de ERP Prodesa / ADPRO.
 * Fuente de verdad: docs/API_CONTRATO.md (v0.1). Este es el ÚNICO archivo que conoce rutas HTTP.
 *
 * Convenciones del contrato:
 * - Decimales (dinero, cantidades, porcentajes) viajan como string ("1250000.0000").
 * - Porcentajes como fracción ("0.05" = 5 %).
 * - Errores: {"error": {"code", "message", "details"}}.
 * - Token Bearer en memoria + sessionStorage. Ante 401 se invoca onUnauthorized (redirige a login).
 *   En producción el login pasa a Microsoft Entra ID (MSAL): solo cambia `TokenProvider`.
 */

// ---------------------------------------------------------------------------
// 0. Tipos base y enums
// ---------------------------------------------------------------------------
export type Dec = string;
export type ISODate = string; // YYYY-MM-DD
export type Periodo = string; // YYYY-MM

export type Rol = "admin" | "presupuesto" | "obra" | "consulta";
export type TipoInsumo = "MAT" | "MO" | "EQ" | "TR" | "SUB";
export type TipoProyecto = "VIS" | "VIP" | "NO_VIS";
export type EstadoProyecto = "PLANEACION" | "EN_EJECUCION" | "TERMINADO" | "SUSPENDIDO";
export type NivelEdt = "CAPITULO" | "DETALLE" | "GRUPO" | "ITEM";
export type TipoVersion = "BASE" | "FIC" | "FIV" | "CONTROL" | "OTRO";
export type EstadoVersion = "BORRADOR" | "APROBADO" | "CERRADO";
export type OrigenValor = "APU" | "MANUAL" | "IMPORTADO";
export type TipoCompromiso = "ORDEN_COMPRA" | "CONTRATO" | "ORDEN_SERVICIO";
export type EstadoCompromiso = "VIGENTE" | "LIQUIDADO" | "ANULADO";
export type NivelComparativo = "item" | "insumo" | "capitulo";
export type EstadoComparativo = "IGUAL" | "MODIFICADO" | "NUEVO" | "ELIMINADO";

export const TIPOS_INSUMO: TipoInsumo[] = ["MAT", "MO", "EQ", "TR", "SUB"];
export const TIPOS_VERSION: TipoVersion[] = ["BASE", "FIC", "FIV", "CONTROL", "OTRO"];

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Auditoria {
  created_at?: string;
  updated_at?: string;
  created_by?: string | null;
  updated_by?: string | null;
}

// ---------------------------------------------------------------------------
// 1. Auth
// ---------------------------------------------------------------------------
export interface UsuarioOut {
  id: number;
  username: string;
  nombre: string;
  email: string | null;
  rol: Rol;
  activo: boolean;
}
export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UsuarioOut;
}
export interface Health {
  status: string;
  app: string;
  version: string;
  environment: string;
  database: string;
}
export interface AuditLogOut {
  id: number;
  timestamp: string;
  username: string | null;
  accion: string;
  entidad: string;
  entidad_id: number | null;
  detalle: unknown;
}

// ---------------------------------------------------------------------------
// 2. Maestros
// ---------------------------------------------------------------------------
export interface UnidadOut extends Auditoria {
  id: number;
  codigo: string;
  nombre: string;
  activo: boolean;
}
export interface CiudadOut extends Auditoria {
  id: number;
  codigo: string;
  nombre: string;
  departamento: string | null;
  regional: string | null;
  activo: boolean;
}
export interface InsumoOut extends Auditoria {
  id: number;
  codigo: string;
  descripcion: string;
  unidad_id: number;
  unidad_codigo: string;
  tipo: TipoInsumo;
  activo: boolean;
  observaciones: string | null;
}
export interface InsumoCreate {
  codigo: string;
  descripcion: string;
  unidad_id: number;
  tipo: TipoInsumo;
  activo?: boolean;
  observaciones?: string | null;
}
export type InsumoUpdate = Partial<InsumoCreate>;
export interface PrecioHistoricoOut {
  lista_id: number;
  lista_codigo: string;
  lista_nombre: string;
  ciudad_id: number;
  ciudad_codigo: string;
  fecha_desde: ISODate;
  precio: Dec;
}
export interface ListaPreciosOut extends Auditoria {
  id: number;
  codigo: string;
  nombre: string;
  ciudad_id: number;
  ciudad_codigo: string;
  fecha_desde: ISODate;
  activo: boolean;
  observaciones: string | null;
  num_precios: number;
}
export interface PrecioOut {
  id: number;
  insumo_id: number;
  insumo_codigo: string;
  insumo_descripcion: string;
  unidad_codigo: string;
  tipo: TipoInsumo;
  precio: Dec;
  fuente: string | null;
}
export interface PrecioVigenteOut {
  insumo_id: number;
  precio: Dec;
  lista_id: number;
  fecha_desde: ISODate;
}
export interface TorreOut {
  id: number;
  etapa_id: number;
  codigo: string;
  nombre: string;
  numero_pisos: number | null;
  numero_unidades: number | null;
}
export interface EtapaOut {
  id: number;
  proyecto_id: number;
  codigo: string;
  nombre: string;
  orden: number;
  numero_unidades: number | null;
  torres: TorreOut[];
}
export interface ProyectoOut extends Auditoria {
  id: number;
  codigo: string;
  nombre: string;
  ciudad_id: number;
  ciudad_codigo: string;
  ciudad_nombre: string;
  tipo: TipoProyecto;
  estado: EstadoProyecto;
  fecha_inicio: ISODate | null;
  fecha_fin_estimada: ISODate | null;
  numero_unidades: number | null;
  descripcion: string | null;
}
export interface ProyectoDetalleOut extends ProyectoOut {
  etapas: EtapaOut[];
}
export interface EdtNodoOut extends Auditoria {
  id: number;
  parent_id: number | null;
  nivel: NivelEdt;
  codigo: string;
  descripcion: string;
  unidad_id: number | null;
  unidad_codigo: string | null;
  orden: number;
  activo: boolean;
  notas: string | null;
  tiene_apu: boolean;
}
export interface EdtArbolNodo extends EdtNodoOut {
  hijos: EdtArbolNodo[];
}
export interface EdtRutaNodo {
  id: number;
  nivel: NivelEdt;
  codigo: string;
  descripcion: string;
}
export interface EdtNodoDetalleOut extends EdtNodoOut {
  ruta: EdtRutaNodo[];
}

// ---------------------------------------------------------------------------
// 3. APU
// ---------------------------------------------------------------------------
export interface ApuOut extends Auditoria {
  id: number;
  item_id: number;
  item_codigo: string;
  item_descripcion: string;
  unidad_codigo: string;
  descripcion: string | null;
  activo: boolean;
  observaciones: string | null;
  num_insumos: number;
}
export interface ApuInsumoOut {
  id: number;
  insumo_id: number;
  insumo_codigo: string;
  insumo_descripcion: string;
  unidad_codigo: string | null;
  tipo: TipoInsumo;
  cantidad: Dec;
  desperdicio_pct: Dec;
  orden: number;
  observacion: string | null;
}
export interface ApuDetalleOut extends ApuOut {
  insumos: ApuInsumoOut[];
}
export interface ApuInsumoIn {
  insumo_id: number;
  cantidad: Dec;
  desperdicio_pct?: Dec;
  orden?: number;
  observacion?: string | null;
}
export interface ComponenteOut {
  insumo_id: number;
  insumo_codigo: string;
  insumo_descripcion: string;
  unidad_codigo: string | null;
  tipo: TipoInsumo;
  cantidad: Dec;
  desperdicio_pct: Dec;
  precio_unitario: Dec | null;
  valor_unitario: Dec;
  precio_faltante: boolean;
  lista_id: number | null;
}
export interface ValorizacionOut {
  apu_id: number;
  item_id: number;
  ciudad_id: number;
  fecha: ISODate;
  valor_unitario: Dec;
  insumos_sin_precio: number[];
  subtotales_por_tipo: Partial<Record<TipoInsumo, Dec>>;
  componentes: ComponenteOut[];
}

// ---------------------------------------------------------------------------
// 4. Presupuesto
// ---------------------------------------------------------------------------
export interface VersionOut extends Auditoria {
  id: number;
  presupuesto_id: number;
  numero: number;
  tipo: TipoVersion;
  estado: EstadoVersion;
  nombre: string;
  descripcion: string | null;
  fecha_precios: ISODate;
  ciudad_precios_id: number;
  ciudad_precios_codigo: string;
  administracion_pct: Dec;
  imprevistos_pct: Dec;
  utilidad_pct: Dec;
  iva_utilidad_pct: Dec;
  version_origen_id: number | null;
  aprobado_at: string | null;
  aprobado_por: string | null;
  cerrado_at: string | null;
  cerrado_por: string | null;
  total_costo_directo: Dec;
  total_presupuesto: Dec;
  num_lineas: number;
  editable: boolean;
}
export interface PresupuestoOut extends Auditoria {
  id: number;
  proyecto_id: number;
  proyecto_codigo: string;
  proyecto_nombre: string;
  etapa_id: number | null;
  etapa_codigo: string | null;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  num_versiones: number;
}
export interface PresupuestoDetalleOut extends PresupuestoOut {
  versiones: VersionOut[];
}
export interface PresupuestoCreate {
  proyecto_id: number;
  etapa_id?: number | null;
  codigo: string;
  nombre: string;
  descripcion?: string | null;
}
export interface VersionCreate {
  tipo: TipoVersion;
  nombre: string;
  descripcion?: string | null;
  fecha_precios: ISODate;
  ciudad_precios_id?: number | null;
  administracion_pct?: Dec;
  imprevistos_pct?: Dec;
  utilidad_pct?: Dec;
  iva_utilidad_pct?: Dec;
}
export type VersionUpdate = Partial<Omit<VersionCreate, "tipo">>;
export interface VersionCopy {
  tipo: TipoVersion;
  nombre: string;
  descripcion?: string | null;
  presupuesto_id_destino?: number | null;
  recalcular_precios?: boolean;
  fecha_precios?: ISODate | null;
}
export interface RecalculoOut {
  version_id: number;
  lineas_recalculadas: number;
  insumos_sin_precio: number[];
  total_costo_directo: Dec;
}
export interface LineaOut {
  id: number;
  version_id: number;
  item_id: number;
  item_codigo: string;
  item_descripcion: string;
  unidad_codigo: string | null;
  capitulo_id: number | null;
  capitulo_codigo: string | null;
  capitulo_descripcion: string | null;
  cantidad: Dec;
  valor_unitario: Dec;
  valor_total: Dec;
  origen_unitario: OrigenValor;
  orden: number;
  observacion: string | null;
  num_insumos: number;
  insumos_sin_precio: number;
}
export interface LineaCreate {
  item_id: number;
  cantidad: Dec;
  valor_unitario?: Dec | null;
  observacion?: string | null;
}
export interface LineaUpdate {
  cantidad?: Dec;
  valor_unitario?: Dec;
  observacion?: string | null;
  orden?: number;
}
export interface LineaInsumoOut {
  insumo_id: number;
  insumo_codigo: string;
  insumo_descripcion: string;
  unidad_codigo: string | null;
  tipo: TipoInsumo;
  cantidad_unitaria: Dec;
  desperdicio_pct: Dec;
  precio_unitario: Dec | null;
  valor_unitario: Dec;
  precio_faltante: boolean;
  cantidad_total: Dec;
  valor_total: Dec;
}
export interface CapituloTotal {
  capitulo_id: number | null;
  codigo: string;
  descripcion: string;
  valor: Dec;
  participacion_pct: Dec;
  num_lineas: number;
}
export interface ResumenOut {
  version_id: number;
  capitulos: CapituloTotal[];
  costo_directo: Dec;
  administracion_pct: Dec;
  imprevistos_pct: Dec;
  utilidad_pct: Dec;
  iva_utilidad_pct: Dec;
  administracion: Dec;
  imprevistos: Dec;
  utilidad: Dec;
  iva_utilidad: Dec;
  total_aiu: Dec;
  total: Dec;
  num_lineas: number;
  lineas_sin_precio: number;
}
export interface ExplosionFila {
  insumo_id: number;
  insumo_codigo: string;
  insumo_descripcion: string;
  unidad_codigo: string | null;
  tipo: TipoInsumo;
  cantidad_total: Dec;
  precio_unitario: Dec;
  valor_total: Dec;
  participacion_pct: Dec;
}
export interface ExplosionPorTipo {
  tipo: TipoInsumo;
  valor_total: Dec;
  participacion_pct: Dec;
}
export interface ExplosionOut {
  version_id: number;
  filas: ExplosionFila[];
  por_tipo: ExplosionPorTipo[];
  total_insumos: Dec;
  valor_sin_desglose: Dec;
  total: Dec;
}

// ---------------------------------------------------------------------------
// 5. Control
// ---------------------------------------------------------------------------
export interface VersionRef {
  id: number;
  presupuesto_id: number;
  numero: number;
  nombre: string;
  tipo: TipoVersion;
  estado: EstadoVersion;
}
export interface ComparativoFila {
  clave_id: number;
  codigo: string;
  descripcion: string;
  unidad_codigo: string | null;
  tipo: TipoInsumo | null;
  capitulo_codigo: string | null;
  cantidad_base: Dec | null;
  cantidad_comparada: Dec | null;
  unitario_base: Dec | null;
  unitario_comparado: Dec | null;
  total_base: Dec;
  total_comparado: Dec;
  diferencia_cantidad: Dec | null;
  diferencia_unitaria: Dec | null;
  impacto: Dec;
  variacion_pct: Dec | null;
  estado: EstadoComparativo;
}
export interface ComparativoOut {
  version_base: VersionRef;
  version_comparada: VersionRef;
  nivel: NivelComparativo;
  filas: ComparativoFila[];
  totales: { total_base: Dec; total_comparado: Dec; impacto: Dec; variacion_pct: Dec | null };
}
export interface CompromisoOut extends Auditoria {
  id: number;
  presupuesto_id: number;
  tipo: TipoCompromiso;
  numero: string;
  fecha: ISODate;
  tercero: string;
  descripcion: string | null;
  estado: EstadoCompromiso;
  valor_total: Dec;
  num_lineas: number;
}
export interface CompromisoLineaOut {
  id: number;
  item_id: number;
  item_codigo: string;
  item_descripcion: string;
  insumo_id: number | null;
  insumo_codigo: string | null;
  descripcion: string | null;
  cantidad: Dec;
  valor_unitario: Dec;
  valor_total: Dec;
}
export interface CompromisoDetalleOut extends CompromisoOut {
  lineas: CompromisoLineaOut[];
  advertencias: string[];
}
export interface CompromisoLineaIn {
  item_id: number;
  insumo_id?: number | null;
  descripcion?: string | null;
  cantidad: Dec;
  valor_unitario: Dec;
}
export interface CompromisoCreate {
  presupuesto_id: number;
  tipo: TipoCompromiso;
  numero: string;
  fecha: ISODate;
  tercero: string;
  descripcion?: string | null;
  lineas: CompromisoLineaIn[];
}
export interface EjecucionOut {
  id: number;
  presupuesto_id: number;
  item_id: number;
  item_codigo: string;
  item_descripcion: string;
  periodo: Periodo;
  valor_ejecutado: Dec;
  cantidad_ejecutada: Dec | null;
  avance_fisico_pct: Dec;
  compromiso_id: number | null;
  observacion: string | null;
}
export interface EjecucionRegistro {
  item_id: number;
  valor_ejecutado: Dec;
  cantidad_ejecutada?: Dec | null;
  avance_fisico_pct: Dec;
  compromiso_id?: number | null;
  observacion?: string | null;
}
export interface EjecucionLote {
  presupuesto_id: number;
  periodo: Periodo;
  registros: EjecucionRegistro[];
}
export interface TableroFila {
  id: number | null;
  codigo: string;
  descripcion: string;
  presupuestado: Dec;
  comprometido: Dec;
  ejecutado: Dec;
  por_comprometer: Dec;
  saldo: Dec;
  pct_comprometido: Dec | null;
  pct_ejecutado: Dec | null;
  avance_fisico_pct: Dec | null;
}
export interface TableroOut {
  presupuesto_id: number;
  version: VersionRef;
  periodo_hasta: Periodo | null;
  capitulos: TableroFila[];
  totales: TableroFila;
  serie_mensual: { periodo: Periodo; ejecutado: Dec; ejecutado_acumulado: Dec }[];
}
export interface ImportResultado {
  aplicado: boolean;
  lineas_creadas: number;
  lineas_actualizadas: number;
  lineas_eliminadas: number;
  errores: { fila: number | null; columna: string | null; mensaje: string }[];
  advertencias: string[];
}

// ---------------------------------------------------------------------------
// 6. Infraestructura HTTP
// ---------------------------------------------------------------------------
const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";
const TOKEN_KEY = "erp_prodesa_token";
const USER_KEY = "erp_prodesa_user";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Sesión: token en memoria + sessionStorage (contrato §1). */
let memToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

function safeSession(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export const session = {
  getToken(): string | null {
    if (memToken) return memToken;
    memToken = safeSession()?.getItem(TOKEN_KEY) ?? null;
    return memToken;
  },
  getUser(): UsuarioOut | null {
    const raw = safeSession()?.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as UsuarioOut;
    } catch {
      return null;
    }
  },
  set(token: string, user: UsuarioOut): void {
    memToken = token;
    safeSession()?.setItem(TOKEN_KEY, token);
    safeSession()?.setItem(USER_KEY, JSON.stringify(user));
  },
  clear(): void {
    memToken = null;
    safeSession()?.removeItem(TOKEN_KEY);
    safeSession()?.removeItem(USER_KEY);
  },
  onUnauthorized(fn: (() => void) | null): void {
    unauthorizedHandler = fn;
  },
};

type QueryValue = string | number | boolean | null | undefined | number[];
type Query = Record<string, QueryValue>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      params.set(k, Array.isArray(v) ? v.join(",") : String(v));
    }
  }
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function toApiError(res: Response): Promise<ApiError> {
  let code = `HTTP_${res.status}`;
  let message = res.statusText || "Error de comunicación con el servidor";
  let details: unknown = null;
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string; details?: unknown } };
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? null;
    }
  } catch {
    /* cuerpo no JSON */
  }
  return new ApiError(res.status, code, message, details);
}

interface RequestOpts {
  query?: Query;
  body?: unknown;
  form?: FormData | URLSearchParams;
  auth?: boolean;
}

async function rawRequest(method: string, path: string, opts: RequestOpts = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = session.getToken();
  if (opts.auth !== false && token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), { method, headers, body });
  } catch {
    throw new ApiError(0, "NETWORK", "No se pudo contactar el servidor. ¿Está corriendo el backend en :8000?");
  }
  if (!res.ok) {
    const err = await toApiError(res);
    if (res.status === 401 && opts.auth !== false) {
      session.clear();
      unauthorizedHandler?.();
    }
    throw err;
  }
  return res;
}

async function request<T>(method: string, path: string, opts: RequestOpts = {}): Promise<T> {
  const res = await rawRequest(method, path, opts);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const get = <T>(path: string, query?: Query) => request<T>("GET", path, { query });
const post = <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, { body: body ?? {}, query });
const put = <T>(path: string, body?: unknown) => request<T>("PUT", path, { body: body ?? {} });
const del = (path: string) => request<void>("DELETE", path);

/** Descarga un archivo (Excel) respetando el nombre de Content-Disposition. */
async function download(path: string, query?: Query, fallbackName = "archivo.xlsx"): Promise<void> {
  const res = await rawRequest("GET", path, { query });
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------------------
// 7. Endpoints
// ---------------------------------------------------------------------------
const A = "/adpro";

export const api = {
  health: () => request<Health>("GET", "/health", { auth: false }),

  auth: {
    login: (username: string, password: string) =>
      request<TokenResponse>("POST", "/auth/login", { body: { username, password }, auth: false }),
    me: () => get<UsuarioOut>("/auth/me"),
  },

  auditoria: (q: { entidad?: string; entidad_id?: number; limit?: number; offset?: number } = {}) =>
    get<Page<AuditLogOut>>("/auditoria", q),

  maestros: {
    unidades: (q: { q?: string; activo?: boolean } = {}) => get<UnidadOut[]>(`${A}/maestros/unidades`, q),
    ciudades: (q: { q?: string; activo?: boolean } = {}) => get<CiudadOut[]>(`${A}/maestros/ciudades`, q),

    insumos: (q: { q?: string; tipo?: TipoInsumo | ""; activo?: boolean; unidad_id?: number; limit?: number; offset?: number } = {}) =>
      get<Page<InsumoOut>>(`${A}/maestros/insumos`, q),
    insumo: (id: number) => get<InsumoOut>(`${A}/maestros/insumos/${id}`),
    crearInsumo: (body: InsumoCreate) => post<InsumoOut>(`${A}/maestros/insumos`, body),
    actualizarInsumo: (id: number, body: InsumoUpdate) => put<InsumoOut>(`${A}/maestros/insumos/${id}`, body),
    preciosInsumo: (id: number, ciudad_id?: number) =>
      get<PrecioHistoricoOut[]>(`${A}/maestros/insumos/${id}/precios`, { ciudad_id }),

    listasPrecios: (q: { ciudad_id?: number; activo?: boolean } = {}) =>
      get<ListaPreciosOut[]>(`${A}/maestros/listas-precios`, q),
    preciosLista: (id: number, q: { q?: string; tipo?: TipoInsumo | ""; limit?: number; offset?: number } = {}) =>
      get<Page<PrecioOut>>(`${A}/maestros/listas-precios/${id}/precios`, q),
    preciosVigentes: (ciudad_id: number, fecha: ISODate, insumo_ids: number[]) =>
      get<PrecioVigenteOut[]>(`${A}/maestros/precios-vigentes`, { ciudad_id, fecha, insumo_ids }),

    proyectos: (q: { q?: string; estado?: EstadoProyecto | ""; tipo?: TipoProyecto | ""; ciudad_id?: number } = {}) =>
      get<ProyectoOut[]>(`${A}/maestros/proyectos`, q),
    proyecto: (id: number) => get<ProyectoDetalleOut>(`${A}/maestros/proyectos/${id}`),

    edt: (q: { nivel?: NivelEdt; parent_id?: number; q?: string; activo?: boolean; limit?: number; offset?: number } = {}) =>
      get<Page<EdtNodoOut>>(`${A}/maestros/edt`, q),
    edtArbol: (q: { capitulo_id?: number; hasta_nivel?: NivelEdt; activo?: boolean } = {}) =>
      get<EdtArbolNodo[]>(`${A}/maestros/edt/arbol`, q),
    edtNodo: (id: number) => get<EdtNodoDetalleOut>(`${A}/maestros/edt/${id}`),
  },

  apu: {
    lista: (q: { q?: string; capitulo_id?: number; activo?: boolean; limit?: number; offset?: number } = {}) =>
      get<Page<ApuOut>>(`${A}/apu/apus`, q),
    detalle: (id: number) => get<ApuDetalleOut>(`${A}/apu/apus/${id}`),
    porItem: (itemId: number) => get<ApuDetalleOut>(`${A}/apu/apus/por-item/${itemId}`),
    valorizacion: (id: number, q: { ciudad_id?: number; fecha?: ISODate } = {}) =>
      get<ValorizacionOut>(`${A}/apu/apus/${id}/valorizacion`, q),
    reemplazarInsumos: (id: number, insumos: ApuInsumoIn[]) =>
      put<ApuDetalleOut>(`${A}/apu/apus/${id}/insumos`, { insumos }),
  },

  presupuestos: {
    lista: (q: { proyecto_id?: number; q?: string } = {}) => get<PresupuestoOut[]>(`${A}/presupuestos`, q),
    crear: (body: PresupuestoCreate) => post<PresupuestoDetalleOut>(`${A}/presupuestos`, body),
    detalle: (id: number) => get<PresupuestoDetalleOut>(`${A}/presupuestos/${id}`),

    crearVersion: (presupuestoId: number, body: VersionCreate) =>
      post<VersionOut>(`${A}/presupuestos/${presupuestoId}/versiones`, body),
    version: (vid: number) => get<VersionOut>(`${A}/presupuestos/versiones/${vid}`),
    actualizarVersion: (vid: number, body: VersionUpdate) => put<VersionOut>(`${A}/presupuestos/versiones/${vid}`, body),
    eliminarVersion: (vid: number) => del(`${A}/presupuestos/versiones/${vid}`),
    aprobar: (vid: number, observacion?: string) =>
      post<VersionOut>(`${A}/presupuestos/versiones/${vid}/aprobar`, { observacion }),
    cerrar: (vid: number, observacion?: string) =>
      post<VersionOut>(`${A}/presupuestos/versiones/${vid}/cerrar`, { observacion }),
    copiar: (vid: number, body: VersionCopy) => post<VersionOut>(`${A}/presupuestos/versiones/${vid}/copiar`, body),
    recalcular: (vid: number) => post<RecalculoOut>(`${A}/presupuestos/versiones/${vid}/recalcular`, {}),

    lineas: (vid: number, q: { capitulo_id?: number; q?: string } = {}) =>
      get<LineaOut[]>(`${A}/presupuestos/versiones/${vid}/lineas`, q),
    crearLinea: (vid: number, body: LineaCreate) => post<LineaOut>(`${A}/presupuestos/versiones/${vid}/lineas`, body),
    actualizarLinea: (vid: number, lid: number, body: LineaUpdate) =>
      put<LineaOut>(`${A}/presupuestos/versiones/${vid}/lineas/${lid}`, body),
    eliminarLinea: (vid: number, lid: number) => del(`${A}/presupuestos/versiones/${vid}/lineas/${lid}`),
    insumosLinea: (vid: number, lid: number) =>
      get<LineaInsumoOut[]>(`${A}/presupuestos/versiones/${vid}/lineas/${lid}/insumos`),

    resumen: (vid: number) => get<ResumenOut>(`${A}/presupuestos/versiones/${vid}/resumen`),
    explosion: (vid: number, tipo?: TipoInsumo | "") =>
      get<ExplosionOut>(`${A}/presupuestos/versiones/${vid}/explosion`, { tipo }),
  },

  control: {
    comparativo: (version_base_id: number, version_comparada_id: number, nivel: NivelComparativo = "item") =>
      get<ComparativoOut>(`${A}/control/comparativo`, { version_base_id, version_comparada_id, nivel }),

    compromisos: (q: { presupuesto_id?: number; estado?: EstadoCompromiso | ""; tipo?: TipoCompromiso | ""; item_id?: number; q?: string; limit?: number; offset?: number } = {}) =>
      get<Page<CompromisoOut>>(`${A}/control/compromisos`, q),
    compromiso: (id: number) => get<CompromisoDetalleOut>(`${A}/control/compromisos/${id}`),
    crearCompromiso: (body: CompromisoCreate) => post<CompromisoDetalleOut>(`${A}/control/compromisos`, body),
    anularCompromiso: (id: number, motivo: string) =>
      post<CompromisoDetalleOut>(`${A}/control/compromisos/${id}/anular`, { motivo }),
    liquidarCompromiso: (id: number) => post<CompromisoDetalleOut>(`${A}/control/compromisos/${id}/liquidar`, {}),

    ejecucion: (q: { presupuesto_id: number; periodo?: Periodo; item_id?: number; desde?: Periodo; hasta?: Periodo }) =>
      get<EjecucionOut[]>(`${A}/control/ejecucion`, q),
    periodos: (presupuesto_id: number) => get<Periodo[]>(`${A}/control/ejecucion/periodos`, { presupuesto_id }),
    guardarEjecucion: (body: EjecucionLote) =>
      put<{ creados: number; actualizados: number; advertencias: string[] }>(`${A}/control/ejecucion`, body),
    eliminarEjecucion: (id: number) => del(`${A}/control/ejecucion/${id}`),

    tablero: (q: { presupuesto_id: number; version_id?: number; periodo_hasta?: Periodo }) =>
      get<TableroOut>(`${A}/control/tablero`, q),
    tableroItems: (q: { presupuesto_id: number; version_id?: number; capitulo_id?: number; periodo_hasta?: Periodo }) =>
      get<TableroFila[]>(`${A}/control/tablero/items`, q),

    excel: {
      plantilla: () => download(`${A}/control/excel/plantilla-presupuesto`, undefined, "plantilla_presupuesto.xlsx"),
      importar: (versionId: number, file: File, modo: "agregar" | "reemplazar" = "agregar") => {
        const form = new FormData();
        form.append("file", file);
        return request<ImportResultado>("POST", `${A}/control/excel/presupuesto/${versionId}/importar`, {
          form,
          query: { modo },
        });
      },
      presupuesto: (versionId: number) =>
        download(`${A}/control/excel/presupuesto/${versionId}`, undefined, `presupuesto_v${versionId}.xlsx`),
      explosion: (versionId: number) =>
        download(`${A}/control/excel/explosion/${versionId}`, undefined, `explosion_v${versionId}.xlsx`),
      comparativo: (version_base_id: number, version_comparada_id: number, nivel: NivelComparativo = "item") =>
        download(`${A}/control/excel/comparativo`, { version_base_id, version_comparada_id, nivel }, "comparativo.xlsx"),
    },
  },
};

/** Permisos por rol (contrato §0.3). */
export const permisos = {
  maestros: (r?: Rol) => r === "admin" || r === "presupuesto",
  presupuesto: (r?: Rol) => r === "admin" || r === "presupuesto",
  aprobacion: (r?: Rol) => r === "admin",
  control: (r?: Rol) => r === "admin" || r === "presupuesto" || r === "obra",
};
