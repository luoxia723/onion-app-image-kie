(function () {
  "use strict";

  var VALID_HASHES = ["#config", "#config-custom", "#workbench", "#lightbox"];

  var state = {
    setsPerPlacement: 3,
    baseOtherSelectedSets: 3,
    currentPlacementSet1Selected: true,
    activeChipForCta: null,
    lightboxIndex: 1
  };

  function normalizeHash(rawHash) {
    if (!rawHash || VALID_HASHES.indexOf(rawHash) === -1) {
      return "#config";
    }
    return rawHash;
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

    if (hash === "#config" || hash === "#config-custom") {
      screenConfig.classList.add("active");
      screenWorkbench.classList.remove("active");
      lightboxOverlay.classList.remove("active");

      var isCustom = hash === "#config-custom";
      configBody.classList.toggle("allow-scroll", isCustom);
      sceneRowCompact.style.display = isCustom ? "none" : "flex";
      scenePanelExpanded.style.display = isCustom ? "block" : "none";
    } else if (hash === "#workbench") {
      screenConfig.classList.remove("active");
      screenWorkbench.classList.add("active");
      lightboxOverlay.classList.remove("active");
    } else if (hash === "#lightbox") {
      screenConfig.classList.remove("active");
      screenWorkbench.classList.add("active");
      lightboxOverlay.classList.add("active");
    }

    var navDraft = document.getElementById("sidebar-active-draft");
    var navProc = document.getElementById("sidebar-active-processing");
    if (navDraft && navProc) {
      var onConfig = hash === "#config" || hash === "#config-custom";
      navDraft.classList.toggle("active", onConfig);
      navProc.classList.toggle("active", !onConfig);
    }
  }

  function updateConfigSummary() {
    var checkboxes = document.querySelectorAll(".placement-checkbox");
    var checkedCount = 0;
    checkboxes.forEach(function (cb) {
      var chip = cb.closest(".placement-chip");
      if (cb.checked) {
        checkedCount += 1;
        if (chip) chip.classList.add("checked");
      } else {
        if (chip) chip.classList.remove("checked");
      }
    });

    var setsVal = Math.max(1, Math.min(20, parseInt(state.setsPerPlacement, 10) || 1));
    state.setsPerPlacement = setsVal;

    var setsInput = document.getElementById("sets-input");
    if (setsInput && document.activeElement !== setsInput) {
      setsInput.value = String(setsVal);
    }

    var totalImages = checkedCount * setsVal;
    var elTotal = document.getElementById("summary-total-images");
    if (elTotal) {
      elTotal.textContent = "共 " + totalImages + " 张";
    }
  }

  function syncPlacementCtas() {
    var globalEnabledEl = document.getElementById("global-cta-enabled");
    var globalInputEl = document.getElementById("global-cta-input");
    var globalEnabled = globalEnabledEl ? globalEnabledEl.checked : true;
    var globalText = globalInputEl ? globalInputEl.value.trim() : "立即体验";

    if (globalInputEl) {
      globalInputEl.disabled = !globalEnabled;
    }

    document.querySelectorAll(".placement-chip").forEach(function (chip) {
      var mode = chip.getAttribute("data-cta-mode") || "inherit";
      var customText = chip.getAttribute("data-cta-custom") || "";
      var labelEl = chip.querySelector(".chip-cta-label");
      if (!labelEl) return;

      if (mode === "none") {
        labelEl.textContent = "无按钮";
      } else if (mode === "custom" && customText) {
        labelEl.textContent = customText;
      } else {
        labelEl.textContent = globalEnabled && globalText ? globalText : "无按钮";
      }
    });
  }

  function updateWorkbenchSelection() {
    var set1Card = document.getElementById("set-1-card");
    var set1Btn = document.getElementById("set-1-check-btn");
    var saveBtn = document.getElementById("workbench-save-btn");
    var saveStatus = document.getElementById("workbench-save-status");
    var lbToggleBtn = document.getElementById("lightbox-toggle-select-btn");
    var lbCheckBox = document.getElementById("lightbox-check-box");
    var dirBadge = document.getElementById("active-dir-selected-badge");

    var isChecked = state.currentPlacementSet1Selected;

    if (set1Card) set1Card.classList.toggle("selected", isChecked);
    if (set1Btn) set1Btn.classList.toggle("checked", isChecked);

    var totalSelected = state.baseOtherSelectedSets + (isChecked ? 1 : 0);
    var coveredPlacements = isChecked ? 5 : 4;
    if (saveBtn) {
      saveBtn.textContent = "保存已合格的 " + totalSelected + " 套";
    }
    if (saveStatus) {
      saveStatus.textContent = "已选 " + totalSelected + " 套 · " + coveredPlacements + "/7 个版位";
    }
    if (lbToggleBtn) {
      lbToggleBtn.classList.toggle("checked", isChecked);
    }
    if (lbCheckBox) {
      lbCheckBox.classList.toggle("checked", isChecked);
    }
    if (dirBadge) {
      dirBadge.textContent = isChecked ? "✓ 1" : "";
      dirBadge.style.display = isChecked ? "inline-block" : "none";
    }
  }

  function bindEvents() {
    window.addEventListener("hashchange", applyRoute);

    // 1. 图片形式切换（单图 / 双图 / 三图）
    var formatSeg = document.getElementById("format-seg-group");
    if (formatSeg) {
      formatSeg.querySelectorAll(".seg-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var fmt = btn.getAttribute("data-format");
          var copySingle = document.getElementById("copy-single");
          var copyMulti = document.getElementById("copy-multi");
          var line3 = document.getElementById("copy-multi-line3");
          if (fmt === "single") {
            copySingle.style.display = "grid";
            copyMulti.style.display = "none";
          } else {
            copySingle.style.display = "none";
            copyMulti.style.display = "grid";
            line3.style.display = fmt === "triple" ? "flex" : "none";
          }
        });
      });
    }

    // 2. 分段按钮组通用切换高亮
    document.querySelectorAll(".seg-group").forEach(function (group) {
      var btns = group.querySelectorAll(".seg-btn");
      btns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          btns.forEach(function (b) { b.classList.remove("active"); });
          btn.classList.add("active");
        });
      });
    });

    // 3. 版位勾选与套数联动
    document.querySelectorAll(".placement-checkbox").forEach(function (cb) {
      cb.addEventListener("change", updateConfigSummary);
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

    // 4. 全局按钮文字与单版位按钮文字紧凑下拉编辑
    var globalCtaEnabled = document.getElementById("global-cta-enabled");
    var globalCtaInput = document.getElementById("global-cta-input");
    if (globalCtaEnabled) globalCtaEnabled.addEventListener("change", syncPlacementCtas);
    if (globalCtaInput) globalCtaInput.addEventListener("input", syncPlacementCtas);

    var popover = document.getElementById("cta-popover");
    var optInherit = document.getElementById("cta-opt-inherit");
    var optCustom = document.getElementById("cta-opt-custom");
    var optNone = document.getElementById("cta-opt-none");
    var customEditor = document.getElementById("cta-custom-editor");
    var popInput = document.getElementById("cta-popover-input");
    var popApply = document.getElementById("cta-popover-apply");

    document.querySelectorAll(".chip-cta").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var chip = btn.closest(".placement-chip");
        state.activeChipForCta = chip;
        var curCustom = chip.getAttribute("data-cta-custom");
        popInput.value = curCustom || (globalCtaInput ? globalCtaInput.value : "立即体验");
        customEditor.style.display = "none";
        popover.style.display = "flex";
        popover.style.top = (chip.offsetTop + chip.offsetHeight + 4) + "px";
        popover.style.left = Math.min(chip.offsetLeft, 420) + "px";
      });
    });

    if (optInherit) {
      optInherit.addEventListener("click", function () {
        if (state.activeChipForCta) {
          state.activeChipForCta.setAttribute("data-cta-mode", "inherit");
          state.activeChipForCta.setAttribute("data-cta-custom", "");
          syncPlacementCtas();
        }
        popover.style.display = "none";
      });
    }
    if (optNone) {
      optNone.addEventListener("click", function () {
        if (state.activeChipForCta) {
          state.activeChipForCta.setAttribute("data-cta-mode", "none");
          syncPlacementCtas();
        }
        popover.style.display = "none";
      });
    }
    if (optCustom) {
      optCustom.addEventListener("click", function (e) {
        e.stopPropagation();
        customEditor.style.display = "flex";
        popInput.focus();
      });
    }
    if (popApply) {
      popApply.addEventListener("click", function () {
        if (state.activeChipForCta) {
          state.activeChipForCta.setAttribute("data-cta-mode", "custom");
          state.activeChipForCta.setAttribute("data-cta-custom", popInput.value.trim() || "立即体验");
          syncPlacementCtas();
        }
        popover.style.display = "none";
      });
    }

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
        styleLockPill.textContent = confirmed ? "🔒 按参考图" : "随机";
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
    if (startGenBtn) startGenBtn.addEventListener("click", function () { window.location.hash = "#workbench"; });

    var editConfigBtn = document.getElementById("btn-edit-config");
    if (editConfigBtn) editConfigBtn.addEventListener("click", function () { window.location.hash = "#config"; });

    var set1Btn = document.getElementById("set-1-check-btn");
    if (set1Btn) {
      set1Btn.addEventListener("click", function () {
        state.currentPlacementSet1Selected = !state.currentPlacementSet1Selected;
        updateWorkbenchSelection();
      });
    }

    var dirItems = document.querySelectorAll(".dir-item");
    var galleryTitle = document.getElementById("workbench-current-placement-title");
    dirItems.forEach(function (item) {
      item.addEventListener("click", function () {
        dirItems.forEach(function (el) { el.classList.remove("active"); });
        item.classList.add("active");
        var pName = item.getAttribute("data-placement-title");
        if (galleryTitle && pName) galleryTitle.textContent = pName;
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
