"""Main module for processing audio file metadata"""
import shutil
from pathlib import Path
from typing import Tuple, Callable

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TPE1, error as ID3Error
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from config import AUDIO_EXTENSIONS
from logger_config import get_logger
from progress_indicator import get_progress_indicator, SpinnerIndicator

logger = get_logger(__name__)


class AudioProcessor:
    """Class for processing audio file metadata"""

    def __init__(self, dry_run=False, backup=True, show_progress=True, use_tqdm=True):
        """
        Initialize audio processor

        Args:
            dry_run: If True, only simulate operations
            backup: If True, create backup files before modifying
            show_progress: If True, show progress indicators
            use_tqdm: If True, use tqdm for progress (if available)
        """
        self.dry_run = dry_run
        self.backup = backup
        self.show_progress = show_progress
        self.use_tqdm = use_tqdm
        self.processed_count = 0
        self.error_count = 0
        self.backup_files = []
        self.progress_callback = None

    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """
        Set callback for progress updates

        Args:
            callback: Function accepting (current, total, description)
        """
        self.progress_callback = callback

    def _update_progress(self, current: int, total: int, description: str = ""):
        """Update progress via callback if set"""
        if self.progress_callback:
            self.progress_callback(current, total, description)

    def set_artist_in_folder(self, folder_path: Path, artist_name: str,
                             recursive: bool = True) -> Tuple[int, int]:
        """
        Set artist for all audio files in a folder

        Args:
            folder_path: Path to the folder with music
            artist_name: Artist name to set
            recursive: Whether to process subdirectories

        Returns:
            tuple: (processed_count, error_count)
        """
        logger.info(f"Starting folder processing: {folder_path}")
        logger.info(f"Setting artist: {artist_name}")

        # Find all audio files
        if recursive:
            files = list(folder_path.rglob('*'))
        else:
            files = list(folder_path.glob('*'))

        audio_files = [f for f in files if f.suffix.lower() in AUDIO_EXTENSIONS]
        total_files = len(audio_files)
        logger.info(f"Found audio files: {total_files}")

        if total_files == 0:
            logger.warning("No audio files found")
            return 0, 0

        # Create progress indicator
        if self.show_progress:
            progress = get_progress_indicator(
                total_files,
                f"Setting artist '{artist_name}'",
                self.use_tqdm
            )
        else:
            progress = None

        self.processed_count = 0
        self.error_count = 0

        # Process files
        for i, file_path in enumerate(audio_files, 1):
            try:
                success = self._set_artist_for_file(file_path, artist_name)
                if success:
                    self.processed_count += 1
                    logger.debug(f"Processed: {file_path.name}")
                else:
                    self.error_count += 1
                    logger.error(f"Failed to process: {file_path.name}")
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error processing {file_path.name}: {e}")

            # Update progress
            if progress:
                progress.update(i)

            # Call callback if set
            self._update_progress(i, total_files, f"Processing: {file_path.name}")

        # Finish indicator
        if progress:
            progress.finish()

        logger.info(f"Processing complete. Success: {self.processed_count}, Errors: {self.error_count}")
        return self.processed_count, self.error_count

    def set_artist_with_spinner(self, folder_path: Path, artist_name: str,
                                recursive: bool = True) -> Tuple[int, int]:
        """
        Set artist with spinner indicator (for unknown total count)

        Args:
            folder_path: Path to the folder with music
            artist_name: Artist name to set
            recursive: Whether to process subdirectories

        Returns:
            tuple: (processed_count, error_count)
        """
        logger.info(f"Starting folder processing with spinner: {folder_path}")

        # Find files
        if recursive:
            files = list(folder_path.rglob('*'))
        else:
            files = list(folder_path.glob('*'))

        audio_files = [f for f in files if f.suffix.lower() in AUDIO_EXTENSIONS]
        total_files = len(audio_files)
        logger.info(f"Found audio files: {total_files}")

        if self.show_progress:
            spinner = SpinnerIndicator(f"Processing {total_files} files")
            spinner.start()
        else:
            spinner = None

        self.processed_count = 0
        self.error_count = 0

        for i, file_path in enumerate(audio_files, 1):
            try:
                success = self._set_artist_for_file(file_path, artist_name)
                if success:
                    self.processed_count += 1
                else:
                    self.error_count += 1
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error: {file_path.name} - {e}")

            if spinner:
                spinner.update(i)

            self._update_progress(i, total_files, f"Processing: {file_path.name}")

        if spinner:
            spinner.finish()

        logger.info(f"Complete. Success: {self.processed_count}, Errors: {self.error_count}")
        return self.processed_count, self.error_count

    def _set_artist_for_file(self, file_path: Path, artist_name: str) -> bool:
        """
        Set artist for a single file

        Args:
            file_path: Path to audio file
            artist_name: Artist name to set

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.dry_run:
                current_artist = self._get_current_artist(file_path)
                logger.info(f"[DRY RUN] {file_path.name}: {current_artist} -> {artist_name}")
                return True

            # Create backup if needed
            if self.backup:
                self._create_backup(file_path)

            # Determine format and set tag
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
                logger.error(f"Failed to update: {file_path.name}")
                return False

        except Exception as e:
            logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
            return False

    def _get_current_artist(self, file_path: Path) -> str:
        """Get current artist from file"""
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio and 'artist' in audio:
                return audio['artist'][0]
            return "Unknown"
        except:
            return "Error"

    def _create_backup(self, file_path: Path) -> Path:
        """Create backup of file"""
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        shutil.copy2(file_path, backup_path)
        self.backup_files.append(backup_path)
        logger.debug(f"Backup created: {backup_path}")
        return backup_path

    def _set_mp3_artist(self, file_path: Path, artist_name: str) -> bool:
        """Set artist for MP3 file"""
        try:
            # Try to open existing tags or create new ones
            try:
                tags = ID3(file_path)
            except ID3Error:
                tags = ID3()

            tags.add(TPE1(encoding=3, text=artist_name))
            tags.save(file_path)
            return True
        except Exception as e:
            # Fallback to easy API
            try:
                audio = mutagen.File(file_path, easy=True)
                audio['artist'] = artist_name
                audio.save()
                return True
            except:
                logger.error(f"Error setting MP3 tags: {e}")
                return False

    def _set_flac_artist(self, file_path: Path, artist_name: str) -> bool:
        """Set artist for FLAC file"""
        try:
            audio = FLAC(file_path)
            audio['artist'] = artist_name
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting FLAC tags: {e}")
            return False

    def _set_m4a_artist(self, file_path: Path, artist_name: str) -> bool:
        """Set artist for M4A file"""
        try:
            audio = MP4(file_path)
            audio['\xa9ART'] = artist_name
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting M4A tags: {e}")
            return False

    def _set_ogg_artist(self, file_path: Path, artist_name: str) -> bool:
        """Set artist for OGG/Opus file"""
        try:
            if file_path.suffix.lower() == '.ogg':
                audio = OggVorbis(file_path)
            else:
                audio = OggOpus(file_path)
            audio['artist'] = artist_name
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting OGG tags: {e}")
            return False

    def cleanup_backups(self):
        """Delete all created backups"""
        if self.backup_files:
            logger.info(f"Deleting {len(self.backup_files)} backups...")
            for backup in self.backup_files:
                try:
                    backup.unlink()
                    logger.debug(f"Deleted backup: {backup}")
                except Exception as e:
                    logger.error(f"Error deleting backup {backup}: {e}")
            self.backup_files.clear()
