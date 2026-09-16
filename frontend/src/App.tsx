import { NavLink, Route, Routes } from "react-router-dom";

import { NewRequestPage } from "./pages/NewRequestPage";
import { PARequestDetailPage } from "./pages/PARequestDetailPage";
import { TrackingPage } from "./pages/TrackingPage";

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium ${
          isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div>
            <h1 className="text-base font-semibold text-slate-900">
              Prior-Authorization &amp; Claims Documentation Assistant
            </h1>
            <p className="text-xs text-slate-400">Built with LangGraph</p>
          </div>
          <nav className="flex gap-1">
            <NavItem to="/">New PA Request</NavItem>
            <NavItem to="/tracking">PA Request Tracking</NavItem>
          </nav>
        </div>
      </header>

      <div className="border-b border-amber-200 bg-amber-50">
        <div className="mx-auto max-w-6xl px-4 py-2 text-xs font-medium text-amber-800">
          Administrative documentation assistance only -- this app does NOT make coverage or medical-necessity
          decisions (that is the payer's decision) and does NOT provide medical advice or diagnose. All
          patients, providers, and payer policies in this demo are synthetic and fictitious. Every draft
          requires staff review and approval before submission.
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<NewRequestPage />} />
          <Route path="/tracking" element={<TrackingPage />} />
          <Route path="/pa-requests/:id" element={<PARequestDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}
