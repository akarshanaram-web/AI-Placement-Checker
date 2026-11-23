# Judgment Framework
**CIT AI-Native Engineering Programme · Assessment 5**  
**Author:** Akarshana R | **System:** Placement Eligibility Checker  
**Domain:** Careers & Placements

---

## 1. Overview of the Judgment Framework
In an AI-native engineering pipeline, delegating decisions entirely to an LLM introduces risks of non-determinism, hallucination, and bias. The **Judgment Framework** structures safety, ethics, and accountability around three fundamental questions for each subsystem:
1. **What could go wrong here?** (Failure modes)
2. **Who gets hurt and how bad is it?** (Harm severity and asymmetry)
3. **How do we catch or prevent it?** (Automated safeguards and human governance)

---

## 2. Core Judgment Framework Analysis

| System Component | 1. What Could Go Wrong? (Failure Mode) | 2. Who Gets Hurt and How Bad Is It? (Impact) | 3. How Do We Catch or Prevent It? (Mitigation) |
| :--- | :--- | :--- | :--- |
| **Input Ingestion** (`load_jobs`, `load_students`) | • Malformed CSV rows (missing delimiters, unquoted commas in posts).<br>• Textual CGPA stored as string, leading to alphabetical sorting errors (`"10.0" < "7.5"`).<br>• Missing files. | **Students**: A parsing bug could exclude eligible students or crash the entire batch run, delaying placement notices. | • Explicit `try/except` handlers during parsing.<br>• Mandatory `float()` casting on CGPA and `int()` casting on backlogs/batch.<br>• Descriptive skip warnings for corrupt rows without terminating the process. |
| **LLM Criteria Extraction** (`call_llm`, `system_prompt.txt`) | • Hallucinated branch codes (e.g. inventing `"SWE"` or inferring CSE from "Software Developer").<br>• Converting percentages (`70%`) to CGPAs (`7.0`).<br>• Outputting malformed JSON or markdown chatter.<br>• Obeying prompt injection payloads embedded in job posts. | **Students & Recruiters**: Inaccurate criteria lead to either mass wrongful disqualification or recruiting inappropriate candidates. | • 5-Role Prompt Framework (Authority, Exemplar, Constraint, Rubric, Metadata).<br>• Strict negative constraints (e.g., "NEVER guess branch from role", "Percentages are NEVER converted").<br>• System prompt treats post as pure data enclosed in `<post></post>`.<br>• Single retry on parse/schema failure before fallback. |
| **Schema Validation** (`is_valid`) | • LLM returns missing keys or unexpected data types.<br>• Value ranges violated (e.g., negative backlogs, CGPA $> 10.0$).<br>• Summary exceeding length limit. | **Placement Office**: Unvalidated dictionaries would raise uncaught runtime exceptions downstream during matching. | • Strict key whitelist check (`FIELDS`).<br>• Type checking using `is_number` (distinguishing booleans from floats/ints).<br>• Range bounds checks ($0 \le \text{CGPA} \le 10$, $\text{backlogs} \ge 0$, $2000 \le \text{batch} \le 2100$). |
| **Python Fact Checking** (`check_facts`, `number_in_post`) | • LLM hallucinates criteria not actually present in post (e.g., hallucinating a batch or branch).<br>• Matching substrings inadvertently (e.g., matching English pronoun "it" as Information Technology). | **Students**: Hallucinated strict criteria filter out deserving students unfairly. | • Python does not trust LLM output.<br>• Regex-based post verification for every branch.<br>• Case-sensitive boundary checking for `\bIT\b`.<br>• Number verification ensuring numerical CGPA is physically written in post and not accompanied by `%` or `percent`. |
| **Job Status Triage** (`job_status`) | • Ambiguous posts (e.g., "top 10% of class" or "70% aggregate") erroneously treated as matched. | **Recruiters & Students**: Arbitrary machine guesses replace company intent, causing disputes or disqualifications. | • Deterministic rule: If `branches` is empty or `min_cgpa` is `None` after fact-checking, status **must** become `needs_review`.<br>• Descriptive reason logged for transparent manual resolution. |
| **Eligibility Matching** (`is_eligible`) | • False negatives: Eligible student excluded due to inequality bugs.<br>• False positives: Ineligible student approved.<br>• `ALL` branch flag mishandled. | **Students**: Missing life-changing placement drives.<br>**Placement Cell**: Loss of trust with recruiters. | • Clean boolean logic with explicit float comparison.<br>• Unit tested via eval harness.<br>• Student records stay entirely in Python; LLM never evaluates eligibility. |
| **Reporting & Export** (`write_reports`) | • Overwriting previous records without notice.<br>• Final lists sent directly to companies without human review. | **Placement Cell**: High liability if unchecked machine output is emailed directly to corporate partners. | • Clear classification into four separate files: `job_summary.csv`, `eligible.csv`, `review.csv`, and `summary.txt`.<br>• Every document explicitly stamped with **DRAFT** headers. |

---

## 3. Asymmetry of Harms: Wrongly Left Out vs. Wrongly Included

In placement operations, errors are fundamentally asymmetric. The cost and reversibility of a False Negative differ drastically from a False Positive:

```
+----------------------------------------------------------------------------------+
|                              ASYMMETRY OF HARMS                                  |
+----------------------------------------------------------------------------------+
|  TYPE OF ERROR              | SEVERITY | REVERSIBILITY | CONSEQUENCE            |
+-----------------------------+----------+---------------+------------------------+
|  FALSE NEGATIVE             | CRITICAL | IRREVERSIBLE  | Student is denied      |
|  (Student Wrongly Left Out) |          |               | the opportunity to     |
|                             |          |               | interview; career harm |
+-----------------------------+----------+---------------+------------------------+
|  FALSE POSITIVE             | MODERATE | REVERSIBLE    | Caught at human review |
|  (Student Wrongly Included) |          |               | or during recruiter    |
|                             |          |               | resume screening       |
+-----------------------------+----------+---------------+------------------------+
```

### Student Wrongly Left Out (False Negative — Critical Harm)
- **What happens:** An eligible student's name is omitted from the submission sent to a recruiter.
- **Why it is severe:** Placement drives have strict deadlines. Once the deadline passes or the test link is dispatched, additions are rarely accepted. The student loses an interview opportunity they earned through years of academic work.
- **System Safeguard:** 
  1. If criteria are ambiguous, the system never guesses a harsh cut-off; it routes the post to `needs_review`.
  2. The placement officer examines `summary.txt` ("Students eligible for no job yet") to verify that no deserving student was silently dropped.

### Student Wrongly Included (False Positive — Moderate / Catchable Harm)
- **What happens:** An ineligible student (e.g., having a backlog or slightly lower CGPA) is included on the draft list.
- **Why it is manageable:** The list produced by the tool is strictly an internal draft. The placement officer reviews `eligible.csv` against college records before mailing it to the recruiter. Even if passed forward, company recruiters verify original transcripts during the interview round.
- **System Safeguard:** 
  Deterministic floating-point verification in Python ensures no numerical cut-off violations occur in automated matching.

---

## 4. The Human Checkpoint
The **Human Checkpoint** is the central design requirement of the system:
> **The Placement Officer is the final decision-maker.** No list generated by the tool is ever transmitted directly to a company or published to students.

### Workflow at the Human Checkpoint:
1. **Step 1: Inspect `summary.txt`**
   - The placement officer reads the high-level eligible count per job.
   - The officer reviews the "Students eligible for no job yet" list to spot check why certain candidates have zero matches.
2. **Step 2: Resolve `review.csv`**
   - The officer reads posts marked `needs_review`.
   - For posts with percentage cut-offs (e.g. 70%), the officer manually consults college percentage-to-CGPA conversion charts or contacts the company recruiter.
   - For posts specifying roles without branches, the officer contacts the hiring manager to clarify eligible degrees.
3. **Step 3: Verification of `eligible.csv`**
   - The officer verifies candidate counts against company expectations.
   - The officer confirms disciplinary clearance or special placement waivers that the tool cannot see.
4. **Step 4: Formal Sign-off**
   - Only after human verification and signature is the student roster exported and dispatched to the hiring partner.
