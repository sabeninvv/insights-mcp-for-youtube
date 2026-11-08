# youtube-insights

Локальный MCP-сервер для аналитики своего YouTube-канала. Только чтение: три read-only scope, GET-запросы к API Google, ноль зависимостей. Данные идут напрямую между вашим компьютером и Google.

Инструменты: `channel`, `videos`, `video`, `analytics`.

## Настройка Google Cloud

Один раз, примерно 20 минут.

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/).
2. Включите **YouTube Data API v3** и **YouTube Analytics API**.
3. Настройте OAuth consent screen: тип External, себя добавьте в Test users.
4. В Credentials создайте OAuth client ID типа **Desktop app** и скачайте JSON.

## Секреты

Держите папку вне iCloud и Dropbox.

```bash
mkdir -p -m 700 ~/.config/youtube-insights
```

```bash
mv ~/Downloads/client_secret_*.json ~/.config/youtube-insights/client_secret.json
```

## Вход

```bash
YOUTUBE_SECRETS_DIR=~/.config/youtube-insights uv run youtube-insights auth
```

На экране Google должны быть только три разрешения:

- View your YouTube account
- View YouTube Analytics reports for your YouTube content
- View monetary and non-monetary YouTube Analytics reports for your YouTube content

Если видите «edit», «delete» или «manage», остановитесь и не подтверждайте.
Если вход уже выполнялся, повторите `auth`: старый токен выдан на два разрешения, и Google откажет в денежных метриках.

## Подключение к Claude Desktop

Файл `~/Library/Application Support/Claude/claude_desktop_config.json`. Путь к `uv` укажите полностью, его подскажет `which uv`: приложения с графическим интерфейсом не видят `PATH` из вашей оболочки.

```json
{
  "mcpServers": {
    "youtube": {
      "command": "/Users/<user>/.local/bin/uv",
      "args": ["run", "--directory", "/Users/<user>/Projects/insights-mcp-for-youtube", "youtube-insights"],
      "env": {"YOUTUBE_SECRETS_DIR": "/Users/<user>/.config/youtube-insights"}
    }
  }
}
```

## Примеры запросов к `analytics`

Даты `start_date` и `end_date` обязательны во всех запросах.

| Отчёт | Параметры |
| --- | --- |
| Канал по дням | `metrics=views,estimatedMinutesWatched,subscribersGained`, `dimensions=day` |
| Топ видео | `metrics=views,estimatedMinutesWatched`, `dimensions=video`, `sort=-views`, `max_results=10` |
| Shorts и другие форматы | `metrics=views,engagedViews`, `dimensions=day,creatorContentType` |
| Удержание видео | `metrics=audienceWatchRatio,totalSegmentImpressions`, `dimensions=elapsedVideoTimeRatio`, `filters=video==ID` (точка = доля длины видео, секунды = доля × `contentDetails.duration` из `video`) |
| Источники трафика | `metrics=views`, `dimensions=insightTrafficSourceType`, `sort=-views` |
| Демография | `metrics=viewerPercentage`, `dimensions=ageGroup,gender` |
| Доход по дням | `metrics=estimatedRevenue,monetizedPlaybacks,playbackBasedCpm`, `dimensions=day`, `currency=EUR` |
| Поисковые запросы | `metrics=views`, `dimensions=insightTrafficSourceDetail`, `filters=insightTrafficSourceType==YT_SEARCH`, `sort=-views`, `max_results=25` |
| Подписчики против остальных | `metrics=views,averageViewPercentage`, `dimensions=subscribedStatus` |
| Весь архив видео | `metrics=views`, `dimensions=video`, `sort=-views`, `max_results=200`, затем `start_index=201` |

Недопустимое сочетание Google отклонит, текст ошибки вернётся модели.

## Ограничения

- **Показы и CTR обложек.** В YouTube Analytics API их нет. Они есть в YouTube Reporting API (отчёты `channel_reach_basic_a1`, `channel_reach_combined_a1`), но тот требует один POST для создания задания и отдаёт CSV раз в сутки. Сюда не включены, цифры пока из Studio.
- **Доход.** Данные приходят только каналам в партнёрской программе; остальным Google вернёт ошибку или пустой отчёт. Нужен scope `yt-analytics-monetary.readonly` (только чтение) и повторный `auth` после обновления.
- **Субтитры.** `captions.list` требует `youtube.force-ssl`, а этот scope даёт право на изменение и удаление, поэтому субтитры не включены.
- **Комментарии.** Не включены. Документация методов не указывает нужный scope, работа с `youtube.readonly` не проверялась.
- **Режим Testing.** Пока проект Google в этом режиме, вход приходится повторять раз в 7 дней. Перевод в Production снимает ограничение, Google покажет предупреждение о непроверенном приложении.

## Отзыв доступа

myaccount.google.com → Безопасность → Сторонние приложения → удалить доступ.

## Версии

Проект следует [семантическому версионированию](https://semver.org/lang/ru/): `MAJOR.MINOR.PATCH`, отсчёт с 1.0.0. Версия задаётся в `pyproject.toml`, сервер берёт её оттуда и отдаёт в `serverInfo`.

Контракт, по которому считается совместимость: имена инструментов, их параметры и форма ответа, команда `auth`, переменная `YOUTUBE_SECRETS_DIR`, файлы в папке секретов, список scope.

| Часть | Когда повышать | Примеры |
| --- | --- | --- |
| MAJOR | Старые вызовы или настройка перестают работать без действий пользователя | Удалён или переименован инструмент либо параметр, изменилась форма ответа, новая обязательная переменная окружения, старый токен перестаёт подходить для существующего инструмента или параметра |
| MINOR | Новая возможность, старое работает как раньше | Новый инструмент, новый необязательный параметр, новые поля в ответе, новый read-only scope для новых метрик (нужен повторный `auth` только ради них) |
| PATCH | Исправление без изменения контракта | Исправлена ошибка, уточнены подсказки и описания в схеме |

Правки только в README, `docs/` и dev-зависимостях версию не меняют. При повышении части справа обнуляются: 1.4.2 → 1.5.0 → 2.0.0.

Выпуск версии:

```bash
uv version --bump minor
```

Команда меняет `pyproject.toml` и `uv.lock`; вместо `minor` подставьте `major` или `patch`. Затем закоммитьте оба файла и поставьте тег:

```bash
git tag v$(uv version --short)
```

После обновления перезапустите Claude Desktop, чтобы он поднял сервер новой версии.

## Разработка

```bash
uv run pytest -q
```

```bash
uv run ruff check .
```
