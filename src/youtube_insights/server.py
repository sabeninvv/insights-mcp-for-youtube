"""MCP-сервер (stdio, JSON-RPC по строкам) с read-only инструментами YouTube."""

import json
import sys
from collections.abc import Callable

from . import google
from .constants import (
    ANALYTICS_API,
    CHANNEL_PARTS,
    DATA_API,
    SERVER_NAME,
    SERVER_VERSION,
    VIDEO_PARTS,
)


def channel() -> dict:
    """Свой канал: профиль, статистика, id плейлиста загрузок."""
    items = google.get(f"{DATA_API}/channels", part=CHANNEL_PARTS, mine="true").get("items")
    if not items:
        raise ValueError("У этого аккаунта нет канала YouTube")
    return items[0]


def videos(max_results: int = 10, page_token: str | None = None) -> dict:
    """Последние загрузки канала с метаданными и статистикой."""
    uploads = channel()["contentDetails"]["relatedPlaylists"]["uploads"]
    page = google.get(
        f"{DATA_API}/playlistItems",
        part="contentDetails",
        playlistId=uploads,
        maxResults=max_results,
        pageToken=page_token,
    )
    ids = ",".join(item["contentDetails"]["videoId"] for item in page["items"])
    details = google.get(f"{DATA_API}/videos", part=VIDEO_PARTS, id=ids)
    return {"items": details["items"], "nextPageToken": page.get("nextPageToken")}


def video(video_id: str) -> dict:
    """Одно видео: метаданные, статистика, статус."""
    items = google.get(f"{DATA_API}/videos", part=VIDEO_PARTS, id=video_id)["items"]
    if not items:
        raise ValueError(f"Видео {video_id} не найдено")
    return items[0]


def analytics(
    start_date: str,
    end_date: str,
    metrics: str,
    dimensions: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    max_results: int | None = None,
    start_index: int | None = None,
    currency: str | None = None,
) -> list[dict]:
    """Отчёт YouTube Analytics по своему каналу; строки возвращаются как словари.

    start_index листает длинные отчёты (с 1), currency влияет только на денежные метрики.
    """
    report = google.get(
        ANALYTICS_API,
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        sort=sort,
        maxResults=max_results,
        startIndex=start_index,
        currency=currency,
    )
    names = [column["name"] for column in report["columnHeaders"]]
    return [dict(zip(names, row, strict=True)) for row in report.get("rows", [])]


DATE = {"type": "string", "description": "YYYY-MM-DD"}
TOOLS: list[tuple[Callable[..., object], dict]] = [
    (channel, {"type": "object", "properties": {}}),
    (
        videos,
        {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "page_token": {"type": "string", "description": "nextPageToken из прошлого ответа"},
            },
        },
    ),
    (
        video,
        {
            "type": "object",
            "properties": {"video_id": {"type": "string"}},
            "required": ["video_id"],
        },
    ),
    (
        analytics,
        {
            "type": "object",
            "properties": {
                "start_date": DATE,
                "end_date": DATE,
                "metrics": {
                    "type": "string",
                    "description": (
                        "Через запятую. Просмотры: views, engagedViews, redViews, "
                        "estimatedMinutesWatched, averageViewDuration, averageViewPercentage. "
                        "Вовлечённость: likes, dislikes, comments, shares, subscribersGained, "
                        "subscribersLost, videosAddedToPlaylists, videosRemovedFromPlaylists. "
                        "Доход (нужен scope monetary, канал в партнёрке): estimatedRevenue, "
                        "estimatedAdRevenue, estimatedRedPartnerRevenue, grossRevenue, cpm, "
                        "playbackBasedCpm, adImpressions, monetizedPlaybacks. "
                        "Подсказки: cardImpressions, cardClicks, cardClickRate, "
                        "cardTeaserImpressions, cardTeaserClicks, cardTeaserClickRate. "
                        "Эфиры: averageConcurrentViewers, peakConcurrentViewers. "
                        "Плейлисты (с dimensions=playlist или filters=playlist==ID): "
                        "playlistStarts, playlistViews, viewsPerPlaylistStart, "
                        "averageTimeInPlaylist, playlistSaves. "
                        "Удержание (только с dimensions=elapsedVideoTimeRatio и "
                        "filters=video==ID): "
                        "audienceWatchRatio, relativeRetentionPerformance, startedWatching, "
                        "stoppedWatching. Демография: viewerPercentage (с dimensions ageGroup "
                        "и/или gender). Показов обложек и CTR в этом API нет."
                    ),
                },
                "dimensions": {
                    "type": "string",
                    "description": (
                        "Через запятую. Время: day, month (даты строго первое число месяца). "
                        "Контент: video (нужен sort, max_results не больше 200), playlist, "
                        "creatorContentType (VIDEO_ON_DEMAND, SHORTS, LIVE_STREAM, STORY), "
                        "liveOrOnDemand, youtubeProduct. "
                        "Аудитория: subscribedStatus, ageGroup, gender, country, province (только "
                        "с filters=country==US), city. "
                        "Трафик: insightTrafficSourceType; insightTrafficSourceDetail (поисковые "
                        "запросы, внешние сайты, видео-источники) только с "
                        "filters=insightTrafficSourceType==YT_SEARCH|EXT_URL|RELATED_VIDEO|"
                        "SUBSCRIBER|YT_CHANNEL|ADVERTISING и max_results не больше 25. "
                        "Где смотрят: insightPlaybackLocationType, insightPlaybackLocationDetail "
                        "(только с filters=insightPlaybackLocationType==EMBEDDED). "
                        "Устройства: deviceType, operatingSystem. Шеринг: sharingService. "
                        "Удержание: elapsedVideoTimeRatio (100 точек, требует filters=video==ID). "
                        "Эфир по минутам: livestreamPosition. Реклама: adType."
                    ),
                },
                "filters": {
                    "type": "string",
                    "description": "Например video==ID или country==RU",
                },
                "sort": {"type": "string", "description": "Например -views"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 200},
                "start_index": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Номер первой строки (с 1), для листания вместе с max_results",
                },
                "currency": {
                    "type": "string",
                    "description": (
                        "ISO 4217, например EUR; только для денежных метрик, по умолчанию USD"
                    ),
                },
            },
            "required": ["start_date", "end_date", "metrics"],
        },
    ),
]


def respond(message: dict) -> dict:
    match message.get("method"):
        case "initialize":
            return {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        case "ping":
            return {}
        case "tools/list":
            return {
                "tools": [
                    {"name": tool.__name__, "description": tool.__doc__, "inputSchema": schema}
                    for tool, schema in TOOLS
                ]
            }
        case "tools/call":
            params = message["params"]
            tool = {tool.__name__: tool for tool, _ in TOOLS}[params["name"]]
            try:
                data = tool(**params.get("arguments", {}))
            # Граница: любая ошибка инструмента — ответ модели, не сбой сервера.
            except Exception as error:  # noqa: BLE001
                return {"content": [{"type": "text", "text": str(error)}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
        case method:
            raise NotImplementedError(f"Method not found: {method}")


def failure(message_id: object, code: int, text: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": text}}


def handle(line: str) -> dict | None:
    """Ответ на строку JSON-RPC; None для уведомления."""
    try:
        message = json.loads(line)
    except json.JSONDecodeError as error:
        return failure(None, -32700, f"Parse error: {error}")
    if not isinstance(message, dict):
        return failure(None, -32600, "Invalid Request")
    if "id" not in message:
        return None
    try:
        return {"jsonrpc": "2.0", "id": message["id"], "result": respond(message)}
    except NotImplementedError as error:
        return failure(message["id"], -32601, str(error))
    except (LookupError, TypeError) as error:  # неизвестный инструмент или неверные params
        return failure(message["id"], -32602, f"Invalid params: {error}")


def serve() -> None:
    for line in sys.stdin:
        reply = handle(line)
        if reply is not None:
            print(json.dumps(reply), flush=True)


def main() -> None:
    if sys.argv[1:] == ["auth"]:
        google.login()
        return
    google.client()  # fail-fast: без секретов не стартуем
    serve()
