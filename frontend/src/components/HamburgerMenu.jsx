import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { ClientSelector } from "./ClientSelector";

function getMenuItems(role) {
  if (role === "Admin") {
    return [
      { to: "/app/settings", label: "Account Settings" },
      { to: "/app/admin-dashboard", label: "Admin Dashboard" },
    ];
  }

  if (role === "Coach") {
    return [{ to: "/app/settings", label: "Account Settings" }];
  }

  return [{ to: "/app/settings", label: "Account Settings" }];
}

function getDisplayName(user) {
  return [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.username || "Unknown user";
}

export function HamburgerMenu() {
  const { logout, user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const menuItems = useMemo(() => getMenuItems(user?.role), [user?.role]);
  const containerRef = useRef(null);

  useOutsideClick(containerRef, () => setIsOpen(false), isOpen);

  return (
    <div className="menu-container" ref={containerRef}>
      <button
        aria-expanded={isOpen}
        aria-label="Open navigation menu"
        className="menu-button"
        onClick={() => setIsOpen((current) => !current)}
        type="button"
      >
        <span />
        <span />
        <span />
      </button>
      {isOpen ? (
        <div className="menu-popover">
          <p className="menu-heading">{user?.role || "User"} Menu</p>
          <nav className="menu-links">
            {menuItems.map((item) => (
              <Link key={item.to} onClick={() => setIsOpen(false)} to={item.to}>
                {item.label}
              </Link>
            ))}
          </nav>
          <ClientSelector />
          <p className="menu-user-label">Logged in as {getDisplayName(user)}</p>
          <button className="menu-logout" onClick={logout} type="button">
            Log out
          </button>
        </div>
      ) : null}
    </div>
  );
}
