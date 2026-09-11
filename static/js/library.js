(function () {
  var library = [];
  var activePublisher = ""; // "" = todas

  function xhr(url, cb) {
    var req = new XMLHttpRequest();
    req.open("GET", url, true);
    req.onreadystatechange = function () {
      if (req.readyState === 4) {
        if (req.status === 200) {
          try { cb(null, JSON.parse(req.responseText)); }
          catch (e) { cb(e, null); }
        } else {
          cb(new Error("HTTP " + req.status), null);
        }
      }
    };
    req.send();
  }

  function showToast(msg) {
    var t = document.getElementById("toast");
    t.textContent = msg;
    t.className = "toast show";
    setTimeout(function () { t.className = "toast"; }, 2200);
  }

  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---- Render series grid ----
  function renderLibrary(data) {
    var container = document.getElementById("library");
    if (!data || data.length === 0) {
      container.innerHTML = '<div class="empty-msg"><p>Nenhuma HQ encontrada.</p><p style="margin-top:10px;font-size:13px;">Coloque seus arquivos .cbz, .cbr ou .pdf<br>na pasta <strong>comics/</strong> do servidor.</p></div>';
      return;
    }

    var html = '<div class="series-grid">';
    for (var i = 0; i < data.length; i++) {
      var s = data[i];
      var coverId = s.cover_id || "";
      var coverUrl = coverId ? "/comic/" + coverId + "/cover" : "";
      var label = s.count === 1 ? "1 vol." : s.count + " vols.";
      var encodedName = encodeURIComponent(s.series);

      html += '<div class="series-card" data-series="' + encodedName + '">';
      html += '<div class="series-cover-wrap">';
      if (coverUrl) {
        html += '<img src="' + coverUrl + '" alt=""'
          + ' onerror="this.style.display=\'none\';this.parentNode.querySelector(\'.series-cover-placeholder\').style.display=\'flex\'">';
      }
      html += '<div class="series-cover-placeholder" style="display:' + (coverUrl ? 'none' : 'flex') + '">&#128218;</div>';
      html += '<span class="series-count-badge">' + label + '</span>';
      html += '</div>';
      html += '<div class="series-card-info"><div class="series-card-name">' + escapeHtml(s.series) + '</div></div>';
      html += '</div>';
    }
    html += '</div>';
    container.innerHTML = html;
  }

  function applyFilters(query) {
    var q = (query || "").toLowerCase();
    var result = library.filter(function (s) {
      if (activePublisher && s.publisher !== activePublisher) return false;
      if (!q) return true;
      if (s.series.toLowerCase().indexOf(q) !== -1) return true;
      for (var j = 0; j < s.comics.length; j++) {
        if (s.comics[j].title.toLowerCase().indexOf(q) !== -1) return true;
      }
      return false;
    });
    renderLibrary(result);
  }

  function loadLibrary() {
    var container = document.getElementById("library");
    container.innerHTML = '<div class="loading"><div class="loading-spinner"></div><p>Carregando biblioteca...</p></div>';
    xhr("/api/library", function (err, data) {
      if (err) {
        container.innerHTML = '<div class="empty-msg"><p>Erro ao carregar a biblioteca.</p></div>';
        return;
      }
      library = data;
      applyFilters(document.getElementById("search-input").value);
      loadPublishers();
    });
  }

  // ---- Publisher chips ----
  function loadPublishers() {
    xhr("/api/publishers", function (err, pubs) {
      if (err || !pubs || pubs.length === 0) return;
      var chips = document.getElementById("publisher-chips");
      var html = '<button class="chip' + (activePublisher === "" ? " chip-active" : "") + '" data-pub="">Todas</button>';
      for (var i = 0; i < pubs.length; i++) {
        var p = pubs[i];
        html += '<button class="chip' + (activePublisher === p ? " chip-active" : "") + '" data-pub="' + escapeHtml(p) + '">' + escapeHtml(p) + '</button>';
      }
      chips.innerHTML = html;
    });
  }

  // ---- Drawer open/close ----
  var drawer = document.getElementById("filter-drawer");
  var backdrop = document.getElementById("drawer-backdrop");

  function openDrawer() {
    drawer.className = "filter-drawer open";
    backdrop.className = "drawer-backdrop open";
  }

  function closeDrawer() {
    drawer.className = "filter-drawer";
    backdrop.className = "drawer-backdrop";
  }

  document.getElementById("btn-filter").addEventListener("click", openDrawer);
  backdrop.addEventListener("click", closeDrawer);

  // Chip selection
  document.getElementById("publisher-chips").addEventListener("click", function (e) {
    var btn = e.target;
    if (!btn.classList.contains("chip")) return;

    // Update active chip visual
    var chips = document.querySelectorAll(".chip");
    for (var i = 0; i < chips.length; i++) chips[i].className = "chip";
    btn.className = "chip chip-active";

    activePublisher = btn.getAttribute("data-pub");
    applyFilters(document.getElementById("search-input").value);
    closeDrawer();
  });

  // ---- Navigate to series ----
  document.getElementById("library").addEventListener("click", function (e) {
    var card = e.target;
    while (card && !card.classList.contains("series-card")) card = card.parentElement;
    if (!card) return;
    var encoded = card.getAttribute("data-series");
    window.location.href = "/series/" + decodeURIComponent(encoded);
  });

  document.getElementById("btn-refresh").addEventListener("click", function () {
    showToast("Atualizando...");
    loadLibrary();
  });

  var searchTimeout = null;
  document.getElementById("search-input").addEventListener("input", function () {
    var q = this.value;
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(function () { applyFilters(q); }, 250);
  });

  // ---- Install banner ----
  (function () {
    var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    var isStandalone = window.navigator.standalone === true;
    var dismissed = false;
    try { dismissed = !!localStorage.getItem("install_dismissed"); } catch(e){}
    if (isIOS && !isStandalone && !dismissed) {
      var banner = document.getElementById("install-banner");
      if (banner) banner.style.display = "-webkit-box";
      var closeBtn = document.getElementById("btn-install-close");
      if (closeBtn) closeBtn.addEventListener("click", function () {
        banner.style.display = "none";
        try { localStorage.setItem("install_dismissed", "1"); } catch(e){}
      });
    }
  })();

  // ---- Continue reading ----
  (function () {
    var last = null;
    try {
      var raw = localStorage.getItem("last_read");
      if (raw) last = JSON.parse(raw);
    } catch (e) {}
    if (!last || !last.id) return;

    var el = document.getElementById("continue-reading");
    if (!el) return;

    el.innerHTML =
      '<div class="continue-card" id="continue-card">' +
      '<img class="continue-card-cover" src="/comic/' + last.id + '/cover" alt=""' +
      ' onerror="this.style.display=\'none\'">' +
      '<div class="continue-card-info">' +
      '<div class="continue-card-label">Continuar lendo</div>' +
      '<div class="continue-card-title">' + escapeHtml(last.title || "") + '</div>' +
      '</div></div>';

    document.getElementById("continue-card").addEventListener("click", function () {
      window.location.href = "/read/" + last.id;
    });
  })();

  loadLibrary();
})();
