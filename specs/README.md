# Specs

This project follows **Spec Driven Development**. Code is written to satisfy a spec, not the other way round.

## Layout

```
specs/
  constitution.md          # project-wide rules every spec and PR must respect
  NNN-feature-name/
    requirements.md        # user stories + numbered acceptance criteria (what & why)
    design.md              # how we'll build it (modules, data, APIs, trade-offs)
    tasks.md               # ordered, checkable implementation steps
```

## Workflow

1. **Specify**: write or change `requirements.md`. Every acceptance criterion gets a stable ID (e.g. `INT-4`).
2. **Design**: write `design.md` and resolve any open questions.
3. **Review**: a human approves the requirements and design. Set `Status: Approved` at the top of both.
4. **Plan**: break the work into `tasks.md`. Each task names the criteria it satisfies.
5. **Build**: implement task by task. Each test names the criterion it covers in its docstring, e.g. `"""INT-4: ..."""`.
6. **Change**: if the build shows the spec is wrong, update the spec first, then the code.

## Status values

`Draft` → `In review` → `Approved` → `Implemented`

## Features

| # | Feature | Status |
|---|---|---|
| 001 | [Platform: FastAPI app, SQLite store, LAN serving](001-platform/requirements.md) | Implemented |
| 002 | [Accounts & login: admin + customer (phone + PIN)](002-accounts-and-login/requirements.md) | Implemented |
| 003 | [Multi-agent order intake](003-multi-agent-intake/requirements.md) | Implemented |
| 004 | [Live progress feed in plain English](004-live-progress-feed/requirements.md) | Implemented |
| 005 | [Order tracking: statuses, admin board, customer view](005-order-tracking/requirements.md) | Implemented |

Build order: 001 → 002 → 003 → 004 → 005. Features 003 and 004 are built together because the agents emit the progress events.
