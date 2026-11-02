# Воспроизводимость и проверенные особенности среды

Дата проверки: 02.11.2026.

- Первоначально на ПК не было Docker, kubectl, kind и Velero. Установлен Docker Desktop 4.97.0
  в профиль пользователя, backend WSL2, без перезагрузки. Docker Engine сообщает 29.9.2.
- GitHub API ограничивал анонимные запросы. Установщик CLI умеет получать release assets и
  опубликованные SHA-256 напрямую без API. Контрольная сумма проверяется в обоих вариантах.
- Публичные Community-образы MinIO возвращали 401 / pull access denied. Поэтому используются
  локальные сборки из официальных исходников. Сборка MinIO: тег RELEASE.2025-04-22T22-12-26Z,
  commit `0d7408fc9969caf07de6a8c3a84f9fbb10a6739e`. Сборка mc: тег RELEASE.2025-04-16T18-13-26Z,
  commit `b00526b153a31b36767991a4f5ce2cced435ee8e`.
- Windows CLI Velero 1.18.3 сформировал hostPath node-agent как `\var\lib\kubelet\pods`.
  Для Linux-узлов kind это неверно. Bootstrap нормализует пути до `/var/lib/kubelet/pods`
  и `/var/lib/kubelet/plugins`, затем ожидает готовность Deployment и DaemonSet.
- Отчёт отличает исправленные ошибки подготовки от намеренных проверок S3 и Restore.
  Ранние неуспешные прогоны сохранены локально в reports/runs; в комплект сдачи выбирается полный PASS.
- При исключении физических PV восстановленные PVC сохраняли старый volumeName и оставались Pending.
  ConfigMap `practice1-restore-modifiers` удаляет volumeName, bind-completed, bound-by-controller и
  selected-node до создания PVC. Повторный прогон проверяет выдачу новых PV и импорт данных.

MinIO и mc распространяются на условиях upstream-лицензий; файлы LICENSE сохранены в образах.
Ссылки на неизменённые исходники приведены выше и в Dockerfile. Архив проекта не содержит собранных
бинарных образов стороннего ПО, а содержит инструкции их воспроизводимой сборки.
