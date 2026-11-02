# Стенд готов к демонстрации

Рабочая папка: `C:\Users\kamil\OneDrive\Desktop\practice1`.
Кластер: `practice1`, контекст: `kind-practice1`.
Проверенное приложение: namespace `practice1-restore-retry-65b7`.
Дополнительно оставлен результат штатного восстановления: `practice1-restore-main-a97b`.
Исходный namespace `practice1-app` удалён в ходе проверки. MinIO и Velero работают.

В PowerShell из этой папки:

```powershell
.\run.ps1 verify --target practice1-restore-retry-65b7
.\tools\bin\kubectl.exe --kubeconfig .\work\kubeconfig --context kind-practice1 -n practice1-restore-retry-65b7 port-forward svc/api 3000:3000 --address 127.0.0.1
```

Откройте `http://127.0.0.1:3000/orders?order=id&limit=10`.
Ежедневное расписание поставлено на паузу после удаления источника. Для возобновления сначала
измените его includedNamespaces на имя выбранного восстановленного приложения.

Отчёт: `reports/technical-report.pdf` (10 страниц). Журналы: `reports/evidence/`.
Для нового полного эксперимента: `.\run.ps1 demo`. Подробности в `docs/RUNBOOK.md`.
Публикация не выполнялась; локальный Git готов для добавления вашего remote и push.
