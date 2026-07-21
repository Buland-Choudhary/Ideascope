import type { Manipulable, ParamValue } from "../types/lesson";

interface ManipulableControlsProps {
  manipulables: Manipulable[];
  values: Record<string, ParamValue>;
  onChange: (param: string, value: ParamValue) => void;
}

/** Renders the beat's manipulable controls (docs/PLAN.md §6.1). */
export function ManipulableControls({ manipulables, values, onChange }: ManipulableControlsProps) {
  if (manipulables.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-6 rounded-lg border border-gray-200 bg-gray-50 p-4">
      {manipulables.map((m) => (
        <Control key={m.id} manipulable={m} value={values[m.param]} onChange={onChange} />
      ))}
    </div>
  );
}

function Control({
  manipulable: m,
  value,
  onChange,
}: {
  manipulable: Manipulable;
  value: ParamValue;
  onChange: (param: string, value: ParamValue) => void;
}) {
  const labelId = `manip-${m.id}`;

  if (m.type === "slider" || m.type === "stepper") {
    return (
      <label className="flex flex-col gap-1 text-sm" htmlFor={labelId}>
        <span className="font-medium text-gray-700">
          {m.label}: <span className="tabular-nums text-gray-500">{String(value)}</span>
        </span>
        <input
          id={labelId}
          type="range"
          min={m.min ?? 0}
          max={m.max ?? 100}
          step={m.step ?? 1}
          value={Number(value)}
          onChange={(e) => onChange(m.param, Number(e.target.value))}
        />
      </label>
    );
  }

  if (m.type === "toggle") {
    return (
      <label className="flex items-center gap-2 text-sm font-medium text-gray-700" htmlFor={labelId}>
        <input
          id={labelId}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(m.param, e.target.checked)}
        />
        {m.label}
      </label>
    );
  }

  // select
  return (
    <label className="flex flex-col gap-1 text-sm" htmlFor={labelId}>
      <span className="font-medium text-gray-700">{m.label}</span>
      <select
        id={labelId}
        value={String(value)}
        onChange={(e) => onChange(m.param, e.target.value)}
        className="rounded border border-gray-300 px-2 py-1"
      >
        {(m.options ?? []).map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}
