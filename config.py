import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
DUPLICATES_DIR = BASE_DIR / "duplicates"

LOGS_DIR.mkdir(exist_ok=True)
DUPLICATES_DIR.mkdir(exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

PROCESSING_LOG = LOGS_DIR / "processing.log"
DUPLICATES_LOG = LOGS_DIR / "duplicates.log"
ERRORS_LOG = LOGS_DIR / "errors.log"

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.m4b', '.ogg', '.opus', '.wma', '.aac'}

DUPLICATE_CHECK_FIELDS = ['title', 'artist', 'duration']
DUPLICATE_MATCH_THRESHOLD = 0.9

ORGANIZE_PATTERN = "{artist}/{album}/{track:02d} - {title}{ext}"
DEFAULT_ARTIST = "Unknown Artist"
DEFAULT_ALBUM = "Unknown Album"

TAG_MAPPING = {
    'mp3': {
        'artist': 'TPE1',
        'album': 'TALB',
        'title': 'TIT2',
        'track': 'TRCK',
        'year': 'TYER'
    },
    'flac': {
        'artist': 'artist',
        'album': 'album',
        'title': 'title',
        'track': 'tracknumber',
        'year': 'date'
    },
    'mp4': {
        'artist': '\xa9ART',
        'album': '\xa9alb',
        'title': '\xa9nam',
        'track': 'trkn',
        'year': '\xa9day'
    },
    'ogg': {
        'artist': 'artist',
        'album': 'album',
        'title': 'title',
        'track': 'tracknumber',
        'year': 'date'
    }
}