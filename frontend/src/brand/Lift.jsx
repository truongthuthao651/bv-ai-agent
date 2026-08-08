import React from "react";

/** Hover-lift affordance shared by the landing/auth navy surfaces — a style
 *  swap on hover, nothing animated beyond what CSS transitions already do. */
export function Lift({ children, style, hoverStyle, as = "button", ...rest }) {
  const [hover, setHover] = React.useState(false);
  const El = as;
  return (
    <El {...rest} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={{ ...style, ...(hover ? hoverStyle : null) }}>
      {children}
    </El>
  );
}
