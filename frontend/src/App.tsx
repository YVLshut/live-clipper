import { useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { Toasts } from "./components/Toasts";
import { SetupWizard } from "./components/SetupWizard";
import { AccountsPage } from "./pages/Accounts";
import { ClippingPage, ClipsPage } from "./pages/Clipping";
import { PublishingPage } from "./pages/Publishing";
import { SettingsPage } from "./pages/Settings";
import { connectWs, useStore } from "./store";

let wsStarted = false;

export default function App() {
  const tab = useStore((s) => s.tab);
  const settings = useStore((s) => s.settings);

  useEffect(() => {
    if (!wsStarted) {
      wsStarted = true;
      connectWs();
    }
  }, []);

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <main className="relative flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-8 py-7">
          {tab === "clipping" && <ClippingPage />}
          {tab === "clips" && <ClipsPage />}
          {tab === "accounts" && <AccountsPage />}
          {tab === "publishing" && <PublishingPage />}
          {tab === "settings" && <SettingsPage />}
        </div>
      </main>
      {settings && !settings.setup_done && <SetupWizard />}
      <Toasts />
    </div>
  );
}
