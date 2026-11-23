"""
Placement Eligibility Checker
-----------------------------
Reads jobs.csv and students.csv, asks an LLM for each post's criteria
(the LLM sees ONLY the post), checks the reply in Python, matches students,
and writes four draft output files for the placement officer to review.
"""

import csv
import json
import os
import re
import sys

# ---------- Settings ----------
JOBS_FILE = "jobs.csv"
STUDENTS_FILE = "students.csv"
PROMPT_FILE = "system_prompt.txt"
OUTPUT_DIR = "output"

ALLOWED_BRANCHES = ["CSE", "IT", "AIDS", "ECE", "EEE", "MECH", "CIVIL"]
FIELDS = ["branches", "min_cgpa", "max_backlogs", "batch", "summary"]

# How each branch can be written in a post (used by the fact check)
BRANCH_PATTERNS = {
    "CSE": r"\bcse\b|computer science",
    "AIDS": r"\bai\s*&\s*ds\b|\bai\s*(and)?\s*ds\b|\baids\b|ai\s*(&|and)\s*data science|artificial intelligence",
    "ECE": r"\bece\b|electronics and communication",
    "EEE": r"\beee\b|electrical",
    "MECH": r"\bmech\b|mechanical",
    "CIVIL": r"\bcivil\b",
}
# "IT" is checked separately and case-sensitively, because "it" is also a normal word.
IT_PATTERN = r"\bIT\b|information technology"


# ---------- 1. Load functions ----------
def load_jobs(path):
    """Read jobs.csv into a list of dictionaries."""
    jobs = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                jobs.append({"id": row["id"].strip(),
                             "company": row["company"].strip(),
                             "post": row["post"].strip()})
    except FileNotFoundError:
        print(f"ERROR: {path} not found.")
    return jobs


def load_students(path):
    """Read students.csv. CGPA is converted with float(), never kept as text."""
    students = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    students.append({
                        "roll": row["roll"].strip(),
                        "name": row["name"].strip(),
                        "branch": row["branch"].strip().upper(),
                        "cgpa": float(row["cgpa"]),
                        "backlogs": int(row["backlogs"]),
                        "batch": int(row["batch"]),
                    })
                except (ValueError, KeyError):
                    print(f"WARNING: skipped bad student row: {row}")
    except FileNotFoundError:
        print(f"ERROR: {path} not found.")
    return students


# ---------- 2. LLM call ----------
def load_system_prompt(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def mock_llm_extract(post):
    """Simulate the LLM's response following the 5-role prompt strictly.
    Used when --mock is passed or in test harnesses / offline demo mode."""
    # 1. Branches
    if re.search(r"any branch|all branches|all branch|any department|all departments",
                 post, flags=re.IGNORECASE):
        branches = ["ALL"]
    else:
        branches = []
        for b in ALLOWED_BRANCHES:
            if b == "IT":
                if re.search(IT_PATTERN, post):
                    branches.append("IT")
            else:
                if re.search(BRANCH_PATTERNS[b], post, flags=re.IGNORECASE):
                    branches.append(b)

    # 2. CGPA (only if written, never convert percentage or vague cut-offs)
    min_cgpa = None
    perc_match = re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b", post, flags=re.IGNORECASE)
    vague_match = re.search(r"top\s+\d+\s*percent|top\s+decile|good\s+academics|first\s+class", post, flags=re.IGNORECASE)
    
    if not perc_match and not vague_match:
        # Match CGPA patterns like "CGPA 7.5", "7.5 CGPA", "CGPA 7 and above", "8.0 CGPA and above"
        cgpa_match = re.search(r"(?:cgpa\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?))|(?:(\d+(?:\.\d+)?)\s*cgpa)",
                               post, flags=re.IGNORECASE)
        if cgpa_match:
            val_str = cgpa_match.group(1) or cgpa_match.group(2)
            min_cgpa = float(val_str)
        else:
            m_gen = re.search(r"(?:minimum|cut-off|cutoff|at least)\s+(\d+(?:\.\d+)?)", post, flags=re.IGNORECASE)
            if m_gen:
                min_cgpa = float(m_gen.group(1))

    # 3. Backlogs
    max_backlogs = None
    if re.search(r"no\s+(?:active\s+|standing\s+)?(?:backlogs?|arrears?)", post, flags=re.IGNORECASE):
        max_backlogs = 0
    else:
        m_back = re.search(r"(?:up to|maximum|max|backlogs up to)\s*(\d+)\s*(?:standing\s+|active\s+)?(?:backlogs?|arrears?)",
                           post, flags=re.IGNORECASE) or \
                 re.search(r"(?:backlogs?|arrears?)\s*(?:up to|max(?:imum)?)\s*(\d+)",
                           post, flags=re.IGNORECASE)
        if m_back:
            max_backlogs = int(m_back.group(1))

    # 4. Batch
    batch = None
    m_batch = re.search(r"\b(20\d\d)\b", post)
    if m_batch:
        batch = int(m_batch.group(1))

    # 5. Summary
    parts = []
    if branches == ["ALL"]:
        parts.append("All branches")
    elif branches:
        parts.append(", ".join(branches))
    else:
        parts.append("No branch named")
    if batch:
        parts.append(str(batch))
    if min_cgpa is not None:
        parts.append(f"CGPA {min_cgpa}+")
    elif perc_match:
        parts.append("percentage cut-off only")
    elif vague_match:
        parts.append("vague cut-off")
    if max_backlogs is not None:
        parts.append("no backlogs" if max_backlogs == 0 else f"max {max_backlogs} backlogs")

    summary = ", ".join(parts)
    words = summary.split()
    if len(words) > 12:
        summary = " ".join(words[:12])

    return json.dumps({
        "branches": branches,
        "min_cgpa": min_cgpa,
        "max_backlogs": max_backlogs,
        "batch": batch,
        "summary": summary
    })


def call_llm(system_prompt, post):
    """Send ONE post to the LLM and return its raw text reply.
    The API key is read from the environment (.env file), never written in code.
    If --mock or MOCK_LLM=1 is set, simulates the extraction."""
    if "--mock" in sys.argv or os.environ.get("MOCK_LLM") == "1":
        return mock_llm_extract(post)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key and anthropic_key != "your-key-here":
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        response = client.messages.create(
            model=os.environ.get("LLM_MODEL", "claude-3-5-haiku-20241022"),
            max_tokens=300,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": f"<post>{post}</post>"}]
        )
        return response.content[0].text or ""

    # Gemini support – uses GOOGLE_GENERATIVEAI SDK
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key and gemini_key != "your-key-here":
        try:
            import google.generativeai as genai
        except ImportError:
            # If the SDK is not installed, raise to trigger fallback
            raise
        genai.configure(api_key=gemini_key)
        model_name = os.environ.get("LLM_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)
        # Provide system prompt and user post
        response = model.generate_content([system_prompt, f"<post>{post}</post>"])
        return response.text or ""

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key and openrouter_key != "your-key-here":
        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
        )
        response = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "openrouter/free"),
            max_tokens=300,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"<post>{post}</post>"},
            ],
        )
        return response.choices[0].message.content or ""

    raise RuntimeError("No valid API key found. Set OPENROUTER_API_KEY or ANTHROPIC_API_KEY in .env, or run with --mock")


def parse_json(text):
    """Turn the LLM's text into a dictionary. Returns None if it is not JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    # If the model added words around the JSON, keep only the part from { to }
    if "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Some models add extra words around the JSON. Try the part between { and }.
        first, last = text.find("{"), text.rfind("}")
        if first == -1 or last <= first:
            return None
        try:
            data = json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


# ---------- 3. Validation ----------
def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def is_valid(d):
    """Check the shape and allowed values of the LLM's reply."""
    if not isinstance(d, dict) or any(k not in d for k in FIELDS):
        return False

    b = d["branches"]
    if not isinstance(b, list) or not all(isinstance(x, str) for x in b):
        return False
    if b == ["ALL"]:
        pass
    elif "ALL" in b or any(x not in ALLOWED_BRANCHES for x in b):
        return False

    if d["min_cgpa"] is not None and not (is_number(d["min_cgpa"]) and 0 <= d["min_cgpa"] <= 10):
        return False
    if d["max_backlogs"] is not None and not (isinstance(d["max_backlogs"], int)
                                              and not isinstance(d["max_backlogs"], bool)
                                              and d["max_backlogs"] >= 0):
        return False
    if d["batch"] is not None and not (isinstance(d["batch"], int)
                                       and not isinstance(d["batch"], bool)
                                       and 2000 <= d["batch"] <= 2100):
        return False
    if not isinstance(d["summary"], str) or len(d["summary"].split()) > 12:
        return False
    return True


def read_criteria(system_prompt, post):
    """Ask the LLM, validate the reply, retry once. Returns a clean dict or None."""
    for attempt in (1, 2):
        try:
            reply = call_llm(system_prompt, post)
        except Exception as e:  # network error, bad key, rate limit...
            print(f"   LLM call failed (attempt {attempt}): {e}")
            continue
        data = parse_json(reply)
        if is_valid(data):
            return {k: data[k] for k in FIELDS}  # copy ONLY the five fields
        print(f"   Invalid reply (attempt {attempt}), retrying..." if attempt == 1
              else "   Invalid reply again, falling back.")
    return None  # fallback: caller marks the post needs_review


# ---------- 4. Fact check (Python does not trust the LLM) ----------
def number_in_post(value, post):
    """True if this number is written in the post and is not a percentage."""
    candidates = {f"{value:g}", f"{value:.1f}", f"{value:.2f}"}
    for c in candidates:
        pattern = r"(?<![\d.])" + re.escape(c) + r"(?!\d|\.\d)(\s*(%|percent|per cent))?"
        for m in re.finditer(pattern, post, flags=re.IGNORECASE):
            if not m.group(2):  # followed by % or "percent" -> not a CGPA
                return True
    return False


def check_facts(post, criteria):
    """Remove anything the post does not actually say.
    Returns (cleaned_criteria, list_of_notes)."""
    c = dict(criteria)
    notes = []

    # Branches
    if c["branches"] == ["ALL"]:
        if not re.search(r"any branch|all branches|all branch|any department|all departments",
                         post, flags=re.IGNORECASE):
            c["branches"] = []
            notes.append("LLM said ALL branches but post does not say so")
    else:
        kept = []
        for b in c["branches"]:
            if b == "IT":
                found = re.search(IT_PATTERN, post)
            else:
                found = re.search(BRANCH_PATTERNS[b], post, flags=re.IGNORECASE)
            if found:
                kept.append(b)
            else:
                notes.append(f"branch {b} not named in post (removed)")
        c["branches"] = kept

    # CGPA
    if c["min_cgpa"] is not None:
        c["min_cgpa"] = float(c["min_cgpa"])
        if not number_in_post(c["min_cgpa"], post):
            notes.append(f"CGPA {c['min_cgpa']} not written in post (removed)")
            c["min_cgpa"] = None

    # Batch
    if c["batch"] is not None and str(c["batch"]) not in post:
        notes.append(f"batch {c['batch']} not written in post (removed)")
        c["batch"] = None

    # Backlogs (my extra safety check): post must mention backlog/arrear at all
    if c["max_backlogs"] is not None and not re.search(r"backlog|arrear", post, flags=re.IGNORECASE):
        notes.append("backlog limit given but post never mentions backlogs (removed)")
        c["max_backlogs"] = None

    return c, notes


# ---------- 5. Job status ----------
def job_status(criteria):
    """needs_review if no branches or no CGPA after the fact check."""
    reasons = []
    if not criteria["branches"]:
        reasons.append("no branch named in post")
    if criteria["min_cgpa"] is None:
        reasons.append("no CGPA cut-off written in post (percentage or vague cut-off?)")
    return ("needs_review", reasons) if reasons else ("matched", [])


# ---------- 6. Eligibility ----------
def is_eligible(student, criteria):
    """branch in list (or ALL), cgpa >= cut-off, backlogs <= limit, batch matches."""
    if criteria["branches"] != ["ALL"] and student["branch"] not in criteria["branches"]:
        return False
    if student["cgpa"] < criteria["min_cgpa"]:
        return False
    if criteria["max_backlogs"] is not None and student["backlogs"] > criteria["max_backlogs"]:
        return False
    if criteria["batch"] is not None and student["batch"] != criteria["batch"]:
        return False
    return True


# ---------- 7. Output files ----------
def write_reports(results, students, outdir):
    os.makedirs(outdir, exist_ok=True)

    # job_summary.csv
    with open(os.path.join(outdir, "job_summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "company", "status", "branches", "min_cgpa", "max_backlogs",
                    "batch", "summary", "eligible_count"])
        for r in results:
            c = r["criteria"]
            if c is None:
                w.writerow([r["id"], r["company"], r["status"], "", "", "", "", "", "n/a"])
            else:
                w.writerow([r["id"], r["company"], r["status"], "|".join(c["branches"]),
                            "" if c["min_cgpa"] is None else c["min_cgpa"],
                            "" if c["max_backlogs"] is None else c["max_backlogs"],
                            "" if c["batch"] is None else c["batch"],
                            c["summary"],
                            len(r["eligible"]) if r["status"] == "matched" else "n/a"])

    # eligible.csv
    with open(os.path.join(outdir, "eligible.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["job_id", "company", "roll", "name", "branch", "cgpa", "backlogs", "batch"])
        for r in results:
            for s in r["eligible"]:
                w.writerow([r["id"], r["company"], s["roll"], s["name"], s["branch"],
                            s["cgpa"], s["backlogs"], s["batch"]])

    # review.csv
    with open(os.path.join(outdir, "review.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "company", "post", "reason"])
        for r in results:
            if r["status"] == "needs_review":
                w.writerow([r["id"], r["company"], r["post"], "; ".join(r["reasons"])])

    # summary.txt
    eligible_rolls = {s["roll"] for r in results for s in r["eligible"]}
    with open(os.path.join(outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("DRAFT - the placement officer must check this before it is shared.\n\n")
        f.write("Eligible students per job\n")
        for r in results:
            if r["status"] == "matched":
                f.write(f"  {r['id']} {r['company']}: {len(r['eligible'])} eligible\n")
            else:
                f.write(f"  {r['id']} {r['company']}: NEEDS REVIEW (not matched)\n")
        f.write("\nStudents eligible for no job yet\n")
        none_yet = [s for s in students if s["roll"] not in eligible_rolls]
        if none_yet:
            for s in none_yet:
                f.write(f"  {s['roll']} {s['name']} ({s['branch']}, CGPA {s['cgpa']})\n")
        else:
            f.write("  (none)\n")


# ---------- Main ----------
def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()  # loads ANTHROPIC_API_KEY from the .env file
    except ImportError:
        pass

    jobs = load_jobs(JOBS_FILE)
    students = load_students(STUDENTS_FILE)
    if not jobs or not students:
        print("Nothing to process. Check your input files.")
        return
    system_prompt = load_system_prompt(PROMPT_FILE)
    print(f"Loaded {len(jobs)} jobs and {len(students)} students.\n")

    results = []
    for job in jobs:
        print(f"{job['id']} {job['company']}")
        raw = read_criteria(system_prompt, job["post"])
        if raw is None:
            results.append({**job, "criteria": None, "status": "needs_review",
                            "reasons": ["LLM reply missing or invalid after retry"],
                            "eligible": []})
            print("   -> needs_review (LLM fallback)")
            continue

        criteria, notes = check_facts(job["post"], raw)
        status, reasons = job_status(criteria)
        reasons = notes + reasons if status == "needs_review" else []
        eligible = [s for s in students if is_eligible(s, criteria)] if status == "matched" else []
        results.append({**job, "criteria": criteria, "status": status,
                        "reasons": reasons, "eligible": eligible})
        print(f"   -> {status}, {len(eligible)} eligible" if status == "matched"
              else f"   -> needs_review ({'; '.join(reasons)})")

    write_reports(results, students, OUTPUT_DIR)
    print(f"\nDone. Draft files written to '{OUTPUT_DIR}/'. Placement officer must check them.")


if __name__ == "__main__":
    main()