# course-clipper

[![tests](https://github.com/hadi-bachir/course-clipper/actions/workflows/tests.yml/badge.svg)](https://github.com/hadi-bachir/course-clipper/actions/workflows/tests.yml)

Copy a record, get a clean CSV row. That's it.

`saves every course record you copy to the clipboard as one row in a spreadsheet, so
bulk-collecting a few thousand university course pages is a day of clicking instead of a
week of typing.*

Built while collecting 2,500 course/fee records from a university website that only offers
a "copy" button per record. The parser is tuned for Malaysian university course-fee pages
(`Label: value` blocks, `1st year: RM 34,900`, an `Other fees` section) but is generic for
any site that copies text in that shape.

- One script, one dependency (`pyperclip`), no config
- **Beep feedback** so you never have to look at the screen
- **Append-only, restart-safe** — stop any time, resume any time, no duplicates
- **Raw text backup** (`records.md`) is the source of truth; the CSV can be regenerated
- **Nothing is silently dropped** — unparseable records go to `rejected.md` with a reason

## Quick start

```sh
python -m pip install pyperclip
python save_clips.py
```

On Windows you can also just double-click `run.bat`.

Then click the page's copy button once, wait for the beep, move to the next record.

## How it works

The script polls the clipboard every 150 ms and reacts to whatever you copied.

| Sound | Meaning |
| --- | --- |
| high beep | saved |
| low beep | duplicate, skipped (nothing to do) |
| two descending beeps | couldn't parse — text kept in `rejected.md`, see the reason there |
| three slow beeps | saved to `records.md`, but `records.csv` is locked; the row is queued and written the moment the lock goes away |

Keys while running: <kbd>Enter</kbd> re-checks the current clipboard (useful after a
reject), <kbd>q</kbd> quits. <kbd>Ctrl</kbd>+<kbd>C</kbd> works too.

> Wait for the beep before clicking the next copy button. Clipboard history only holds one
> value, so a second click before the first is read loses that record.

## Files it creates

| File | Purpose |
| --- | --- |
| `records.md` | every record exactly as copied, separated by `<!-- auto-clipper:record -->` |
| `records.csv` | one row per record, UTF-8 with BOM so Excel reads it correctly |
| `rejected.md` | records it refused to save, plus why |

Columns: `university`, `course`, `duration`, `english_requirement`, `intake`, `tuition`,
`tuition_total_rm`, `other_fees`.

`tuition` keeps the original breakdown (`1st year: RM 34,900 | 2nd year: RM 36,100`).
`tuition_total_rm` is the numeric sum, for sorting and filtering. `other_fees` holds
everything that isn't a tuition instalment, including per-semester charges
(`Semester Fee: RM 400`) and assessment fees (`Assessment Fee (Per Subject): RM 50`) which
some sites list above their `Other fees` heading.

A few rules the parser applies so the numbers stay trustworthy:

- `Total: RM 40,000` never lands in `tuition`, so totals aren't double counted.
- If a record lists both semester and year instalments, the year breakdown wins.
- `tuition_total_rm` only ever sums `tuition`, never the extra fees.

## Project layout

```
save_clips.py            the whole tool
tests/test_parse.py      parser tests, one per layout that ever broke
samples/                 example record text for --dry-run
run.bat                  double-click to run on Windows
records.md / records.csv / rejected.md   created at runtime, gitignored
```

## Other commands

```sh
python save_clips.py --dry-run FILE   # parse one text file, print the CSV row, exit
python save_clips.py --rebuild-csv    # re-parse records.md into records.csv
```

`--dry-run` is the way to check a new site layout before you collect anything:

```sh
> save a single record from the browser, save it as one.txt
python save_clips.py --dry-run one.txt
```

## If something goes wrong

This is the part that matters when you're a third of the way through 2,500 records:

- **Lost or mangled rows** — `--rebuild-csv` regenerates the whole CSV from `records.md`
  with the current parser. You never have to re-click anything.
- **Parser changed / new site layout** — same thing. Change `parse()`, run the tests, then
  `--rebuild-csv`.
- **Suspected duplicates** — dedup ignores whitespace and case, so re-copying the same
  record is skipped. `--rebuild-csv` also drops duplicates it finds in `records.md`.
- **Start-up mismatch** — if `records.csv` and `records.md` disagree on the row count, the
  script says so instead of letting you discover it at the end.
- **No undo** — `records.md` is the only copy of the raw text. Back it up when you feel
  like it.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `PermissionError` on start | `records.csv` is open in Excel. Close it, even in read-only mode Excel still locks the file. |
| Nothing happens after clicking copy | You copied something that isn't a record, or the clipboard didn't change. Press <kbd>Enter</kbd> to re-check. |
| Downward beeps | Check `rejected.md`. Usually a page that doesn't follow the usual layout. |
| Course name empty in the CSV | A header line was mistaken for the course name; add it to `NOISE_RE` in `save_clips.py` and run `--rebuild-csv`. |
| `csv has N rows but records.md has M` | Close Excel and run `--rebuild-csv`. |
| No beep at all | Beeps need `winsound`, i.e. Windows. |

## Limitations

- Windows only: `winsound` for beeps and `msvcrt` for keypresses. The parser itself is
  portable, and the script still runs elsewhere with beeps and Enter-to-retry disabled.
- One record at a time, via the clipboard. If you copy anything else mid-run (a URL,
  `Ctrl+C` of some text) it simply isn't a record and gets ignored unless it happens to
  contain `Duration`/`Intake` lines — in which case it lands in `rejected.md`.
- Fee names are kept as one text column. If you need one column per fee type, that's a
  change to `parse()` plus `--rebuild-csv`.

## Development

```sh
python -m pip install pytest
python -m pytest
```

The tests pin every layout that broke during a real collection run — blank-line spacing
variations, `Semester 1:` vs `1st year:`, course names containing a colon, flat fees,
`Total:` lines, per-semester charges, and `Human Resource` being mistaken for a header.

Validated on a 2,467-record collection across 22 universities.

## License

MIT