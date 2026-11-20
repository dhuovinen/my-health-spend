// The landing page's sample review: a native dialog with tabs. Same-origin, so it runs under the Content Security Policy.
document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.getElementById("sample");
  document.querySelectorAll("[data-open-sample]").forEach((button) => {
    button.addEventListener("click", () => dialog.showModal());
  });
  dialog.querySelector("[data-close-sample]").addEventListener("click", () => dialog.close());
  // A click on the backdrop lands on the dialog element itself, outside its content box.
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    const inside = event.clientX >= box.left && event.clientX <= box.right
      && event.clientY >= box.top && event.clientY <= box.bottom;
    if (!inside) dialog.close();
  });

  const tabs = [...dialog.querySelectorAll('[role="tab"]')];
  const select = (chosen) => {
    tabs.forEach((tab) => {
      const on = tab === chosen;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden = !on;
    });
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const next = tabs[(index + step + tabs.length) % tabs.length];
      select(next);
      next.focus();
    });
  });
});
