import { kk } from './translations.ts'
import { authKk } from './auth.translations.ts'

export type Locale = 'ru' | 'kk'
const storageKey = 'profitleak.locale'
const listeners = new Set<() => void>()
let locale: Locale = 'ru'
try { if (typeof localStorage !== 'undefined' && localStorage.getItem(storageKey) === 'kk') locale = 'kk' } catch { /* Storage is optional. */ }

export function getLocale(): Locale { return locale }
export function localeTag(): string { return locale === 'kk' ? 'kk-KZ' : 'ru-KZ' }
export function setLocale(next: Locale) {
  if (next !== 'ru' && next !== 'kk') return
  if (locale === next) return
  locale = next
  try { if (typeof localStorage !== 'undefined') localStorage.setItem(storageKey, next) } catch { /* Storage is optional. */ }
  for (const listener of listeners) listener()
}
export function subscribeLocale(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }
export function tr(source: string, params: Record<string, string | number> = {}): string {
  const text = locale === 'kk' ? kk[source] ?? authKk[source] ?? source : source
  return text.replace(/\{([A-Za-z0-9_]+)\}/g, (placeholder, name: string) => Object.hasOwn(params, name) ? String(params[name]) : placeholder)
}

// Translate only explicitly enumerated product/category/status labels, never user data.
export function localizedRecord<T extends Record<string, string>>(source: T): T {
  return Object.defineProperties({}, Object.fromEntries(Object.entries(source).map(([key, value]) => [key, { enumerable: true, get: () => tr(value) }]))) as T
}

if (typeof window !== 'undefined') window.addEventListener('storage', event => {
  if (event.key === storageKey) setLocale(event.newValue === 'kk' ? 'kk' : 'ru')
})
