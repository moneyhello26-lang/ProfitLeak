# Публикация на одном Linux-сервере без Docker

> Дополнительная историческая инструкция для сервера. Текущий согласованный
> выпуск — локальный проект без облачных сервисов: [LOCAL_RELEASE.md](LOCAL_RELEASE.md).

Пользователь выбрал только бесплатный хостинг. Текущий основной вариант —
[Render Free + Neon Free](FREE_DEPLOYMENT.md). Инструкция VPS ниже оставлена
как альтернатива и не означает согласия на расходы.

Подготовленный вариант: FastAPI обслуживает API и production-сборку React,
Caddy принимает HTTPS и передаёт запросы на 127.0.0.1:8000.
SQLite хранится в /var/lib/profitleak, приложение работает одним процессом.
Это переносимый вариант; сервер и домен ещё не выбраны и не оплачены.

Для текущего релиза рекомендован VPS с постоянным диском: конфигурация ниже
подготовлена для него и сохраняет работу без Docker. Если удобнее управляемая
площадка, рассматривайте [Render с persistent disk](https://render.com/docs/disks)
или [Railway с volume](https://docs.railway.com/volumes/reference).
У Render постоянный диск требует платного сервиса;
[бесплатный web service не сохраняет локальные файлы](https://render.com/docs/free).
С SQLite такой тариф не подходит для хранения аккаунтов и данных между запусками.
Цены, регион и бюджет должны быть согласованы до оформления услуги.

## Подготовка

Нужен сервер с постоянным диском, Python 3.11+, Node.js 22.18+, Caddy,
systemd и доменом. Для сборки и scrypt-проверки паролей разумный старт —
2 ГБ памяти; это инженерная оценка, нагрузочное тестирование ещё не выполнено.
DNS A/AAAA домена должны указывать на сервер, TCP 80/443 доступны извне.
Не публикуйте порт 8000 наружу. Можно собрать frontend на другом компьютере
и перенести frontend/dist, тогда Node.js на работающем сервере не требуется.

Разместите проверенный исходный код в /opt/profitleak. Создайте отдельного
системного пользователя profitleak и каталог /var/lib/profitleak с владельцем
profitleak и правами 700. Код должен читаться этим пользователем.

Из /opt/profitleak:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install ./backend
npm --prefix frontend ci
npm --prefix frontend run build
```

## Переменные сервера

Создайте /etc/profitleak.env с владельцем root и правами 600. Не копируйте
локальную .env на сервер и не помещайте секреты в Git. Пример содержимого
(замените домен и ключ):

```ini
DATABASE_URL=sqlite:////var/lib/profitleak/profitleak.db
FRONTEND_DIST=/opt/profitleak/frontend/dist
CORS_ORIGINS='["https://your-domain.example"]'
IMPORT_SIGNING_KEY=REPLACE_WITH_A_RANDOM_SECRET
SESSION_COOKIE_SECURE=true
LLM_ENABLED=false
```

Ключ сгенерируйте локально на сервере:

```sh
backend/.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Для внешнего советника отдельно настройте провайдера по LLM_ADVISOR_GUIDE.md.
Первая публикация может работать с локальными рекомендациями без API-ключа.

## Службы

Скопируйте deploy/profitleak.service в /etc/systemd/system/profitleak.service.
Он применяет миграции перед запуском, слушает loopback и доверяет proxy-заголовкам
только локального Caddy. Запустите:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now profitleak
curl --fail http://127.0.0.1:8000/api/v1/health
```

В /etc/caddy/Caddyfile используйте deploy/Caddyfile, заменив
`{$PROFITLEAK_DOMAIN}` реальным доменом, например `app.example.kz`.
Либо передайте PROFITLEAK_DOMAIN в окружение службы Caddy, не приложения.
Проверьте конфигурацию и перезагрузите службу:

```sh
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy получает сертификат автоматически при выполнении условий DNS и доступа
к портам: [Automatic HTTPS](https://caddyserver.com/docs/automatic-https),
[reverse proxy](https://caddyserver.com/docs/quick-starts/reverse-proxy).

Проверьте https://ВАШ-ДОМЕН/api/v1/health, регистрацию, демо, импорт, анализ,
PDF и перезагрузку https://ВАШ-ДОМЕН/insights. Второй аккаунт не должен видеть
бизнес первого. После перезапуска profitleak данные должны сохраняться.

## Резервная копия и восстановление

Утилита использует SQLite backup API, включая зафиксированные данные WAL,
и проверяет целостность и внешние ключи. Источник открывается только для чтения,
файл назначения обязан отсутствовать. Каталог копий должен существовать
и иметь доступ только у администратора/службы; копии содержат финансовые
данные и сессии пользователей. Храните отдельную копию за пределами сервера.

```sh
umask 077
sudo -u profitleak /opt/profitleak/backend/.venv/bin/python /opt/profitleak/backend/scripts/sqlite_snapshot.py backup /var/lib/profitleak/profitleak.db /var/lib/profitleak/backup-20261016.db
```

Для проверки восстановите в НОВЫЙ файл:

```sh
sudo -u profitleak /opt/profitleak/backend/.venv/bin/python /opt/profitleak/backend/scripts/sqlite_snapshot.py restore /var/lib/profitleak/backup-20261016.db /var/lib/profitleak/restored-20261016.db
```

При настоящем восстановлении остановите приложение, сохраните текущую БД,
укажите новый файл в DATABASE_URL и запустите службу. Не заменяйте открытую БД
и не переносите WAL/SHM отдельно. Убедитесь, что копия совместима с версией кода.

## Обновление и откат

До обновления сохраните копию БД и предыдущую версию кода/сборки.
Остановите службу, установите зависимости и соберите frontend, затем запустите
службу и проверьте health и пользовательский путь. При неудаче остановите её,
верните предыдущий код и восстановите совместимую копию в новый файл.
Автоматический downgrade миграций на рабочей базе не предусмотрен.

Журналы: `journalctl -u profitleak -n 100 --no-pager`.
Шаблоны systemd/Caddy подготовлены, но на реальном Linux-сервере ещё не проверены.
