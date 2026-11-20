// Small same-origin behaviours that replace inline handlers, so pages work under the Content Security Policy.
document.addEventListener("DOMContentLoaded", () => {
  // Plan-year selects submit their form on change.
  document.querySelectorAll("select[data-autosubmit]").forEach((el) => {
    el.addEventListener("change", () => el.form.submit());
  });
  // A file input marked data-autosubmit uploads as soon as a file is chosen (the phone's "Take a photo").
  document.querySelectorAll("input[type=file][data-autosubmit]").forEach((el) => {
    el.addEventListener("change", () => { if (el.files.length) el.form.submit(); });
  });
  // Forms with data-confirm ask before submitting (e.g. deleting a note).
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  // Menus (the account menu, the phone's More): one open at a time; a click elsewhere or Escape closes them.
  const menus = document.querySelectorAll("details.menu");
  menus.forEach((menu) => menu.addEventListener("toggle", () => {
    if (menu.open) menus.forEach((other) => { if (other !== menu) other.open = false; });
  }));
  document.addEventListener("click", (event) => {
    menus.forEach((menu) => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") menus.forEach((menu) => { menu.open = false; });
  });
  // Progress bars take their width from data-pct.
  // UX-11: a dot's details, on hover, keyboard focus or a tap.
  const detail = document.getElementById("dot-detail");
  document.querySelectorAll(".charges-chart .dot").forEach((dot) => {
    const show = () => {
      const d = dot.dataset;
      detail.textContent = `${d.provider}, ${d.member}, ${d.date}. Billed ${d.billed}; your share ${d.share}. ${d.status}.`;
      detail.classList.remove("muted");
    };
    dot.addEventListener("mouseenter", show);
    dot.addEventListener("focus", show);
    dot.addEventListener("click", (event) => { event.preventDefault(); show(); });
  });
  document.querySelectorAll(".bar span[data-pct]").forEach((el) => {
    const pct = Math.max(0, Math.min(100, Number(el.dataset.pct) || 0));
    el.style.width = pct + "%";
  });
});
