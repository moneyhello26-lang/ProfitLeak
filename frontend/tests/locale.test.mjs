import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { getLocale, localizedRecord, setLocale, subscribeLocale, tr } from '../src/locale.ts'
import { kk } from '../src/translations.ts'
import { authKk } from '../src/auth.translations.ts'
import { api, categoryLabel, dateLabel, kindLabel, money, productLabel } from '../src/lib/api.ts'

test('language changes update enumerated labels without translating business data', () => {
  setLocale('ru')
  assert.equal(tr('Сравнение периодов'), 'Сравнение периодов')
  const labels = localizedRecord({ revenue: 'Выручка' })
  setLocale('kk')
  try {
    assert.equal(getLocale(), 'kk')
    assert.equal(tr('Сравнение периодов'), 'Кезеңдерді салыстыру')
    assert.equal(labels.revenue, 'Түсім')
    assert.equal(kindLabel.sales, 'Сатылымдар')
    assert.equal(categoryLabel.packaging, 'Қаптама')
    assert.equal(productLabel.Tea, 'Шай')
    assert.equal(tr('Кофейня «Шолпан»'), 'Кофейня «Шолпан»')
    assert.equal(tr('Готово! Загружено {p0} записей. Данные доступны в обзоре.', { p0: 17 }), 'Дайын! 17 жазба жүктелді. Деректер шолуда қолжетімді.')
    assert.equal(tr('{unknown}', {}), '{unknown}')
    assert.equal(money('9999999999999999.99'), '9\u202f999\u202f999\u202f999\u202f999\u202f999,99 ₸')
    assert.equal(dateLabel('2026-07-04'), '4 шіл.')
  } finally { setLocale('ru') }
  assert.equal(labels.revenue, 'Выручка')
})

test('locale subscriptions and persistence only notify on an actual change', () => {
  setLocale('ru')
  const values = new Map()
  const original = globalThis.localStorage
  globalThis.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  let notifications = 0
  const unsubscribe = subscribeLocale(() => notifications++)
  try {
    setLocale('kk'); setLocale('kk')
    assert.equal(notifications, 1)
    assert.equal(values.get('profitleak.locale'), 'kk')
    unsubscribe(); setLocale('ru')
    assert.equal(notifications, 1)
  } finally { unsubscribe(); setLocale('ru'); globalThis.localStorage = original }
})

test('all existing application UI copy has a Kazakh translation', () => {
  const missing = new Set()
  for (const filename of ['App.tsx', 'PlanningPages.tsx', 'Auth.tsx', 'lib/api.ts']) {
    const source = readFileSync(new URL(`../src/${filename}`, import.meta.url), 'utf8')
    const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    function visit(node) {
      // The Russian year suffix below is a formatter token removed from dates, not UI copy.
      if (ts.isStringLiteral(node) && node.text !== ' г.' && /[А-Яа-яЁё]/.test(node.text) && !(node.text in kk) && !(node.text in authKk)) missing.add(node.text)
      if (ts.isJsxText(node) && /[А-Яа-яЁё]/.test(node.text)) missing.add(`Untranslated JSX: ${node.text}`)
      ts.forEachChild(node, visit)
    }
    visit(tree)
  }
  assert.deepEqual([...missing], [])
})

test('API requests carry cookies and selected language, including multipart headers; 204 is supported', async () => {
  const original = globalThis.fetch
  let request
  globalThis.fetch = async (path, init) => { request = { path, init }; return new Response(null, { status: 204 }) }
  setLocale('kk')
  try {
    const form = new FormData(); form.set('kind', 'sales')
    assert.equal(await api('/imports/preview', { method: 'POST', body: form, headers: { 'X-Test': 'test' } }), undefined)
    assert.equal(request.init.credentials, 'include')
    assert.equal(request.init.headers.get('Accept-Language'), 'kk')
    assert.equal(request.init.headers.get('X-Test'), 'test')
    assert.equal(request.init.headers.has('Content-Type'), false)
    assert.equal(request.init.body, form)
  } finally { globalThis.fetch = original; setLocale('ru') }
})

test('unauthorized responses notify auth gate; aborted obsolete requests do not', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  globalThis.window = new EventTarget()
  let events = 0
  window.addEventListener('profitleak:unauthorized', () => events++)
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: { message: 'Session expired' } }), { status: 401 })
  try {
    await assert.rejects(api('/businesses'), /Session expired/)
    assert.equal(events, 1)
    const controller = new AbortController(); controller.abort()
    await assert.rejects(api('/businesses', { signal: controller.signal }), /Session expired/)
    assert.equal(events, 1)
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow }
})
