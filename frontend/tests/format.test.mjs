import { test } from 'node:test'
import assert from 'node:assert/strict'
import { decimal, money, periodLabel } from '../src/lib/api.ts'

test('financial amounts retain precision above Number safe integers', () => {
  assert.equal(money('9999999999999999.99'), '9\u202f999\u202f999\u202f999\u202f999\u202f999,99 ₸')
  assert.equal(money('-1234567890123456.01'), '−1\u202f234\u202f567\u202f890\u202f123\u202f456,01 ₸')
})
test('missing values stay missing and nonzero fractional amounts stay visible', () => {
  assert.equal(money(null), '—')
  assert.equal(money('0.00'), '0 ₸')
  assert.equal(money('1500.50'), '1\u202f500,50 ₸')
  assert.equal(decimal('54.62'), '54,62')
  assert.equal(decimal('1.125'), '1,125')
})
test('period labels remain on the API calendar dates', () => {
  assert.equal(periodLabel({ date_from: '2026-07-04', date_to: '2026-10-01' }), '4 июл. — 1 окт. 2026')
})
