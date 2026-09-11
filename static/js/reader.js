(function () {
  var pages = [];
  var current = 0;
  var comicType = "";
  var nextComic = null;
  var prevComic = null;
  var onEndScreen = false;
  var uiVisible = true;
  var uiTimeout = null;
  var swipeStartX = 0;
  var swipeStartY = 0;
  var swipeThreshold = 50;
  var isPinching = false;
  var baseInnerWidth = 0; // detectar zoom pelo narrowing de window.innerWidth
  var readerMode = "single"; // "single" | "vertical"

  var elMain    = document.getElementById("reader-main");
  var elHeader  = document.getElementById("reader-header");
  var elFooter  = document.getElementById("reader-footer");
  var elCounter = document.getElementById("page-counter");
  var elFill    = document.getElementById("progress-fill");
  var elInput   = document.getElementById("page-input");
  var elToast   = document.getElementById("toast");
  var elBtnMode = document.getElementById("btn-mode");

  // ---- Toast ----
  function showToast(msg) {
    elToast.textContent = msg;
    elToast.className = "toast show";
    setTimeout(function () { elToast.className = "toast"; }, 2000);
  }

  function escHtml(s) {
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  var cinemaMode = false;

  // ---- UI visibility toggle ----
  function showUI() {
    if (cinemaMode) return;
    uiVisible = true;
    elHeader.className = "reader-header";
    elFooter.className = "reader-footer";
    clearTimeout(uiTimeout);
    uiTimeout = setTimeout(hideUI, 4000);
  }

  function hideUI() {
    uiVisible = false;
    elHeader.className = "reader-header hidden";
    elFooter.className = "reader-footer hidden";
  }

  function toggleUI() {
    if (cinemaMode) { exitCinema(); return; }
    if (uiVisible) hideUI();
    else showUI();
  }

  var elBtnFullscreen = document.getElementById("btn-fullscreen");

  function enterCinema() {
    cinemaMode = true;
    clearTimeout(uiTimeout);
    hideUI();
    var el = document.documentElement;
    if (el.requestFullscreen) el.requestFullscreen();
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
    showToast("Toque no centro para sair");
  }

  function exitCinema() {
    cinemaMode = false;
    elBtnFullscreen.innerHTML = "&#9974;";
    showUI();
    if (document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
  }

  // ---- Counter & progress ----
  function updateCounter(index) {
    if (pages.length === 0) return;
    var num = index + 1;
    elCounter.textContent = num + " / " + pages.length;
    elInput.value = num;
    elInput.max = pages.length;
    var pct = pages.length > 1 ? (index / (pages.length - 1)) * 100 : 100;
    elFill.style.width = pct + "%";
  }

  // ---- Save/restore progress ----
  function saveProgress(index) {
    try { localStorage.setItem("progress_" + COMIC_ID, index); } catch (e) {}
  }

  function loadProgress() {
    try {
      var v = localStorage.getItem("progress_" + COMIC_ID);
      if (v !== null) return parseInt(v, 10) || 0;
    } catch (e) {}
    return 0;
  }

  // ---- "Continue reading" + "read" tracking (per-device, like progress) ----
  function saveLastRead() {
    try {
      localStorage.setItem("last_read", JSON.stringify({ id: COMIC_ID, title: COMIC_TITLE, ts: Date.now() }));
    } catch (e) {}
  }

  function markAsRead() {
    try {
      var raw = localStorage.getItem("read_comics");
      var set = raw ? JSON.parse(raw) : {};
      set[COMIC_ID] = true;
      localStorage.setItem("read_comics", JSON.stringify(set));
    } catch (e) {}
  }

  // ---- Reader mode (single page vs vertical scroll) ----
  function loadReaderMode() {
    try {
      var v = localStorage.getItem("reader_mode");
      if (v === "vertical" || v === "single") return v;
    } catch (e) {}
    return "single";
  }

  function saveReaderMode(mode) {
    try { localStorage.setItem("reader_mode", mode); } catch (e) {}
  }

  function updateModeButton() {
    if (!elBtnMode) return;
    elBtnMode.innerHTML = readerMode === "vertical" ? "&#9776;" : "&#8597;";
    elBtnMode.title = readerMode === "vertical" ? "Mudar para modo página" : "Mudar para rolagem vertical";
  }

  function switchMode(mode) {
    if (mode === readerMode) return;
    var savedIndex = readerMode === "vertical" ? vscrollCurrentIndex() : current;
    if (readerMode === "vertical") teardownVerticalReader();
    readerMode = mode;
    saveReaderMode(mode);
    updateModeButton();
    if (comicType === "cbz") {
      if (readerMode === "vertical") buildVerticalReader(savedIndex);
      else showPage(savedIndex);
    }
  }

  // ---- End screen markup (shared by single-page and vertical modes) ----
  function buildEndScreenInner() {
    var inner = '<div class="end-screen-inner">';
    inner += '<div class="end-screen-check">&#10003;</div>';
    inner += '<div class="end-screen-done">Fim do volume</div>';
    inner += '<div class="end-screen-title">' + escHtml(COMIC_TITLE) + '</div>';

    if (nextComic) {
      inner += '<div class="end-screen-next-label">Próximo na série</div>';
      inner += '<div class="end-screen-next-title">' + escHtml(nextComic.title) + '</div>';
      inner += '<button class="end-screen-btn" id="btn-end-next">Próximo volume &#8594;</button>';
    }

    inner += '<button class="end-screen-btn end-screen-btn-outline" id="btn-end-back">&#8592; Voltar à última página</button>';
    inner += '<a class="end-screen-library" href="/">Ver biblioteca</a>';
    inner += '</div>';
    return inner;
  }

  function wireEndScreenButtons(root, onBack) {
    var btnNext = root.querySelector("#btn-end-next");
    if (btnNext) {
      btnNext.addEventListener("click", function () {
        window.location.href = "/read/" + nextComic.id;
      });
    }
    root.querySelector("#btn-end-back").addEventListener("click", onBack);
  }

  // ---- End screen (single-page mode) ----
  function showEndScreen() {
    onEndScreen = true;
    markAsRead();
    elMain.innerHTML = "";

    var wrap = document.createElement("div");
    wrap.className = "end-screen";
    wrap.innerHTML = buildEndScreenInner();
    elMain.appendChild(wrap);

    wireEndScreenButtons(wrap, hideEndScreen);

    // Oculta footer (não faz sentido na tela de fim)
    elFooter.className = "reader-footer hidden";
    elHeader.className = "reader-header";
    clearTimeout(uiTimeout);
  }

  function hideEndScreen() {
    onEndScreen = false;
    showPage(pages.length - 1);
  }

  // ---- Image page renderer (single-page mode) ----
  function buildImagePage(url) {
    var wrap = document.createElement("div");
    wrap.className = "page-img";
    var img = document.createElement("img");
    img.src = url;
    wrap.appendChild(img);
    return wrap;
  }

  function isZoomedIn() {
    return baseInnerWidth > 0 && window.innerWidth < baseInnerWidth * 0.95;
  }

  function showPage(index) {
    if (index < 0) index = 0;
    if (index >= pages.length) index = pages.length - 1;
    current = index;
    onEndScreen = false;

    elMain.innerHTML = "";

    var page = buildImagePage(pages[current]);

    var prev = document.createElement("div");
    prev.className = "touch-prev";
    prev.addEventListener("click", function (e) {
      e.stopPropagation();
      if (isZoomedIn()) return; // não muda página com zoom ativo
      goTo(current - 1);
    });

    var next = document.createElement("div");
    next.className = "touch-next";
    next.addEventListener("click", function (e) {
      e.stopPropagation();
      if (isZoomedIn()) return; // não muda página com zoom ativo
      goTo(current + 1);
    });

    page.addEventListener("click", function () {
      toggleUI();
    });

    elMain.appendChild(page);
    elMain.appendChild(prev);
    elMain.appendChild(next);

    updateCounter(current);
    saveProgress(current);
    showUI();
  }

  function goTo(index) {
    if (index < 0) {
      showToast("Primeira página");
      return;
    }
    if (index >= pages.length) {
      // Passou da última página — mostra tela de fim
      showEndScreen();
      return;
    }
    showPage(index);
  }

  // ---- Vertical scroll mode (virtualized: only pages near the viewport
  // keep a real <img> mounted, to stay usable on old/low-memory devices) ----
  var vscrollEl = null;
  var vslots = [];      // { el, index, mounted, measured }
  var vEndSlotEl = null;
  var vRafPending = false;
  var vLastReportedIndex = -1;

  function vscrollGuessHeight() {
    // Rough placeholder until the real image loads and we measure it.
    var w = elMain.clientWidth || window.innerWidth;
    return Math.round(w * 1.5);
  }

  function vscrollCurrentIndex() {
    return vLastReportedIndex >= 0 ? vLastReportedIndex : current;
  }

  function buildVerticalReader(startIndex) {
    elMain.innerHTML = "";
    onEndScreen = false;

    vscrollEl = document.createElement("div");
    vscrollEl.className = "vscroll";

    vslots = [];
    for (var i = 0; i < pages.length; i++) {
      var slotEl = document.createElement("div");
      slotEl.className = "vscroll-slot";
      slotEl.style.height = vscrollGuessHeight() + "px";
      vscrollEl.appendChild(slotEl);
      vslots.push({ el: slotEl, index: i, mounted: false, measured: false });
    }

    vEndSlotEl = document.createElement("div");
    vEndSlotEl.className = "vscroll-end-slot";
    vscrollEl.appendChild(vEndSlotEl);

    elMain.appendChild(vscrollEl);
    // Reserve one full screen at the end for the end-of-volume screen,
    // measured only after the container is in the DOM.
    vEndSlotEl.style.height = (vscrollEl.clientHeight || window.innerHeight) + "px";

    vscrollEl.addEventListener("click", function (e) {
      if (e.target === vscrollEl) toggleUI();
    });
    vscrollEl.addEventListener("scroll", onVscrollScroll, { passive: true });

    // Jump to saved position without animating, then run one mount pass.
    var target = vslots[Math.min(startIndex, vslots.length - 1)];
    if (target) vscrollEl.scrollTop = target.el.offsetTop;
    vscrollTick();
  }

  function teardownVerticalReader() {
    if (!vscrollEl) return;
    vscrollEl.removeEventListener("scroll", onVscrollScroll);
    vscrollEl = null;
    vslots = [];
    vEndSlotEl = null;
    vLastReportedIndex = -1;
  }

  function onVscrollScroll() {
    if (vRafPending) return;
    vRafPending = true;
    var raf = window.requestAnimationFrame || function (cb) { setTimeout(cb, 16); };
    raf(function () {
      vRafPending = false;
      vscrollTick();
    });
  }

  function mountSlot(slot) {
    if (slot.mounted) return;
    slot.mounted = true;
    var img = document.createElement("img");
    img.addEventListener("load", function () {
      if (!slot.measured) {
        slot.measured = true;
        var w = elMain.clientWidth || window.innerWidth;
        var ratio = img.naturalHeight / (img.naturalWidth || 1);
        slot.el.style.height = Math.round(w * ratio) + "px";
      }
    });
    img.src = pages[slot.index];
    slot.el.appendChild(img);
  }

  function unmountSlot(slot) {
    if (!slot.mounted) return;
    slot.mounted = false;
    slot.el.innerHTML = "";
  }

  function vscrollTick() {
    if (!vscrollEl) return;
    var containerHeight = vscrollEl.clientHeight;
    var buffer = containerHeight; // one screen of buffer above/below
    var vsTop = vscrollEl.getBoundingClientRect().top;

    var reportedIndex = -1;
    for (var i = 0; i < vslots.length; i++) {
      var slot = vslots[i];
      var r = slot.el.getBoundingClientRect();
      var top = r.top - vsTop;
      var bottom = r.bottom - vsTop;

      if (bottom > -buffer && top < containerHeight + buffer) {
        mountSlot(slot);
      } else {
        unmountSlot(slot);
      }

      if (reportedIndex === -1 && bottom > 0) {
        reportedIndex = i;
      }
    }

    if (reportedIndex !== -1 && reportedIndex !== vLastReportedIndex) {
      vLastReportedIndex = reportedIndex;
      current = reportedIndex;
      updateCounter(reportedIndex);
      saveProgress(reportedIndex);
    }

    // End-of-volume screen: lives as the last item in the same scroll list.
    var endRect = vEndSlotEl.getBoundingClientRect();
    var endTop = endRect.top - vsTop;
    var showingEnd = endTop < containerHeight * 0.6;
    if (showingEnd && !onEndScreen) {
      onEndScreen = true;
      markAsRead();
      var endInner = document.createElement("div");
      endInner.className = "end-screen";
      endInner.innerHTML = buildEndScreenInner();
      vEndSlotEl.appendChild(endInner);
      wireEndScreenButtons(endInner, function () {
        scrollVerticalTo(pages.length - 1);
      });
      elFooter.className = "reader-footer hidden";
    } else if (!showingEnd && onEndScreen) {
      onEndScreen = false;
      vEndSlotEl.innerHTML = "";
      elFooter.className = uiVisible ? "reader-footer" : "reader-footer hidden";
    }
  }

  function scrollVerticalTo(index) {
    if (!vscrollEl) return;
    var slot = vslots[Math.max(0, Math.min(index, vslots.length - 1))];
    if (slot) vscrollEl.scrollTop = slot.el.offsetTop;
  }

  // ---- PDF renderer ----
  function showPDF(url) {
    elHeader.className = "reader-header";
    elFooter.style.display = "none";
    if (elBtnMode) elBtnMode.style.display = "none";
    var wrap = document.createElement("div");
    wrap.className = "pdf-wrap";
    var frame = document.createElement("iframe");
    frame.src = url;
    frame.setAttribute("allowfullscreen", "true");
    wrap.appendChild(frame);
    elMain.innerHTML = "";
    elMain.appendChild(wrap);
  }

  // ---- Swipe detection (single-page mode only; vertical mode scrolls natively) ----
  elMain.addEventListener("touchstart", function (e) {
    if (e.touches.length >= 2) {
      isPinching = true;
    } else {
      // Só registra início de swipe se não veio de pinch recente
      if (!isPinching) {
        swipeStartX = e.touches[0].clientX;
        swipeStartY = e.touches[0].clientY;
      }
    }
  }, false);

  elMain.addEventListener("touchmove", function (e) {
    if (e.touches.length >= 2) isPinching = true;
  }, false);

  elMain.addEventListener("touchend", function (e) {
    if (comicType !== "cbz" || readerMode !== "single") return;

    // Se ainda há dedos na tela, aguarda o último levantar
    if (e.touches.length > 0) return;

    // Verifica se está com zoom ativo (window.innerWidth diminui quando zoomed)
    var isZoomed = baseInnerWidth > 0 && window.innerWidth < baseInnerWidth * 0.95;

    if (isPinching || isZoomed) {
      isPinching = false;
      return;
    }

    var dx = e.changedTouches[0].clientX - swipeStartX;
    var dy = e.changedTouches[0].clientY - swipeStartY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > swipeThreshold) {
      if (onEndScreen) {
        if (dx > 0) hideEndScreen();
        else if (nextComic) window.location.href = "/read/" + nextComic.id;
      } else {
        if (dx < 0) goTo(current + 1);
        else goTo(current - 1);
      }
    }
  }, false);

  // ---- Keyboard ----
  document.addEventListener("keydown", function (e) {
    if (comicType !== "cbz") return;

    if (readerMode === "vertical") {
      if (e.keyCode === 38 || e.keyCode === 37) vscrollEl.scrollBy(0, -Math.round(vscrollEl.clientHeight * 0.9));
      if (e.keyCode === 40 || e.keyCode === 39) vscrollEl.scrollBy(0, Math.round(vscrollEl.clientHeight * 0.9));
      return;
    }

    if (onEndScreen) {
      if (e.keyCode === 37 || e.keyCode === 38) hideEndScreen();
      if ((e.keyCode === 39 || e.keyCode === 40) && nextComic) window.location.href = "/read/" + nextComic.id;
      return;
    }
    if (e.keyCode === 37 || e.keyCode === 38) goTo(current - 1);
    if (e.keyCode === 39 || e.keyCode === 40) goTo(current + 1);
  });

  // ---- Page jump ----
  document.getElementById("btn-go").addEventListener("click", function () {
    var v = parseInt(elInput.value, 10);
    if (isNaN(v)) return;
    if (readerMode === "vertical") scrollVerticalTo(v - 1);
    else goTo(v - 1);
  });

  elInput.addEventListener("keydown", function (e) {
    if (e.keyCode === 13) {
      var v = parseInt(this.value, 10);
      if (isNaN(v)) return;
      if (readerMode === "vertical") scrollVerticalTo(v - 1);
      else goTo(v - 1);
    }
  });

  // ---- Fullscreen / Cinema mode ----
  document.getElementById("btn-fullscreen").addEventListener("click", function () {
    if (cinemaMode) exitCinema();
    else enterCinema();
  });

  // ---- Reading mode toggle ----
  if (elBtnMode) {
    elBtnMode.addEventListener("click", function () {
      switchMode(readerMode === "vertical" ? "single" : "vertical");
    });
  }

  // ---- Load comic data ----
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

  function init() {
    xhr("/api/comic/" + COMIC_ID, function (err, data) {
      if (err) {
        elMain.innerHTML = '<div class="empty-msg"><p style="color:#e94560;">Erro ao carregar HQ.</p><p style="margin-top:8px;font-size:13px;">' + err.message + '</p></div>';
        return;
      }

      comicType = data.type;
      nextComic = data.next || null;
      prevComic = data.prev || null;
      saveLastRead();

      if (data.type === "pdf") {
        showPDF(data.url);
        return;
      }

      if (data.type === "cbz") {
        pages = data.pages;
        if (pages.length === 0) {
          elMain.innerHTML = '<div class="empty-msg"><p>Nenhuma página encontrada neste arquivo.</p></div>';
          return;
        }

        readerMode = loadReaderMode();
        updateModeButton();

        var saved = loadProgress();
        if (saved >= pages.length) saved = 0;

        if (readerMode === "vertical") {
          buildVerticalReader(saved);
          return;
        }

        function preload(index) {
          if (index < pages.length) {
            var img = new Image();
            img.src = pages[index];
          }
        }

        showPage(saved);
        preload(saved + 1);

        var _goTo = goTo;
        goTo = function (index) {
          _goTo(index);
          if (!onEndScreen) preload(index + 1);
        };

        return;
      }

      elMain.innerHTML = '<div class="empty-msg"><p>Formato não suportado.</p></div>';
    });
  }

  // Salva largura original para detectar zoom
  baseInnerWidth = window.innerWidth;
  window.addEventListener("resize", function () {
    // Se voltou ao tamanho original, reseta flag de pinch
    if (window.innerWidth >= baseInnerWidth * 0.95) isPinching = false;
  });

  init();
  showUI();
})();
