(function () {
  "use strict";

  var API_URL = "https://api.getupandflow.co/api/leads/";
  var VIMEO_ID = "1133967200";

  // --- Founder video bubble -----------------------------------------------
  // The looping preview is injected after load so the Vimeo embed never
  // competes with first paint; without JS the bubble shows a play icon.
  var bubble = document.getElementById("video-bubble");
  var bubbleSlot = document.getElementById("bubble-video-slot");

  window.addEventListener("load", function () {
    if (!bubbleSlot || !bubble || bubble.hidden) return;
    var iframe = document.createElement("iframe");
    iframe.src =
      "https://player.vimeo.com/video/" +
      VIMEO_ID +
      "?background=1&autoplay=1&muted=1&loop=1&autopause=0";
    iframe.title = "Hear from our founder (preview)";
    iframe.setAttribute("allow", "autoplay; fullscreen; picture-in-picture");
    iframe.setAttribute("aria-hidden", "true");
    iframe.tabIndex = -1;
    // Oversize and center the 16:9 player so it covers the circular bubble.
    iframe.className =
      "pointer-events-none absolute left-1/2 top-1/2 h-full w-[178%] max-w-none -translate-x-1/2 -translate-y-1/2";
    bubbleSlot.classList.add("relative");
    bubbleSlot.appendChild(iframe);
  });

  var dismissButton = document.getElementById("video-bubble-dismiss");
  if (dismissButton && bubble) {
    dismissButton.addEventListener("click", function () {
      bubble.hidden = true;
      var preview = bubbleSlot && bubbleSlot.querySelector("iframe");
      if (preview) preview.remove();
    });
  }

  // --- Founder video modal ------------------------------------------------
  var modal = document.getElementById("video-modal");
  var modalIframe = document.getElementById("video-modal-iframe");
  var modalClose = document.getElementById("video-modal-close");

  function openModal() {
    if (!modal || !modalIframe) return;
    modalIframe.src = "https://player.vimeo.com/video/" + VIMEO_ID + "?autoplay=1";
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    document.body.style.overflow = "hidden";
    if (modalClose) modalClose.focus();
  }

  function closeModal() {
    if (!modal || !modalIframe) return;
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    modalIframe.src = "about:blank";
    document.body.style.overflow = "";
  }

  document.querySelectorAll("[data-video-open]").forEach(function (trigger) {
    trigger.addEventListener("click", openModal);
  });
  if (modalClose) modalClose.addEventListener("click", closeModal);
  if (modal) {
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeModal();
    });
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeModal();
  });

  // --- Lead form ----------------------------------------------------------
  var form = document.getElementById("lead-form");
  var statusEl = document.getElementById("form-status");

  function showStatus(message, ok) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.classList.remove("hidden", "text-emerald-600", "text-red-600");
    statusEl.classList.add(ok ? "text-emerald-600" : "text-red-600");
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();

      var fullName = form.elements.full_name.value.trim();
      var email = form.elements.email.value.trim();
      if (!fullName) {
        showStatus("Please enter your name.", false);
        form.elements.full_name.focus();
        return;
      }
      if (!email || email.indexOf("@") === -1) {
        showStatus("Please enter a valid email address.", false);
        form.elements.email.focus();
        return;
      }

      var payload = {
        full_name: fullName,
        email: email,
        plan: form.elements.plan.value,
        billing_period: form.elements.billing_period.value,
        notes: form.elements.notes.value.trim(),
      };

      var submitButton = form.querySelector('button[type="submit"]');
      submitButton.disabled = true;
      showStatus("Sending…", true);

      fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (response) {
          if (response.ok) {
            form.reset();
            showStatus(
              "You're on the list! We'll reach out within 48 hours to schedule your onboarding call.",
              true
            );
            return;
          }
          if (response.status === 429) {
            showStatus(
              "Looks like you've already submitted recently. Hang tight — we'll be in touch soon.",
              false
            );
            return;
          }
          return response
            .json()
            .catch(function () {
              return {};
            })
            .then(function (data) {
              var firstError =
                data && typeof data === "object"
                  ? Object.values(data).flat()[0]
                  : null;
              showStatus(
                firstError ||
                  "Something went wrong. Please try again, or email hello@getupandflow.co.",
                false
              );
            });
        })
        .catch(function () {
          showStatus(
            "We couldn't reach the server. Please try again, or email hello@getupandflow.co.",
            false
          );
        })
        .finally(function () {
          submitButton.disabled = false;
        });
    });
  }
})();

// --- Billing period: one state, synced across pricing cards and the signup form ---
(function () {
  var ACTIVE = ["bg-white", "text-slate-900", "shadow-sm"];
  var IDLE = ["text-slate-600"];
  function apply(period) {
    document.querySelectorAll(".billing-toggle button").forEach(function (btn) {
      var on = btn.dataset.billing === period;
      ACTIVE.forEach(function (c) { btn.classList.toggle(c, on); });
      IDLE.forEach(function (c) { btn.classList.toggle(c, !on); });
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    document.querySelectorAll("[data-price],[data-suffix],[data-price-compact]").forEach(function (el) {
      var v = el.dataset[period];
      if (v) el.textContent = v;
    });
    var radio = document.querySelector('input[name="billing_period"][value="' + period + '"]');
    if (radio && !radio.checked) radio.checked = true;
  }
  document.querySelectorAll(".billing-toggle button").forEach(function (btn) {
    btn.addEventListener("click", function () { apply(btn.dataset.billing); });
  });
  document.querySelectorAll('input[name="billing_period"]').forEach(function (r) {
    r.addEventListener("change", function () { if (r.checked) apply(r.value); });
  });
  apply("monthly");
})();
