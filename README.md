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
| Удержание видео | `metrics=audienceWatchRatio`, `dimensions=elapsedVideoTimeRatio`, `filters=video==ID` |
| Источники трафика | `metrics=views`, `dimensions=insightTrafficSourceType`, `sort=-views` |
| Демография | `metrics=viewerPercentage`, `dimensions=ageGroup,gender` |

Недопустимое сочетание Google отклонит, текст ошибки вернётся модели.

## Ограничения

- **Показы и CTR обложек.** На странице метрик Analytics API их нет, эти цифры по-прежнему берутся из Studio.
- **Субтитры.** `captions.list` требует `youtube.force-ssl`, а этот scope даёт право на изменение и удаление, поэтому субтитры не включены.
- **Комментарии.** Не включены. Документация методов не указывает нужный scope, работа с `youtube.readonly` не проверялась.
- **Режим Testing.** Пока проект Google в этом режиме, вход приходится повторять раз в 7 дней. Перевод в Production снимает ограничение, Google покажет предупреждение о непроверенном приложении.

## Отзыв доступа

myaccount.google.com → Безопасность → Сторонние приложения → удалить доступ.

## Разработка

```bash
uv run pytest -q
```

```bash
uv run ruff check .
```
