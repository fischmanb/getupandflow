import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppShell } from "./components/AppShell";
import { RoleRoute } from "./components/RoleRoute";
import { AccountSettingsPage } from "./pages/AccountSettingsPage";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { AssignedClientsPage } from "./pages/AssignedClientsPage";
import { BillingSuccessPage } from "./pages/BillingSuccessPage";
import { CalendarPage } from "./pages/CalendarPage";
import { CategoryManagementPage } from "./pages/CategoryManagementPage";
import { ClientListPage } from "./pages/ClientListPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { SignupPage } from "./pages/SignupPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/billing/success" element={<BillingSuccessPage />} />
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
        >
          <Route index element={<HomePage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="settings" element={<AccountSettingsPage />} />
          <Route
            path="onboarding"
            element={
              <RoleRoute allowedRoles={["Client"]}>
                <OnboardingPage />
              </RoleRoute>
            }
          />
          <Route
            path="categories"
            element={
              <RoleRoute allowedRoles={["Client", "Coach", "Admin"]}>
                <CategoryManagementPage />
              </RoleRoute>
            }
          />
          <Route
            path="assigned-clients"
            element={
              <RoleRoute allowedRoles={["Coach"]}>
                <AssignedClientsPage />
              </RoleRoute>
            }
          />
          <Route
            path="clients"
            element={
              <RoleRoute allowedRoles={["Admin"]}>
                <ClientListPage />
              </RoleRoute>
            }
          />
          <Route
            path="admin-dashboard"
            element={
              <RoleRoute allowedRoles={["Admin"]}>
                <AdminDashboardPage />
              </RoleRoute>
            }
          />
        </Route>
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
