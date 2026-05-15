export function ComparisonBars({
  items,
}: {
  items: { label: string; leftLabel: string; leftValue: number; rightLabel: string; rightValue: number }[];
}) {
  return (
    <div className="space-y-4">
      {items.map((item) => (
        <div key={item.label} className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-700">{item.label}</span>
            <span className="text-slate-500">
              {item.leftLabel} {item.leftValue}% · {item.rightLabel} {item.rightValue}%
            </span>
          </div>
          <div className="space-y-2">
            <div>
              <div className="mb-1 flex justify-between text-xs text-slate-500">
                <span>{item.leftLabel}</span>
                <span>{item.leftValue}%</span>
              </div>
              <div className="h-2 rounded-full bg-slate-200">
                <div className="h-2 rounded-full bg-slate-400" style={{ width: `${item.leftValue}%` }} />
              </div>
            </div>
            <div>
              <div className="mb-1 flex justify-between text-xs text-slate-500">
                <span>{item.rightLabel}</span>
                <span>{item.rightValue}%</span>
              </div>
              <div className="h-2 rounded-full bg-sky-100">
                <div className="h-2 rounded-full bg-sky-600" style={{ width: `${item.rightValue}%` }} />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function BeforeAfterBars({
  items,
}: {
  items: { label: string; before: number; after: number }[];
}) {
  return (
    <div className="space-y-4">
      {items.map((item) => (
        <div key={item.label} className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-700">{item.label}</span>
            <span className="text-slate-500">Before {item.before} · After {item.after}</span>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <div className="rounded-xl bg-rose-50 p-3">
              <div className="mb-2 flex justify-between text-xs text-rose-700">
                <span>Before cleanup</span>
                <span>{item.before}</span>
              </div>
              <div className="h-2 rounded-full bg-rose-100">
                <div className="h-2 rounded-full bg-rose-500" style={{ width: `${Math.min(item.before, 100)}%` }} />
              </div>
            </div>
            <div className="rounded-xl bg-emerald-50 p-3">
              <div className="mb-2 flex justify-between text-xs text-emerald-700">
                <span>After cleanup</span>
                <span>{item.after}</span>
              </div>
              <div className="h-2 rounded-full bg-emerald-100">
                <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${Math.min(item.after, 100)}%` }} />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
