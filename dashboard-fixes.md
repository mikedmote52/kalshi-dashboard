# Kalshi Dashboard Bug Fixes

This document outlines the exact code changes needed to fix three bugs in the React dashboard.

---

## Bug 1: Confidence field always shows 0

### Problem
The sector_consensus data in dashboard_data.json has `confidence: 0` for every sector, causing the dashboard to display a misleading "0" confidence value instead of hiding it or showing "N/A".

### Solution
Hide the confidence display when its value is 0, or show "N/A" when the pipeline hasn't computed it yet.

### Code Fix Location
Find the component that renders sector consensus data (likely in the sector consensus table/display section). Look for where confidence is rendered, typically in a JSX fragment like:

```jsx
<div className="...">
  {sector.confidence}
</div>
```

### Replace With
```jsx
<div className="...">
  {sector.confidence === 0 || sector.confidence === undefined ? 'N/A' : sector.confidence}
</div>
```

### Alternative Implementation (More Semantic)
If you have a dedicated component for displaying confidence:

```jsx
const ConfidenceDisplay = ({ value }) => {
  if (!value || value === 0) {
    return <span className="text-gray-400">N/A</span>;
  }
  return <span>{value}%</span>;
};

// Usage in parent component:
<ConfidenceDisplay value={sector.confidence} />
```

### Why This Works
- Checks if confidence is 0 or undefined (not yet computed)
- Displays "N/A" or a styled placeholder instead of a misleading 0
- Clearly signals to users that this metric hasn't been calculated

---

## Bug 2: Brent crude price displays as "10000¢"

### Problem
The JSON contains prices in different units:
- Brent crude: `current_price: 100.0` (dollars, >1.0)
- Other commodities/stocks: prices in cents (typically 0.xx or small values)

The dashboard assumes all prices are in cents and multiplies by 100, turning $100 into 10000¢.

### Solution
Detect whether a price is already in dollars (>1.0) vs cents (≤1.0) and format accordingly.

### Code Fix Location
Find the price formatting function in the Market Signals table or wherever prices are displayed. Look for code like:

```jsx
const formatPrice = (price) => {
  return `${(price * 100).toFixed(2)}¢`;
};
```

### Replace With
```jsx
const formatPrice = (price) => {
  // If price > 1.0, it's likely in dollars; otherwise in cents
  if (price > 1.0) {
    return `$${price.toFixed(2)}`;
  } else {
    return `${(price * 100).toFixed(2)}¢`;
  }
};
```

### Alternative (If metadata is available)
If your data structure includes a `currency` or `unit` field per price:

```jsx
const formatPrice = (price, unit = 'cents') => {
  if (unit === 'dollars' || price > 1.0) {
    return `$${price.toFixed(2)}`;
  } else {
    return `${(price * 100).toFixed(2)}¢`;
  }
};

// Usage:
<td>{formatPrice(brentCrude.current_price, 'dollars')}</td>
<td>{formatPrice(otherStock.current_price, 'cents')}</td>
```

### Why This Works
- Automatically detects unit based on magnitude (>1.0 = dollars, ≤1.0 = cents)
- Prevents absurd values like 10000¢ for $100 commodities
- Displays prices in their natural unit ($ for large values, ¢ for small fractional values)

---

## Bug 3: Duplicate pattern alerts

### Problem
The `pattern_alerts` array in dashboard_data.json contains the "authority_shift" pattern twice with the same description. The dashboard should deduplicate and combine frequency counts.

### Solution
Deduplicate pattern alerts by pattern name before rendering, summing the frequency counts.

### Code Fix Location
Find where pattern_alerts are loaded/processed. Look for code like:

```jsx
const [alerts, setAlerts] = useState([]);

useEffect(() => {
  fetch('dashboard_data.json')
    .then(res => res.json())
    .then(data => {
      setAlerts(data.pattern_alerts);
    });
}, []);

// Render:
{alerts.map(alert => (
  <div key={alert.pattern_name}>
    {alert.pattern_name}: {alert.frequency}
  </div>
))}
```

### Replace With
```jsx
const deduplicateAlerts = (alerts) => {
  const alertMap = {};
  
  alerts.forEach(alert => {
    if (alertMap[alert.pattern_name]) {
      // Combine frequencies
      alertMap[alert.pattern_name].frequency += alert.frequency;
    } else {
      alertMap[alert.pattern_name] = { ...alert };
    }
  });
  
  return Object.values(alertMap);
};

const [alerts, setAlerts] = useState([]);

useEffect(() => {
  fetch('dashboard_data.json')
    .then(res => res.json())
    .then(data => {
      const dedupedAlerts = deduplicateAlerts(data.pattern_alerts);
      setAlerts(dedupedAlerts);
    });
}, []);

// Render (unchanged):
{alerts.map(alert => (
  <div key={alert.pattern_name}>
    {alert.pattern_name}: {alert.frequency}
  </div>
))}
```

### Alternative (If rendering in a table/list)
If you're using a map function to render alerts:

```jsx
const uniqueAlerts = [];
const seenPatterns = new Set();

data.pattern_alerts.forEach(alert => {
  if (seenPatterns.has(alert.pattern_name)) {
    // Find and update the existing alert
    const existing = uniqueAlerts.find(a => a.pattern_name === alert.pattern_name);
    existing.frequency += alert.frequency;
  } else {
    uniqueAlerts.push(alert);
    seenPatterns.add(alert.pattern_name);
  }
});

// Then use uniqueAlerts instead of data.pattern_alerts
```

### Why This Works
- Removes duplicate pattern entries from the alert array
- Combines frequency counts so the total impact is preserved
- Prevents redundant display of the same pattern alert twice
- Maintains data integrity by aggregating rather than dropping data

---

## Implementation Priority

1. **Bug 2 (Price formatting)** - Highest priority, most visible to users
2. **Bug 1 (Confidence field)** - Medium priority, affects data credibility
3. **Bug 3 (Duplicate alerts)** - Lower priority, affects user perception of alert frequency

---

## Testing Recommendations

After implementing these fixes:

1. **Bug 1 test**: Verify sectors show "N/A" for confidence instead of 0
2. **Bug 2 test**: Verify Brent crude shows as "$100.00" not "10000¢"
3. **Bug 3 test**: Verify "authority_shift" appears once with combined frequency count

---

## File Location
All changes are in the large inline React script (~278k chars) in `index.html`. The component/function locations depend on your specific component structure, but typically these formatting functions are near:
- Market Signals table rendering
- Sector consensus data display
- Pattern alerts list/table rendering
