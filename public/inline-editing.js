/**
 * Universal Inline Editing System
 * Apply to any text element: click Edit → becomes textarea → Save/Cancel
 * Persists to localStorage and Supabase automatically
 */

class InlineEditor {
  constructor() {
    this.editingElement = null;
    this.originalContent = null;
    this.storageKey = 'inline-edits-' + window.location.pathname;
    this.initEditableElements();
    this.loadEditHistory();
  }

  initEditableElements() {
    // Find all elements with data-editable attribute
    document.querySelectorAll('[data-editable="true"]').forEach((el, index) => {
      const editableId = el.getAttribute('data-editable-id') || `editable-${index}`;
      el.setAttribute('data-editable-id', editableId);
      this.addEditButton(el, editableId);
    });

    // Also detect common content containers if no explicit attribute
    document.querySelectorAll('.section p, .proposal-section, .summary-box, [contenteditable], .auto-generated').forEach((el, index) => {
      if (!el.hasAttribute('data-editable-id')) {
        const editableId = `auto-editable-${index}`;
        el.setAttribute('data-editable-id', editableId);
        this.addEditButton(el, editableId);
      }
    });
  }

  addEditButton(element, editableId) {
    // Don't add button if already present
    if (element.querySelector('.edit-toggle-btn')) return;

    // Create edit button
    const editBtn = document.createElement('button');
    editBtn.className = 'edit-toggle-btn';
    editBtn.setAttribute('data-editable-id', editableId);
    editBtn.innerHTML = '✎ Edit';
    editBtn.title = 'Click to edit this content';

    // Insert button at start of element or in parent
    if (element.children.length === 0) {
      // Text node, insert as sibling
      element.parentElement.insertBefore(editBtn, element.nextSibling);
    } else {
      // Has children, insert at top
      element.insertBefore(editBtn, element.firstChild);
    }

    // Click handler
    editBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.startEditing(element, editableId);
    });
  }

  startEditing(element, editableId) {
    // Store original
    this.originalContent = element.innerHTML;
    this.editingElement = element;

    // Get current text (excluding button)
    let currentText = element.innerText || element.textContent;
    const editBtn = element.querySelector('.edit-toggle-btn');
    if (editBtn) {
      currentText = currentText.replace(editBtn.innerText, '').trim();
    }

    // Create textarea
    const textarea = document.createElement('textarea');
    textarea.className = 'inline-editor-textarea';
    textarea.value = currentText;
    textarea.setAttribute('data-editable-id', editableId);

    // Create control buttons
    const controls = document.createElement('div');
    controls.className = 'inline-editor-controls';
    controls.innerHTML = `
      <button class="editor-save-btn" data-editable-id="${editableId}">✓ Save</button>
      <button class="editor-cancel-btn" data-editable-id="${editableId}">✕ Cancel</button>
    `;

    // Hide original content
    element.style.display = 'none';

    // Insert editor into DOM
    element.parentElement.insertBefore(textarea, element);
    element.parentElement.insertBefore(controls, element);

    // Focus textarea
    textarea.focus();
    textarea.select();

    // Save button
    controls.querySelector('.editor-save-btn').addEventListener('click', () => {
      this.saveEdit(element, editableId, textarea.value);
    });

    // Cancel button
    controls.querySelector('.editor-cancel-btn').addEventListener('click', () => {
      this.cancelEdit(element, textarea, controls);
    });

    // Keyboard shortcuts
    textarea.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.key === 'Enter') {
        this.saveEdit(element, editableId, textarea.value);
      } else if (e.key === 'Escape') {
        this.cancelEdit(element, textarea, controls);
      }
    });

    // Auto-save on blur (optional - can disable)
    textarea.addEventListener('blur', () => {
      // Wait a moment to see if user clicked Save/Cancel
      setTimeout(() => {
        if (document.contains(textarea)) {
          // User didn't click Save/Cancel, auto-save
          this.saveEdit(element, editableId, textarea.value);
        }
      }, 200);
    });
  }

  saveEdit(element, editableId, newContent) {
    // Update element
    element.innerHTML = newContent;
    element.style.display = 'block';

    // Remove editor
    const parent = element.parentElement;
    parent.querySelectorAll('.inline-editor-textarea, .inline-editor-controls').forEach(el => el.remove());

    // Re-add edit button if missing
    if (!element.querySelector('.edit-toggle-btn')) {
      this.addEditButton(element, editableId);
    }

    // Persist to localStorage
    this.saveToStorage(editableId, newContent);

    // Persist to Supabase (async, don't block UI)
    this.syncToSupabase(editableId, newContent);

    // Visual feedback
    this.showSavedFeedback(element);
  }

  cancelEdit(element, textarea, controls) {
    element.style.display = 'block';
    textarea.remove();
    controls.remove();
  }

  saveToStorage(editableId, content) {
    const edits = JSON.parse(localStorage.getItem(this.storageKey) || '{}');
    edits[editableId] = {
      content: content,
      timestamp: new Date().toISOString(),
      url: window.location.href
    };
    localStorage.setItem(this.storageKey, JSON.stringify(edits));
  }

  loadEditHistory() {
    const edits = JSON.parse(localStorage.getItem(this.storageKey) || '{}');
    Object.entries(edits).forEach(([editableId, data]) => {
      const element = document.querySelector(`[data-editable-id="${editableId}"]`);
      if (element) {
        element.innerHTML = data.content;
      }
    });
  }

  syncToSupabase(editableId, content) {
    // POST to API endpoint that saves to Supabase
    const payload = {
      page: window.location.pathname,
      element_id: editableId,
      content: content,
      timestamp: new Date().toISOString()
    };

    fetch('/api/inline-edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).catch(err => {
      console.warn('Could not sync to Supabase:', err);
      // Still saved locally in localStorage, user won't lose data
    });
  }

  showSavedFeedback(element) {
    const feedback = document.createElement('div');
    feedback.className = 'edit-saved-feedback';
    feedback.textContent = '✓ Saved';
    element.appendChild(feedback);

    setTimeout(() => {
      feedback.remove();
    }, 2000);
  }

  static clearAllEdits() {
    const keys = Object.keys(localStorage).filter(k => k.startsWith('inline-edits-'));
    keys.forEach(k => localStorage.removeItem(k));
    console.log('Cleared all inline edits from localStorage');
  }

  static getEditHistory(pathname = null) {
    const path = pathname || window.location.pathname;
    const key = 'inline-edits-' + path;
    return JSON.parse(localStorage.getItem(key) || '{}');
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  window.inlineEditor = new InlineEditor();

  // Make available globally
  window.toggleEdit = (elementId) => {
    const el = document.getElementById(elementId);
    if (el) window.inlineEditor.startEditing(el, elementId);
  };
});

// Listen for dynamically added content
const observer = new MutationObserver((mutations) => {
  mutations.forEach((mutation) => {
    if (mutation.addedNodes.length) {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) { // Element node
          if (node.hasAttribute && node.hasAttribute('data-editable')) {
            const editableId = node.getAttribute('data-editable-id') || `editable-${Date.now()}`;
            node.setAttribute('data-editable-id', editableId);
            window.inlineEditor.addEditButton(node, editableId);
          }
        }
      });
    }
  });
});

observer.observe(document.body, {
  childList: true,
  subtree: true
});
