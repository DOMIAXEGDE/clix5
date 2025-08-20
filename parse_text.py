import argparse
import json
import os

"""
python parse_text.py --input D:\cache\composed.txt --parser parser.json --output-dir D:\parsed
"""

def load_parser_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def apply_transformations(text, config):
    rules = config.get("transform", {})
    
    if rules.get("strip_whitespace", False):
        text = "\n".join(line.strip() for line in text.splitlines())

    if rules.get("uppercase", False):
        text = text.upper()

    replacements = rules.get("replace", {})
    for old, new in replacements.items():
        text = text.replace(old, new)

    return text

def main():
    parser = argparse.ArgumentParser(description="Parse and transform text using parser.json rules.")
    parser.add_argument('--input', required=True, help="Path to input text file")
    parser.add_argument('--parser', required=True, help="Path to parser.json")
    parser.add_argument('--output-dir', required=True, help="Directory to save parsed output")

    args = parser.parse_args()
    config = load_parser_config(args.parser)

    with open(args.input, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    parsed_text = apply_transformations(raw_text, config)

    output_name = config.get("output_name", "output")
    output_ext = config.get("output_extension", ".txt")
    output_path = os.path.join(args.output_dir, output_name + output_ext)

    with open(output_path, 'w', encoding='utf-8') as out:
        out.write(parsed_text)

    print(f"✅ Parsed output saved to {output_path}")

if __name__ == "__main__":
    main()