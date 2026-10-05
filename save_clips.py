"""Watches the clipboard and saves every course record you copy.

Run:  python save_clips.py
Copy:  click the site's "copy" button once, wait for the beep, move on.
Keys: Enter = re-check the clipboard (use after a down-beep), q = quit

High beep  = saved
Low beep   = duplicate, skipped
Down-beep  = could not parse, kept in rejected.md so nothing is lost
Slow beeps = saved to records.md, but records.csv is locked (Excel open).
            The row is queued and written the moment Excel closes it.

Other commands:
  python save_clips.py --dry-run FILE   parse one text file, print the CSV row
  python save_clips.py --rebuild-csv    re-parse records.md into records.csv
"""

import argparse
import csv
import os
import re
import sys
import time

try:
    import winsound
except ImportError:
    winsound = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

MD = "records.md"
CSV_FILE = "records.csv"
REJ = "rejected.md"
SEP = "<!-- auto-clipper:record -->"
SEP_RE = re.compile(r"^<!--\s*auto-clipper:record\s*-->$", re.M)
POLL = 0.15

COLUMNS = ["university", "course", "duration", "english_requirement",
           "intake", "tuition", "tuition_total_rm", "other_fees"]

LABEL_RE = re.compile(r"^([^:]{1,60}?)\s*:\s*(.+)$")
PERIOD_RE = re.compile(r"^(?:\d+\s*(?:st|nd|rd|th)\s*)?(?:year|semester|term)\b", re.I)
SEM_RE = re.compile(r"semester|term", re.I)
TOTAL_RE = re.compile(r"^(?:total|grand|overall|programme total|course total)", re.I)
AMOUNT_RE = re.compile(r"(?:RM|MYR|USD|SGD)\s*([\d,]+(?:\.\d+)?)", re.I)
BARE_RE = re.compile(r"^[\s]*([\d,]+(?:\.\d+)?)[\s]*$")
KNOWN_LABEL_RE = re.compile(r"duration|english|intake|requirement|year|semester|term|fee|tuition|"
                            r"cost|price|programme|program", re.I)
FEEWORD_RE = re.compile(r"fee|tuition|price|programme|course|cost|rate", re.I)
SKIP_FEE_RE = re.compile(r"\bnote\b|\btax\b|\bsst\b|\bexclud\w*|\binclud\w*|\bremark\w*|"
                         r"\bimportant\b|\bsubject\b|\btotal\b", re.I)
FEE_HEADER_RE = re.compile(r"other fee|additional fee|other cost|non-academic|student service", re.I)
NOISE_RE = re.compile(r"\bfees?\b|\btuition\b|\bsst\b|\btax\b|\bexclud\w*|\byearly\b|"
                      r"\bsemester\w*|\bper\s|\bnotes?\b|\bimportant\b|\bsubject\b|\bupdat\w*|"
                      r"\bwebsite\b|\bbased on\b|^\*|\bstudent\b", re.I)
MONEY_RE = re.compile(r"RM|MYR|\d")


def beep(freq, dur):
    if winsound is None:
        return
    try:
        winsound.Beep(freq, dur)
    except Exception:
        pass


def beep_bad():
    for f in (900, 600):
        beep(f, 120)
        time.sleep(0.06)


def beep_locked():
    for f in (500, 500, 350):
        beep(f, 180)
        time.sleep(0.08)


def amount(text):
    m = AMOUNT_RE.search(text)
    if not m:
        m = BARE_RE.match(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse(text):
    rec = {c: "" for c in COLUMNS}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    plain, tuition, fees = [], [], []
    in_fees = False
    pairs = 0

    for line in lines:
        m = LABEL_RE.match(line)
        if not m:
            if FEE_HEADER_RE.search(line):
                in_fees = True
            else:
                plain.append(line)
            continue
        label, value = m.group(1).strip(), m.group(2).strip()
        low = label.lower()
        pairs += 1
        if "duration" in low:
            rec["duration"] = value
        elif "english" in low:
            rec["english_requirement"] = value
        elif "intake" in low:
            rec["intake"] = value
        elif PERIOD_RE.match(label) and FEEWORD_RE.search(low) and "year" not in low:
            fees.append((label, value))
        elif PERIOD_RE.match(label) and amount(value) is not None and not TOTAL_RE.match(label):
            tuition.append((label, value))
        elif in_fees and not SKIP_FEE_RE.search(low):
            fees.append((label, value))
        elif FEEWORD_RE.search(low) and amount(value) is not None:
            tuition.append((label, value))

    if len(tuition) > 1:
        years = [t for t in tuition if "year" in t[0].lower() and not SEM_RE.search(t[0])]
        if years:
            spill = [t for t in tuition if t not in years and FEEWORD_RE.search(t[0])]
            tuition = years
            fees.extend(spill)

    rec["university"] = lines[0] if lines else ""
    course = next((p for p in plain[1:] if not NOISE_RE.search(p)), "")
    if not course and len(lines) > 1 and not KNOWN_LABEL_RE.search(lines[1]) \
            and not NOISE_RE.search(lines[1]):
        course = lines[1]
    rec["course"] = course
    rec["tuition"] = " | ".join("%s: %s" % p for p in tuition)
    rec["other_fees"] = " | ".join("%s: %s" % p for p in fees)
    nums = [n for n in (amount(v) for _, v in tuition) if n is not None]
    rec["tuition_total_rm"] = ("%.2f" % sum(nums)) if nums else ""

    problems = []
    if not rec["university"]:
        problems.append("no university line")
    if len(course) < 4:
        problems.append("no course line")
    if pairs < 2:
        problems.append("only %d label:value lines" % pairs)
    if not (rec["duration"] or rec["intake"] or rec["tuition"]):
        problems.append("no duration/intake/tuition")
    if rec["tuition"] and MONEY_RE.search(rec["tuition"]) is None:
        problems.append("tuition has no amount")
    return rec, problems


def status(msg):
    sys.stdout.write("\r" + msg.ljust(60))
    sys.stdout.flush()


def dedup_key(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def open_csv():
    try:
        return open(CSV_FILE, "a", encoding="utf-8", newline="")
    except OSError:
        return None


def write_header():
    try:
        with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(COLUMNS)
        return True
    except OSError:
        return False


def load(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [p.strip() for p in SEP_RE.split(f.read()) if p.strip()]
    except OSError:
        return []


def csv_rows():
    try:
        with open(CSV_FILE, encoding="utf-8-sig", errors="replace") as f:
            return max(0, sum(1 for _ in f) - 1)
    except OSError:
        return -1


def print_row(rec, problems):
    w = csv.writer(sys.stdout)
    w.writerow(COLUMNS)
    w.writerow([rec[c] for c in COLUMNS])
    for p in problems:
        w.writerow(["PROBLEM: " + p])


def dry_run(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        rec, problems = parse(f.read())
    print_row(rec, problems)
    return 0


def rebuild():
    if not os.path.exists(MD) and not os.path.exists(CSV_FILE):
        print("no %s or %s in this folder." % (MD, CSV_FILE))
        print("Run this from the folder where you have been collecting - "
              "or just use run.bat, which always does.")
        return 1
    records = load(MD)
    if not records and os.path.exists(MD) and os.path.getsize(MD) > 0:
        print("%s exists but could not be read. Nothing written." % MD)
        print("Close whatever has it open (Excel, a sync client) and run this from the same "
              "folder as the script.")
        return 1
    have = csv_rows()
    if records and 0 <= have < len(records):
        print("%s holds %d records but %s already has %d rows." % (MD, len(records), CSV_FILE, have))
        print("That looks like a partial read. Refusing to rebuild - check records.md first.")
        return 1
    if not write_header():
        print("cannot write %s - close Excel and try again" % CSV_FILE)
        return 1
    bad = 0
    seen = set()
    with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for i, raw in enumerate(sorted(records), 1):
            key = dedup_key(raw)
            if key in seen:
                status("rebuilding %d/%d (skipped %d duplicates)" % (i, len(records), bad))
                continue
            seen.add(key)
            rec, problems = parse(raw)
            w.writerow([rec[c] for c in COLUMNS])
            bad += 1 if problems else 0
            status("rebuilding %d/%d" % (i, len(records)))
    print("\nrewrote %d unique rows from %s (%d duplicates dropped), %d need attention"
          % (len(seen), MD, len(records) - len(seen), bad))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", metavar="FILE", help="parse one text file and print the CSV row")
    ap.add_argument("--rebuild-csv", action="store_true", help="re-parse records.md into records.csv")
    args = ap.parse_args()
    if args.dry_run:
        return dry_run(args.dry_run)
    if args.rebuild_csv:
        return rebuild()

    import pyperclip

    stored = load(MD)
    if not stored and os.path.exists(MD) and os.path.getsize(MD) > 0:
        print("WARNING: %s exists but could not be read. Duplicate detection is starting empty." % MD)
    known = set(dedup_key(r) for r in stored)
    rejected = set(dedup_key(r) for r in load(REJ))
    if not os.path.exists(CSV_FILE) and not write_header():
        print("cannot create %s - close it in Excel, then start again" % CSV_FILE)
        return 1
    cf = open_csv()
    count, dups = len(stored), 0
    pending = []
    rows = csv_rows()
    status("%d records loaded, csv has %d rows. Waiting for copies..." % (count, rows))
    if cf is None:
        status("! records.csv is locked (Excel?) - rows will queue until it closes")
    elif rows != count:
        status("! csv has %d rows but %s has %d - close Excel, run --rebuild-csv" % (rows, MD, count))
    print()

    md = open(MD, "a", encoding="utf-8")
    rf = open(REJ, "a", encoding="utf-8")
    try:
        last = ""
        while True:
            if msvcrt is not None and msvcrt.kbhit():
                key = msvcrt.getwch().lower()
                if key == "q":
                    break
                if key in ("\r", "\n"):
                    last = ""
                    status("re-checking clipboard...")

            if pending:
                if cf is None:
                    cf = open_csv()
                if cf is not None:
                    try:
                        w = csv.writer(cf)
                        for row in pending:
                            w.writerow(row)
                        cf.flush()
                        status("records.csv unlocked, wrote %d queued rows" % len(pending))
                        beep(1400, 70)
                        pending = []
                    except OSError:
                        cf = None

            try:
                text = pyperclip.paste().strip()
            except Exception:
                text = ""
            if text and text != last and ("ntake" in text or "uration" in text):
                last = text
                key = dedup_key(text)
                if key in known:
                    dups += 1
                    beep(400, 200)
                    status("%d saved | duplicate skipped | %d dups" % (count, dups))
                    continue
                rec, problems = parse(text)
                if problems:
                    if key not in rejected:
                        rejected.add(key)
                        rf.write("\n%s\n%s\n%s\n" % (SEP, text, "PROBLEMS: " + "; ".join(problems)))
                        rf.flush()
                    beep_bad()
                    status("%d saved | REJECTED: %s" % (count, problems[0]))
                    continue
                known.add(key)
                count += 1
                md.write(text + "\n\n" + SEP + "\n\n")
                md.flush()
                row = [rec[c] for c in COLUMNS]
                if cf is None:
                    cf = open_csv()
                queued = False
                if cf is not None:
                    try:
                        csv.writer(cf).writerow(row)
                        cf.flush()
                    except OSError:
                        cf = None
                        queued = True
                else:
                    queued = True
                if queued:
                    pending.append(row)
                    beep_locked()
                    status("%d saved to %s | csv locked, %d queued" % (count, MD, len(pending)))
                else:
                    beep(1400, 70)
                    status("%d saved | %s" % (count, rec["university"][:30]))
            time.sleep(POLL)
    finally:
        if cf is not None:
            cf.close()
        md.close()
        rf.close()
    if pending:
        print("\n%d rows were queued but never written. Close Excel and run: python save_clips.py --rebuild-csv"
              % len(pending))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped")