/* Shopping list: check items off, remove extras with undo, and keep the
   "left to buy" counter live without reloading the page.
   Without JavaScript the same forms still work as normal page submissions. */
(function () {
  "use strict";

  const root = document.getElementById("shopping");
  if (!root) return;

  const summary = document.getElementById("shop-summary");
  const bar = document.getElementById("shop-bar");

  function boxes() {
    return Array.prototype.slice.call(
      root.querySelectorAll(".toggle-form input[type=checkbox]")
    );
  }

  function updateSummary() {
    if (!summary) return;
    const all = boxes();
    const total = all.length;
    const done = all.filter(function (box) { return box.checked; }).length;

    if (total === 0) summary.textContent = "";
    else if (done === total) summary.textContent = "All done! Everything is checked off.";
    else summary.textContent = (total - done) + " of " + total + " left to buy";

    if (bar) bar.style.width = (total ? Math.round(done / total * 100) : 0) + "%";
  }

  // Resolves to the parsed JSON, or null when the page is reloading (e.g. session expired).
  async function send(form) {
    try {
      const res = await fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new URLSearchParams(new FormData(form))
      });
      if (res.redirected) { window.location.reload(); return null; }
      if (!res.ok) return { ok: false };
      return await res.json();
    } catch (err) {
      return { ok: false };
    }
  }

  root.addEventListener("change", async function (event) {
    const box = event.target;
    if (!box.matches || !box.matches(".toggle-form input[type=checkbox]")) return;

    updateSummary();
    const result = await send(box.form);
    if (result === null) return;

    if (!result.ok) {
      box.checked = !box.checked;
      updateSummary();
      UI.showToast("Could not save that change. Try again.", "error");
    }
  });

  async function addBack(name, quantity) {
    try {
      const res = await fetch(root.dataset.addUrl, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new URLSearchParams({
          csrf_token: root.dataset.csrf,
          week: root.dataset.week,
          name: name,
          quantity: quantity
        })
      });
      if (res.ok) { window.location.reload(); return; }
    } catch (err) { /* fall through to the message below */ }
    UI.showToast("Could not undo. Add the item again from the form below.", "error");
  }

  root.addEventListener("submit", async function (event) {
    const form = event.target;
    if (!form.classList || !form.classList.contains("remove-form")) return;

    event.preventDefault();
    const name = form.dataset.name;
    const quantity = form.dataset.quantity;
    const row = form.closest("li");

    const result = await send(form);
    if (result === null) return;
    if (!result.ok) {
      UI.showToast("Could not remove that item. Try again.", "error");
      return;
    }

    const list = row.parentElement;
    row.remove();
    if (!list.querySelector("li")) {
      const section = document.getElementById("extras-section");
      if (section) section.hidden = true;
    }
    updateSummary();
    UI.showUndo('Removed "' + name + '" from your list.', function () {
      addBack(name, quantity);
    });
  });
})();
