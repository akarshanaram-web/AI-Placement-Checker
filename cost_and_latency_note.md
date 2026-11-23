# Cost and Latency Note

Placement Eligibility Checker, Akarshana R

## How many API calls does one day of input need?

The tool makes **one LLM call per job post**. The placement cell receives several posts a
week, so I plan for a busy day of **10 posts** (the size of my test file `jobs.csv`).

- 10 posts = **10 calls**.
- If every call failed once and was retried (my code retries once), the worst case is
  **20 calls**.
- Student records are never sent. Only the post text goes to the LLM, so the number of
  students does not change the number of calls.

## How long does each call take?

I timed a full run of all 10 posts, including loading the files, matching students and
writing the four output files:

- Total time: **about 65 seconds** for 10 posts.
- Average: **about 6.5 seconds per post**.

This run used the `openrouter/free` model router, which picks a different free model each
time, so speed varies from call to call and from day to day. The Python work (fact checks,
matching, writing files) takes a tiny part of that time. Almost all of it is waiting for
the LLM. A whole day of posts finishes in about a minute or two, which is fine because the
tool runs once, not live.

## What does it cost per day?

Estimated size of one call (about 4 characters per token, so these are estimates):

- System prompt: about 840 tokens, plus the post about 20 tokens, so **about 870 input tokens**.
- Reply: one small JSON object, **about 75 output tokens**.
- 10 calls = about **8,700 input and 750 output tokens**.

**Cost today: Rs 0.** I use a free-tier key (OpenRouter free models). The limits of the free tier
are a daily request cap, and I hit it once (error 429). The tool handled that safely by
sending the posts to `needs_review` instead of crashing.

**If I used a paid model,** the cost is:
(input tokens / 1,000,000 x input price) + (output tokens / 1,000,000 x output price).
Example with made-up prices of $1 per million input tokens and $3 per million output
tokens (these are example numbers, not a real quote):

- 10 calls: 0.0087 + 0.00225 = about **$0.011 per day**, roughly one cent.
- Worst case with retries (20 calls): about **$0.022 per day**.

Even at a real paid price, a day of posts would cost very little. The cost grows with the
number of posts, not with the number of students.
