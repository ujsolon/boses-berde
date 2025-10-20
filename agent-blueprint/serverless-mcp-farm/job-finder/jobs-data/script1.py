Source URL: https://www.example-site.com/script1.py
import os

# Full path to your data folder
directory = "/home/yujey02/boses-berde/agent-blueprint/serverless-mcp-farm/job-finder/jobs-data"

# Confirm directory exists
if not os.path.exists(directory):
    print(f"❌ Directory not found: {directory}")
    exit(1)

print(f"📁 Checking files in: {directory}\n")

for filename in os.listdir(directory):
    filepath = os.path.join(directory, filename)

    # Skip folders
    if not os.path.isfile(filepath):
        continue

    print(f"🔹 Processing: {filename}")

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            content = file.read()

        source_line = f"Source URL: https://www.example-site.com/{filename}\n"

        # Avoid duplicate header
        if content.startswith(source_line):
            print("   ↪ Already has source line, skipping.")
            continue

        with open(filepath, "w", encoding="utf-8") as file:
            file.write(source_line + content)

        print("   ✅ Line added successfully.")

    except Exception as e:
        print(f"   ⚠️ Error updating {filename}: {e}")

print("\n🎉 Done processing files.")
