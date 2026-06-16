"""Command-line interface for the music metadata utility"""
import argparse
import sys
from pathlib import Path

from audio_processor import AudioProcessor
from file_organizer import FileOrganizer
from logger_config import get_logger
from progress_indicator import SpinnerIndicator, SimpleProgressBar

logger = get_logger(__name__)


def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(
        description='Music Metadata Tool - Process and organize audio files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
      # Set artist for all files in a folder
      python cli.py set-metadata -f /path/to/music -a "The Beatles"
      
      # Set artist and album
      python cli.py set-metadata -f /path/to/music -a "Nirvana" -b "Nevermind"
      
      # Set full metadata
      python cli.py set-metadata -f /path/to/music -a "Pink Floyd" -b "The Wall" -y 1979
      
      # Use filenames as titles
      python cli.py set-metadata -f /path/to/music --title-from-filename
      
      # Organize files into folders (artist/album)
      python cli.py organize -s /path/to/source -t /path/to/target
      
      # Find and process duplicates (with lyrics check by default)
      python cli.py find-duplicates -f /path/to/music
      
      # Find duplicates without lyrics check
      python cli.py find-duplicates -f /path/to/music --no-lyrics
      
      # Preview mode (dry run)
      python cli.py set-metadata -f /path/to/music -a "Queen" --dry-run
      
      # Legacy command (still works)
      python cli.py set-artist -f /path/to/music -a "The Beatles"
      
      # Disable progress bar (for scripts)
      python cli.py set-metadata -f /path/to/music -a "Queen" --no-progress
            """
    )

    # Global options for all commands
    parser.add_argument('--no-progress', action='store_true', help='Disable progress indicators')
    parser.add_argument('--no-tqdm', action='store_true', help='Use simple progress bar instead of tqdm')

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Command: set-metadata (NEW - more powerful)
    set_metadata_parser = subparsers.add_parser('set-metadata', help='Set metadata for audio files')
    set_metadata_parser.add_argument('-f', '--folder', required=True, help='Path to folder with music')
    set_metadata_parser.add_argument('-a', '--artist', help='Artist name to set')
    set_metadata_parser.add_argument('-b', '--album', help='Album name to set')
    set_metadata_parser.add_argument('-t', '--title', help='Title to set')
    set_metadata_parser.add_argument('-y', '--year', help='Year to set')
    set_metadata_parser.add_argument('-n', '--track', type=int, help='Track number to set')
    set_metadata_parser.add_argument('--title-from-filename', action='store_true',
                                     help='Use filename (without extension) as title')
    set_metadata_parser.add_argument('-r', '--recursive', action='store_true',
                                     help='Process subdirectories recursively')
    set_metadata_parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    set_metadata_parser.add_argument('--no-backup', action='store_true', help='Skip creating backup files')
    set_metadata_parser.add_argument('--spinner', action='store_true', help='Use spinner instead of progress bar')

    # Command: set-artist (legacy, kept for backward compatibility)
    set_artist_parser = subparsers.add_parser('set-artist', help='Set artist for audio files (legacy)')
    set_artist_parser.add_argument('-f', '--folder', required=True, help='Path to folder with music')
    set_artist_parser.add_argument('-a', '--artist', required=True, help='Artist name to set')
    set_artist_parser.add_argument('-r', '--recursive', action='store_true', help='Process subdirectories recursively')
    set_artist_parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    set_artist_parser.add_argument('--no-backup', action='store_true', help='Skip creating backup files')
    set_artist_parser.add_argument('--spinner', action='store_true', help='Use spinner instead of progress bar')

    # Command: organize
    organize_parser = subparsers.add_parser('organize', help='Organize files by metadata')
    organize_parser.add_argument('-s', '--source', required=True, help='Source directory')
    organize_parser.add_argument('-t', '--target', required=True, help='Target directory')
    organize_parser.add_argument('--no-duplicates', action='store_true', help='Skip duplicate handling')
    organize_parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    organize_parser.add_argument('--no-backup', action='store_true', help='Skip creating backup files')
    organize_parser.add_argument('--no-lyrics', action='store_true', help='Disable lyrics check when handling duplicates (enabled by default)')

    # Command: find-duplicates
    duplicates_parser = subparsers.add_parser('find-duplicates', help='Find duplicate files')
    duplicates_parser.add_argument('-f', '--folder', required=True, help='Path to folder')
    duplicates_parser.add_argument('--report', help='Save report to specific file')
    duplicates_parser.add_argument('--quarantine', action='store_true', help='Move duplicates to quarantine')
    duplicates_parser.add_argument('--no-lyrics', action='store_true',
                                   help='Disable lyrics presence check (enabled by default)')

    # Command: clean-backups
    clean_parser = subparsers.add_parser('clean-backups', help='Remove backup files')
    clean_parser.add_argument('-f', '--folder', help='Path to folder (recursive)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == 'set-metadata':
            cmd_set_metadata(args)
        elif args.command == 'set-artist':
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
        print("\n\n⚠️  Operation cancelled by user")
        logger.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


def cmd_set_metadata(args):
    """Handle set-metadata command"""
    folder = Path(args.folder)
    if not folder.exists():
        print(f"❌ Folder does not exist: {folder}")
        logger.error(f"Folder does not exist: {folder}")
        sys.exit(1)

    # Build description of changes
    changes = []
    if args.artist: changes.append(f"artist='{args.artist}'")
    if args.album: changes.append(f"album='{args.album}'")
    if args.title: changes.append(f"title='{args.title}'")
    if args.year: changes.append(f"year='{args.year}'")
    if args.track is not None: changes.append(f"track={args.track}")
    if args.title_from_filename: changes.append("title=filename")

    if not changes:
        print("❌ No metadata changes specified. Use -a, -b, -t, -y, -n, or --title-from-filename")
        sys.exit(1)

    print(f"\n🎵 Processing folder: {folder}")
    print(f"📝 Changes: {', '.join(changes)}")
    if args.dry_run:
        print("🔍 DRY RUN MODE (changes will not be applied)")

    processor = AudioProcessor(
        dry_run=args.dry_run,
        backup=not args.no_backup,
        show_progress=not args.no_progress,
        use_tqdm=not args.no_tqdm
    )

    if args.spinner:
        processed, errors = processor.set_metadata_with_spinner(
            folder_path=folder,
            artist=args.artist,
            album=args.album,
            title=args.title,
            year=args.year,
            track=args.track,
            use_filename_as_title=args.title_from_filename,
            recursive=args.recursive
        )
    else:
        processed, errors = processor.set_metadata_in_folder(
            folder_path=folder,
            artist=args.artist,
            album=args.album,
            title=args.title,
            year=args.year,
            track=args.track,
            use_filename_as_title=args.title_from_filename,
            recursive=args.recursive
        )

    # Display results
    print(f"\n📊 Results:")
    print(f"  ✅ Successfully processed: {processed}")
    if errors > 0:
        print(f"  ❌ Errors: {errors}")
    if args.dry_run:
        print("  🔍 Mode: DRY RUN (changes not applied)")

    if not args.dry_run and processor.backup_files:
        print(f"\n💾 Created {len(processor.backup_files)} backup files")
        print("   To remove backups: python cli.py clean-backups -f <folder>")

    if errors == 0 and processed > 0:
        print("\n✅ Operation completed successfully!")
    elif errors > 0:
        print(f"\n⚠️  Operation completed with {errors} errors. Check the log.")


def cmd_set_artist(args):
    """Handle set-artist command (legacy)"""
    print("ℹ️  Note: 'set-artist' is a legacy command. Use 'set-metadata' for more features.")

    folder = Path(args.folder)
    if not folder.exists():
        print(f"❌ Folder does not exist: {folder}")
        logger.error(f"Folder does not exist: {folder}")
        sys.exit(1)

    print(f"\n🎵 Processing folder: {folder}")
    print(f"📝 Setting artist: {args.artist}")
    if args.dry_run:
        print("🔍 DRY RUN MODE (changes will not be applied)")

    processor = AudioProcessor(
        dry_run=args.dry_run,
        backup=not args.no_backup,
        show_progress=not args.no_progress,
        use_tqdm=not args.no_tqdm
    )

    if args.spinner:
        processed, errors = processor.set_artist_with_spinner(
            folder_path=folder,
            artist_name=args.artist,
            recursive=args.recursive
        )
    else:
        processed, errors = processor.set_artist_in_folder(
            folder_path=folder,
            artist_name=args.artist,
            recursive=args.recursive
        )

    # Display results
    print(f"\n📊 Results:")
    print(f"  ✅ Successfully processed: {processed}")
    if errors > 0:
        print(f"  ❌ Errors: {errors}")
    if args.dry_run:
        print("  🔍 Mode: DRY RUN (changes not applied)")

    if not args.dry_run and processor.backup_files:
        print(f"\n💾 Created {len(processor.backup_files)} backup files")
        print("   To remove backups: python cli.py clean-backups -f <folder>")

    if errors == 0 and processed > 0:
        print("\n✅ Operation completed successfully!")
    elif errors > 0:
        print(f"\n⚠️  Operation completed with {errors} errors. Check the log.")


def cmd_organize(args):
    """Handle organize command"""
    source = Path(args.source)
    target = Path(args.target)

    if not source.exists():
        print(f"❌ Source folder does not exist: {source}")
        logger.error(f"Source folder does not exist: {source}")
        sys.exit(1)

    print(f"\n📁 Organizing files")
    print(f"  📂 Source: {source}")
    print(f"  📂 Target: {target}")
    if args.dry_run:
        print("  🔍 DRY RUN MODE (changes will not be applied)")

    organizer = FileOrganizer(
        dry_run=args.dry_run,
        backup=not args.no_backup,
        show_progress=not args.no_progress,
        use_tqdm=not args.no_tqdm,
        check_lyrics = not args.no_lyrics
    )

    result = organizer.organize_by_metadata(
        source_dir=source,
        target_dir=target,
        handle_duplicates=not args.no_duplicates
    )

    # Display results
    print(f"\n📊 Organization results:")
    print(f"  📁 Files found: {result['total_found']}")
    print(f"  ✅ Organized: {result['organized']}")
    if result['errors'] > 0:
        print(f"  ❌ Errors: {result['errors']}")
    if args.dry_run:
        print("  🔍 Mode: DRY RUN (changes not applied)")

    if result['organized'] > 0 and result['errors'] == 0:
        print("\n✅ Organization completed successfully!")
    elif result['errors'] > 0:
        print(f"\n⚠️  Organization completed with {result['errors']} errors. Check the log.")


def cmd_find_duplicates(args):
    """Handle find-duplicates command"""
    folder = Path(args.folder)
    if not folder.exists():
        print(f"❌ Folder does not exist: {folder}")
        logger.error(f"Folder does not exist: {folder}")
        sys.exit(1)

    # Show lyrics status
    lyrics_status = "disabled" if args.no_lyrics else "enabled"
    print(f"\n🔍 Searching for duplicates in: {folder}")
    print(f"📝 Lyrics check: {lyrics_status}")

    from duplicate_handler import DuplicateHandler

    handler = DuplicateHandler(
        check_lyrics=not args.no_lyrics,  # Enabled by default, disabled with --no-lyrics
        show_progress=not args.no_progress,
        use_tqdm=not args.no_tqdm,
    )

    # Find all audio files
    print("  📂 Scanning files...")
    with SpinnerIndicator("Searching for audio files") as spinner:
        audio_files = [f for f in folder.rglob('*')
                      if f.suffix.lower() in {'.mp3', '.flac', '.m4a', '.ogg', '.opus'}]
        spinner.update(len(audio_files))

    if not audio_files:
        print("❌ No audio files found")
        return

    print(f"  📁 Found files: {len(audio_files)}")

    # Find duplicates
    print("  🔍 Finding duplicates...")
    duplicates = handler.find_duplicates(audio_files)

    if not duplicates:
        print("✅ No duplicates found!")
        return

    print(f"  📊 Found {len(duplicates)} duplicate groups")

    # Analyze duplicates
    print("  📊 Analyzing duplicates...")
    if not args.no_lyrics:
        print("  🎤 Checking for embedded lyrics (bonus for files with lyrics)...")
    recommendations = handler.analyze_duplicates(duplicates)

    # Save report
    print("  💾 Saving report...")
    if args.report:
        report_path = Path(args.report)
    else:
        report_path = None
    report_path = handler.generate_duplicate_report(recommendations, report_path)
    print(f"  📄 Report saved: {report_path}")

    # Move to quarantine if requested
    if args.quarantine:
        print("  📦 Moving duplicates to quarantine...")
        moved = handler.move_duplicates_to_quarantine(recommendations)
        print(f"  📦 Moved to quarantine: {len(moved)} files")

    # Display statistics
    total_files = sum(len(rec['all_files']) for rec in recommendations)
    keep_files = len(recommendations)
    remove_files = sum(len(rec['remove']) for rec in recommendations)

    # Show lyrics statistics if enabled
    print(f"\n📊 Duplicate statistics:")
    print(f"  📁 Total files in groups: {total_files}")
    print(f"  ✅ Recommended to keep: {keep_files}")
    print(f"  ❌ Recommended to remove: {remove_files}")

    if not args.no_lyrics:
        keep_with_lyrics = sum(1 for rec in recommendations if rec.get('has_lyrics_keep', False))
        print(f"  🎤 Keep files with lyrics: {keep_with_lyrics} / {keep_files}")

    if args.quarantine:
        print(f"\n📦 Duplicates moved to quarantine in: logs/duplicates/quarantine")
        print("   Verify them before permanent deletion")
    else:
        print(f"\n💡 To move duplicates to quarantine, use: --quarantine")

    print(f"\n📄 Detailed report: {report_path}")


def cmd_clean_backups(args):
    """Handle clean-backups command"""
    if args.folder:
        folder = Path(args.folder)
        if not folder.exists():
            print(f"❌ Folder does not exist: {folder}")
            logger.error(f"Folder does not exist: {folder}")
            sys.exit(1)

        print(f"\n🧹 Searching for backup files in: {folder}")

        # Find backup files
        with SpinnerIndicator("Searching for .backup files") as spinner:
            backup_files = list(folder.rglob('*.backup'))
            spinner.update(len(backup_files))

        if not backup_files:
            print("✅ No backup files found")
            return

        print(f"  📁 Found {len(backup_files)} backup files")

        # Show a few examples
        for backup in backup_files[:5]:
            print(f"    - {backup}")
        if len(backup_files) > 5:
            print(f"    ... and {len(backup_files) - 5} more files")

        response = input("\nDelete all backup files? (y/N): ")

        if response.lower() == 'y':
            print("  🗑️  Deleting...")
            with SimpleProgressBar(len(backup_files), "Deleting") as prog:
                for i, backup in enumerate(backup_files, 1):
                    try:
                        backup.unlink()
                        logger.info(f"Deleted: {backup}")
                    except Exception as e:
                        logger.error(f"Error deleting {backup}: {e}")
                    prog.update(i)
            print(f"\n✅ Deleted {len(backup_files)} backup files")
        else:
            print("❌ Operation cancelled")
    else:
        print("\n⚠️  Specify a folder to clean backups: --folder <path>")
        print("   Example: python cli.py clean-backups -f /path/to/music")


if __name__ == "__main__":
    main()
