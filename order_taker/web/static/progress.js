// Live "What's happening" box for an intake run (004).
(function () {
  var box = document.getElementById("progress");
  if (!box) return;
  var feed = box.querySelector("[data-feed]");
  var counter = box.querySelector("[data-counter]");
  var timer = box.querySelector("[data-timer]");
  var toggle = box.querySelector("[data-toggle]");
  var drafts = document.getElementById("drafts");
  var ICONS = { info: "✓", done: "✓", working: "…", warn: "⚠", error: "✗", summary: "★", draft_ready: "✓" };
  var started = null, finished = false, seen = {};

  // Follow the newest line unless the reader has scrolled up (PRG-1)
  function nearBottom() { return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 24; }

  function add(ev) {
    if (seen[ev.seq]) return;  // replay after reconnect (PRG-8)
    seen[ev.seq] = true;
    if (!started && ev.at) started = new Date(ev.at).getTime();
    var stick = nearBottom();
    var li = document.createElement("li");
    li.className = "k-" + ev.kind;
    var icon = document.createElement("span");
    icon.className = "icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = ICONS[ev.kind] || "•";
    var text = document.createElement("span");
    text.textContent = ev.text;
    li.appendChild(icon);
    li.appendChild(text);
    feed.appendChild(li);
    if (stick) feed.scrollTop = feed.scrollHeight;

    if (ev.total_count) counter.textContent = ev.done_count + " of " + ev.total_count + " people done ·";
    if (ev.draft_id) loadCard(ev.draft_id);
    if (ev.kind === "summary" || ev.finished) finish();
  }

  function loadCard(id) {
    if (document.getElementById("draft-" + id)) return;
    fetch("/admin/drafts/" + id + "/card", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.text() : ""; })
      .then(function (html) {
        if (!html || document.getElementById("draft-" + id)) return;
        if (!drafts.querySelector("h2")) {
          var h = document.createElement("h2");
          h.textContent = "To check";
          drafts.prepend(h);
        }
        var tmp = document.createElement("div");
        tmp.innerHTML = html.trim();
        var card = tmp.firstElementChild;
        card.classList.add("fresh");
        drafts.appendChild(card);
      });
  }

  function finish() {
    if (finished) return;
    finished = true;
    toggle.hidden = false;
    feed.classList.add("collapsed");
    feed.scrollTop = feed.scrollHeight;
    toggle.textContent = "Show details";
  }
  toggle.addEventListener("click", function () {
    var collapsed = feed.classList.toggle("collapsed");
    toggle.textContent = collapsed ? "Show details" : "Hide details";
    feed.scrollTop = feed.scrollHeight;
  });

  function tick() {
    if (!started || finished) return;
    var s = Math.max(0, Math.round((Date.now() - started) / 1000));
    timer.textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }
  setInterval(tick, 1000);

  var es = new EventSource("/admin/intake/" + box.getAttribute("data-run") + "/events");
  es.addEventListener("progress", function (e) { add(JSON.parse(e.data)); });
  es.addEventListener("end", function () { es.close(); finish(); });
})();
