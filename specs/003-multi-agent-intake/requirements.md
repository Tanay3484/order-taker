# 003 Multi-Agent Order Intake: Requirements

Status: Implemented

## Context
Today the whole chat goes to one 7B model call. It takes a minute or more, it re-reads messages that were already handled, and nothing happens until the very end. We want a **Master agent** that splits the work and hands it to small, focused **sub-agents** working in parallel, so new orders are ready for the admin to accept as quickly as possible.

## User stories
- **US-1** As the admin, I paste the day's WhatsApp chat (or upload the exported `.txt`) and get draft orders back faster than before.
- **US-2** As the admin, when I paste the same chat again later with new messages at the bottom, only the new messages get processed.
- **US-3** As the admin, when a customer changes or cancels an order they placed earlier, the app proposes a change to that existing order, not a duplicate.
- **US-4** As the admin, I review every draft (accept, edit or discard) before it becomes a real order, and the app points out anything that's missing or odd.

## Acceptance criteria

### Master agent
| ID | Criterion |
|---|---|
| INT-1 | THE SYSTEM SHALL parse both WhatsApp export formats, `[02/10/26, 9:14 PM] Name: text` (iOS) and `02/10/26, 9:14 pm - Name: text` (Android), including multi-line messages and system lines ("Messages are end-to-end encrypted", "<Media omitted>"), which are dropped. |
| INT-2 | WHEN the pasted text has no recognisable timestamps, THE SYSTEM SHALL treat it as a single conversation from an unknown sender and still process it. |
| INT-3 | THE SYSTEM SHALL skip any message already processed in an earlier run (same sender, timestamp and text) and report how many were skipped. |
| INT-4 | THE SYSTEM SHALL group the new messages by sender, and each group SHALL move through Sorter → Extractor → Checker on its own, without waiting for other groups. |
| INT-5 | THE SYSTEM SHALL run at most `ORDER_PARALLEL` model calls at the same time. |
| INT-6 | Only one intake run SHALL be active at a time. A second request while one is running SHALL show the running one. |

### Sorter agent (small model)
| ID | Criterion |
|---|---|
| INT-7 | THE SYSTEM SHALL classify each sender's group as `new_order`, `change`, `cancel`, `question` or `chit_chat`, using `ORDER_SORTER_MODEL`. |
| INT-8 | Groups classed `chit_chat` SHALL skip the Extractor. Groups classed `question` SHALL become a "Needs a reply" note for the admin and skip the Extractor. A group made only of greeting/thanks words and emojis, with no numbers, SHALL be recognised as chit-chat in code, with no model call at all. Any unfamiliar word sends it to the model. *(Last sentence added during build.)* |
| INT-9 | WHEN the sorter model isn't installed, or is the same as `ORDER_MODEL`, THE SYSTEM SHALL skip the separate sorting call and have the Extractor classify the messages in the same call (one model call per sender instead of two), and say so once in the progress feed. *(Amended during build: the benchmark showed that sorting with the 7B model doubled the number of slow calls.)* |

### Extractor agents (main model, one per sender)
| ID | Criterion |
|---|---|
| INT-10 | THE SYSTEM SHALL extract that sender's orders using only their messages (with when each was sent) and their currently open orders (matched by phone, otherwise by exact name). Dates are worked out afterwards in code (INT-21). |
| INT-11 | Each extracted item SHALL be one of: `new` order; `update` of an existing open order (with its ID and the new full details); or `cancel` of an existing open order (with its ID). |
| INT-12 | WHEN the model returns invalid output, THE SYSTEM SHALL retry once. If it fails again, it SHALL create a draft flagged "Couldn't read this one, please check the messages" containing the original messages. |
| INT-13 | Existing extraction rules are kept: ignore chit-chat, keep only the final version of an edited order, never invent details, translate mixed-language item names to plain English. |
| INT-21 | The model SHALL copy the delivery day as the customer wrote it ("Sunday", "kal", "tomorrow", "5th Oct"), and **code** SHALL turn it into a date relative to when the customer's last message was sent (today, tomorrow/kal/naale/naalai, day after/parso, weekday names with optional "this"/"next", day + month). Anything it can't resolve stays as written and is flagged "The delivery date isn't clear." *(Added during build: on the sample chat the 7B model mapped "Sunday" to a Thursday.)* |
| INT-22 | WHEN the model leaves the phone empty, THE SYSTEM SHALL use the first Indian mobile number found in the sender's messages, or the sender's number if they're an unsaved contact. *(Added during build: the model missed "My number 98450 12345".)* |

### Checker agent
| ID | Criterion |
|---|---|
| INT-14 | THE SYSTEM SHALL flag, in plain English, any draft that has: no delivery date; a date in the past; no address and no sign of pickup ("Delivery or pickup?"); no phone; a phone that isn't 10 digits ("The phone number doesn't look right. It needs 10 digits."); a quantity of 0; an `update`/`cancel` pointing at an order that isn't open; or the same customer + date + items as another draft or open order ("Looks like a duplicate"). |
| INT-15 | Flags SHALL NOT block acceptance. They're shown on the draft for the admin to judge. |

### Review
| ID | Criterion |
|---|---|
| INT-16 | Drafts SHALL appear on the admin intake page as soon as each sender's group finishes, without waiting for the whole run. |
| INT-17 | For each draft, the admin SHALL be able to **Accept**, **Edit then accept**, or **Discard**. `update` drafts SHALL show what changes (old → new). |
| INT-18 | Nothing extracted SHALL change real orders until the admin accepts it. |

### Speed
| ID | Criterion |
|---|---|
| INT-19 | With a faked model that takes 1s per call and `ORDER_PARALLEL=3`, a 3-sender chat SHALL finish in under 2.5× one sender's time (i.e. the work really runs in parallel). |
| INT-20 | A benchmark script SHALL time the new pipeline against the old single-call extraction on `samples/` with the real model and print both times. |

## Out of scope
- Reading WhatsApp directly (still paste or upload), images and voice notes, automatic replies to customers.
