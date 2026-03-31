import csv
import os
import shutil
from datetime import datetime


def normalize_amount(s: str) -> str:
    if not s:
        return ''
    s = s.strip()
    if s in ('-', '--'):
        return ''
    # remove surrounding parentheses or stray commas
    s = s.replace(',', '').replace('，', '')
    # remove '万' unit
    s = s.replace('万', '')
    return s


def read_assets_header(assets_path: str):
    with open(assets_path, 'r', encoding='utf-8') as f:
        first = f.readline().strip()
        if not first:
            return []
        # assume CSV header
        return [h.strip() for h in first.split(',')]


def parse_raw(raw_path: str):
    with open(raw_path, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f if l.strip()]

    if not lines:
        return [], None

    # check first line for date (e.g., 2026/3/30)
    potential_date = lines[0].strip()
    # basic check for YYYY/M/D or YYYY-M-D
    file_date = None
    if any(c in potential_date for c in ['/', '-']) and any(c.isdigit() for c in potential_date):
        # assume first line is a date if it looks like one
        file_date = potential_date.split()[0] # take first part in case of extra spaces
        data_lines = lines[1:]
    else:
        data_lines = lines

    rows = []
    for line in data_lines:
        # detect delimiter (tab or comma)
        if '\t' in line:
            delim = '\t'
        elif ',' in line:
            delim = ','
        else:
            delim = None
        
        if delim:
            parts = [p.strip() for p in line.split(delim)]
        else:
            parts = [p.strip() for p in line.split()]
        if not parts:
            continue
        rows.append(parts)

    if not rows:
        return [], file_date

    # detect header row among data lines
    header_idx = -1
    names = None
    for idx, parts in enumerate(rows):
        if any('市场' in c or '公司名称' in c for c in parts):
            names = [c.replace('\ufeff', '').strip() for c in parts]
            header_idx = idx
            break
    
    if header_idx == -1:
        # assume a default column order if no header present
        names = ['市场', '公司名称', '成本价', '当前价', 'pos/cost', 'pos/curr', '盈亏%', '持有数量', '投入', '当前']
        data_start = 0
    else:
        data_start = header_idx + 1

    parsed = []
    for parts in rows[data_start:]:
        if not parts:
            continue
        # skip summary rows
        if any('汇总' in p for p in parts):
            continue
        # build dict from names
        data = {names[i]: parts[i] if i < len(parts) else '' for i in range(len(names))}
        parsed.append(data)

    return parsed, file_date


def convert_and_append(raw_path: str, assets_path: str):
    # backup
    bak_path = assets_path + '.bak.' + datetime.now().strftime('%Y%m%d%H%M%S')
    shutil.copy2(assets_path, bak_path)

    header = read_assets_header(assets_path)
    if not header:
        # default header if assets file empty
        header = ['日期','市场','公司名称','成本价','当前价','pos/cost','pos/curr','盈亏%','持有数量','投入(万)','当前(万)','现金(万)','收益(万)','收益率(%)']

    parsed, file_date = parse_raw(raw_path)
    if not parsed:
        print('No data found in raw file.')
        return

    # use date from file or current date as fallback
    if file_date:
        today = file_date
    else:
        today = datetime.now().strftime('%Y/%-m/%-d') if os.name != 'nt' else datetime.now().strftime('%Y/%#m/%#d')

    # FIX: Check if file ends with newline before appending
    if os.path.exists(assets_path) and os.path.getsize(assets_path) > 0:
        with open(assets_path, 'rb+') as f:
            f.seek(-1, os.SEEK_END)
            last_char = f.read(1)
            if last_char != b'\n' and last_char != b'\r':
                f.write(b'\n')

    with open(assets_path, 'a', encoding='utf-8', newline='') as fout:
        # Add an empty line before the block to separate it from existing data
        fout.write('\n')
        writer = csv.writer(fout)
        for d in parsed:
            name = d.get('公司名称', '')
            if not name or name.startswith('汇总'):
                continue
            row = [
                today,
                d.get('市场',''),
                d.get('公司名称',''),
                normalize_amount(d.get('成本价','')),
                normalize_amount(d.get('当前价','')),
                normalize_amount(d.get('pos/cost','')),
                normalize_amount(d.get('pos/curr','')),
                d.get('盈亏%',''),
                normalize_amount(d.get('持有数量','')),
                normalize_amount(d.get('投入','')),
                normalize_amount(d.get('当前','')),
                '',
                '',
                ''
            ]
            # ensure same number of columns as header
            if len(row) < len(header):
                row += [''] * (len(header) - len(row))
            writer.writerow(row)
        # Add an empty line after the block
        fout.write('\n')

    print(f'Appended {len(parsed)} rows to {assets_path} (date: {today}, backup at {bak_path})')


if __name__ == '__main__':
    base = os.path.dirname(__file__)
    assets = os.path.join(base, 'assets.csv')
    raw = os.path.join(base, 'raw.txt')
    if not os.path.exists(assets):
        print('assets.csv not found in script directory.')
    elif not os.path.exists(raw):
        print('raw.txt not found in script directory.')
    else:
        convert_and_append(raw, assets)
