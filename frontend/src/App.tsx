import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router'
import { Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, BarChart3, Building2, CalendarDays, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, FileSpreadsheet, LayoutDashboard, LoaderCircle, Menu, Package, Plus, RefreshCw, Settings2, Sparkles, Upload, Wallet, X, AlertCircle, TrendingUp, Layers3 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, categoryLabel, dateLabel, decimal, downloadPdf, kindLabel, metricReason, money, periodLabel, productLabel, query } from './lib/api'
import type { Business, Demo, Expenses, ImportConfirmation, ImportKind, ImportPreview, ImportRead, Metric, Period, Products, Revenue, Summary } from './lib/api'
import type { Analysis, Insight, Insights, InsightType, Severity } from './lib/api'
import type { AdvisorReply, AdvisorStatus } from './lib/api'

type Workspace = {
  businesses: Business[]; business: Business | null; selectBusiness: (id: string) => void
  reloadBusinesses: (select?: string) => Promise<void>; period: Period | null
  effectivePeriod: Period | null; setPeriod: (period: Period | null) => void
  setEffectivePeriod: (period: Period) => void; revision: number; refresh: () => void
}
const WorkspaceContext = createContext<Workspace | null>(null)
function useWorkspace() { return useContext(WorkspaceContext)! }
const demoId = '99d4acb9-bdac-531b-9e03-e29a32d92a85'
const colors = ['#088b7a', '#8bc9bd', '#bec7dc', '#e6b76f', '#b29cce', '#728ea2']
function rememberedBusiness() { try { return localStorage.getItem('profitleak.business') } catch { return null } }

function useRemote<T>(path: string | null) {
  const { revision } = useWorkspace()
  const [state, setState] = useState<{ data: T | null; error: string; loading: boolean }>({ data: null, error: '', loading: true })
  useEffect(() => {
    const controller = new AbortController()
    setState({ data: null, error: '', loading: !!path })
    if (path) api<T>(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ data, error: '', loading: false })
    }).catch(error => {
      if (!controller.signal.aborted) setState({ data: null, error: error.message, loading: false })
    })
    return () => controller.abort()
  }, [path, revision])
  return state
}

function Button({ children, className = '', ...props }: React.ComponentProps<'button'>) {
  return <button className={`button ${className}`} {...props}>{children}</button>
}
function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-box" role="alert"><AlertCircle size={20} /><div><strong>Не удалось выполнить запрос</strong><p>{message}</p></div>{retry && <Button onClick={retry}>Повторить</Button>}</div>
}
function Loading({ label = 'Загружаем данные…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={22} />{label}</div>
}
function Empty({ title, text, children }: { title: string; text: string; children?: ReactNode }) {
  return <div className="empty"><div className="empty-icon"><BarChart3 size={28} /></div><h3>{title}</h3><p>{text}</p>{children}</div>
}
function MetricValue({ metric, percent = false }: { metric: Metric; percent?: boolean }) {
  return <span title={metric.reason ? metricReason[metric.reason] : undefined}>{metric.value == null ? '—' : percent ? `${decimal(metric.value)}%` : money(metric.value)}</span>
}

export default function App() {
  const [businesses, setBusinesses] = useState<Business[]>([])
  const [businessId, setBusinessId] = useState('')
  const [boot, setBoot] = useState(true)
  const [error, setError] = useState('')
  const [period, setPeriod] = useState<Period | null>(null)
  const [effectivePeriod, setEffectivePeriod] = useState<Period | null>(null)
  const [revision, setRevision] = useState(0)
  const selectBusiness = useCallback((id: string) => {
    setBusinessId(id); setPeriod(null); setEffectivePeriod(null)
    try { localStorage.setItem('profitleak.business', id) } catch { /* Storage is optional. */ }
  }, [])
  const reloadBusinesses = useCallback(async (select?: string) => {
    const result = await api<Business[]>('/businesses?limit=100')
    setBusinesses(result)
    const remembered = select || rememberedBusiness()
    const chosen = result.find(b => b.id === remembered) || result.find(b => b.id === demoId) || result[0]
    if (chosen) selectBusiness(chosen.id)
  }, [selectBusiness])
  const bootstrap = useCallback(async () => {
    setBoot(true); setError('')
    try { await reloadBusinesses() } catch (e) { setError((e as Error).message) }
    finally { setBoot(false) }
  }, [reloadBusinesses])
  useEffect(() => { void bootstrap() }, [bootstrap])
  const refresh = useCallback(() => setRevision(v => v + 1), [])
  const value = useMemo<Workspace>(() => ({ businesses, business: businesses.find(b => b.id === businessId) || null, selectBusiness, reloadBusinesses, period, effectivePeriod, setPeriod, setEffectivePeriod, revision, refresh }), [businesses, businessId, selectBusiness, reloadBusinesses, period, effectivePeriod, revision, refresh])
  return <WorkspaceContext.Provider value={value}><Shell>{boot ? <Loading label="Открываем рабочее пространство…" /> : error ? <ErrorBox message={error} retry={bootstrap} /> : <Routes>
    <Route path="/" element={value.business ? <Dashboard /> : <Welcome />} />
    <Route path="/products" element={value.business ? <ProductsPage /> : <Welcome />} />
    <Route path="/imports" element={value.business ? <ImportPage key={businessId} /> : <Welcome />} />
    <Route path="/insights" element={value.business ? <DetectorPage /> : <Welcome />} />
    <Route path="/insights/:insightId" element={value.business ? <InsightPage /> : <Welcome />} />
    <Route path="/advisor" element={value.business ? <AdvisorPage /> : <Welcome />} />
    <Route path="/settings" element={<SettingsPage />} />
    <Route path="*" element={<Empty title="Страница не найдена" text="Вернитесь к обзору вашего бизнеса."><Link className="button primary" to="/">К обзору</Link></Empty>} />
  </Routes>}</Shell></WorkspaceContext.Provider>
}

function Shell({ children }: { children: ReactNode }) {
  const { business, businesses, selectBusiness } = useWorkspace()
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const health = useRemote<{ status: string; database: string }>('/health')
  useEffect(() => { setMobileOpen(false); window.scrollTo({ top: 0, left: 0 }) }, [location.pathname])
  useEffect(() => {
    if (!mobileOpen) return
    const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobileOpen(false) }
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [mobileOpen])
  const links: { to: string; label: string; icon: LucideIcon }[] = [
    { to: '/', label: 'Обзор', icon: LayoutDashboard }, { to: '/products', label: 'Товары', icon: Package },
    { to: '/insights', label: 'Детектор проблем', icon: Activity },
    { to: '/advisor', label: 'AI-советник', icon: Sparkles },
    { to: '/imports', label: 'Импорт данных', icon: ArrowDownToLine }, { to: '/settings', label: 'Мой бизнес', icon: Settings2 },
  ]
  return <div className="app-shell">
    {mobileOpen && <button className="sidebar-scrim" aria-label="Закрыть меню" onClick={() => setMobileOpen(false)} />}
    <aside className={`sidebar ${mobileOpen ? 'is-open' : ''}`}>
      <Link to="/" className="brand"><span className="brand-icon"><BarChart3 size={24} strokeWidth={2.3} /></span><span>ProfitLeak<span className="brand-ai">AI</span></span></Link>
      <div className="workspace-switch"><span className="workspace-avatar"><Building2 size={20} /></span><div><small>РАБОЧЕЕ ПРОСТРАНСТВО</small><strong>{business?.name || 'Ваш бизнес'}</strong></div></div>
      <p className="nav-label">УПРАВЛЕНИЕ БИЗНЕСОМ</p>
      <nav aria-label="Главное меню">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={19} /><span>{label}</span>{to === '/' && <span className="nav-dot" />}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><span className="note-icon"><Layers3 size={21} /></span><h3>Хорошие решения<br />начинаются с данных</h3><p>Загрузите продажи и расходы, чтобы увидеть полную картину.</p><Link to="/imports">Загрузить данные <ArrowUpRight size={16} /></Link></div>
        <div className="connection"><span className={`status-dot ${health.data?.database === 'ok' ? 'online' : ''}`} /><span>{health.loading ? 'Проверяем подключение' : health.data?.database === 'ok' ? 'Сервер подключён' : 'Сервер недоступен'}</span></div>
        <div className="sidebar-footer">ProfitLeak AI <span>Локальная версия</span></div>
      </div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-left"><Button className="icon-button mobile-menu" aria-label="Открыть меню" aria-expanded={mobileOpen} onClick={() => setMobileOpen(v => !v)}><Menu size={22} /></Button><span className="breadcrumb">Рабочее пространство <ChevronRight size={13} /> <strong>{links.find(l => l.to === location.pathname)?.label || 'Обзор'}</strong></span></div><div className="topbar-right">{business?.id === demoId && <span className="demo-label"><span /> Демо-данные</span>}<div className="business-select"><Building2 size={16} /><select aria-label="Выбрать бизнес" value={business?.id || ''} onChange={e => selectBusiness(e.target.value)} disabled={!businesses.length}>{!businesses.length && <option value="">Ваш бизнес</option>}{businesses.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select><ChevronDown size={14} /></div><span className="profile-avatar" title="Рабочее пространство">{business?.name.slice(0, 1).toUpperCase() || 'P'}</span></div></header>
      <main id="main-content" className="main-content" key={business?.id || 'empty'}>{children}</main><footer className="content-footer"><span>ProfitLeak AI · Ясность в каждом тенге</span><span>Валюта: KZT · Часовой пояс: Алматы</span></footer>
    </div>
  </div>
}

function PageHeading({ eyebrow, title, description, dates = false, reportPeriod }: { eyebrow: string; title: string; description: string; dates?: boolean; reportPeriod?: Period }) {
  const { refresh } = useWorkspace()
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div><div className="heading-actions">{dates && <DateFilter />}{(dates || reportPeriod) && <PdfButton selected={reportPeriod} />}<Button className="icon-button" onClick={refresh} aria-label="Обновить данные" title="Обновить данные"><RefreshCw size={17} /></Button></div></div>
}

function PdfButton({ selected }: { selected?: Period }) {
  const { business, period } = useWorkspace()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function save() {
    setBusy(true); setError('')
    try { await downloadPdf(business!.id, selected || period) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="pdf-action"><Button onClick={() => void save()} disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <ArrowDownToLine size={16} />}{busy ? 'Готовим PDF…' : 'Скачать PDF'}</Button>{error && <span className="field-error" role="alert">{error}</span>}</div>
}

function DateFilter() {
  const { period, effectivePeriod, setPeriod } = useWorkspace()
  const shown = period || effectivePeriod
  const [open, setOpen] = useState(false)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [error, setError] = useState('')
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    function close(e: PointerEvent) { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    function escape(e: KeyboardEvent) { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', close); document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', escape) }
  }, [open])
  function toggle() { setStart(shown?.date_from || ''); setEnd(shown?.date_to || ''); setError(''); setOpen(!open) }
  function apply(e: FormEvent) {
    e.preventDefault()
    const days = (Date.parse(end) - Date.parse(start)) / 86400000 + 1
    if (!start || !end || !Number.isFinite(days) || days < 1 || days > 366) { setError('Выберите период от 1 до 366 дней.'); return }
    setPeriod({ date_from: start, date_to: end }); setOpen(false)
  }
  function preset(days: number) {
    if (!effectivePeriod) { setPeriod(null); setOpen(false); return }
    const last = effectivePeriod.date_to
    const first = new Date(`${last}T12:00:00Z`); first.setUTCDate(first.getUTCDate() - days + 1)
    setPeriod({ date_from: first.toISOString().slice(0, 10), date_to: last }); setOpen(false)
  }
  return <div className="date-filter" ref={box}><Button aria-expanded={open} onClick={toggle}><CalendarDays size={17} />{periodLabel(shown)}<ChevronDown size={14} /></Button>{open && <div className="date-popover"><h3>Период анализа</h3><div className="period-presets">{[7, 30, 90].map(days => <Button key={days} onClick={() => preset(days)} disabled={!effectivePeriod}>{days} дней</Button>)}</div><small>До последней даты в загруженных данных</small><form onSubmit={apply}><label>Начало<input type="date" value={start} onChange={e => setStart(e.target.value)} required /></label><label>Конец<input type="date" value={end} onChange={e => setEnd(e.target.value)} required /></label>{error && <p className="field-error" role="alert">{error}</p>}<div className="popover-actions"><Button type="button" onClick={() => { setPeriod(null); setOpen(false) }}>Сбросить</Button><Button className="primary">Применить</Button></div></form></div>}</div>
}

type DashboardData = { summary: Summary; revenue: Revenue; expenses: Expenses; products: Products }
function Dashboard() {
  const { business, period, setEffectivePeriod, revision, refresh } = useWorkspace()
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const params = query(business!.id, period)
  useEffect(() => {
    const controller = new AbortController(); const init = { signal: controller.signal }
    setLoading(true); setError(''); setData(null)
    // Resolve the default period once, so all panels use the same dates.
    api<Summary>(`/dashboard/summary?${params}`, init).then(async summary => {
      const resolved = query(business!.id, summary.period)
      const [revenue, expenses, products] = await Promise.all([
        api<Revenue>(`/analytics/revenue?${resolved}`, init), api<Expenses>(`/analytics/expenses?${resolved}`, init), api<Products>(`/analytics/products?${resolved}&limit=5`, init),
      ])
      if (!controller.signal.aborted) { setData({ summary, revenue, expenses, products }); if (!period) setEffectivePeriod(summary.period); setLoading(false) }
    }).catch(e => { if (!controller.signal.aborted) { setError(e.message); setLoading(false) } })
    return () => controller.abort()
  }, [params, business, period, revision, setEffectivePeriod])
  return <><PageHeading eyebrow="ВАШ БИЗНЕС В ЦИФРАХ" title="Финансы под контролем" description="Всё, что нужно знать о доходах, расходах и прибыли." dates />
    {loading ? <DashboardSkeleton /> : error ? <ErrorBox message={error} retry={refresh} /> : data && <>
      <div className="period-note"><span className="small-dot" />По подтверждённым данным за {periodLabel(data.summary.period)}<Link to="/imports"><Upload size={14} /> Импортировать</Link></div>
      <div className="kpi-grid"><Kpi label="Выручка" metric={data.summary.revenue} icon={Wallet} note={`${decimal(String(data.summary.sales_rows))} записей о продажах`} /><Kpi label="Операционная прибыль" metric={data.summary.operating_profit} icon={TrendingUp} note="После себестоимости и расходов" featured /><Kpi label="Операционные расходы" metric={data.summary.operating_expenses} icon={ArrowUpRight} note={`${decimal(String(data.summary.expense_rows))} записей о расходах`} /><Kpi label="Валовая маржа" metric={data.summary.gross_margin_percent} icon={Activity} note="Доля валовой прибыли в выручке" percent /></div>
      {!!data.summary.missing_cost_rows && <div className="notice"><CircleHelp size={18} /><span>В {data.summary.missing_cost_rows} записях не указана себестоимость. Добавьте её в продажи для расчёта прибыли.</span></div>}
      <div className="chart-grid"><RevenueChart data={data.revenue} total={data.summary.revenue} /><ExpenseChart data={data.expenses} /></div>
      <section className="panel product-panel"><div className="panel-heading"><div><h2>Прибыльность товаров</h2><p>Какие товары приносят бизнесу больше всего</p></div><Link className="text-link" to="/products">Все товары <ArrowRight size={16} /></Link></div><ProductTable data={data.products} compact /><div className="panel-footnote"><CircleHelp size={14} /> Валовая прибыль = выручка − себестоимость. Операционные расходы здесь не учитываются.</div></section>
      <RecentInsights period={data.summary.period} />
      <div className="data-note"><CheckCircle2 size={15} /><span>Расчёты по загруженным данным. Отсутствие записей не означает отсутствие операций.</span><span className="currency-note">₸ Казахстанский тенге</span></div>
    </>}
  </>
}
function DashboardSkeleton() { return <div aria-label="Загрузка обзора" aria-busy="true"><div className="kpi-grid">{[1, 2, 3, 4].map(v => <div key={v} className="skeleton skeleton-card" />)}</div><div className="chart-grid"><div className="skeleton skeleton-chart" /><div className="skeleton skeleton-chart" /></div><Loading /></div> }
function Kpi({ label, metric, icon: Icon, note, featured = false, percent = false }: { label: string; metric: Metric; icon: LucideIcon; note: string; featured?: boolean; percent?: boolean }) {
  return <section className={`kpi-card ${featured ? 'featured' : ''}`}><div className="kpi-top"><h2>{label}</h2><span className="kpi-icon"><Icon size={19} /></span></div><div className={`kpi-value ${metric.value == null ? 'unavailable' : ''}`}><MetricValue metric={metric} percent={percent} /></div><div className="kpi-note">{metric.reason ? <><CircleHelp size={13} />{metricReason[metric.reason]}</> : <><span className="small-dot" />{note}</>}</div></section>
}

function RevenueChart({ data, total }: { data: Revenue; total: Metric }) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const points = data.points.map(p => ({ ...p, value: p.revenue.value == null ? null : Number(p.revenue.value) }))
  return <section className="panel revenue-panel"><div className="panel-heading"><div><h2>Динамика выручки</h2><p>Каждый день вашего бизнеса</p></div><div className="segmented" aria-label="Представление выручки"><button className={view === 'chart' ? 'selected' : ''} aria-pressed={view === 'chart'} onClick={() => setView('chart')}>График</button><button className={view === 'table' ? 'selected' : ''} aria-pressed={view === 'table'} onClick={() => setView('table')}>Таблица</button></div></div><div className="chart-summary"><strong><MetricValue metric={total} /></strong><span><i /> Выручка за период</span></div>
    {!data.points.some(p => p.revenue.value !== null) ? <Empty title="Здесь появится график" text="Загрузите продажи за выбранный период." /> : view === 'table' ? <div className="daily-table scroll-table"><table><thead><tr><th>Дата</th><th className="numeric">Записей</th><th className="numeric">Выручка</th></tr></thead><tbody>{data.points.map(p => <tr key={p.date}><td>{dateLabel(p.date, true)}</td><td className="numeric">{p.sales_rows}</td><td className="numeric"><MetricValue metric={p.revenue} /></td></tr>)}</tbody></table></div> : <div className="revenue-chart" role="img" aria-label="Дневная выручка. Точные значения доступны во вкладке Таблица."><ResponsiveContainer width="100%" height="100%"><AreaChart data={points} margin={{ top: 15, right: 15, left: 0, bottom: 0 }}><defs><linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#159682" stopOpacity={0.17} /><stop offset="100%" stopColor="#159682" stopOpacity={0.01} /></linearGradient></defs><CartesianGrid stroke="#edf0f4" vertical={false} strokeDasharray="4 4" /><XAxis dataKey="date" tickFormatter={d => dateLabel(d)} tickLine={false} axisLine={false} minTickGap={45} tick={{ fill: '#8993a4', fontSize: 11 }} dy={12} /><YAxis tickFormatter={v => `${new Intl.NumberFormat('ru-RU', { notation: 'compact', maximumFractionDigits: 1 }).format(v)}`} tickLine={false} axisLine={false} width={57} tick={{ fill: '#8993a4', fontSize: 11 }} /><Tooltip content={({ active, payload }) => active && payload?.[0] ? <div className="chart-tooltip"><small>{dateLabel(payload[0].payload.date, true)}</small><strong>{money(payload[0].payload.revenue.value)}</strong></div> : null} /><Area type="linear" dataKey="value" stroke="#088b7a" strokeWidth={2.5} fill="url(#revenueFill)" connectNulls={false} isAnimationActive={false} activeDot={{ r: 5, fill: '#088b7a', stroke: '#fff', strokeWidth: 3 }} /></AreaChart></ResponsiveContainer></div>}
  </section>
}
function ExpenseChart({ data }: { data: Expenses }) {
  const positive = data.categories.every(c => Number(c.amount) >= 0) && data.categories.some(c => Number(c.amount) > 0)
  return <section className="panel expense-panel"><div className="panel-heading"><div><h2>Структура расходов</h2><p>Куда уходят деньги</p></div><span className="subtle-icon"><Wallet size={18} /></span></div>{!data.categories.length ? <Empty title="Нет расходов" text="Загрузите расходы, чтобы увидеть их структуру." /> : <>{positive && <div className="donut-wrap" role="img" aria-label="Расходы по категориям. Значения перечислены под диаграммой."><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data.categories.map(c => ({ name: categoryLabel[c.category] || c.category, value: Number(c.amount), raw: c.amount }))} dataKey="value" innerRadius="72%" outerRadius="92%" paddingAngle={3} cornerRadius={5} stroke="none" isAnimationActive={false}>{data.categories.map((c, i) => <Cell key={c.category} fill={colors[i % colors.length]} />)}</Pie><Tooltip content={({ active, payload }) => active && payload?.[0] ? <div className="chart-tooltip"><small>{payload[0].payload.name}</small><strong>{money(payload[0].payload.raw)}</strong></div> : null} /></PieChart></ResponsiveContainer><div className="donut-label"><small>Всего расходов</small><strong>{money(data.total.value)}</strong><span>за выбранный период</span></div></div>}<div className="expense-legend">{data.categories.map((c, i) => <div key={c.category}><span className="legend-dot" style={{ background: colors[i % colors.length] }} /><span>{categoryLabel[c.category] || c.category}</span><strong>{money(c.amount)}</strong></div>)}</div>{!positive && <p className="panel-footnote">Суммы включают возвраты. Диаграмма доступна для положительных расходов.</p>}</>}</section>
}

function ProductTable({ data, compact = false }: { data: Products; compact?: boolean }) {
  if (!data.items.length) return <Empty title="Товары пока не появились" text="Загрузите продажи за этот период, чтобы сравнить прибыльность товаров." />
  return <div className="scroll-table"><table className="product-table"><thead><tr><th>Товар</th>{!compact && <th className="numeric">Количество</th>}<th className="numeric">Выручка</th><th className="numeric">Себестоимость</th><th className="numeric">Валовая прибыль</th><th className="numeric">Маржа</th></tr></thead><tbody>{data.items.map((p, i) => <tr key={p.product_id}><td><div className="product-name"><span className={`product-avatar tone-${i % 3}`}><Package size={18} /></span><div><strong>{productLabel[p.name] || p.name}</strong><small>{p.external_id}</small></div></div></td>{!compact && <td className="numeric">{decimal(p.net_quantity)}</td>}<td className="numeric"><MetricValue metric={p.revenue} /></td><td className="numeric muted"><MetricValue metric={p.cogs} /></td><td className="numeric profit-cell"><MetricValue metric={p.gross_profit} /></td><td className="numeric"><span className={`margin-badge ${p.gross_margin_percent.value == null ? 'neutral' : Number(p.gross_margin_percent.value) < 30 ? 'low' : ''}`}><MetricValue metric={p.gross_margin_percent} percent /></span></td></tr>)}</tbody></table></div>
}
function ProductsPage() {
  const { business, period, setEffectivePeriod, refresh } = useWorkspace()
  const [offset, setOffset] = useState(0)
  const params = query(business!.id, period)
  useEffect(() => { setOffset(0) }, [params])
  const result = useRemote<Products>(`/analytics/products?${params}&limit=10&offset=${offset}`)
  useEffect(() => { if (result.data && !period) setEffectivePeriod(result.data.period) }, [result.data, period, setEffectivePeriod])
  return <><PageHeading eyebrow="АНАЛИТИКА ТОВАРОВ" title="Что приносит прибыль" description="Выручка, себестоимость и маржа каждого товара." dates />{result.loading ? <Loading /> : result.error ? <ErrorBox message={result.error} retry={refresh} /> : result.data && <section className="panel"><div className="panel-heading"><div><h2>Все товары <span className="count-badge">{result.data.total}</span></h2><p>По убыванию валовой прибыли · {periodLabel(result.data.period)}</p></div><Link className="button" to="/imports"><Upload size={16} />Загрузить продажи</Link></div><ProductTable data={result.data} /><div className="pagination"><span>{result.data.total ? `${offset + 1}–${offset + result.data.items.length} из ${result.data.total} товаров` : 'Нет товаров'}</span><div><Button className="icon-button" disabled={offset === 0} onClick={() => setOffset(v => Math.max(0, v - 10))} aria-label="Предыдущая страница"><ChevronLeft size={17} /></Button><Button className="icon-button" disabled={offset + 10 >= result.data.total} onClick={() => setOffset(v => v + 10)} aria-label="Следующая страница"><ChevronRight size={17} /></Button></div></div></section>}<div className="notice"><CircleHelp size={18} /><span>Маржа рассчитана до операционных расходов. Если себестоимость не указана, прибыль и маржа остаются без значения.</span></div></>
}

function DemoButton({ className = 'primary' }: { className?: string }) {
  const { reloadBusinesses, refresh } = useWorkspace()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function load() {
    setBusy(true); setError('')
    try { const result = await api<Demo>('/demo/load', { method: 'POST' }); await reloadBusinesses(result.business.id); refresh(); navigate('/') }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <div><Button className={className} onClick={load} disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}{busy ? 'Загружаем демо…' : 'Открыть демо-бизнес'}</Button>{error && <p className="field-error" role="alert">{error}</p>}</div>
}
function Welcome() {
  return <><PageHeading eyebrow="ДОБРО ПОЖАЛОВАТЬ" title="Познакомьтесь с вашими финансами" description="Создайте бизнес и загрузите данные. Всё остальное мы посчитаем." /><section className="welcome panel"><div className="welcome-art"><BarChart3 size={54} /><span className="welcome-orbit" /><span className="welcome-orbit second" /></div><span className="eyebrow">ПЕРВЫЙ ШАГ К ЯСНОСТИ</span><h2>Ваш бизнес. Вся картина.</h2><p>Продажи, расходы и прибыль в одном рабочем пространстве. Начните со своего бизнеса или изучите пример кафе в Таразе.</p><div className="welcome-actions"><Link className="button primary" to="/settings"><Plus size={17} />Создать бизнес</Link><DemoButton className="" /></div><span className="welcome-caption">Демо содержит 90 дней синтетических данных</span></section></>
}

const columnLabel: Record<string, string> = { date: 'Дата', product_id: 'ID товара', product_name: 'Товар', quantity: 'Количество', unit_price: 'Цена', unit_cost: 'Себестоимость', record_type: 'Тип записи', category: 'Категория', description: 'Описание', amount: 'Сумма', name: 'Название' }
function importTypeHint(preview: ImportPreview | null): ImportKind | null {
  if (!preview) return null
  const unknown = new Set(preview.errors.filter(error => error.row === 1 && error.message === 'Неизвестная колонка.').map(error => error.field))
  const candidate = unknown.has('quantity') && unknown.has('unit_price') ? 'sales'
    : unknown.has('description') && unknown.has('amount') ? 'expenses'
    : unknown.has('name') ? 'products' : null
  return candidate !== preview.kind ? candidate : null
}
function ImportPage() {
  const { business, refresh, revision } = useWorkspace()
  const [kind, setKind] = useState<ImportKind>('sales')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [busy, setBusy] = useState<'preview' | 'confirm' | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [dragging, setDragging] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [historyLimit, setHistoryLimit] = useState(20)
  const fileInput = useRef<HTMLInputElement>(null)
  const request = useRef<AbortController | null>(null)
  const history = useRemote<ImportRead[]>(`/imports?business_id=${business!.id}&limit=${historyLimit}`)
  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [])
  useEffect(() => { setHistoryLimit(20) }, [revision])
  function reset(keepFile = false) { request.current?.abort(); request.current = null; setPreview(null); setBusy(null); setError(''); setSuccess(''); if (!keepFile) { setFile(null); if (fileInput.current) fileInput.current.value = '' } }
  function changeKind(next: ImportKind) { reset(true); setKind(next) }
  function choose(candidate: File | undefined) {
    reset(); if (!candidate) return
    if (!/\.(csv|xlsx)$/i.test(candidate.name)) { setError('Выберите файл CSV или XLSX.'); return }
    if (candidate.size > 10 * 1024 * 1024) { setError('Размер файла не должен превышать 10 МБ.'); return }
    setFile(candidate)
  }
  async function send(action: 'preview' | 'confirm') {
    if (!file || (action === 'confirm' && !preview?.preview_token)) return
    request.current?.abort(); const controller = new AbortController(); request.current = controller
    setBusy(action); setError(''); setSuccess('')
    const form = new FormData(); form.set('business_id', business!.id); form.set('kind', kind); form.set('file', file)
    if (action === 'confirm') form.set('preview_token', preview!.preview_token!)
    try {
      if (action === 'preview') {
        const result = await api<ImportPreview>('/imports/preview', { method: 'POST', body: form, signal: controller.signal })
        if (!controller.signal.aborted) { setPreview(result); setNow(Date.now()) }
      } else {
        const result = await api<ImportConfirmation>('/imports/confirm', { method: 'POST', body: form, signal: controller.signal })
        if (!controller.signal.aborted) { setSuccess(result.already_imported ? 'Этот файл уже загружен. Данные не продублированы.' : `Готово! Загружено ${result.imported.row_count} записей. Данные доступны в обзоре.`); setPreview(null); setFile(null); if (fileInput.current) fileInput.current.value = ''; refresh() }
      }
    } catch (e) { if (!controller.signal.aborted) setError((e as Error).message) }
    finally { if (!controller.signal.aborted) setBusy(null) }
  }
  const expired = !!preview?.expires_at && Date.parse(preview.expires_at) <= now
  const columns = preview?.preview[0] ? Object.keys(preview.preview[0].data) : []
  const suggestedKind = importTypeHint(preview)
  return <><PageHeading eyebrow="ДАННЫЕ ВАШЕГО БИЗНЕСА" title="От файла к ясной картине" description="Загрузите файл, проверьте записи и подтвердите импорт." />
    <div className="import-grid"><section className="panel upload-panel"><div className="panel-heading"><div><h2>Новый импорт</h2><p>Данные для {business!.name}</p></div><span className="step-badge">Шаг {preview ? '2' : '1'} из 2</span></div>
      <div className="upload-body"><label className="field-label">Какие данные загружаем?</label><div className="import-types">{(['sales', 'expenses', 'products'] as ImportKind[]).map(k => <button key={k} className={kind === k ? 'selected' : ''} aria-pressed={kind === k} disabled={!!busy} onClick={() => changeKind(k)}>{k === 'sales' ? <TrendingUp size={17} /> : k === 'expenses' ? <Wallet size={17} /> : <Package size={17} />}{kindLabel[k]}</button>)}</div>
        <input ref={fileInput} className="visually-hidden" type="file" accept=".csv,.xlsx" id="import-file" onChange={e => choose(e.target.files?.[0])} disabled={!!busy} />
        <label htmlFor="import-file" className={`drop-zone ${dragging ? 'dragging' : ''} ${busy ? 'disabled' : ''}`} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!busy) choose(e.dataTransfer.files[0]) }}><span className="upload-icon"><Upload size={25} /></span><strong>{file ? file.name : 'Перетащите файл сюда'}</strong><span>{file ? `${decimal((file.size / 1024).toFixed(1))} КБ · Нажмите, чтобы заменить` : <>или <em>выберите на компьютере</em></>}</span><small>Тип данных: {kindLabel[kind]} · CSV или XLSX · до 10 МБ</small></label>
        <div className="upload-actions"><a href={`/templates/${kind}.csv`} download className="text-link"><ArrowDownToLine size={16} />Скачать шаблон</a><Button className="primary" disabled={!file || !!busy} onClick={() => void send('preview')}>{busy === 'preview' ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />}{busy === 'preview' ? 'Проверяем…' : 'Проверить файл'}</Button></div>
      </div></section><aside className="panel import-guide"><span className="guide-icon"><FileSpreadsheet size={23} /></span><h2>Пара минут —<br />и данные в порядке</h2><ol><li><span>1</span><div><strong>Подготовьте файл</strong><p>Используйте шаблон с нужными колонками. Даты — в формате ГГГГ-ММ-ДД.</p></div></li><li><span>2</span><div><strong>Проверьте предпросмотр</strong><p>Мы покажем строки и ошибки до сохранения в базу.</p></div></li><li><span>3</span><div><strong>Подтвердите импорт</strong><p>Повторная загрузка того же файла не создаст дубликатов.</p></div></li></ol><div className="guide-footnote"><CircleHelp size={16} /><span>В CSV используйте UTF-8 и запятые. XLSX должен содержать один лист без формул.</span></div></aside></div>
    {error && <ErrorBox message={error} />}{success && <div className="success-box" role="status"><CheckCircle2 size={21} /><span>{success}</span><Link to="/" className="text-link">Перейти к обзору <ArrowRight size={16} /></Link></div>}
    {preview && <section className="panel preview-panel"><div className="panel-heading"><div><h2>Проверьте данные</h2><p>{preview.filename} · {kindLabel[preview.kind]} · {preview.valid_row_count} корректных из {preview.row_count} строк</p></div><Button className="icon-button" aria-label="Закрыть предпросмотр" disabled={!!busy} onClick={() => setPreview(null)}><X size={18} /></Button></div>{suggestedKind && <div className="notice import-kind-hint" role="status"><CircleHelp size={20} /><div><strong>По колонкам файл похож на «{kindLabel[suggestedKind]}».</strong><p>Сейчас выбран тип «{kindLabel[preview.kind]}». Переключите тип и проверьте файл повторно.</p></div><Button disabled={!!busy} onClick={() => changeKind(suggestedKind)}>Переключить на «{kindLabel[suggestedKind]}»</Button></div>}{!!preview.errors.length && <div className="preview-errors" role="alert"><h3>{suggestedKind ? "Проверьте тип данных" : "Исправьте ошибки в файле"}</h3><ul>{preview.errors.map((e, i) => <li key={i}>Строка {e.row} · {columnLabel[e.field] || e.field}: {e.message}</li>)}</ul>{preview.errors_truncated && <p>Показаны первые 100 ошибок. В файле есть другие ошибки.</p>}</div>}{preview.existing_import_id && <div className="notice"><CheckCircle2 size={18} /><span>Эти данные уже загружены. Повторный импорт не требуется.</span></div>}{!!preview.preview.length && <div className="scroll-table"><table><thead><tr><th>Строка</th>{columns.map(c => <th key={c}>{columnLabel[c] || c}</th>)}</tr></thead><tbody>{preview.preview.map(row => <tr key={row.source_row}><td className="muted">{row.source_row}</td>{columns.map(c => <td key={c}>{String((row.data as unknown as Record<string, unknown>)[c] ?? '—')}</td>)}</tr>)}</tbody></table></div>}<div className="preview-footer"><span>{expired ? 'Предпросмотр истёк. Проверьте файл ещё раз.' : 'Показаны первые 20 корректных строк. Сохраняются все записи.'}</span><Button className="primary" disabled={!preview.can_confirm || !preview.preview_token || expired || !!busy} onClick={() => void send('confirm')}>{busy === 'confirm' ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}{busy === 'confirm' ? 'Сохраняем…' : 'Подтвердить импорт'}</Button></div></section>}
    <section className="panel history-panel"><div className="panel-heading"><div><h2>История загрузок</h2><p>Подтверждённые файлы и статус обработки</p></div><span className="subtle-icon"><ArrowDownToLine size={19} /></span></div>{history.loading ? <Loading /> : history.error ? <ErrorBox message={history.error} retry={refresh} /> : !history.data?.length ? <Empty title="Первый файл ещё впереди" text="Загруженные файлы появятся здесь после подтверждения." /> : <><div className="scroll-table"><table><thead><tr><th>Файл</th><th>Тип данных</th><th>Дата загрузки</th><th className="numeric">Строки</th><th>Статус</th></tr></thead><tbody>{history.data.map(row => <tr key={row.id}><td><span className="file-name"><FileSpreadsheet size={18} />{row.filename}</span></td><td>{kindLabel[row.kind]}</td><td className="muted">{new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }).format(new Date(row.created_at))}</td><td className="numeric">{decimal(String(row.row_count))}</td><td><span className={`status-badge ${row.status}`}><span />{row.status === 'confirmed' ? 'Загружен' : row.status === 'failed' ? 'Ошибка' : 'Обработка'}</span></td></tr>)}</tbody></table></div>{history.data.length >= historyLimit && historyLimit < 100 && <div className="load-more"><Button onClick={() => setHistoryLimit(v => Math.min(100, v + 20))}>Показать ещё</Button></div>}</>}</section>
  </>
}

function SettingsPage() {
  const { business, reloadBusinesses } = useWorkspace()
  const [name, setName] = useState('')
  const [industry, setIndustry] = useState('cafe')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setSuccess('')
    try { const result = await api<Business>('/businesses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim(), industry }) }); await reloadBusinesses(result.id); setName(''); setSuccess('Бизнес создан. Теперь можно загрузить продажи и расходы.') }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <><PageHeading eyebrow="РАБОЧЕЕ ПРОСТРАНСТВО" title="Мой бизнес" description="Профиль компании и основные параметры аналитики." /><div className="settings-grid"><section className="panel"><div className="panel-heading"><div><h2>Профиль бизнеса</h2><p>Текущее рабочее пространство</p></div><Building2 size={20} className="muted" /></div>{business ? <div className="business-profile"><span className="large-avatar">{business.name.slice(0, 1)}</span><h3>{business.name}</h3><span className="muted">{({ cafe: 'Кафе', retail: 'Розничная торговля', services: 'Услуги', other: 'Другое' } as Record<string, string>)[business.industry] || business.industry}</span><dl><div><dt>Валюта</dt><dd>Казахстанский тенге · KZT</dd></div><div><dt>Часовой пояс</dt><dd>Алматы · Asia/Almaty</dd></div><div><dt>Создан</dt><dd>{new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Almaty' }).format(new Date(business.created_at))}</dd></div></dl><Link className="button" to="/imports"><Upload size={16} />Загрузить данные</Link></div> : <Empty title="Создайте свой бизнес" text="Название и отрасль помогут организовать данные." />}</section><section className="panel"><div className="panel-heading"><div><h2>Добавить бизнес</h2><p>Отдельное пространство для каждой компании</p></div><Plus size={21} className="muted" /></div><form className="business-form" onSubmit={create}><label>Название бизнеса<input value={name} onChange={e => setName(e.target.value)} maxLength={200} placeholder="Например, Кофейня на Абая" required disabled={busy} /></label><label>Отрасль<select value={industry} onChange={e => setIndustry(e.target.value)} disabled={busy}><option value="cafe">Кафе и рестораны</option><option value="retail">Розничная торговля</option><option value="services">Услуги</option><option value="other">Другое</option></select></label><div className="fixed-fields"><span><Wallet size={16} /> KZT — тенге</span><span><CalendarDays size={16} /> Алматы</span></div><p className="form-hint">Продажи, расходы и товары каждого бизнеса хранятся отдельно.</p>{error && <p className="field-error" role="alert">{error}</p>}{success && <p className="success-text" role="status">{success}</p>}<Button className="primary" disabled={busy || !name.trim()}>{busy ? <LoaderCircle className="spin" size={17} /> : <Plus size={17} />}{busy ? 'Создаём…' : 'Создать бизнес'}</Button></form></section></div><section className="demo-card"><span className="demo-card-icon"><Sparkles size={26} /></span><div><h2>Посмотрите, как работает ProfitLeak</h2><p>Кафе в Таразе · 3 товара · 90 дней синтетических продаж и расходов</p></div><DemoButton /></section></>
}

const insightLabels: Record<InsightType, string> = {
  EXPENSE_SPIKE: 'Рост расходов', MARGIN_DROP: 'Падение маржи',
  LOW_PROFIT_PRODUCT: 'Низкая маржа', SALES_DROP: 'Снижение выручки',
  POSSIBLE_DUPLICATE: 'Возможный дубликат',
}
const severityLabels: Record<Severity, string> = { high: 'Высокий', medium: 'Средний', low: 'Низкий' }
function insightTitle(item: Insight) {
  return `${insightLabels[item.type]}${item.type === 'SALES_DROP' ? '' : `: ${categoryLabel[item.evidence.entity] || productLabel[item.evidence.entity] || item.evidence.entity}`}`
}
function EvidenceValue({ value, unit }: { value: string | null; unit: 'KZT' | 'percent' }) {
  return <>{value == null ? '—' : unit === 'percent' ? `${decimal(value)}%` : money(value)}</>
}
function InsightCard({ item }: { item: Insight }) {
  return <article className="panel insight-card">
    <div className="insight-card-top"><span className={`risk-badge ${item.severity}`}>Приоритет: {severityLabels[item.severity]}</span><span className="insight-kind">{insightLabels[item.type]}</span></div>
    <h2><Link to={`/insights/${item.id}`}>{insightTitle(item)}</Link></h2>
    <p>{item.evidence.explanation}</p>
    <div className="insight-values"><div><span>Текущее значение</span><strong><EvidenceValue value={item.evidence.current_value} unit={item.evidence.value_unit} /></strong></div>{item.evidence.baseline_value != null && <div><span>Базовое значение</span><strong><EvidenceValue value={item.evidence.baseline_value} unit={item.evidence.value_unit} /></strong></div>}</div>
    {item.evidence.deviation_percent != null && <span className="deviation">Изменение: {decimal(item.evidence.deviation_percent)}%</span>}
    {item.evidence.deviation_pp != null && <span className="deviation">Изменение маржи: {decimal(item.evidence.deviation_pp)} п.п.</span>}
    <div className="insight-card-footer"><span>{item.potential_savings_kzt != null ? <>Сценарная оценка: <strong>{money(item.potential_savings_kzt)}</strong></> : 'Экономия не оценена'}</span><Link className="text-link" to={`/insights/${item.id}`}>Разобрать сигнал <ArrowRight size={15} /></Link></div>
  </article>
}
function RunAnalysisButton({ period: selected, onDone }: { period?: Period | null; onDone?: () => void }) {
  const { business, period, refresh } = useWorkspace()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const scope = query(business!.id, selected === undefined ? period : selected)
  const active = useRef(scope)
  active.current = scope
  useEffect(() => { setError(''); setMessage('') }, [scope])
  async function run() {
    setBusy(true); setError(''); setMessage('')
    const requestedScope = scope
    const chosen = selected === undefined ? period : selected
    try {
      const result = await api<Analysis>('/analysis/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_id: business!.id, ...chosen }) })
      if (active.current === requestedScope) { setMessage(`Анализ завершён. Сигналов: ${result.insight_count}.`); onDone?.() }
      refresh()
    } catch (e) { if (active.current === requestedScope) setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="analysis-action"><Button className="primary" onClick={() => void run()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Activity size={17} />}{busy ? 'Анализируем…' : 'Запустить анализ'}</Button>{error && <p className="field-error" role="alert">{error}</p>}{message && <p className="success-text" role="status">{message}</p>}</div>
}
function AnalysisNotice({ analysis }: { analysis: Analysis }) {
  return <div className={`notice analysis-notice ${analysis.stale ? 'stale' : ''}`}><CircleHelp size={18} /><div>{analysis.stale ? <strong>После анализа загружены новые данные. Запустите анализ повторно.</strong> : <span>Обновлено {new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }).format(new Date(analysis.analyzed_at))} · {analysis.rules_version}</span>}{analysis.current_period && analysis.baseline_period && <p>Сравниваем {periodLabel(analysis.current_period)} с {periodLabel(analysis.baseline_period)}.</p>}<p>Сигналы требуют проверки. Сценарные оценки могут пересекаться, поэтому они не суммируются.</p></div></div>
}
function RecentInsights({ period }: { period: Period }) {
  const { business, refresh } = useWorkspace()
  const result = useRemote<Insights>(`/insights?${query(business!.id, period)}&limit=3`)
  return <section className="recent-insights"><div className="section-heading"><div><h2>Сигналы для проверки</h2><p>Правила анализа и подтверждённые данные</p></div><Link className="text-link" to="/insights">Детектор проблем <ArrowRight size={16} /></Link></div>{result.loading ? <Loading /> : result.error ? <ErrorBox message={result.error} retry={refresh} /> : result.data && <>{!result.data.analysis ? <div className="panel"><Empty title="Проверьте расходы и маржу" text="Запустите анализ, чтобы получить сигналы с расчётами и рекомендациями."><RunAnalysisButton period={period} /></Empty></div> : <><AnalysisNotice analysis={result.data.analysis} />{result.data.items.length ? <div className="insight-grid">{result.data.items.map(item => <InsightCard key={item.id} item={item} />)}</div> : <div className="panel"><Empty title="Сигналов по правилам не найдено" text="Откройте детектор, чтобы проверить достаточность данных для каждого правила." /></div>}</>}</>}</section>
}
function DetectorPage() {
  const { business, period, setEffectivePeriod, refresh } = useWorkspace()
  const [severity, setSeverity] = useState<Severity | ''>('')
  const [kind, setKind] = useState<InsightType | ''>('')
  const [page, setPage] = useState({ scope: '', offset: 0 })
  const scope = `${query(business!.id, period)}&severity=${severity}&kind=${kind}`
  const offset = page.scope === scope ? page.offset : 0
  const filters = new URLSearchParams()
  if (severity) filters.set('severity', severity)
  if (kind) filters.set('type', kind)
  const result = useRemote<Insights>(`/insights?${query(business!.id, period)}&${filters}&limit=9&offset=${offset}`)
  useEffect(() => { if (!period && result.data) setEffectivePeriod(result.data.period) }, [period, result.data, setEffectivePeriod])
  return <><PageHeading eyebrow="ОБЪЯСНИМЫЙ АНАЛИЗ" title="Детектор проблем" description="Проверьте рост расходов, маржу, продажи и возможные повторные платежи." dates />
    <div className="detector-toolbar"><div className="insight-filters"><label>Приоритет<select value={severity} onChange={e => setSeverity(e.target.value as Severity | '')}><option value="">Все приоритеты</option>{Object.entries(severityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Тип сигнала<select value={kind} onChange={e => setKind(e.target.value as InsightType | '')}><option value="">Все типы</option>{Object.entries(insightLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><RunAnalysisButton onDone={() => setPage({ scope, offset: 0 })} /></div>
    {result.loading ? <Loading /> : result.error ? <ErrorBox message={result.error} retry={refresh} /> : result.data && <>
      {!result.data.analysis ? <section className="panel"><Empty title="Анализ ещё не запускался" text="Запустите анализ для выбранного периода. Расчёты и рекомендации работают без подключения LLM." /></section> : <>
        <AnalysisNotice analysis={result.data.analysis} />
        {result.data.items.length ? <div className="insight-grid">{result.data.items.map(item => <InsightCard key={item.id} item={item} />)}</div> : <section className="panel"><Empty title={severity || kind ? 'Сигналов с такими фильтрами нет' : 'Сигналов по правилам не найдено'} text="Ниже показано, какие проверки удалось выполнить и где данных не хватило." /></section>}
        {result.data.total > 9 && <div className="pagination"><span>{offset + 1}–{offset + result.data.items.length} из {result.data.total} сигналов</span><div><Button className="icon-button" disabled={!offset} aria-label="Предыдущие сигналы" onClick={() => setPage({ scope, offset: Math.max(0, offset - 9) })}><ChevronLeft size={17} /></Button><Button className="icon-button" disabled={offset + 9 >= result.data.total} aria-label="Следующие сигналы" onClick={() => setPage({ scope, offset: offset + 9 })}><ChevronRight size={17} /></Button></div></div>}
        <section className="panel rule-panel"><div className="panel-heading"><div><h2>Достаточность данных</h2><p>Отсутствие сигнала не подтверждает отсутствие проблем.</p></div><CheckCircle2 size={20} className="muted" /></div><div className="rule-list">{result.data.analysis.checks.map(check => <div key={check.type}><div><strong>{insightLabels[check.type]}</strong><span className={`rule-status ${check.status}`}>{check.status === 'evaluated' ? `Проверено · сигналов: ${check.signals}` : 'Недостаточно данных'}</span></div><p>{check.reason}</p>{check.skipped_entities > 0 && <small>Пропущено объектов или записей: {check.skipped_entities}</small>}</div>)}</div></section>
      </>}
    </>}
  </>
}
function InsightPage() {
  const { insightId } = useParams()
  const { business, refresh } = useWorkspace()
  const result = useRemote<Insight>(`/insights/${insightId}?business_id=${business!.id}`)
  const snapshot = useRemote<Insights>(result.data ? `/insights?${query(business!.id, result.data.period)}&limit=1` : null)
  const item = result.data
  return <><Link className="text-link back-link" to="/insights"><ChevronLeft size={16} />К списку сигналов</Link>{result.loading ? <Loading /> : result.error ? <ErrorBox message={result.error} retry={refresh} /> : item && <>
    <PageHeading eyebrow={insightLabels[item.type].toUpperCase()} title={insightTitle(item)} description="Факты, исходные записи и действия для проверки." reportPeriod={item.period} />
    {snapshot.data?.analysis && <AnalysisNotice analysis={snapshot.data.analysis} />}
    <div className="insight-detail-grid"><section className="panel evidence-panel"><div className="panel-heading"><div><h2>Что показали данные</h2><p>{periodLabel(item.evidence.current_period)}</p></div><span className={`risk-badge ${item.severity}`}>{severityLabels[item.severity]} приоритет</span></div><div className="evidence-body"><p>{item.evidence.explanation}</p><div className="insight-values"><div><span>Текущее значение</span><strong><EvidenceValue value={item.evidence.current_value} unit={item.evidence.value_unit} /></strong></div>{item.evidence.baseline_value != null && <div><span>Базовое значение</span><strong><EvidenceValue value={item.evidence.baseline_value} unit={item.evidence.value_unit} /></strong></div>}</div><dl className="evidence-facts">
      {item.evidence.baseline_period && <div><dt>Базовый период</dt><dd>{periodLabel(item.evidence.baseline_period)}</dd></div>}
      {item.evidence.deviation_percent != null && <div><dt>Изменение</dt><dd>{decimal(item.evidence.deviation_percent)}%</dd></div>}
      {item.evidence.deviation_pp != null && <div><dt>Изменение маржи</dt><dd>{decimal(item.evidence.deviation_pp)} п.п.</dd></div>}
      {item.evidence.current_revenue != null && <div><dt>Текущая выручка / COGS</dt><dd>{money(item.evidence.current_revenue)} / {money(item.evidence.current_cogs)}</dd></div>}
      {item.evidence.baseline_revenue != null && <div><dt>Базовая выручка / COGS</dt><dd>{money(item.evidence.baseline_revenue)} / {money(item.evidence.baseline_cogs)}</dd></div>}
      <div><dt>Текущие записи / дни</dt><dd>{item.evidence.current_rows} / {item.evidence.current_days}</dd></div>
      {item.evidence.baseline_period && <div><dt>Базовые записи / дни</dt><dd>{item.evidence.baseline_rows} / {item.evidence.baseline_days}</dd></div>}
      <div><dt>Достоверность сопоставления</dt><dd>{severityLabels[item.confidence]} уровень</dd></div>
    </dl><div className="formula"><strong>Правило расчёта</strong><p>{item.evidence.formula}</p></div><p className="evidence-caveat">{item.evidence.caveat}</p></div></section>
    <aside className="panel recommendation-panel"><span className="guide-icon"><Sparkles size={23} /></span><h2>Что проверить</h2><p>{item.recommendation}</p><span className="recommendation-source">Шаблонная рекомендация · работает без LLM</span><div className="savings-box"><small>Сценарная оценка за текущий период</small><strong>{item.potential_savings_kzt != null ? money(item.potential_savings_kzt) : 'Не оценена'}</strong><p>{item.evidence.savings_assumption || 'Данных для обоснованной оценки экономии недостаточно.'}</p><span>Оценка требует проверки и не гарантирует экономию.</span></div></aside></div>
    <section className="panel sources-panel"><div className="panel-heading"><div><h2>Исходные записи</h2><p>Показано {item.evidence.source_rows.length} из {item.evidence.source_rows_total} строк, участвующих в расчёте. Для сравнения показаны примеры из обоих периодов.</p></div><FileSpreadsheet size={20} className="muted" /></div><div className="scroll-table"><table><thead><tr><th>Файл</th><th>Строка</th><th>Дата</th><th>Операция</th><th className="numeric">Сумма</th></tr></thead><tbody>{item.evidence.source_rows.map(row => <tr key={row.record_id}><td>{row.filename}</td><td>{row.source_row}</td><td>{dateLabel(row.date, true)}</td><td>{({ sale: 'Продажа', return: 'Возврат продажи', expense: 'Расход', refund: 'Возврат расхода' } as Record<string, string>)[row.record_type] || row.record_type}</td><td className="numeric">{money(row.amount)}</td></tr>)}</tbody></table></div><div className="panel-footnote">Строки возвратов показаны положительной суммой; в расчётах они вычитаются.</div></section>
    <InsightAdvisor item={item} />
  </>}</>
}

const fallbackLabels: Record<string, string> = {
  disabled: 'LLM отключён в настройках сервера.', missing_key: 'На сервере не задан API-ключ.',
  consent_required: 'Отправка выбранному провайдеру не разрешена.', timeout: 'Внешний API не ответил вовремя.',
  connection_error: 'Не удалось связаться с внешним API.', authentication_error: 'Провайдер отклонил API-ключ или доступ.',
  rate_limit: 'Достигнут лимит внешнего API.', quota_exhausted: 'Закончились кредиты или достигнут лимит расходов проекта.', model_error: 'Проверьте модель и параметры API на сервере.',
  provider_error: 'Внешний API временно недоступен.', invalid_response: 'Ответ LLM не прошёл проверку фактов.',
}
function ExternalConsent({ allowed, setAllowed, provider }: { allowed: boolean; setAllowed: (value: boolean) => void; provider: AdvisorStatus['provider'] }) {
  return <label className="external-consent"><input type="checkbox" checked={allowed} onChange={e => setAllowed(e.target.checked)} /><span>Разрешить отправку вопроса, истории этой беседы и агрегированных показателей в {provider === 'gemini' ? 'Google Gemini' : 'OpenAI'}. Исходные файлы и строки платежей не отправляются.{provider === 'gemini' && <small>На бесплатном тарифе Google может использовать переданные данные для улучшения продуктов.</small>}</span></label>
}
function AdvisorAnswer({ reply }: { reply: AdvisorReply }) {
  return <div className="advisor-answer"><div className="reply-meta"><span className={`mode-badge ${reply.source}`}>{reply.source === 'llm' ? `${reply.provider === 'gemini' ? 'Gemini' : 'OpenAI'} · ${reply.model}` : 'Шаблонный ответ'}</span>{reply.cached && <span>Сохранённый ответ · API-токены не потрачены</span>}{reply.retry_after_seconds != null && <span>Пауза API: повторите через {reply.retry_after_seconds} сек.</span>}{reply.fallback_reason && <span>{fallbackLabels[reply.fallback_reason]} Чат работает без LLM.</span>}</div>
    {reply.analysis_status !== 'current' && <p className="advisor-warning">{reply.analysis_status === 'stale' ? 'Анализ устарел после импорта.' : 'Анализ за этот период ещё не запускался.'} <Link to="/insights">Открыть детектор</Link></p>}
    <p className="answer-text">{reply.answer}</p><details className="advisor-facts"><summary>Факты backend · {reply.facts.length}</summary><dl>{reply.facts.map(fact => <div key={fact.id}><dt>{fact.insight_id ? <Link to={`/insights/${fact.insight_id}`}>{fact.label}</Link> : fact.label}</dt><dd>{fact.value}</dd></div>)}</dl></details><small>{reply.disclaimer}</small>
  </div>
}
type ChatTurn = { question: string; reply: AdvisorReply }
function AdvisorPage() {
  const { business, period, setEffectivePeriod, refresh } = useWorkspace()
  const connection = useRemote<AdvisorStatus>('/advisor/status')
  const overview = useRemote<Summary>(`/dashboard/summary?${query(business!.id, period)}`)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [question, setQuestion] = useState('')
  const [allowed, setAllowed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const scope = query(business!.id, period)
  const activeRequest = useRef<AbortController | null>(null)
  const chatEnd = useRef<HTMLDivElement>(null)
  useEffect(() => { setAllowed(false) }, [connection.data?.provider, connection.data?.model])
  useEffect(() => {
    setTurns([]); setQuestion(''); setError(''); setBusy(false); setAllowed(false)
    return () => activeRequest.current?.abort()
  }, [scope])
  useEffect(() => { if (!period && overview.data) setEffectivePeriod(overview.data.period) }, [period, overview.data, setEffectivePeriod])
  useEffect(() => { if (turns.length) chatEnd.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [turns.length])
  async function send(e: FormEvent) {
    e.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    setBusy(true); setError('')
    const controller = new AbortController()
    activeRequest.current = controller
    try {
      const history = turns.flatMap(turn => [{ role: 'user', content: turn.question }, { role: 'assistant', content: turn.reply.answer }]).slice(-4)
      const reply = await api<AdvisorReply>('/advisor/chat', { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_id: business!.id, ...period, message: text, history, allow_external: allowed, external_provider: connection.data?.provider }) })
      if (!controller.signal.aborted) { setTurns(old => [...old, { question: text, reply }]); setQuestion('') }
    } catch (e) { if (!controller.signal.aborted) setError((e as Error).message) }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }
  return <><PageHeading eyebrow="ОТ ФАКТОВ К ДЕЙСТВИЯМ" title="AI-советник" description="Обсудите показатели и сигналы выбранного бизнеса и периода." dates />
    {connection.loading ? <Loading label="Проверяем настройки советника…" /> : connection.error ? <ErrorBox message={connection.error} retry={refresh} /> : connection.data && <div className="notice advisor-connection"><Sparkles size={20} /><div><strong>{connection.data.ready ? `LLM настроен · ${connection.data.model}` : 'Советник работает в шаблонном режиме'}</strong><p>{connection.data.ready ? 'Внешний API используется после вашего разрешения. При ошибке будет доступен шаблонный ответ.' : fallbackLabels[connection.data.fallback_reason || 'disabled']}</p></div></div>}
    <section className="panel chat-panel"><div className="panel-heading"><div><h2>Беседа о финансах</h2><p>{periodLabel(period || overview.data?.period || null)} · {business!.name}</p></div><Button disabled={!turns.length || busy} onClick={() => setTurns([])}>Новая беседа</Button></div>
      {overview.error && <ErrorBox message={overview.error} retry={refresh} />}
      <div className="chat-messages" role="log" aria-label="История беседы" aria-live="polite">{!turns.length ? <div className="chat-intro"><span className="guide-icon"><Sparkles size={23} /></span><h3>С чего начать проверку?</h3><p>Советник объясняет рассчитанные показатели и предлагает проверки. Для подробного разбора сначала запустите детектор.</p><div className="suggested-questions">{['Какие проблемы проверить в первую очередь?', 'Почему падает маржа?', 'Как проверить расходы на упаковку?'].map(text => <Button key={text} onClick={() => setQuestion(text)}>{text}</Button>)}</div></div> : turns.map((turn, i) => <article key={i} className="chat-turn"><div className="user-message"><small>Вы</small><p>{turn.question}</p></div><div className="assistant-message"><strong>Советник ProfitLeak</strong><AdvisorAnswer reply={turn.reply} /></div></article>)}<div ref={chatEnd} /></div>
      <form className="chat-form" onSubmit={e => void send(e)}><ExternalConsent allowed={allowed} setAllowed={setAllowed} provider={connection.data?.provider || 'openai'} /><label htmlFor="advisor-question">Ваш вопрос</label><textarea id="advisor-question" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Например: какие расходы нужно проверить?" maxLength={2000} rows={3} required disabled={busy} /><div className="chat-form-footer"><small>История хранится только в этой вкладке и очищается при смене бизнеса или периода.</small><Button className="primary" disabled={busy || !question.trim() || overview.loading || !!overview.error}>{busy ? <LoaderCircle size={17} className="spin" /> : <ArrowRight size={17} />}{busy ? 'Советник отвечает…' : 'Отправить вопрос'}</Button></div>{error && <ErrorBox message={error} />}</form>
    </section>
  </>
}
function InsightAdvisor({ item }: { item: Insight }) {
  const connection = useRemote<AdvisorStatus>('/advisor/status')
  const [allowed, setAllowed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [reply, setReply] = useState<AdvisorReply | null>(null)
  const [error, setError] = useState('')
  const requestRef = useRef<AbortController | null>(null)
  useEffect(() => { setAllowed(false) }, [connection.data?.provider, connection.data?.model])
  useEffect(() => { setReply(null); setError(''); setBusy(false); setAllowed(false); return () => requestRef.current?.abort() }, [item.id, item.created_at])
  async function explain() {
    setBusy(true); setError('')
    const controller = new AbortController(); requestRef.current = controller
    try {
      const result = await api<AdvisorReply>('/advisor/chat', { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_id: item.business_id, ...item.period, insight_id: item.id, message: 'Объясни этот сигнал и предложи конкретные действия для проверки.', allow_external: allowed, external_provider: connection.data?.provider }) })
      if (!controller.signal.aborted) setReply(result)
    } catch (e) { if (!controller.signal.aborted) setError((e as Error).message) }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }
  return <section className="panel insight-advisor"><div className="panel-heading"><div><h2>Разобрать с советником</h2><p>Пояснение по этому сигналу с подтверждёнными фактами.</p></div><Link className="text-link" to="/advisor">Открыть чат <ArrowRight size={15} /></Link></div><div className="insight-advisor-body"><ExternalConsent allowed={allowed} setAllowed={setAllowed} provider={connection.data?.provider || 'openai'} /><Button className="primary" onClick={() => void explain()} disabled={busy}>{busy ? <LoaderCircle size={17} className="spin" /> : <Sparkles size={17} />}{busy ? 'Готовим пояснение…' : 'Получить пояснение'}</Button>{error && <ErrorBox message={error} />}{reply && <AdvisorAnswer reply={reply} />}</div></section>
}
