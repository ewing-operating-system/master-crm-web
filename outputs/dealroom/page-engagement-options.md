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
            color: var(--gray-text);
            font-style: italic;
            margin-bottom: 2rem;
            padding: 1rem;
            background-color: white;
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
            border-radius: 8px;
            padding: 2rem;
            border: 1px solid var(--gray-border);
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            display: flex;
            flex-direction: column;
        }
        .option-card.recommended {
            border: 2px solid var(--accent);
            box-shadow: 0 4px 12px var(--accent-light);
            position: relative;
            order: -1; /* Brings recommended to front on mobile */
        }
        .recommended-badge {
            position: absolute;
            top: -12px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--accent);
            color: white;
            padding: 0.25rem 1rem;
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
        .best-for {
            background: var(--accent-light);
            padding: 1rem;
            border-radius: 6px;
            margin-top: auto;
        }
        .best-for strong {
            display: block;
            margin-bottom: 0.25rem;
            color: var(--accent);
        }
        .comparison-section {
            margin: 4rem 0;
        }
        .comparison-section h2 {
            font-size: 1.75rem;
            margin-bottom: 1.5rem;
        }
        table {
            width: 100%;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--gray-border);
            border-collapse: collapse;
        }
        th {
            background: var(--primary-dark);
            color: white;
            text-align: left;
            padding: 1rem;
            font-weight: 600;
        }
        td {
            padding: 1rem;
            border-bottom: 1px solid var(--gray-border);
        }
        tr:last-child td {
            border-bottom: none;
        }
        .highlight-cell {
            background-color: var(--accent-light);
            font-weight: 600;
        }
        .tail-clause {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            border: 1px solid var(--gray-border);
            margin: 3rem 0;
        }
        .tail-clause h2 {
            margin-bottom: 1rem;
        }
        .tail-clause ul {
            list-style-position: inside;
            margin: 1rem 0;
        }
        .tail-clause li {
            margin-bottom: 0.5rem;
        }
        .bottom-statement {
            text-align: center;
            padding: 3rem 1rem;
            border-top: 1px solid var(--gray-border);
            margin-top: 3rem;
        }
        .bottom-statement p {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }
        .bottom-statement .deadline {
            color: var(--accent);
            font-weight: 700;
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

    <main>
        <div class="options-grid">
            <!-- Option 1 -->
            <div class="option-card">
                <h3 class="option-title">Clean Exit</h3>
                <p class="option-subtitle">Tighter buyer set, bundled approach, faster timeline</p>
                <ul class="option-features">
                    <li><strong>$15K/month</strong> engagement fee</li>
                    <li><strong>4%</strong> success fee</li>
                    <li>Performance kicker above agreed floor</li>
                </ul>
                <div class="best-for">
                    <strong>Best for:</strong> Getting to an outcome quickly with a focused buyer set.
                </div>
            </div>

            <!-- Option 2 - Recommended -->
            <div class="option-card recommended">
                <div class="recommended-badge">Recommended</div>
                <h3 class="option-title">Max Value Process</h3>
                <p class="option-subtitle">Three parallel tracks, different buyer universes</p>
                <ul class="option-features">
                    <li><strong>$8K/month</strong> (half of Option 1)</li>
                    <li><strong>5%</strong> success fee</li>
                    <li>No performance tier</li>
                </ul>
                <div class="best-for">
                    <strong>Best for:</strong> Maximum value extraction across all three assets.
                </div>
            </div>

            <!-- Option 3 -->
            <div class="option-card">
                <h3 class="option-title">Conviction Bet</h3>
                <p class="option-subtitle">Aggressive. Maximum alignment.</p>
                <ul class="option-features">
                    <li><strong>No upfront fee</strong> — we eat the cost</li>
                    <li><strong>90-day exclusivity</strong> required</li>
                    <li><strong>6%</strong> on first $40M, <strong>20%</strong> above $40M</li>
                </ul>
                <div class="best-for">
                    <strong>Best for:</strong> If you believe in the process and want maximum incentive alignment.
                </div>
            </div>
        </div>

        <section class="comparison-section">
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
                        <td>No</td>
                        <td class="highlight-cell">No</td>
                        <td>90-day required</td>
                    </tr>
                    <tr>
                        <td>Timeline</td>
                        <td>Fastest</td>
                        <td class="highlight-cell">Comprehensive</td>
                        <td>Extended</td>
                    </tr>
                    <tr>
                        <td>Best For</td>
                        <td>Speed & focus</td>
                        <td class="highlight-cell">Max value extraction</td>
                        <td>Maximum alignment</td>
                    </tr>
                </tbody>
            </table>
        </section>

        <section class="tail-clause">
            <h2>Tail Clause</h2>
            <p>Simple and fair. The tail applies only to buyers we directly contacted AND received a response from.</p>
            <ul>
                <li><strong>12-month tail period</strong></li>
                <li><strong>Named buyer list</strong> provided at start, updated weekly</li>
                <li>Transparent. Auditable. Fair.</li>
            </ul>
        </section>

        <div class="bottom-statement">
            <p>Every option runs a real market.</p>
            <p>The difference is scope, speed, and how we split the economics.</p>
            <p class="deadline">Wednesday we pick one and go.</p>
        </div>
    </main>
</body>
</html>
```
