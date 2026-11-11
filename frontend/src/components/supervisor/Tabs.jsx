import { useRef } from "react";

// WAI-ARIA tabs: arrow keys, Home, and End move between tabs.
// tabs: [{ id, label, count? }]. Panels use id `panel-${id}` and aria-labelledby `tab-${id}`.
export default function Tabs({ tabs, active, onChange, label }) {
  const tabRefs = useRef({});

  function handleKeyDown(event, index) {
    const steps = { ArrowRight: 1, ArrowLeft: -1 };
    let next = null;
    if (event.key in steps) next = (index + steps[event.key] + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].id);
    tabRefs.current[tabs[next].id]?.focus();
  }

  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          ref={(node) => {
            tabRefs.current[tab.id] = node;
          }}
          type="button"
          role="tab"
          id={`tab-${tab.id}`}
          className="tab"
          aria-selected={active === tab.id}
          aria-controls={`panel-${tab.id}`}
          tabIndex={active === tab.id ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          {tab.label}
          {tab.count !== undefined && <span className="tab-count">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}
