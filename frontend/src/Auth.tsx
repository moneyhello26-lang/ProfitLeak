import { createContext, Fragment, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import type { components } from './types/api'
import { Link } from 'react-router'
import { BarChart3, ChevronRight, LoaderCircle, LogOut, ShieldCheck, Trash2, UserRound, UsersRound } from 'lucide-react'
import { api } from './lib/api'
import { getLocale, LanguageSwitcher, tr, useLocale } from './i18n'
import { invalidateAuthRequests } from './lib/authEpoch'
import './auth.css'

export type Role = components['schemas']['MembershipRead']['role']
type AccountSession = components['schemas']['AuthRead']
type Member = components['schemas']['MemberRead']
type AuthContextValue = {
  session: AccountSession
  reload: () => Promise<void>
  logout: () => Promise<void>
}
const AuthContext = createContext<AuthContextValue | null>(null)
export function useAuth() { return useContext(AuthContext)! }
export function useBusinessRole(businessId: string | null): Role | null {
  return useAuth().session.memberships.find(m => m.business_id === businessId)?.role || null
}
export function useCanEdit(businessId: string | null) {
  const role = useBusinessRole(businessId)
  return role === 'owner' || role === 'analyst'
}
export function roleLabel(role: Role) {
  return tr({ owner: 'Владелец', analyst: 'Аналитик', viewer: 'Наблюдатель' }[role])
}
const json = (value: unknown) => ({ headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })

async function currentAccount(signal?: AbortSignal): Promise<AccountSession | null> {
  let response: Response
  try {
    response = await fetch('/api/v1/auth/me', {
      credentials: 'include', headers: { 'Accept-Language': getLocale() }, cache: 'no-store', signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error(tr('Не удалось связаться с сервером. Проверьте подключение и попробуйте ещё раз.'))
  }
  if (response.status === 401) return null
  if (!response.ok) throw new Error(tr('Не удалось проверить аккаунт. Проверьте, что сервер запущен и миграции применены.'))
  return response.json() as Promise<AccountSession>
}

export function AuthGate({ children }: { children: ReactNode }) {
  const locale = useLocale()
  const [session, setSession] = useState<AccountSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const generation = useRef(0)
  const identity = useRef<string | null>(null)
  const acceptSession = useCallback((value: AccountSession | null) => {
    const next = value?.user.id || null
    if (next !== identity.current) { invalidateAuthRequests(); identity.current = next }
    setSession(value)
  }, [])
  const reload = useCallback(async () => {
    const requested = ++generation.current
    try {
      const value = await currentAccount()
      if (requested === generation.current) { acceptSession(value); setError(''); setLoading(false) }
    } catch (error) {
      if (requested === generation.current) { setError((error as Error).message); setLoading(false) }
      throw error
    }
  }, [acceptSession])
  useEffect(() => {
    const controller = new AbortController()
    const requested = ++generation.current
    currentAccount(controller.signal).then(value => {
      if (!controller.signal.aborted && requested === generation.current) { acceptSession(value); setError(''); setLoading(false) }
    }).catch(e => {
      if (!controller.signal.aborted && requested === generation.current) { setError(e.message); setLoading(false) }
    })
    return () => controller.abort()
  }, [revision, locale, acceptSession])
  useEffect(() => {
    const expired = () => { generation.current++; acceptSession(null); setError(''); setLoading(false) }
    window.addEventListener('profitleak:unauthorized', expired)
    return () => window.removeEventListener('profitleak:unauthorized', expired)
  }, [acceptSession])
  useEffect(() => {
    const check = () => { void reload().catch(() => { /* Keep the account visible during a connection failure. */ }) }
    const visible = () => { if (document.visibilityState === 'visible') check() }
    window.addEventListener('focus', check)
    document.addEventListener('visibilitychange', visible)
    return () => { window.removeEventListener('focus', check); document.removeEventListener('visibilitychange', visible) }
  }, [reload])
  const logout = useCallback(async () => {
    generation.current++
    invalidateAuthRequests()
    await api<void>('/auth/logout', { method: 'POST' })
    generation.current++
    acceptSession(null)
  }, [acceptSession])
  if (loading) return <div className="auth-loading" role="status"><LoaderCircle className="spin" size={24} />{tr('Проверяем аккаунт…')}</div>
  return session ? <AuthContext.Provider value={{ session, reload, logout }}><Fragment key={session.user.id}>{children}</Fragment></AuthContext.Provider> : <AuthForm
    error={error} retry={() => { setLoading(true); setRevision(v => v + 1) }}
    onAuthenticated={value => { generation.current++; acceptSession(value); setError('') }}
  />
}

function AuthForm({ onAuthenticated, error: connectionError, retry }: {
  onAuthenticated: (value: AccountSession) => void; error: string; retry: () => void
}) {
  useLocale()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError('')
    const fields = new FormData(e.currentTarget)
    const payload = {
      email: String(fields.get('email') || '').trim(), password: String(fields.get('password') || ''),
      ...(mode === 'register' ? { full_name: String(fields.get('full_name') || '').trim() } : {}),
    }
    if (mode === 'register' && payload.password !== fields.get('confirm_password')) {
      setError(tr('Пароли не совпадают.')); setBusy(false); return
    }
    try { onAuthenticated(await api<AccountSession>(`/auth/${mode}`, { method: 'POST', ...json(payload) })) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="auth-screen"><header className="auth-header"><Link to="/" className="brand"><span className="brand-icon"><BarChart3 size={24} /></span><span>ProfitLeak<span className="brand-ai">AI</span></span></Link><LanguageSwitcher /></header>
    <main className="auth-layout"><section className="auth-intro"><div className="eyebrow">{tr('ФИНАНСЫ ВАШЕГО БИЗНЕСА')}</div><h1>{tr('Ваши данные. Ваша команда.')}</h1><p>{tr('Сравнивайте периоды, находите причины потери прибыли и планируйте результаты в одном рабочем пространстве.')}</p><div className="auth-feature"><ShieldCheck size={22} /><div><strong>{tr('Доступ по ролям')}</strong><p>{tr('Владелец управляет командой, аналитик работает с данными, наблюдатель изучает отчёты.')}</p></div></div><div className="auth-feature"><UsersRound size={22} /><div><strong>{tr('Отдельные бизнесы')}</strong><p>{tr('Каждый аккаунт видит только свои компании и компании, к которым его пригласили.')}</p></div></div></section>
      <section className="panel auth-card"><div className="segmented auth-tabs"><button className={mode === 'login' ? 'selected' : ''} disabled={busy} onClick={() => { setMode('login'); setError('') }}>{tr('Вход')}</button><button className={mode === 'register' ? 'selected' : ''} disabled={busy} onClick={() => { setMode('register'); setError('') }}>{tr('Регистрация')}</button></div><h2>{mode === 'login' ? tr('Войти в аккаунт') : tr('Создать аккаунт')}</h2><p>{mode === 'login' ? tr('Введите email и пароль для доступа к вашим бизнесам.') : tr('Зарегистрируйтесь, затем создайте бизнес или попросите владельца добавить ваш email в команду.')}</p>
        {connectionError && <div className="auth-error" role="alert"><p>{connectionError}</p><button className="button" onClick={retry}>{tr('Повторить')}</button></div>}
        <form key={mode} className="auth-form" onSubmit={e => void submit(e)}>
          {mode === 'register' && <label>{tr('Имя')}<input name="full_name" autoComplete="name" required minLength={1} maxLength={120} disabled={busy} /></label>}
          <label>Email<input name="email" type="email" autoComplete="username" required maxLength={254} disabled={busy} /></label>
          <label>{tr('Пароль')}<input name="password" type="password" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required minLength={mode === 'register' ? 10 : 1} maxLength={128} disabled={busy} /></label>
          {mode === 'register' && <><small>{tr('Не менее 10 символов. Используйте отдельный пароль для этого сайта.')}</small><label>{tr('Повторите пароль')}<input name="confirm_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} disabled={busy} /></label></>}
          {error && <p className="field-error" role="alert">{error}</p>}
          <button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <ChevronRight size={17} />}{busy ? tr('Подождите…') : mode === 'login' ? tr('Войти') : tr('Зарегистрироваться')}</button>
        </form>
        {mode === 'register' && <p className="first-account-note">{tr('Первый зарегистрированный аккаунт станет владельцем бизнесов, созданных до добавления аккаунтов. Для последующих аккаунтов доступ выдаёт владелец.')}</p>}
      </section>
    </main><footer className="auth-footer">ProfitLeak AI · {tr('Русский и қазақша · KZT')}</footer>
  </div>
}

export function AuthActions({ businessId }: { businessId: string | null }) {
  useLocale()
  const { session, reload, logout } = useAuth()
  const role = useBusinessRole(businessId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { void reload().catch(() => { /* A business request displays connection failures. */ }) }, [businessId, reload])
  async function leave() {
    setBusy(true); setError('')
    try { await logout() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <div className="auth-actions">{role && <span className={`role-badge ${role}`}>{roleLabel(role)}</span>}<Link className="account-link" to="/account" title={tr('Аккаунт и команда')} aria-label={tr('Аккаунт и команда')}><UserRound size={18} /><span>{session.user.full_name}</span></Link><button className="button icon-button" title={tr('Выйти')} aria-label={tr('Выйти')} disabled={busy} onClick={() => void leave()}>{busy ? <LoaderCircle className="spin" size={17} /> : <LogOut size={17} />}</button>{error && <span className="auth-action-error" role="alert">{error}</span>}</div>
}

export function AccountPage({ businessId, businessName }: { businessId: string | null; businessName: string }) {
  useLocale()
  const { session, reload } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function changePassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError('')
    const fields = new FormData(e.currentTarget)
    const next = String(fields.get('new_password') || '')
    if (next !== fields.get('confirm_password')) { setError(tr('Пароли не совпадают.')); setBusy(false); return }
    try {
      await api<void>('/auth/password', { method: 'POST', ...json({ current_password: String(fields.get('current_password') || ''), new_password: next }) })
      await reload()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <><div className="page-heading"><div><div className="eyebrow">{tr('ДОСТУП И КОМАНДА')}</div><h1>{tr('Аккаунт и команда')}</h1><p>{tr('Профиль, пароль и участники выбранного бизнеса.')}</p></div></div>
    <div className="account-grid"><section className="panel"><div className="panel-heading"><div><h2>{tr('Ваш профиль')}</h2><p>{tr('Аккаунт используется для всех ваших бизнесов.')}</p></div><UserRound size={22} /></div><div className="account-body"><dl className="account-profile"><div><dt>{tr('Имя')}</dt><dd>{session.user.full_name}</dd></div><div><dt>Email</dt><dd>{session.user.email}</dd></div><div><dt>{tr('Доступных бизнесов')}</dt><dd>{session.memberships.length}</dd></div></dl><Link className="button" to="/settings">{tr('Управление бизнесами')}<ChevronRight size={15} /></Link></div></section>
      <section className="panel"><div className="panel-heading"><div><h2>{tr('Изменить пароль')}</h2><p>{tr('После изменения все сеансы завершатся. Войдите с новым паролем.')}</p></div><ShieldCheck size={22} /></div><form className="auth-form account-body" onSubmit={e => void changePassword(e)}><label>{tr('Текущий пароль')}<input name="current_password" type="password" autoComplete="current-password" required maxLength={128} disabled={busy} /></label><label>{tr('Новый пароль')}<input name="new_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} disabled={busy} /></label><label>{tr('Повторите новый пароль')}<input name="confirm_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} disabled={busy} /></label>{error && <p className="field-error" role="alert">{error}</p>}<button className="button primary" disabled={busy}>{busy ? tr('Сохраняем…') : tr('Сохранить пароль')}</button></form></section></div>
    {businessId ? <TeamPanel key={businessId} businessId={businessId} businessName={businessName} /> : <div className="notice"><CircleNotice />{tr('Создайте бизнес в разделе «Мой бизнес», чтобы добавить участников.')}</div>}
  </>
}

function CircleNotice() { return <UsersRound size={20} /> }

function TeamPanel({ businessId, businessName }: { businessId: string; businessName: string }) {
  const locale = useLocale()
  const { session, reload } = useAuth()
  const role = useBusinessRole(businessId)
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [removing, setRemoving] = useState<Member | null>(null)
  useEffect(() => {
    if (role !== 'owner') { setMembers([]); setLoading(false); return }
    const controller = new AbortController()
    setLoading(true); setError('')
    api<Member[]>(`/businesses/${businessId}/members`, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) { setMembers(result); setLoading(false) }
    }).catch(e => { if (!controller.signal.aborted) { setError(e.message); setLoading(false) } })
    return () => controller.abort()
  }, [businessId, role, locale, revision])
  async function mutate(path: string, init: RequestInit, message: string) {
    setBusy(true); setError(''); setSuccess('')
    try {
      await api<unknown>(path, init)
      setSuccess(message); setRemoving(null); await reload(); setRevision(v => v + 1)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const fields = new FormData(form)
    await mutate(`/businesses/${businessId}/members`, {
      method: 'POST', ...json({ email: String(fields.get('email') || '').trim(), role: String(fields.get('role') || 'analyst') }),
    }, 'Участник добавлен.')
  }
  return <section className="panel team-panel"><div className="panel-heading"><div><h2>{tr('Команда бизнеса')} · {businessName}</h2><p>{tr('Ваша роль: {role}', { role: role ? roleLabel(role) : tr('Нет доступа') })}</p></div><UsersRound size={22} /></div><div className="account-body"><div className="role-guide"><div><strong>{tr('Владелец')}</strong><p>{tr('Просмотр, импорт, анализ и управление участниками.')}</p></div><div><strong>{tr('Аналитик')}</strong><p>{tr('Просмотр, импорт и запуск анализа. Без управления командой.')}</p></div><div><strong>{tr('Наблюдатель')}</strong><p>{tr('Просмотр показателей, сравнения, прогноза, PDF и советника.')}</p></div></div>
      {role !== 'owner' ? <div className="notice"><ShieldCheck size={19} /><span>{tr('Участниками и ролями управляет владелец бизнеса.')}</span></div> : <>
        <form className="member-form" onSubmit={e => void add(e)}><label>{tr('Email зарегистрированного пользователя')}<input name="email" type="email" required maxLength={254} disabled={busy} placeholder="name@example.com" /></label><label>{tr('Роль')}<select name="role" defaultValue="analyst" disabled={busy}>{(['analyst', 'viewer', 'owner'] as Role[]).map(r => <option key={r} value={r}>{roleLabel(r)}</option>)}</select></label><button className="button primary" disabled={busy}>{busy ? tr('Сохраняем…') : tr('Добавить участника')}</button></form><p className="form-hint">{tr('Пользователь должен сначала зарегистрироваться на этом сайте. Письма и ссылки приглашения не отправляются.')}</p>
        {loading ? <div className="loading" role="status">{tr('Загружаем участников…')}</div> : <div className="scroll-table"><table><thead><tr><th>{tr('Участник')}</th><th>{tr('Роль')}</th><th>{tr('Действия')}</th></tr></thead><tbody>{members.map(member => <tr key={member.user_id}><td><strong>{member.full_name}{member.user_id === session.user.id ? ` · ${tr('Вы')}` : ''}</strong><small className="table-detail">{member.email}</small></td><td><select aria-label={tr('Роль участника {email}', { email: member.email })} value={member.role} disabled={busy} onChange={e => void mutate(`/businesses/${businessId}/members/${member.user_id}`, { method: 'PATCH', ...json({ role: e.target.value }) }, 'Роль изменена.')}>{(['owner', 'analyst', 'viewer'] as Role[]).map(r => <option key={r} value={r}>{roleLabel(r)}</option>)}</select></td><td><button className="button icon-button" aria-label={tr('Удалить участника {email}', { email: member.email })} disabled={busy || member.user_id === session.user.id} onClick={() => setRemoving(member)}><Trash2 size={16} /></button></td></tr>)}</tbody></table></div>}
        {removing && <div className="member-remove-confirm" role="alert"><p>{tr('Отозвать доступ к этому бизнесу у {email}?', { email: removing.email })}</p><div><button className="button" disabled={busy} onClick={() => setRemoving(null)}>{tr('Отмена')}</button><button className="button danger" disabled={busy} onClick={() => void mutate(`/businesses/${businessId}/members/${removing.user_id}`, { method: 'DELETE' }, 'Доступ участника отозван.')}>{tr('Отозвать доступ')}</button></div></div>}
        <p className="form-hint">{tr('Последнего владельца нельзя удалить или понизить в роли.')}</p>
      </>}
      {error && <p className="field-error" role="alert">{error}</p>}{success && <p className="success-text" role="status">{tr(success)}</p>}
    </div></section>
}
