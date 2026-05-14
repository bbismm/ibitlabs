/* tz.js — viewer-local timestamp rendering for ibitlabs.com
 *
 * Convention: emit
 *     <time datetime="2026-05-14T20:10:42Z" data-tz="dual">2026-05-14 20:10 UTC</time>
 * The text inside is a UTC fallback (used if JS is off or parsing fails).
 * On page load this script overwrites the textContent with viewer-local rendering.
 *
 * data-tz modes:
 *   "dual"        → "2026-05-14 20:10 UTC · 16:10 EDT"  (default)
 *   "local"       → "2026-05-14 16:10 EDT"
 *   "date-local"  → "May 14, 2026"
 *   "time-local"  → "16:10 EDT"
 *
 * The viewer's actual locale is used; "EDT/EST" is whatever timeZoneName: 'short' returns.
 */
(function () {
  function tzAbbrev(d) {
    try {
      const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
        .formatToParts(d);
      const tz = parts.find(p => p.type === "timeZoneName");
      return tz ? tz.value : "";
    } catch (_) {
      return "";
    }
  }

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function fmtLocalHHMM(d) {
    return pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function fmtLocalDate(d) {
    return d.toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric"
    });
  }

  function fmtUtcYMDHM(d) {
    return d.getUTCFullYear() + "-" +
      pad(d.getUTCMonth() + 1) + "-" +
      pad(d.getUTCDate()) + " " +
      pad(d.getUTCHours()) + ":" +
      pad(d.getUTCMinutes());
  }

  function render(d, mode) {
    const tz = tzAbbrev(d);
    switch (mode) {
      case "date-local":
        return fmtLocalDate(d);
      case "time-local":
        return fmtLocalHHMM(d) + (tz ? " " + tz : "");
      case "local":
        return fmtLocalDate(d) + " " + fmtLocalHHMM(d) + (tz ? " " + tz : "");
      case "dual":
      default:
        return fmtUtcYMDHM(d) + " UTC · " +
          fmtLocalHHMM(d) + (tz ? " " + tz : "");
    }
  }

  function apply(root) {
    (root || document).querySelectorAll("time[data-tz]").forEach(function (el) {
      const iso = el.getAttribute("datetime");
      if (!iso) return;
      const d = new Date(iso);
      if (isNaN(d.getTime())) return;
      const mode = el.getAttribute("data-tz") || "dual";
      el.textContent = render(d, mode);
      el.setAttribute("title", iso); // hover shows ISO8601 UTC
    });
  }

  // Expose so dynamic JS (e.g. signals.html fetch handlers) can re-run after injecting <time>.
  window.tzApply = apply;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { apply(); });
  } else {
    apply();
  }
})();
