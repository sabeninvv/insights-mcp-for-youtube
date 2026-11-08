"""Константы: адреса и scope Google, имена файлов, параметры сервера."""

# Google OAuth
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly "
    "https://www.googleapis.com/auth/yt-analytics.readonly "
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"
)

# YouTube API
DATA_API = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
CHANNEL_PARTS = "snippet,statistics,contentDetails"
VIDEO_PARTS = "snippet,statistics,contentDetails,status"

# Секреты
SECRETS_DIR_ENV = "YOUTUBE_SECRETS_DIR"
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

# Таймауты, секунды
REQUEST_TIMEOUT = 60
LOGIN_TIMEOUT = 300

# MCP-сервер
SERVER_NAME = "youtube-insights"
SERVER_VERSION = "0.1.0"
