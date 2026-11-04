(function () {
  "use strict";

  var VALID_HASHES = ["#config", "#config-app3", "#config-custom", "#workbench", "#workbench-3", "#lightbox"];

  var PLACEMENTS_DB = {
    "appstore:single": [
      { group: "华为", items: [{ id: "as-hw-1", name: "单图", size: "984×422", checked: true }] },
      { group: "OPPO", items: [{ id: "as-oppo-1", name: "横版大图", size: "1280×720", checked: true, ctaMode: "none" }] },
      { group: "小米", items: [
        { id: "as-xm-1", name: "大图", size: "960×540", checked: true },
        { id: "as-xm-s", name: "小图", size: "480×320", checked: false }
      ] },
      { group: "荣耀", items: [{ id: "as-ry-1", name: "大图文", size: "1280×720", checked: false }] }
    ],
    "appstore:double": [
      { group: "OPPO", items: [{ id: "as-oppo-2", name: "竖版两图", size: "474×768", checked: true }] },
      { group: "小米", items: [{ id: "as-xm-2", name: "横版二图", size: "960×540", checked: true }] }
    ],
    "appstore:triple": [
      { group: "vivo", items: [{ id: "as-vivo-3", name: "搜索三图", size: "320×211", checked: true }] },
      { group: "OPPO", items: [{ id: "as-oppo-3", name: "横版三图", size: "320×210", checked: true }] },
      { group: "小米", items: [{ id: "as-xm-3", name: "搜索三图", size: "320×320", checked: true }] },
      { group: "荣耀", items: [{ id: "as-ry-3", name: "三图文", size: "1080×1920", checked: true }] }
    ],
    "feed:single": [
      { group: "微博粉丝通", items: [{ id: "feed-wb", name: "横版单图", size: "1280×720", checked: true }] },
      { group: "CPA", items: [
        { id: "feed-cpa-h", name: "横图", size: "690×360", checked: false },
        { id: "feed-cpa-v", name: "竖图", size: "1080×1920", checked: true, ctaMode: "none" }
      ] },
      { group: "喜马拉雅", span2: true, items: [
        { id: "feed-xm-1280", name: "单图", size: "1280×720", checked: true },
        { id: "feed-xm-720x1280", name: "单图", size: "720×1280", checked: true, forceLogo: true },
        { id: "feed-xm-1200x480", name: "单图", size: "1200×480", checked: true },
        { id: "feed-xm-1000", name: "单图", size: "1000×1000", checked: true, ctaMode: "custom", ctaCustom: "马上听" },
        { id: "feed-xm-720x1559", name: "单图", size: "720×1559", checked: true, forceLogo: true }
      ] }
    ]
  };

  var DEFRAME_SIZES = ["1200×480", "720×1559", "690×360"];

  var state = {
    channel: "feed",
    format: "single",
    setsPerPlacement: 3,
    currentPlacementSet1Selected: true,
    currentPlacementSet2Developed: false,
    currentPlacementSet2Selected: false,
    app3Set1Selected: true,
    activeChipForCta: null,
    globalLogoUse: true
  };

  function normalizeHash(rawHash) {
    if (!rawHash || VALID_HASHES.indexOf(rawHash) === -1) {
      return "#config";
    }
    return rawHash;
  }

  function renderPlacementRows() {
    var container = document.getElementById("placement-rows-container");
    var emptyBox = document.getElementById("device-empty-state");
    var formatRow = document.getElementById("format-row");
    var copySingle = document.getElementById("copy-single");
    var copyMulti = document.getElementById("copy-multi");
    var line3 = document.getElementById("copy-multi-line3");

    var hasChannel = Boolean(state.channel);
    document.querySelectorAll(".channel-dependent").forEach(function (el) {
      el.classList.toggle("is-disabled", !hasChannel);
    });

    if (formatRow) {
      formatRow.style.display = state.channel === "appstore" ? "flex" : "none";
    }

    var effFormat = state.channel === "appstore" ? state.format : "single";
    if (copySingle && copyMulti) {
      if (effFormat === "single") {
        copySingle.style.display = "grid";
        copyMulti.style.display = "none";
      } else {
        copySingle.style.display = "none";
        copyMulti.style.display = "grid";
        copyMulti.classList.toggle("is-triple", effFormat === "triple");
        if (line3) line3.style.display = effFormat === "triple" ? "flex" : "none";
      }
    }

    if (state.channel === "device") {
      if (container) container.style.display = "none";
      if (emptyBox) emptyBox.style.display = "block";
      updateConfigSummary();
      return;
    }

    if (container) container.style.display = "grid";
    if (emptyBox) emptyBox.style.display = "none";

    var key = (state.channel || "feed") + ":" + effFormat;
    var groups = PLACEMENTS_DB[key] || PLACEMENTS_DB["feed:single"];

    if (container) {
      container.innerHTML = groups.map(function (grp) {
        var spanCls = grp.span2 ? " span-2" : "";
        var listCls = grp.span2 ? " grid-2col" : "";
        var rowsHtml = grp.items.map(function (item) {
          var checkedCls = item.checked ? " checked" : "";
          var checkedAttr = item.checked ? " checked" : "";
          var ctaMode = item.ctaMode || "inherit";
          var ctaCustom = item.ctaCustom || "";
          var forceLogoAttr = item.forceLogo ? ' data-force-logo="true"' : "";
          var lockSpan = item.forceLogo
            ? '<span class="logo-lock-icon' + (!state.globalLogoUse ? " force-highlight" : "") + '" title="固定带 Logo"><svg class="ui-icon lock-mini-svg" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="7.25" width="9" height="6.25" rx="1.5"/><path d="M5.5 7.25V5.25a2.5 2.5 0 0 1 5 0v2"/></svg><span>Logo</span></span>'
            : "";
          return (
            '<div class="placement-row' + checkedCls + '" data-id="' + item.id + '" data-cta-mode="' + ctaMode + '" data-cta-custom="' + ctaCustom + '"' + forceLogoAttr + ">" +
              '<label class="row-check-label">' +
                '<input type="checkbox" class="placement-checkbox"' + checkedAttr + " />" +
                '<span class="row-name">' + item.name + "</span>" +
              "</label>" +
              '<span class="row-size-cell"><span class="row-size">' + item.size + "</span>" + lockSpan + "</span>" +
              '<div class="row-trailing">' +
                '<button type="button" class="chip-cta mode-' + ctaMode + '"><span class="chip-cta-label">立即体验</span><span class="chip-cta-caret">▾</span></button>' +
              "</div>" +
            "</div>"
          );
        }).join("");

        return (
          '<div class="platform-group' + spanCls + '">' +
            '<div class="platform-group-title">' + grp.group + "</div>" +
            '<div class="platform-items-list' + listCls + '">' + rowsHtml + "</div>" +
          "</div>"
        );
      }).join("");
    }

    syncPlacementCtas();
    updateConfigSummary();
  }

  function applyRoute() {
    var hash = normalizeHash(window.location.hash);

    document.querySelectorAll(".proto-link").forEach(function (link) {
      link.classList.toggle("active", link.getAttribute("href") === hash);
    });

    var screenConfig = document.getElementById("screen-config");
    var screenWorkbench = document.getElementById("screen-workbench");
    var lightboxOverlay = document.getElementById("lightbox-overlay");
    var configBody = document.getElementById("config-body");
    var sceneRowCompact = document.getElementById("scene-setting-compact");
    var scenePanelExpanded = document.getElementById("scene-setting-expanded");

    if (hash === "#config" || hash === "#config-app3" || hash === "#config-custom") {
      screenConfig.classList.add("active");
      screenWorkbench.classList.remove("active");
      lightboxOverlay.classList.remove("active");

      document.getElementById("sidebar-active-draft").classList.toggle("active", hash !== "#config-app3");
      document.getElementById("sidebar-draft-app3").classList.toggle("active", hash === "#config-app3");

      if (hash === "#config-app3") {
        state.channel = "appstore";
        state.format = "triple";
        state.setsPerPlacement = 2;
      } else {
        state.channel = "feed";
        state.format = "single";
        state.setsPerPlacement = 3;
      }

      document.querySelectorAll("#channel-seg-group .seg-btn").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-channel") === state.channel);
      });
      document.querySelectorAll("#format-seg-group .seg-btn").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-format") === state.format);
      });

      var isCustom = hash === "#config-custom";
      configBody.classList.toggle("allow-scroll", isCustom);
      sceneRowCompact.style.display = isCustom ? "none" : "flex";
      scenePanelExpanded.style.display = isCustom ? "block" : "none";

      renderPlacementRows();
    } else if (hash === "#workbench" || hash === "#workbench-3") {
      screenConfig.classList.remove("active");
      screenWorkbench.classList.add("active");
      lightboxOverlay.classList.remove("active");
      switchWorkbenchMode(hash === "#workbench-3");
    } else if (hash === "#lightbox") {
      screenConfig.classList.remove("active");
      screenWorkbench.classList.add("active");
      lightboxOverlay.classList.add("active");
    }
  }

  function updateConfigSummary() {
    var checkboxes = document.querySelectorAll("#placement-rows-container .placement-checkbox");
    var checkedCount = 0;
    checkboxes.forEach(function (cb) {
      var row = cb.closest(".placement-row");
      if (cb.checked) {
        checkedCount += 1;
        if (row) row.classList.add("checked");
      } else {
        if (row) row.classList.remove("checked");
      }
    });

    if (!state.channel || state.channel === "device") {
      checkedCount = 0;
    }

    var setsVal = Math.max(1, Math.min(20, parseInt(state.setsPerPlacement, 10) || 1));
    state.setsPerPlacement = setsVal;

    var setsInput = document.getElementById("sets-input");
    if (setsInput && document.activeElement !== setsInput) {
      setsInput.value = String(setsVal);
    }

    var effFormat = state.channel === "appstore" ? state.format : "single";
    var imgsPerSet = effFormat === "triple" ? 3 : effFormat === "double" ? 2 : 1;
    var totalImages = checkedCount * setsVal * imgsPerSet;

    var elTotal = document.getElementById("summary-total-images");
    if (elTotal) {
      elTotal.textContent = "共 " + totalImages + " 张";
    }

    var elFormula = document.getElementById("summary-formula-sub");
    if (elFormula) {
      elFormula.textContent = imgsPerSet > 1
        ? checkedCount + " 版位 × " + setsVal + " 套 × " + imgsPerSet + " 张"
        : checkedCount + " 版位 × " + setsVal + " 套";
    }

    var badge = document.getElementById("placement-combo-badge");
    if (badge) {
      var chLabel = state.channel === "appstore" ? "应用商店" : state.channel === "device" ? "学习机" : "信息流";
      var fmtLabel = effFormat === "triple" ? "三图" : effFormat === "double" ? "双图" : "单图";
      badge.textContent = !state.channel
        ? "请先选择渠道"
        : chLabel + " · " + fmtLabel + "（已选 " + checkedCount + "/" + checkboxes.length + "）";
    }
  }

  function syncPlacementCtas() {
    var isMulti = state.channel === "appstore" && state.format !== "single";
    var globalEnabledEl = document.getElementById(isMulti ? "global-cta-enabled-multi" : "global-cta-enabled");
    var globalInputEl = document.getElementById(isMulti ? "global-cta-input-multi" : "global-cta-input");
    var globalEnabled = globalEnabledEl ? globalEnabledEl.checked : true;
    var globalText = globalInputEl ? globalInputEl.value.trim() : "立即体验";

    if (globalInputEl) {
      globalInputEl.disabled = !globalEnabled;
    }

    document.querySelectorAll(".placement-row").forEach(function (row) {
      var mode = row.getAttribute("data-cta-mode") || "inherit";
      var customText = row.getAttribute("data-cta-custom") || "";
      var labelEl = row.querySelector(".chip-cta-label");
      if (!labelEl) return;
      row.querySelector(".chip-cta").className = "chip-cta mode-" + mode;

      if (mode === "none") {
        labelEl.textContent = "无按钮";
      } else if (mode === "custom" && customText) {
        labelEl.textContent = customText;
      } else {
        labelEl.textContent = globalEnabled && globalText ? globalText : "无按钮";
      }
    });
  }

  function switchWorkbenchMode(isTriple) {
    var dirFeed = document.getElementById("dir-list-feed");
    var dirApp3 = document.getElementById("dir-list-app3");
    var stageSingle = document.getElementById("gallery-stage-single");
    var stageTriple = document.getElementById("gallery-stage-triple");
    var wbTitle = document.getElementById("wb-task-title");
    var wbProgress = document.getElementById("wb-progress-pill");
    var curPlacement = document.getElementById("workbench-current-placement-title");

    if (dirFeed) dirFeed.style.display = isTriple ? "none" : "flex";
    if (dirApp3) dirApp3.style.display = isTriple ? "flex" : "none";
    if (stageSingle) {
      stageSingle.style.display = isTriple ? "none" : "grid";
      stageSingle.setAttribute("data-force-logo", "true");
    }
    if (stageTriple) stageTriple.style.display = isTriple ? "flex" : "none";

    if (wbTitle) wbTitle.textContent = isTriple ? "搜题三步讲透" : "这不看不懂？点开听一听";
    if (wbProgress) {
      var feedDone = 16 + (state.currentPlacementSet2Developed ? 1 : 0);
      wbProgress.innerHTML = isTriple
        ? '已出 <strong class="metric-num">14 / 24</strong> 张'
        : '已出 <strong class="metric-num">' + feedDone + ' / 21</strong> 张';
    }
    if (curPlacement) curPlacement.textContent = isTriple ? "OPPO 横版三图 320×210" : "喜马拉雅 单图 720×1559";

    updateWorkbenchSelection();
  }

  function updateWorkbenchSelection() {
    var isTriple = normalizeHash(window.location.hash) === "#workbench-3";
    var saveBtn = document.getElementById("workbench-save-btn");
    var saveStatus = document.getElementById("workbench-save-status");

    if (isTriple) {
      var tCard = document.getElementById("triple-set-1-card");
      var tBtn = document.getElementById("triple-set-1-check-btn");
      var tBadge = document.getElementById("app3-dir-selected-badge");
      var tChecked = state.app3Set1Selected;
      if (tCard) tCard.classList.toggle("selected", tChecked);
      if (tBtn) tBtn.classList.toggle("checked", tChecked);
      if (tBadge) {
        tBadge.textContent = tChecked ? "✓ 1" : "0/1 待选";
        tBadge.className = tChecked ? "badge-selected" : "badge-unselected-ready";
      }
      var app3Total = 2 + (tChecked ? 1 : 0);
      var app3Covered = 2 + (tChecked ? 1 : 0);
      if (saveStatus) {
        saveStatus.innerHTML = '已选 <strong class="metric-num">' + app3Total + '</strong> 套 <span class="facts-sep">·</span> ' + app3Covered + '/4 个版位';
      }
      if (saveBtn) saveBtn.textContent = "保存已合格的 " + app3Total + " 套";
      return;
    }

    var set1Card = document.getElementById("set-1-card");
    var set1Btn = document.getElementById("set-1-check-btn");
    var set2Card = document.getElementById("set-2-card");
    var set2Btn = document.getElementById("set-2-check-btn");
    var lbToggleBtn = document.getElementById("lightbox-toggle-select-btn");
    var lbCheckBox = document.getElementById("lightbox-check-box");
    var dirBadge = document.getElementById("active-dir-selected-badge");
    var isChecked1 = state.currentPlacementSet1Selected;
    var isChecked2 = state.currentPlacementSet2Developed && state.currentPlacementSet2Selected;
    var curCount = (isChecked1 ? 1 : 0) + (isChecked2 ? 1 : 0);
    var readyTotal = state.currentPlacementSet2Developed ? 2 : 1;

    if (set1Card) set1Card.classList.toggle("selected", isChecked1);
    if (set1Btn) set1Btn.classList.toggle("checked", isChecked1);
    if (set2Card) set2Card.classList.toggle("selected", isChecked2);
    if (set2Btn) set2Btn.classList.toggle("checked", isChecked2);
    if (lbToggleBtn) lbToggleBtn.classList.toggle("checked", isChecked1);
    if (lbCheckBox) lbCheckBox.classList.toggle("checked", isChecked1);
    if (dirBadge) {
      dirBadge.textContent = curCount > 0 ? ("✓ " + curCount) : ("0/" + readyTotal + " 待选");
      dirBadge.className = curCount > 0 ? "badge-selected" : "badge-unselected-ready";
    }

    var totalSelected = 3 + curCount;
    var coveredPlacements = 3 + (curCount > 0 ? 1 : 0);
    if (saveBtn) saveBtn.textContent = "保存已合格的 " + totalSelected + " 套";
    if (saveStatus) {
      saveStatus.innerHTML = '已选 <strong class="metric-num">' + totalSelected + '</strong> 套 <span class="facts-sep">·</span> ' + coveredPlacements + '/7 个版位';
    }
  }

  function bindEvents() {
    window.addEventListener("hashchange", applyRoute);

    // 1. 渠道切换与重置未选
    var channelSeg = document.getElementById("channel-seg-group");
    if (channelSeg) {
      channelSeg.querySelectorAll(".seg-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          state.channel = btn.getAttribute("data-channel");
          renderPlacementRows();
        });
      });
    }
    var clearChannelBtn = document.getElementById("clear-channel-btn");
    if (clearChannelBtn) {
      clearChannelBtn.addEventListener("click", function () {
        state.channel = null;
        document.querySelectorAll("#channel-seg-group .seg-btn").forEach(function (b) {
          b.classList.remove("active");
        });
        renderPlacementRows();
      });
    }

    // 2. 图片形式切换（单图 / 双图 / 三图）
    var formatSeg = document.getElementById("format-seg-group");
    if (formatSeg) {
      formatSeg.querySelectorAll(".seg-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          state.format = btn.getAttribute("data-format");
          renderPlacementRows();
        });
      });
    }

    // 3. 分段按钮组通用切换高亮与全局 Logo 锁定演示
    document.querySelectorAll(".seg-group").forEach(function (group) {
      var btns = group.querySelectorAll(".seg-btn");
      btns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          btns.forEach(function (b) { b.classList.remove("active"); });
          btn.classList.add("active");
          if (group.id === "global-logo-seg") {
            state.globalLogoUse = btn.getAttribute("data-logo") === "use";
            document.querySelectorAll(".logo-lock-icon").forEach(function (tag) {
              tag.classList.toggle("force-highlight", !state.globalLogoUse);
            });
          }
        });
      });
    });

    // 4. 版位勾选与单版位按钮文字下拉（事件委托）
    var rowsContainer = document.getElementById("placement-rows-container");
    var popover = document.getElementById("cta-popover");
    var optInherit = document.getElementById("cta-opt-inherit");
    var optCustom = document.getElementById("cta-opt-custom");
    var optNone = document.getElementById("cta-opt-none");

    if (rowsContainer) {
      rowsContainer.addEventListener("change", function (e) {
        if (e.target.classList.contains("placement-checkbox")) {
          updateConfigSummary();
        }
      });
      rowsContainer.addEventListener("click", function (e) {
        var btn = e.target.closest(".chip-cta");
        if (!btn) return;
        e.stopPropagation();
        var row = btn.closest(".placement-row");
        state.activeChipForCta = row;
        var mode = row.getAttribute("data-cta-mode");
        optInherit.classList.toggle("is-current", mode === "inherit");
        optCustom.classList.toggle("is-current", mode === "custom");
        optNone.classList.toggle("is-current", mode === "none");
        var isMulti = state.channel === "appstore" && state.format !== "single";
        var globalInput = document.getElementById(isMulti ? "global-cta-input-multi" : "global-cta-input");
        var globalEnabled = document.getElementById(isMulti ? "global-cta-enabled-multi" : "global-cta-enabled");
        document.getElementById("cta-inherit-text").textContent = " · " + (globalEnabled.checked && globalInput.value.trim() ? globalInput.value.trim() : "无按钮");
        popover.style.display = "flex";
        var rect = btn.getBoundingClientRect();
        var parent = popover.offsetParent;
        var parentRect = parent.getBoundingClientRect();
        popover.style.top = (rect.bottom - parentRect.top + parent.scrollTop - parent.clientTop + 4) + "px";
        popover.style.left = (rect.left - parentRect.left + parent.scrollLeft - parent.clientLeft) + "px";
      });
    }

    ["global-cta-enabled", "global-cta-input", "global-cta-enabled-multi", "global-cta-input-multi"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) {
        el.addEventListener("change", syncPlacementCtas);
        el.addEventListener("input", syncPlacementCtas);
      }
    });

    var btnMinus = document.getElementById("sets-minus-btn");
    var btnPlus = document.getElementById("sets-plus-btn");
    var setsInput = document.getElementById("sets-input");
    if (btnMinus) {
      btnMinus.addEventListener("click", function () {
        if (state.setsPerPlacement > 1) {
          state.setsPerPlacement -= 1;
          updateConfigSummary();
        }
      });
    }
    if (btnPlus) {
      btnPlus.addEventListener("click", function () {
        if (state.setsPerPlacement < 20) {
          state.setsPerPlacement += 1;
          updateConfigSummary();
        }
      });
    }
    if (setsInput) {
      setsInput.addEventListener("input", function () {
        state.setsPerPlacement = parseInt(setsInput.value, 10) || 1;
        updateConfigSummary();
      });
    }

    [optInherit, optNone].forEach(function (option) {
      option.addEventListener("click", function () {
        state.activeChipForCta.setAttribute("data-cta-mode", option === optInherit ? "inherit" : "none");
        state.activeChipForCta.setAttribute("data-cta-custom", "");
        syncPlacementCtas();
        popover.style.display = "none";
      });
    });
    optCustom.addEventListener("click", function () {
      var row = state.activeChipForCta;
      var btn = row.querySelector(".chip-cta");
      var input = document.createElement("input");
      input.type = "text";
      input.className = "inline-cta-input";
      input.maxLength = 12;
      input.value = btn.querySelector(".chip-cta-label").textContent;
      input.setAttribute("aria-label", "自定义按钮文字");
      popover.style.display = "none";
      btn.replaceWith(input);
      input.onblur = function () {
        var text = input.value.trim();
        row.setAttribute("data-cta-mode", text ? "custom" : "inherit");
        row.setAttribute("data-cta-custom", text);
        input.replaceWith(btn);
        syncPlacementCtas();
      };
      input.addEventListener("keydown", function (e) {
        if (e.isComposing) return;
        if (e.key === "Enter") {
          e.preventDefault();
          input.blur();
        } else if (e.key === "Escape") {
          input.onblur = null;
          input.replaceWith(btn);
          syncPlacementCtas();
          btn.focus();
        }
      });
      input.focus();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") popover.style.display = "none";
    });

    document.addEventListener("click", function (e) {
      if (popover && popover.style.display !== "none" && !popover.contains(e.target)) {
        popover.style.display = "none";
      }
    });

    // 5. 参考风格要点：待确认 <-> 已确认状态切换 + 删除/添加标签
    var pointsArea = document.getElementById("points-confirm-area");
    var pointsList = document.getElementById("points-tag-list");
    var addPointBtn = document.getElementById("add-point-btn");
    var confirmPointsBtn = document.getElementById("confirm-points-btn");
    var editPointsLink = document.getElementById("edit-points-link");
    var styleLockPill = document.getElementById("style-lock-pill");

    function setPointsConfirmed(confirmed) {
      if (!pointsArea) return;
      pointsArea.setAttribute("data-status", confirmed ? "confirmed" : "pending");
      pointsArea.querySelectorAll(".point-tag-text").forEach(function (el) {
        el.setAttribute("contenteditable", confirmed ? "false" : "true");
      });
      if (confirmPointsBtn) confirmPointsBtn.style.display = confirmed ? "none" : "inline-block";
      if (editPointsLink) editPointsLink.style.display = confirmed ? "inline-block" : "none";
      if (styleLockPill) {
        styleLockPill.innerHTML = confirmed
          ? '<svg class="ui-icon lock-mini-svg" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="7.25" width="9" height="6.25" rx="1.5"/><path d="M5.5 7.25V5.25a2.5 2.5 0 0 1 5 0v2"/></svg><span>按参考图</span>'
          : "随机";
        styleLockPill.classList.toggle("locked", confirmed);
      }
    }

    if (confirmPointsBtn) {
      confirmPointsBtn.addEventListener("click", function () { setPointsConfirmed(true); });
    }
    if (editPointsLink) {
      editPointsLink.addEventListener("click", function () { setPointsConfirmed(false); });
    }
    if (pointsList) {
      pointsList.addEventListener("click", function (e) {
        if (e.target.classList.contains("point-tag-del")) {
          var tag = e.target.closest(".point-tag");
          if (tag) tag.remove();
        }
      });
    }
    if (addPointBtn && pointsList) {
      addPointBtn.addEventListener("click", function () {
        var span = document.createElement("span");
        span.className = "point-tag";
        span.innerHTML = '<span class="point-tag-text" contenteditable="true" spellcheck="false">新要点</span><button type="button" class="point-tag-del" aria-label="删除">×</button>';
        pointsList.insertBefore(span, addPointBtn);
      });
    }

    // 5. 定制画面展开/收起与 IP 指定角色列表
    var openCustomBtn = document.getElementById("open-custom-btn");
    var collapseCustomBtn = document.getElementById("collapse-custom-btn");
    if (openCustomBtn) {
      openCustomBtn.addEventListener("click", function () { window.location.hash = "#config-custom"; });
    }
    if (collapseCustomBtn) {
      collapseCustomBtn.addEventListener("click", function () { window.location.hash = "#config"; });
    }

    var ipSelect = document.getElementById("ip-mode-select");
    var ipRoster = document.getElementById("ip-roster-pills");
    if (ipSelect && ipRoster) {
      ipSelect.addEventListener("change", function () {
        ipRoster.style.display = ipSelect.value === "custom" ? "inline-flex" : "none";
      });
    }

    // 6. 工作台与大图弹层联动
    var startGenBtn = document.getElementById("start-gen-btn");
    if (startGenBtn) {
      startGenBtn.addEventListener("click", function () {
        window.location.hash = (state.channel === "appstore" && state.format === "triple") ? "#workbench-3" : "#workbench";
      });
    }

    var editConfigBtn = document.getElementById("btn-edit-config");
    if (editConfigBtn) editConfigBtn.addEventListener("click", function () { window.location.hash = "#config"; });

    var set1Btn = document.getElementById("set-1-check-btn");
    if (set1Btn) {
      set1Btn.addEventListener("click", function () {
        state.currentPlacementSet1Selected = !state.currentPlacementSet1Selected;
        updateWorkbenchSelection();
      });
    }

    var set2Card = document.getElementById("set-2-card");
    var set2Btn = document.getElementById("set-2-check-btn");
    var set2Frame = document.getElementById("set-2-frame");
    var set2Pill = document.getElementById("set-2-state-pill");
    if (set2Card) {
      set2Card.addEventListener("click", function (e) {
        if (e.target.closest("#set-2-check-btn")) return;
        if (!state.currentPlacementSet2Developed) {
          state.currentPlacementSet2Developed = true;
          set2Card.classList.remove("is-generating");
          set2Card.classList.add("is-developing", "is-developed");
          set2Card.removeAttribute("title");
          if (set2Frame) {
            set2Frame.classList.remove("skeleton");
            set2Frame.classList.add("clickable");
          }
          if (set2Pill) set2Pill.style.display = "none";
          var wbProgress = document.getElementById("wb-progress-pill");
          if (wbProgress && normalizeHash(window.location.hash) !== "#workbench-3") {
            wbProgress.innerHTML = '已出 <strong class="metric-num">17 / 21</strong> 张';
          }
          updateWorkbenchSelection();
        } else {
          window.location.hash = "#lightbox";
        }
      });
    }
    if (set2Btn) {
      set2Btn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (!state.currentPlacementSet2Developed) return;
        state.currentPlacementSet2Selected = !state.currentPlacementSet2Selected;
        updateWorkbenchSelection();
      });
    }

    var tripleSet1Btn = document.getElementById("triple-set-1-check-btn");
    if (tripleSet1Btn) {
      tripleSet1Btn.addEventListener("click", function () {
        state.app3Set1Selected = !state.app3Set1Selected;
        updateWorkbenchSelection();
      });
    }

    var dirItems = document.querySelectorAll(".dir-item");
    var galleryTitle = document.getElementById("workbench-current-placement-title");
    dirItems.forEach(function (item) {
      item.addEventListener("click", function () {
        var listEl = item.closest(".dir-list");
        if (listEl) {
          listEl.querySelectorAll(".dir-item").forEach(function (el) { el.classList.remove("active"); });
        }
        item.classList.add("active");
        var pName = item.getAttribute("data-placement-title") || "";
        if (galleryTitle && pName) galleryTitle.textContent = pName;
        document.getElementById("gallery-stage-single").setAttribute("data-force-logo", item.getAttribute("data-force-logo") === "true" ? "true" : "false");

        // 业务规则 6：只有 3 个版位（1200×480、720×1559、690×360）可能去框失败，其余异常为生成失败 + 补齐
        var canDeframe = DEFRAME_SIZES.some(function (sz) { return pName.indexOf(sz) !== -1; });
        var pCard = document.getElementById("single-problem-card");
        var pTag = document.getElementById("single-problem-tag");
        var deframeAct = document.getElementById("single-problem-deframe-actions");
        var genAct = document.getElementById("single-problem-gen-actions");
        if (pCard) {
          pCard.classList.toggle("is-warning", canDeframe);
          pCard.classList.toggle("is-error", !canDeframe);
        }
        if (pTag) pTag.textContent = canDeframe ? "需去框" : "生成失败";
        if (deframeAct) deframeAct.style.display = canDeframe ? "flex" : "none";
        if (genAct) genAct.style.display = canDeframe ? "none" : "flex";
      });
    });

    document.querySelectorAll(".js-open-lightbox").forEach(function (el) {
      el.addEventListener("click", function () { window.location.hash = "#lightbox"; });
    });

    var closeLbBtn = document.getElementById("close-lightbox-btn");
    if (closeLbBtn) closeLbBtn.addEventListener("click", function () { window.location.hash = "#workbench"; });

    var lbToggleBtn = document.getElementById("lightbox-toggle-select-btn");
    if (lbToggleBtn) {
      lbToggleBtn.addEventListener("click", function () {
        state.currentPlacementSet1Selected = !state.currentPlacementSet1Selected;
        updateWorkbenchSelection();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindEvents();
    updateConfigSummary();
    syncPlacementCtas();
    updateWorkbenchSelection();
    applyRoute();
  });
})();
