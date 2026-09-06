/**
 * Tagify v9.1 — 前端交互逻辑
 */

// ── 状态 ──
const state = {
  viewMode: 'gallery',
  currentTag: null,
  currentPage: 1,
  totalPages: 0,
  sortBy: 'time',
  sortOrder: 'DESC',
  selectedImage: null,
  showDetails: false,
  favoriteTag: 'collect',
  theme: 'light',
  config: null,      // 服务器配置（来自 /api/config）
};

// ── DOM 引用 ──
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  searchInput: $('#search-input'),
  suggestDropdown: $('#suggest-dropdown'),
  tagList: $('#tag-list'),
  imageGrid: $('#image-grid'),
  pagination: $('#pagination'),
  infoName: $('#info-name'),
  infoSize: $('#info-size'),
  infoTime: $('#info-time'),
  showDetailsCb: $('#show-details'),
  tagCount: $('#tag-count'),
  tagDetail: $('#tag-detail'),
  ratingSection: $('#rating-section'),
  ratingTags: $('#rating-tags'),
  characterSection: $('#character-section'),
  characterTags: $('#character-tags'),
  progressFill: $('.progress-fill'),
  progressText: $('.progress-text'),
  statusText: $('#status-text'),
  modal: $('#image-modal'),
  modalImage: $('#modal-image'),
  modalFav: $('#modal-fav'),
  modalDelete: $('#modal-delete'),
  settingsPanel: $('#settings-panel'),
  settingsSaveStatus: $('#settings-save-status'),
  detailToggleText: $('#detail-toggle-text'),
  toast: $('#toast'),
};

// ── 初始化 ──
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  bindEvents();
  initConfig().then(() => {
    updateSortUI();
    loadImages();
  });
});

function initTheme() {
  const saved = localStorage.getItem('tagify_theme') || 'light';
  state.theme = saved;
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeButtons();
}

function bindEvents() {
  // 搜索
  dom.searchInput.addEventListener('input', onSearchInput);
  dom.searchInput.addEventListener('keydown', onSearchKeydown);
  $('#btn-search').addEventListener('click', searchTags);
  document.addEventListener('click', (e) => {
    if (!dom.suggestDropdown.contains(e.target) && e.target !== dom.searchInput) {
      dom.suggestDropdown.classList.add('hidden');
    }
  });

  // 图片网格
  dom.imageGrid.addEventListener('click', onGridClick);
  dom.imageGrid.addEventListener('dblclick', onGridDblClick);

  // 排序
  $$('.sort-btn').forEach(btn => {
    btn.addEventListener('click', () => toggleSort(btn.dataset.sort));
  });

  // 显示详情切换
  dom.showDetailsCb.addEventListener('change', () => {
    state.showDetails = dom.showDetailsCb.checked;
    if (state.selectedImage) showImageDetail(state.selectedImage);
  });

  // 工具栏
  $('#btn-process').addEventListener('click', startProcess);
  $('#btn-gallery').addEventListener('click', showGallery);
  $('#btn-integrity').addEventListener('click', checkIntegrity);
  $('#btn-settings').addEventListener('click', openSettings);

  // 设置面板
  $('.settings-overlay').addEventListener('click', closeSettings);
  $('.settings-close').addEventListener('click', closeSettings);
  $$('.theme-option').forEach(btn => {
    btn.addEventListener('click', () => setTheme(btn.dataset.theme));
  });
  $('#btn-save-settings').addEventListener('click', saveSettings);
  $('#btn-reset-settings').addEventListener('click', resetSettings);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !dom.settingsPanel.classList.contains('hidden')) {
      closeSettings();
    }
  });

  // 原图弹窗
  $('.modal-close').addEventListener('click', closeModal);
  $('.modal-overlay').addEventListener('click', closeModal);
  dom.modalFav.addEventListener('click', toggleFavorite);
  dom.modalDelete.addEventListener('click', deleteImage);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !dom.modal.classList.contains('hidden')) closeModal();
  });
}

// ════════════════════════════════════════════════════
//  主题
// ════════════════════════════════════════════════════

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('tagify_theme', theme);
  updateThemeButtons();
}

function updateThemeButtons() {
  $$('.theme-option').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === state.theme);
  });
}

// ════════════════════════════════════════════════════
//  设置面板（读取 / 保存 / 恢复默认，即时生效）
// ════════════════════════════════════════════════════

async function initConfig() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    applyConfig(await res.json());
  } catch (e) { /* 加载失败时使用默认值 */ }
}

function applyConfig(cfg) {
  state.config = cfg;
  state.favoriteTag = cfg.behavior.favorite_tag;
  state.sortBy = cfg.behavior.default_sort;
  state.sortOrder = cfg.behavior.default_order;
  document.documentElement.style.setProperty('--thumb-size', cfg.ui.thumbnail_size[0] + 'px');
  updateDetailToggleLabel();
}

function updateDetailToggleLabel() {
  const cfg = state.config;
  if (!cfg || !dom.detailToggleText) return;
  const lo = Math.round(cfg.model.detail_tag_min * 100);
  const hi = Math.round(cfg.model.main_tag_threshold * 100);
  dom.detailToggleText.textContent = `显示更多标签 (${lo}%-${hi}%)`;
}

function openSettings() {
  const cfg = state.config;
  if (!cfg) { showToast('配置未加载，请刷新页面'); return; }
  $('#set-fav-tag').value = cfg.behavior.favorite_tag;
  $('#set-sfw-only').checked = !!cfg.behavior.sfw_only;
  $('#set-sort').value = cfg.behavior.default_sort;
  $('#set-order').value = cfg.behavior.default_order;
  $('#set-page-size').value = cfg.ui.page_size;
  $('#set-process-threshold').value = cfg.model.process_threshold;
  $('#set-main-threshold').value = cfg.model.main_tag_threshold;
  $('#set-detail-min').value = cfg.model.detail_tag_min;
  $('#set-default-threshold').value = cfg.model.default_threshold;
  $('#set-thumb-w').value = cfg.ui.thumbnail_size[0];
  $('#set-thumb-h').value = cfg.ui.thumbnail_size[1];
  $('#set-input-folder').value = cfg.paths.input_folder;
  $('#set-archive-folder').value = cfg.paths.archive_folder;
  dom.settingsSaveStatus.textContent = '';
  dom.settingsPanel.classList.remove('hidden');
}

function closeSettings() {
  dom.settingsPanel.classList.add('hidden');
}

async function saveSettings() {
  const payload = {
    behavior: {
      favorite_tag: $('#set-fav-tag').value.trim(),
      sfw_only: $('#set-sfw-only').checked,
      default_sort: $('#set-sort').value,
      default_order: $('#set-order').value,
    },
    ui: {
      page_size: parseInt($('#set-page-size').value, 10),
      thumbnail_size: [
        parseInt($('#set-thumb-w').value, 10),
        parseInt($('#set-thumb-h').value, 10),
      ],
    },
    model: {
      process_threshold: parseFloat($('#set-process-threshold').value),
      main_tag_threshold: parseFloat($('#set-main-threshold').value),
      detail_tag_min: parseFloat($('#set-detail-min').value),
      default_threshold: parseFloat($('#set-default-threshold').value),
    },
    paths: {
      input_folder: $('#set-input-folder').value.trim(),
      archive_folder: $('#set-archive-folder').value.trim(),
    },
  };

  try {
    const res = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      dom.settingsSaveStatus.textContent = data.detail || '保存失败';
      return;
    }
    applyConfig(data);
    showToast('设置已保存');
    closeSettings();
    state.currentPage = 1;
    loadImages();
  } catch (e) {
    dom.settingsSaveStatus.textContent = '保存失败，请检查网络';
  }
}

async function resetSettings() {
  if (!confirm('确定要恢复所有默认设置吗？')) return;
  try {
    const res = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reset_defaults: true }),
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.detail || '重置失败'); return; }
    applyConfig(data);
    showToast('已恢复默认设置');
    closeSettings();
    state.currentPage = 1;
    loadImages();
  } catch (e) { showToast('重置失败'); }
}

// ════════════════════════════════════════════════════
//  标签搜索
// ════════════════════════════════════════════════════

let suggestTimer = null;

function onSearchInput() {
  const val = dom.searchInput.value.trim();
  clearTimeout(suggestTimer);
  if (val.length < 1) {
    dom.suggestDropdown.classList.add('hidden');
    return;
  }
  suggestTimer = setTimeout(() => fetchSuggestions(val), 200);
}

function onSearchKeydown(e) {
  const items = $$('.suggest-item');
  let active = dom.suggestDropdown.querySelector('.suggest-item.active');
  const idx = active ? Array.from(items).indexOf(active) : -1;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (idx < items.length - 1) {
      if (active) active.classList.remove('active');
      items[idx + 1].classList.add('active');
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (idx > 0) {
      if (active) active.classList.remove('active');
      items[idx - 1].classList.add('active');
    }
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (active) {
      dom.searchInput.value = active.textContent;
      dom.suggestDropdown.classList.add('hidden');
    }
    searchTags();
  } else if (e.key === 'Escape') {
    dom.suggestDropdown.classList.add('hidden');
  }
}

async function fetchSuggestions(prefix) {
  try {
    const res = await fetch(`/api/tags/suggest?prefix=${encodeURIComponent(prefix)}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.length === 0) { dom.suggestDropdown.classList.add('hidden'); return; }

    dom.suggestDropdown.innerHTML = data.map(t => `<div class="suggest-item">${escHtml(t)}</div>`).join('');
    dom.suggestDropdown.classList.remove('hidden');

    dom.suggestDropdown.querySelectorAll('.suggest-item').forEach(item => {
      item.addEventListener('click', () => {
        dom.searchInput.value = item.textContent;
        dom.suggestDropdown.classList.add('hidden');
        searchTags();
      });
    });
  } catch (e) { /* ignore */ }
}

async function searchTags() {
  const q = dom.searchInput.value.trim();
  if (!q) return;

  try {
    const res = await fetch(`/api/tags/search?q=${encodeURIComponent(q)}`);
    const tags = await res.json();

    if (tags.length === 0) {
      dom.tagList.innerHTML = '<div class="tag-empty">未找到匹配标签</div>';
      return;
    }

    dom.tagList.innerHTML = tags.map(t => {
      const cls = getTagTextClass(t);
      return `
      <div class="tag-item" data-tag="${escHtml(t.tag)}">
        <span class="tag-name ${cls}" style="${cls ? 'font-weight:600' : ''}">${escHtml(t.display)}</span>
        <span class="tag-count">${t.count}</span>
      </div>`;
    }).join('');

    dom.tagList.querySelectorAll('.tag-item').forEach(item => {
      item.addEventListener('click', () => {
        state.viewMode = 'tag';
        state.currentTag = item.dataset.tag;
        state.currentPage = 1;
        loadImages();
      });
    });
  } catch (e) {
    showToast('搜索失败');
  }
}

// ════════════════════════════════════════════════════
//  图片加载
// ════════════════════════════════════════════════════

async function loadImages() {
  let url = `/api/images?page=${state.currentPage}&sort=${state.sortBy}&order=${state.sortOrder}`;
  if (state.viewMode === 'tag' && state.currentTag) {
    url += `&tag=${encodeURIComponent(state.currentTag)}`;
  }

  try {
    const res = await fetch(url);
    const data = await res.json();
    state.totalPages = data.total_pages;

    if (data.images.length === 0) {
      const msg = state.viewMode === 'gallery' ? '图库中没有图片' : `没有找到标签为 '${state.currentTag}' 的图片`;
      dom.imageGrid.innerHTML = `<div class="grid-empty">${msg}</div>`;
    } else {
      dom.imageGrid.innerHTML = data.images.map(name => `
        <div class="image-card" data-name="${escHtml(name)}">
          <img src="/api/images/${encodeURIComponent(name)}/thumbnail" alt="${escHtml(name)}" loading="lazy">
          <div class="card-name">${escHtml(name)}</div>
        </div>
      `).join('');
    }

    renderPagination();
  } catch (e) {
    dom.imageGrid.innerHTML = '<div class="grid-empty">加载失败</div>';
  }
}

function renderPagination() {
  if (state.totalPages <= 1) { dom.pagination.innerHTML = ''; return; }

  let html = '';
  html += `<button class="page-btn" ${state.currentPage <= 1 ? 'disabled' : ''}
    data-page="${state.currentPage - 1}">◀</button>`;

  const range = getPageRange(state.totalPages, state.currentPage);
  for (const p of range) {
    if (p === '...') {
      html += '<span class="page-ellipsis">...</span>';
    } else {
      html += `<button class="page-btn${p === state.currentPage ? ' active' : ''}" data-page="${p}">${p}</button>`;
    }
  }

  html += `<button class="page-btn" ${state.currentPage >= state.totalPages ? 'disabled' : ''}
    data-page="${state.currentPage + 1}">▶</button>`;

  dom.pagination.innerHTML = html;

  dom.pagination.querySelectorAll('.page-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = parseInt(btn.dataset.page);
      if (p >= 1 && p <= state.totalPages) {
        state.currentPage = p;
        loadImages();
        dom.imageGrid.scrollTop = 0;
      }
    });
  });
}

function getPageRange(total, current) {
  if (total <= 10) return Array.from({ length: total }, (_, i) => i + 1);
  const result = [1];
  const side = 4;
  if (current - side > 2) result.push('...');
  else if (current - side === 2) result.push(2);
  for (let i = Math.max(2, current - side); i <= Math.min(total - 1, current + side); i++) result.push(i);
  if (current + side < total - 1) result.push('...');
  else if (current + side === total - 1) result.push(total - 1);
  if (total > 1) result.push(total);
  return result;
}

// ════════════════════════════════════════════════════
//  图片详情 — 评级/角色独立区块
// ════════════════════════════════════════════════════

async function showImageDetail(name) {
  state.selectedImage = name;

  try {
    const res = await fetch(`/api/images/${encodeURIComponent(name)}`);
    const data = await res.json();

    dom.infoName.textContent = data.name;
    dom.infoSize.textContent = data.size_kb;
    dom.infoTime.textContent = data.process_time;
    dom.tagCount.textContent = `共 ${data.tags.length} 个标签`;

    // 分类标签（阈值来自服务器配置）
    const m = state.config ? state.config.model : null;
    const mainThreshold = m ? m.main_tag_threshold : 0.5;
    const detailMin = m ? m.detail_tag_min : 0.05;

    // SFW 模式下详情面板只展示 general 评级徽章，其余评级照常放入一般标签隐藏区
    const sfwOnly = !!(state.config && state.config.behavior.sfw_only);
    const ratingTags = data.tags.filter(t => t.is_rating && (!sfwOnly || t.tag === 'general'));
    const charTags = data.tags.filter(t => t.is_character && !t.is_rating);
    const mainTags = data.tags.filter(t => !t.is_rating && !t.is_character && t.confidence > mainThreshold);
    const detailTags = data.tags.filter(t =>
      !t.is_rating && !t.is_character && t.confidence > detailMin && t.confidence <= mainThreshold
    );

    // ── 评级区域 ──
    if (ratingTags.length > 0) {
      dom.ratingSection.classList.remove('hidden');
      dom.ratingTags.innerHTML = ratingTags.map(t => {
        const cls = getRatingBadgeClass(t.tag);
        return `<span class="tag-badge ${cls}" data-tag="${escHtml(t.tag)}">${escHtml(t.display)} <span class="badge-conf">${t.percent}</span></span>`;
      }).join('');
    } else {
      dom.ratingSection.classList.add('hidden');
    }

    // ── 角色区域 ──
    if (charTags.length > 0) {
      dom.characterSection.classList.remove('hidden');
      dom.characterTags.innerHTML = charTags.map(t =>
        `<span class="tag-badge character" data-tag="${escHtml(t.tag)}">${escHtml(t.display)} <span class="badge-conf">${t.percent}</span></span>`
      ).join('');
    } else {
      dom.characterSection.classList.add('hidden');
    }

    // 绑定评级/角色徽章点击事件
    dom.ratingTags.querySelectorAll('.tag-badge').forEach(badge => {
      badge.addEventListener('click', () => searchByTag(badge.dataset.tag));
    });
    dom.characterTags.querySelectorAll('.tag-badge').forEach(badge => {
      badge.addEventListener('click', () => searchByTag(badge.dataset.tag));
    });

    // ── 一般标签区域 ──
    let html = '';

    for (const tag of mainTags) {
      html += `<div class="tag-row" data-tag="${escHtml(tag.tag)}">
        <span class="tag-left"><span>${escHtml(tag.display)}</span></span>
        <span class="tag-conf">${tag.percent}</span></div>`;
    }

    if (state.showDetails && detailTags.length > 0) {
      html += '<div class="tag-separator">─ 更多标签 (5%-50%) ─</div>';
      for (const tag of detailTags) {
        html += `<div class="tag-row detail" data-tag="${escHtml(tag.tag)}" style="padding-left:20px">
          <span class="tag-left"><span>${escHtml(tag.display)}</span></span>
          <span class="tag-conf">${tag.percent}</span></div>`;
      }
    }

    dom.tagDetail.innerHTML = html || '<div class="detail-empty">无标签数据</div>';

    // 绑定一般标签点击
    dom.tagDetail.querySelectorAll('.tag-row').forEach(row => {
      row.addEventListener('click', () => searchByTag(row.dataset.tag));
    });

    // 更新弹窗
    dom.modalFav.textContent = data.is_favorite ? '取消收藏' : '收藏';

  } catch (e) {
    showToast('加载详情失败');
  }
}

function getRatingBadgeClass(tagName) {
  const name = tagName.toLowerCase();
  if (name === 'general') return 'rating-general';
  if (name === 'sensitive') return 'rating-sensitive';
  if (name === 'questionable') return 'rating-questionable';
  if (name === 'explicit') return 'rating-explicit';
  return 'rating-general';
}

// 标签列表文字着色：评级/角色用主题 CSS 变量，一般标签用默认文字色（明暗主题均清晰）
function getTagTextClass(t) {
  if (t.category === 9) return 'rating-text-' + getRatingBadgeClass(t.tag).replace('rating-', '');
  if (t.category === 4) return 'char-text';
  return '';
}

function searchByTag(tag) {
  dom.searchInput.value = tag;
  state.viewMode = 'tag';
  state.currentTag = tag;
  state.currentPage = 1;
  loadImages();
  searchTags();
}

// ════════════════════════════════════════════════════
//  图片交互
// ════════════════════════════════════════════════════

function onGridClick(e) {
  const card = e.target.closest('.image-card');
  if (!card) return;
  showImageDetail(card.dataset.name);
}

function onGridDblClick(e) {
  const card = e.target.closest('.image-card');
  if (!card) return;
  openModal(card.dataset.name);
}

function openModal(name) {
  dom.modalImage.src = `/gallery/${encodeURIComponent(name)}`;
  dom.modal.dataset.imageName = name;
  dom.modal.classList.remove('hidden');
  showImageDetail(name);
}

function closeModal() {
  dom.modal.classList.add('hidden');
}

async function toggleFavorite() {
  const name = dom.modal.dataset.imageName;
  if (!name) return;
  try {
    const res = await fetch(`/api/images/${encodeURIComponent(name)}/favorite`, { method: 'POST' });
    const data = await res.json();
    dom.modalFav.textContent = data.favorite ? '取消收藏' : '收藏';
    showImageDetail(name);
  } catch (e) { showToast('操作失败'); }
}

async function deleteImage() {
  const name = dom.modal.dataset.imageName;
  if (!name || !confirm('确定要永久删除这张图片吗？')) return;
  try {
    await fetch(`/api/images/${encodeURIComponent(name)}`, { method: 'DELETE' });
    closeModal();
    // 清除右侧面板
    dom.ratingSection.classList.add('hidden');
    dom.characterSection.classList.add('hidden');
    dom.tagDetail.innerHTML = '<div class="detail-empty">点击图片查看标签详情</div>';
    dom.infoName.textContent = '-';
    dom.infoSize.textContent = '-';
    dom.infoTime.textContent = '-';
    loadImages();
    showToast('删除成功');
  } catch (e) { showToast('删除失败'); }
}

// ════════════════════════════════════════════════════
//  排序 + 视图切换
// ════════════════════════════════════════════════════

function updateSortUI() {
  const arrows = { ASC: ' ▲', DESC: ' ▼' };
  $$('.sort-btn').forEach(b => {
    const base = b.textContent.replace(/ [▲▼]$/, '');
    const isActive = b.dataset.sort === state.sortBy;
    b.classList.toggle('active', isActive);
    b.textContent = isActive ? base + arrows[state.sortOrder] : base;
  });
}

function toggleSort(field) {
  if (state.sortBy === field) {
    state.sortOrder = state.sortOrder === 'ASC' ? 'DESC' : 'ASC';
  } else {
    state.sortBy = field;
    state.sortOrder = 'DESC';
  }
  updateSortUI();
  state.currentPage = 1;
  loadImages();
}

function showGallery() {
  state.viewMode = 'gallery';
  state.currentTag = null;
  state.currentPage = 1;
  dom.searchInput.value = '';
  dom.tagList.innerHTML = '<div class="tag-empty">输入关键词搜索标签</div>';
  loadImages();
}

// ════════════════════════════════════════════════════
//  批量处理 + 完整性检查
// ════════════════════════════════════════════════════

async function startProcess() {
  try {
    const res = await fetch('/api/process', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || '启动失败');
      return;
    }
    pollProcessStatus();
  } catch (e) { showToast('启动处理失败'); }
}

function pollProcessStatus() {
  const interval = setInterval(async () => {
    try {
      const res = await fetch('/api/process/status');
      const status = await res.json();

      dom.progressFill.style.width = (status.progress || 0) + '%';
      dom.progressText.textContent = status.message || '';
      dom.statusText.textContent = status.running ? '处理中...' : '';

      if (!status.running && status.progress >= 100) {
        clearInterval(interval);
        dom.statusText.textContent = '处理完成';
        loadImages();
        setTimeout(() => {
          dom.progressFill.style.width = '0%';
          dom.progressText.textContent = '';
          dom.statusText.textContent = '';
        }, 3000);
      } else if (!status.running) {
        clearInterval(interval);
        dom.statusText.textContent = status.message || '';
      }
    } catch (e) { clearInterval(interval); }
  }, 500);
}

async function checkIntegrity() {
  try {
    const res = await fetch('/api/check-integrity');
    const data = await res.json();
    alert(data.report);
  } catch (e) { showToast('检查失败'); }
}

// ════════════════════════════════════════════════════
//  工具
// ════════════════════════════════════════════════════

function showToast(msg) {
  dom.toast.textContent = msg;
  dom.toast.classList.remove('hidden');
  setTimeout(() => dom.toast.classList.add('hidden'), 2500);
}

function escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
