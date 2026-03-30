/**
 * Meeting Form v2 — Auto-save, Completeness Scoring, Summary Generation
 * Persists to localStorage automatically, syncs to Supabase on save
 */

class MeetingForm {
    constructor() {
        this.storageKey = 'meeting_form_' + this.getCompanyId();
        this.requiredFields = ['motivation-type', 'timeline-type', 'annual-revenue', 'ebitda-margin'];
        this.formFields = new Map();
        this.initFormFields();
        this.loadFormData();
        this.setupEventListeners();
        this.updateCompleteness();
    }

    // Get company ID from URL or use default
    getCompanyId() {
        const params = new URLSearchParams(window.location.search);
        return params.get('company_id') || 'default';
    }

    // Initialize all form fields
    initFormFields() {
        // Meeting setup
        this.formFields.set('company-name', { selector: '#company-name', type: 'text' });
        this.formFields.set('rep-name', { selector: '#rep-name', type: 'text' });
        this.formFields.set('meeting-date', { selector: '#meeting-date', type: 'datetime-local' });
        this.formFields.set('duration', { selector: '#duration', type: 'number' });
        this.formFields.set('notes', { selector: '#notes', type: 'textarea' });

        // Owner motivation
        this.formFields.set('motivation-type', { selector: '#motivation-type', type: 'select', required: true });
        this.formFields.set('motivation-quote', { selector: '#motivation-quote', type: 'textarea' });
        this.formFields.set('motivation-confidence', { selector: '#motivation-confidence', type: 'range' });

        // Timeline
        this.formFields.set('timeline-type', { selector: '#timeline-type', type: 'select', required: true });
        this.formFields.set('timeline-confidence', { selector: '#timeline-confidence', type: 'range' });
        this.formFields.set('timeline-notes', { selector: '#timeline-notes', type: 'textarea' });

        // Revenue
        this.formFields.set('annual-revenue', { selector: '#annual-revenue', type: 'number', required: true });
        this.formFields.set('growth-rate', { selector: '#growth-rate', type: 'number' });
        this.formFields.set('service-split', { selector: '#service-split', type: 'range' });
        this.formFields.set('recurring-revenue', { selector: '#recurring-revenue', type: 'range' });
        this.formFields.set('growth-notes', { selector: '#growth-notes', type: 'textarea' });

        // Margins
        this.formFields.set('estimated-ebitda', { selector: '#estimated-ebitda', type: 'number' });
        this.formFields.set('ebitda-margin', { selector: '#ebitda-margin', type: 'range', required: true });
        this.formFields.set('vehicle-allowance', { selector: '#vehicle-allowance', type: 'number' });
        this.formFields.set('family-salary', { selector: '#family-salary', type: 'number' });
        this.formFields.set('travel-entertainment', { selector: '#travel-entertainment', type: 'number' });
        this.formFields.set('insurance-benefits', { selector: '#insurance-benefits', type: 'number' });
        this.formFields.set('margins-notes', { selector: '#margins-notes', type: 'textarea' });

        // Key People
        this.formFields.set('owner-dependency', { selector: '#owner-dependency', type: 'range' });
        this.formFields.set('team-readiness', { selector: '#team-readiness', type: 'textarea' });

        // Emotional
        this.formFields.set('readiness-scale', { selector: '#readiness-scale', type: 'range' });
        this.formFields.set('emotional-notes', { selector: '#emotional-notes', type: 'textarea' });

        // Story
        this.formFields.set('story-origin', { selector: '#story-origin', type: 'textarea' });
        this.formFields.set('story-challenge', { selector: '#story-challenge', type: 'textarea' });
        this.formFields.set('story-community', { selector: '#story-community', type: 'textarea' });
        this.formFields.set('story-culture', { selector: '#story-culture', type: 'textarea' });
        this.formFields.set('story-quirky', { selector: '#story-quirky', type: 'textarea' });
        this.formFields.set('story-personal', { selector: '#story-personal', type: 'textarea' });
    }

    // Load form data from localStorage
    loadFormData() {
        const saved = localStorage.getItem(this.storageKey);
        if (!saved) {
            this.setDefaultValues();
            return;
        }

        try {
            const data = JSON.parse(saved);

            // Restore all fields
            this.formFields.forEach((config, key) => {
                const el = document.querySelector(config.selector);
                if (el && data[key]) {
                    el.value = data[key];
                }
            });

            // Restore checkboxes
            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (data[cb.id]) cb.checked = data[cb.id];
            });

            // Restore radios
            document.querySelectorAll('input[type="radio"]').forEach(radio => {
                if (data[radio.name] === radio.value) radio.checked = true;
            });

            console.log('Meeting form data restored from localStorage');
        } catch (e) {
            console.warn('Could not load meeting form data:', e);
        }
    }

    // Set default/current values
    setDefaultValues() {
        const now = new Date();
        const dateStr = now.toISOString().slice(0, 16);
        document.querySelector('#meeting-date').value = dateStr;
        document.querySelector('#company-name').value = this.getCompanyNameFromPage();
        document.querySelector('#rep-name').value = this.getRepNameFromPage();
    }

    // Get company name from page context (or query param)
    getCompanyNameFromPage() {
        const params = new URLSearchParams(window.location.search);
        return params.get('company_name') || 'Unnamed Company';
    }

    // Get rep name from page context (could be from auth)
    getRepNameFromPage() {
        return 'Rep User'; // TODO: Pull from auth context
    }

    // Setup all event listeners
    setupEventListeners() {
        // Auto-save on every field change
        this.formFields.forEach((config, key) => {
            const el = document.querySelector(config.selector);
            if (el) {
                el.addEventListener('change', () => this.saveFormData());
                el.addEventListener('input', (e) => {
                    // Debounce text input
                    clearTimeout(this.saveTimeout);
                    this.saveTimeout = setTimeout(() => this.saveFormData(), 500);
                });
            }
        });

        // Checkboxes
        document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => this.saveFormData());
        });

        // Radios
        document.querySelectorAll('input[type="radio"]').forEach(radio => {
            radio.addEventListener('change', () => this.saveFormData());
        });

        // Slider value displays
        document.querySelector('#motivation-confidence').addEventListener('input', (e) => {
            document.querySelector('#motivation-confidence-value').textContent = e.target.value;
        });
        document.querySelector('#timeline-confidence').addEventListener('input', (e) => {
            document.querySelector('#timeline-confidence-value').textContent = e.target.value;
        });
        document.querySelector('#owner-dependency').addEventListener('input', (e) => {
            document.querySelector('#owner-dependency-value').textContent = e.target.value;
        });
        document.querySelector('#readiness-scale').addEventListener('input', (e) => {
            document.querySelector('#readiness-value').textContent = e.target.value;
        });

        // Revenue sliders with bidirectional binding
        document.querySelector('#service-split').addEventListener('input', (e) => {
            const service = parseInt(e.target.value);
            const install = 100 - service;
            document.querySelector('#service-pct-label').textContent = service;
            document.querySelector('#install-pct-label').textContent = install;
            this.saveFormData();
        });

        document.querySelector('#recurring-revenue').addEventListener('input', (e) => {
            document.querySelector('#recurring-pct-label').textContent = e.target.value;
            this.saveFormData();
        });

        // EBITDA margin slider
        document.querySelector('#ebitda-margin').addEventListener('input', (e) => {
            document.querySelector('#ebitda-margin-pct').textContent = e.target.value;
            this.updateMarginCalculations();
        });

        // Margin add-back auto-calculations
        document.querySelectorAll('#vehicle-allowance, #family-salary, #travel-entertainment, #insurance-benefits').forEach(input => {
            input.addEventListener('change', () => this.updateMarginCalculations());
            input.addEventListener('input', () => this.updateMarginCalculations());
        });

        // Generate summary button
        document.querySelector('#generate-summary-btn').addEventListener('click', () => this.generateSummary());

        // Action buttons
        document.querySelector('#generate-letter-btn').addEventListener('click', () => this.generateLetter());
        document.querySelector('#create-proposal-btn').addEventListener('click', () => this.createProposal());
        document.querySelector('#identify-buyers-btn').addEventListener('click', () => this.identifyBuyers());
        document.querySelector('#schedule-followup-btn').addEventListener('click', () => this.scheduleFollowup());

        // Track completeness changes
        this.formFields.forEach((config, key) => {
            const el = document.querySelector(config.selector);
            if (el) {
                el.addEventListener('change', () => this.updateCompleteness());
            }
        });

        document.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach(input => {
            input.addEventListener('change', () => this.updateCompleteness());
        });
    }

    // Save form data to localStorage
    saveFormData() {
        const data = {};

        // Save regular form fields
        this.formFields.forEach((config, key) => {
            const el = document.querySelector(config.selector);
            if (el) data[key] = el.value;
        });

        // Save checkboxes
        document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            data[cb.id] = cb.checked;
        });

        // Save radios
        document.querySelectorAll('input[type="radio"]').forEach(radio => {
            if (radio.checked) {
                data[radio.name] = radio.value;
            }
        });

        data.savedAt = new Date().toISOString();
        localStorage.setItem(this.storageKey, JSON.stringify(data));
        console.log('Meeting form auto-saved to localStorage');

        // Also sync to Supabase in background (don't block UI)
        this.syncToSupabase(data);
    }

    // Sync form data to Supabase (async, non-blocking)
    syncToSupabase(data) {
        const companyName = data['company-name'] || '';
        const slug = companyName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'unknown';

        fetch('/api/meetings/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                company_slug: slug,
                meeting_date: data['meeting-date'] || new Date().toISOString(),
                meeting_notes: JSON.stringify(data),
                attendees: [data['rep-name'] || 'unknown'],
                action_items: [],
                entity: 'next_chapter'
            })
        }).then(function(res) {
            if (res.ok) console.log('Meeting data synced to Supabase');
            else console.warn('Meeting sync failed:', res.status);
        }).catch(function(err) {
            console.warn('Meeting sync error (server may be offline):', err.message);
        });
    }

    // Update margin calculations
    updateMarginCalculations() {
        const vehicle = parseFloat(document.querySelector('#vehicle-allowance').value) || 0;
        const family = parseFloat(document.querySelector('#family-salary').value) || 0;
        const travel = parseFloat(document.querySelector('#travel-entertainment').value) || 0;
        const insurance = parseFloat(document.querySelector('#insurance-benefits').value) || 0;

        const totalAddbacks = vehicle + family + travel + insurance;
        document.querySelector('#total-addbacks').textContent = '$' + totalAddbacks.toLocaleString();

        const estimatedEbitda = parseFloat(document.querySelector('#estimated-ebitda').value) || 0;
        const adjustedEbitda = estimatedEbitda + totalAddbacks;
        document.querySelector('#adjusted-ebitda').textContent = '$' + adjustedEbitda.toLocaleString();

        this.saveFormData();
    }

    // Update completeness score
    updateCompleteness() {
        let filledCount = 0;
        const totalRequiredFields = this.requiredFields.length;

        this.requiredFields.forEach(fieldKey => {
            const el = document.querySelector(`#${fieldKey}`);
            if (el && el.value && el.value.trim() !== '') {
                filledCount++;
            }
        });

        // Also count optional fields that are filled
        let optionalFilled = 0;
        const optionalFields = [
            'motivation-quote', 'timeline-notes', 'growth-rate', 'growth-notes',
            'estimated-ebitda', 'margins-notes', 'team-readiness', 'emotional-notes',
            'story-origin', 'story-challenge', 'story-community', 'story-culture'
        ];
        optionalFields.forEach(fieldKey => {
            const el = document.querySelector(`#${fieldKey}`);
            if (el && el.value && el.value.trim() !== '') optionalFilled++;
        });

        const totalFields = 12; // Total data categories we're tracking
        const percentage = Math.round((filledCount + optionalFilled * 0.3) / totalFields * 100);

        document.querySelector('#completeness-score').textContent = `${filledCount}/${totalRequiredFields} required fields • ${percentage}% complete`;

        // Update progress bar
        const progressFill = document.querySelector('#progress-fill');
        progressFill.style.width = percentage + '%';
        if (percentage >= 75) {
            progressFill.classList.add('complete');
        } else {
            progressFill.classList.remove('complete');
        }

        // Update checklist
        this.updateChecklist();

        // Enable/disable action buttons
        const isComplete = filledCount >= totalRequiredFields;
        document.querySelector('#generate-letter-btn').disabled = !isComplete;
        document.querySelector('#create-proposal-btn').disabled = !isComplete;
        document.querySelector('#identify-buyers-btn').disabled = !isComplete;
        document.querySelector('#schedule-followup-btn').disabled = !isComplete;
    }

    // Update data completeness checklist
    updateChecklist() {
        const checklistItems = document.querySelectorAll('#completeness-checklist .checklist-item');
        checklistItems.forEach(item => {
            const fieldName = item.getAttribute('data-field');
            const hasData = this.fieldHasData(fieldName);
            if (hasData) {
                item.classList.add('complete');
                item.querySelector('.checklist-icon').textContent = '✓';
            } else {
                item.classList.remove('complete');
                item.querySelector('.checklist-icon').textContent = '○';
            }
        });
    }

    // Check if a field section has data
    fieldHasData(fieldName) {
        const fieldMap = {
            'owner_motivation': ['motivation-type', 'motivation-quote'],
            'timeline': ['timeline-type', 'timeline-notes'],
            'revenue': ['annual-revenue', 'growth-rate'],
            'margins': ['estimated-ebitda', 'ebitda-margin'],
            'key_people': ['owner-dependency', 'team-readiness'],
            'deal_breakers': ['db-whole-company', 'db-customer-list'],
            'emotional': ['readiness-scale', 'emotional-notes'],
            'story': ['story-origin', 'story-challenge']
        };

        const fields = fieldMap[fieldName] || [];
        return fields.some(fieldKey => {
            const el = document.querySelector(`#${fieldKey}`);
            if (!el) return false;
            if (el.type === 'checkbox') return el.checked;
            return el.value && el.value.trim() !== '';
        });
    }

    // Generate AI summary from form data
    async generateSummary() {
        const btn = document.querySelector('#generate-summary-btn');
        const loading = document.querySelector('#summary-loading');
        const content = document.querySelector('#summary-content');
        const empty = document.querySelector('#summary-empty');

        btn.disabled = true;
        loading.style.display = 'block';
        content.style.display = 'none';
        empty.style.display = 'none';

        try {
            const formData = this.getFormData();

            // Call LLM to generate summary
            const response = await fetch('/api/meetings/generate-summary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    company_id: this.getCompanyId(),
                    form_data: formData
                })
            });

            if (!response.ok) throw new Error('Failed to generate summary');

            const result = await response.json();

            content.innerHTML = result.summary.replace(/\n/g, '<br>');
            content.style.display = 'block';

            // Populate action items
            this.populateActionItems(result.action_items || []);

            // Show summary was saved
            localStorage.setItem(this.storageKey + '_summary', JSON.stringify({
                summary: result.summary,
                actionItems: result.action_items,
                generatedAt: new Date().toISOString()
            }));

        } catch (err) {
            console.error('Summary generation failed:', err);
            content.textContent = 'Failed to generate summary. Please try again.';
            content.style.display = 'block';
        } finally {
            loading.style.display = 'none';
            btn.disabled = false;
        }
    }

    // Populate action items
    populateActionItems(items) {
        const actionItems = document.querySelector('#action-items');
        const actionEmpty = document.querySelector('#action-empty');

        if (items.length === 0) {
            actionEmpty.style.display = 'block';
            actionItems.style.display = 'none';
            return;
        }

        const actionList = document.querySelector('#action-list');
        actionList.innerHTML = items.map(item => `<li>${item}</li>`).join('');

        actionItems.style.display = 'block';
        actionEmpty.style.display = 'none';
    }

    // Get all form data as JSON
    getFormData() {
        const data = {};

        // Required fields
        data.motivation_type = document.querySelector('#motivation-type').value;
        data.motivation_quote = document.querySelector('#motivation-quote').value;
        data.motivation_confidence = parseInt(document.querySelector('#motivation-confidence').value);

        data.timeline = document.querySelector('#timeline-type').value;
        data.timeline_confidence = parseInt(document.querySelector('#timeline-confidence').value);
        data.timeline_notes = document.querySelector('#timeline-notes').value;

        data.annual_revenue = parseFloat(document.querySelector('#annual-revenue').value) || 0;
        data.growth_rate = parseInt(document.querySelector('#growth-rate').value) || 0;
        data.service_percentage = parseInt(document.querySelector('#service-split').value) || 0;
        data.recurring_revenue_percentage = parseInt(document.querySelector('#recurring-revenue').value) || 0;

        data.estimated_ebitda = parseFloat(document.querySelector('#estimated-ebitda').value) || 0;
        data.ebitda_margin = parseInt(document.querySelector('#ebitda-margin').value) || 0;
        data.owner_perks = {
            vehicle_allowance: parseFloat(document.querySelector('#vehicle-allowance').value) || 0,
            family_salary: parseFloat(document.querySelector('#family-salary').value) || 0,
            travel_entertainment: parseFloat(document.querySelector('#travel-entertainment').value) || 0,
            insurance_benefits: parseFloat(document.querySelector('#insurance-benefits').value) || 0
        };

        // Key people
        data.key_people = {
            tech_leader: {
                name: document.querySelector('.tech-leader-name').value,
                years: parseInt(document.querySelector('.tech-leader-years').value) || 0,
                can_stay: document.querySelector('input[name="tech-stay"]:checked')?.value,
                criticality: document.querySelector('#tech-criticality').value
            },
            sales_leader: {
                name: document.querySelector('.sales-leader-name').value,
                years: parseInt(document.querySelector('.sales-leader-years').value) || 0,
                can_stay: document.querySelector('input[name="sales-stay"]:checked')?.value,
                criticality: document.querySelector('#sales-criticality').value
            },
            other_key: {
                name: document.querySelector('.other-emp-name').value,
                role: document.querySelector('.other-emp-role').value,
                years: parseInt(document.querySelector('.other-emp-years').value) || 0,
                can_stay: document.querySelector('input[name="other-stay"]:checked')?.value,
                criticality: document.querySelector('#other-criticality').value
            }
        };

        data.owner_dependency = parseInt(document.querySelector('#owner-dependency').value) || 0;
        data.team_readiness = document.querySelector('#team-readiness').value;

        // Deal breakers
        data.deal_breakers = {
            whole_company: document.querySelector('#db-whole-company').checked,
            not_customer_list: document.querySelector('#db-customer-list').checked,
            stay_operator: document.querySelector('#db-stay-operator').checked,
            full_proceeds: document.querySelector('#db-full-proceeds').checked,
            keep_employees: document.querySelector('#db-keep-employees').checked,
            maintain_location: document.querySelector('#db-location').checked
        };
        data.deal_killer = document.querySelector('#deal-killer').value;
        data.hidden_concerns = document.querySelector('#hidden-concerns').value;

        // Emotional
        data.emotional_readiness = parseInt(document.querySelector('#readiness-scale').value) || 0;
        data.personality_types = {
            analytical: document.querySelector('#pers-analytical').checked,
            gut_trusting: document.querySelector('#pers-gut').checked,
            data_driven: document.querySelector('#pers-data').checked,
            story_driven: document.querySelector('#pers-story').checked
        };
        data.emotional_notes = document.querySelector('#emotional-notes').value;

        // Story
        data.story_elements = {
            origin: document.querySelector('#story-origin').value,
            challenge: document.querySelector('#story-challenge').value,
            community: document.querySelector('#story-community').value,
            culture: document.querySelector('#story-culture').value,
            quirky: document.querySelector('#story-quirky').value,
            personal: document.querySelector('#story-personal').value
        };

        return data;
    }

    // Generate letter from meeting data
    generateLetter() {
        const formData = this.getFormData();
        const params = new URLSearchParams({
            company_id: this.getCompanyId(),
            data: JSON.stringify(formData)
        });
        window.open(`/letter-template.html?${params.toString()}`, '_blank');
    }

    // Create proposal from meeting data
    createProposal() {
        const formData = this.getFormData();
        const params = new URLSearchParams({
            company_id: this.getCompanyId(),
            data: JSON.stringify(formData)
        });
        window.open(`/interactive-proposal-auto.html?${params.toString()}`, '_blank');
    }

    // Identify ideal buyers
    identifyBuyers() {
        const formData = this.getFormData();
        const params = new URLSearchParams({
            company_id: this.getCompanyId(),
            data: JSON.stringify(formData)
        });
        window.open(`/buyer-matching.html?${params.toString()}`, '_blank');
    }

    // Schedule follow-up call
    scheduleFollowup() {
        const timeline = document.querySelector('#timeline-type').value;
        const timelineMap = {
            '3months': 30,
            '6months': 60,
            '12months': 120,
            '18months': 180,
            'none': 14
        };
        const daysOut = timelineMap[timeline] || 14;

        // Suggest 3 dates based on owner's timeline
        const options = [
            { label: '1 week', days: 7 },
            { label: '2 weeks', days: 14 },
            { label: '30 days', days: 30 }
        ];

        // Build and show modal
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;';

        const modal = document.createElement('div');
        modal.style.cssText = 'background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;max-width:400px;width:90%;';

        let html = '<h3 style="color:#f0f6fc;margin-bottom:16px;font-size:16px;">Schedule Follow-up</h3>';
        html += '<p style="color:#8b949e;font-size:13px;margin-bottom:16px;">Based on the ' + (timeline || 'default') + ' timeline, pick a follow-up date:</p>';

        options.forEach(function(opt) {
            const d = new Date();
            d.setDate(d.getDate() + opt.days);
            const dateStr = d.toISOString().split('T')[0];
            const displayDate = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
            html += '<button class="followup-option" data-date="' + dateStr + '" data-label="' + opt.label + '" style="display:block;width:100%;padding:12px 16px;margin-bottom:8px;background:#21262d;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;cursor:pointer;font-size:13px;text-align:left;font-weight:600;transition:all 0.2s;">' +
                opt.label + ' <span style="color:#8b949e;font-weight:400;">(' + displayDate + ')</span></button>';
        });

        html += '<button class="followup-cancel" style="display:block;width:100%;padding:10px;margin-top:8px;background:transparent;border:1px solid #30363d;border-radius:6px;color:#8b949e;cursor:pointer;font-size:13px;">Cancel</button>';
        modal.innerHTML = html;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // Wire up buttons
        const self = this;
        modal.querySelectorAll('.followup-option').forEach(function(btn) {
            btn.addEventListener('mouseenter', function() { btn.style.borderColor = '#58a6ff'; btn.style.color = '#58a6ff'; });
            btn.addEventListener('mouseleave', function() { btn.style.borderColor = '#30363d'; btn.style.color = '#c9d1d9'; });
            btn.addEventListener('click', function() {
                const selectedDate = btn.getAttribute('data-date');
                const selectedLabel = btn.getAttribute('data-label');
                self.saveFollowup(selectedDate, selectedLabel);
                document.body.removeChild(overlay);
            });
        });

        modal.querySelector('.followup-cancel').addEventListener('click', function() {
            document.body.removeChild(overlay);
        });

        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) document.body.removeChild(overlay);
        });
    }

    // Save follow-up date to server
    saveFollowup(date, label) {
        const companyName = document.querySelector('#company-name').value || 'unknown';
        const slug = companyName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

        fetch('/api/meetings/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                company_slug: slug,
                meeting_date: new Date().toISOString(),
                meeting_notes: 'Follow-up scheduled for ' + date + ' (' + label + ')',
                attendees: [document.querySelector('#rep-name').value || 'unknown'],
                action_items: ['Follow-up call on ' + date],
                entity: 'next_chapter'
            })
        }).then(function(res) {
            if (res.ok) {
                // Show confirmation on the button
                const btn = document.querySelector('#schedule-followup-btn');
                const origText = btn.textContent;
                btn.textContent = 'Follow-up: ' + date;
                btn.style.background = '#238636';
                btn.style.color = '#fff';
                btn.style.borderColor = '#238636';
                setTimeout(function() {
                    btn.textContent = origText;
                    btn.style.background = '';
                    btn.style.color = '';
                    btn.style.borderColor = '';
                }, 3000);
            }
        }).catch(function(err) {
            console.warn('Follow-up save error:', err.message);
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.meetingForm = new MeetingForm();
});
