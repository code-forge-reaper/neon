import os

def extract_code_blocks(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    in_code_block = False
    code_lang = None
    out_file = None
    buffers = {}

    for line in lines:
        stripped = line.strip()

        # Check for the start of a code block
        if stripped.startswith('%') and stripped.endswith('%') and 'out:' in stripped:
            parts = stripped.strip('%').split()
            code_lang = parts[0]
            for part in parts:
                if part.startswith('out:'):
                    out_file = part.split(':', 1)[1]
                    break
            if out_file not in buffers:
                buffers[out_file] = []
            in_code_block = True
            continue

        # End of a code block
        if stripped == '%end%':
            in_code_block = False
            code_lang = None
            out_file = None
            continue

        # Collect code lines
        if in_code_block and out_file:
            buffers[out_file].append(line)

    # Write out the collected buffers
    for out_file, code_lines in buffers.items():
        with open(out_file, 'w') as f:
            f.writelines(code_lines)
        print(f'Wrote {len(code_lines)} lines to {out_file}')

if __name__ == '__main__':
    extract_code_blocks('tokeniser.rdb')
