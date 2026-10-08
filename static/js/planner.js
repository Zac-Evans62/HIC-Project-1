/* Meal planner: add and remove meals without reloading the page.
   The server returns the updated HTML for just the slot that changed.
   Without JavaScript the same forms still work as normal submissions. */
(function () {
  "use strict";

  const planner = document.getElementById("planner");
  if (!planner) return;

  const summary = document.getElementById("planner-summary");
  const total = Number(planner.dataset.total);

  function updateSummary() {
    const filled = planner.querySelectorAll(".planner-slot.filled").length;
    summary.textContent = filled + " of " + total + " meals planned";
  }

  async function post(url, data) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new URLSearchParams(data)
      });
      if (res.redirected) { window.location.reload(); return { failed: true, silent: true }; }
      if (!res.headers.get("X-Planner-Slot")) return { failed: true };
      return { ok: res.ok, html: (await res.text()).trim() };
    } catch (err) {
      return { failed: true };
    }
  }

  function fail(result) {
    if (!result.silent) {
      UI.showToast("Something went wrong. Reload the page and try again.", "error");
    }
  }

  function swap(slotId, html) {
    const old = document.getElementById(slotId);
    if (!old) return null;
    old.outerHTML = html;
    updateSummary();
    return document.getElementById(slotId);
  }

  async function undoRemove(meal) {
    const result = await post(planner.dataset.addUrl, {
      csrf_token: planner.dataset.csrf,
      plan_date: meal.date,
      meal_slot: meal.slot,
      recipe_id: meal.recipeId,
      week: planner.dataset.week
    });
    if (result.failed) { fail(result); return; }

    swap(meal.slotId, result.html);
    if (result.ok) {
      UI.showToast('Put "' + meal.title + '" back in ' + meal.label + ".");
    } else {
      UI.showToast("Could not undo because that slot has a new meal.", "error");
    }
  }

  planner.addEventListener("submit", async function (event) {
    const form = event.target;
    const slotEl = form.closest(".planner-slot");
    const isAdd = form.classList.contains("add-form");
    const isRemove = form.classList.contains("remove-form");
    if (!slotEl || !(isAdd || isRemove)) return;

    event.preventDefault();

    const slotId = slotEl.id;
    const label = slotEl.dataset.label;
    const select = form.querySelector("select");
    const chosen = select && select.selectedOptions[0];
    const addedTitle = chosen ? chosen.textContent.trim() : "";
    const meal = isRemove ? {
      slotId: slotId,
      label: label,
      date: slotEl.dataset.date,
      slot: slotEl.dataset.slot,
      recipeId: form.dataset.recipeId,
      title: form.dataset.title
    } : null;

    const button = form.querySelector("button[type=submit]");
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = isAdd ? "Adding..." : "Removing...";

    const result = await post(form.action, new FormData(form));

    if (result.failed) {
      button.disabled = false;
      button.textContent = oldText;
      fail(result);
      return;
    }

    const fresh = swap(slotId, result.html);

    if (isAdd && result.ok) {
      UI.showToast('Added "' + addedTitle + '" to ' + label + ".");
      if (fresh) { const link = fresh.querySelector(".planned-meal a"); if (link) link.focus(); }
    } else if (isAdd) {
      if (fresh) { const pick = fresh.querySelector("select"); if (pick) pick.focus(); }
    } else if (result.ok) {
      UI.showUndo('Removed "' + meal.title + '" from ' + meal.label + ".",
                  function () { undoRemove(meal); });
      if (fresh) { const pick = fresh.querySelector("select"); if (pick) pick.focus(); }
    }
  });
})();
