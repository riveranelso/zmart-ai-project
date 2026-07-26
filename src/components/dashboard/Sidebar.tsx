"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  PhoneCall,
  CalendarDays,
  Target,
} from "lucide-react";

const links = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/contacts", label: "Contacts", icon: Users },
  { href: "/dashboard/calls", label: "Calls", icon: PhoneCall },
  { href: "/dashboard/appointments", label: "Appointments", icon: CalendarDays },
  { href: "/dashboard/leads", label: "Leads", icon: Target },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="w-60 shrink-0 border-r border-neutral-200 p-4 dark:border-neutral-800">
      <Link href="/" className="mb-6 block px-3 text-lg font-bold">
        Zmart AI
      </Link>
      <ul className="space-y-1">
        {links.map((link) => {
          const isActive =
            link.href === "/dashboard"
              ? pathname === link.href
              : pathname.startsWith(link.href);
          const Icon = link.icon;

          return (
            <li key={link.href}>
              <Link
                href={link.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-400"
                    : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
                }`}
              >
                <Icon size={18} />
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
