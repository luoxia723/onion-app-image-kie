/* =========================================================
   洋葱学园 · 广告图工作台 — 灰度线框原型交互逻辑
   支持 #config / #config-custom / #workbench / #lightbox 切换与状态联动
   ========================================================= */

(function () {
  "use strict";

  var VALID_HASHES = ["#config", "#config-custom", "#workbench", "#lightbox"];

  // 工作台默认已选 4 套（跨版位总计 4 套，其中当前版位第 1 套默认选中）
  var state = {
    setsPerPlacement: 3,
    baseOtherSelectedSets: 3, // 其他版位已选 3 套 + 当前版位第 1 套 = 默认已选 4 套
    currentPlacementSet1Selected: true
  };

  function normalizeHash(rawHash) {
    if (!rawHash || VALID_HASHES.indexOf(rawHash) === -1) {
      return "#config";
    }
    return rawHash;
  }

  function applyRoute() {
    var hash = normalizeHash(window.location.hash);

    // 1. 更新顶部原型切换栏高亮
    var protoLinks = document.querySelectorAll(".proto-link");
    protoLinks.forEach(function (link) {
      if (link.getAttribute("href") === hash) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });

    // 2. 切换主画面（#lightbox 是在 #workbench 之上叠加半透明遮罩）
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

      if (hash === "#config-custom") {
        configBody.classList.add("allow-scroll");
        sceneRowCompact.style.display = "none";
        scenePanelExpanded.style.display = "block";
      } else {
        configBody.classList.remove("allow-scroll");
        sceneRowCompact.style.display = "flex";
        scenePanelExpanded.style.display = "none";
      }
    } else if (hash === "#workbench") {
      screenConfig.classList.remove("active");
      screenWorkbench.classList.add("active");
      lightboxOverlay.classList.remove("active");
    } else if (hash === "#lightbox") {
      screenConfig.classList.remove("active");
      screenWorkbench.classList.add("active");
      lightboxOverlay.classList.add("active");
    }

    // 同步左侧全局栏当前任务高亮
    var navNewTask = document.getElementById("sidebar-active-draft");
    var navProcessingTask = document.getElementById("sidebar-active-processing");
    if (navNewTask && navProcessingTask) {
      if (hash === "#config" || hash === "#config-custom") {
        navNewTask.classList.add("active");
        navProcessingTask.classList.remove("active");
      } else {
        navNewTask.classList.remove("active");
        navProcessingTask.classList.add("active");
      }
    }
  }

  // 更新画面 1 & 2 的「本次生成」汇总数字
  function updateConfigSummary() {
    var checkboxes = document.querySelectorAll(".placement-checkbox");
    var checkedCount = 0;
    checkboxes.forEach(function (cb) {
      var label = cb.closest(".placement-tag");
      if (cb.checked) {
        checkedCount += 1;
        if (label) label.classList.add("checked");
      } else {
        if (label) label.classList.remove("checked");
      }
    });

    var totalImages = checkedCount * state.setsPerPlacement;

    var elPlacementCount = document.getElementById("summary-placement-count");
    var elSetsCount = document.getElementById("summary-sets-count");
    var elTotalImages = document.getElementById("summary-total-images");
    var elStepperVal = document.getElementById("sets-stepper-val");

    if (elPlacementCount) elPlacementCount.textContent = checkedCount + " 个";
    if (elSetsCount) elSetsCount.textContent = state.setsPerPlacement + " 套";
    if (elTotalImages) elTotalImages.textContent = "共 " + totalImages + " 张";
    if (elStepperVal) elStepperVal.textContent = String(state.setsPerPlacement);
  }

  // 更新画面 3 底部保存栏与卡片勾选高亮
  function updateWorkbenchSelection() {
    var set1Checkbox = document.getElementById("set-1-checkbox");
    var set1CheckboxText = document.getElementById("set-1-checkbox-text");
    var set1Card = document.getElementById("set-1-card");
    var saveStatusText = document.getElementById("workbench-save-status");
    var saveMainBtn = document.getElementById("workbench-save-btn");
    var lightboxToggleBtn = document.getElementById("lightbox-toggle-select-btn");

    var isChecked = set1Checkbox ? set1Checkbox.checked : state.currentPlacementSet1Selected;
    state.currentPlacementSet1Selected = isChecked;

    if (set1CheckboxText) {
      set1CheckboxText.textContent = isChecked ? "已勾选" : "未勾选";
    }

    if (set1Card) {
      if (isChecked) {
        set1Card.classList.add("selected");
      } else {
        set1Card.classList.remove("selected");
      }
    }

    var totalSelected = state.baseOtherSelectedSets + (isChecked ? 1 : 0);
    var coveredPlacements = isChecked ? 5 : 4;

    if (saveStatusText) {
      saveStatusText.textContent =
        "已选 " + totalSelected + " 套 · 覆盖 " + coveredPlacements + "/7 个版位 · 还有 2 套在出";
    }
    if (saveMainBtn) {
      saveMainBtn.textContent = "保存已合格的 " + totalSelected + " 套";
    }
    if (lightboxToggleBtn) {
      lightboxToggleBtn.textContent = isChecked ? "✓ 已勾选这一套（点击取消）" : "勾选这一套";
    }

    // 同步当前高亮目录项的状态文案
    var activeDirStatus = document.querySelector(".dir-item.active .dir-item-status");
    if (activeDirStatus) {
      activeDirStatus.textContent = isChecked ? "✓ 已选 1 套" : "3 套待挑";
      if (isChecked) {
        activeDirStatus.classList.add("status-done");
      } else {
        activeDirStatus.classList.remove("status-done");
      }
    }
  }

  function bindEvents() {
    window.addEventListener("hashchange", applyRoute);

    // 版位勾选变化
    var checkboxes = document.querySelectorAll(".placement-checkbox");
    checkboxes.forEach(function (cb) {
      cb.addEventListener("change", updateConfigSummary);
    });

    // 每版位套数步进器
    var btnMinus = document.getElementById("sets-minus-btn");
    var btnPlus = document.getElementById("sets-plus-btn");
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
        if (state.setsPerPlacement < 10) {
          state.setsPerPlacement += 1;
          updateConfigSummary();
        }
      });
    }

    // 主标题输入同步高级里的方向名
    var mainTitleInput = document.getElementById("input-main-title");
    var dirNameInput = document.getElementById("input-direction-name");
    if (mainTitleInput && dirNameInput) {
      mainTitleInput.addEventListener("input", function () {
        dirNameInput.value = mainTitleInput.value;
      });
    }

    // 分段按钮组切换效果
    var segGroups = document.querySelectorAll(".seg-group");
    segGroups.forEach(function (group) {
      var btns = group.querySelectorAll(".seg-btn");
      btns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          btns.forEach(function (b) {
            b.classList.remove("active");
          });
          btn.classList.add("active");
        });
      });
    });

    // 定制画面展开/收起按钮
    var openCustomBtn = document.getElementById("open-custom-btn");
    if (openCustomBtn) {
      openCustomBtn.addEventListener("click", function () {
        window.location.hash = "#config-custom";
      });
    }

    var collapseCustomBtn = document.getElementById("collapse-custom-btn");
    if (collapseCustomBtn) {
      collapseCustomBtn.addEventListener("click", function () {
        window.location.hash = "#config";
      });
    }

    // 开始生成按钮 -> 跳转到 #workbench
    var startGenBtn = document.getElementById("start-gen-btn");
    if (startGenBtn) {
      startGenBtn.addEventListener("click", function () {
        window.location.hash = "#workbench";
      });
    }

    // 工作台「修改配置」按钮 -> 回到 #config
    var editConfigBtn = document.getElementById("btn-edit-config");
    if (editConfigBtn) {
      editConfigBtn.addEventListener("click", function () {
        window.location.hash = "#config";
      });
    }

    // 工作台第 1 套复选框交互
    var set1Checkbox = document.getElementById("set-1-checkbox");
    if (set1Checkbox) {
      set1Checkbox.addEventListener("change", updateWorkbenchSelection);
    }

    // 工作台左侧版位目录点击切换高亮
    var dirItems = document.querySelectorAll(".dir-item");
    var galleryTitle = document.getElementById("workbench-current-placement-title");
    dirItems.forEach(function (item) {
      item.addEventListener("click", function () {
        dirItems.forEach(function (el) {
          el.classList.remove("active");
        });
        item.classList.add("active");
        var pName = item.getAttribute("data-placement-title");
        if (galleryTitle && pName) {
          galleryTitle.textContent = pName;
        }
      });
    });

    // 点击第 1 套大图占位进入 #lightbox
    var openLightboxTriggers = document.querySelectorAll(".js-open-lightbox");
    openLightboxTriggers.forEach(function (el) {
      el.addEventListener("click", function () {
        window.location.hash = "#lightbox";
      });
    });

    // 关闭大图弹层回到 #workbench
    var closeLightboxBtn = document.getElementById("close-lightbox-btn");
    if (closeLightboxBtn) {
      closeLightboxBtn.addEventListener("click", function () {
        window.location.hash = "#workbench";
      });
    }

    // 大图弹层中的「勾选这一套」联动工作台勾选状态
    var lightboxToggleBtn = document.getElementById("lightbox-toggle-select-btn");
    if (lightboxToggleBtn && set1Checkbox) {
      lightboxToggleBtn.addEventListener("click", function () {
        set1Checkbox.checked = !set1Checkbox.checked;
        updateWorkbenchSelection();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindEvents();
    updateConfigSummary();
    updateWorkbenchSelection();
    applyRoute();
  });
})();
