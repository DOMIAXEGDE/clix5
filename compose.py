import os
import re
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Compose code.txt files from filtered plugin folders.")
    parser.add_argument("--parent", required=True, help="Parent directory containing plugin folders")
    parser.add_argument("--cache-dir", required=True, help="Directory to write the composed output")
    parser.add_argument("--registers", nargs="+", required=True, help="List of register prefixes (e.g., r01 r02)")
    parser.add_argument("--range", nargs="+", required=True, help="Address ranges per register (e.g., r01:0010-0018)")
    parser.add_argument("--reg-base", type=int, default=10, help="Base for register parsing (default: 10)")
    parser.add_argument("--addr-base", type=int, default=10, help="Base for address parsing (default: 10)")
    parser.add_argument("--output", required=True, help="Output filename")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()

def parse_ranges(range_args, addr_base):
    ranges = {}
    for r in range_args:
        match = re.match(r"^(r\d{2}):([0-9a-fA-F]+)-([0-9a-fA-F]+)$", r)
        if not match:
            raise ValueError(f"Invalid range format: {r}")
        reg, start, end = match.groups()
        ranges[reg] = (int(start, addr_base), int(end, addr_base))
    return ranges

def is_valid_plugin(folder_name, registers, ranges, addr_base):
    match = re.match(r"^(r\d{2})a([0-9a-fA-F]+)$", folder_name)
    if not match:
        return False
    reg, addr_str = match.groups()
    if reg not in registers:
        return False
    try:
        addr = int(addr_str, addr_base)
        min_addr, max_addr = ranges.get(reg, (None, None))
        return min_addr is not None and min_addr <= addr <= max_addr
    except ValueError:
        return False

def find_code_file(folder_path):
    for root, _, files in os.walk(folder_path):
        if "code.txt" in files:
            return os.path.join(root, "code.txt")
    return None

def compose_files(parent_dir, cache_dir, registers, ranges, reg_base, addr_base, output_file, verbose=False):
    os.makedirs(cache_dir, exist_ok=True)
    output_path = os.path.join(cache_dir, output_file)
    composed = []

    for folder_name in os.listdir(parent_dir):
        folder_path = os.path.join(parent_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
        if not is_valid_plugin(folder_name, registers, ranges, addr_base):
            if verbose:
                print(f"⏭️ Skipping {folder_name}: does not match filter criteria")
            continue

        code_path = find_code_file(folder_path)
        if code_path:
            if verbose:
                print(f"✅ Including {folder_name}: {code_path}")
            with open(code_path, "r", encoding="utf-8") as f:
                composed.append(f.read())
        else:
            if verbose:
                print(f"⚠️ No code.txt found in {folder_name}")

    with open(output_path, "w", encoding="utf-8") as out:
        out.write("\n\n".join(composed))

    print(f"✅ Composed {len(composed)} files into {output_path}")

if __name__ == "__main__":
    args = parse_args()
    ranges = parse_ranges(args.range, args.addr_base)
    compose_files(
        parent_dir=args.parent,
        cache_dir=args.cache_dir,
        registers=set(args.registers),
        ranges=ranges,
        reg_base=args.reg_base,
        addr_base=args.addr_base,
        output_file=args.output,
        verbose=args.verbose
    )