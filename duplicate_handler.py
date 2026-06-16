"""Module for detecting and handling duplicate audio files"""
import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Callable
import mutagen
from config import DUPLICATES_DIR, DUPLICATE_CHECK_FIELDS, DUPLICATE_MATCH_THRESHOLD
from logger_config import get_logger
from progress_indicator import ProgressIndicator, SpinnerIndicator, SimpleProgressBar, get_progress_indicator

logger = get_logger(__name__)
duplicates_logger = get_logger('duplicates')


class DuplicateHandler:
    """Handler for detecting and processing duplicate audio files"""

    def __init__(self, compare_by_hash=True, compare_by_metadata=True,
                 check_lyrics=True, show_progress=True, use_tqdm=True):
        """
        Initialize duplicate handler

        Args:
            compare_by_hash: Whether to compare files by hash
            compare_by_metadata: Whether to compare files by metadata
            check_lyrics: Whether to check for lyrics presence
            show_progress: Whether to show progress indicators
            use_tqdm: Whether to use tqdm for progress (if available)
        """
        self.compare_by_hash = compare_by_hash
        self.compare_by_metadata = compare_by_metadata
        self.check_lyrics = check_lyrics
        self.show_progress = show_progress
        self.use_tqdm = use_tqdm
        self.duplicates_found = []
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

    def find_duplicates(self, files: List[Path]) -> Dict[str, List[Path]]:
        """
        Find duplicates among a list of files

        Returns:
            Dictionary: key - duplicate identifier, value - list of paths
        """
        logger.info(f"Finding duplicates among {len(files)} files")

        file_info = {}
        total_files = len(files)

        # Create progress indicator
        if self.show_progress:
            progress = get_progress_indicator(
                total_files,
                "Scanning files for duplicates",
                self.use_tqdm
            )
        else:
            progress = None

        # Process each file
        for i, file_path in enumerate(files, 1):
            # Get file identifier
            info = self._get_file_identifier(file_path)
            if info:
                file_info[str(file_path)] = info

            # Update progress
            if progress:
                progress.update(i)

            self._update_progress(i, total_files, f"Scanning: {file_path.name}")

        if progress:
            progress.finish()

        # Group by identifiers
        from collections import defaultdict
        grouped = defaultdict(list)

        for path, identifier in file_info.items():
            grouped[identifier].append(Path(path))

        # Keep only groups with duplicates (more than 1 file)
        duplicates = {k: v for k, v in grouped.items() if len(v) > 1}

        # Save found duplicates
        self.duplicates_found = duplicates

        # Log results
        if duplicates:
            duplicates_logger.info(f"Found {len(duplicates)} duplicate groups:")
            for identifier, paths in duplicates.items():
                duplicates_logger.info(f"  Group: {identifier[:100]}...")
                for path in paths:
                    duplicates_logger.info(f"    - {path}")

        logger.info(f"Found {len(duplicates)} duplicate groups")
        return duplicates

    def _get_file_identifier(self, file_path: Path) -> Optional[str]:
        """Get unique identifier for a file"""
        identifiers = []

        # 1. Compare by file hash (most accurate)
        if self.compare_by_hash:
            file_hash = self._calculate_file_hash(file_path)
            if file_hash:
                identifiers.append(f"hash_{file_hash}")

        # 2. Compare by metadata
        if self.compare_by_metadata:
            metadata = self._extract_metadata(file_path)
            if metadata:
                # Create key based on important fields
                key_parts = []
                for field in DUPLICATE_CHECK_FIELDS:
                    if field in metadata and metadata[field]:
                        key_parts.append(f"{field}={metadata[field]}")

                if key_parts:
                    identifiers.append("|".join(key_parts))

                # Also try fuzzy comparison of titles
                if 'title' in metadata and 'artist' in metadata:
                    fuzzy_key = self._create_fuzzy_key(metadata['title'], metadata['artist'])
                    identifiers.append(f"fuzzy_{fuzzy_key}")

        # Return first found identifier (priority: hash > metadata)
        for identifier in identifiers:
            if identifier.startswith('hash_'):
                return identifier
        for identifier in identifiers:
            if identifier.startswith('fuzzy_'):
                return identifier
        for identifier in identifiers:
            if identifier:
                return identifier

        return None

    def _calculate_file_hash(self, file_path: Path, algorithm='md5') -> Optional[str]:
        """Calculate file hash"""
        try:
            hash_func = hashlib.new(algorithm)
            with open(file_path, 'rb') as f:
                # Read only first 10 MB for speed
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    hash_func.update(chunk)
                    if f.tell() > 10 * 1024 * 1024:  # 10 MB limit
                        break
            return hash_func.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return None

    def _extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from audio file"""
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio is None:
                return {}

            metadata = {}
            for field in DUPLICATE_CHECK_FIELDS:
                if field in audio and audio[field]:
                    metadata[field] = audio[field][0]

            # Add file size
            metadata['size'] = file_path.stat().st_size

            return metadata
        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {e}")
            return {}

    def _create_fuzzy_key(self, title: str, artist: str) -> str:
        """Create fuzzy key for comparison"""
        import re
        title_clean = re.sub(r'[^\w\s]', '', title.lower())
        artist_clean = re.sub(r'[^\w\s]', '', artist.lower())

        # Take first 50 characters
        return f"{artist_clean[:30]}_{title_clean[:50]}"

    def _has_lyrics(self, file_path: Path) -> bool:
        """
        Check if audio file has embedded lyrics

        Args:
            file_path: Path to audio file

        Returns:
            bool: True if lyrics are present, False otherwise
        """
        try:
            extension = file_path.suffix.lower()

            # MP3 files - check for USLT (Unsychronized Lyrics) or SYLT (Synchronized Lyrics)
            if extension == '.mp3':
                try:
                    audio = mutagen.id3.ID3(file_path)
                    # Check for unsynchronized lyrics
                    if audio.get('USLT'):
                        return True
                    # Check for synchronized lyrics
                    if audio.get('SYLT'):
                        return True
                except:
                    pass

            # FLAC, OGG, Opus files - check for 'lyrics' tag
            elif extension in ['.flac', '.ogg', '.opus']:
                audio = mutagen.File(file_path)
                if audio and 'lyrics' in audio:
                    lyrics = audio.get('lyrics')
                    if lyrics and len(str(lyrics)) > 10:  # Some content
                        return True

            # M4A/MP4 files - check for lyrics atom
            elif extension in ['.m4a', '.m4b']:
                audio = mutagen.mp4.MP4(file_path)
                # Check for lyrics atom (©lyr)
                if audio and '\xa9lyr' in audio:
                    lyrics = audio.get('\xa9lyr')
                    if lyrics and len(str(lyrics)) > 10:
                        return True
                # Also check for iTunes lyrics
                if audio and '----:com.apple.iTunes:lyrics' in audio:
                    return True

            # Try easy access for all formats
            audio = mutagen.File(file_path, easy=True)
            if audio and 'lyrics' in audio:
                lyrics = audio.get('lyrics')
                if lyrics and len(str(lyrics)) > 10:
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking lyrics in {file_path.name}: {e}")
            return False

    def _extract_lyrics_text(self, file_path: Path) -> Optional[str]:
        """
        Extract lyrics text from audio file

        Args:
            file_path: Path to audio file

        Returns:
            str: Lyrics text or None if not found
        """
        try:
            extension = file_path.suffix.lower()

            # MP3 files
            if extension == '.mp3':
                try:
                    audio = mutagen.id3.ID3(file_path)
                    # Get unsynchronized lyrics
                    uslt = audio.get('USLT')
                    if uslt:
                        return str(uslt)
                    # Get synchronized lyrics
                    sylt = audio.get('SYLT')
                    if sylt:
                        return str(sylt)
                except:
                    pass

            # FLAC, OGG, Opus files
            elif extension in ['.flac', '.ogg', '.opus']:
                audio = mutagen.File(file_path)
                if audio and 'lyrics' in audio:
                    return str(audio.get('lyrics'))

            # M4A/MP4 files
            elif extension in ['.m4a', '.m4b']:
                audio = mutagen.mp4.MP4(file_path)
                if audio and '\xa9lyr' in audio:
                    return str(audio.get('\xa9lyr')[0])
                if audio and '----:com.apple.iTunes:lyrics' in audio:
                    return str(audio.get('----:com.apple.iTunes:lyrics')[0])

            # Try easy access
            audio = mutagen.File(file_path, easy=True)
            if audio and 'lyrics' in audio:
                return str(audio.get('lyrics')[0])

            return None

        except Exception as e:
            logger.debug(f"Error extracting lyrics from {file_path.name}: {e}")
            return None

    def analyze_duplicates(self, duplicates: Dict[str, List[Path]]) -> List[Dict]:
        """
        Analyze duplicates and recommend which file to keep

        Returns:
            List of recommendations for each duplicate group
        """
        logger.info(f"Analyzing {len(duplicates)} duplicate groups")

        recommendations = []
        total_groups = len(duplicates)

        # Create progress indicator
        if self.show_progress:
            progress = get_progress_indicator(
                total_groups,
                "Analyzing duplicates",
                self.use_tqdm
            )
        else:
            progress = None

        for i, (identifier, paths) in enumerate(duplicates.items(), 1):
            files_info = []

            # Analyze each file in the group
            for path in paths:
                info = {
                    'path': path,
                    'size': path.stat().st_size,
                    'modified': datetime.fromtimestamp(path.stat().st_mtime),
                    'metadata': self._extract_metadata(path),
                    'has_lyrics': False,
                    'lyrics_length': 0,
                    'score': 0
                }

                # Check for lyrics
                if self.check_lyrics:
                    info['has_lyrics'] = self._has_lyrics(path)
                    if info['has_lyrics']:
                        lyrics_text = self._extract_lyrics_text(path)
                        if lyrics_text:
                            info['lyrics_length'] = len(lyrics_text)

                # Score the file quality
                score = 0

                # 1. By size (larger = better quality)
                if len(paths) > 1:
                    max_size = max(p.stat().st_size for p in paths)
                    if info['size'] == max_size:
                        score += 10
                    elif info['size'] > max_size * 0.9:
                        score += 5
                    else:
                        score += 1

                # 2. By metadata completeness
                metadata_count = len(info['metadata'])
                score += min(metadata_count * 2, 20)  # max 20 points

                # 3. By modification date (newer = better)
                if len(paths) > 1:
                    newest = max(datetime.fromtimestamp(p.stat().st_mtime) for p in paths)
                    if info['modified'] == newest:
                        score += 5

                # 4. By lyrics presence (BIG bonus - important criterion!)
                if self.check_lyrics:
                    if info['has_lyrics']:
                        # Bonus for having lyrics
                        score += 25

                        # Extra bonus for longer lyrics (more complete)
                        if info['lyrics_length'] > 1000:
                            score += 10  # Very long lyrics
                        elif info['lyrics_length'] > 500:
                            score += 5   # Medium lyrics
                        elif info['lyrics_length'] > 100:
                            score += 2   # Short lyrics
                    else:
                        # Penalty for missing lyrics (but not too harsh)
                        score -= 5

                info['score'] = score
                files_info.append(info)

            # Sort by score descending
            files_info.sort(key=lambda x: x['score'], reverse=True)

            recommendation = {
                'identifier': identifier,
                'keep': files_info[0]['path'],  # recommend keeping the best one
                'remove': [info['path'] for info in files_info[1:]],  # others to remove
                'all_files': paths,
                'analysis': files_info,
                'has_lyrics_keep': files_info[0]['has_lyrics'] if files_info else False
            }

            recommendations.append(recommendation)

            # Update progress
            if progress:
                progress.update(i)

            self._update_progress(i, total_groups, f"Analyzing group {i}/{total_groups}")

            # Log recommendation with lyrics info
            duplicates_logger.info(f"\nRecommendation for group {identifier[:50]}...")
            duplicates_logger.info(f"  Keep: {recommendation['keep']}")
            if self.check_lyrics:
                keep_lyrics = "Yes" if files_info[0]['has_lyrics'] else "No"
                duplicates_logger.info(f"    Lyrics: {keep_lyrics} (length: {files_info[0]['lyrics_length']} chars)")
            for remove_file in recommendation['remove']:
                duplicates_logger.info(f"  Remove: {remove_file}")

        if progress:
            progress.finish()

        logger.info(f"Analysis complete. Found {len(recommendations)} recommendation groups")
        return recommendations

    def move_duplicates_to_quarantine(self, recommendations: List[Dict],
                                      quarantine_dir: Path = None) -> List[Path]:
        """
        Move duplicate files to quarantine

        Args:
            recommendations: List of recommendations from analyze_duplicates
            quarantine_dir: Directory for quarantine (default: DUPLICATES_DIR)

        Returns:
            List of moved files
        """
        if quarantine_dir is None:
            quarantine_dir = DUPLICATES_DIR / "quarantine"

        quarantine_dir.mkdir(parents=True, exist_ok=True)
        moved_files = []

        # Count total files to move
        total_to_move = sum(len(rec['remove']) for rec in recommendations)
        logger.info(f"Moving {total_to_move} duplicate files to quarantine")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create progress indicator
        if self.show_progress and total_to_move > 0:
            progress = get_progress_indicator(
                total_to_move,
                "Moving duplicates to quarantine",
                self.use_tqdm
            )
        else:
            progress = None

        moved_count = 0
        for rec in recommendations:
            for remove_file in rec['remove']:
                try:
                    # Create unique name for moved file
                    new_name = f"{timestamp}_{remove_file.name}"
                    dest_path = quarantine_dir / new_name

                    # Save information about origin
                    info_file = quarantine_dir / f"{new_name}.json"
                    with open(info_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            'original_path': str(remove_file),
                            'original_name': remove_file.name,
                            'reason': f"Duplicate of {rec['keep'].name}",
                            'timestamp': timestamp,
                            'has_lyrics': self._has_lyrics(remove_file) if self.check_lyrics else False
                        }, f, indent=2, ensure_ascii=False)

                    # Move file
                    shutil.move(str(remove_file), str(dest_path))
                    moved_files.append(dest_path)
                    moved_count += 1

                    logger.info(f"Moved duplicate to quarantine: {remove_file} -> {dest_path}")
                    duplicates_logger.info(f"Moved duplicate: {remove_file}")

                    # Update progress
                    if progress:
                        progress.update(moved_count)

                    self._update_progress(moved_count, total_to_move,
                                        f"Moving: {remove_file.name}")

                except Exception as e:
                    logger.error(f"Error moving {remove_file}: {e}")

        if progress:
            progress.finish()

        logger.info(f"Moved {len(moved_files)} files to quarantine")
        return moved_files

    def generate_duplicate_report(self, recommendations: List[Dict],
                                  report_path: Path = None) -> Path:
        """
        Generate detailed HTML report about duplicates

        Args:
            recommendations: List of recommendations from analyze_duplicates
            report_path: Path to save the report (auto-generated if None)

        Returns:
            Path to the generated report
        """
        if report_path is None:
            report_path = DUPLICATES_DIR / f"duplicate_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        logger.info(f"Generating duplicate report: {report_path}")

        if self.show_progress:
            print("  Generating HTML report...")

        html_content = self._generate_html_report(recommendations)

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Duplicate report saved: {report_path}")
        return report_path

    def _generate_html_report(self, recommendations: List[Dict]) -> str:
        """Generate HTML report about duplicates"""
        html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Duplicate Audio Files Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .duplicate-group {{ border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; }}
        .keep {{ background-color: #d4edda; border-left: 4px solid #28a745; }}
        .remove {{ background-color: #f8d7da; border-left: 4px solid #dc3545; margin: 10px 0; padding: 10px; }}
        .file-info {{ margin: 5px 0; font-family: monospace; }}
        .score {{ font-weight: bold; }}
        h1 {{ color: #333; }}
        h3 {{ margin-top: 0; }}
        .summary {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }}
        .badge-keep {{ background: #28a745; color: white; }}
        .badge-remove {{ background: #dc3545; color: white; }}
        .badge-lyrics {{ background: #17a2b8; color: white; }}
        .badge-no-lyrics {{ background: #6c757d; color: white; }}
        .file-details {{ margin-left: 20px; }}
        .metadata {{ font-size: 12px; color: #666; margin-left: 20px; }}
        .lyrics-info {{ font-size: 13px; margin-left: 20px; }}
    </style>
</head>
<body>
    <h1>📊 Duplicate Audio Files Report</h1>
    <div class="summary">
        <p><strong>Generated:</strong> {timestamp}</p>
        <p><strong>Duplicate groups found:</strong> {total_groups}</p>
        <p><strong>Total files in groups:</strong> {total_files}</p>
        <p><strong>Recommended to keep:</strong> {keep_files}</p>
        <p><strong>Recommended to remove:</strong> {remove_files}</p>
        <p><strong>Files with lyrics (kept):</strong> {keep_with_lyrics}</p>
    </div>
"""

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_files = sum(len(rec['all_files']) for rec in recommendations)
        keep_files = len(recommendations)
        remove_files = sum(len(rec['remove']) for rec in recommendations)
        keep_with_lyrics = sum(1 for rec in recommendations if rec.get('has_lyrics_keep', False))

        html = html.format(
            timestamp=timestamp,
            total_groups=len(recommendations),
            total_files=total_files,
            keep_files=keep_files,
            remove_files=remove_files,
            keep_with_lyrics=keep_with_lyrics
        )

        for i, rec in enumerate(recommendations, 1):
            # Information about file recommended to keep
            keep_info = next(f for f in rec['analysis'] if f['path'] == rec['keep'])

            # Lyrics badge for keep file
            lyrics_badge = ""
            if self.check_lyrics and keep_info.get('has_lyrics', False):
                lyrics_badge = f"<span class='badge badge-lyrics'>🎤 Has Lyrics ({keep_info.get('lyrics_length', 0)} chars)</span>"
            elif self.check_lyrics:
                lyrics_badge = "<span class='badge badge-no-lyrics'>No Lyrics</span>"

            html += f"""
    <div class="duplicate-group">
        <h3>Duplicate Group #{i}</h3>
        <div class="keep">
            <strong>✅ Keep:</strong>
            {lyrics_badge}
            <div class="file-details">
                <div class="file-info">📁 {rec['keep']}</div>
                <div class="file-info">📦 Size: {rec['keep'].stat().st_size:,} bytes ({rec['keep'].stat().st_size / 1024 / 1024:.2f} MB)</div>
                <div class="file-info">⭐ Quality score: {keep_info['score']}</div>
                <div class="metadata">
                    <strong>Metadata:</strong>
                    {self._format_metadata(keep_info['metadata'])}
                </div>
                {self._format_lyrics_info(keep_info) if self.check_lyrics else ''}
            </div>
        </div>
        <div style="margin-top: 15px;">
            <strong>❌ Remove ({len(rec['remove'])} files):</strong>
        """

            for remove_file in rec['remove']:
                remove_info = next(f for f in rec['analysis'] if f['path'] == remove_file)

                # Lyrics badge for remove files
                remove_lyrics_badge = ""
                if self.check_lyrics and remove_info.get('has_lyrics', False):
                    remove_lyrics_badge = f"<span class='badge badge-lyrics'>🎤 Has Lyrics ({remove_info.get('lyrics_length', 0)} chars)</span>"
                elif self.check_lyrics:
                    remove_lyrics_badge = "<span class='badge badge-no-lyrics'>No Lyrics</span>"

                html += f"""
            <div class="remove">
                <div class="file-details">
                    <div class="file-info">📁 {remove_file}</div>
                    <div class="file-info">📦 Size: {remove_file.stat().st_size:,} bytes ({remove_file.stat().st_size / 1024 / 1024:.2f} MB)</div>
                    <div class="file-info">⭐ Quality score: {remove_info['score']}</div>
                    {remove_lyrics_badge}
                    <div class="metadata">
                        <strong>Metadata:</strong>
                        {self._format_metadata(remove_info['metadata'])}
                    </div>
                    {self._format_lyrics_info(remove_info) if self.check_lyrics else ''}
                </div>
            </div>
            """

            html += """
        </div>
    </div>
    """

        html += """
    <div style="margin-top: 30px; padding: 15px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 5px;">
        <h3>⚠️ Instructions for Removing Duplicates</h3>
        <ol>
            <li>Verify that all files marked as "Keep" are indeed the best versions</li>
            <li>Files marked as "Remove" are duplicates and can be safely deleted</li>
            <li><strong>Lyrics criterion:</strong> Files with embedded lyrics are given higher priority</li>
            <li>If you used the --quarantine option, duplicates have been moved to the quarantine folder</li>
            <li>After verification, you can delete files from quarantine</li>
        </ol>
    </div>
    <div style="margin-top: 20px; color: #666; font-size: 12px;">
        <p>Report generated automatically. Time: {timestamp}</p>
    </div>
</body>
</html>
    """.format(timestamp=timestamp)

        return html

    def _format_metadata(self, metadata: Dict) -> str:
        """Format metadata for HTML display"""
        if not metadata:
            return "<span style='color: #999;'>No data</span>"

        items = []
        for key, value in metadata.items():
            if value:
                items.append(f"<span style='margin-right: 10px;'><strong>{key}:</strong> {value}</span>")

        if not items:
            return "<span style='color: #999;'>No data</span>"

        return " ".join(items)

    def _format_lyrics_info(self, file_info: Dict) -> str:
        """Format lyrics information for HTML display"""
        if not self.check_lyrics:
            return ""

        has_lyrics = file_info.get('has_lyrics', False)
        lyrics_length = file_info.get('lyrics_length', 0)

        if has_lyrics:
            return f"""
                <div class="lyrics-info">
                    <strong>🎤 Lyrics:</strong> Present ({lyrics_length} characters)
                </div>
            """
        else:
            return """
                <div class="lyrics-info">
                    <strong>🎤 Lyrics:</strong> Not found
                </div>
            """

    def process_with_full_progress(self, files: List[Path],
                                   quarantine: bool = False,
                                   report_path: Path = None) -> Dict:
        """
        Complete duplicate processing pipeline with progress indication

        Args:
            files: List of files to check for duplicates
            quarantine: Whether to move duplicates to quarantine
            report_path: Path to save the report

        Returns:
            Dictionary with processing results
        """
        logger.info(f"Starting full duplicate processing for {len(files)} files")

        # Step 1: Find duplicates
        duplicates = self.find_duplicates(files)

        if not duplicates:
            logger.info("No duplicates found")
            return {
                'duplicates_found': False,
                'groups': 0,
                'files_affected': 0,
                'recommendations': []
            }

        # Step 2: Analyze duplicates
        recommendations = self.analyze_duplicates(duplicates)

        # Step 3: Generate report
        report_path = self.generate_duplicate_report(recommendations, report_path)

        # Step 4: Move to quarantine if requested
        moved_files = []
        if quarantine:
            moved_files = self.move_duplicates_to_quarantine(recommendations)

        total_files = sum(len(rec['all_files']) for rec in recommendations)
        keep_files = len(recommendations)
        remove_files = sum(len(rec['remove']) for rec in recommendations)
        keep_with_lyrics = sum(1 for rec in recommendations if rec.get('has_lyrics_keep', False))

        result = {
            'duplicates_found': True,
            'groups': len(recommendations),
            'total_files': total_files,
            'keep_files': keep_files,
            'remove_files': remove_files,
            'keep_with_lyrics': keep_with_lyrics,
            'recommendations': recommendations,
            'report_path': report_path,
            'moved_to_quarantine': len(moved_files),
            'quarantine_files': moved_files
        }

        logger.info(f"Processing complete: {result}")
        return result