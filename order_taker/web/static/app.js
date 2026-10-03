// Small progressive enhancements shared by every page. Pages work without it.
(function () {
  // Confirm before destructive admin actions
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Copy-to-clipboard buttons
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var value = document.getElementById(btn.getAttribute("data-copy")).value;
    var done = function () { btn.textContent = "Copied!"; };
    // Over plain http on the Wi-Fi the Clipboard API isn't available, so fall back to a temporary textarea
    var fallback = function () {
      var t = document.createElement("textarea");
      t.value = value;
      t.setAttribute("readonly", "");
      t.style.position = "fixed";
      t.style.opacity = "0";
      document.body.appendChild(t);
      t.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      document.body.removeChild(t);
      if (ok) done();
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(value).then(done, fallback);
    else fallback();
  });

  // Item rows: add / remove
  document.addEventListener("click", function (e) {
    var add = e.target.closest("[data-add-item]");
    if (add) {
      var box = add.closest("[data-items]");
      var rows = box.querySelectorAll(".item-row");
      var row = rows[rows.length - 1].cloneNode(true);
      row.querySelectorAll("input").forEach(function (i) { i.value = ""; });
      box.insertBefore(row, add);
      row.querySelector("input").focus();
      return;
    }
    var rm = e.target.closest("[data-remove-item]");
    if (rm) {
      var all = rm.closest("[data-items]").querySelectorAll(".item-row");
      var r = rm.closest(".item-row");
      if (all.length > 1) r.remove();
      else r.querySelectorAll("input").forEach(function (i) { i.value = ""; });
    }
  });

  // Demo: fill the intake box with the sample chat (HOST-6)
  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-sample-chat]")) return;
    var box = e.target.closest("form").querySelector("textarea[name=text]");
    box.value = document.getElementById("sample-chat").content.textContent.trim();
    box.focus();
  });

  // Pickup toggle hides the address
  function syncPickup(box) {
    var form = box.closest("form");
    var addr = form && form.querySelector("[data-address]");
    if (addr) addr.hidden = box.checked;
  }
  document.querySelectorAll("[data-pickup]").forEach(function (b) {
    syncPickup(b);
    b.addEventListener("change", function () { syncPickup(b); });
  });

  // "Updated 10 minutes ago" (TRK-15)
  window.ago = function (iso) {
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "just now";
    var m = Math.round(s / 60);
    if (m < 60) return m + (m === 1 ? " minute ago" : " minutes ago");
    var h = Math.round(m / 60);
    if (h < 24) return h + (h === 1 ? " hour ago" : " hours ago");
    var d = Math.round(h / 24);
    return d + (d === 1 ? " day ago" : " days ago");
  };
  window.refreshAgo = function () {
    document.querySelectorAll("[data-ago]").forEach(function (t) {
      t.textContent = window.ago(t.getAttribute("data-ago"));
      t.title = t.getAttribute("data-ago").replace("T", " ");
    });
  };
  window.refreshAgo();
  setInterval(window.refreshAgo, 60000);
})();
