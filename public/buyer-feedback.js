(function () {
  'use strict';

  // ---- Config ----
  const SUPABASE_URL = window.__SUPABASE_URL;
  const SUPABASE_KEY = window.__SUPABASE_ANON_KEY;
  // Write directly to Supabase REST API — no localhost dependency
  var SB_PATCH_HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
  };
  const SB_HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json'
  };

  // ---- Inject CSS ----
  var style = document.createElement('style');
  style.textContent = [
    '.buyer-feedback-panel {',
    '  border-top: 1px solid #30363d;',
    '  padding: 8px 12px;',
    '  margin-top: 8px;',
    '}',
    '.feedback-buttons {',
    '  display: flex;',
    '  gap: 8px;',
    '  align-items: center;',
    '}',
    '.feedback-btn {',
    '  width: 30px;',
    '  height: 30px;',
    '  border-radius: 50%;',
    '  border: 1px solid #30363d;',
    '  background: #21262d;',
    '  color: #8b949e;',
    '  font-size: 14px;',
    '  cursor: pointer;',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  transition: all 0.15s;',
    '  padding: 0;',
    '  line-height: 1;',
    '}',
    '.feedback-btn:hover {',
    '  background: #30363d;',
    '  color: #e6edf3;',
    '}',
    '.feedback-btn.accept {',
    '  border-color: #238636;',
    '}',
    '.feedback-btn.accept.active {',
    '  background: #238636;',
    '  color: #fff;',
    '}',
    '.feedback-btn.reject {',
    '  border-color: #da3633;',
    '}',
    '.feedback-btn.reject.active {',
    '  background: #da3633;',
    '  color: #fff;',
    '}',
    '.feedback-comment-area {',
    '  margin-top: 8px;',
    '}',
    '.feedback-comment-area textarea {',
    '  width: 100%;',
    '  background: #0d1117;',
    '  border: 1px solid #30363d;',
    '  border-radius: 6px;',
    '  color: #e6edf3;',
    '  font-size: 12px;',
    '  padding: 6px 8px;',
    '  resize: vertical;',
    '  font-family: inherit;',
    '  box-sizing: border-box;',
    '}',
    '.feedback-comment-area textarea:focus {',
    '  outline: none;',
    '  border-color: #58a6ff;',
    '}',
    '.feedback-meta {',
    '  display: flex;',
    '  align-items: center;',
    '  gap: 8px;',
    '  margin-top: 6px;',
    '}',
    '.feedback-expert-name {',
    '  background: #0d1117;',
    '  border: 1px solid #30363d;',
    '  border-radius: 6px;',
    '  color: #c9d1d9;',
    '  font-size: 12px;',
    '  padding: 4px 8px;',
    '  flex: 1;',
    '}',
    '.feedback-expert-name:focus {',
    '  outline: none;',
    '  border-color: #58a6ff;',
    '}',
    '.feedback-save-btn {',
    '  background: #21262d;',
    '  border: 1px solid #30363d;',
    '  border-radius: 6px;',
    '  color: #c9d1d9;',
    '  font-size: 12px;',
    '  font-weight: 600;',
    '  padding: 4px 12px;',
    '  cursor: pointer;',
    '  transition: all 0.15s;',
    '  white-space: nowrap;',
    '}',
    '.feedback-save-btn:hover {',
    '  border-color: #58a6ff;',
    '  color: #58a6ff;',
    '}',
    '.feedback-save-btn:disabled {',
    '  opacity: 0.5;',
    '  cursor: not-allowed;',
    '}',
    '.feedback-existing {',
    '  display: flex;',
    '  align-items: baseline;',
    '  flex-wrap: wrap;',
    '  gap: 6px;',
    '  margin-top: 6px;',
    '}',
    '.feedback-verdict-badge {',
    '  display: inline-block;',
    '  border-radius: 12px;',
    '  padding: 1px 9px;',
    '  font-size: 11px;',
    '  font-weight: 700;',
    '  text-transform: uppercase;',
    '  letter-spacing: 0.04em;',
    '}',
    '.feedback-verdict-badge.badge-accept {',
    '  background: #238636;',
    '  color: #fff;',
    '}',
    '.feedback-verdict-badge.badge-reject {',
    '  background: #da3633;',
    '  color: #fff;',
    '}',
    '.feedback-comment-text {',
    '  color: #8b949e;',
    '  font-size: 12px;',
    '  font-style: italic;',
    '}',
    '.feedback-expert-label {',
    '  color: #6e7681;',
    '  font-size: 11px;',
    '}'
  ].join('\n');
  document.head.appendChild(style);

  // ---- Helpers ----
  function buildPanel(buyerId) {
    var panel = document.createElement('div');
    panel.className = 'buyer-feedback-panel';
    panel.dataset.buyerId = buyerId;

    panel.innerHTML =
      '<div class="feedback-buttons">' +
        '<button class="feedback-btn accept" title="Accept">&#10003;</button>' +
        '<button class="feedback-btn reject" title="Reject">&#10007;</button>' +
      '</div>' +
      '<div class="feedback-comment-area" style="display:none">' +
        '<textarea placeholder="Expert notes on this buyer..." rows="2"></textarea>' +
        '<div class="feedback-meta">' +
          '<select class="feedback-expert-name">' +
            '<option value="">Who\'s commenting?</option>' +
            '<option value="Debbie">Debbie</option>' +
            '<option value="Mark">Mark</option>' +
            '<option value="Ewing">Ewing</option>' +
            '<option value="John">John</option>' +
          '</select>' +
          '<button class="feedback-save-btn">Save</button>' +
        '</div>' +
      '</div>' +
      '<div class="feedback-existing" style="display:none">' +
        '<span class="feedback-verdict-badge"></span>' +
        '<span class="feedback-comment-text"></span>' +
        '<span class="feedback-expert-label"></span>' +
      '</div>';

    wirePanel(panel, buyerId);
    return panel;
  }

  function wirePanel(panel, buyerId) {
    var acceptBtn = panel.querySelector('.feedback-btn.accept');
    var rejectBtn = panel.querySelector('.feedback-btn.reject');
    var commentArea = panel.querySelector('.feedback-comment-area');
    var saveBtn = panel.querySelector('.feedback-save-btn');
    var textarea = panel.querySelector('textarea');
    var expertSelect = panel.querySelector('.feedback-expert-name');
    var existingDiv = panel.querySelector('.feedback-existing');

    var currentVerdict = null;

    function setVerdict(v) {
      if (currentVerdict === v) {
        // deselect
        currentVerdict = null;
        acceptBtn.classList.remove('active');
        rejectBtn.classList.remove('active');
        commentArea.style.display = 'none';
        return;
      }
      currentVerdict = v;
      if (v === 'accept') {
        acceptBtn.classList.add('active');
        rejectBtn.classList.remove('active');
      } else {
        rejectBtn.classList.add('active');
        acceptBtn.classList.remove('active');
      }
      commentArea.style.display = 'block';
    }

    acceptBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      setVerdict('accept');
    });

    rejectBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      setVerdict('reject');
    });

    saveBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (!currentVerdict) {
        alert('Please select Accept or Reject first.');
        return;
      }
      var expertName = expertSelect.value;
      var comment = textarea.value.trim();

      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';

      fetch(SUPABASE_URL + '/rest/v1/engagement_buyers?id=eq.' + encodeURIComponent(buyerId), {
        method: 'PATCH',
        headers: SB_PATCH_HEADERS,
        body: JSON.stringify({
          expert_verdict: currentVerdict,
          expert_comment: comment,
          expert_name: expertName,
          expert_verdict_at: new Date().toISOString()
        })
      })
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then(function () {
          commentArea.style.display = 'none';
          showExisting(panel, currentVerdict, comment, expertName);
        })
        .catch(function (err) {
          console.error('[buyer-feedback] Save failed:', err);
          saveBtn.textContent = 'Retry';
          saveBtn.disabled = false;
          alert('Save failed: ' + err.message);
        });
    });

    // Stop clicks inside the panel from bubbling to card click handlers
    panel.addEventListener('click', function (e) {
      e.stopPropagation();
    });
  }

  function showExisting(panel, verdict, comment, expertName) {
    var existingDiv = panel.querySelector('.feedback-existing');
    var badge = panel.querySelector('.feedback-verdict-badge');
    var commentEl = panel.querySelector('.feedback-comment-text');
    var expertEl = panel.querySelector('.feedback-expert-label');

    badge.className = 'feedback-verdict-badge badge-' + verdict;
    badge.textContent = verdict === 'accept' ? 'Accepted' : 'Rejected';
    commentEl.textContent = comment || '';
    expertEl.textContent = expertName ? '— ' + expertName : '';

    existingDiv.style.display = 'flex';

    // Reflect on buttons without reopening comment area
    var acceptBtn = panel.querySelector('.feedback-btn.accept');
    var rejectBtn = panel.querySelector('.feedback-btn.reject');
    if (verdict === 'accept') {
      acceptBtn.classList.add('active');
      rejectBtn.classList.remove('active');
    } else {
      rejectBtn.classList.add('active');
      acceptBtn.classList.remove('active');
    }
  }

  // ---- Fetch existing feedback from Supabase ----
  function loadFeedbackForBuyer(buyerId, panel) {
    if (!buyerId) return;
    fetch(
      SUPABASE_URL + '/rest/v1/engagement_buyers?id=eq.' + encodeURIComponent(buyerId) +
      '&select=id,expert_comment,expert_verdict,expert_name,expert_verdict_at',
      { headers: SB_HEADERS }
    )
      .then(function (res) { return res.json(); })
      .then(function (rows) {
        if (!rows || rows.length === 0) return;
        var row = rows[0];
        if (row.expert_verdict) {
          showExisting(panel, row.expert_verdict, row.expert_comment || '', row.expert_name || '');
        }
      })
      .catch(function (err) {
        console.warn('[buyer-feedback] Could not load feedback for', buyerId, err);
      });
  }

  // ---- Inject panels into buyer cards ----
  function injectIntoCards() {
    var cards = document.querySelectorAll('.buyer-card[data-buyer-id]');
    cards.forEach(function (card) {
      // Skip if already injected
      if (card.querySelector('.buyer-feedback-panel')) return;
      var buyerId = card.dataset.buyerId;
      if (!buyerId) return;
      var panel = buildPanel(buyerId);
      card.appendChild(panel);
      loadFeedbackForBuyer(buyerId, panel);
    });
  }

  // ---- Dossier page support ----
  // Single-buyer dossier pages have class .page; buyer ID from URL or meta tag
  function getDossierBuyerId() {
    // 1. URL param ?buyer_id=xxx
    var params = new URLSearchParams(window.location.search);
    if (params.get('buyer_id')) return params.get('buyer_id');
    // 2. Meta tag <meta name="buyer-id" content="xxx">
    var meta = document.querySelector('meta[name="buyer-id"]');
    if (meta && meta.content) return meta.content;
    // 3. data-buyer-id on .page element
    var page = document.querySelector('.page[data-buyer-id]');
    if (page) return page.dataset.buyerId;
    return null;
  }

  function injectIntoDossier() {
    var page = document.querySelector('.page');
    if (!page) return;
    // Already injected
    if (page.querySelector('.buyer-feedback-panel')) return;
    var buyerId = getDossierBuyerId();
    if (!buyerId) return;
    var panel = buildPanel(buyerId);
    page.appendChild(panel);
    loadFeedbackForBuyer(buyerId, panel);
  }

  // ---- Table row support (meeting prep pages) ----
  // Finds buyer tables, looks up IDs by name from Supabase, injects feedback per row
  function injectIntoTableRows() {
    // Find tables with buyer data — look for header "Buyer" in first th
    var tables = document.querySelectorAll('table');
    tables.forEach(function (table) {
      if (table.dataset.feedbackInjected) return;
      var headers = table.querySelectorAll('th');
      var buyerColIdx = -1;
      for (var i = 0; i < headers.length; i++) {
        if (headers[i].textContent.trim().toLowerCase() === 'buyer') {
          buyerColIdx = i;
          break;
        }
      }
      if (buyerColIdx < 0) return;

      table.dataset.feedbackInjected = 'true';

      // Add Verdict + Comment columns to header
      var headerRow = table.querySelector('tr');
      var thVerdict = document.createElement('th');
      thVerdict.textContent = 'Verdict';
      headerRow.appendChild(thVerdict);
      var thComment = document.createElement('th');
      thComment.textContent = 'Expert Notes';
      thComment.style.minWidth = '200px';
      headerRow.appendChild(thComment);

      // Collect buyer names from rows
      var rows = table.querySelectorAll('tr');
      var buyerNames = [];
      for (var r = 1; r < rows.length; r++) {
        var cells = rows[r].querySelectorAll('td');
        if (cells.length > buyerColIdx) {
          buyerNames.push({ row: rows[r], name: cells[buyerColIdx].textContent.trim() });
        }
      }
      if (buyerNames.length === 0) return;

      // Look up buyer IDs from Supabase by name
      // Get proposal_id from URL or page meta
      var params = new URLSearchParams(window.location.search);
      var proposalId = params.get('proposal_id') || '';

      // Fetch all engagement_buyers for this proposal (or all if no proposal_id)
      var fetchUrl = SUPABASE_URL + '/rest/v1/engagement_buyers?select=id,buyer_company_name,expert_comment,expert_verdict,expert_name';
      if (proposalId) {
        fetchUrl += '&proposal_id=eq.' + encodeURIComponent(proposalId);
      }
      fetchUrl += '&limit=500';

      fetch(fetchUrl, { headers: SB_HEADERS })
        .then(function (res) { return res.json(); })
        .then(function (buyers) {
          // Build name → buyer lookup (fuzzy match)
          var buyerMap = {};
          buyers.forEach(function (b) {
            buyerMap[b.buyer_company_name.toLowerCase()] = b;
            // Also index by first word for fuzzy matching
            var firstWord = b.buyer_company_name.toLowerCase().split(/[\s(]/)[0];
            if (!buyerMap[firstWord]) buyerMap[firstWord] = b;
          });

          buyerNames.forEach(function (entry) {
            var name = entry.name.toLowerCase();
            var match = buyerMap[name];
            // Try fuzzy: first word, or contains
            if (!match) {
              var firstWord = name.split(/[\s(\/]/)[0];
              match = buyerMap[firstWord];
            }
            if (!match) {
              // Try substring match
              for (var key in buyerMap) {
                if (key.indexOf(name) >= 0 || name.indexOf(key) >= 0) {
                  match = buyerMap[key];
                  break;
                }
              }
            }

            // Add verdict cell
            var tdVerdict = document.createElement('td');
            tdVerdict.style.whiteSpace = 'nowrap';

            // Add comment cell
            var tdComment = document.createElement('td');

            if (match && match.id) {
              // Verdict buttons
              var acceptBtn = document.createElement('button');
              acceptBtn.className = 'feedback-btn accept';
              acceptBtn.innerHTML = '&#10003;';
              acceptBtn.title = 'Accept';
              acceptBtn.style.marginRight = '4px';

              var rejectBtn = document.createElement('button');
              rejectBtn.className = 'feedback-btn reject';
              rejectBtn.innerHTML = '&#10007;';
              rejectBtn.title = 'Reject';

              var currentVerdict = match.expert_verdict || null;

              // Show existing verdict
              if (currentVerdict === 'accept') acceptBtn.classList.add('active');
              if (currentVerdict === 'reject') rejectBtn.classList.add('active');

              var buyerId = match.id;

              function makeVerdictHandler(btn, verdict, otherBtn, bId, commentInput, nameSelect) {
                return function (e) {
                  e.stopPropagation();
                  if (btn.classList.contains('active')) {
                    btn.classList.remove('active');
                    currentVerdict = null;
                  } else {
                    btn.classList.add('active');
                    otherBtn.classList.remove('active');
                    currentVerdict = verdict;
                    // Auto-save verdict immediately
                    fetch(SUPABASE_URL + '/rest/v1/engagement_buyers?id=eq.' + encodeURIComponent(bId), {
                      method: 'PATCH',
                      headers: SB_PATCH_HEADERS,
                      body: JSON.stringify({
                        expert_verdict: verdict,
                        expert_name: nameSelect.value || 'Debbie',
                        expert_verdict_at: new Date().toISOString()
                      })
                    }).catch(function () {});
                  }
                };
              }

              // Comment input
              var commentInput = document.createElement('input');
              commentInput.type = 'text';
              commentInput.placeholder = 'Notes...';
              commentInput.value = match.expert_comment || '';
              commentInput.style.cssText = 'width:100%;background:#f8f9fa;border:1px solid #ddd;border-radius:4px;padding:4px 6px;font-size:12px;';

              // Expert name select (compact)
              var nameSelect = document.createElement('select');
              nameSelect.style.cssText = 'background:#f8f9fa;border:1px solid #ddd;border-radius:4px;padding:2px 4px;font-size:11px;margin-left:4px;';
              ['Debbie', 'Mark', 'Ewing', 'John'].forEach(function (n) {
                var opt = document.createElement('option');
                opt.value = n;
                opt.textContent = n;
                if (match.expert_name === n) opt.selected = true;
                nameSelect.appendChild(opt);
              });

              acceptBtn.addEventListener('click', makeVerdictHandler(acceptBtn, 'accept', rejectBtn, buyerId, commentInput, nameSelect));
              rejectBtn.addEventListener('click', makeVerdictHandler(rejectBtn, 'reject', acceptBtn, buyerId, commentInput, nameSelect));

              // Save comment on blur
              commentInput.addEventListener('blur', function () {
                var comment = commentInput.value.trim();
                if (comment || currentVerdict) {
                  fetch(SUPABASE_URL + '/rest/v1/engagement_buyers?id=eq.' + encodeURIComponent(buyerId), {
                    method: 'PATCH',
                    headers: SB_PATCH_HEADERS,
                    body: JSON.stringify({
                      expert_comment: comment,
                      expert_name: nameSelect.value || 'Debbie',
                      expert_verdict_at: new Date().toISOString()
                    })
                  }).catch(function () {});
                }
              });

              tdVerdict.appendChild(acceptBtn);
              tdVerdict.appendChild(rejectBtn);
              tdVerdict.appendChild(nameSelect);

              tdComment.appendChild(commentInput);
            } else {
              tdVerdict.textContent = '—';
              tdComment.style.color = '#999';
              tdComment.style.fontSize = '11px';
              tdComment.textContent = 'Not in buyer list';
            }

            entry.row.appendChild(tdVerdict);
            entry.row.appendChild(tdComment);
          });
        })
        .catch(function (err) {
          console.warn('[buyer-feedback] Table lookup failed:', err);
        });
    });
  }

  // ---- MutationObserver to catch dynamically rendered cards ----
  var observer = null;

  function startObserver() {
    if (observer) return;
    observer = new MutationObserver(function () {
      injectIntoCards();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // ---- Init ----
  function init() {
    injectIntoCards();
    injectIntoDossier();
    injectIntoTableRows();
    startObserver();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
