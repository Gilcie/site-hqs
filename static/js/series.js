(function () {
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

  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---- Read tracking (per-device, same store the reader writes to) ----
  function getReadSet() {
    try {
      var raw = localStorage.getItem("read_comics");
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  }

  function setReadSet(set) {
    try { localStorage.setItem("read_comics", JSON.stringify(set)); } catch (e) {}
  }

  function render(data) {
    var container = document.getElementById("issue-list");
    var comics = data.comics;

    if (!comics || comics.length === 0) {
      container.innerHTML = '<div class="empty-msg"><p>Nenhum volume encontrado.</p></div>';
      return;
    }

    var readSet = getReadSet();

    var html = '<div class="issue-grid">';
    for (var i = 0; i < comics.length; i++) {
      var c = comics[i];
      var coverUrl = c.ext !== ".pdf" ? "/comic/" + c.id + "/cover" : "";
      var isRead = !!readSet[c.id];

      html += '<div class="issue-card" data-id="' + c.id + '">';
      html += '<div class="issue-cover-wrap">';
      if (coverUrl) {
        html += '<img src="' + coverUrl + '" alt="" onerror="this.style.display=\'none\';this.parentNode.querySelector(\'.issue-cover-placeholder\').style.display=\'flex\'">';
      }
      html += '<div class="issue-cover-placeholder" style="display:' + (coverUrl ? 'none' : 'flex') + '">&#128218;</div>';
      html += '<div class="issue-read-badge' + (isRead ? ' is-read' : '') + '" data-toggle-read="' + c.id + '">&#10003;</div>';
      html += '</div>';
      html += '<div class="issue-card-title">' + escapeHtml(c.title) + '</div>';
      html += '</div>';
    }
    html += '</div>';
    container.innerHTML = html;
  }

  document.getElementById("issue-list").addEventListener("click", function (e) {
    var badgeId = e.target.getAttribute("data-toggle-read");
    if (badgeId) {
      e.stopPropagation();
      var readSet = getReadSet();
      if (readSet[badgeId]) delete readSet[badgeId];
      else readSet[badgeId] = true;
      setReadSet(readSet);
      e.target.className = "issue-read-badge" + (readSet[badgeId] ? " is-read" : "");
      return;
    }

    var card = e.target;
    while (card && !card.classList.contains("issue-card")) card = card.parentElement;
    if (!card) return;
    window.location.href = "/read/" + card.getAttribute("data-id");
  });

  xhr("/api/series/" + encodeURIComponent(SERIES_NAME), function (err, data) {
    var container = document.getElementById("issue-list");
    if (err) {
      container.innerHTML = '<div class="empty-msg"><p style="color:#e94560;">Erro ao carregar série.</p></div>';
      return;
    }
    render(data);
  });
})();
