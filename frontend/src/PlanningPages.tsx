import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link } from 'react-router'
import { ArrowLeftRight, ChevronLeft, ChevronRight, CircleHelp, TrendingUp } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, categoryLabel, dateLabel, decimal, metricReason, money, periodLabel, productLabel, query } from './lib/api'
import type { ComparedMetric, Comparison, Forecast, Metric, Period } from './lib/api'
import { localeTag, localizedRecord, tr, useLocale } from './i18n'

type PlanningProps = {
  businessId: string; period: Period | null; revision: number
  setEffectivePeriod: (period: Period) => void; heading: ReactNode
}
type MetricName = 'revenue' | 'cogs' | 'gross_profit' | 'gross_margin_percent' | 'operating_expenses' | 'operating_profit'
const labels: Record<MetricName, string> = localizedRecord({
  revenue: "Выручка", cogs: "Себестоимость", gross_profit: "Валовая прибыль",
  gross_margin_percent: "Валовая маржа", operating_expenses: "Операционные расходы", operating_profit: "Операционная прибыль",
})
const names = Object.keys(labels) as MetricName[]
const presence = localizedRecord({ both: '', current_only: "Только в выбранном периоде", baseline_only: "Только в базовом периоде" })
const compactMoney = (value: number) => new Intl.NumberFormat(localeTag(), { notation: 'compact', maximumFractionDigits: 1 }).format(value)
const chartNumber = (value: string | null) => value == null ? null : Number(value)

function usePlanning<T>(path: string, revision: number) {
  const locale = useLocale()
  const [state, setState] = useState<{ data: T | null; error: string; loading: boolean }>({ data: null, error: '', loading: true })
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setState({ data: null, error: '', loading: true })
    api<T>(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ data, error: '', loading: false })
    }).catch(error => { if (!controller.signal.aborted) setState({ data: null, error: error.message, loading: false }) })
    return () => controller.abort()
  }, [path, revision, retry, locale])
  return { ...state, retry: () => setRetry(v => v + 1) }
}

function Status({ loading, error, retry }: { loading: boolean; error: string; retry: () => void }) {
  return loading ? <div className="loading" role="status">{tr("Рассчитываем показатели…")}</div> : error ? <div className="error-box" role="alert"><div><strong>{tr("Не удалось выполнить расчёт")}</strong><p>{error}</p></div><button className="button" onClick={retry}>{tr("Повторить")}</button></div> : null
}
function Warnings({ items }: { items: string[] }) {
  return <>{items.map(item => <div className="notice" key={item}><CircleHelp size={18} /><span>{item}</span></div>)}</>
}
function Value({ metric, percent = false }: { metric: Metric; percent?: boolean }) {
  return <span title={metric.reason ? metricReason[metric.reason] : undefined}>{metric.value == null ? '—' : percent ? `${decimal(metric.value)}%` : money(metric.value)}</span>
}
function format(value: string | null, unit: ComparedMetric['unit']) {
  return value == null ? '—' : unit === 'percent' ? `${decimal(value)}%` : unit === 'quantity' ? decimal(value) : money(value)
}
function Change({ metric, daily = false, cost = false }: { metric: ComparedMetric; daily?: boolean; cost?: boolean }) {
  const value = daily && metric.unit !== 'percent' ? metric.per_day_change : metric.change
  const percent = daily ? metric.per_day_change_percent : metric.change_percent
  if (value == null) return <span className="change-neutral" title={tr("Недостаточно сопоставимых данных")}>{tr("Нет сравнения")}</span>
  const zero = /^-?0(?:\.0+)?$/.test(value)
  const negative = value.startsWith('-')
  const positivePrefix = zero || negative ? '' : '+'
  const suffix = metric.unit === 'percent' ? tr(" п.п.") : metric.unit === 'money' ? ' ₸' : ''
  return <span className={`change-value ${zero ? 'change-neutral' : negative === cost ? 'change-good' : 'change-bad'}`}>
    {positivePrefix}{decimal(value)}{suffix}
    {metric.unit !== 'percent' && <small>{percent != null ? `${percent.startsWith('-') || /^0(?:\.0+)?$/.test(percent) ? '' : '+'}${decimal(percent)}%` : tr("База = 0: % не определён")}</small>}
  </span>
}
function CompareCells({ metric, daily, cost = false }: { metric: ComparedMetric; daily: boolean; cost?: boolean }) {
  return <><td title={metric.baseline.reason ? metricReason[metric.baseline.reason] : undefined}>{format(daily && metric.unit !== 'percent' ? metric.baseline_per_day : metric.baseline.value, metric.unit)}</td><td title={metric.current.reason ? metricReason[metric.current.reason] : undefined}>{format(daily && metric.unit !== 'percent' ? metric.current_per_day : metric.current.value, metric.unit)}</td><td><Change metric={metric} daily={daily} cost={cost} /></td></>
}
function Pages({ total, offset, onChange }: { total: number; offset: number; onChange: (offset: number) => void }) {
  if (total <= 20) return null
  return <div className="pagination"><span>{offset + 1}–{Math.min(offset + 20, total)} {tr("из")} {total}</span><button className="button icon-button" aria-label={tr("Предыдущая страница")} disabled={!offset} onClick={() => onChange(Math.max(0, offset - 20))}><ChevronLeft size={16} /></button><button className="button icon-button" aria-label={tr("Следующая страница")} disabled={offset + 20 >= total} onClick={() => onChange(offset + 20)}><ChevronRight size={16} /></button></div>
}

export function ComparisonPage({ businessId, period, revision, setEffectivePeriod, heading }: PlanningProps) {
  const [daily, setDaily] = useState(false)
  const [mode, setMode] = useState('previous')
  const [baseline, setBaseline] = useState<Period | null>(null)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [validation, setValidation] = useState('')
  const [productsOffset, setProductsOffset] = useState(0)
  const [categoriesOffset, setCategoriesOffset] = useState(0)
  const [view, setView] = useState('chart')
  const [productMetric, setProductMetric] = useState<'revenue' | 'gross_profit' | 'gross_margin_percent' | 'quantity'>('revenue')
  // A filter change requests page one immediately; stale pages never hide the new result.
  const filterKey = `${query(businessId, period)}&${baseline?.date_from || ''}&${baseline?.date_to || ''}`
  const [pageKey, setPageKey] = useState(filterKey)
  const po = pageKey === filterKey ? productsOffset : 0
  const co = pageKey === filterKey ? categoriesOffset : 0
  const params = new URLSearchParams(query(businessId, period))
  if (baseline) { params.set('baseline_from', baseline.date_from); params.set('baseline_to', baseline.date_to) }
  params.set('products_offset', String(po)); params.set('categories_offset', String(co))
  const state = usePlanning<Comparison>(`/analytics/comparison?${params}`, revision)
  const data = state.data
  useEffect(() => { if (data && !period) setEffectivePeriod(data.current.period) }, [data, period, setEffectivePeriod])
  useEffect(() => { if (mode === 'previous' && data) { setStart(data.baseline.period.date_from); setEnd(data.baseline.period.date_to) } }, [data, mode])
  function apply(e: FormEvent) {
    e.preventDefault(); setValidation('')
    const fields = new FormData(e.currentTarget as HTMLFormElement)
    const from = String(fields.get('baseline_from') || '')
    const to = String(fields.get('baseline_to') || '')
    const length = (Date.parse(to) - Date.parse(from)) / 86400000 + 1
    if (!Number.isFinite(length) || length < 1 || length > 366) { setValidation(tr("Выберите базовый период от 1 до 366 дней.")); return }
    if (data && to >= data.current.period.date_from) { setValidation(tr("Базовый период должен завершаться до выбранного.")); return }
    setStart(from); setEnd(to); setBaseline({ date_from: from, date_to: to })
  }
  function paginate(kind: 'products' | 'categories', offset: number) {
    setPageKey(filterKey)
    setProductsOffset(kind === 'products' ? offset : po)
    setCategoriesOffset(kind === 'categories' ? offset : co)
  }
  return <>{heading}
    <section className="panel planning-controls"><div><h2><ArrowLeftRight size={19} /> {tr("С чем сравниваем")}</h2><p>{tr("Выбранный период задаётся календарём вверху. По умолчанию — последние 30 дней данных.")}</p></div>
      <form className="comparison-form" onSubmit={apply}><label>{tr("Базовый период")}<select value={mode} onChange={e => { setMode(e.target.value); setValidation(''); if (e.target.value === 'previous') setBaseline(null) }}><option value="previous">{tr("Предыдущий такой же длины")}</option><option value="custom">{tr("Выбрать даты")}</option></select></label>{mode === 'custom' && <><label>{tr("С")}<input name="baseline_from" aria-label={tr("Начало базового периода")} type="date" required value={start} onChange={e => setStart(e.target.value)} /></label><label>{tr("По")}<input name="baseline_to" aria-label={tr("Конец базового периода")} type="date" required value={end} onChange={e => setEnd(e.target.value)} /></label><button className="button primary" type="submit">{tr("Сравнить")}</button></>}</form>
      {validation && <p className="field-error" role="alert">{validation}</p>}
    </section>
    <Status {...state} />
    {data && <>
      <div className="comparison-periods"><div><span className="series-dot baseline" /><div><small>{tr("Базовый ·")} {data.baseline_days} {tr("дн.")}</small><strong>{periodLabel(data.baseline.period)}</strong><p>{tr("Дней с продажами:")} {data.baseline_sales_days} {tr("· Записей:")} {data.baseline.sales_rows}</p></div></div><ArrowLeftRight size={20} /><div><span className="series-dot current" /><div><small>{tr("Выбранный ·")} {data.current_days} {tr("дн.")}</small><strong>{periodLabel(data.current.period)}</strong><p>{tr("Дней с продажами:")} {data.current_sales_days} {tr("· Записей:")} {data.current.sales_rows}</p></div></div></div>
      <Warnings items={data.warnings} />
      <div className="planning-toolbar"><p>{daily ? tr("Суммы разделены на все календарные дни периода. Маржа не нормализуется.") : tr("Изменение = выбранный период − базовый. Маржа сравнивается в процентных пунктах.")}</p><div className="segmented"><button className={!daily ? 'active' : ''} onClick={() => setDaily(false)}>{tr("Суммы")}</button><button className={daily ? 'active' : ''} onClick={() => setDaily(true)}>{tr("За день")}</button></div></div>
      <div className="comparison-kpis">{data.metrics.map(metric => <article className="panel comparison-kpi" key={metric.name}><span>{labels[metric.name]}{daily && metric.unit !== 'percent' ? tr(" / день") : ''}</span><strong title={metric.current.reason ? metricReason[metric.current.reason] : undefined}>{format(daily && metric.unit !== 'percent' ? metric.current_per_day : metric.current.value, metric.unit)}</strong><p>{tr("База:")} {format(daily && metric.unit !== 'percent' ? metric.baseline_per_day : metric.baseline.value, metric.unit)}</p><Change metric={metric} daily={daily} cost={metric.name === 'cogs' || metric.name === 'operating_expenses'} /></article>)}</div>
      <section className="panel planning-chart"><div className="panel-heading"><div><h2>{tr("Выручка по дням")}</h2><p>{tr("День 1 — начало каждого периода; пробелы означают отсутствие данных.")}</p></div><div className="segmented"><button className={view === 'chart' ? 'active' : ''} onClick={() => setView('chart')}>{tr("График")}</button><button className={view === 'table' ? 'active' : ''} onClick={() => setView('table')}>{tr("Таблица")}</button></div></div>
        {view === 'chart' ? <div className="planning-chart-canvas"><ResponsiveContainer width="100%" height="100%"><LineChart data={data.points.map(p => ({ ...p, current: chartNumber(p.current.value), baseline: chartNumber(p.baseline.value) }))}><CartesianGrid strokeDasharray="3 5" vertical={false} /><XAxis dataKey="day" tickLine={false} axisLine={false} minTickGap={25} /><YAxis tickFormatter={compactMoney} width={70} tickLine={false} axisLine={false} /><Tooltip formatter={(value, name) => [money(String(value)), name]} labelFormatter={(_, payload) => { const point = payload?.[0]?.payload; return point ? tr("День {p0}: {p1} / {p2}", { p0: point.day, p1: point.current_date ? dateLabel(point.current_date) : '—', p2: point.baseline_date ? dateLabel(point.baseline_date) : '—' }) : '' }} /><Legend /><Line name={tr("Базовый период")} type="linear" dataKey="baseline" stroke="#9aa4bb" strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={false} /><Line name={tr("Выбранный период")} type="linear" dataKey="current" stroke="#088b7a" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div> : <div className="scroll-table planning-series-table"><table><thead><tr><th>{tr("День")}</th><th>{tr("Дата базы")}</th><th>{tr("Выручка базы")}</th><th>{tr("Дата выбранного")}</th><th>{tr("Выручка выбранного")}</th></tr></thead><tbody>{data.points.map(p => <tr key={p.day}><td>{p.day}</td><td>{p.baseline_date ? dateLabel(p.baseline_date, true) : '—'}</td><td><Value metric={p.baseline} /></td><td>{p.current_date ? dateLabel(p.current_date, true) : '—'}</td><td><Value metric={p.current} /></td></tr>)}</tbody></table></div>}
      </section>
      <section className="panel"><div className="panel-heading"><div><h2>{tr("Товары ·")} {data.products_total}</h2><p>{tr("Сначала самые крупные изменения выручки по модулю.")}</p></div><label className="compact-select">{tr("Показатель")}<select aria-label={tr("Показатель сравнения товаров")} value={productMetric} onChange={e => setProductMetric(e.target.value as typeof productMetric)}><option value="revenue">{tr("Выручка")}</option><option value="gross_profit">{tr("Валовая прибыль")}</option><option value="gross_margin_percent">{tr("Маржа")}</option><option value="quantity">{tr("Количество")}</option></select></label></div><div className="scroll-table"><table><thead><tr><th>{tr("Товар")}</th><th>{tr("Базовый")}{daily && productMetric !== 'gross_margin_percent' ? tr(" / день") : ''}</th><th>{tr("Выбранный")}{daily && productMetric !== 'gross_margin_percent' ? tr(" / день") : ''}</th><th>{tr("Изменение")}</th></tr></thead><tbody>{data.products.map(p => <tr key={p.product_id}><td><strong>{productLabel[p.name] || p.name}</strong><small className="table-detail">{p.external_id}{p.presence !== 'both' ? ` · ${presence[p.presence]}` : ''}</small></td><CompareCells metric={p[productMetric]} daily={daily} /></tr>)}</tbody></table>{!data.products.length && <div className="planning-empty">{tr("Нет продаж в обоих периодах.")} <Link to="/imports">{tr("Загрузить данные")}</Link></div>}</div><Pages total={data.products_total} offset={po} onChange={offset => paginate('products', offset)} /><div className="panel-footnote">{tr("Если товар встречается только в одном периоде, отсутствующие значения и изменение не рассчитываются.")}</div></section>
      <section className="panel"><div className="panel-heading"><div><h2>{tr("Категории расходов ·")} {data.categories_total}</h2><p>{tr("С учётом возвратов расходов; рост расходов выделен красным.")}</p></div></div><div className="scroll-table"><table><thead><tr><th>{tr("Категория")}</th><th>{tr("Базовый")}{daily ? tr(" / день") : ''}</th><th>{tr("Выбранный")}{daily ? tr(" / день") : ''}</th><th>{tr("Изменение")}</th></tr></thead><tbody>{data.categories.map(c => <tr key={c.category}><td><strong>{categoryLabel[c.category] || c.category}</strong>{c.presence !== 'both' && <small className="table-detail">{presence[c.presence]}</small>}</td><CompareCells metric={c.amount} daily={daily} cost /></tr>)}</tbody></table>{!data.categories.length && <div className="planning-empty">{tr("Нет расходов в обоих периодах.")}</div>}</div><Pages total={data.categories_total} offset={co} onChange={offset => paginate('categories', offset)} /></section>
      <div className="data-note"><CircleHelp size={15} /><span>{tr("Процент изменения = разница / модуль базового значения × 100. При нулевой базе и ненулевом результате процент не определяется. Ноль → ноль означает 0%.")}</span></div>
    </>}
  </>
}

export function ForecastPage({ businessId, period, revision, setEffectivePeriod, heading }: PlanningProps) {
  const [horizon, setHorizon] = useState(30)
  const [complete, setComplete] = useState(false)
  const [salesChange, setSalesChange] = useState('0')
  const [expenseChange, setExpenseChange] = useState('0')
  const [scenario, setScenario] = useState({ sales: '0', expense: '0' })
  const [selected, setSelected] = useState<MetricName>('revenue')
  const [view, setView] = useState('chart')
  const params = new URLSearchParams(query(businessId, period))
  params.set('horizon_days', String(horizon)); params.set('complete_calendar', String(complete))
  params.set('sales_change_percent', scenario.sales); params.set('expense_change_percent', scenario.expense)
  const state = usePlanning<Forecast>(`/analytics/forecast?${params}`, revision)
  const data = state.data
  useEffect(() => { if (data && !period) setEffectivePeriod(data.period) }, [data, period, setEffectivePeriod])
  function apply(e: FormEvent) {
    e.preventDefault()
    const fields = new FormData(e.currentTarget as HTMLFormElement)
    const sales = String(fields.get('sales_change') || '0')
    const expense = String(fields.get('expense_change') || '0')
    setSalesChange(sales); setExpenseChange(expense); setScenario({ sales, expense })
  }
  const nonzeroScenario = Number(scenario.sales) !== 0 || Number(scenario.expense) !== 0
  const chart = data ? [
    ...data.history.map((p, i) => ({ date: p.date, actual: chartNumber(p[selected].value), forecast: i === data.history.length - 1 ? chartNumber(p[selected].value) : null })),
    ...data.points.map(p => ({ date: p.date, actual: null, forecast: chartNumber(p[selected].value) })),
  ] : []
  return <>{heading}
    <section className="panel planning-controls"><div><h2><TrendingUp size={19} /> {tr("Параметры прогноза")}</h2><p>{tr("Календарь вверху задаёт историю. Расчёт начинается со следующего дня после её окончания.")}</p></div>
      <form className="forecast-form" onSubmit={apply}><label>{tr("Горизонт")}<select value={horizon} onChange={e => setHorizon(Number(e.target.value))}>{[7, 14, 30, 60, 90].map(days => <option key={days} value={days}>{days} {tr("дней")}</option>)}</select></label><label>{tr("Изменение продаж, %")}<input name="sales_change" type="number" min="-50" max="100" step="0.01" required value={salesChange} onChange={e => setSalesChange(e.target.value)} /></label><label>{tr("Изменение расходов, %")}<input name="expense_change" type="number" min="-50" max="100" step="0.01" required value={expenseChange} onChange={e => setExpenseChange(e.target.value)} /></label><button className="button primary" type="submit">{tr("Рассчитать сценарий")}</button><button className="button" type="button" onClick={() => { setSalesChange('0'); setExpenseChange('0'); setScenario({ sales: '0', expense: '0' }) }}>{tr("Сбросить сценарий")}</button></form>
      <label className="calendar-confirm"><input type="checkbox" checked={complete} onChange={e => setComplete(e.target.checked)} /><span>{tr("Подтверждаю, что отчёты за выбранную историю полные: дни без записей можно считать нулевыми.")}<small>{tr("Например, выходные без продаж или дни без платежей. Не включайте при неполном импорте.")}</small></span></label>
    </section>
    <Status {...state} />
    {data && <>
      <div className="forecast-period-strip"><div><small>{tr("ИСТОРИЯ ДЛЯ РАСЧЁТА")}</small><strong>{periodLabel(data.training_period)}</strong><span>{data.training_days} {tr("дн. · с продажами")} {data.observed_sales_days} {tr("· с расходами")} {data.observed_expense_days}</span></div><TrendingUp size={24} /><div><small>{tr("ПРОГНОЗ НА")} {data.horizon_days} {tr("ДН.")}</small><strong>{periodLabel(data.forecast_period)}</strong><span>{data.status === 'available' ? tr("Все показатели рассчитаны") : data.status === 'partial' ? tr("Часть показателей недоступна") : tr("Недостаточно данных")}</span></div></div>
      <Warnings items={data.warnings} />
      {nonzeroScenario && <div className="notice scenario-note"><TrendingUp size={18} /><span>{tr("Применён сценарий: продажи")} {decimal(data.sales_change_percent)}{tr("%, расходы")} {decimal(data.expense_change_percent)}{tr("%. В карточках ниже указана база без этих изменений.")}</span></div>}
      <div className="comparison-kpis">{names.map(name => <article className="panel comparison-kpi" key={name}><span>{labels[name]}</span><strong><Value metric={data.totals[name]} percent={name === 'gross_margin_percent'} /></strong>{data.totals[name].reason && <p>{metricReason[data.totals[name].reason]}</p>}{nonzeroScenario && <p>{tr("База:")} <Value metric={data.baseline_totals[name]} percent={name === 'gross_margin_percent'} /></p>}</article>)}</div>
      <section className="panel planning-chart"><div className="panel-heading"><div><h2>{tr("История и прогноз")}</h2><p>{tr("Сплошная линия — данные, пунктир — расчётный сценарий.")}</p></div><div className="planning-chart-options"><select aria-label={tr("Показатель прогноза")} value={selected} onChange={e => setSelected(e.target.value as MetricName)}>{names.filter(n => n !== 'gross_margin_percent').map(n => <option value={n} key={n}>{labels[n]}</option>)}</select><div className="segmented"><button className={view === 'chart' ? 'active' : ''} onClick={() => setView('chart')}>{tr("График")}</button><button className={view === 'table' ? 'active' : ''} onClick={() => setView('table')}>{tr("Таблица")}</button></div></div></div>
        {view === 'chart' ? data.totals[selected].value == null ? <div className="planning-empty">{metricReason[data.totals[selected].reason || 'insufficient_history']}{tr(". Выберите другой показатель или дополните данные.")}</div> : <div className="planning-chart-canvas"><ResponsiveContainer width="100%" height="100%"><LineChart data={chart}><CartesianGrid strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={value => dateLabel(value)} minTickGap={40} tickLine={false} axisLine={false} /><YAxis tickFormatter={compactMoney} width={70} tickLine={false} axisLine={false} /><Tooltip formatter={(value, name) => [money(String(value)), name]} labelFormatter={value => dateLabel(String(value), true)} /><Legend /><ReferenceLine x={data.training_period.date_to} stroke="#bac4c0" /><Line dataKey="actual" name={tr("История")} stroke="#088b7a" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} /><Line dataKey="forecast" name={tr("Прогноз")} stroke="#7565ab" strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div> : <div className="scroll-table planning-series-table"><table><thead><tr><th>{tr("Дата")}</th><th>{tr("Тип")}</th><th>{tr("Выручка")}</th><th>{tr("Себестоимость")}</th><th>{tr("Расходы")}</th><th>{tr("Опер. прибыль")}</th></tr></thead><tbody>{[...data.history.map(p => ({ ...p, kind: tr("История") })), ...data.points.map(p => ({ ...p, kind: tr("Прогноз") }))].map(p => <tr key={p.date} className={p.kind === tr("Прогноз") ? 'forecast-table-row' : ''}><td>{dateLabel(p.date, true)}</td><td>{p.kind}</td><td><Value metric={p.revenue} /></td><td><Value metric={p.cogs} /></td><td><Value metric={p.operating_expenses} /></td><td><Value metric={p.operating_profit} /></td></tr>)}</tbody></table></div>}
      </section>
      <div className="forecast-details"><section className="panel"><div className="panel-heading"><div><h2>{tr("Проверка на истории")}</h2><p>{tr("Последние 7 дней скрываются от расчёта и сравниваются с прогнозом выручки.")}</p></div></div><div className="forecast-detail-body">{data.backtest.status === 'available' ? <><p>{tr("Обучение:")} <strong>{periodLabel(data.backtest.training_period || null)}</strong></p><p>{tr("Проверка:")} <strong>{periodLabel(data.backtest.test_period || null)}</strong></p><div className="backtest-metrics"><div><small>{tr("Средняя ошибка за день (MAE)")}</small><strong>{money(data.backtest.revenue_mae)}</strong></div><div><small>{tr("Суммарная относительная ошибка (WAPE)")}</small><strong>{data.backtest.revenue_wape_percent == null ? '—' : `${decimal(data.backtest.revenue_wape_percent)}%`}</strong></div></div><p>{tr("WAPE = сумма абсолютных ошибок / сумма модулей фактической выручки. При нулевой выручке процент недоступен. Проверка относится к базовому прогнозу выручки без сценарных изменений.")}</p></> : <p>{data.backtest.reason}</p>}</div></section>
      <section className="panel"><div className="panel-heading"><div><h2>{tr("Как считается прогноз")}</h2><p>{tr("Локальный расчёт · API-токены не расходуются")}</p></div></div><div className="forecast-detail-body"><ul>{data.assumptions.map(a => <li key={a}>{a}</li>)}</ul></div></section></div>
    </>}
  </>
}
