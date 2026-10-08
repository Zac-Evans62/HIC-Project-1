/* Shared interface pieces used by every page.
   UI.showToast(message, type)     short message that fades out
   UI.showUndo(message, onUndo)    "Undo" bar at the bottom of the screen
   UI.undoLast()                   triggers Undo if the bar is showing
   UI.confirmDialog({...})         Promise<boolean> for risky actions
   Any <form data-confirm="..."> asks for confirmation before it submits. */
(function () {
  "use strict";

  function toastArea() {
    let area = document.querySelector(".toast-area");
    if (!area) {
      area = document.createElement("div");
      area.className = "toast-area";
      area.setAttribute("role", "status");
      document.body.appendChild(area);
    }
    return area;
  }

  function dismissToast(el) {
    el.classList.add("hiding");
    setTimeout(function () { el.remove(); }, 300);
  }

  function showToast(message, type, ms) {
    const el = document.createElement("div");
    el.className = "toast toast-" + (type || "success");
    el.textContent = message;
    toastArea().appendChild(el);
    setTimeout(function () { dismissToast(el); }, ms || 4000);
  }

  document.querySelectorAll(".toast-area .toast").forEach(function (el) {
    const ms = el.classList.contains("toast-error") ? 8000 : 5000;
    setTimeout(function () { dismissToast(el); }, ms);
  });

  let bar = null;
  let timer = null;

  function hideUndo() {
    clearTimeout(timer);
    if (bar) { bar.remove(); bar = null; }
  }

  function showUndo(message, onUndo, ms) {
    hideUndo();
    const duration = ms || 6000;

    const el = document.createElement("div");
    el.className = "snackbar";
    el.setAttribute("role", "status");

    const text = document.createElement("span");
    text.textContent = message;

    const undo = document.createElement("button");
    undo.type = "button";
    undo.className = "snackbar-undo";
    undo.textContent = "Undo";

    const close = document.createElement("button");
    close.type = "button";
    close.className = "snackbar-close";
    close.setAttribute("aria-label", "Dismiss");
    close.textContent = "×";

    el.append(text, undo, close);
    document.body.appendChild(el);
    bar = el;

    function start() { clearTimeout(timer); timer = setTimeout(hideUndo, duration); }
    function pause() { clearTimeout(timer); }

    start();
    el.addEventListener("mouseenter", pause);
    el.addEventListener("mouseleave", start);
    el.addEventListener("focusin", pause);
    el.addEventListener("focusout", start);

    undo.addEventListener("click", function () { hideUndo(); onUndo(); });
    close.addEventListener("click", hideUndo);
  }

  function undoLast() {
    if (bar) { bar.querySelector(".snackbar-undo").click(); return true; }
    return false;
  }

  function confirmDialog(options) {
    const opts = options || {};
    return new Promise(function (resolve) {
      const dlg = document.createElement("dialog");
      dlg.className = "confirm-dialog";

      const form = document.createElement("form");
      form.method = "dialog";

      const title = document.createElement("h2");
      title.textContent = opts.title || "Are you sure?";

      const message = document.createElement("p");
      message.textContent = opts.message || "";

      const actions = document.createElement("div");
      actions.className = "confirm-actions";

      const cancel = document.createElement("button");
      cancel.value = "cancel";
      cancel.className = "btn btn-secondary";
      cancel.textContent = opts.cancelText || "Cancel";

      const ok = document.createElement("button");
      ok.value = "ok";
      ok.className = "btn " + (opts.danger ? "btn-danger" : "btn-primary");
      ok.textContent = opts.confirmText || "Confirm";

      actions.append(cancel, ok);
      form.append(title, message, actions);
      dlg.append(form);
      document.body.appendChild(dlg);

      dlg.addEventListener("close", function () {
        resolve(dlg.returnValue === "ok");
        dlg.remove();
      });

      dlg.showModal();
      cancel.focus();
    });
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!form.matches || !form.matches("form[data-confirm]") || form.dataset.confirmed) return;

    event.preventDefault();
    confirmDialog({
      title: form.dataset.confirmTitle,
      message: form.dataset.confirm,
      confirmText: form.dataset.confirmButton,
      danger: form.hasAttribute("data-confirm-danger")
    }).then(function (agreed) {
      if (agreed) {
        form.dataset.confirmed = "1";
        form.submit();
      }
    });
  });

  window.UI = {
    showToast: showToast,
    showUndo: showUndo,
    undoLast: undoLast,
    confirmDialog: confirmDialog
  };
})();
