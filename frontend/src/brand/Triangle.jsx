import React from "react";

/** The recurring brand motif — echoes the logo's gold "V" wedge. Reused
 *  wherever the kit calls for it; never redrawn ad hoc per screen. */
export function Triangle({ size = 14, color = "var(--gold)" }) {
  return (
    <span
      style={{
        width: 0,
        height: 0,
        borderLeft: `${size * 0.58}px solid transparent`,
        borderRight: `${size * 0.58}px solid transparent`,
        borderBottom: `${size}px solid ${color}`,
        display: "block",
      }}
    />
  );
}
