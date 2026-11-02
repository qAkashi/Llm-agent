# Эксплуатационная инструкция

## 1. Подготовка

Запустите Docker Desktop в режиме Linux containers. `docker info` должен отвечать без ошибок.
На Windows `run.ps1` находит CLI в `tools/bin`, Docker Desktop и Python в виртуальном окружении
или в установленном окружении этой рабочей станции. На другом ПК установите Python и зависимости.
Имена ресурсов фиксированы, поэтому используйте отдельный кластер `practice1`.

```powershell
.\run.ps1 preflight
.\run.ps1 bootstrap
```

Bootstrap создаёт namespace `practice1-app`, `practice1-storage`, `velero`, StorageClass `practice1-local`,
Secret и два PVC приложения. `defaultVolumeType: local` обеспечивает local PV вместо hostPath PV.
MinIO использует свой PVC и отдельного S3-пользователя с правами только на учебный бакет.
Права администратора MinIO не передаются рабочему Velero.

В Windows CLI Velero может сформировать hostPath с обратными слешами. Сценарий нормализует
hostPath node-agent в Linux-формат перед ожиданием Ready.
MinIO и mc собираются из официальных исходников Dockerfile в каталоге docker/ и загружаются в kind;
это устраняет зависимость от снятых с публикации Community-образов. Первая сборка требует сети и нескольких минут.

Версии и контейнеры записаны в `config/versions.json`; Kubernetes node image закреплён digest.
Теги остальных контейнеров фиксированы; фактически загруженные digest следует сохранять вместе с результатами.
Это учебная комбинация версий, а не рекомендация использовать её без обновления в production.

## 2. Копирование

```powershell
.\run.ps1 backup
.\run.ps1 scheduled-proof
```

Ежедневное расписание `0 23 * * *` выполняется в UTC: 02:00 следующего дня по Москве.
TTL копий составляет 168 часов. `scheduled-proof` создаёт отдельное минутное расписание,
дожидается Backup с меткой `velero.io/schedule-name`, приостанавливает и удаляет это расписание.
Ручной запуск по шаблону Schedule не выдаётся за проверку планировщика.

Pre-hook создаёт `pg_dump -Fc --no-owner --no-acl`, проверяет его оглавление и вычисляет SHA-256.
Параллельный запуск защищён каталогом-блокировкой; post-hook снимает блокировку после FSB.
Ошибка hook прерывает успешное завершение Backup. При аварии блокировка может остаться:
удаляйте `/backup/.dump-lock` только после проверки отсутствия активных Backup/PVB.

## 3. Удаление и восстановление

```powershell
.\run.ps1 destroy-app
.\run.ps1 restore --target practice1-restore-check
.\run.ps1 verify --target practice1-restore-check
```

Используется имя последнего успешного Backup из `work/state.json`; можно указать `--backup NAME`.
Удаление разрешено только при Completed, нулевых errors, завершённом PodVolumeBackup с ненулевым объёмом
и совпадении текущих данных с сохранённым эталоном. Перед удалением ежедневное расписание приостанавливается.
Namespace восстановления должен отсутствовать и иметь префикс `practice1-restore-`.
В существующий namespace сценарий намеренно не восстанавливает.

Velero переносит имена namespace, восстанавливает описания PVC и данные `/backup`.
ConfigMap `practice1-restore-modifiers` очищает старые volumeName и аннотации привязки PVC.
StorageClass создаёт новые PV. FSB init container должен закончиться до запуска PostgreSQL.
Стандартная инициализация PostgreSQL на пустом PGDATA выполняет `restore.sh`:
проверяет SHA-256 дампа, импортирует его одной транзакцией и выдаёт read-only права API.
Строка `RESTORE_IMPORT_COMPLETED` фиксирует именно успешный импорт.

Проверка сравнивает 100 accounts, 1000 orders, сумму 8 508 500, канонический SHA-256,
пять ограничений схемы, состояние sequence `1000|t` и JSON API для первого заказа.
Во время измерения приложение не содержит писателей; API использует роль reader.
Для изменяемой production-БД эталон нужно связывать с тем же snapshot, что и дамп.

## 4. Сценарии сбоев

```powershell
.\run.ps1 failures
.\run.ps1 interrupt
```

Ошибки S3 создаются в отдельных BackupStorageLocation и Secret, рабочая `default` не редактируется.
Тест прерывания временно останавливает node-agent посредством nodeSelector, начинает Restore,
дожидается незавершённого PodVolumeRestore и перезапускает сервер Velero.
Ограничение node-agent снимается в `finally`; затем частичный namespace удаляется и восстановление
повторяется в другом чистом namespace. Не запускайте этот тест рядом с чужими операциями Velero.

## 5. Наблюдение

```powershell
$env:KUBECONFIG = "$PWD/work/kubeconfig"
.\tools\bin\kubectl.exe --context kind-practice1 get pods -A
.\tools\bin\velero.exe --kubeconfig $env:KUBECONFIG backup get
.\tools\bin\velero.exe --kubeconfig $env:KUBECONFIG restore get
.\tools\bin\kubectl.exe --context kind-practice1 -n velero get podvolumebackups,podvolumerestores
```

Для просмотра API после восстановления:

```powershell
.\tools\bin\kubectl.exe --kubeconfig .\work\kubeconfig --context kind-practice1 -n <NAMESPACE> port-forward svc/api 3000:3000 --address 127.0.0.1
```

Откройте `http://127.0.0.1:3000/orders?order=id&limit=10`.
После удаления исходного namespace ежедневное расписание остаётся на паузе, чтобы не создавать пустые копии.
Для дальнейшего копирования восстановленного приложения измените includedNamespaces на новый namespace
и снимите paused; это новая область резервирования.

## 6. Журналы и измерения

В `reports/runs/<команда-время-id>/` сохраняются:

- `steps.csv`, `steps.json`: начало/конец UTC, фактические секунды, PASS/FAIL;
- `commands.jsonl`: команды, stdout/stderr, returncode; секретные payload исключены;
- Backup/Restore/PVB/PVR JSON и журналы Velero;
- размер дампа, инвентаризация S3, сравнение контрольных данных и проверка API;
- диагностические Pod/Event при ошибке.

Размер S3 включает метаданные, логи и Kopia, поэтому он не равен размеру pg_dump.
RTO в отчёте измеряется от начала операции Restore (включая предварительную проверку копии)
до успешной проверки API и данных.
Период расписания определяет плановый верхний предел RPO; задержки, сбои и длительность дампа его увеличивают.
Нулевой RPO не заявляется.

## 7. Остановка и очистка

Остановка Docker сохраняет стенд на диске. Для полной очистки именно этого учебного кластера:

```powershell
.\tools\bin\kind.exe delete cluster --name practice1
```

Команда удалит также MinIO и все его локальные копии. Сначала экспортируйте нужные копии во внешнее S3.
Файлы `work/` с секретами остаются локально; удаляйте их только когда они больше не нужны.
