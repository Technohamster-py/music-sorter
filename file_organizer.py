import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from unittest import result

import mutagen
from config import ORGANIZE_PATTERN, DEFAULT_ARTIST, DEFAULT_ALBUM
from logger_config import get_logger
from duplicate_handler import DuplicateHandler

logger = get_logger(__name__)


class FileOrganizer:
    def __init__(self, dry_run: bool = False, bakup = True):
        self.dry_run = dry_run
        self.bakup = bakup
        self.duplicate_handler: DuplicateHandler = DuplicateHandler()
        self.organized_count = 0
        self.error_count = 0

    def organize_by_metadata(self, source_dir: Path, target_dir: Path, handle_duplicates: bool = True) -> Dict:
        audio_files = [f for f in source_dir.rglob('*') if f.suffix.lower() in {'.mp3', '.flac', '.m4a', '.ogg'}]
        logger.info(f"Found audio files: {len(audio_files)}")

        if handle_duplicates:
            logger.info("Searching for duplicates")
            duplicates = self.duplicate_handler.find_duplicates(audio_files)

            if duplicates:
                logger.info(f"Found {len(duplicates)} groups of duplicates")
                recommendations = self.duplicate_handler.analyze_duplicates(duplicates)
                report_path = self.duplicate_handler.generate_duplicate_report(recommendations)
                logger.info(f"Duplications report saved to {report_path}")

                if not self.dry_run:
                    moved = self.duplicate_handler.move_duplicates_to_quarantine(recommendations)
                    logger.info(f"Moved: duplicates to quarantine: {len(moved)}")

                    audio_files = [f for f in audio_files if f not in [p for rec in recommendations for p in rec['remove']]]

                    self.organized_count += 0
                    self.error_count = 0

                    for file_path in audio_files:
                        try:
                            self._organize_single_file(file_path, target_dir)
                            self.organized_count += 1
                        except Exception as e:
                            self.error_count += 1
                            logger.error(f"Organization Error {file_path.name}: {e}")

                    result = {
                        'total_found': len(audio_files),
                        'organized': self.organized_count,
                        'errors': self.error_count,
                        'dry_run': self.dry_run
                    }

                    logger.info(f"Organisation finished. Statistics: {result}")
                    return result

    def _organize_single_file(self, file_path: Path, target_dir: Path):
        metadata = self._extract_metadata(file_path)

        target_path = self._build_target_path(file_path, target_dir, metadata)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if self.dry_run:
            logger.info(f"[DRY RUN] {file_path} -> {target_path}")
            return

        try:
            shutil.move(str(file_path), str(target_path))
            logger.info(f"File organized: {file_path.name} -> {target_path}")
        except Exception as e:
            logger.error(f"Moving error {file_path}: {e}")
            raise

    def _extract_metadata(self, file_path: Path) -> Dict:
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio is None:
                return {'artist': DEFAULT_ARTIST, 'album': DEFAULT_ALBUM, 'title': file_path.stem}

            artist = audio.get('artist', [DEFAULT_ARTIST])[0] or DEFAULT_ARTIST
            album = audio.get('album', [DEFAULT_ALBUM])[0] or DEFAULT_ALBUM
            title = audio.get('title', [file_path.stem])[0] or file_path.stem

            # Очищаем от недопустимых символов
            for field in ['artist', 'album', 'title']:
                locals()[field] = self._sanitize_filename(locals()[field])

            # Получаем номер трека
            track = audio.get('track', ['0'])[0]
            track_num = self._extract_track_number(track)

            return {
                'artist': artist,
                'album': album,
                'title': title,
                'track': track_num,
                'ext': file_path.suffix
            }
        except Exception as e:
            logger.error(f"Error extracting metadata fom file {file_path.name}: {e}")
            return {
                'artist': DEFAULT_ARTIST,
                'album': DEFAULT_ALBUM,
                'title': file_path.stem,
                'track': 0,
                'ext': file_path.suffix
            }

    def _sanitize_filename(self, filename: str) -> str:
        import re
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = ' '.join(filename.split())
        return filename

    def _extract_track_number(self, track_str: str) -> int:
        try:
            if '/' in track_str:
                return int(track_str.split('/')[0])
            return int(track_str)
        except:
            return 0

    def _build_target_path(self, file_path: Path, target_dir: Path, metadata: Dict) -> Path:
        track_str = f"{metadata['track']:02d}" if metadata['track'] > 0 else ""

        if ORGANIZE_PATTERN:
            try:
                target_name = ORGANIZE_PATTERN.format(
                    artist=metadata['artist'],
                    album=metadata['album'],
                    track=track_str,
                    title=metadata['title'],
                    ext=metadata['ext']
                )
            except KeyError:
                target_name = f"{metadata['artist']}/{metadata['album']}/{metadata['title']}{metadata['ext']}"
        else:
            target_name = f"{metadata['artist']}/{metadata['album']}/{metadata['title']}{metadata['ext']}"

        target_name = '/'.join(part for part in target_name.split('/') if part)

        return target_dir / target_name