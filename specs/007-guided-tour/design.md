# 007 Guided Tour: Design

Status: Implemented

## Where the words live
`order_taker/tours.py` holds every tour as data, so the text can be tested in Python like the progress templates:
```python
@dataclass(frozen=True)
class Step:
    target: str          # matches data-tour="..." on the page
    title: str
    text: str
    demo_only: bool = False
    optional: bool = False  # may be missing (no orders yet, no changes…)

TOURS: dict[str, list[Step]]              # "login-customer", "login-admin", "board", "intake", "my-orders"
def for_page(template, ctx, demo) -> dict | None   # {"id", "version", "steps": [...]}, demo-only steps removed
```
`deps.render()` calls `for_page`, so routes don't change. `base.html` writes the tour as JSON (`<script type="application/json" id="tour-data">`, escaped with Jinja's `tojson`) and shows the **Show me around** button.

## Targets
Templates mark parts of the page with `data-tour="name"`. When a name appears more than once (order cards), the first visible one is used. Steps whose target isn't on the page or isn't visible are dropped in the browser (TOUR-5).

## Browser (`static/tour.js`, about 150 lines)
- **Spotlight:** a fixed-position box over the target with a huge `box-shadow` that dims everything else. `pointer-events: none`, so the page still works underneath.
- **Popover:** `role="dialog"`, `aria-labelledby` the title, focus moves to **Next**. Placed below the target if it fits, else above, else as a bottom sheet. Clamped 16px from the screen edges.
- **Movement:** the target is scrolled into view (smoothly unless `prefers-reduced-motion`). Position updates on scroll and resize.
- **Memory:** `localStorage["ot-tour-<id>-v<version>"] = "done"` on Done/Skip/Esc. Bumping `version` in `tours.py` shows a changed tour again. All storage access is wrapped in try/catch (TOUR-8).

## Tests
- Every non-optional target exists on its rendered page (demo data seeded) (TOUR-1, TOUR-5).
- PIN step wording (TOUR-3). Demo-only steps excluded without demo (TOUR-5).
- Banned-word check over all tour text (TOUR-6).
- Customers never get an admin tour; pages without a tour have no button (TOUR-1).
- Visual check with headless Edge on a phone-width page (TOUR-7).
