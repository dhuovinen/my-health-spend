// The landing page's motion (ADR-047, REBRAND_PLAN.md §5). The page reads complete without this file: it only lines the
// sample documents up the first time they come into view and keeps the red pen redrawing its loop while a loop is on
// screen. Visitors who ask for reduced motion get the finished drawing, and anyone can pause the pen (WCAG 2.2.2).
// Same-origin, so it runs under the Content Security Policy.
document.addEventListener("DOMContentLoaded", () => {
  if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const root = document.documentElement;
  const KEY = "careback-pen-paused";
  const remembered = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } };
  const remember = (paused) => { try { localStorage.setItem(KEY, paused ? "1" : "0"); } catch { /* private window */ } };

  root.classList.add("motion");
  const toggle = document.querySelector(".pen-toggle");
  const show = (paused) => {
    root.classList.toggle("pen-paused", paused);
    toggle.textContent = paused ? "Play the red pen" : "Pause the red pen";
  };
  show(remembered());
  toggle.hidden = false;
  toggle.addEventListener("click", () => {
    const paused = !root.classList.contains("pen-paused");
    show(paused);
    remember(paused);
  });

  // .drawn starts the block's animation once; .offscreen holds the pen still while nobody can see it.
  const watch = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (entry.isIntersecting) entry.target.classList.add("drawn");
    entry.target.classList.toggle("offscreen", !entry.isIntersecting);
  }), { threshold: 0.35 });
  document.querySelectorAll("[data-draw]").forEach((block) => watch.observe(block));
});
