import shutil
from email.mime import audio
from importlib.metadata import files
from pathlib import Path
from typing import List, Optional, Tuple
import mutagen
from mutagen.id3 import ID3, TPE1, TALB, TIT2, TRCK, TYER, error as ID3Error
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus

from config import AUDIO_EXTENSIONS, TAG_MAPPING
from logger_config import get_logger

logger = get_logger(__name__)


class AudioProcessor:
    def __init__(self, dry_run=False, backup=True):
        self.dry_run = dry_run
        self.backup = backup
        self.processed_count = 0
        self.error_count = 0
        self.backup_files = []

    def set_artist_in_folder(self, foler_path: Path, artist_name: str, recursive: bool = True) -> Tuple[int, int]:
        logger.info(f"Processing folder: {foler_path.name}")
        logger.info(f"Setting artist: {artist_name}")

        if recursive:
            files = foler_path.rglob('*')
        else:
            files = foler_path.glob('*')

        audio_files = [f for f in files if f.suffix.lower() in AUDIO_EXTENSIONS]
        logger.info(f"Found {len(audio_files)} audio files")

        self.processed_count = 0
        self.backup_files = 0

        for file_path in audio_files:
            success = self.set_artist_for_file(file_path, artist_name)
            if success:
                self.processed_count += 1
                logger.debug(f"Processed: {file_path.name}")
            else:
                self.error_count += 1
                logger.error(f"Error processing: {file_path.name}")

        logger.info(f"Processing complete. Successfully processed: {self.processed_count}; Errors: {self.error_count}")
        return self.processed_count, self.error_count

    def set_artist_for_file(self, file_path: Path, artist_name: str):
        try:
            if self.dry_run:
                current_artist = self._get_current_artist(file_path)
                logger.info(f"[DRY RUN] {file_path.name}: {current_artist} -> {artist_name}")
                return True

            if self.backup:
                self._create_backup(file_path)

            extension = file_path.suffix.lower()

            if extension == '.mp3':
                success = self._set_mp3_artist(file_path, artist_name)
            elif extension == '.flac':
                success = self._set_flac_artist(file_path, artist_name)
            elif extension in ('.m4a', '.m4b'):
                success = self._set_m4a_artist(file_path, artist_name)
            elif extension in ('.ogg', '.opus'):
                success = self._set_ogg_artist(file_path, artist_name)
            else:
                logger.warning(f"Unsupported format: {extension}")
                return False

            if success:
                logger.info(f"Updated: {file_path.name} -> {artist_name}")
                return True
            else:
                logger.error(f"Can't update: {file_path.name}")
                return False

        except Exception as e:
            logger.error(f"Error while processing file {file_path.name}: {e}", exc_info=True)
            return False


    def _get_current_artist(self, file_path: Path) -> str:
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio and 'artist' in audio:
                return audio['artist'][0]
            return "Unknown"
        except:
            return "Error"

    def _create_backup(self, file_path: Path):
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")
        shutil.copy2(file_path, backup_path)
        self.backup_files.append(backup_path)
        logger.debug(f"Backup created at {backup_path}")
        return backup_path

    def _set_mp3_artist(self, file_path: Path, artist_name: str) -> bool:
        try:
            try:
                tags = ID3(file_path)
            except ID3Error:
                tags = ID3()

            tags.add(TPE1(encoding=3, text=artist_name))
            tags.save(file_path)
            return True
        except Exception as e:
            try:
                audio = mutagen.File(file_path, easy=True)
                audio["artist"] = artist_name
                audio.save()
            except:
                logger.error(f"Error setting MP3 tags: {e}")
                return False

    def _set_flac_artist(self, file_path: Path, artist_name: str) -> bool:
        try:
            audio = FLAC(file_path)
            audio["artist"] = artist_name
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting FLAC tags: {e}")
            return False

    def _set_m4a_artist(self, file_path: Path, artist_name: str) -> bool:
        try:
            audio = MP4(file_path)
            audio['\xa9ART'] = artist_name
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting M4A tags: {e}")
            return False

    def _set_ogg_artist(self, file_path: Path, artist_name: str) -> bool:
        try:
            if file_path.suffix == ".ogg":
                audio = OggVorbis(file_path)
            else:
                audio = OggOpus(file_path)
            audio["artist"] = artist_name
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting ogg tags: {e}")
            return False

    def cleanup_backups(self):
        if self.backup_files:
            logger.info(f"Removing {len(self.backup_files)} backups...")
            for backup in self.backup_files:
                try:
                    backup.unlink()
                    logger.debug(f"Removed backup: {backup}")
                except Exception as e:
                    logger.error(f"Error while removing backup {backup}: {e}")
            self.backup_files.clear()