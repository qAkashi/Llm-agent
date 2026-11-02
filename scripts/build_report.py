import json
from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
REPORTS.mkdir(exist_ok=True)
fonts = [(Path('C:/Windows/Fonts/arial.ttf'), Path('C:/Windows/Fonts/arialbd.ttf')),
         (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))]
regular, bold = next(pair for pair in fonts if all(x.exists() for x in pair))
pdfmetrics.registerFont(TTFont('Body', str(regular)))
pdfmetrics.registerFont(TTFont('BodyBold', str(bold)))
pdfmetrics.registerFontFamily('Body', normal='Body', bold='BodyBold', italic='Body', boldItalic='BodyBold')
NAVY = colors.HexColor('#16324f')
TEAL = colors.HexColor('#007f87')
GRAY = colors.HexColor('#5b6875')
LIGHT = colors.HexColor('#edf3f7')
styles = {
    'title': ParagraphStyle('Title', fontName='BodyBold', fontSize=27, leading=33, textColor=NAVY, spaceAfter=16),
    'h1': ParagraphStyle('H1', fontName='BodyBold', fontSize=19, leading=24, textColor=NAVY, spaceAfter=14),
    'h2': ParagraphStyle('H2', fontName='BodyBold', fontSize=12, leading=16, textColor=TEAL, spaceBefore=10, spaceAfter=6),
    'body': ParagraphStyle('Body', fontName='Body', fontSize=10.3, leading=15, spaceAfter=9),
    'small': ParagraphStyle('Small', fontName='Body', fontSize=8.3, leading=11.7, spaceAfter=6),
    'cell': ParagraphStyle('Cell', fontName='Body', fontSize=8.8, leading=12),
    'code': ParagraphStyle('Code', fontName='Body', fontSize=9, leading=13, backColor=LIGHT, borderPadding=8, spaceAfter=11),
    'label': ParagraphStyle('Label', fontName='BodyBold', fontSize=10, leading=14, textColor=TEAL, spaceAfter=12)
}
story, markdown = [], []

def p(text, style='body'):
    story.append(Paragraph(escape(text).replace('\n', '<br/>'), styles[style]))
    markdown.append(text + '\n')

def heading(text):
    p(text, 'h2')

def page(number, title):
    if number > 1:
        story.append(PageBreak())
    p(f'PRACTICE1   /   ТЕХНИЧЕСКИЙ ОТЧЁТ   /   {number:02d}', 'label')
    p(title, 'title' if number == 1 else 'h1')
    markdown.append('\n')

def table(headers, rows, widths):
    data = [[Paragraph(escape(str(value)), styles['cell']) for value in row] for row in [headers] + rows]
    tbl = Table(data, colWidths=[v * mm for v in widths], repeatRows=1, hAlign='LEFT')
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT), ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('LINEBELOW', (0, 0), (-1, 0), 0.8, TEAL),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#d4dde5'))]))
    story.append(tbl)
    story.append(Spacer(1, 9))
    markdown.append('| ' + ' | '.join(headers) + ' |\n|' + '|'.join(['---'] * len(headers)) + '|')
    markdown.extend('| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows)
    markdown.append('\n')

runs = sorted((REPORTS / 'runs').glob('*'))
successful = []
for path in runs:
    result_path = path / 'result.json'
    if result_path.exists():
        result = json.loads(result_path.read_text())
        if result.get('command') == 'demo' and result.get('status') == 'PASS':
            successful.append(path)
chosen = successful[-1] if successful else (runs[-1] if runs else None)
steps = json.loads((chosen / 'steps.json').read_text()) if chosen and (chosen / 'steps.json').exists() else []
state = json.loads((ROOT / 'work/state.json').read_text()) if (ROOT / 'work/state.json').exists() else {}
baseline = state.get('baseline', {})
verifications = sorted(chosen.glob('*verification*.json')) if chosen else []
verification = json.loads(verifications[-1].read_text()) if verifications else {}
dump_bytes = (chosen / 'dump-bytes.txt').read_text().strip() if chosen and (chosen / 'dump-bytes.txt').exists() else 'не измерено'
bucket_size = 'не измерено'
if chosen:
    for log_path in sorted(chosen.glob('minio-*.log')):
        lines = log_path.read_text(encoding='utf-8').splitlines()
        if lines and lines[0].startswith('{'):
            try:
                du = json.loads(lines[0])
                if 'objects' in du and 'size' in du and 'prefix' in du:
                    bucket_size = f"{du['size']} байт; {du['objects']} объектов (включая предыдущие копии)"
            except ValueError:
                pass
status = 'ПОЛНЫЙ ПРОГОН: PASS' if successful else 'ПОЛНЫЙ ПРОГОН НЕ ПОДТВЕРЖДЁН'
versions = json.loads((ROOT / 'config/versions.json').read_text())

page(1, 'Резервное копирование\nKubernetes-приложения\nв S3')
p('Локальный стенд, восстановление в чистом namespace и проверка целостности', 'h2')
p('Проект practice1 • 02 ноября 2026 года • Windows / Docker / kind', 'small')
story.append(Spacer(1, 14 * mm))
p(status, 'h2')
p('Цель работы - создать воспроизводимый цикл защиты приложения: подготовить контрольные данные PostgreSQL, '
  'сохранить объекты Kubernetes и согласованный дамп в S3, удалить исходное приложение, восстановить его в новом '
  'пространстве имён и проверить результат на уровне данных и API.')
p('Основной результат - исходный код стенда, манифесты, сценарии штатных и аварийных операций, эксплуатационная '
  'инструкция и реальные журналы с длительностями. Облачный вариант VK Cloud описан отдельно; учётные данные '
  'облака не использовались. Публикацию локального Git-репозитория выполняет пользователь.')
heading('Состав отчёта')
table(['Страница', 'Раздел'], [
    ['2', 'Архитектура и границы стенда'], ['3', 'Данные и согласованность копии'],
    ['4', 'Развёртывание и конфигурация'], ['5', 'Ручное и плановое копирование'],
    ['6', 'Восстановление и критерии приёмки'], ['7', 'Проверка отказов'],
    ['8', 'Секреты и подключение VK Cloud'], ['9', 'Фактические измерения'],
    ['10', 'Инструкция сдачи, ограничения и источники']], [23, 147])

page(2, 'Архитектура стенда')
p('На компьютере запущен один узел kind. Отдельный kubeconfig и явный контекст kind-practice1 изолируют '
  'сценарии от других кластеров пользователя. Локальный provisioner создаёт PV типа local; размер в PVC '
  'задаёт запрос ресурса, но для локального хранилища не заменяет контроль свободного места на диске.')
table(['Область', 'Компоненты и назначение'], [
    ['practice1-app', 'PostgreSQL, API PostgREST, Service, Secret, ConfigMap; PVC pgdata (2 GiB) и backup-data (1 GiB).'],
    ['practice1-storage', 'MinIO, Service ClusterIP, PVC 5 GiB, Secret администратора и технических пользователей, служебные Job mc.'],
    ['velero', 'Сервер Velero, node-agent, AWS plugin, BackupStorageLocation, Schedule, Backup, Restore, PVB/PVR.'],
    ['practice1-restore-*', 'Новый namespace с восстановленными объектами, новым PGDATA и импортированным дампом.'],
    ['Хост: practice1', 'Манифесты, Python-сценарии, отчёт и журналы; приватное состояние в work/.']], [41, 129])
heading('Поток резервирования')
p('PostgreSQL → pg_dump → PVC backup-data → Velero FSB / Kopia → S3 MinIO.\n'
  'Объекты Kubernetes → Velero AWS plugin → тот же приватный бакет.\n'
  'S3 → новый PVC backup-data → проверка SHA-256 → pg_restore → новый PostgreSQL → SQL + HTTP-проверка.', 'code')
p('Снимки облачных дисков отключены. Аннотация Pod явно выбирает только backup-data для файлового '
  'резервирования. Описания PVC входят в копию, физические PV и их привязка к исходному узлу не переносятся. '
  'StorageClass заранее установлен на целевом кластере, а восстановление создаёт новые тома.')
p('Restore использует ConfigMap resource modifiers: из PVC удаляются старый volumeName и аннотации '
  'привязки. Без этого при исключённых физических PV ссылки на удалённые тома оставляли PVC в Pending.', 'small')
heading('Граница доказанного восстановления')
p('MinIO находится в том же кластере, но вне namespace приложения. Это позволяет проверить удаление '
  'приложения и его данных, сохранив резервную копию. Потеря всего kind-кластера, диска или компьютера '
  'уничтожит и локальный MinIO. Для такой аварии нужен внешний S3, отдельно сохранённые ключи '
  'и пароль репозитория. Отказоустойчивость production-системы здесь не заявляется.')
p('Основание: документация Kubernetes PV, Velero FSB и Rancher Local Path Provisioner; см. источники 1, 6, 7.', 'small')

page(3, 'Контрольные данные и согласованность')
table(['Параметр', 'Значение'], [
    ['accounts', '100 строк: id и уникальное имя account-NNN'],
    ['orders', '1000 строк: id, внешний ключ account_id, amount_cents, description'],
    ['Сумма amount_cents', '8 508 500; целочисленные копейки исключают ошибки float'],
    ['Ограничения', '2 primary key, 1 unique, 1 foreign key, 1 check'],
    ['Sequence', 'orders_id_seq: last_value=1000; is_called=true'],
    ['Эталон SHA-256', baseline.get('sha256', 'не получен')]], [42, 128])
p('seed.sql выполняется только при первоначальной подготовке пустой базы. API использует роль reader '
  'с правом SELECT и default_transaction_read_only. Во время контрольного эксперимента писателей нет; '
  'это делает сравнение до и после копии однозначным. При появлении production-писателей контрольный '
  'эталон должен вычисляться из того же snapshot, что и дамп, либо должна вводиться пауза записи.')
heading('Почему выбран логический дамп')
p('PostgreSQL pg_dump создаёт согласованный архив одной базы. Формат custom используется для '
  'pg_restore; параметры no-owner и no-acl отделяют данные от кластерных ролей. Роль reader создаётся '
  'отдельно при инициализации. Глобальные роли, tablespace и PITR/WAL не входят в этот вариант копии. '
  'Файловое копирование активного PGDATA здесь не применяется.')
heading('Два разных контроля целостности')
p('Первый SHA-256 относится к файлу app.dump: он проверяется перед импортом и обнаруживает повреждение '
  'архива. Второй SHA-256 относится к данным: таблицы выгружаются в CSV с фиксированным набором '
  'столбцов и ORDER BY id; строки нормализуются по LF, таблицы разделяются метками. Такой хеш обнаруживает '
  'изменение значения даже при сохранении общего числа строк и суммы.')
p('Дополнительно сравниваются количество accounts/orders, сумма, ограничения схемы, sequence и '
  'ответ /orders?order=id&limit=1. В unit-тесте специально меняются местами суммы двух строк: '
  'агрегат остаётся равным, а SHA-256 различается. Это проверяет смысл контрольной процедуры.')
p('Основание: PostgreSQL 17 pg_dump/pg_restore; контрольный набор и алгоритм хеширования определены кодом проекта.', 'small')

page(4, 'Развёртывание и конфигурация')
table(['Компонент', 'Закреплённая версия / режим'], [
    ['kind / Kubernetes', versions['kind'] + ' / ' + versions['kubernetes']],
    ['Velero / AWS plugin', versions['velero'] + ' / ' + versions['aws_plugin']],
    ['PostgreSQL / API', versions['postgres'] + ' / ' + versions['postgrest']],
    ['MinIO / mc', 'Сборка официальных исходников из релизов 22.04.2025 / 16.04.2025'],
    ['FSB', 'Kopia, node-agent, opt-in по аннотации, snapshots=false']], [43, 127])
p('На рабочей станции первоначально отсутствовали Docker, kind, kubectl и Velero. Docker Desktop '
  'установлен в профиль пользователя с WSL2 и запущен без перезагрузки. CLI загружены в tools/bin '
  'с проверкой SHA-256 издателя. Node image kind закреплён digest, а версия приложения - явными тегами.')
p('Первый запуск обнаружил отказ реестра при загрузке Community-образов MinIO. Репозиторий MinIO '
  'описывает распространение исходным кодом. Поэтому проект содержит Dockerfile.minio и Dockerfile.mc: '
  'сборка из официального Git-тега, затем kind load docker-image. Повторный bootstrap использует локальный '
  'кеш. Исходники не модифицируются; лицензия сохраняется в образе.')
heading('Последовательность bootstrap')
p('Проверка Linux Docker → кластер и namespaces → StorageClass → сборка образов → случайные ключи '
  'и Secret → MinIO и бакет → Velero и node-agent → проверка BSL Available → приложение → '
  'заполнение БД → проверка API и PV → ежедневное расписание.')
p('python scripts/install_tools.py\npython -m pip install -r requirements.txt\n.\\run.ps1 bootstrap', 'code')
p('Velero запускается с provider=aws, s3ForcePathStyle=true, локальным s3Url и region=us-east-1. '
  'Создаётся отдельный технический пользователь MinIO, которому доступны операции только в бакете '
  'practice1-backups. У root-пользователя остаются административные операции создания бакета и политик.')
p('Ошибки любого шага дают ненулевой код завершения, файл result.json: FAIL и диагностику Pod/Event. '
  'Частичный запуск не помечается успешным. Повторный запуск не перезаполняет уже существующую контрольную БД.')

page(5, 'Ручная и плановая резервные копии')
p('Backup включает только practice1-app. Из копии исключаются events, jobs и persistentvolumes; '
  'includeClusterResources=false, snapshotVolumes=false, defaultVolumesToFsBackup=false. '
  'PVC backup-data выбирается аннотацией Pod. Ручной Backup и Schedule используют один шаблон.')
heading('Pre-hook и post-hook')
p('Pre-hook получает атомарную блокировку каталогом .dump-lock, запускает pg_dump во временный файл, '
  'проверяет читаемость оглавления и заменяет app.dump. Затем записываются app.dump.sha256, '
  'dump-bytes.txt и dump-created-utc.txt. Post-hook освобождает блокировку после чтения тома Velero. '
  'on-error=Fail запрещает считать ошибку подготовки успешной копией.')
table(['Механизм', 'Параметры / проверка'], [
    ['Ручной запуск', '.\\run.ps1 backup; уникальное имя Backup; ожидание терминальной фазы.'],
    ['Ежедневный Schedule', '0 23 * * * UTC; 02:00 по Москве следующего дня; TTL 168 часов.'],
    ['Проверка планировщика', 'Отдельный Schedule * * * * *; фактически созданный контроллером Backup; затем пауза и очистка Schedule.'],
    ['Готовность копии', 'Completed, errors=0, ровно один завершённый PVB backup-data и totalBytes > 0.'],
    ['Фактический размер дампа', str(dump_bytes) + ' байт' if str(dump_bytes).isdigit() else str(dump_bytes)],
    ['Бакет после ручной копии', bucket_size]], [42, 128])
p('После завершения сохраняются JSON Backup/PVB, журнал Velero, размер дампа и инвентаризация бакета mc ls '
  'с mc du. Размер дампа, объём прочитанных FSB-данных и полный размер бакета различны: S3 также содержит '
  'метаданные, журналы и служебные объекты Kopia. Дедупликация влияет на физически занятый объём.')
heading('Условия допустимого удаления')
p('Скрипт повторно проверяет состояние копии и данные источника, а также метку принадлежности namespace '
  'стенду. После этого приостанавливает ежедневный Schedule и удаляет practice1-app. '
  'Готовность одной лишь копии Kubernetes-объектов недостаточна: отсутствие PVB запрещает удаление.')
p('Срок хранения управляется Velero. Самостоятельное удаление блоков Kopia или несогласованный S3 lifecycle '
  'могут повредить несколько дедуплицированных копий. Для очистки используются штатные операции Velero.')

page(6, 'Восстановление и критерии приёмки')
p('Restore создаётся только для отсутствующего namespace с префиксом practice1-restore-. '
  'namespaceMapping переносит practice1-app в целевое имя. Исходный namespace к этому моменту удалён. '
  'Восстановление в существующую среду запрещено, чтобы не смешивать старые и восстановленные данные.')
heading('Порядок восстановления')
p('1. Velero читает описания объектов и восстанавливает PVC, конфигурацию, Secret и приложение.\n'
  '2. Provisioner выдаёт новые локальные PV. FSB восстанавливает /backup.\n'
  '3. Init-контейнер Velero пропускает запуск приложения после завершения переноса тома.\n'
  '4. PostgreSQL инициализирует пустой PGDATA; restore.sh проверяет файл и импортирует архив одной транзакцией.\n'
  '5. После Ready выполняются SQL-проверки и HTTP-запрос к API.')
table(['Уровень', 'Условие приёмки'], [
    ['Velero', 'Restore Completed, errors=0; PodVolumeRestore существуют и все Completed.'],
    ['Контейнеры', 'PostgreSQL Ready; Deployment API доступен; лог содержит RESTORE_IMPORT_COMPLETED.'],
    ['Файл', 'sha256sum --check app.dump.sha256 завершается успешно до импорта.'],
    ['Данные', 'Хеш совпадает с эталоном; 100 accounts, 1000 orders, сумма 8 508 500.'],
    ['Схема', '5 ограничений; sequence 1000|t.'],
    ['Приложение', 'Первый заказ: id=1, account_id=1, amount_cents=17, description=order-0001.']], [36, 134])
p('Если PostgreSQL уже имеет данные, штатный entrypoint не выполняет импорт повторно. Наличие маркера '
  'в журнале и запрет существующего namespace не позволяют выдать такой запуск за проверку чистого '
  'восстановления. seed.sql после Restore не вызывается ни явно, ни через init-скрипты.')
p('Фактическое сравнение: ' + ('SHA-256 и контрольные данные совпали.' if verification.get('equal') else 'успешное сравнение пока не подтверждено.'))
p('В завершённых Restore зарегистрированы 3 предупреждения: два об исключённых физических PV и одно '
  'об уже существующей kube-root-ca.crt. Они проверены: новые PVC Bound, том восстановлен, данные и API '
  'верны. Ненулевое число ошибок при этом недопустимо.', 'small')
p('Для этого эксперимента RTO определяется от начала операции Restore до конца проверки данных/API, включая предварительную проверку копии. '
  'Это более строгая граница, чем время появления фазы Completed. Плановый RPO зависит от интервала '
  'расписания и возраста последней действительно успешной копии.')

page(7, 'Проверка отказов и действия оператора')
table(['Сбой', 'Инъекция и ожидаемый сигнал', 'Восстановление работы'], [
    ['Нет бакета', 'Уникальное отсутствующее имя, правильные ключи; BSL Unavailable, NoSuchBucket.', 'Проверить endpoint/регион/имя; создать бакет; дождаться Available.'],
    ['Неверный ключ', 'Несуществующий Access Key ID; InvalidAccessKeyId либо отказ доступа.', 'Обновить пару ключей через Secret; повторить проверку BSL.'],
    ['Нет разрешений', 'Реальный пользователь с Deny-политикой; AccessDenied/Forbidden.', 'Исправить bucket/object права; учесть явный Deny.'],
    ['Прерван Restore', 'Node-agent временно заблокирован; активный Restore и PVR; сервер Velero перезапущен.', 'Вернуть agent; сохранить логи; удалить частичный namespace; новый Restore.']], [30, 73, 67])
p('Три теста S3 создают отдельные BackupStorageLocation и Secret. После проверки диагностического сообщения '
  'создаётся реальный Backup в неисправную BSL: ожидается отказ, а не Completed. Временные BSL/Secret '
  'очищаются, рабочая default должна остаться Available. Это проверяет реакцию Velero, а не только '
  'возможность выполнить команду клиента S3.')
heading('Как исключается ложная проверка прерывания')
p('Перед перезапуском сервера сценарий обязан увидеть активный Restore и PodVolumeRestore. '
  'Блокировка node-agent оставляет окно для детерминированной инъекции. Если Restore успел завершиться '
  'раньше, тест считается неуспешным. finally возвращает исходный nodeSelector и реплики сервера. '
  'Затем выполняется повторное восстановление в новом чистом namespace с полной проверкой данных.')
p('Перезапуск сервера Velero прерывает его текущие операции. Такой тест допустим в выделенном учебном '
  'кластере, где не выполняются сторонние копии. Состояние Failed/PartiallyFailed не означает, что '
  'восстановленные объекты автоматически удалены: очистка частичной среды выполняется отдельно.')
heading('При любой ошибке')
p('Не переключать пользователей на неподтверждённую БД. Сохранить Restore/Backup/PVB/PVR JSON, '
  'логи Velero и PostgreSQL, события Pod, время начала и завершения. Устранить причину и использовать '
  'новый namespace. Наличие файлов в S3 не заменяет проверку восстановления.')

page(8, 'Секреты и подключение VK Cloud')
p('Секреты генерируются криптографически случайно; в репозиторий входят только ссылки secretKeyRef. '
  'В kubectl данные передаются через stdin, а payload и секретные ответы не записываются в журнал команд. '
  'Приватные файлы, kubeconfig и сырые журналы исключены из Git. Перед публикацией проверяются '
  'отслеживаемые файлы и содержимое архива.')
table(['Не публиковать', 'Почему / где хранится'], [
    ['Пароли PostgreSQL и API', 'Secret приложения и приватное work/; API URI также содержит пароль.'],
    ['S3 access/secret key', 'Secret Velero; отдельная пара ключей для каждого хранилища.'],
    ['MinIO root credentials', 'Только административные Job; рабочему Velero не выдаются.'],
    ['Пароль Kopia repository', 'Нужен для чтения репозитория после потери установки; сохранить отдельно.'],
    ['kubeconfig и дампы', 'Доступ к кластеру и содержимое базы; не отправлять в Git/публичный архив.']], [55, 115])
p('Secret Kubernetes - кодирование base64, а не шифрование. Secret приложения входит в резервную '
  'копию объектов. Шифрование данных Kopia не следует распространять как обещание на все файлы '
  'Velero в бакете. Нужны приватность S3, TLS, защита ключей, ACL и шифрование хранилища.')
p('Рабочий стол расположен в OneDrive: исключение из Git не отключает синхронизацию ОС. '
  'Для production-ключей приватный каталог следует вынести из синхронизируемой папки. '
  'Локальный HTTP MinIO и привилегированный node-agent являются ограничениями учебной среды.')
heading('Вариант VK Cloud')
p('Создать приватный бакет и технический S3-аккаунт. В config/vk-cloud-bsl.yaml указать свой бакет, '
  'endpoint и регион. Пример Москвы: https://hb.ru-msk.vkcloud-storage.ru, region=ru-msk; '
  'значения сверяются с текущим проектом. Secret vk-s3 создаётся из приватного AWS credentials-файла.')
p('После применения отдельной BSL vk-cloud дождаться Available, создать малую копию с '
  'storageLocation=vk-cloud и выполнить тест Restore. Требуются ListBucket/GetBucketLocation и '
  'операции Get/Put/Delete/multipart над объектами своего бакета. TLS-проверку не отключать. '
  'Подключение к VK Cloud в данном прогоне не выполнялось; инструкция и шаблон предоставлены.')

page(9, 'Фактические журналы и измерения')
p('Источник измерений: ' + (chosen.name if chosen else 'прогон отсутствует') + '. '
  'Длительности получены monotonic-таймером Python; метки времени записаны в UTC. '
  'На рабочей станции использовалось московское время UTC+3.', 'small')
labels = {
    'preflight': 'Проверка окружения', 'create-kind-cluster': 'Создание / проверка kind',
    'build-and-load-minio-images': 'Сборка / загрузка MinIO', 'generate-private-secrets': 'Создание Secret',
    'deploy-minio-and-create-bucket': 'MinIO и бакет', 'install-velero': 'Установка Velero',
    'deploy-app-and-seed': 'Приложение и контрольные данные', 'install-daily-schedule': 'Ежедневный Schedule',
    'scheduled-backup-proof': 'Проверка плановой копии', 'manual-backup': 'Ручная копия и размер S3',
    'failure-missing-bucket': 'Сбой: нет бакета', 'failure-wrong-key': 'Сбой: неверный ключ',
    'failure-access-denied': 'Сбой: запрет доступа', 'delete-source-namespace': 'Удаление исходного namespace',
    'restore-to-new-namespace': 'Восстановление в новый namespace',
    'verify-data-schema-and-api': 'Проверка данных, схемы, API', 'failure-interrupted-restore': 'Прерывание Restore и очистка'}
rows = [[labels.get(x['step'], x['step']), x['status'], f"{x['seconds']:.3f}"] for x in steps]
table(['Операция', 'Статус', 'Секунды'], rows or [['Нет измерений', 'НЕ ПРОВЕРЕНО', '-']], [119, 24, 27])
restore_pairs = []
for i, row in enumerate(steps[:-1]):
    if row['step'] == 'restore-to-new-namespace' and steps[i+1]['step'] == 'verify-data-schema-and-api':
        restore_pairs.append(round(row['seconds'] + steps[i+1]['seconds'], 3))
p('RTO до подтверждённого приложения: ' + (', '.join(str(v) + ' с' for v in restore_pairs) if restore_pairs else 'не измерено') +
  '. Размер логического дампа: ' + str(dump_bytes) + (' байт.' if str(dump_bytes).isdigit() else '.'), 'small')
p('Таблица отражает один выбранный прогон, а не статистическую оценку производительности. '
  'Повторная сборка использует кеш, скачивание образов и первая инициализация увеличивают длительность. '
  'Исходные JSON/CSV и безопасные выдержки журнала включены в комплект сдачи.', 'small')
p('Дополнительно выполнены 13 unit-проверок; все прошли. Проверен синтаксис Bash-скриптов. '
  'Unit-проверки дополняют реальное восстановление, а не заменяют его.', 'small')

page(10, 'Эксплуатация, сдача и источники')
heading('Повторение и передача результата')
p('Полный цикл: .\\run.ps1 demo. Отдельные операции: bootstrap, backup, scheduled-proof, '
  'destroy-app, restore --target practice1-restore-check, verify, failures, interrupt. '
  'Завершённый demo оставляет восстановленное приложение и MinIO доступными в кластере, '
  'а ежедневное расписание исходного namespace - на паузе. Для продолжения резервирования '
  'измените namespace в Schedule и только затем снимите паузу.')
p('Для платформы подготовлены Git-исходники, манифесты, сценарии, отчёт и проверенные результаты. '
  'Пользователь добавляет remote и выполняет push. Содержимое work/ и сырые резервные копии '
  'в публичный архив не входят. Для полного удаления стенда используется kind delete cluster --name practice1; '
  'это также удаляет локальный MinIO, поэтому предварительно сохраните нужные копии во внешнем S3.')
heading('Ограничения')
p('Один узел, одна база, неизменяемый контрольный набор; без PITR, HA, нагрузочного теста и проверки '
  'полной потери кластера. MinIO Community собирается из закреплённого архивного релиза исключительно '
  'для практики. VK Cloud описан, но не проверен учётными данными пользователя. '
  'Фактический PASS относится только к выполненному локальному сценарию.')
heading('Первичные источники (проверены 02.11.2026)')
refs = [
 ('1-4. Kubernetes: PV, Secret, Namespace, Job', 'https://kubernetes.io/docs/concepts/'),
 ('5. kind v0.33.0 и образы узлов', 'https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0'),
 ('6. Local Path Provisioner', 'https://github.com/rancher/local-path-provisioner'),
 ('7. Velero: File System Backup', 'https://velero.io/docs/v1.18/file-system-backup/'),
 ('8-9. Velero: hooks и restore', 'https://velero.io/docs/v1.18/backup-hooks/'),
 ('10. AWS plugin: совместимость', 'https://github.com/velero-io/velero-plugin-for-aws'),
 ('11. PostgreSQL: pg_dump', 'https://www.postgresql.org/docs/17/app-pgdump.html'),
 ('12. MinIO: исходники и способ сборки', 'https://github.com/minio/minio'),
 ('13. VK Cloud: документация S3', 'https://github.com/vk-cs/docs-public/tree/master/docs/ru/storage/s3'),
 ('14. Docker Desktop: Windows', 'https://docs.docker.com/desktop/setup/install/windows-install/')]
for label, url in refs:
    story.append(Paragraph(escape(label) + '<br/><link href="' + url + '" color="#007f87">' + url + '</link>', styles['small']))
    markdown.append(f'{label}: {url}\n')
p('Точные тематические ссылки и дополнительные пояснения находятся в docs/SOURCES.md. '
  'Реализация и журналы проекта являются источником экспериментальных результатов.', 'small')

def footer(canvas, doc):
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(0.7)
    canvas.line(20 * mm, 17 * mm, 190 * mm, 17 * mm)
    canvas.setFont('Body', 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(20 * mm, 12 * mm, 'practice1 | Kubernetes · PostgreSQL · S3')
    canvas.drawRightString(190 * mm, 12 * mm, f'{doc.page} / 10')

doc = SimpleDocTemplate(str(REPORTS / 'technical-report.pdf'), pagesize=(210 * mm, 297 * mm),
                        rightMargin=20 * mm, leftMargin=20 * mm, topMargin=19 * mm, bottomMargin=23 * mm,
                        title='practice1: Kubernetes backup and restore', author='practice1')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
(REPORTS / 'technical-report.md').write_text('\n'.join(markdown), encoding='utf-8')
summary = {'status': status, 'evidence_run': chosen.name if chosen else None, 'baseline': baseline,
           'dump_bytes': dump_bytes, 'bucket_size_at_backup': bucket_size, 'restore_and_verify_seconds': restore_pairs, 'steps': steps,
           'vk_cloud_tested': False}
(REPORTS / 'validation-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(REPORTS / 'technical-report.pdf')
