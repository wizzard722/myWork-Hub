import { Icon } from "../components/Icon";

export function AdminNav({ route }: { route: string }) {
  const items = [
    { href: "#/beheer/gebruikers", path: "/beheer/gebruikers", label: "Gebruikers", icon: "users" },
    { href: "#/beheer/thema", path: "/beheer/thema", label: "Thema", icon: "palette" },
  ] as const;
  return (
    <nav className="tabs" aria-label="Beheer">
      {items.map((item) => (
        <a
          key={item.path}
          href={item.href}
          className="tab"
          aria-current={route === item.path ? "page" : undefined}
        >
          <Icon name={item.icon} size={16} />
          {item.label}
        </a>
      ))}
    </nav>
  );
}
