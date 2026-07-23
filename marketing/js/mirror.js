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
    // Signup CTAs (hero + pricing cards) deep-link the app signup page with
    // the plan they sit on and the currently toggled billing interval.
    document.querySelectorAll("a[data-signup-plan]").forEach(function (a) {
      a.setAttribute(
        "href",
        "https://app.getupandflow.co/signup?plan=" +
          a.getAttribute("data-signup-plan") +
          "&interval=" +
          period
      );
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

  // who-we-are coach photo -> Cindy's video, swapped in place (original behavior)
  var trigger = [].slice.call(document.querySelectorAll("div")).filter(function (d) {
    var c = typeof d.className === "string" ? d.className : "";
    return c.indexOf("aspect-[4/3]") > -1 && c.indexOf("cursor-pointer") > -1;
  })[0] || null;
  if (trigger) {
    trigger.addEventListener("click", function () {
      if (trigger.dataset.playing) return;
      trigger.dataset.playing = "1";
      trigger.style.aspectRatio = "16/9";
      trigger.classList.remove("cursor-pointer");
      trigger.innerHTML = "<iframe src=\"https://player.vimeo.com/video/1134719805?badge=0&autopause=0&autoplay=1&app_id=58479\" style=\"width:100%;height:100%;border:0\" allow=\"autoplay; fullscreen; picture-in-picture\" allowfullscreen title=\"Meet a GUAF coach\"></iframe>";
    }, { once: false });
  }
  })();

// sticky header appears after scrolling past the hero brand row (mirrors original behavior)
(function () {
  var h = document.getElementById("site-header");
  if (!h) return;
  function onScroll() { h.style.display = window.scrollY > 80 ? "" : "none"; }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
})();

// FAQ accordion (single-open, mirrors Radix data-state behavior; chevron rotation is pure CSS)
(function () {
  var buttons = [].slice.call(document.querySelectorAll("button[aria-controls][data-state]"));
  if (!buttons.length) return;
  function setState(btn, open) {
    var region = document.getElementById(btn.getAttribute("aria-controls"));
    var item = btn.closest("[data-state][class*=border]");
    var st = open ? "open" : "closed";
    btn.setAttribute("data-state", st);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (item) item.setAttribute("data-state", st);
    if (region) { region.setAttribute("data-state", st); if (open) { region.removeAttribute("hidden"); region.style.height = "auto"; } else { region.setAttribute("hidden", ""); } }
  }
  buttons.forEach(function (b) { setState(b, false); });
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      var willOpen = b.getAttribute("data-state") !== "open";
      buttons.forEach(function (o) { setState(o, false); });
      if (willOpen) setState(b, true);
    });
  });
})();