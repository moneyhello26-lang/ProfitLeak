# Бесплатная публикация: Render Free + Neon Free

Пользователь выбрал бюджет 0 ₸. Это основной вариант для демонстрационного
выпуска 17 октября; платный VPS из DEPLOYMENT.md остаётся альтернативой на будущее.
Исходники готовы к этой схеме. Владелец создал Neon ProfitLeak (PostgreSQL 18,
Ohio); Render ещё настраивается.

## Как устроено

Один Render web service собирает React и запускает FastAPI.
Они используют общий адрес `https://ИМЯ.onrender.com`, поэтому отдельный
домен и отдельный хостинг frontend не требуются. PostgreSQL находится в Neon,
а не на временном диске Render. Локальная SQLite продолжает работать как раньше.

Условия проверены 16.10.2026:

- [Render Free](https://render.com/docs/free): сервис засыпает после простоя,
  первый запрос после сна может ждать около минуты; локальные файлы не сохраняются.
  Площадка позиционирует этот тариф для разработки и демонстраций.
- [Neon Free](https://neon.com/pricing): бесплатный план без срока окончания
  и без обязательной карты, с ограничениями ресурсов. Не включать платный план.
- Бесплатная PostgreSQL самого Render ограничена 30 днями; для этого варианта
  используется Neon. Его квоты нужно отслеживать в консоли.

## 1. Подготовить источник

В GitHub должны находиться все изменения, включая `render.yaml`, миграцию 0006,
новый `backend/scripts/start_hosted.py` и frontend. Не публиковать `.env`, БД,
резервные копии и `.tmp`. Render нужно дать доступ именно к этому репозиторию.
Если изменения находятся в release-ветке, выбрать эту ветку в Render.

Из корня проекта перед публикацией:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe backend/scripts/export_openapi.py --check
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

## 2. Создать Neon Free

1. Войти в [Neon Console](https://console.neon.tech/).
2. Создать проект `profitleak` на плане Free, выбрать регион рядом с Render
   (для подготовленного конфига — Ohio), PostgreSQL 18, если доступна.
3. Открыть Connect и скопировать **direct connection** (Connection pooling выключен).
   Для одного процесса этого достаточно; тот же адрес подходит для миграций.
4. Строка вида `postgresql://.../neondb?sslmode=require&channel_binding=require`
   является секретом. Вставить её только в DATABASE_URL на Render.

Приложение автоматически выбирает psycopg для `postgres://` и `postgresql://`,
сохраняя пароль и параметры TLS.
[Как получить подключение](https://neon.com/docs/connect/connect-from-any-app).

## 3. Создать Render Free

Войти в [Render Dashboard](https://dashboard.render.com/), открыть New → Blueprint,
выбрать репозиторий ProfitLeak и ветку с подготовленным `render.yaml`.
Проверить, что service plan — **Free**, нет дисков или дополнительных платных
ресурсов. Ввести DATABASE_URL из Neon. IMPORT_SIGNING_KEY генерируется площадкой.

При ручном создании Web Service использовать:

| Настройка | Значение |
| --- | --- |
| Runtime | Python |
| Region | Ohio |
| Plan | Free |
| Root directory | пусто, корень репозитория |
| Build command | `python -m pip install './backend[postgres]' && npm --prefix frontend ci && npm --prefix frontend run build` |
| Start command | `python backend/scripts/start_hosted.py` |
| Health check | `/api/v1/health` |
| PYTHON_VERSION | `3.14.0` |
| NODE_VERSION | `24.15.0` |
| DATABASE_URL | секрет подключения к Neon |
| IMPORT_SIGNING_KEY | случайная строка не короче 32 символов |
| SESSION_COOKIE_SECURE | `true` |
| LLM_ENABLED | `false` |
| FORWARDED_ALLOW_IPS | `*` (только за входным прокси Render) |

У Render в Python runtime есть Node/npm, поэтому обе части собираются вместе.
[Native runtimes](https://render.com/docs/native-runtimes),
[FastAPI deploy](https://render.com/docs/deploy-fastapi),
[Blueprint](https://render.com/docs/blueprint-spec).

На бесплатном тарифе не использовать pre-deploy command. Стартовый скрипт
проверяет настройки, применяет Alembic, затем запускает один процесс Uvicorn
на PORT площадки. При ошибке миграции HTTP-сервер не запускается.
FRONTEND_DIST задаётся автоматически; CORS_ORIGINS берётся из RENDER_EXTERNAL_URL.
Для другого домена CORS_ORIGINS нужно задать явно JSON-массивом HTTPS-адресов.

После успешного размещения не удалять и не менять IMPORT_SIGNING_KEY при
обычном рестарте. LLM можно подключить отдельно по LLM_ADVISOR_GUIDE.md;
для первого показа локальных рекомендаций достаточно.

## 4. Приёмка опубликованного приложения

1. `/api/v1/health` возвращает `{"status":"ok","database":"ok"}`.
2. Открывается `/insights` напрямую и после обновления страницы.
3. Зарегистрировать свой аккаунт, открыть демо, запустить анализ.
4. Проверить показатели, исходные строки и PDF; переключить RU/ҚАЗ.
5. Установить статус «В работе» и заметку. Обновить страницу, повторить анализ:
   данные сохраняются у совпадающего сигнала того же периода.
6. Загрузить CSV/XLSX: ошибка → корректный предпросмотр → подтверждение →
   повторный файл без дублирования. Обновить анализ после нового импорта.
7. В другом аккаунте бизнес первого пользователя не виден.
8. Перезапустить web service; аккаунт, бизнес, импорты и заметки сохранены.
9. Открыть с телефона/другого устройства и проверить загрузку после простоя.

Уже созданная локальная SQLite автоматически в Neon не переносится. Для первого
показа создайте новое демо через интерфейс; реальные данные переносятся отдельно.

## Резервная копия PostgreSQL

SQLite-утилита `sqlite_snapshot.py` для Neon не подходит. Используйте pg_dump /
pg_restore от PostgreSQL той же основной версии, что сервер, или новее.
Установленная локально PostgreSQL 18 подходит для сервера 18.

В терминале задайте PGHOST, PGDATABASE, PGUSER, PGPASSWORD и PGSSLMODE=require
из Neon Connect. Не отправляйте пароль в чат и не коммитьте его.
Используйте direct host, без `-pooler`. Затем:

```powershell
& 'C:/Program Files/PostgreSQL/18/bin/pg_dump.exe' --format=custom --no-owner --no-acl --file profitleak-backup.dump
```

Храните копию отдельно от приложения с ограниченным доступом. Для проверки
восстановления создайте новую пустую БД/ветку в пределах Free, укажите её параметры
PGHOST/PGDATABASE/PGUSER/PGPASSWORD и выполните:

```powershell
& 'C:/Program Files/PostgreSQL/18/bin/pg_restore.exe' --exit-on-error --single-transaction --no-owner --no-acl --dbname $env:PGDATABASE profitleak-backup.dump
```

Не восстанавливайте поверх работающей БД. После операции удалите PGPASSWORD
из окружения терминала. Автоматическое расписание копий ещё не настроено.

## Что понадобится от владельца аккаунта

Вход в Neon и Render, создание ресурсов Free и предоставление Render доступа
к GitHub-репозиторию. Все настройки и код выше подготовлены; этих доступов
у агента пока нет. Публикация не подтверждается до проверки реального HTTPS-URL.
