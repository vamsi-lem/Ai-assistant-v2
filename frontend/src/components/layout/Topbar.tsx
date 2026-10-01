import { GlobalSearch } from "@/components/layout/GlobalSearch";
import { RoleBadge } from "@/components/layout/RoleBadge";
import { MobileNav } from "@/components/layout/MobileNav";

export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/80 px-4 backdrop-blur md:px-5">
      <MobileNav />
      <GlobalSearch />
      <div className="ml-auto flex items-center gap-3">
        <RoleBadge />
      </div>
    </header>
  );
}
