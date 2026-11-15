export default function Button({ children, variant = "default", ...props }) {
  return <button className={`button button-${variant}`} {...props}>{children}</button>;
}
