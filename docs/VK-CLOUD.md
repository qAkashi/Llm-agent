# Подключение VK Cloud

Доступ к облаку не требуется для локального стенда. Пример ниже не содержит реальных ключей.
Создайте отдельный приватный бакет и техническую учётную запись в своём проекте VK Cloud.
Возьмите endpoint и регион из панели именно своего проекта.
Для Москвы в официальной документации указан `https://hb.ru-msk.vkcloud-storage.ru`;
пример `region: ru-msk` нужно проверить для своего аккаунта.

1. Запишите пару ключей в приватный файл вне репозитория:

   ```ini
   [default]
   aws_access_key_id=YOUR_ACCESS_KEY
   aws_secret_access_key=YOUR_SECRET_KEY
   ```

2. Создайте Secret из файла, не передавая ключи как аргументы командной строки:

   ```powershell
   .\tools\bin\kubectl.exe --kubeconfig .\work\kubeconfig --context kind-practice1 -n velero create secret generic vk-s3 --from-file=cloud=C:\private\vk.credentials
   ```

3. Скопируйте `config/vk-cloud-bsl.yaml` в `work/`, замените имя бакета, endpoint и регион.
   Примените файл и проверьте `status.phase: Available`:

   ```powershell
   .\tools\bin\kubectl.exe --kubeconfig .\work\kubeconfig --context kind-practice1 apply -f .\work\vk-cloud-bsl.yaml
   .\tools\bin\kubectl.exe --kubeconfig .\work\kubeconfig --context kind-practice1 -n velero get backupstoragelocation vk-cloud -o yaml
   ```

4. Создайте отдельный Backup с `storageLocation: vk-cloud` или настройте шаблон Schedule.
   Предварительно выполните малую тестовую копию и восстановление с проверкой данных.
   Не меняйте default во время активного копирования. `lab.py` по умолчанию намеренно проверяет MinIO.

Минимальная политика для отдельного бакета:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect":"Allow", "Action":["s3:ListBucket","s3:GetBucketLocation","s3:ListBucketMultipartUploads"],
     "Resource":"arn:aws:s3:::YOUR_BUCKET"},
    {"Effect":"Allow", "Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],
     "Resource":"arn:aws:s3:::YOUR_BUCKET/*"}
  ]
}
```

Применимость действий и синтаксис политики проверьте в VK Cloud. Для версионируемых бакетов могут понадобиться
операции с версиями объектов. Не отключайте TLS-проверку для решения ошибок доступа.
При ошибке checksum уточните поддержку выбранной пары AWS plugin/S3 API; не добавляйте обходные параметры
без воспроизведения проблемы и проверки восстановления. Пример подключения не является выполненным тестом VK Cloud.
