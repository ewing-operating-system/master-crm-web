/**
 * Source Attribution System
 * Every fact on every page gets a numbered footnote: [1] → source URL
 * When they ask "where'd you get that?" you say "click the footnote."
 */

class SourceAttribution {
  constructor() {
    this.sources = new Map();
    this.footnoteCounts = new Map();
  }

  /**
   * Register a source (adds to footnote list, returns footnote number)
   * 
   * @param {string} url - Source URL (must be valid HTTP/HTTPS)
   * @param {string} title - Display title for footnote
   * @returns {number} Footnote number [1], [2], etc.
   */
  addSource(url, title) {
    const key = `${url}|${title}`;
    
    if (this.sources.has(key)) {
      return this.sources.get(key).number;
    }
    
    const number = this.sources.size + 1;
    this.sources.set(key, { url, title, number });
    return number;
  }

  /**
   * Insert footnote in HTML text
   * 
   * @param {string} element - HTML element selector
   * @param {string} searchText - Text to find
   * @param {string} url - Source URL
   * @param {string} title - Footnote title
   */
  annotateText(element, searchText, url, title) {
    const footnoteNum = this.addSource(url, title);
    const selector = document.querySelector(element);
    
    if (!selector) return;
    
    const text = selector.textContent;
    const idx = text.indexOf(searchText);
    
    if (idx === -1) return;
    
    // Insert [n] after found text
    const beforeText = text.substring(0, idx + searchText.length);
    const afterText = text.substring(idx + searchText.length);
    
    const footnoteSpan = document.createElement('span');
    footnoteSpan.className = 'source-footnote';
    footnoteSpan.innerHTML = ` <a href="#source-${footnoteNum}" class="footnote-link">[${footnoteNum}]</a>`;
    
    // Replace text with before + footnote + after
    selector.innerHTML = 
      selector.innerHTML.replace(
        searchText,
        `${searchText}<a href="#source-${footnoteNum}" class="footnote-link">[${footnoteNum}]</a>`
      );
  }

  /**
   * Render footnotes section at bottom of page
   * 
   * @param {string} containerId - Container element ID to append to
   */
  renderFootnotes(containerId = 'sources') {
    const container = document.getElementById(containerId) || 
                      document.createElement('div');
    
    if (!container.id) {
      container.id = containerId;
      document.body.appendChild(container);
    }
    
    container.className = 'sources-section';
    container.innerHTML = '<h3>Sources</h3><ol class="sources-list"></ol>';
    
    const list = container.querySelector('.sources-list');
    
    for (const [key, source] of this.sources) {
      const li = document.createElement('li');
      li.id = `source-${source.number}`;
      li.innerHTML = `<a href="${source.url}" target="_blank">${source.title}</a>`;
      list.appendChild(li);
    }
  }

  /**
   * Get all sources as JSON (for export/API)
   */
  export() {
    return Array.from(this.sources.values());
  }
}

// CSS for source attribution
const attributionCSS = `
.source-footnote {
  font-size: 0.85em;
  vertical-align: super;
}

.footnote-link {
  color: #0066cc;
  text-decoration: none;
  border-bottom: 1px dotted #0066cc;
  cursor: pointer;
}

.footnote-link:hover {
  background-color: #f0f0f0;
  border-bottom: 1px solid #0066cc;
}

.sources-section {
  margin-top: 3rem;
  padding-top: 2rem;
  border-top: 1px solid #e0e0e0;
  font-size: 0.9em;
  color: #666;
}

.sources-section h3 {
  margin-top: 0;
  color: #333;
}

.sources-list {
  margin: 0;
  padding-left: 1.5rem;
}

.sources-list li {
  margin-bottom: 0.5rem;
}

.sources-list a {
  color: #0066cc;
  text-decoration: none;
}

.sources-list a:hover {
  text-decoration: underline;
}

@print {
  .source-footnote,
  .footnote-link {
    color: #000;
    border-bottom: none;
  }
  
  .sources-section {
    page-break-before: always;
  }
}
`;

// Inject CSS on load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent = attributionCSS;
    document.head.appendChild(style);
  });
} else {
  const style = document.createElement('style');
  style.textContent = attributionCSS;
  document.head.appendChild(style);
}

// Global instance
window.sourceAttribution = new SourceAttribution();

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SourceAttribution;
}
