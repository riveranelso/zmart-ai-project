import Link from "next/link";

const links = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/contacts", label: "Contacts" },
  { href: "/dashboard/calls", label: "Calls" },
  { href: "/dashboard/appointments", label: "Appointments" },
  { href: "/dashboard/leads", label: "Leads" },
];

export function Sidebar() {
  return (
    <nav className="w-56 shrink-0 border-r border-gray-200 p-4">
      <div className="mb-6 text-lg font-bold">Zmart AI</div>
      <ul className="space-y-1">
        {links.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="block rounded px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
