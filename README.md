# practice1: резервное копирование Kubernetes в S3

Учебный стенд: **kind + PostgreSQL + PostgREST + MinIO + Velero/Kopia**.
Автоматический сценарий создаёт контрольную БД, проверяет настоящую плановую и ручную копии,
удаляет исходный namespace, восстанавливает приложение в новый и проверяет целостность.
Дополнительно проверяются отсутствующий бакет, неверный ключ, запрет доступа и прерывание Restore.

**Проверено 02.11.2026:** полный локальный прогон PASS; 13 unit-проверок PASS.
Восстановление с проверкой приложения: 33,641 с; повторное после сбоя: 34,062 с.
SHA-256 данных до и после совпал. [Отчёт PDF, 10 страниц](reports/technical-report.pdf),
[измерения](reports/validation-summary.json), [журналы](reports/evidence/README.md).

## Быстрый запуск

Требуются Docker с Linux-контейнерами и Python 3.10+; рекомендовано 4 CPU, 8 ГБ RAM и 15 ГБ диска.
CLI устанавливаются в `tools/bin`, версии закреплены в `config/versions.json`.

```powershell
python -m pip install -r requirements.txt
python scripts/install_tools.py
.\run.ps1 demo
```

В Linux/macOS:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/install_tools.py
export PATH="$PWD/tools/bin:$PATH"
python scripts/lab.py demo
```

Полный `demo` предназначен для отдельного учебного кластера `practice1`.
Он удаляет только `practice1-app` и собственный namespace прерванного восстановления.
Контекст задаётся явно: `kind-practice1`, kubeconfig хранится в `work/kubeconfig`.
Обычный kubeconfig пользователя не используется. При повторном запуске используйте отдельные команды,
описанные в [эксплуатационной инструкции](docs/RUNBOOK.md), либо пересоздайте учебный кластер.

## Что входит в копию

- Объекты namespace: Pod PostgreSQL, Deployment API, Service, PVC, ConfigMap, Secret.
- Согласованный архив `pg_dump`, его SHA-256, размер и время создания на томе `backup-data`.
- Байты тома `backup-data`, передаваемые Velero FSB/Kopia в MinIO.

Рабочие файлы `PGDATA` не копируются: после восстановления новый том инициализируется,
и в него импортируется дамп. Проверка не запускает `seed.sql` после восстановления.
Иначе повторное создание тестовых данных могло бы скрыть потерю резервной копии.

## Результаты и файлы

| Каталог | Содержимое |
|---|---|
| `manifests/` | Kubernetes-манифесты, StorageClass, расписание |
| `config/` | kind, закреплённые версии, шаблон VK Cloud |
| `scripts/` | Управление стендом, дамп, импорт и отчёт |
| `sql/seed.sql` | 100 пользователей, 1000 заказов, сумма 8 508 500 копеек |
| `tests/` | Проверки целостности и защитных ограничений |
| `reports/runs/` | Фактические журналы, JSON/CSV с длительностями; исключены из Git |
| `reports/` | Технический отчёт и подготовленная сводка проверки |
| `work/` | Приватные ключи, kubeconfig, состояние; исключены из Git |

Критерий успеха: `result.json: PASS`, Restore и все PodVolumeRestore завершены,
дамп импортирован, SHA-256 до и после совпадает, схема и sequence проверены, API возвращает контрольный заказ.
Фаза Velero `Completed` без проверки приложения не считается достаточной.

Инструкции: [оператор](docs/RUNBOOK.md), [ошибки](docs/FAILURES.md),
[безопасность](docs/SECURITY.md), [VK Cloud](docs/VK-CLOUD.md), [источники](docs/SOURCES.md).

## Публикация в Git

Локальный Git подготовлен; внешнего remote и публикации нет.
Перед отправкой убедитесь, что `git status` не содержит `work/`, ключей, kubeconfig или дампов.

```bash
git remote add origin <URL-ВАШЕГО-РЕПОЗИТОРИЯ>
git push -u origin main
```

Архив для сдачи формируется только из отслеживаемых Git-файлов и проверенного отчёта.
Не загружайте на платформу всю рабочую папку с `work/`.
