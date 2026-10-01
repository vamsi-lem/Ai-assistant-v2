import { Eyebrow } from "@/components/ui/Card";
import { IncomingLeads } from "@/components/leads/IncomingLeads";
import { RequirePerm } from "@/components/auth/Gate";

export default function IncomingLeadsPage() {
  return (
    <RequirePerm perm="leads:assign" message="Lead assignment is available to admins and managers.">
      <div className="space-y-5">
        <div>
          <Eyebrow>Assignment</Eyebrow>
          <h1 className="mt-1.5 text-[24px] font-extrabold tracking-[-0.02em]">Incoming leads</h1>
        </div>
        <IncomingLeads />
      </div>
    </RequirePerm>
  );
}
