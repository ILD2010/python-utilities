# ==================================================
# STANDARD LIBRARY IMPORTS
# ==================================================

from pathlib import Path
from datetime import datetime
import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
import hashlib


# ==================================================
# APPLICATION CONFIGURATION
# ==================================================

VERSION = "0.8"

FILE_TYPES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "Documents": [".pdf", ".docx", ".txt", ".xlsx"],
    "Videos": [".mp4", ".mov", ".mkv"],
    "Audio": [".mp3", ".wav", ".flac"],
    "Archives": [".zip", ".rar", ".7z", ".gz"],
    "Code": [".py", ".js", ".html", ".css", ".go"],
    "Installers": [".deb", ".exe", ".msi", ".appimage"],
    "Modeling": [".psd", ".ai", ".svg", ".obj", ".fbx", ".stl", ".dwg"],
    "Virtualization": [".iso", ".vmdk", ".ova", ".ovf", ".dmg"],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2"],
    "System": [".env", ".yaml", ".yml", ".ini", ".conf", ".log", ".sys", ".dll"],
    "Data": [".csv", ".json", ".xml", ".sql", ".db", ".pcap", ".sqlite"],
}


# ==================================================
# TIMESTAMP UTILITIES
# ==================================================

def now():
    return datetime.now().astimezone().isoformat()


# ==================================================
# FILE INTEGRITY VERIFICATION
# ==================================================

def calculate_file_hash(file_path):
    """Calculate and return the SHA-256 hash of a file"""

    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(65536)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


# ==================================================
# CROSS-PLATFORM LOG DIRECTORY
# ==================================================

def get_log_directory():

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "DownloadJanitor" / "logs"
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    return base / "downloadjanitor" / "logs"


# ==================================================
# FILE CATEGORIZATION
# ==================================================

def get_category(file):
    extension = file.suffix.lower()
    for category, extensions in FILE_TYPES.items():
        if extension in extensions:
            return category
    return "Other"


# ==================================================
# DESTINATION PATH PLANNING
# ==================================================

def get_destination(file, category):
    return file.parent / category


# ==================================================
# DUPLICATE FILE PROTECTION
# ==================================================

def get_unique_path(destination):
    if not destination.exists() and not destination.is_symlink():
        return destination
    counter = 1
    while True:
        candidate = destination.with_name(f"{destination.stem}_{counter}{destination.suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        counter += 1


# ==================================================
# JSON JOURNAL WRITING
# ==================================================

def write_journal(journal, path):
    """Atomically replace the JSON journal with its latest state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".janitor_", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(journal, handle, indent=4)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


# ==================================================
# JSON JOURNAL READING
# ==================================================

def read_journal(path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("operations"), list):
        raise ValueError("Invalid journal structure")
    return data


# ==================================================
# JOURNAL DISCOVERY
# ==================================================

def journals():
    directory = get_log_directory()
    if not directory.is_dir():
        return []
    return sorted(directory.glob("run_*.json"), reverse=True)

def choose_journal(run_id=None):
    available = journals()
    if run_id:
        matches = [path for path in available if path.stem == run_id or path.stem == f"run_{run_id}"]
        if not matches:
            raise ValueError(f"No journal found for run: {run_id}")
        return matches[0]
    if not available:
        raise ValueError("No journals found")
    # The newest run may have no moves; it is still the most recent run.
    return available[0]


# ==================================================
# FILE MOVEMENT AND OVERWRITE PROTECTION
# ==================================================

def copy_without_overwrite(source, destination, expected_hash):
    """Copy a file without overwriting, verify its SHA-256, then remove the source.

    The source is removed only after the destination passes verification.
    Interrupted operations may still require manual recovery.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        # 'xb' fails if the destination already exists (including most symlinks)..
        with source.open("rb") as reader, destination.open("xb") as writer:
            created = True
            shutil.copyfileobj(reader, writer)
            writer.flush()
            os.fsync(writer.fileno())
        shutil.copystat(source, destination)
        destination_hash = calculate_file_hash(destination)

        if destination_hash != expected_hash:
            raise ValueError(f"SHA-256 Verification failed: {destination.name}")
        
        source.unlink()

    except Exception:

        if created and source.exists():
            try:
                destination.unlink()
            except OSError:
                pass
        raise


# ==================================================
# JOURNAL INITIALIZATION
# ==================================================

def new_journal(directory):
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8]
    return {
        "version": VERSION,
        "run_id": run_id,
        "timestamp": now(),
        "directory": str(directory),
        "operations": [],
    }


# ==================================================
# FILE ORGANIZATION ENGINE
# ==================================================

def organize(directory, apply):
    if not directory.is_dir():
        print(f"[ERROR] Directory does not exist: {directory}")
        return 1

    print("=" * 55)
    print(f"DOWNLOADJANITOR v{VERSION}")
    print("=" * 55)
    print(f"Scanning: {directory}")
    print(f"Mode: {'APPLY' if apply else 'PREVIEW'}\n")

    journal = new_journal(directory) if apply else None
    journal_path = (get_log_directory() / f"run_{journal['run_id']}.json") if apply else None
    if apply:
        try:
            write_journal(journal, journal_path)
        except OSError as error:
            print(f"[ERROR] Cannot initialize journal: {error}")
            return 1

    file_count = folder_count = moved_count = preview_count = failed_count = 0
    category_count = {}

    try:
        items = sorted(directory.iterdir())
    except OSError as error:
        print(f"[ERROR] Cannot scan directory: {error}")
        return 1

    for item in items:
        # Symlinks are skipped to avoid following links outside the target.
        if item.is_symlink():
            print(f"[SKIP] Symbolic link: {item.name}")
            continue
        if item.is_dir():
            folder_count += 1
            print(f"[FOLDER] {item.name}")
            continue
        if not item.is_file():
            continue

        file_count += 1
        category = get_category(item)
        category_count[category] = category_count.get(category, 0) + 1
        destination = get_unique_path(get_destination(item, category) / item.name)

        if not apply:
            preview_count += 1
            print(f"[PREVIEW] {item.name} -> {destination}")
            continue

        # Calculate a hash before copying the file.
        try:
            file_hash = calculate_file_hash(item)

        except OSError as error:
            failed_count += 1
            print(f"[ERROR] Could not hash {item.name}: {error}")
            continue

        entry = {
            "original": str(item.absolute()),
            "destination": str(destination.absolute()),
            "category": category,
            "status": "pending",
            "timestamp": now(),
            "sha256": file_hash,
        }
        journal["operations"].append(entry)
        try:
            write_journal(journal, journal_path)
        except OSError as error:
            journal["operations"].pop()
            print(f"[ERROR] Cannot journal {item.name}: {error}")
            failed_count += 1
            continue

        try:
            copy_without_overwrite(item, destination, file_hash)
            entry["status"] = "completed"
            moved_count += 1
            print(f"[MOVED] {item.name} -> {destination}")
        except (OSError, shutil.Error, ValueError) as error:
            entry["status"] = "failed"
            entry["error"] = str(error)
            failed_count += 1
            print(f"[ERROR] {item.name}: {error}")

        try:
            write_journal(journal, journal_path)
        except OSError as error:
            print(f"[CRITICAL] Journal update failed: {error}")
            print(f"[CRITICAL] Inspect journal and files before retrying: {journal_path}")
            return 1

    print("\n" + "=" * 55)
    print("SCAN COMPLETE")
    print("=" * 55)
    print(f"Files found: {file_count} | Folders found: {folder_count}")
    print(f"Previewed: {preview_count} | Moved: {moved_count} | Failed: {failed_count}")
    print("\nCATEGORY BREAKDOWN")
    for category, count in sorted(category_count.items(), key=lambda x: x[1], reverse=True):
        print(f"{category}: {count}")
    if apply:
        print(f"\nJournal: {journal_path}")
    else:
        print("\nPreview only; no journal created.")
    return 1 if failed_count else 0


# ==================================================
# OPERATION HISTORY
# ==================================================

def show_history():
    available = journals()
    if not available:
        print("No DownloadJanitor history found.")
        return 0
    print("DOWNLOADJANITOR HISTORY\n" + "=" * 75)
    for path in available:
        try:
            data = read_journal(path)
            ops = data["operations"]
            completed = sum(op.get("status") == "completed" for op in ops)
            undone = sum(op.get("status") == "undone" for op in ops)
            unresolved = sum(op.get("status") in ("pending", "undo_pending") for op in ops)
            print(f"Run: {data.get('run_id', path.stem)}")
            print(f"  Date: {data.get('timestamp', 'unknown')}")
            print(f"  Folder: {data.get('directory', 'unknown')}")
            print(f"  Completed: {completed} | Undone: {undone} | Needs review: {unresolved}")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"[UNREADABLE] {path.name}: {error}")
    return 0


# ==================================================
# FILE RESTORATION / UNDO SYSTEM
# ==================================================

def undo(run_id, apply):
    try:
        path = choose_journal(run_id)
        data = read_journal(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[ERROR] {error}")
        return 1
    

    print("=" * 55)
    print(f"DOWNLOADJANITOR UNDO — {'APPLY' if apply else 'PREVIEW'}")
    print("=" * 55)
    print(f"Run: {data.get('run_id', path.stem)}")
    print(f"Journal: {path}\n")

    restored = skipped = failed = 0
    # Undo in reverse order of original moves (reversal of file transfer does not delete folders created by the program)
    for entry in reversed(data["operations"]):
        status = entry.get("status")
        if status != "completed":
            if status in ("pending", "undo_pending"):
                print(f"[REVIEW] Unresolved operation: {entry.get('original', '?')}")
            continue

        source = Path(entry["destination"])
        original = Path(entry["original"])

        if source.is_symlink() or not source.is_file():
            print(f"[SKIP] Organized file missing or not regular: {source}")
            skipped += 1
            continue
        if original.exists() or original.is_symlink():
            print(f"[SKIP] Original location occupied: {original}")
            skipped += 1
            continue
        if not original.parent.is_dir():
            print(f"[SKIP] Original parent directory missing: {original.parent}")
            skipped += 1
            continue

        
        # HASH VERIFICATION
        
        expected_hash = entry.get("sha256")                                 
                                                                            
        if not expected_hash:                                               
            print(f"[SKIP] No recorded SHA-256 hash: {source}")             
            skipped += 1                                                    
            continue                                          

        try:
            current_hash = calculate_file_hash(source)

        except OSError as error:
            print(f"[ERROR] cannot verify {source.name}: {error}")
            failed += 1
            continue

        if current_hash != expected_hash:
            print(f"[SKIP] File contents have been changed: {source}")
            skipped += 1
            continue

        if not apply:
            print(f"[PREVIEW] {source} -> {original}")
            continue

        entry["status"] = "undo_pending"
        entry["undo_started"] = now()
        try:
            write_journal(data, path)
        except OSError as error:
            entry["status"] = "completed"
            print(f"[CRITICAL] Cannot journal undo: {error}")
            return 1

        try:
            copy_without_overwrite(source, original, expected_hash)
            entry["status"] = "undone"
            entry["undone_at"] = now()
            restored += 1
            print(f"[RESTORED] {source} -> {original}")
        except (OSError, shutil.Error, ValueError) as error:
            entry["status"] = "completed" if source.is_file() and not original.exists() else "undo_pending"
            entry["undo_error"] = str(error)
            failed += 1
            print(f"[ERROR] Could not restore {source}: {error}")

        try:
            write_journal(data, path)
        except OSError as error:
            print(f"[CRITICAL] Cannot update undo journal: {error}")
            print("[CRITICAL] Stop and inspect both file locations before retrying.")
            return 1

    if not apply:
        print("\nPreview only. Add --apply (-p) to restore eligible files.")
    else:
        print(f"\nRestored: {restored} | Skipped: {skipped} | Failed: {failed}")
    return 1 if failed else 0


# ==================================================
# AUTOMATIC RECOVERY INSPECTION
# ==================================================

def inspect_pending_operation(entry):
    """Read file locations and hashes for an unresolved journal operation."""
    original = Path(entry["original"])
    destination = Path(entry["destination"])
    expected_hash = entry.get("sha256")

    result = {
        "original": str(original),
        "destination": str(destination),
        "status": entry.get("status"),
        "original_exists": original.is_file() and not original.is_symlink(),
        "destination_exists": destination.is_file() and not destination.is_symlink(),
        "original_hash_matches": None,
        "destination_hash_matches": None,
    }

    if expected_hash:
        for label, path in (("original", original), ("destination", destination)):
            if result[f"{label}_exists"]:
                try:
                    result[f"{label}_hash_matches"] = (
                        calculate_file_hash(path) == expected_hash
                    )
                except OSError:
                    # Unknown is different from a confirmed mismatch.
                    result[f"{label}_hash_matches"] = None

    return result


def check_recovery_status():
    """Inspect journals on startup; never change files or journal entries.

    Return True only when all available journals are readable and no
    operations require manual recovery review.
    """
    print("[STARTUP] Checking previous operations...")
    issues = 0

    try:
        available = journals()
    except OSError as error:
        print(f"[WARNING] Cannot list journals: {error}")
        return False

    for path in available:
        try:
            journal = read_journal(path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            issues += 1
            print(f"[WARNING] Unreadable journal {path.name}: {error}")
            continue

        for index, entry in enumerate(journal["operations"], start=1):
            if not isinstance(entry, dict):
                issues += 1
                print(f"[WARNING] Invalid operation #{index} in {path.name}")
                continue
            status = entry.get("status")
            if status not in ("pending", "undo_pending", "failed"):
                continue

            try:
                result = inspect_pending_operation(entry)
            except (KeyError, TypeError, ValueError, OSError) as error:
                issues += 1
                print(f"[REVIEW] Cannot inspect {status} operation in {path.name} (#{index}): {error}")
                continue

            # A failed copy that left its original intact and no destination
            # does not need recovery. Keep its journal entry for history.
            if (status == "failed" and result["original_exists"]
                    and not result["destination_exists"]):
                continue

            issues += 1
            print(f"[REVIEW] Unresolved {status} operation in {path.name} (#{index})")
            print(f"         Original: {result['original']}")
            print(f"           exists={result['original_exists']}, "
                  f"hash_matches={result['original_hash_matches']}")
            print(f"         Destination: {result['destination']}")
            print(f"           exists={result['destination_exists']}, "
                  f"hash_matches={result['destination_hash_matches']}")
            print("         No recovery changes were made.")

    if issues:
        print(f"[WARNING] {issues} journal issue(s) require manual review.")
        print("[NEXT] Run --history and inspect the reported original and destination paths.")
        print("[NEXT] Preserve both copies until you know which is correct.")
        print("[NEXT] After resolving the files, update the affected journal status")
        print("       only when you have confirmed the outcome. Keep a journal backup.")
        return False

    print("[OK] No unresolved operations detected.")
    return True


# ==================================================
# COMMAND-LINE ARGUMENTS
# ==================================================

def parse_arguments():
    parser = argparse.ArgumentParser(description="Organize files and safely review or undo prior runs.")
    parser.add_argument("--apply", "-p", action="store_true", help="Execute changes; default is preview")
    parser.add_argument("--directory", "-d", type=Path, default=Path.home() / "Downloads", help="Folder to organize")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--history", action="store_true", help="List previous organization runs")
    actions.add_argument("--undo", nargs="?", const="latest", metavar="RUN_ID", help="Undo newest run or a specified run ID")
    return parser.parse_args()


# ==================================================
# MAIN APP CONTROLLER
# ==================================================

def main():
    args = parse_arguments()
    recovery_clear = check_recovery_status()

    # Diagnostics are read-only. Never perform file-changing actions while
    # a journal is unresolved or unreadable to prevent any data losses; previews/history will remain available
    if args.apply and not recovery_clear:
        print("[BLOCKED] File-changing actions paused until journal issues are reviewed.")
        return 1

    if args.history:
        return show_history()
    if args.undo is not None:
        return undo(None if args.undo == "latest" else args.undo, args.apply)
    return organize(args.directory.expanduser().absolute(), args.apply)


if __name__ == "__main__":
    sys.exit(main())
