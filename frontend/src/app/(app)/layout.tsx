import { AuthGuard } from "@/components/providers/AuthGuard";
import { RoleProvider } from "@/components/providers/RoleProvider";
import { ToastProvider } from "@/components/providers/ToastProvider";
import { LeadsProvider } from "@/components/providers/LeadsProvider";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

/** Everything under (app) needs a signed in user with a profile. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <RoleProvider>
        <ToastProvider>
          <LeadsProvider>
            <div className="flex min-h-screen">
              <Sidebar />
              <div className="flex min-w-0 flex-1 flex-col">
                <Topbar />
                <main className="flex-1 p-4 sm:p-6">{children}</main>
              </div>
            </div>
          </LeadsProvider>
        </ToastProvider>
      </RoleProvider>
    </AuthGuard>
  );
}
