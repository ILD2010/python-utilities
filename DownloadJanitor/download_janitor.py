from pathlib import Path
import shutil


# ==================================================
# CONFIGURATION
# ==================================================

# True = Preview changes
# False = Actually move files
DRY_RUN = False

# Directory to organize
downloads_folder = Path.home() / "Downloads"


# ==================================================
# FILE CATEGORIES
# ==================================================

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
    "Data": [".csv", ".json", ".xml", ".sql", ".db", ".pcap", ".sqlite"]
}


# ==================================================
# CATEGORY IDENTIFICATION
# ==================================================

def get_category(file):
    """Determine a file's category based on its extension."""

    extension = file.suffix.lower()

    for category, extensions in FILE_TYPES.items():

        if extension in extensions:
            return category

    return "Other"


# ==================================================
# DESTINATION PLANNING
# ==================================================

def get_destination(file, category):
    """Determine which folder a file belongs in."""

    destination_folder = file.parent / category

    return destination_folder


# ==================================================
# DUPLICATE FILE PROTECTION
# ==================================================

def get_unique_path(destination):
    """Generate a unique filename if the destination exists."""

    if not destination.exists():
        return destination

    counter = 1

    while True:

        new_name = f"{destination.stem}_{counter}{destination.suffix}"

        new_path = destination.with_name(new_name)

        if not new_path.exists():
            return new_path

        counter += 1


# ==================================================
# FILE MOVEMENT
# ==================================================

def move_file(file, destination_folder):
    """Preview or move a file into its category folder."""

    destination = destination_folder / file.name

    destination = get_unique_path(destination)

    if DRY_RUN:

        print(f"[PREVIEW] {file.name}")
        print(f"          Destination: {destination}\n")

        return "preview"

    try:

        # Create the destination folder when required
        destination_folder.mkdir(parents=True, exist_ok=True)

        # Move the file
        shutil.move(str(file), str(destination))

        print(f"[MOVED] {file.name}")
        print(f"        Destination: {destination}\n")

        return "moved"

    except OSError as error:

        print(f"[ERROR] Failed to move {file.name}: {error}\n")

        return "failed"


# ==================================================
# DIRECTORY VALIDATION
# ==================================================

if not downloads_folder.is_dir():

    print("ERROR: Downloads directory does not exist.")
    raise SystemExit(1)


# ==================================================
# PROGRAM HEADER INFO
# ==================================================

print("=" * 50)
print("DOWNLOADJANITOR v0.3")
print("=" * 50)

print(f"Scanning: {downloads_folder}")
print(f"Mode: {'PREVIEW' if DRY_RUN else 'APPLY'}")
print()


# COUNTERS

file_count = 0
folder_count = 0

moved_count = 0
preview_count = 0
failed_count = 0

category_count = {}


# ==================================================
# FILE SCANNING AND ORGANIZATION
# ==================================================

for item in sorted(downloads_folder.iterdir()):

    if item.is_file():

        file_count += 1

        # Determine file category
        category = get_category(item)

        # Update category statistics
        category_count[category] = category_count.get(category, 0) + 1

        # Determine destination
        destination_folder = get_destination(item, category)

        # move the file
        result = move_file(item, destination_folder)

        # Track operations
        if result == "moved":
            moved_count += 1

        elif result == "preview":
            preview_count += 1

        elif result == "failed":
            failed_count += 1

    elif item.is_dir():

        folder_count += 1

        print(f"[FOLDER] {item.name}\n")


# ==================================================
# SUMMARY
# ==================================================

print()
print("=" * 50)
print("SCAN COMPLETE")
print("=" * 50)

print(f"File(s) found: {file_count}")
print(f"Folder(s) found: {folder_count}")

print(f"File(s) previewed: {preview_count}")
print(f"File(s) moved: {moved_count}")
print(f"Failed operations: {failed_count}")

print()
print("CATEGORY BREAKDOWN")
print("-" * 30)

for category, count in sorted(
    category_count.items(),
    key=lambda item: item[1],
    reverse=True
):
    print(f"{category}: {count}")


# ==================================================
# VERIFICATION
# ==================================================

print()
print("VERIFICATION")
print("-" * 30)

total_categorized = sum(category_count.values())

total_processed = moved_count + preview_count + failed_count

if total_categorized == file_count:
    print("[PASS] All discovered files categorized.")
else:
    print("[FAIL] Category totals do not match file count.")

if total_processed == file_count:
    print("[PASS] All discovered files processed.")
else:
    print("[FAIL] Processing totals do not match file count.")


print()
print("=" * 50)
print("DOWNLOADJANITOR FINISHED")
print("=" * 50)