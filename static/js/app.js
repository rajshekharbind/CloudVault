/* CloudVault App JS */

// ---- Theme Init ----
(function() {
  const saved = localStorage.getItem('cv_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
})();

document.addEventListener('DOMContentLoaded', () => {
  // Theme toggle
  const themeBtn = document.getElementById('themeToggleBtn');
  const themeIcon = document.getElementById('themeIcon');
  if (themeBtn) {
    const applyTheme = (t) => {
      document.documentElement.setAttribute('data-theme', t);
      localStorage.setItem('cv_theme', t);
      if (themeIcon) {
        themeIcon.className = t === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
      }
    };
    const cur = () => document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(cur());
    themeBtn.addEventListener('click', () => applyTheme(cur() === 'dark' ? 'light' : 'dark'));
  }

  initDropzone();
  initShareModal();
  initPreviewModal();
});

// ---- Drag & Drop Upload ----
function initDropzone() {
  const dz = document.getElementById('uploadDropzone');
  const fi = document.getElementById('uploadFileInput');
  if (!dz || !fi) return;

  ['dragenter', 'dragover'].forEach(ev => {
    dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('over'); }, false);
  });
  ['dragleave', 'drop'].forEach(ev => {
    dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('over'); }, false);
  });
  dz.addEventListener('drop', e => {
    if (e.dataTransfer.files.length) doUpload(e.dataTransfer.files);
  });
  fi.addEventListener('change', () => { if (fi.files.length) doUpload(fi.files); });
}

function doUpload(files) {
  const folderId = (document.getElementById('currentFolderId') || {}).value || '';
  const fd = new FormData();
  Array.from(files).forEach(f => fd.append('files', f));
  if (folderId) fd.append('folder_id', folderId);

  const progCont = document.getElementById('uploadProgressContainer');
  const progBar = document.getElementById('uploadProgressBar');
  const status = document.getElementById('uploadStatusText');

  if (progCont) progCont.classList.remove('d-none');
  if (status) status.textContent = 'Uploading…';

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/files/upload/', true);
  xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));

  xhr.upload.onprogress = e => {
    if (e.lengthComputable && progBar) {
      const pct = Math.round(e.loaded / e.total * 100);
      progBar.style.width = pct + '%';
      if (status) status.textContent = `Uploading… ${pct}%`;
    }
  };

  xhr.onload = () => {
    if (xhr.status === 201) {
      showToast('Uploaded', 'File(s) uploaded successfully!', 'success');
      bootstrap.Modal.getInstance(document.getElementById('uploadModal'))?.hide();
      setTimeout(() => location.reload(), 600);
    } else {
      let msg = 'Upload failed.';
      try { msg = JSON.parse(xhr.responseText).error || msg; } catch(e) {}
      showToast('Error', msg, 'danger');
      if (progCont) progCont.classList.add('d-none');
    }
  };
  xhr.onerror = () => showToast('Error', 'Network error during upload.', 'danger');
  xhr.send(fd);
}

// ---- Share Modal ----
function initShareModal() {
  window.openShareModal = function(fileId, fileName) {
    document.getElementById('shareFileId').value = fileId;
    document.getElementById('shareTargetName').textContent = fileName;
    document.getElementById('shareResultArea').classList.add('d-none');
    document.getElementById('sharePassword').value = '';
    document.getElementById('shareExpiryDays').value = '';
    new bootstrap.Modal(document.getElementById('shareModal')).show();
  };

  document.getElementById('generateShareBtn')?.addEventListener('click', () => {
    const payload = {
      file_id:         document.getElementById('shareFileId').value,
      access_type:     document.getElementById('shareAccessType').value,
      permission:      document.getElementById('sharePermission').value,
      password:        document.getElementById('sharePassword').value || null,
      expires_in_days: document.getElementById('shareExpiryDays').value || null,
    };
    fetch('/api/shares/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
      if (data.token) {
        const url = `${location.origin}/s/${data.token}/`;
        document.getElementById('shareInputUrl').value = url;
        document.getElementById('shareResultArea').classList.remove('d-none');
        showToast('Link Created', 'Share link generated!', 'success');
      } else {
        showToast('Error', data.error || 'Failed to create link', 'danger');
      }
    });
  });

  document.getElementById('copyShareUrlBtn')?.addEventListener('click', () => {
    const v = document.getElementById('shareInputUrl').value;
    navigator.clipboard.writeText(v).then(() => showToast('Copied!', 'URL copied to clipboard', 'info'));
  });
}

// ---- Preview Modal ----
function initPreviewModal() {
  window.openPreviewModal = function(fileId, fileName, fileType, fileUrl) {
    const modal = new bootstrap.Modal(document.getElementById('previewModal'));
    document.getElementById('previewModalTitle').textContent = fileName;
    const cont = document.getElementById('previewContentContainer');
    const actions = document.getElementById('previewModalActions');

    cont.innerHTML = '<div style="height:300px;display:flex;align-items:center;justify-content:center"><div class="spinner-border text-primary"></div></div>';
    actions.innerHTML = `<a href="/files/${fileId}/download/" class="btn btn-sm btn-outline-secondary"><i class="bi bi-download me-1"></i>Download</a>
                         <button class="btn btn-sm btn-brand" onclick="openShareModal(${fileId}, '${escHtml(fileName)}')"><i class="bi bi-share me-1"></i>Share</button>`;
    modal.show();

    switch (fileType) {
      case 'image':
        cont.innerHTML = `<img src="${fileUrl}" class="img-fluid rounded" style="max-height:520px;width:auto" alt="${escHtml(fileName)}">`;
        break;
      case 'video':
        cont.innerHTML = `<video controls autoplay class="w-100 rounded" style="max-height:500px"><source src="${fileUrl}">Browser does not support video.</video>`;
        break;
      case 'audio':
        cont.innerHTML = `<div class="py-5"><i class="bi bi-disc-fill" style="font-size:4rem;color:var(--brand-1);display:block;margin-bottom:1.5rem"></i><audio controls autoplay class="w-100"><source src="${fileUrl}">Browser does not support audio.</audio></div>`;
        break;
      case 'pdf':
        cont.innerHTML = `<iframe src="${fileUrl}" style="width:100%;height:520px;border:none;border-radius:8px"></iframe>`;
        break;
      case 'code':
      case 'text':
        fetch(`/files/${fileId}/preview/`).then(r => r.json()).then(d => {
          if (d.content) {
            cont.innerHTML = `<pre class="text-start p-3 rounded" style="background:var(--bg-body);max-height:480px;overflow:auto;font-size:.825rem;color:#e6edf3"><code>${escHtml(d.content)}</code></pre>`;
          } else {
            cont.innerHTML = noPreview(fileId);
          }
        }).catch(() => { cont.innerHTML = noPreview(fileId); });
        break;
      default:
        cont.innerHTML = noPreview(fileId);
    }
  };
}

function noPreview(fileId) {
  return `<div class="py-5"><i class="bi bi-file-earmark-x" style="font-size:3.5rem;color:var(--text-muted);display:block;margin-bottom:1rem"></i>
          <p style="color:var(--text-muted)">Preview not available for this file type.</p>
          <a href="/files/${fileId}/download/" class="btn-brand d-inline-flex"><i class="bi bi-download me-2"></i>Download File</a></div>`;
}

// ---- Utility functions ----
function getCookie(name) {
  for (const c of document.cookie.split(';')) {
    const [k, v] = c.trim().split('=');
    if (k === name) return decodeURIComponent(v);
  }
  return null;
}

function showToast(title, message, type = 'info') {
  const cont = document.getElementById('toastContainer');
  if (!cont) return;
  const id = 'toast_' + Date.now();
  const bgMap = { success: '#22c55e', danger: '#ef4444', warning: '#f59e0b', info: '#6366f1' };
  const bg = bgMap[type] || bgMap.info;
  cont.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="toast align-items-center border-0 shadow" role="alert" style="background:${bg};color:#fff;border-radius:10px;min-width:260px">
      <div class="d-flex">
        <div class="toast-body"><strong>${title}:</strong> ${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>`);
  new bootstrap.Toast(document.getElementById(id), { delay: 4000 }).show();
}

function escHtml(t) {
  return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
