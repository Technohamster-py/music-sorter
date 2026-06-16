"""Main module for processing audio file metadata"""
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Callable, Dict, Union
import mutagen
from mutagen.id3 import ID3, TPE1, TALB, TIT2, TRCK, TYER, TDRC, error as ID3Error
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus

from config import AUDIO_EXTENSIONS, TAG_MAPPING
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

    def set_metadata_in_folder(self, folder_path: Path,
                               artist: Optional[str] = None,
                               album: Optional[str] = None,
                               title: Optional[str] = None,
                               year: Optional[str] = None,
                               track: Optional[int] = None,
                               recursive: bool = True,
                               use_filename_as_title: bool = False) -> Tuple[int, int]:
        """
        Set metadata for all audio files in a folder

        Args:
            folder_path: Path to the folder with music
            artist: Artist name to set (None to skip)
            album: Album name to set (None to skip)
            title: Title to set (None to skip)
            year: Year to set (None to skip)
            track: Track number to set (None to skip)
            recursive: Whether to process subdirectories
            use_filename_as_title: If True, use filename (without extension) as title

        Returns:
            tuple: (processed_count, error_count)
        """
        # Build description for progress
        changes = []
        if artist: changes.append(f"artist='{artist}'")
        if album: changes.append(f"album='{album}'")
        if title: changes.append(f"title='{title}'")
        if year: changes.append(f"year='{year}'")
        if track is not None: changes.append(f"track={track}")
        if use_filename_as_title: changes.append("title=filename")

        description = "Setting " + ", ".join(changes) if changes else "No changes"
        logger.info(f"Starting folder processing: {folder_path}")
        logger.info(f"Metadata changes: {description}")

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
                description,
                self.use_tqdm
            )
        else:
            progress = None

        self.processed_count = 0
        self.error_count = 0

        # Process files
        for i, file_path in enumerate(audio_files, 1):
            try:
                success = self._set_metadata_for_file(
                    file_path,
                    artist=artist,
                    album=album,
                    title=title,
                    year=year,
                    track=track,
                    use_filename_as_title=use_filename_as_title
                )
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

    def _set_metadata_for_file(self, file_path: Path,
                               artist: Optional[str] = None,
                               album: Optional[str] = None,
                               title: Optional[str] = None,
                               year: Optional[str] = None,
                               track: Optional[int] = None,
                               use_filename_as_title: bool = False) -> bool:
        """
        Set metadata for a single file

        Args:
            file_path: Path to audio file
            artist: Artist name to set
            album: Album name to set
            title: Title to set
            year: Year to set
            track: Track number to set
            use_filename_as_title: If True, use filename as title

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.dry_run:
                current_artist = self._get_current_artist(file_path)
                current_album = self._get_current_album(file_path)
                current_title = self._get_current_title(file_path)
                logger.info(f"[DRY RUN] {file_path.name}: "
                           f"Artist: {current_artist} -> {artist or 'unchanged'}, "
                           f"Album: {current_album} -> {album or 'unchanged'}, "
                           f"Title: {current_title} -> {title or 'unchanged'}")
                return True

            # Create backup if needed
            if self.backup:
                self._create_backup(file_path)

            # Determine format and set tags
            extension = file_path.suffix.lower()

            if extension == '.mp3':
                success = self._set_mp3_metadata(
                    file_path, artist, album, title, year, track, use_filename_as_title
                )
            elif extension == '.flac':
                success = self._set_flac_metadata(
                    file_path, artist, album, title, year, track, use_filename_as_title
                )
            elif extension in ('.m4a', '.m4b'):
                success = self._set_m4a_metadata(
                    file_path, artist, album, title, year, track, use_filename_as_title
                )
            elif extension in ('.ogg', '.opus'):
                success = self._set_ogg_metadata(
                    file_path, artist, album, title, year, track, use_filename_as_title
                )
            else:
                logger.warning(f"Unsupported format: {extension}")
                return False

            if success:
                changes = []
                if artist: changes.append(f"artist={artist}")
                if album: changes.append(f"album={album}")
                if title: changes.append(f"title={title}")
                if year: changes.append(f"year={year}")
                if track is not None: changes.append(f"track={track}")
                if use_filename_as_title: changes.append("title=filename")

                logger.info(f"Updated: {file_path.name} -> {', '.join(changes)}")
                return True
            else:
                logger.error(f"Failed to update: {file_path.name}")
                return False

        except Exception as e:
            logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
            return False

    # Legacy method for backward compatibility
    def set_artist_in_folder(self, folder_path: Path, artist_name: str,
                           recursive: bool = True) -> Tuple[int, int]:
        """
        Set artist for all audio files in a folder (legacy method)

        Args:
            folder_path: Path to the folder with music
            artist_name: Artist name to set
            recursive: Whether to process subdirectories

        Returns:
            tuple: (processed_count, error_count)
        """
        return self.set_metadata_in_folder(
            folder_path=folder_path,
            artist=artist_name,
            recursive=recursive
        )

    def _get_current_artist(self, file_path: Path) -> str:
        """Get current artist from file"""
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio and 'artist' in audio:
                return audio['artist'][0]
            return "Unknown"
        except:
            return "Error"

    def _get_current_album(self, file_path: Path) -> str:
        """Get current album from file"""
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio and 'album' in audio:
                return audio['album'][0]
            return "Unknown"
        except:
            return "Error"

    def _get_current_title(self, file_path: Path) -> str:
        """Get current title from file"""
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio and 'title' in audio:
                return audio['title'][0]
            return file_path.stem
        except:
            return "Error"

    def _create_backup(self, file_path: Path) -> Path:
        """Create backup of file"""
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        shutil.copy2(file_path, backup_path)
        self.backup_files.append(backup_path)
        logger.debug(f"Backup created: {backup_path}")
        return backup_path

    def _set_mp3_metadata(self, file_path: Path,
                          artist: Optional[str] = None,
                          album: Optional[str] = None,
                          title: Optional[str] = None,
                          year: Optional[str] = None,
                          track: Optional[int] = None,
                          use_filename_as_title: bool = False) -> bool:
        """Set metadata for MP3 file"""
        try:
            # Try to open existing tags or create new ones
            try:
                tags = ID3(file_path)
            except ID3Error:
                tags = ID3()

            from mutagen.id3 import TPE1, TALB, TIT2, TRCK, TYER, TDRC

            if artist:
                tags.add(TPE1(encoding=3, text=artist))
            if album:
                tags.add(TALB(encoding=3, text=album))
            if title:
                tags.add(TIT2(encoding=3, text=title))
            elif use_filename_as_title:
                title_from_filename = file_path.stem
                tags.add(TIT2(encoding=3, text=title_from_filename))
            if year:
                tags.add(TYER(encoding=3, text=year))
            if track is not None:
                tags.add(TRCK(encoding=3, text=str(track)))

            tags.save(file_path)
            return True
        except Exception as e:
            # Fallback to easy API
            try:
                audio = mutagen.File(file_path, easy=True)
                if artist:
                    audio['artist'] = artist
                if album:
                    audio['album'] = album
                if title:
                    audio['title'] = title
                elif use_filename_as_title:
                    audio['title'] = file_path.stem
                if year:
                    audio['date'] = year
                if track is not None:
                    audio['tracknumber'] = str(track)
                audio.save()
                return True
            except Exception as e2:
                logger.error(f"Error setting MP3 tags: {e2}")
                return False

    def _set_flac_metadata(self, file_path: Path,
                          artist: Optional[str] = None,
                          album: Optional[str] = None,
                          title: Optional[str] = None,
                          year: Optional[str] = None,
                          track: Optional[int] = None,
                          use_filename_as_title: bool = False) -> bool:
        """Set metadata for FLAC file"""
        try:
            audio = FLAC(file_path)
            if artist:
                audio['artist'] = artist
            if album:
                audio['album'] = album
            if title:
                audio['title'] = title
            elif use_filename_as_title:
                audio['title'] = file_path.stem
            if year:
                audio['date'] = year
            if track is not None:
                audio['tracknumber'] = str(track)
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting FLAC tags: {e}")
            return False

    def _set_m4a_metadata(self, file_path: Path,
                         artist: Optional[str] = None,
                         album: Optional[str] = None,
                         title: Optional[str] = None,
                         year: Optional[str] = None,
                         track: Optional[int] = None,
                         use_filename_as_title: bool = False) -> bool:
        """Set metadata for M4A file"""
        try:
            audio = MP4(file_path)
            if artist:
                audio['\xa9ART'] = artist
            if album:
                audio['\xa9alb'] = album
            if title:
                audio['\xa9nam'] = title
            elif use_filename_as_title:
                audio['\xa9nam'] = file_path.stem
            if year:
                audio['\xa9day'] = year
            if track is not None:
                # M4A uses tuple (track_number, total_tracks)
                audio['trkn'] = [(track, 0)]
            audio.save()
            return True
        except Exception as e:
            logger.error(f"Error setting M4A tags: {e}")
            return False

    def _set_ogg_metadata(self, file_path: Path,
                         artist: Optional[str] = None,
                         album: Optional[str] = None,
                         title: Optional[str] = None,
                         year: Optional[str] = None,
                         track: Optional[int] = None,
                         use_filename_as_title: bool = False) -> bool:
        """Set metadata for OGG/Opus file"""
        try:
            if file_path.suffix.lower() == '.ogg':
                audio = OggVorbis(file_path)
            else:
                audio = OggOpus(file_path)

            if artist:
                audio['artist'] = artist
            if album:
                audio['album'] = album
            if title:
                audio['title'] = title
            elif use_filename_as_title:
                audio['title'] = file_path.stem
            if year:
                audio['date'] = year
            if track is not None:
                audio['tracknumber'] = str(track)
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