import { test } from 'node:test'
import assert from 'node:assert/strict'
import { setLocale } from '../src/locale.ts'
import { dateLabel, dateTimeLabel, periodLabel } from '../src/lib/api.ts'

test('Kazakh dates use bundled month names even when kk ICU locale is unavailable', () => {
  const Original = Intl.DateTimeFormat
  Intl.DateTimeFormat = new Proxy(Original, {
    construct(target, args) {
      assert.ok(!String(args[0]).startsWith('kk'), 'Kazakh month names must not depend on kk ICU support')
      return Reflect.construct(target, args)
    },
  })
  setLocale('kk')
  try {
    const months = ['қаң.', 'ақп.', 'нау.', 'сәу.', 'мам.', 'мау.', 'шіл.', 'там.', 'қыр.', 'қаз.', 'қар.', 'жел.']
    months.forEach((month, index) => assert.equal(dateLabel(`2026-${String(index + 1).padStart(2, '0')}-02`), `2 ${month}`))
    assert.equal(dateLabel('2024-02-29', true), '29 ақп. 2024')
    assert.equal(periodLabel({ date_from: '2026-09-02', date_to: '2026-10-01' }), '2 қыр. — 1 қаз. 2026')
    assert.equal(dateTimeLabel('2026-09-30T21:30:00Z', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }), '1 қаз. 2026, 02:30')
    assert.equal(dateTimeLabel('2026-09-30T21:30:00Z', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Almaty' }), '1 қазан 2026')
  } finally { setLocale('ru'); Intl.DateTimeFormat = Original }
})

test('Russian calendar and timestamp labels preserve existing Intl formatting', () => {
  setLocale('ru')
  assert.equal(dateLabel('2026-09-02'), '2 сент.')
  assert.equal(periodLabel({ date_from: '2026-09-02', date_to: '2026-10-01' }), '2 сент. — 1 окт. 2026')
  const options = { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }
  assert.equal(dateTimeLabel('2026-09-30T21:30:00Z', options), new Intl.DateTimeFormat('ru-KZ', options).format(new Date('2026-09-30T21:30:00Z')))
})
