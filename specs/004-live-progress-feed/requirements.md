# 004 Live Progress Feed: Requirements

Status: Implemented

## Context
Right now the admin sees "Processing…" for a minute or more, which feels broken to non-technical users. While the agents work, the admin page should show a small, friendly running commentary of what's happening, in everyday English.

This is **narration of the steps**, not the model's raw "thinking". Raw model reasoning can be long, technical or just wrong, so we never show it.

## User stories
- **US-1** As the admin, I can see that the app is working and roughly what it's doing, so I don't think it's stuck.
- **US-2** As the admin, I can understand every message without knowing anything about AI.
- **US-3** As the admin, I can see how far along it is and start reviewing orders that are already done.

## Acceptance criteria
| ID | Criterion |
|---|---|
| PRG-1 | WHEN an intake run starts, THE SYSTEM SHALL show a small progress box (about 6 lines tall, scrolls itself, newest at the bottom) on the admin intake page within 1 second. |
| PRG-2 | THE SYSTEM SHALL post a message at each step: started, messages skipped, people found, each person sorted (with the outcome), each person's details being written down, each draft ready, each flag raised, each failure, and finished. |
| PRG-3 | Every message SHALL come from a fixed set of plain-English templates filled in with names and counts. Model-generated text SHALL NOT be shown. |
| PRG-4 | Messages SHALL NOT contain technical words: no model names, "JSON", "API", "agent", "token", "Ollama", "error code" or stack traces. A test SHALL check every template against this word list. |
| PRG-5 | WHEN one person's step has been running for 15 seconds, THE SYSTEM SHALL post a reassurance ("Still working on Priya's messages, nearly there…"), and again every 15 seconds after that (with varied wording). |
| PRG-6 | THE SYSTEM SHALL show an overall progress line, "2 of 4 people done", plus a running timer. |
| PRG-7 | WHEN the run finishes, THE SYSTEM SHALL post a one-line summary, e.g. "All done in 38 seconds: 3 orders to check, 1 message needs a reply, 1 just chatting." |
| PRG-8 | WHEN the admin reloads the page or the connection drops during a run, THE SYSTEM SHALL show all messages so far and keep updating. |
| PRG-9 | The progress box SHALL be readable by screen readers (`aria-live="polite"`) and fit a 360px-wide phone. |
| PRG-10 | Only the admin SHALL be able to see the progress feed (it contains customer names). |

## Example feed (sample chat)
```
✓ Got it! Reading 6 new messages…
✓ Found messages from 4 people: Priya, Rahul Bhaiya, Meena, Sneha.
✓ Meena is just saying good night. Nothing to order.
… Priya wants to order something. Writing down the details…
… Rahul Bhaiya changed his order. Working out what's different…
… Sneha wants to order something. Writing down the details…
✓ Sneha's order is ready for you to check.
⚠ Sneha didn't say whether it's delivery or pickup. I've marked it for you.
… Still working on Priya's messages, nearly there…
✓ Priya's order is ready for you to check.
✓ Rahul Bhaiya's change is ready for you to check.
★ All done in 41 seconds: 3 orders to check, 1 just chatting.
```
