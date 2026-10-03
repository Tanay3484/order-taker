// Customer page: refresh when the page comes back to the screen (TRK-15).
(function () {
  var last = null;
  function signature(data) {
    return JSON.stringify(data.orders.map(function (o) { return [o.id, o.status, o.updated_at, o.request_state]; }));
  }
  function check() {
    fetch("/my-orders.json", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var sig = signature(data);
        if (last !== null && sig !== last) window.location.replace("/my-orders");
        last = sig;
        window.refreshAgo();
      });
  }
  check();
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") check();
  });
})();
