```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Engagement Options | Debbie Deal Room</title>
    <style>
        :root {
            --primary-dark: #1a1a1a;
            --primary-light: #f8f9fa;
            --accent: #2563eb;
            --accent-light: #dbeafe;
            --gray-border: #e5e7eb;
            --gray-text: #6b7280;
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        body {
            background-color: var(--primary-light);
            color: var(--primary-dark);
            line-height: 1.6;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            border-bottom: 1px solid var(--gray-border);
            padding-bottom: 2rem;
            margin-bottom: 3rem;
        }
        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 1rem;
        }
        .framing {
            font-size: 1.25rem;
            color: var(--accent);
            font-weight: 500;
            font-style: italic;
            margin-bottom: 2rem;
            padding: 1rem;
            background-color: var(--accent-light);
            border-radius: 8px;
            border-left: 4px solid var(--accent);
        }
        .options-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin-bottom: 4rem;
        }
        .option-card {
            background: white;
            border-radius: 12px;
            padding: 2rem;
            border: 2px solid var(--gray-border);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            transition: all 0.2s ease;
            display: flex;
            flex-direction: column;
        }
        .option-card:hover {
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08);
        }
        .option-card.recommended {
            border-color: var(--accent);
            box-shadow: 0 10px 25px -5px rgba(37, 99, 235, 0.15);
            position: relative;
            order: -1;
        }
        .recommended-badge {
            position: absolute;
            top: -12px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--accent);
            color: white;
            padding: 0.5rem 1.5rem;
            border-radius: 20px;
            font-size: 0.875rem;
            font-weight: 600;
            white-space: nowrap;
        }
        .option-title {
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .option-subtitle {
            color: var(--gray-text);
            margin-bottom: 1.5rem;
            font-size: 0.95rem;
        }
        .option-features {
            list-style: none;
            margin-bottom: 2rem;
            flex-grow: 1;
        }
        .option-features li {
            padding: 0.5rem 0;
            border-bottom: 1px solid var(--gray-border);
        }
        .option-features li:last-child {
            border-bottom: none;
        }
        .fee-structure {
            background: var(--primary-light);
            padding: 1.5rem;
            border-radius: 8px;
            margin-top: auto;
        }
        .monthly-fee {
            font-size: 2rem;
            font-weight: 800;
            color: var(--accent);
        }
        .success-fee {
            font-size: 1.25rem;
            font-weight: 600;
            margin-top: 0.5rem;
        }
        .best-for {
            margin-top: 1.5rem;
            padding-top: 1.5rem;
            border-top: 2px solid var(--gray-border);
            font-weight: 600;
        }
        .best-for span {
            color: var(--gray-text);
            font-weight: normal;
            display: block;
            margin-top: 0.25rem;
        }
        .comparison-section {
            margin: 4rem 0;
        }
        .comparison-section h2 {
            font-size: 1.75rem;
            margin-bottom: 2rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        }
        thead {
            background-color: var(--primary-dark);
            color: white;
        }
        th {
            padding: 1.25rem 1rem;
            text-align: left;
            font-weight: 600;
        }
        th:first-child {
            width: 25%;
        }
        td {
            padding: 1.25rem 1rem;
            border-bottom: 1px solid var(--gray-border);
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        .highlight-cell {
            background-color: var(--accent-light);
            font-weight: 600;
        }
        .tail-clause {
            background: white;
            padding: 2.5rem;
            border-radius: 12px;
            margin: 4rem 0;
            border-left: 4px solid var(--accent);
        }
        .tail-clause h2 {
            margin-bottom: 1.5rem;
            font-size: 1.75rem;
        }
        .tail-clause ul {
            list-style: none;
            margin: 1.5rem 0;
        }
        .tail-clause li {
            padding: 0.75rem 0;
            border-bottom: 1px solid var(--gray-border);
        }
        .tail-clause li:last-child {
            border-bottom: none;
        }
        .bottom-cta {
            text-align: center;
            padding: 3rem;
            background: var(--primary-dark);
            color: white;
            border-radius: 12px;
            margin-top: 4rem;
        }
        .bottom-cta p {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }
        .bottom-cta .subtext {
            font-size: 1rem;
            font-weight: normal;
            opacity: 0.9;
        }
        @media (max-width: 768px) {
            .options-grid {
                grid-template-columns: 1fr;
            }
            .option-card.recommended {
                order: -1;
            }
            table {
                display: block;
                overflow-x: auto;
            }
        }
    </style>
</head>
<body>
    <header>
        <h1>Engagement Options</h1>
        <div class="framing">
            This is not a pricing decision. It is a decision about how aggressively to run the market.
        </div>
    </header>

    <div class="options-grid">
        <!-- Option 1 -->
        <div class="option-card">
            <h3 class="option-title">Clean Exit</h3>
            <p class="option-subtitle">Tighter buyer set, bundled approach, faster timeline</p>
            <ul class="option-features">
                <li>Focused, high-probability buyer outreach</li>
                <li>Assets bundled for a streamlined sale</li>
                <li>Accelerated 60-90 day timeline</li>
                <li>Performance kicker above agreed floor price</li>
            </ul>
            <div class="fee-structure">
                <div class="monthly-fee">$15K/month</div>
                <div class="success-fee">4% success fee</div>
            </div>
            <div class="best-for">
                Best for:
                <span>Getting to an outcome quickly with a focused buyer set</span>
            </div>
        </div>

        <!-- Option 2 - Recommended -->
        <div class="option-card recommended">
            <div class="recommended-badge">RECOMMENDED</div>
            <h3 class="option-title">Max Value Process</h3>
            <p class="option-subtitle">Three parallel tracks, different buyer universes</p>
            <ul class="option-features">
                <li>Track 1: Strategic acquirers (industry players)</li>
                <li>Track 2: Financial buyers (PE, family offices)</li>
                <li>Track 3: Opportunistic & non-traditional buyers</li>
                <li>Designed to surface maximum competitive tension</li>
            </ul>
            <div class="fee-structure">
                <div class="monthly-fee">$8K/month</div>
                <div class="success-fee">5% success fee</div>
            </div>
            <div class="best-for">
                Best for:
                <span>Maximum value extraction across all three assets</span>
            </div>
        </div>

        <!-- Option 3 -->
        <div class="option-card">
            <h3 class="option-title">Conviction Bet</h3>
            <p class="option-subtitle">No upfront fee — we eat the cost</p>
            <ul class="option-features">
                <li>We carry all upfront costs and effort</li>
                <li>90-day exclusivity required</li>
                <li>Highly aggressive outreach and process</li>
                <li>Maximum incentive alignment on outcome</li>
            </ul>
            <div class="fee-structure">
                <div class="monthly-fee">$0/month</div>
                <div class="success-fee">6% on first $40M<br>20% above $40M</div>
            </div>
            <div class="best-for">
                Best for:
                <span>If you believe in the process and want maximum incentive alignment</span>
            </div>
        </div>
    </div>

    <div class="comparison-section">
        <h2>Comparison</h2>
        <table>
            <thead>
                <tr>
                    <th>Feature</th>
                    <th>Clean Exit</th>
                    <th>Max Value (Rec.)</th>
                    <th>Conviction Bet</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Monthly Fee</td>
                    <td>$15,000</td>
                    <td class="highlight-cell">$8,000</td>
                    <td>$0</td>
                </tr>
                <tr>
                    <td>Success Fee</td>
                    <td>4%</td>
                    <td class="highlight-cell">5%</td>
                    <td>6% on first $40M<br>20% above $40M</td>
                </tr>
                <tr>
                    <td>Exclusivity</td>
                    <td>None required</td>
                    <td class="highlight-cell">None required</td>
                    <td>90 days required</td>
                </tr>
                <tr>
                    <td>Timeline</td>
                    <td>60-90 days</td>
                    <td class="highlight-cell">90-120 days</td>
                    <td>90-120 days</td>
                </tr>
                <tr>
                    <td>Best For</td>
                    <td>Speed & certainty</td>
                    <td class="highlight-cell">Max value extraction</td>
                    <td>Maximum alignment</td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="tail-clause">
        <h2>Tail Clause</h2>
        <p>Clear, fair, and designed to protect both parties.</p>
        <ul>
            <li><strong>Scope:</strong> Tail applies only to buyers we directly contacted AND received a response from.</li>
            <li><strong>Period:</strong> 12-month tail period post-engagement.</li>
            <li><strong>Transparency:</strong> Named buyer list provided at start, updated weekly.</li>
            <li><strong>Principle:</strong> Transparent. Auditable. Fair.</li>
        </ul>
    </div>

    <div class="bottom-cta">
        <p>Every option runs a real market.</p>
        <p class="subtext">The difference is scope, speed, and how we split the economics.<br>Wednesday we pick one and go.</p>
    </div>
</body>
</html>
```
