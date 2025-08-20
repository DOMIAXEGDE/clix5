import os
import shutil
import argparse
import json
from datetime import datetime

def discover_code_files(parent_dir, target_filename="code.txt"):
    matched = []
    for dirpath, _, filenames in os.walk(parent_dir):
        if target_filename in filenames:
            matched.append(os.path.abspath(os.path.join(dirpath, target_filename)))
    return matched

def cache_code_lines(file_paths, cache_dir, aggregate_file):
    os.makedirs(cache_dir, exist_ok=True)
    aggregated = []
    for path in file_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                code_line = f.readline().strip()
            filename = os.path.basename(path)
            subdir = os.path.join(cache_dir, os.path.splitext(filename)[0])
            os.makedirs(subdir, exist_ok=True)
            cached_path = os.path.join(subdir, filename)
            with open(cached_path, 'w', encoding='utf-8') as f:
                f.write(code_line + '\n')
            aggregated.append(code_line)
        except Exception as e:
            print(f"[!] Error caching {path}: {e}")
    with open(aggregate_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(aggregated))
    print(f"[✓] Cached {len(aggregated)} files to {aggregate_file}")

def commit_cached_files(cache_dir, commit_dir, new_ext):
    os.makedirs(commit_dir, exist_ok=True)
    for root, _, files in os.walk(cache_dir):
        for file in files:
            src = os.path.join(root, file)
            try:
                with open(src, 'r', encoding='utf-8') as f:
                    code_line = f.readline().strip()
                base = os.path.splitext(file)[0]
                dest = os.path.join(commit_dir, base + new_ext)
                with open(dest, 'w', encoding='utf-8') as f:
                    f.write(code_line + '\n')
                print(f"[✓] Committed: {dest}")
            except Exception as e:
                print(f"[!] Failed to commit {src}: {e}")

def clear_cache(cache_dir):
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir)
        print(f"[✓] Cleared cache: {cache_dir}")
    else:
        print(f"[!] Cache directory not found: {cache_dir}")

def parse_aggregate(aggregate_file, rules_file, output_file=None):
    if not os.path.isfile(aggregate_file):
        print(f"[!] Aggregate file not found: {aggregate_file}")
        return
    if not os.path.isfile(rules_file):
        print(f"[!] Rules file not found: {rules_file}")
        return

    with open(rules_file, 'r', encoding='utf-8') as f:
        try:
            rules = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[!] Failed to parse rules JSON: {e}")
            return

    # Add dynamic tokens
    rules.setdefault("{{DATE}}", datetime.now().strftime("%Y-%m-%d"))
    rules.setdefault("{{TIME}}", datetime.now().strftime("%H:%M:%S"))

    with open(aggregate_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    parsed_lines = []
    for line in lines:
        for key, val in rules.items():
            line = line.replace(key, val)
        parsed_lines.append(line)

    output_path = output_file or aggregate_file.replace('.txt', '_parsed.txt')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(parsed_lines)

    print(f"[✓] Parsed aggregate written to: {output_path}")

def interactive_menu():
    print("\n🧠 Welcome to Compose.py — One Script to Rule Them All")
    while True:
        print("\nChoose an option:")
        print("1. Discover and cache code.txt files")
        print("2. Commit cached files with new extension")
        print("3. Parse aggregate.txt with rules")
        print("4. Clear cache")
        print("5. Exit")
        choice = input("Enter choice [1-5]: ").strip()
        if choice == '1':
            parent = input("Enter parent directory to scan: ").strip()
            cache_dir = input("Enter cache directory: ").strip()
            aggregate_file = os.path.join(cache_dir, 'aggregate.txt')
            files = discover_code_files(parent)
            if not files:
                print("[!] No code.txt files found.")
                continue
            cache_code_lines(files, cache_dir, aggregate_file)
        elif choice == '2':
            cache_dir = input("Enter cache directory: ").strip()
            new_ext = input("Enter new file extension (e.g., .py): ").strip()
            commit_dir = os.path.join(os.path.dirname(__file__), 'commit')
            commit_cached_files(cache_dir, commit_dir, new_ext)
        elif choice == '3':
            cache_dir = input("Enter cache directory: ").strip()
            rules_file = input("Enter path to rules JSON file: ").strip()
            aggregate_file = os.path.join(cache_dir, 'aggregate.txt')
            parse_aggregate(aggregate_file, rules_file)
        elif choice == '4':
            cache_dir = input("Enter cache directory to clear: ").strip()
            clear_cache(cache_dir)
        elif choice == '5':
            print("Goodbye 👋")
            break
        else:
            print("[!] Invalid choice. Try again.")

def main():
    parser = argparse.ArgumentParser(description="Unified script for discovery, caching, committing, and parsing code snippets.")
    parser.add_argument('--parent', help='Parent directory to scan for code.txt files')
    parser.add_argument('--cache-dir', help='Directory to store cached files')
    parser.add_argument('--commit', action='store_true', help='Commit cached files')
    parser.add_argument('--new-ext', help='New file extension for committed files')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cache directory')
    parser.add_argument('--parse', action='store_true', help='Parse aggregate.txt using replacement rules')
    parser.add_argument('--rules', help='Path to JSON file with replacement rules')
    parser.add_argument('--output', help='Optional output file for parsed aggregate')
    args = parser.parse_args()

    if args.clear_cache and args.cache_dir:
        clear_cache(args.cache_dir)
    elif args.commit and args.cache_dir and args.new_ext:
        commit_dir = os.path.join(os.path.dirname(__file__), 'commit')
        commit_cached_files(args.cache_dir, commit_dir, args.new_ext)
    elif args.parse and args.rules and args.cache_dir:
        aggregate_file = os.path.join(args.cache_dir, 'aggregate.txt')
        parse_aggregate(aggregate_file, args.rules, args.output)
    elif args.parent and args.cache_dir:
        aggregate_file = os.path.join(args.cache_dir, 'aggregate.txt')
        files = discover_code_files(args.parent)
        if files:
            cache_code_lines(files, args.cache_dir, aggregate_file)
        else:
            print(f"[!] No code.txt files found under {args.parent}")
    else:
        interactive_menu()

if __name__ == '__main__':
    main()