"""Module for organizing files into folders by metadata"""
import shutil
from pathlib import Path
from typing import Dict, Callable

import mutagen

from config import ORGANIZE_PATTERN, DEFAULT_ARTIST, DEFAULT_ALBUM
from duplicate_handler import DuplicateHandler
from logger_config import get_logger
from progress_indicator import get_progress_indicator

logger = get_logger(__name__)


class FileOrganizer:
    """Class for organizing music files into folders"""

    def __init__(self, dry_run=False, backup=True, show_progress=True, use_tqdm=True):
        """
        Initialize file organizer

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
        self.duplicate_handler = DuplicateHandler(
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

            # Use progress indicator for duplicate search
            if self.show_progress:
                print("  Searching for duplicates...")

            duplicates = self.duplicate_handler.find_duplicates(audio_files)

            if duplicates:
                logger.info(f"Found {len(duplicates)} duplicate groups")

                # Analyze duplicates
                if self.show_progress:
                    print("  Analyzing duplicates...")

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
                self._organize_single_file(file_path, target_dir)
                self.organized_count += 1
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

    def _organize_single_file(self, file_path: Path, target_dir: Path):
        """
        Organize a single file

        Args:
            file_path: Path to the file
            target_dir: Target directory
        """
        # Extract metadata
        metadata = self._extract_metadata(file_path)

        # Build target path
        target_path = self._build_target_path(file_path, target_dir, metadata)

        # Create target directory
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if self.dry_run:
            logger.info(f"[DRY RUN] {file_path} -> {target_path}")
            return

        # Copy or move file
        try:
            shutil.move(str(file_path), str(target_path))
            logger.info(f"File organized: {file_path.name} -> {target_path}")
        except Exception as e:
            logger.error(f"Error moving {file_path}: {e}")
            raise

    def _extract_metadata(self, file_path: Path) -> Dict:
        """
        Extract metadata from file

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with metadata
        """
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio is None:
                return {'artist': DEFAULT_ARTIST, 'album': DEFAULT_ALBUM, 'title': file_path.stem}

            artist = audio.get('artist', [DEFAULT_ARTIST])[0] or DEFAULT_ARTIST
            album = audio.get('album', [DEFAULT_ALBUM])[0] or DEFAULT_ALBUM
            title = audio.get('title', [file_path.stem])[0] or file_path.stem

            # Sanitize filenames
            for field in ['artist', 'album', 'title']:
                locals()[field] = self._sanitize_filename(locals()[field])

            # Extract track number
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
            logger.error(f"Error extracting metadata from {file_path.name}: {e}")
            return {
                'artist': DEFAULT_ARTIST,
                'album': DEFAULT_ALBUM,
                'title': file_path.stem,
                'track': 0,
                'ext': file_path.suffix
            }

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
        return filename

    def _extract_track_number(self, track_str: str) -> int:
        """
        Extract track number from string

        Args:
            track_str: Track number string (e.g., "5" or "5/10")

        Returns:
            Track number as integer
        """
        try:
            if '/' in track_str:
                return int(track_str.split('/')[0])
            return int(track_str)
        except:
            return 0

    def _build_target_path(self, file_path: Path, target_dir: Path, metadata: Dict) -> Path:
        """
        Build target path for file

        Args:
            file_path: Original file path
            target_dir: Target directory
            metadata: File metadata

        Returns:
            Target path
        """
        # Format track number
        track_str = f"{metadata['track']:02d}" if metadata['track'] > 0 else ""

        # Use pattern or simple path
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
                # Fallback to simple path
                target_name = f"{metadata['artist']}/{metadata['album']}/{metadata['title']}{metadata['ext']}"
        else:
            target_name = f"{metadata['artist']}/{metadata['album']}/{metadata['title']}{metadata['ext']}"

        # Remove double slashes and normalize path
        target_name = '/'.join(part for part in target_name.split('/') if part)
