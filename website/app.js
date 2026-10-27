// YouTube Automation Studio — Download & Auto-Update Portal Client Script
(function () {
  const FALLBACK_MANIFEST = {
    version: "0.1.0",
    channel: "stable",
    published_at: "2026-10-27",
    headline: "Mobile-Responsive Dark Studio, Preconfigured MCP Hub (vidIQ, TubeBuddy, Suno) & Harmonic Mixing Engine",
    channels: {
      stable: {
        version: "0.1.0",
        published_at: "2026-10-27",
        headline: "Stable Release v0.1.0 — Full Production Studio & Preconfigured MCP Hub"
      },
      beta: {
        version: "0.2.0-beta.1",
        published_at: "2026-10-27",
        headline: "Beta Channel v0.2.0-beta.1 — Multi-Track Stem Separation & Delta Auto-Updater Preview"
      }
    }
  };

  function getSystemScheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function getStoredScheme() {
    try {
      const val = localStorage.getItem("color-scheme");
      return val === "light" || val === "dark" ? val : null;
    } catch {
      return null;
    }
  }

  function getRenderedScheme() {
    return getStoredScheme() || getSystemScheme();
  }

  function syncThemeMetaAndButton() {
    const meta = document.querySelector('meta[name="color-scheme"]');
    const stored = getStoredScheme();
    if (meta) {
      meta.content = stored ?? "light dark";
    }
    const rendered = getRenderedScheme();
    const iconEl = document.getElementById("theme-toggle-icon");
    const labelEl = document.getElementById("theme-toggle-label");
    if (iconEl && labelEl) {
      if (rendered === "dark") {
        iconEl.textContent = "☀️";
        labelEl.textContent = "Light";
      } else {
        iconEl.textContent = "🌙";
        labelEl.textContent = "Dark";
      }
    }
  }

  function setupColorSchemeToggle() {
    const toggleBtn = document.getElementById("theme-toggle-btn");
    const mql = window.matchMedia("(prefers-color-scheme: dark)");

    // Update UI when OS color scheme changes (never delete stored override here)
    mql.addEventListener("change", () => {
      syncThemeMetaAndButton();
    });

    // Stay in sync across tabs
    window.addEventListener("storage", (e) => {
      if (e.key === "color-scheme") {
        syncThemeMetaAndButton();
      }
    });

    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const currentRendered = getRenderedScheme();
        const target = currentRendered === "dark" ? "light" : "dark";
        const system = getSystemScheme();
        try {
          if (target === system) {
            localStorage.removeItem("color-scheme");
          } else {
            localStorage.setItem("color-scheme", target);
          }
        } catch {}
        const meta = document.querySelector('meta[name="color-scheme"]');
        if (meta) {
          meta.content = target === system ? "light dark" : target;
        }
        syncThemeMetaAndButton();
      });
    }

    syncThemeMetaAndButton();
  }

  function detectVisitorPlatformKey() {
    const ua = navigator.userAgent.toLowerCase();
    const platform = (navigator.platform || "").toLowerCase();
    if (ua.includes("mac") || platform.includes("mac")) {
      return "macos_arm64";
    }
    if (ua.includes("win") || platform.includes("win")) {
      return "windows_x64";
    }
    if (ua.includes("linux")) {
      return "linux_x64";
    }
    return "macos_arm64";
  }

  function highlightDetectedOS() {
    const detected = detectVisitorPlatformKey();
    const cards = document.querySelectorAll("[data-platform]");
    cards.forEach((card) => {
      if (card.getAttribute("data-platform") === detected) {
        card.classList.add("recommended-os");
        const badge = card.querySelector(".os-detected-badge");
        if (badge) {
          badge.textContent = "Recommended for Your Device";
          badge.style.display = "inline-block";
        }
      }
    });

    const primaryBtn = document.getElementById("hero-primary-download");
    const labels = {
      macos_arm64: "⬇ Download for macOS (Apple Silicon .dmg)",
      macos_x64: "⬇ Download for macOS (Intel .dmg)",
      windows_x64: "⬇ Download for Windows 10/11 (.exe)",
      linux_x64: "⬇ Download for Linux (.AppImage)"
    };
    if (primaryBtn && labels[detected]) {
      primaryBtn.textContent = labels[detected];
    }
  }

  function setupChannelSwitcher(manifest) {
    const btnStable = document.getElementById("btn-channel-stable");
    const btnBeta = document.getElementById("btn-channel-beta");
    const versionLabel = document.getElementById("active-channel-version");
    const headlineLabel = document.getElementById("active-channel-headline");

    function applyChannel(chKey) {
      const chData = (manifest.channels && manifest.channels[chKey]) || FALLBACK_MANIFEST.channels[chKey];
      if (!chData) return;
      if (btnStable && btnBeta) {
        btnStable.classList.toggle("active", chKey === "stable");
        btnBeta.classList.toggle("active", chKey === "beta");
      }
      if (versionLabel) {
        versionLabel.textContent = `v${chData.version} (${chKey.toUpperCase()})`;
      }
      if (headlineLabel) {
        headlineLabel.textContent = chData.headline;
      }
    }

    if (btnStable) btnStable.addEventListener("click", () => applyChannel("stable"));
    if (btnBeta) btnBeta.addEventListener("click", () => applyChannel("beta"));
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupColorSchemeToggle();
    highlightDetectedOS();
    fetch("./releases.json")
      .then((r) => (r.ok ? r.json() : FALLBACK_MANIFEST))
      .then((manifest) => setupChannelSwitcher(manifest))
      .catch(() => setupChannelSwitcher(FALLBACK_MANIFEST));
  });
})();
