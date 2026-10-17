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
  // Progress bars take their width from data-pct.
  document.querySelectorAll(".bar span[data-pct]").forEach((el) => {
    const pct = Math.max(0, Math.min(100, Number(el.dataset.pct) || 0));
    el.style.width = pct + "%";
  });
});
