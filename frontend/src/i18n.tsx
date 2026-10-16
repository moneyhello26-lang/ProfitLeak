import { useEffect, useSyncExternalStore } from 'react'
import { getLocale, setLocale, subscribeLocale, tr } from './locale.ts'
export { getLocale, localeTag, localizedRecord, setLocale, tr } from './locale.ts'
export type { Locale } from './locale.ts'

export function useLocale() {
  const locale = useSyncExternalStore(subscribeLocale, getLocale, () => 'ru' as const)
  useEffect(() => {
    document.documentElement.lang = locale
    document.title = locale === 'kk' ? 'ProfitLeak AI — Бизнес қаржысын талдау' : 'ProfitLeak AI — Аналитика финансов бизнеса'
  }, [locale])
  return locale
}

export function LanguageSwitcher() {
  useLocale()
  return <label className="language-switcher"><span className="visually-hidden">{tr('Язык')}</span><select aria-label={tr('Язык')} value={getLocale()} onChange={event => setLocale(event.target.value === 'kk' ? 'kk' : 'ru')}><option value="ru">RU</option><option value="kk">ҚАЗ</option></select></label>
}
