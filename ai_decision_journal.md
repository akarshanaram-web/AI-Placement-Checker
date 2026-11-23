# AI Decision Journal
**CIT AI-Native Engineering Programme · Assessment 5**  
**Author:** Akarshana R | **System:** Placement Eligibility Checker  
**Domain:** Careers & Placements

---

## Purpose of this Journal
This journal documents the major architectural, algorithmic, and safety decisions made during the design and implementation of the Placement Eligibility Checker. Each entry captures the context, options considered, the decision made, and the underlying rationale.

---

### Decision 1: Boundary Separation — Criteria Extraction vs. Eligibility Matching
- **Date:** Week 11 / Project Inception
- **Context:** The placement cell needs to filter hundreds of student profiles against messy, unstructured job posts.
- **Alternatives Considered:**
  1. *Full LLM Pipeline:* Feed both the job post and the entire `students.csv` database to the LLM and prompt it to directly output eligible students.
  2. *Hybrid Pipeline:* Use the LLM only as a semantic parser to extract structured eligibility criteria from the job post; execute deterministic student matching in Python.
- **Decision:** Adopt the **Hybrid Pipeline**. Student data NEVER goes to the LLM.
- **Rationale:**
  - *Privacy & Security:* Transmitting student PII (rolls, names, CGPAs, backlog records) to third-party LLM providers violates data protection principles (DPDP Act).
  - *Reliability:* LLMs are notoriously unreliable at multi-condition numerical inequality checks across hundreds of records. Python performs arithmetic comparisons with 100% mathematical certainty.
  - *Cost & Scalability:* Sending hundreds of student records with every job post would balloon token consumption. Criteria extraction requires only ~870 tokens per post regardless of student population size.
  - *Injection Immunity:* Keeping student databases in Python ensures prompt injection attacks cannot manipulate candidate eligibility.

---

### Decision 2: System Prompt Architecture (5-Role Framework)
- **Date:** Week 12
- **Context:** Raw LLM completions frequently included conversational filler, markdown formatting (` ```json `), or hallucinated branch acronyms.
- **Alternatives Considered:**
  1. *Zero-Shot Prompt:* Simple instruction: "Extract eligibility criteria as JSON."
  2. *5-Role Structured Prompt:* Explicitly structured into **Authority, Constraint, Exemplar, Rubric, and Metadata**.
- **Decision:** Implement the **5-Role Framework** in `system_prompt.txt`.
- **Rationale:**
  - *Authority:* Defines the narrow persona ("careful data-extraction assistant; never decides eligibility").
  - *Constraint:* Strict schema whitelists (`branches` restricted to 7 college branches or `ALL`; negative constraints forbidding inference of branch from job role).
  - *Exemplar:* Four comprehensive few-shot examples demonstrating edge cases (percentage cut-off, all-branches, missing branches).
  - *Rubric:* Self-verification checklist executed by the model before emitting JSON.
  - *Metadata:* Clear input/output framing using `<post></post>` XML tags.

---

### Decision 3: Deterministic Fact-Checking Layer in Python
- **Date:** Week 13
- **Context:** Even with temperature 0, LLMs can hallucinate branches or misread numbers.
- **Alternatives Considered:**
  1. *Trust LLM output:* Directly accept validated JSON into the matching engine.
  2. *Python Fact Checker:* A deterministic verification layer (`check_facts()`) that independently confirms every branch and number exists in the raw post text.
- **Decision:** Implement **Python Fact-Checking**. Python does not trust the LLM.
- **Rationale:**
  - Defense-in-depth: If the LLM claims `ECE` is eligible because the post mentions "electronics", but the college only offers `ECE` when explicitly stated, regex verification enforces institutional taxonomy.
  - Special handling for `IT`: Searching for `IT` case-insensitively causes false positives on the English pronoun "it" (e.g., "apply if it fits you"). Python uses case-sensitive regex `\bIT\b`.

---

### Decision 4: Non-Conversion of Percentages and Vague Cut-Offs
- **Date:** Week 13
- **Context:** Companies frequently state criteria as "70 percent in all semesters" or "top 10 percent of class".
- **Alternatives Considered:**
  1. *Mathematical Conversion:* Convert 70% to 7.0 CGPA (or divide by 9.5).
  2. *Strict Null Setting with Review Routing:* Refuse conversion; emit `min_cgpa: null` and flag the job as `needs_review`.
- **Decision:** Enforce **strict non-conversion**.
- **Rationale:**
  - Universities have divergent formulaic conversion scales between percentage marks and 10-point CGPA systems. Any algorithmic conversion without official placement cell sanction introduces unfair advantages or exclusions.
  - Vague terms like "top 10%" require class ranking data that is not part of a standard CGPA ledger.
  - Routing to `needs_review` ensures the human placement officer makes the policy decision.

---

### Decision 5: Transient Error Recovery and Retry Budget
- **Date:** Week 14
- **Context:** Cloud APIs experience transient failures, network latency, rate limits (HTTP 429), or occasional JSON decode errors.
- **Alternatives Considered:**
  1. Crash the program immediately on any API error.
  2. Infinite retry loop.
  3. Single retry, followed by graceful fallback to `needs_review`.
- **Decision:** Implement **single retry + graceful fallback**.
- **Rationale:**
  - A single transient timeout or bad JSON completion is frequently resolved on an immediate retry.
  - If the second attempt fails, continuing to retry causes cascading hangs.
  - Falling back to `needs_review` allows the placement officer to manually process the single failed job post while allowing the remaining 90% of jobs to match successfully.

---

### Decision 6: Numerical Casting of CGPA
- **Date:** Week 14
- **Context:** Reading data from CSV files returns string values by default.
- **Alternatives Considered:**
  1. Lexicographical string comparison (`student["cgpa"] >= criteria["min_cgpa"]`).
  2. Float casting (`float(student["cgpa"]) >= criteria["min_cgpa"]`).
- **Decision:** Mandatory **float casting**.
- **Rationale:**
  - In string comparison, `"10.0" < "7.5"` evaluates to `True` because the character `'1'` is ASCII-less than `'7'`. This classic bug would systematically disqualify all perfect 10.0 CGPA students.
  - Explicit `float()` and `int()` casting ensures mathematical correctness.

---

### Decision 7: Multi-File Draft Reporting Architecture
- **Date:** Week 15
- **Context:** How to present results so that placement officers can quickly act without risk of sending raw AI output to companies.
- **Decision:** Output four separated files:
  1. `job_summary.csv`: Master overview of all postings.
  2. `eligible.csv`: Per-job student rosters.
  3. `review.csv`: Exception handling queue with explicit reasons.
  4. `summary.txt`: Executive brief highlighting unplaced students.
- **Rationale:** Decoupling exceptions (`review.csv`) from successful matches (`eligible.csv`) prevents human reviewers from having to sift through hundreds of clean records to find ambiguous cases.

