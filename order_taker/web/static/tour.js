// Guided tour (007). The words come from order_taker/tours.py via #tour-data;
// this file only finds the highlighted part, dims the rest and places the explanation.
(function () {
  var dataEl = document.getElementById("tour-data");
  if (!dataEl) return;
  var tour = JSON.parse(dataEl.textContent);
  var KEY = "ot-tour-" + tour.id + "-v" + tour.version;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var steps = [], index = 0, spot = null, pop = null, target = null, frame = 0;

  // TOUR-8: the page works the same if storage is blocked
  function seen() { try { return localStorage.getItem(KEY) === "done"; } catch (e) { return false; } }
  function remember() { try { localStorage.setItem(KEY, "done"); } catch (e) { /* ignore */ } }

  function visible(el) { return !!(el && el.getClientRects().length && getComputedStyle(el).visibility !== "hidden"); }

  // TOUR-5: skip steps whose part of the page isn't there
  function findSteps() {
    return tour.steps.map(function (s) {
      var all = document.querySelectorAll('[data-tour="' + s.target + '"]');
      for (var i = 0; i < all.length; i++) if (visible(all[i])) return { step: s, el: all[i] };
      return null;
    }).filter(Boolean);
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function build() {
    spot = el("div", "tour-spot");
    spot.setAttribute("aria-hidden", "true");
    pop = el("div", "tour-pop");
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-modal", "false");
    pop.setAttribute("aria-labelledby", "tour-title");
    pop.innerHTML =
      '<p class="tour-count"></p><h2 class="tour-title" id="tour-title"></h2><p class="tour-text"></p>' +
      '<div class="tour-buttons"><button type="button" class="link tour-skip">Skip tour</button>' +
      '<span class="row"><button type="button" class="btn small tour-back">Back</button>' +
      '<button type="button" class="btn small primary tour-next">Next</button></span></div>';
    document.body.appendChild(spot);
    document.body.appendChild(pop);
    pop.querySelector(".tour-skip").addEventListener("click", end);
    pop.querySelector(".tour-back").addEventListener("click", function () { go(index - 1); });
    pop.querySelector(".tour-next").addEventListener("click", function () { go(index + 1); });
    listen();
  }

  function listen() {
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("scrollend", schedule);
    window.addEventListener("resize", schedule);
    document.addEventListener("keydown", onKey);
  }

  function onKey(e) {
    if (!pop) return;
    if (e.key === "Escape") end();
    else if (e.key === "ArrowRight") go(index + 1);
    else if (e.key === "ArrowLeft" && index > 0) go(index - 1);
  }

  function schedule() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(place);
  }

  // TOUR-7: below if it fits, else above, else a bottom sheet; always 16px from the edges
  function place() {
    if (!target || !pop) return;
    var r = target.getBoundingClientRect(), pad = 6, gap = 12, edge = 16;
    spot.style.top = (r.top - pad) + "px";
    spot.style.left = (r.left - pad) + "px";
    spot.style.width = (r.width + pad * 2) + "px";
    spot.style.height = (r.height + pad * 2) + "px";

    var vw = window.innerWidth, vh = window.innerHeight;
    var w = Math.min(340, vw - edge * 2);
    pop.style.width = w + "px";
    var h = pop.offsetHeight;
    var left = Math.min(Math.max(r.left, edge), vw - w - edge);
    var top;
    pop.classList.remove("sheet");
    if (r.bottom + pad + gap + h <= vh - edge) top = r.bottom + pad + gap;
    else if (r.top - pad - gap - h >= edge) top = r.top - pad - gap - h;
    else { pop.classList.add("sheet"); top = vh - h - edge; left = (vw - w) / 2; }
    pop.style.top = top + "px";
    pop.style.left = left + "px";
  }

  function go(i) {
    if (i >= steps.length) { end(); return; }
    if (i < 0) return;
    index = i;
    var s = steps[i];
    target = s.el;
    pop.querySelector(".tour-count").textContent = "Step " + (i + 1) + " of " + steps.length;
    pop.querySelector(".tour-title").textContent = s.step.title;
    pop.querySelector(".tour-text").textContent = s.step.text;
    pop.querySelector(".tour-back").hidden = i === 0;
    pop.querySelector(".tour-next").textContent = i === steps.length - 1 ? "Done" : "Next";
    target.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
    place();
    // Smooth scrolling takes a moment and doesn't always fire scroll events at the end,
    // so place again once it has settled.
    [150, 400, 800].forEach(function (ms) { setTimeout(place, ms); });
    pop.querySelector(".tour-next").focus({ preventScroll: true });
  }

  function start() {
    steps = findSteps();
    if (!steps.length) return;
    build();
    document.documentElement.classList.add("touring");
    go(0);
  }

  function end() {
    remember();
    document.documentElement.classList.remove("touring");
    window.removeEventListener("scroll", schedule);
    window.removeEventListener("scrollend", schedule);
    window.removeEventListener("resize", schedule);
    document.removeEventListener("keydown", onKey);
    if (spot) spot.remove();
    if (pop) pop.remove();
    spot = pop = target = null;
    var again = document.querySelector("[data-tour-start]");
    if (again) again.focus({ preventScroll: true });
  }

  // TOUR-4: replay any time; start by itself the first time
  document.querySelectorAll("[data-tour-start]").forEach(function (b) {
    b.addEventListener("click", function () { if (pop) end(); start(); });
  });
  if (!seen()) setTimeout(start, 500);
})();
