/**
 * Section Control System
 * Adds interactive controls to every section: move up/down, hide, collapse, delete
 * Persists state to localStorage
 */

class SectionControlManager {
  constructor() {
    this.sections = [];
    this.storageKey = 'section-state-' + window.location.pathname;
    this.initSections();
    this.loadState();
    this.setupEventListeners();
  }

  initSections() {
    // Find all sections with class="section"
    const sectionElements = document.querySelectorAll('.section, .card');
    sectionElements.forEach((el, index) => {
      el.setAttribute('data-section-id', index);
      el.setAttribute('data-section-original-order', index);
      this.sections.push({
        id: index,
        element: el,
        hidden: false,
        collapsed: false,
        order: index
      });
      this.addControlIcon(el, index);
    });
  }

  addControlIcon(sectionElement, sectionId) {
    // Create control icon button
    const controlButton = document.createElement('button');
    controlButton.className = 'section-control-btn';
    controlButton.setAttribute('data-section-id', sectionId);
    controlButton.setAttribute('aria-label', 'Section controls');
    controlButton.innerHTML = '⋯'; // Three dots icon
    controlButton.title = 'Section controls: move, hide, collapse, delete';

    // Create popup menu
    const menu = document.createElement('div');
    menu.className = 'section-control-menu';
    menu.setAttribute('data-section-id', sectionId);
    menu.innerHTML = `
      <button class="control-action" data-action="move-up" title="Move section up">
        <span class="action-icon">↑</span> Move Up
      </button>
      <button class="control-action" data-action="move-down" title="Move section down">
        <span class="action-icon">↓</span> Move Down
      </button>
      <button class="control-action" data-action="collapse" title="Collapse/expand section">
        <span class="action-icon">−</span> Collapse
      </button>
      <button class="control-action" data-action="hide" title="Hide section (still loaded, not deleted)">
        <span class="action-icon">👁</span> Hide
      </button>
      <button class="control-action" data-action="delete" title="Delete section permanently">
        <span class="action-icon">🗑</span> Delete
      </button>
    `;

    // Insert button and menu into section
    const titleElement = sectionElement.querySelector('.section-title, h2, h3');
    if (titleElement) {
      titleElement.style.position = 'relative';
      titleElement.appendChild(controlButton);
      titleElement.appendChild(menu);
    } else {
      sectionElement.insertBefore(menu, sectionElement.firstChild);
      sectionElement.insertBefore(controlButton, sectionElement.firstChild);
    }

    // Click to show/hide menu
    controlButton.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleMenu(sectionId);
    });

    // Close menu when clicking outside
    document.addEventListener('click', () => {
      menu.classList.remove('visible');
    });

    menu.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }

  toggleMenu(sectionId) {
    const menu = document.querySelector(`.section-control-menu[data-section-id="${sectionId}"]`);
    if (menu) {
      // Close all other menus
      document.querySelectorAll('.section-control-menu.visible').forEach(m => {
        if (m !== menu) m.classList.remove('visible');
      });
      menu.classList.toggle('visible');

      // Attach action listeners
      menu.querySelectorAll('.control-action').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const action = e.currentTarget.getAttribute('data-action');
          this.executeAction(sectionId, action);
          menu.classList.remove('visible');
        });
      });
    }
  }

  executeAction(sectionId, action) {
    const section = this.sections.find(s => s.id === sectionId);
    if (!section) return;

    const el = section.element;

    switch (action) {
      case 'move-up':
        this.moveSection(sectionId, 'up');
        break;
      case 'move-down':
        this.moveSection(sectionId, 'down');
        break;
      case 'hide':
        this.toggleHide(sectionId);
        break;
      case 'collapse':
        this.toggleCollapse(sectionId);
        break;
      case 'delete':
        this.deleteSection(sectionId);
        break;
    }
    this.saveState();
  }

  moveSection(sectionId, direction) {
    const sectionEl = document.querySelector(`[data-section-id="${sectionId}"]`);
    if (!sectionEl) return;

    const parent = sectionEl.parentElement;
    const sections = Array.from(parent.querySelectorAll('[data-section-id]'));
    const currentIndex = sections.indexOf(sectionEl);

    if (direction === 'up' && currentIndex > 0) {
      sectionEl.parentElement.insertBefore(sectionEl, sections[currentIndex - 1]);
    } else if (direction === 'down' && currentIndex < sections.length - 1) {
      sectionEl.parentElement.insertBefore(sections[currentIndex + 1], sectionEl);
    }

    this.saveState();
  }

  toggleHide(sectionId) {
    const section = this.sections.find(s => s.id === sectionId);
    if (!section) return;

    section.hidden = !section.hidden;
    section.element.style.display = section.hidden ? 'none' : 'block';

    // Update button text
    const menu = document.querySelector(`.section-control-menu[data-section-id="${sectionId}"]`);
    const hideBtn = menu?.querySelector('[data-action="hide"]');
    if (hideBtn) {
      hideBtn.textContent = section.hidden ? '👁 Show' : '👁 Hide';
    }
  }

  toggleCollapse(sectionId) {
    const section = this.sections.find(s => s.id === sectionId);
    if (!section) return;

    section.collapsed = !section.collapsed;
    const el = section.element;

    if (section.collapsed) {
      const content = el.querySelectorAll('.section-title + *, .section-title ~ *:not(.section-control-btn):not(.section-control-menu)');
      content.forEach(c => c.style.display = 'none');
      el.style.opacity = '0.6';
    } else {
      el.querySelectorAll('*').forEach(el => {
        el.style.display = '';
      });
      el.style.opacity = '1';
    }

    // Update button text
    const menu = document.querySelector(`.section-control-menu[data-section-id="${sectionId}"]`);
    const collapseBtn = menu?.querySelector('[data-action="collapse"]');
    if (collapseBtn) {
      collapseBtn.innerHTML = section.collapsed ? '<span class="action-icon">+</span> Expand' : '<span class="action-icon">−</span> Collapse';
    }
  }

  deleteSection(sectionId) {
    const section = this.sections.find(s => s.id === sectionId);
    if (!section) return;

    if (confirm('Delete this section permanently? This cannot be undone.')) {
      section.element.style.opacity = '0.3';
      section.element.style.pointerEvents = 'none';
      section.element.setAttribute('data-deleted', 'true');

      setTimeout(() => {
        section.element.remove();
      }, 300);
    }
  }

  saveState() {
    const state = {
      timestamp: new Date().toISOString(),
      sections: this.sections.map(s => ({
        id: s.id,
        hidden: s.hidden,
        collapsed: s.collapsed,
        deleted: s.element.hasAttribute('data-deleted')
      })),
      order: Array.from(document.querySelectorAll('[data-section-id]')).map(el =>
        parseInt(el.getAttribute('data-section-id'))
      )
    };
    localStorage.setItem(this.storageKey, JSON.stringify(state));

    // Also persist to server (fire-and-forget — localStorage is primary, server is backup)
    try {
      fetch('/api/sections/save-order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          page_path: window.location.pathname,
          user_id: localStorage.getItem('crm_user') || 'default',
          section_order: state
        })
      }).catch(() => {});
    } catch(e) {}
  }

  loadState() {
    const saved = localStorage.getItem(this.storageKey);

    // If no localStorage state, try loading from server asynchronously
    if (!saved) {
      fetch('/api/sections/get-order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          page_path: window.location.pathname,
          user_id: localStorage.getItem('crm_user') || 'default'
        })
      }).then(r => r.json()).then(data => {
        if (data.section_order) {
          localStorage.setItem(this.storageKey, JSON.stringify(data.section_order));
          this.loadState();
        }
      }).catch(() => {});
      return;
    }

    try {
      const state = JSON.parse(saved);

      // Restore order
      if (state.order && state.order.length > 0) {
        const container = document.querySelector('.container') || document.body;
        const sectionMap = new Map();
        this.sections.forEach(s => sectionMap.set(s.id, s.element));

        state.order.forEach(id => {
          const el = sectionMap.get(id);
          if (el) container.appendChild(el);
        });
      }

      // Restore state (hidden, collapsed, deleted)
      state.sections?.forEach(savedSection => {
        const section = this.sections.find(s => s.id === savedSection.id);
        if (section) {
          if (savedSection.hidden) this.toggleHide(savedSection.id);
          if (savedSection.collapsed) this.toggleCollapse(savedSection.id);
          if (savedSection.deleted) {
            section.element.style.display = 'none';
            section.element.setAttribute('data-deleted', 'true');
          }
        }
      });
    } catch (e) {
      console.warn('Could not load section state:', e);
    }
  }

  setupEventListeners() {
    // Nothing needed yet, but here for future enhancements
  }

  static clearAllState() {
    const keys = Object.keys(localStorage).filter(k => k.startsWith('section-state-'));
    keys.forEach(k => localStorage.removeItem(k));
    location.reload();
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  window.sectionManager = new SectionControlManager();
});
