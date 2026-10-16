import { getLocale, localeTag } from '../locale.ts'

// Some browsers ship incomplete kk ICU data and render month names as M01…M12.
// Keep month copy in the app; use Intl only for numeric Gregorian timezone parts.
const kazakhMonths = [
  'қаңтар', 'ақпан', 'наурыз', 'сәуір', 'мамыр', 'маусым',
  'шілде', 'тамыз', 'қыркүйек', 'қазан', 'қараша', 'желтоқсан',
]
const kazakhShortMonths = [
  'қаң.', 'ақп.', 'нау.', 'сәу.', 'мам.', 'мау.',
  'шіл.', 'там.', 'қыр.', 'қаз.', 'қар.', 'жел.',
]

export function dateLabel(value: string, year = false) {
  // A date-only API value always stays on its UTC calendar day.
  const date = new Date(`${value}T12:00:00Z`)
  if (getLocale() === 'kk') {
    return `${date.getUTCDate()} ${kazakhShortMonths[date.getUTCMonth()]}${year ? ` ${date.getUTCFullYear()}` : ''}`
  }
  return new Intl.DateTimeFormat(localeTag(), { day: 'numeric', month: 'short', ...(year ? { year: 'numeric' } : {}), timeZone: 'UTC' }).format(date).replace(' г.', '')
}

export function dateTimeLabel(value: string, options: Intl.DateTimeFormatOptions) {
  const date = new Date(value)
  if (getLocale() !== 'kk') return new Intl.DateTimeFormat(localeTag(), options).format(date)
  const parts = new Intl.DateTimeFormat('en-GB', {
    ...options, day: 'numeric', month: 'numeric', year: 'numeric',
    calendar: 'gregory', numberingSystem: 'latn', hourCycle: 'h23',
  }).formatToParts(date)
  const part = (name: Intl.DateTimeFormatPartTypes) => parts.find(item => item.type === name)?.value || ''
  const months = options.month === 'long' ? kazakhMonths : kazakhShortMonths
  const day = Number(part('day'))
  const month = months[Number(part('month')) - 1]
  const year = options.year ? ` ${part('year')}` : ''
  const time = options.hour ? `, ${part('hour')}${options.minute ? `:${part('minute')}` : ''}` : ''
  return `${day} ${month}${year}${time}`
}
