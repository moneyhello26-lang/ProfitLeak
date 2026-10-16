import type { components } from '../types/api'
import { getLocale, localizedRecord, tr } from '../locale.ts'
import { dateLabel } from './dates.ts'
export { dateLabel, dateTimeLabel } from './dates.ts'
import { authRequestEpoch } from './authEpoch.ts'

export type Business = components['schemas']['BusinessRead']
export type Period = components['schemas']['Period']
export type Metric = components['schemas']['Metric']
export type Summary = components['schemas']['DashboardSummary']
export type Revenue = components['schemas']['RevenueAnalytics']
export type Expenses = components['schemas']['ExpensesAnalytics']
export type Products = components['schemas']['ProductsAnalytics']
export type ImportPreview = components['schemas']['ImportPreview']
export type ImportRead = components['schemas']['ImportRead']
export type ImportConfirmation = components['schemas']['ImportConfirmation']
export type Demo = components['schemas']['DemoLoad']
export type ImportKind = ImportRead['kind']
export type Analysis = components['schemas']['AnalysisRead']
export type Insights = components['schemas']['InsightsRead']
export type Insight = components['schemas']['InsightRead']
export type InsightType = Insight['type']
export type Severity = Insight['severity']
export type AdvisorStatus = components['schemas']['AdvisorStatus']
export type AdvisorReply = components['schemas']['AdvisorResponse']
export type Comparison = components['schemas']['PeriodComparison']
export type ComparedMetric = components['schemas']['MetricComparison']
export type Forecast = components['schemas']['FinancialForecast']

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const requestEpoch = authRequestEpoch()
  let response: Response
  const headers = new Headers(init?.headers)
  headers.set('Accept-Language', getLocale())
  try { response = await fetch(`/api/v1${path}`, { ...init, credentials: 'include', headers }) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error(tr('Не удалось связаться с сервером. Проверьте подключение и попробуйте ещё раз.'))
  }
  if (response.status === 401 && requestEpoch === authRequestEpoch() && !init?.signal?.aborted && typeof window !== 'undefined') window.dispatchEvent(new Event('profitleak:unauthorized'))
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail
    throw new Error(typeof detail?.message === 'string' ? detail.message :
      response.status === 422 ? tr(path.startsWith('/auth/') || path.includes('/members') ? 'Проверьте заполненные поля.' : 'Проверьте заполненные поля и выбранный период (не более 366 дней).') :
      tr('Не удалось загрузить данные. Проверьте, что сервер и база данных запущены.'))
  }
  return body as T
}

export function query(businessId: string, period: Period | null) {
  const params = new URLSearchParams({ business_id: businessId })
  if (period) { params.set('date_from', period.date_from); params.set('date_to', period.date_to) }
  return params.toString()
}

export async function downloadPdf(businessId: string, period: Period | null) {
  const requestEpoch = authRequestEpoch()
  const response = await fetch(`/api/v1/reports/pdf?${query(businessId, period)}`, { credentials: 'include', headers: { 'Accept-Language': getLocale() } })
  if (response.status === 401 && requestEpoch === authRequestEpoch()) window.dispatchEvent(new Event('profitleak:unauthorized'))
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail?.message || tr('Не удалось сформировать PDF. Проверьте период и подключение к серверу.'))
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = response.headers.get('Content-Disposition')?.match(/filename="([a-zA-Z0-9_.-]+)"/)?.[1] || 'profitleak.pdf'
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// Keep API decimal strings exact for display. Number conversion is only used by charts.
export function decimal(value: string | null | undefined, fraction = 0): string {
  if (value == null) return '—'
  const negative = value.startsWith('-')
  const [whole, tail = ''] = value.replace(/^-/, '').split('.')
  const digits = (whole.replace(/^0+(?=\d)/, '') || '0').replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f')
  // Financial values already have two decimal places from the API; preserve nonzero cents.
  const places = Math.max(fraction, /[1-9]/.test(tail) ? tail.length : 0)
  return `${negative ? '−' : ''}${digits}${places ? ',' + tail.padEnd(places, '0') : ''}`
}
export function money(value: string | null | undefined) { return value == null ? '—' : `${decimal(value)} ₸` }
export function periodLabel(period: Period | null) {
  return period ? `${dateLabel(period.date_from)} — ${dateLabel(period.date_to, true)}` : tr('Последние 90 дней')
}
export const metricReason: Record<string, string> = localizedRecord({
  no_sales: 'Нет продаж за этот период', missing_cost: 'Не указана себестоимость части продаж',
  no_expenses: 'Нет расходов за этот период', zero_revenue: 'Нулевая выручка: маржа не рассчитывается',
  insufficient_history: 'Нужно не менее 28 календарных дней истории',
  incomplete_sales_calendar: 'Есть дни без записей о продажах',
  incomplete_expense_calendar: 'Есть дни без записей о расходах',
})
export const categoryLabel: Record<string, string> = localizedRecord({
  packaging: 'Упаковка', wages: 'Зарплата', utilities: 'Коммунальные услуги', rent: 'Аренда',
  Packaging: 'Упаковка', Wages: 'Зарплата', Utilities: 'Коммунальные услуги', Rent: 'Аренда',
<<<<<<< Updated upstream
})
export const productLabel: Record<string, string> = localizedRecord({ Coffee: 'Кофе', Tea: 'Чай', Sandwich: 'Сэндвич' })
export const kindLabel: Record<ImportKind, string> = localizedRecord({ sales: 'Продажи', expenses: 'Расходы', products: 'Товары' })
=======
  Salary: 'Зарплата', Software: 'Программы и связь', BankFees: 'Банковские комиссии',
  Delivery: 'Доставка', Marketing: 'Реклама', Cleaning: 'Уборка', Spoilage: 'Списания',
  Repairs: 'Ремонт и обслуживание',
}
export const productLabel: Record<string, string> = { Coffee: 'Кофе', Tea: 'Чай', Sandwich: 'Сэндвич' }
export const kindLabel: Record<ImportKind, string> = { sales: 'Продажи', expenses: 'Расходы', products: 'Товары' }
>>>>>>> Stashed changes
