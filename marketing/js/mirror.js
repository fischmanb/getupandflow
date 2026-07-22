(function () {
  // billing toggles: buttons whose text is Monthly/Weekly inside bg-slate-100 pill containers
  var groups = [];
  document.querySelectorAll("button").forEach(function (b) {
    var t = b.textContent.trim();
    if (t === "Monthly" || t === "Weekly") groups.push(b);
  });
  function apply(period) {
    groups.forEach(function (b) {
      var on = (b.textContent.trim() === "Weekly") === (period === "weekly");
      ["bg-white", "shadow-sm"].forEach(function (c) { b.classList.toggle(c, on); });
      b.classList.toggle("text-slate-900", on);
      b.classList.toggle("text-slate-600", !on);
    });
    document.querySelectorAll("[data-price],[data-suffix],[data-price-compact]").forEach(function (el) {
      var v = el.dataset[period];
      if (v) el.textContent = v;
    });
    window.__billing = period;
  }
  groups.forEach(function (b) {
    b.addEventListener("click", function (e) { e.preventDefault(); apply(b.textContent.trim() === "Weekly" ? "weekly" : "monthly"); });
  });
  apply("monthly");

  // lead form
  var form = document.querySelector("form");
  if (form && document.getElementById("full_name")) {
    var status = document.createElement("p");
    status.className = "text-center text-sm mt-3";
    status.setAttribute("aria-live", "polite");
    form.appendChild(status);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var planRaw = (form.querySelector("input[name=plan]:checked") || {}).value || "Full Support";
      var payload = {
        full_name: document.getElementById("full_name").value,
        email: document.getElementById("email").value,
        notes: (document.getElementById("notes") || {}).value || "",
        plan: planRaw === "Focus Lite" ? "focus_lite" : "full_support",
        billing_period: window.__billing || "monthly"
      };
      status.textContent = "Sending\u2026";
      status.style.color = "#475569";
      fetch("https://api.getupandflow.co/api/leads/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (r.status === 201) { status.textContent = "Got it \u2014 we will reach out within 48 hours."; status.style.color = "#059669"; form.reset(); apply("monthly"); }
        else if (r.status === 429) { status.textContent = "Too many submissions from this network \u2014 try again later."; status.style.color = "#b45309"; }
        else { r.json().then(function (d) { status.textContent = Object.values(d).flat().join(" ") || "Please check the form and try again."; status.style.color = "#b91c1c"; }).catch(function () { status.textContent = "Please check the form and try again."; status.style.color = "#b91c1c"; }); }
      }).catch(function () { status.textContent = "Network error \u2014 please try again."; status.style.color = "#b91c1c"; });
    });
  }

  // founder bubble dismiss
  document.querySelectorAll("button").forEach(function (b) {
    if (b.querySelector("svg.lucide-x")) {
      b.addEventListener("click", function () {
        var root = b.closest(".fixed");
        if (root) root.style.display = "none";
      });
    }
  });

  // who-we-are photo -> video modal
  var photo = document.querySelector(".aspect-\\[4\\/3\\].cursor-pointer") || document.querySelector("div.cursor-pointer img[alt*=coach i]");
  var trigger = photo ? (photo.closest(".cursor-pointer") || photo) : null;
  if (trigger) {
    trigger.addEventListener("click", function () {
      var overlay = document.createElement("div");
      overlay.style.cssText = "position:fixed;inset:0;background:rgba(15,23,42,.8);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px";
      overlay.innerHTML = "<div style=\"position:relative;width:min(960px,100%);aspect-ratio:16/9\"><iframe src=\"https://player.vimeo.com/video/1133967200?autoplay=1\" style=\"width:100%;height:100%;border:0;border-radius:16px\" allow=\"autoplay; fullscreen; picture-in-picture\"></iframe></div>";
      overlay.addEventListener("click", function (e) { if (e.target === overlay) overlay.remove(); });
      document.addEventListener("keydown", function esc(e) { if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", esc); } });
      document.body.appendChild(overlay);
    });
  }
})();
