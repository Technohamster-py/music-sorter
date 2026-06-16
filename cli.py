import argparse
import sys
from pathlib import Path
from urllib import response
from xml.sax import handler

from audio_processor import AudioProcessor
from file_organizer import FileOrganizer
from logger_config import get_logger

logger = get_logger(__name__)

def main():
    parser = argparse.ArgumentParser(description="A utility for working with audio file metadata",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="""
                                            Usage examples:
                                            # Set an artist for all files in a folder
                                              python cli.py set-artist -f /path/to/music -a "The Beatles"
                                            
                                            # Organize files by folders (artist/album)
                                            python cli.py organize -s /path/to/source -t /path/to/target
                                            
                                            # Find and process duplicates
                                              python cli.py find-duplicates -f /path/to/music
                                            
                                            # Preview (dry run)
                                            python cli.py organize -s /path/to/source -t /path/to/target --dry-run 
                                     """)

    subparsers = parser.add_subparsers(dest="command", help="command")

    set_artist_parser = subparsers.add_parser("set-artist", help="Set an artist")
    set_artist_parser.add_argument("-f", '--folder', required=True, help="Path to the music folder")
    set_artist_parser.add_argument("-a", '--artist', required=True, help="Artist name")
    set_artist_parser.add_argument('-r', '--recursive', action='store_true', help="Recursive mode")
    set_artist_parser.add_argument('--dry-run', action='store_true', help="Show what would be done")
    set_artist_parser.add_argument('--no-backup', action='store_true', help="Don't create backups")

    organize_parser = subparsers.add_parser("organize", help="Organize files")
    organize_parser.add_argument("-s" '--source', required=True, help="Path to the music folder")
    organize_parser.add_argument("-t", '--target', required=True, help="Target folder")
    organize_parser.add_argument("--no-duplicates", action='store_true', help="Don't process duplicate files")
    organize_parser.add_argument('--dry-run', action='store_true', help="Show what would be done")
    organize_parser.add_argument('--no-backup', action='store_true', help="Don't create backups")

    duplicates_parser = subparsers.add_parser("find-duplicates", help="Find duplicate files")
    duplicates_parser.add_argument("-f", "--folder", required=True, help="Path to the music folder")
    duplicates_parser.add_argument("--report", help="Save report to file")
    duplicates_parser.add_argument('--quarantine', action='store_true', help="Move duplicate files to quarantine")

    clean_parser = subparsers.add_parser("clean-backups", help="Remove backups")
    clean_parser.add_argument("-f", "--folder", required=True, help="Path to folder (recursive)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == 'set-artist':
            cmd_set_artist(args)
        elif args.command == 'organize':
            cmd_organize(args)
        elif args.command == 'find-duplicates':
            cmd_find_duplicates(args)
        elif args.command == 'clean-backups':
            cmd_clean_backups(args)
        else:
            parser.print_help()
            sys.exit(1)


    except KeyboardInterrupt:
        logger.info(f"Operation interrupted by user")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        sys.exit(1)

def cmd_set_artist(args):
    folder = Path(args.folder)
    if not folder.exists():
        logger.error(f"Folder {folder} does not exist")
        sys.exit(1)

    processor = AudioProcessor(dry_run=args.dry_run, backup=not args.no_backup)
    processed, errors = processor.set_artist_in_folder(foler_path=folder, artist_name=args.artist, recursive=args.recursive)

    if not args.dry_run and processor.backup_files:
        print(f"\nCreated {len(processor.backup_files)} backup file(s)")
        print("To remove backups execute: python cli.py clean-backups -f <your/folder>")

def cmd_organize(args):
    source = Path(args.source)
    target = Path(args.target)

    if not source.exists():
        logger.error(f"Source folder {source} does not exist")
        sys.exit(1)

    organizer = FileOrganizer(dry_run=args.dry_run, bakup=not args.no_backup)

    result = organizer.organize_by_metadata(source_dir=source, target_dir=target, handle_duplicates=not args.no_duplicates)

    print(f"\nOrganisation result")
    print(f"\tFiles found: {result['total_found']}")
    print(f"\tOrganized files: {result['organized']}")
    print(f"\tErrors: {result['errors']}")
    if args.dry_run:
        print("\nThis is a DRY RUN; changes are NOT committed")

def cmd_find_duplicates(args):
    folder = Path(args.folder)
    if not folder.exists():
        logger.error(f"Folder {folder} does not exist")
        sys.exit(1)

    from duplicate_handler import DuplicateHandler
    handler = DuplicateHandler()

    audio_files = [f for f in folder.rglob('*') if f.suffix.lower() in {'.mp3', '.flac', '.m4a', '.ogg', '.opus'}]
    if not audio_files:
        logger.info(f"No audio files found in folder {folder}")
        return

    logger.info(f"Found {len(audio_files)} audio file(s)")

    duplicates = handler.find_duplicates(audio_files)
    if not duplicates:
        logger.info(f"No duplicate files found in folder {folder}")
        return

    logger.info(f"Found {len(duplicates)} froups of duplicate file(s)")
    recomendations = handler.analyze_duplicates(duplicates)

    report_path = handler.generate_duplicate_report(recomendations)
    logger.info(f"Generated report at {report_path}")

    if args.quarantine:
        moved = handler.move_duplicates_to_quarantine(recomendations)
        logger.info(f"Moved to quarantine {len(moved)} duplicate file(s)")

    total_files = sum(len(rec['all_files']) for rec in recomendations)
    keep_files = len(recomendations)
    remove_files = sum(len(rec['remove']) for rec in recomendations)

    print(f"\nDuplicate statistics:")
    print(f"\tTotal files: {total_files} in groups")
    print(f"\tRecommended to keep: {keep_files}")
    print(f"\tRecommended to delete / move: {remove_files}")

def cmd_clean_backups(args):
    if args.folder:
        folder = Path(args.folder)
        if not folder.exists():
            logger.error(f"Folder {folder} does not exist")
            sys.exit(1)

        backup_files = list(folder.rglob('*.backup'))
        if not backup_files:
            logger.info(f"No backup files found in folder {folder}")
            return

        logger.info(f"Found {len(backup_files)} backup files")
        response = input("\nDelete all backups? (y/n) ")

        if response.lower() == 'y':
            for backup in backup_files:
                try:
                    backup.unlink()
                    logger.info(f"Deleted {backup}")
                except Exception as e:
                    logger.error(f"Error while deleting backup {backup}")
            logger.info("All backups deleted")
        else:
            logger.info("Operation cancelled")

    else:
        logger.info(f"To remove all backups execute: python cli.py clean-backups --folder <your/folder>")


if __name__ == '__main__':
    main()