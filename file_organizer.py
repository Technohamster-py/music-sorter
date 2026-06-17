"""Module for organizing files into folders by metadata"""
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Callable
import mutagen
from config import ORGANIZE_PATTERN, DEFAULT_ARTIST, DEFAULT_ALBUM
from logger_config import get_logger
from duplicate_handler import DuplicateHandler
from progress_indicator import get_progress_indicator, ProgressWithLogging

logger = get_logger(__name__)


class FileOrganizer:
    """Class for organizing music files into folders"""

    def __init__(self, dry_run=False, backup=True, show_progress=True, use_tqdm=True,
                 check_lyrics=True):
        """
        Initialize file organizer

        Args:
            dry_run: If True, only simulate operations
            backup: If True, create backup files before modifying
            show_progress: If True, show progress indicators
            use_tqdm: If True, use tqdm for progress (if available)
            check_lyrics: If True, check for lyrics presence in duplicates
        """
        self.dry_run = dry_run
        self.backup = backup
        self.show_progress = show_progress
        self.use_tqdm = use_tqdm
        self.check_lyrics = check_lyrics
        self.duplicate_handler = DuplicateHandler(
            check_lyrics=check_lyrics,
            show_progress=show_progress,
            use_tqdm=use_tqdm
        )
        self.organized_count = 0
        self.error_count = 0
        self.progress_callback = None

    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """
        Set callback for progress updates

        Args:
            callback: Function accepting (current, total, description)
        """
        self.progress_callback = callback
        # Also set callback for duplicate handler
        self.duplicate_handler.set_progress_callback(callback)

    def _update_progress(self, current: int, total: int, description: str = ""):
        """Update progress via callback if set"""
        if self.progress_callback:
            self.progress_callback(current, total, description)

    def organize_by_metadata(self, source_dir: Path, target_dir: Path,
                           handle_duplicates: bool = True) -> Dict:
        """
        Organize files by metadata

        Args:
            source_dir: Source directory with files
            target_dir: Target directory for organized files
            handle_duplicates: Whether to handle duplicate files

        Returns:
            Dictionary with statistics
        """
        logger.info(f"Starting file organization from {source_dir} to {target_dir}")

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Find all audio files
        audio_files = [f for f in source_dir.rglob('*')
                      if f.suffix.lower() in {'.mp3', '.flac', '.m4a', '.ogg', '.opus'}]
        logger.info(f"Found audio files: {len(audio_files)}")

        if not audio_files:
            logger.warning("No audio files found")
            return {'total_found': 0, 'organized': 0, 'errors': 0, 'dry_run': self.dry_run}

        # Handle duplicates if requested
        if handle_duplicates:
            logger.info("Searching for duplicates...")
            if self.check_lyrics:
                logger.info("Lyrics check is enabled (bonus for files with lyrics)")

            # Use progress indicator for duplicate search
            if self.show_progress:
                print("  Searching for duplicates...")

            duplicates = self.duplicate_handler.find_duplicates(audio_files)

            if duplicates:
                logger.info(f"Found {len(duplicates)} duplicate groups")

                # Analyze duplicates
                if self.show_progress:
                    print("  Analyzing duplicates...")
                    if self.check_lyrics:
                        print("  🎤 Checking for embedded lyrics...")

                recommendations = self.duplicate_handler.analyze_duplicates(duplicates)

                # Generate report
                report_path = self.duplicate_handler.generate_duplicate_report(recommendations)
                logger.info(f"Duplicate report saved: {report_path}")

                # Move duplicates to quarantine if not dry run
                if not self.dry_run:
                    if self.show_progress:
                        print("  Moving duplicates to quarantine...")

                    moved = self.duplicate_handler.move_duplicates_to_quarantine(recommendations)
                    logger.info(f"Moved duplicates to quarantine: {len(moved)}")

                    # Update file list (exclude moved files)
                    removed_paths = set()
                    for rec in recommendations:
                        removed_paths.update(rec['remove'])
                    audio_files = [f for f in audio_files if f not in removed_paths]

        # Organize files
        self.organized_count = 0
        self.error_count = 0

        if self.show_progress:
            progress = get_progress_indicator(
                len(audio_files),
                "Organizing files",
                self.use_tqdm
            )
        else:
            progress = None

        for i, file_path in enumerate(audio_files, 1):
            try:
                result = self._organize_single_file(file_path, target_dir)
                if result:
                    self.organized_count += 1
                else:
                    self.error_count += 1
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error organizing {file_path.name}: {e}")

            if progress:
                progress.update(i)

            self._update_progress(i, len(audio_files), f"Organizing: {file_path.name}")

        if progress:
            progress.finish()

        result = {
            'total_found': len(audio_files),
            'organized': self.organized_count,
            'errors': self.error_count,
            'dry_run': self.dry_run
        }

        logger.info(f"Organization complete. Statistics: {result}")
        return result

    def _organize_single_file(self, file_path: Path, target_dir: Path) -> bool:
        """
        Organize a single file

        Args:
            file_path: Path to the file
            target_dir: Target directory

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Extract metadata
            metadata = self._extract_metadata(file_path)

            if not metadata:
                logger.warning(f"No metadata extracted from {file_path.name}, using fallback")
                metadata = self._get_fallback_metadata(file_path)

            # Build target path
            target_path = self._build_target_path(file_path, target_dir, metadata)

            # Check if target_path is valid
            if target_path is None:
                logger.error(f"Failed to build target path for {file_path.name}")
                return False

            # Create target directory
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create directory {target_path.parent}: {e}")
                return False

            if self.dry_run:
                logger.info(f"[DRY RUN] {file_path} -> {target_path}")
                return True

            # Check if target file already exists
            if target_path.exists():
                logger.warning(f"Target file already exists: {target_path}")
                # Add a suffix to avoid overwriting
                counter = 1
                while target_path.exists():
                    stem = target_path.stem
                    # Remove existing counter if present
                    import re
                    stem_clean = re.sub(r'_\d+$', '', stem)
                    new_name = f"{stem_clean}_{counter}{target_path.suffix}"
                    target_path = target_path.parent / new_name
                    counter += 1
                logger.info(f"Using alternative name: {target_path.name}")

            # Copy or move file
            try:
                shutil.move(str(file_path), str(target_path))
                logger.info(f"File organized: {file_path.name} -> {target_path}")
                return True
            except Exception as e:
                logger.error(f"Error moving {file_path}: {e}")
                return False

        except Exception as e:
            logger.error(f"Error organizing {file_path.name}: {e}")
            return False

    def _get_fallback_metadata(self, file_path: Path) -> Dict:
        """
        Get fallback metadata when extraction fails

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with fallback metadata
        """
        return {
            'artist': DEFAULT_ARTIST,
            'album': DEFAULT_ALBUM,
            'title': file_path.stem,
            'track': 0,
            'ext': file_path.suffix
        }

    def _extract_metadata(self, file_path: Path) -> Optional[Dict]:
        """
        Extract metadata from file

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with metadata or None if extraction fails
        """
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio is None:
                logger.debug(f"Mutagen could not read {file_path.name}")
                return None

            # Try to get metadata, using defaults if missing
            artist = audio.get('artist', [DEFAULT_ARTIST])[0] or DEFAULT_ARTIST
            album = audio.get('album', [DEFAULT_ALBUM])[0] or DEFAULT_ALBUM
            title = audio.get('title', [file_path.stem])[0] or file_path.stem

            # Sanitize filenames
            artist = self._sanitize_filename(str(artist))
            album = self._sanitize_filename(str(album))
            title = self._sanitize_filename(str(title))

            # Extract track number
            track = audio.get('track', ['0'])[0]
            track_num = self._extract_track_number(str(track))

            # Ensure we have at least the title
            if not title or title == '':
                title = file_path.stem

            return {
                'artist': artist or DEFAULT_ARTIST,
                'album': album or DEFAULT_ALBUM,
                'title': title,
                'track': track_num if track_num is not None else 0,
                'ext': file_path.suffix
            }
        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path.name}: {e}")
            return None

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename by removing invalid characters

        Args:
            filename: Filename to sanitize

        Returns:
            Sanitized filename
        """
        import re
        # Replace invalid characters with _
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove extra spaces
        filename = ' '.join(filename.split())
        # Remove leading/trailing spaces and dots
        filename = filename.strip('. ')
        return filename or "untitled"

    def _extract_track_number(self, track_str: str) -> Optional[int]:
        """
        Extract track number from string

        Args:
            track_str: Track number string (e.g., "5" or "5/10")

        Returns:
            Track number as integer or None
        """
        try:
            if '/' in track_str:
                return int(track_str.split('/')[0])
            return int(track_str) if track_str else None
        except (ValueError, TypeError):
            return None

    def _build_target_path(self, file_path: Path, target_dir: Path, metadata: Dict) -> Optional[Path]:
        """
        Build target path for file

        Args:
            file_path: Original file path
            target_dir: Target directory
            metadata: File metadata

        Returns:
            Target path or None if building fails
        """
        try:
            # Format track number
            track_str = f"{metadata.get('track', 0):02d}" if metadata.get('track', 0) > 0 else ""

            # Ensure we have all required fields
            artist = metadata.get('artist', DEFAULT_ARTIST) or DEFAULT_ARTIST
            album = metadata.get('album', DEFAULT_ALBUM) or DEFAULT_ALBUM
            title = metadata.get('title', file_path.stem) or file_path.stem
            ext = metadata.get('ext', file_path.suffix) or file_path.suffix

            # Sanitize again for safety
            artist = self._sanitize_filename(artist)
            album = self._sanitize_filename(album)
            title = self._sanitize_filename(title)

            # Use pattern or simple path
            if ORGANIZE_PATTERN:
                try:
                    target_name = ORGANIZE_PATTERN.format(
                        artist=artist,
                        album=album,
                        track=track_str,
                        title=title,
                        ext=ext
                    )
                except KeyError as e:
                    logger.warning(f"Missing key in pattern: {e}, using fallback")
                    target_name = f"{artist}/{album}/{title}{ext}"
                except Exception as e:
                    logger.warning(f"Error formatting pattern: {e}, using fallback")
                    target_name = f"{artist}/{album}/{title}{ext}"
            else:
                target_name = f"{artist}/{album}/{title}{ext}"

            # Remove double slashes and normalize path
            target_name = '/'.join(part for part in target_name.split('/') if part)

            # Ensure target_name is not empty
            if not target_name:
                logger.warning(f"Empty target name for {file_path.name}, using fallback")
                target_name = f"{DEFAULT_ARTIST}/{DEFAULT_ALBUM}/{file_path.stem}{file_path.suffix}"

            return target_dir / target_name

        except Exception as e:
            logger.error(f"Error building target path for {file_path.name}: {e}")
            return None