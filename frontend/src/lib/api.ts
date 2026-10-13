import type { components } from '../types/api'

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

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(`/api/v1${path}`, init) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error('Не удалось связаться с сервером. Проверьте подключение и попробуйте ещё раз.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail
    throw new Error(typeof detail?.message === 'string' ? detail.message :
      response.status === 422 ? 'Проверьте заполненные поля и выбранный период (не более 366 дней).' :
      'Не удалось загрузить данные. Проверьте, что сервер и база данных запущены.')
  }
  return body as T
}

export function query(businessId: string, period: Period | null) {
  const params = new URLSearchParams({ business_id: businessId })
  if (period) { params.set('date_from', period.date_from); params.set('date_to', period.date_to) }
  return params.toString()
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
export function dateLabel(value: string, year = false) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', ...(year ? { year: 'numeric' } : {}), timeZone: 'UTC' }).format(new Date(`${value}T12:00:00Z`)).replace(' г.', '')
}
export function periodLabel(period: Period | null) {
  return period ? `${dateLabel(period.date_from)} — ${dateLabel(period.date_to, true)}` : 'Последние 90 дней'
}
export const metricReason: Record<string, string> = {
  no_sales: 'Нет продаж за этот период', missing_cost: 'Не указана себестоимость части продаж',
  no_expenses: 'Нет расходов за этот период', zero_revenue: 'Нулевая выручка: маржа не рассчитывается',
}
export const categoryLabel: Record<string, string> = {
  packaging: 'Упаковка', wages: 'Зарплата', utilities: 'Коммунальные услуги', rent: 'Аренда',
  Packaging: 'Упаковка', Wages: 'Зарплата', Utilities: 'Коммунальные услуги', Rent: 'Аренда',
}
export const productLabel: Record<string, string> = { Coffee: 'Кофе', Tea: 'Чай', Sandwich: 'Сэндвич' }
export const kindLabel: Record<ImportKind, string> = { sales: 'Продажи', expenses: 'Расходы', products: 'Товары' }
