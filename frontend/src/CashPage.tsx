import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { components } from './types/api'
import { api, dateLabel, money } from './lib/api'
import { tr, useLocale } from './i18n'
import { useCanEdit } from './Auth'
import './cash.css'

type Report = components['schemas']['CashReport']
type Entry = components['schemas']['EntryRead']
type Preview = components['schemas']['StatementPreview']
type Tab = 'accounts' | 'entries' | 'payments' | 'budgets' | 'exchange'
const tabs: { id: Tab; label: string }[] = [
  { id: 'accounts', label: 'Счета и остатки' }, { id: 'entries', label: 'Движение денег' },
  { id: 'payments', label: 'Платёжный календарь' }, { id: 'budgets', label: 'Бюджет и план-факт' },
  { id: 'exchange', label: 'Банк и 1С: файлы' },
]
const kindNames = { income: 'Поступление', expense: 'Списание', transfer: 'Перевод' }
const statusNames = { pending: 'Ожидается', paid: 'Оплачен', cancelled: 'Отменён' }
const recurrenceNames = { none: 'Однократно', weekly: 'Каждую неделю', monthly: 'Каждый месяц' }
function today() {
  // Calendar date in the business timezone, independent of the computer timezone.
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Almaty', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const value = (type: string) => parts.find(p => p.type === type)!.value
  return `${value('year')}-${value('month')}-${value('day')}`
}
function initialPeriod() {
  const day = today()
  const [year, month] = day.split('-').map(Number)
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate()
  return { from: day.slice(0, 8) + '01', to: day.slice(0, 8) + last }
}

export function CashPage({ businessId, revision }: { businessId: string; revision: number }) {
  const locale = useLocale()
  const canEdit = useCanEdit(businessId)
  const [tab, setTab] = useState<Tab>('accounts')
  const [period, setPeriod] = useState(initialPeriod)
  const [report, setReport] = useState<Report | null>(null)
  const [entries, setEntries] = useState<Entry[]>([])
  const [page, setPage] = useState(0)
  const [version, setVersion] = useState(0)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [accountId, setAccountId] = useState('')
  const [entryKind, setEntryKind] = useState<'income' | 'expense' | 'transfer'>('expense')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const scope = `business_id=${encodeURIComponent(businessId)}`
  const range = `${scope}&date_from=${period.from}&date_to=${period.to}`
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setReport(null); setEntries([])
    Promise.all([
      api<Report>(`/cash/report?${range}`, { signal: controller.signal }),
      api<Entry[]>(`/cash/entries?${range}&limit=50&offset=${page * 50}`, { signal: controller.signal }),
    ]).then(([nextReport, nextEntries]) => {
      if (!controller.signal.aborted) {
        setReport(nextReport); setEntries(nextEntries)
        setAccountId(previous => nextReport.accounts.some(a => a.id === previous) ? previous : nextReport.accounts[0]?.id || '')
      }
    }).catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [range, page, revision, version, locale])

  async function execute(action: () => Promise<void>, refresh = true) {
    setBusy(true); setError(''); setSuccess('')
    try { await action(); if (refresh) { setSuccess('Сохранено.'); setVersion(v => v + 1) } }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  function submit(path: string, build: (f: FormData) => object) {
    return (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const form = event.currentTarget
      const data = new FormData(form)
      void execute(async () => {
        await api(`/cash/${path}?${scope}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(build(data)) })
        form.reset()
      })
    }
  }
  const value = (form: FormData, key: string) => String(form.get(key) || '')
  const accountName = (id: string | null) => report?.accounts.find(a => a.id === id)?.name || '—'
  const accountSelect = <label>{tr('Счёт')}<select name="account_id" value={accountId} disabled={busy} onChange={e => { setAccountId(e.target.value); setPreview(null) }} required>{report?.accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
  const categoryField = <label>{tr('Категория')}<input name="category" maxLength={100} required list="cash-categories" /></label>
  const amountField = <label>{tr('Сумма, ₸')}<input name="amount" type="number" min="0.01" step="0.01" required /></label>
  const descriptionField = <label className="cash-wide">{tr('Описание')}<input name="description" maxLength={500} /></label>
  const actionButton = <button className="button primary" type="submit" disabled={busy}>{tr('Сохранить')}</button>
  async function paymentAction(id: string, action: 'pay' | 'cancel', form?: HTMLFormElement) {
    const paidDate = form ? String(new FormData(form).get('paid_date')) : null
    await execute(async () => { await api(`/cash/payments/${id}?${scope}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, paid_date: paidDate }) }) })
  }
  async function statement(confirm: boolean) {
    if (!file || !accountId) return
    const body = new FormData()
    body.set('business_id', businessId); body.set('account_id', accountId); body.set('file', file)
    if (confirm && preview?.preview_token) body.set('preview_token', preview.preview_token)
    await execute(async () => {
      if (confirm) { await api('/cash/statements/confirm', { method: 'POST', body }); setPreview(null); setFile(null) }
      else { setPreview(null); setPreview(await api<Preview>('/cash/statements/preview', { method: 'POST', body })) }
    }, confirm)
  }
  const firstGap = report?.projection.find(p => p.gap_accounts.length)
  return <div className="cash-page">
    <div className="page-heading"><div><div className="eyebrow">{tr('ДЕНЕЖНЫЙ ПОТОК')}</div><h1>{tr('Деньги и платежи')}</h1><p>{tr('Остатки на счетах, обязательства и бюджет вашего бизнеса.')}</p></div></div>
    <form className="cash-period panel" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); setPage(0); setPeriod({ from: value(f, 'from'), to: value(f, 'to') }) }}>
      <label>{tr('Начало периода')}<input key={`from-${period.from}`} name="from" type="date" defaultValue={period.from} required /></label><label>{tr('Конец периода')}<input key={`to-${period.to}`} name="to" type="date" defaultValue={period.to} required /></label><button className="button" disabled={busy}>{tr('Показать')}</button>
    </form>
    <p className="cash-hint">{tr('Денежные операции учитываются отдельно от продаж и расходов в обзоре прибыли. Переводы между своими счетами не меняют общий денежный поток.')}</p>
    {error && <div className="error-box" role="alert">{error}<button className="button" onClick={() => setVersion(v => v + 1)}>{tr('Повторить')}</button></div>}
    {success && <p className="notice" role="status">{tr(success)}</p>}
    <div className="cash-tabs" role="tablist" aria-label={tr('Деньги и платежи')}>{tabs.map(t => <button key={t.id} role="tab" aria-selected={tab === t.id} aria-controls={`cash-${t.id}`} id={`cash-tab-${t.id}`} className={`button ${tab === t.id ? 'primary' : ''}`} onClick={() => { setTab(t.id); setSuccess('') }}>{tr(t.label)}</button>)}</div>
    {loading && <p role="status">{tr('Загружаем данные…')}</p>}
    {report && <>
      <div className="cash-kpis">{[['Остаток на начало', report.opening_balance], ['Поступления', report.income], ['Списания', report.expense], ['Остаток на конец', report.closing_balance]].map(([label, amount]) => <article className="panel" key={label}><span>{tr(label)}</span><strong>{money(amount)}</strong></article>)}</div>
      <section className="panel cash-section" role="tabpanel" id={`cash-${tab}`} aria-labelledby={`cash-tab-${tab}`}>
        <datalist id="cash-categories">{Array.from(new Set([...report.categories.map(c => c.category), ...report.budgets.map(b => b.category)])).map(c => <option key={c} value={c} />)}</datalist>
        {tab === 'accounts' && <><h2>{tr('Счета и остатки')}</h2><p>{tr('Остатки показаны на конец выбранного периода. Начальный остаток задаётся на начало дня открытия счёта.')}</p>
          <div className="cash-account-grid">{report.accounts.map(a => <article key={a.id}><h3>{a.name}</h3><strong>{money(a.balance)}</strong><p>{dateLabel(a.opening_date, true)} · {money(a.opening_balance)}</p></article>)}</div>
          {!report.accounts.length && <p>{tr('Добавьте первый счёт или кассу.')}</p>}
          {canEdit && <form className="cash-form" onSubmit={submit('accounts', f => ({ name: value(f, 'name'), opening_date: value(f, 'opening_date'), opening_balance: value(f, 'opening_balance') }))}><h3 className="cash-wide">{tr('Добавить счёт')}</h3><label>{tr('Название счёта')}<input name="name" maxLength={120} required /></label><label>{tr('Дата начального остатка')}<input name="opening_date" type="date" defaultValue={today()} required /></label><label>{tr('Начальный остаток, ₸')}<input name="opening_balance" type="number" step="0.01" defaultValue="0" required /></label>{actionButton}</form>}
        </>}
        {tab === 'entries' && <><h2>{tr('Движение денег')}</h2><div className="scroll-table"><table><thead><tr>{['Дата', 'Тип', 'Счёт', 'Категория', 'Сумма, ₸', 'Описание'].map(s => <th key={s}>{tr(s)}</th>)}</tr></thead><tbody>{entries.map(e => <tr key={e.id}><td>{dateLabel(e.date, true)}</td><td>{tr(kindNames[e.kind])}</td><td>{accountName(e.account_id)}{e.destination_id && ` → ${accountName(e.destination_id)}`}</td><td>{e.category}</td><td>{money(e.amount)}</td><td>{e.description}</td></tr>)}</tbody></table></div>
          {!entries.length && <p>{tr('За этот период операций нет.')}</p>}
          <div className="cash-actions"><button className="button" disabled={page === 0 || loading} onClick={() => setPage(p => p - 1)}>{tr('Назад')}</button><span>{page + 1}</span><button className="button" disabled={entries.length < 50 || loading} onClick={() => setPage(p => p + 1)}>{tr('Далее')}</button></div>
          {canEdit && !!report.accounts.length && <form className="cash-form" onSubmit={submit('entries', f => ({ account_id: accountId, destination_id: entryKind === 'transfer' ? value(f, 'destination_id') : null, date: value(f, 'date'), kind: entryKind, amount: value(f, 'amount'), category: value(f, 'category'), description: value(f, 'description'), reference: value(f, 'reference') || null }))}><h3 className="cash-wide">{tr('Добавить операцию')}</h3>{accountSelect}<label>{tr('Тип')}<select value={entryKind} onChange={e => setEntryKind(e.target.value as typeof entryKind)}>{Object.entries(kindNames).map(([k, v]) => <option key={k} value={k}>{tr(v)}</option>)}</select></label>{entryKind === 'transfer' && <label>{tr('Счёт получателя')}<select name="destination_id" required><option value="">—</option>{report.accounts.filter(a => a.id !== accountId).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>}<label>{tr('Дата')}<input name="date" type="date" defaultValue={today()} required /></label>{amountField}{categoryField}<label>{tr('Номер операции')}<input name="reference" maxLength={160} /></label>{descriptionField}{actionButton}</form>}
        </>}
        {tab === 'payments' && <><h2>{tr('Платёжный календарь')}</h2><p>{tr('Прогноз учитывает записанные операции и ожидаемые платежи. Просроченные платежи включены в первый день периода. Повторный платёж создаётся после оплаты предыдущего.')}</p>
          {firstGap ? <p className="error-box">{tr('Возможен кассовый разрыв:')} {dateLabel(firstGap.date, true)} · {firstGap.gap_accounts.map(accountName).join(', ')}</p> : <p className="notice">{tr('По записанным платежам кассового разрыва нет.')}</p>}
          <p>{tr('Ожидаемый остаток на конец:')} <strong>{money(report.projection.at(-1)?.balance)}</strong></p>
          <div className="scroll-table"><table><thead><tr>{['Дата', 'Счёт', 'Тип', 'Категория', 'Сумма, ₸', 'Повторение', 'Статус', 'Действия'].map(s => <th key={s}>{tr(s)}</th>)}</tr></thead><tbody>{report.payments.map(p => <tr key={p.id}><td>{dateLabel(p.due_date, true)}</td><td>{accountName(p.account_id)}</td><td>{tr(kindNames[p.kind])}</td><td>{p.category}<small className="cash-description">{p.description}</small></td><td>{money(p.amount)}</td><td>{tr(recurrenceNames[p.recurrence])}</td><td>{tr(statusNames[p.status])}</td><td>{canEdit && p.status === 'pending' && <form className="cash-actions" onSubmit={e => { e.preventDefault(); void paymentAction(p.id, 'pay', e.currentTarget) }}><label><span className="visually-hidden">{tr('Дата оплаты')}</span><input name="paid_date" type="date" defaultValue={today()} aria-label={tr('Дата оплаты')} required /></label><button className="button" disabled={busy}>{tr('Оплатить')}</button><button className="button" type="button" disabled={busy} onClick={() => void paymentAction(p.id, 'cancel')}>{tr('Отменить')}</button></form>}</td></tr>)}</tbody></table></div>
          {canEdit && !!report.accounts.length && <form className="cash-form" onSubmit={submit('payments', f => ({ account_id: accountId, due_date: value(f, 'due_date'), kind: value(f, 'kind'), amount: value(f, 'amount'), category: value(f, 'category'), description: value(f, 'description'), recurrence: value(f, 'recurrence') }))}><h3 className="cash-wide">{tr('Запланировать платёж')}</h3>{accountSelect}<label>{tr('Тип')}<select name="kind"><option value="expense">{tr('Списание')}</option><option value="income">{tr('Поступление')}</option></select></label><label>{tr('Дата платежа')}<input name="due_date" type="date" defaultValue={today()} required /></label>{amountField}{categoryField}<label>{tr('Повторение')}<select name="recurrence">{Object.entries(recurrenceNames).map(([k, v]) => <option key={k} value={k}>{tr(v)}</option>)}</select></label>{descriptionField}{actionButton}</form>}
          <details><summary>{tr('Ежедневный прогноз остатка')}</summary><div className="scroll-table cash-projection"><table><thead><tr><th>{tr('Дата')}</th><th>{tr('Ожидаемый остаток')}</th><th>{tr('Счета с дефицитом')}</th></tr></thead><tbody>{report.projection.map(p => <tr key={p.date}><td>{dateLabel(p.date, true)}</td><td>{money(p.balance)}</td><td>{p.gap_accounts.map(accountName).join(', ') || '—'}</td></tr>)}</tbody></table></div></details>
        </>}
        {tab === 'budgets' && <><h2>{tr('Бюджет и план-факт')}</h2><p>{tr('Бюджет расходов сравнивается с денежными списаниями за весь месяц начала выбранного периода. Переводы исключены. Повторное сохранение категории обновляет лимит.')}</p><div className="scroll-table"><table><thead><tr>{['Месяц', 'Категория', 'План', 'Факт', 'Осталось'].map(s => <th key={s}>{tr(s)}</th>)}</tr></thead><tbody>{report.budgets.map(b => <tr key={b.id}><td>{b.month.slice(0, 7)}</td><td>{b.category}</td><td>{money(b.amount)}</td><td>{money(b.actual)}</td><td>{money(b.remaining)}</td></tr>)}</tbody></table></div>
          {canEdit && <form className="cash-form" onSubmit={submit('budgets', f => ({ month: value(f, 'month') + '-01', category: value(f, 'category'), amount: value(f, 'amount') }))}><label>{tr('Месяц')}<input name="month" type="month" defaultValue={period.from.slice(0, 7)} required /></label>{categoryField}<label>{tr('Лимит расходов, ₸')}<input name="amount" type="number" min="0" step="0.01" required /></label>{actionButton}</form>}
        </>}
        {tab === 'exchange' && <><h2>{tr('Банк и 1С: файлы')}</h2><p>{tr('Выгрузите выписку из банка или 1С и приведите её к шаблону CSV/XLSX. Данные загружаются на выбранный счёт после проверки. Автоматическое подключение к банку или 1С не настроено.')}</p><a className="button" href="/templates/cash_statement.csv" download>{tr('Скачать шаблон выписки')}</a><p><code>date,kind,amount,category,description,reference</code></p><p>{tr('Дата: YYYY-MM-DD. Тип: income или expense. Сумма положительная, до двух знаков после точки. Номер операции обязателен и уникален в пределах счёта. XLSX: один лист, без формул. CSV: UTF-8, разделитель — запятая.')}</p>
          {canEdit && !!report.accounts.length && <><div className="cash-form">{accountSelect}<label>{tr('Файл CSV или XLSX')}<input type="file" accept=".csv,.xlsx" disabled={busy} onChange={e => { setFile(e.target.files?.[0] || null); setPreview(null); setSuccess('') }} /></label><button className="button" disabled={busy || !file} onClick={() => void statement(false)}>{tr('Проверить файл')}</button></div>
            {preview && <><p>{tr('Строк в файле:')} {preview.row_count}</p>{preview.errors.map((e, i) => <p className="field-error" key={i}>{e.row} · {e.field}: {e.message}</p>)}<div className="scroll-table"><table><thead><tr>{['Строка', 'Дата', 'Тип', 'Сумма, ₸', 'Категория', 'Номер операции'].map(s => <th key={s}>{tr(s)}</th>)}</tr></thead><tbody>{preview.preview.map(r => <tr key={r.source_row}><td>{r.source_row}</td><td>{r.data.date}</td><td>{tr(kindNames[r.data.kind])}</td><td>{money(r.data.amount)}</td><td>{r.data.category}</td><td>{r.data.reference}</td></tr>)}</tbody></table></div><button className="button primary" disabled={busy || !preview.can_confirm} onClick={() => void statement(true)}>{tr('Подтвердить импорт')}</button></>}
          </>}
        </>}
        {!canEdit && <p className="cash-hint">{tr('У вашей роли доступ только к просмотру.')}</p>}
      </section>
    </>}
  </div>
}
