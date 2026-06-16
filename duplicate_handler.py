import  hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional
import mutagen
from pip._internal.operations.build import metadata

from config import DUPLICATES_DIR, DUPLICATE_CHECK_FIELDS, DUPLICATE_MATCH_THRESHOLD
from logger_config import get_logger, duplicates_logger

logger = get_logger(__name__)
duplicates_logger = get_logger("duplicates")

class DuplicateHandler:
    def __init__(self, compare_by_hash: bool = True, compare_by_metadata: bool = True):
        self.compare_by_hash = compare_by_hash
        self.compare_by_metadata = compare_by_metadata
        self.duplicates_found = []

    def find_duplicates(self, files: List[Path]) -> Dict[str, List[Path]]:
        file_info = {}

        for file_path in files:
            info = self._get_file_identifier(file_path)
            if info:
                file_info[str(file_path)] = info

        from collections import defaultdict
        grouped = defaultdict(list)
        for path, identifier in file_info.items():
            grouped[identifier].append(Path(path))

        duplicates = {k: v for k, v in grouped.items() if len(v) > 1}
        self.duplicates_found = duplicates

        if duplicates:
            duplicates_logger.info(f"Found {len(duplicates)} duplicate groups:")
            for identifier, paths in duplicates.items():
                duplicates_logger.info(f"  Group: {identifier[:100]}...")
                for path in paths:
                    duplicates_logger.info(f"        - {path}")

        return duplicates


    def _get_file_identifier(self, file_path: Path) -> Optional[str]:
        identifiers = []

        if self.compare_by_hash:
            file_hash = self._calculate_file_hash(file_path)
            if file_hash:
                identifiers.append(f"hash_{file_hash}")

        if self.compare_by_metadata:
            metadata = self._extract_metadata(file_path)
            if metadata:
                key_parts = []
                for field in DUPLICATE_CHECK_FIELDS:
                    if field in metadata and metadata[field]:
                        key_parts.append(f"{field}={metadata[field]}")

                if key_parts:
                    identifiers.append("||".join(key_parts))

                if 'title' in metadata and 'artist' in metadata:
                    fuzzy_key = self._create_fuzzy_key(metadata['title'], metadata['artist'])
                    identifiers.append(f"fuzzy_{fuzzy_key}")

        for identifier in identifiers:
            if identifier.startswith("hash_"):
                return identifier
        for identifier in identifiers:
            if identifier.startswith("fuzzy_"):
                return identifier
        for identifier in identifiers:
            if identifier:
                return identifier

        return None

    def _calculate_file_hash(self, file_path: Path, algorithm="md5") -> Optional[str]:
        try:
            has_func = hashlib.new(algorithm)
            with file_path.open('rb') as f:
                for chunk in iter(lambda: f.read(1024*1024), b''):
                    has_func.update(chunk)
                    if f.tell() > 10*1024*1024:
                        break
            return has_func.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for file {file_path}: {e}")
            return None

    def _extract_metadata(self, file_path: Path) -> Dict:
        try:
            audio = mutagen.File(file_path, easy=True)
            if audio is None:
                return {}

            metadata = {}
            for field in DUPLICATE_CHECK_FIELDS:
                if field in audio and audio[field]:
                    metadata[field] = audio[field][0]
            metadata['size'] = file_path.stat().st_size
            return metadata

        except Exception as e:
            logger.error(f"Error extracting metadata from file {file_path}: {e}")
            return {}

    def _create_fuzzy_key(self, title: str, artist: str) -> str:
        import re
        title_clean = re.sub(r'[^\w\s]', '', title.lower())
        artist_clean = re.sub(r'[^\w\s]', '', artist.lower())

        return f"{artist_clean[:30]}_{title_clean[:50]}"


    def analyze_duplicates(self, duplicates: Dict[str, List[Path]]) -> List[Dict]:
        recommendations = []

        for identifier, paths in duplicates.items():
            files_info = []

            for path in paths:
                info = {
                    "path": path,
                    "size": path.stat().st_size,
                    "modified": datetime.fromtimestamp(path.stat().st_mtime),
                    "metadata": self._extract_metadata(path),
                    "score": 0
                }

                score = 0

                if len(paths) > 1:
                    max_size = max(p.stat().st_size for p in paths)
                    if info["size"] == max_size:
                        score += 10
                    elif info["size"] > max_size * 0.9:
                        score += 5
                    else:
                        score += 1

                metadata_count = len(info["metadata"])
                score += min(metadata_count * 2, 20)

                if len(paths) > 1:
                    newest = max(datetime.fromtimestamp(p.stat().st_mtime) for p in paths)
                    if info["modified"] == newest:
                        score += 5

                info["score"] = score
                files_info.append(info)

            files_info.sort(key=lambda x: x["score"], reverse=True)

            recommendation = {
                "identifier": identifier,
                "keep": files_info[0]["path"],
                "remove": [info["path"] for info in files_info[1:]],
                "all_files": paths,
                "analysis": files_info
            }

            recommendations.append(recommendation)

            duplicates_logger.info(f"Recommendation for group {identifier[:50]}...:")
            duplicates_logger.info(f"  Keep: {recommendation['keep']}")
            for remove_file in recommendation["remove"]:
                duplicates_logger.info(f"  Remove: {remove_file}")

        return recommendations

    def move_duplicates_to_quarantine(self, recommendations: List[Dict], quarantine_dir: Path=None) -> List[Path]:
        if quarantine_dir is None:
            quarantine_dir = Path(DUPLICATES_DIR) / "quarantine"

        quarantine_dir.mkdir(parents=True, exist_ok=True)
        moved_files = []

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for rec in recommendations:
            for remove_file in rec["remove"]:
                try:
                    new_name = f"{timestamp}_{remove_file.name}"
                    dest_path = quarantine_dir / new_name

                    info_file = quarantine_dir / f"{new_name}.json"
                    with info_file.open("w", encoding="utf-8") as f:
                        json.dump({
                            "original_path": str(remove_file),
                            "original_name": remove_file.name,
                            "reason": f"Duplicate of {rec['keep'].name}",
                            "timestamp": timestamp
                        }, f, indent=2, ensure_ascii=False)

                    shutil.move(str(remove_file), str(dest_path))
                    moved_files.append(dest_path)

                    logger.info(f"Duplicate moved to quarantine: {remove_file} -> {dest_path}")
                    duplicates_logger.info(f"Duplicate moved: {remove_file}")
                except Exception as e:
                    logger.error(f"Error while moving file {remove_file}: {e}")
        return moved_files

    def generate_duplicate_report(self, recommendations: List[Dict], report_path: Path = None):
        if report_path is None:
            report_path = DUPLICATES_DIR / f"duplicate_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        html_content = self._generate_html_report(recommendations)

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Duplicate report saved: {report_path}")
        return report_path

    def _generate_html_report(self, recommendations: List[Dict]) -> str:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Report on duplicate audio files</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .duplicate-group {{ border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; }}
                .keep {{ background-color: #d4edda; border-left: 4px solid #28a745; }}
                .remove {{ background-color: #f8d7da; border-left: 4px solid #dc3545; margin: 10px 0; padding: 10px; }}
                .file-info {{ margin: 5px 0; font-family: monospace; }}
                .score {{ font-weight: bold; }}
                h1 {{ color: #333; }}
                h3 {{ margin-top: 0; }}
            </style>
        </head>
        <body>
            <h1>Report on duplicate audio files</h1>
            <p>Generated: {timestamp}</p>
            <p>Duplicate groups found: {total_groups}</p>
        """

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html = html.format(timestamp=timestamp, total_groups=len(recommendations))

        for i, rec in enumerate(recommendations, 1):
            html += f"""
            <div class="duplicate-group">
                <h3>Duplicate group #{i}</h3>
                <div class="keep">
                    <strong>✓ Keep:</strong>
                    <div class="file-info">{rec['keep']}</div>
                    <div class="file-info">Size: {rec['keep'].stat().st_size:,} bytes</div>
                    <div class="file-info">Score: {rec['analysis'][0]['score']}</div>
                </div>
                <div>
                    <strong>✗ Remove ({len(rec['remove'])} files):</strong>
            """

            for remove_file in rec['remove']:
                html += f"""
                <div class="remove">
                    <div class="file-info">{remove_file}</div>
                    <div class="file-info">Size: {remove_file.stat().st_size:,} bytes</div>
                    <div class="file-info">Score: {next(f['score'] for f in rec['analysis'] if f['path'] == remove_file)}</div>
                </div>
                """

            html += "</div></div>"

        html += """
        </body>
        </html>
        """

        return html