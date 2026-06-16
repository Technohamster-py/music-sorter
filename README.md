# 🎵 Music Metadata Tool

A powerful Python utility for managing, organizing, and cleaning up your music library. Edit metadata, find duplicates, and organize files automatically.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v2.0](https://img.shields.io/badge/License-GPL_2.0-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- **📝 Edit Metadata** - Batch edit artist, album, title, year, and track numbers
- **🔍 Find Duplicates** - Detect duplicate audio files using hash comparison and metadata analysis
- **📂 Organize Library** - Automatically sort files into `Artist/Album/` folder structure
- **🎤 Lyrics Detection** - Identify files with embedded lyrics (bonus for duplicate selection)
- **💾 Safe Operations** - Automatic backups and dry-run mode for previewing changes
- **📊 Detailed Reports** - Generate HTML reports about duplicates and library structure
- **🔄 Cross-Format Support** - Works with MP3, FLAC, M4A, OGG, Opus, and more
- **📈 Progress Indicators** - Visual progress bars with ETA for all operations

## 📦 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Install from source

```bash
# Clone the repository
git clone https://github.com/yourusername/music-metadata-tool.git
cd music-metadata-tool

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

### Dependencies
- `mutagen` - Audio metadata handling
- `tqdm` - Progress bars (optional but recommended)

## 🚀 Quick Start

### 1. Set metadata for all files in a folder

```bash
# Set only artist
python cli.py set-metadata -f /path/to/music -a "The Beatles"

# Set artist and album
python cli.py set-metadata -f /path/to/music -a "Nirvana" -b "Nevermind"

# Set full metadata
python cli.py set-metadata -f /path/to/music -a "Pink Floyd" -b "The Wall" -y 1979 -t "Another Brick in the Wall"

# Use filenames as titles
python cli.py set-metadata -f /path/to/music --title-from-filename

# Preview changes without applying (dry run)
python cli.py set-metadata -f /path/to/music -a "Queen" --dry-run
```

### 2. Organize files by metadata

```bash
# Basic organization
python cli.py organize -s /path/to/source -t /path/to/target

# Organize with duplicate handling
python cli.py organize -s /path/to/source -t /path/to/target

# Preview organization (dry run)
python cli.py organize -s /path/to/source -t /path/to/target --dry-run
```

### 3. Find and handle duplicates

```bash
# Find duplicates and generate report
python cli.py find-duplicates -f /path/to/music

# Find duplicates and move them to quarantine
python cli.py find-duplicates -f /path/to/music --quarantine

# Save report to custom location
python cli.py find-duplicates -f /path/to/music --report my_report.html
```

### 4. Clean up backup files

```bash
# Remove all .backup files
python cli.py clean-backups -f /path/to/music
```

## 📋 Command Reference

### Global Options

| Option          | Description                             |
|-----------------|-----------------------------------------|
| `--no-progress` | Disable progress indicators             |
| `--no-tqdm`     | Use simple progress bar instead of tqdm |
| `-h, --help`    | Show help message                       |

### set-metadata Command

Set metadata for audio files in a folder.

| Option                  | Description                          |
|-------------------------|--------------------------------------|
| `-f, --folder`          | Path to folder with music (required) |
| `-a, --artist`          | Artist name to set                   |
| `-b, --album`           | Album name to set                    |
| `-t, --title`           | Title to set                         |
| `-y, --year`            | Year to set                          |
| `-n, --track`           | Track number to set                  |
| `--title-from-filename` | Use filename as title                |
| `-r, --recursive`       | Process subdirectories               |
| `--dry-run`             | Preview changes without applying     |
| `--no-backup`           | Skip creating backup files           |
| `--spinner`             | Use spinner instead of progress bar  |

### organize Command

Organize files into folder structure (Artist/Album).

| Option            | Description                      |
|-------------------|----------------------------------|
| `-s, --source`    | Source directory (required)      |
| `-t, --target`    | Target directory (required)      |
| `--no-duplicates` | Skip duplicate handling          |
| `--dry-run`       | Preview changes without applying |
| `--no-backup`     | Skip creating backup files       |

### find-duplicates Command

Find and analyze duplicate files.

| Option         | Description                   |
|----------------|-------------------------------|
| `-f, --folder` | Path to folder (required)     |
| `--report`     | Save report to specific file  |
| `--quarantine` | Move duplicates to quarantine |

### clean-backups Command

Remove backup files.

| Option         | Description                |
|----------------|----------------------------|
| `-f, --folder` | Path to folder (recursive) |

## 📁 Project Structure

```
music-metadata-tool/
├── cli.py                 # Command-line interface
├── audio_processor.py     # Metadata editing logic
├── file_organizer.py      # File organization logic
├── duplicate_handler.py   # Duplicate detection & handling
├── progress_indicator.py  # Progress indicators
├── logger_config.py       # Logging configuration
├── config.py              # Configuration settings
├── logs/                  # Log files
│   ├── processing.log     # All processing events
│   ├── duplicates.log     # Duplicate information
│   ├── errors.log         # Error logs
│   └── duplicates/        # Duplicate reports & quarantine
│       ├── quarantine/    # Moved duplicate files
│       └── *.html         # HTML reports
└── README.md              # This file
```

## 🎯 Use Cases

### Organize a Messy Music Collection

```bash
# Step 1: Preview what will happen
python cli.py organize -s ~/Downloads/Music -t ~/Music/Library --dry-run

# Step 2: Actually organize
python cli.py organize -s ~/Downloads/Music -t ~/Music/Library

# Step 3: Find and handle any duplicates
python cli.py find-duplicates -f ~/Music/Library --quarantine
```

### Batch Update Metadata

```bash
# Add missing artist and album info
python cli.py set-metadata -f ~/Music/Library/Unknown -a "Radiohead" -b "OK Computer"

# Use filenames as titles
python cli.py set-metadata -f ~/Music/Library/Tracks --title-from-filename -a "Coldplay"
```

### Clean Up After Import

```bash
# Remove all backup files created by the tool
python cli.py clean-backups -f ~/Music/Library
```

## 🔧 Configuration

Edit `config.py` to customize behavior:

```python
# Organization pattern
ORGANIZE_PATTERN = "{artist}/{album}/{track:02d} - {title}{ext}"

# Duplicate detection fields
DUPLICATE_CHECK_FIELDS = ['title', 'artist', 'duration']

# Supported audio formats
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.m4b', '.ogg', '.opus', '.wma', '.aac'}
```

## 📊 Report Examples

The tool generates detailed HTML reports with:

- Summary statistics
- Duplicate groups with quality scores
- Metadata comparison
- Lyrics presence indicator
- Recommendations for keeping/deleting

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Write clear, documented code
- Add tests for new features
- Update README if needed
- Use English for code and comments
- Follow PEP 8 style guide

## 📝 License

This project is licensed under the GPL License – see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Mutagen](https://github.com/quodlibet/mutagen) – Audio metadata library
- [tqdm](https://github.com/tqdm/tqdm) – Progress bars
- All contributors and users of this tool

## ❓ FAQ

### Does it support all audio formats?

Currently supports MP3, FLAC, M4A, OGG, Opus, WMA, and AAC.

### Will it damage my files?

No! The tool creates backup files (.backup) before any modifications. You can also use `--dry-run` to preview changes.

### How does duplicate detection work?

It uses multiple methods:
1. File hash comparison (most accurate)
2. Metadata matching (artist, title, duration)
3. Fuzzy title matching (handles slight variations)

### Where are backup files stored?

Backup files are created in the same directory as the original files with a `.backup` extension. Use `clean-backups` to remove them.

### Can I undo changes?

Yes! Either:
- Use the `.backup` files (rename back to original)
- Use version control if you're managing files with git

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/Technohamster-py/music-sorter/issues)

---

Made with ❤️ for music lovers everywhere.