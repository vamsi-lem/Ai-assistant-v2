"use client";

/**
 * The enquiry form. The entry point to the whole pipeline.
 *
 * The consent checkbox is not decoration. India prohibits cold calling and
 * requires explicit digital consent before a commercial call, so ticking this
 * box is what makes the call lawful. The exact wording is sent to the backend
 * and stored against the lead, because in a complaint you need to show what
 * the person actually agreed to.
 */

import { useState } from "react";
import type { LeadInput } from "@/lib/types";

/**
 * Stored verbatim as consent evidence. If you change this wording, you change
 * what you can prove, so change it deliberately.
 */
export const CONSENT_TEXT = "I agree to receive an automated AI voice call about this enquiry.";

export const COURSES = [
  "MBBS Admission",
  "MD / MS Postgraduate",
  "BDS Admission",
  "Nursing",
  "Allied Health Sciences",
  "Other",
];

const field =
  "w-full rounded-xl border border-line bg-bg-2 px-3.5 py-2.5 text-[14px] text-ink outline-none transition-colors focus:border-line-2 placeholder:text-mut";
const label = "mb-1.5 block text-[12px] font-medium text-soft";

interface Props {
  onSubmit: (input: LeadInput) => Promise<void>;
  busy: boolean;
}

export function LeadForm({ onSubmit, busy }: Props) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [course, setCourse] = useState(COURSES[0]);
  const [notes, setNotes] = useState("");
  const [consent, setConsent] = useState(false);

  const canSubmit = name.trim().length >= 2 && phone.trim().length >= 10 && consent && !busy;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    await onSubmit({
      name: name.trim(),
      phone: phone.trim(),
      email: email.trim() || undefined,
      product_or_course: course,
      notes: notes.trim() || undefined,
      consent_given: consent,
      consent_text: CONSENT_TEXT,
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4 rounded-2xl border border-line bg-panel p-5">
      <div>
        <label htmlFor="name" className={label}>Your name</label>
        <input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Priya Sharma" autoComplete="name" required className={field} />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="phone" className={label}>Mobile number</label>
          <input id="phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" inputMode="tel" autoComplete="tel" required className={field} />
          <p className="mt-1 text-[11.5px] text-mut">A 10 digit Indian number is fine. We add +91 for you.</p>
        </div>
        <div>
          <label htmlFor="email" className={label}>Email <span className="text-mut">optional</span></label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="priya@example.com" autoComplete="email" className={field} />
        </div>
      </div>

      <div>
        <label htmlFor="course" className={label}>What are you enquiring about</label>
        <select id="course" value={course} onChange={(e) => setCourse(e.target.value)} className={field}>
          {COURSES.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </div>

      <div>
        <label htmlFor="notes" className={label}>Anything else <span className="text-mut">optional</span></label>
        <textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Looking at this year's intake, would like to know about the process." className={`${field} resize-y`} />
      </div>

      <label htmlFor="consent" className="flex items-start gap-3 rounded-xl border border-line bg-bg-2 p-3.5 text-[13px] text-soft">
        <input id="consent" type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--violet)]" />
        <span>{CONSENT_TEXT} <strong className="text-ink">Required.</strong></span>
      </label>

      <button type="submit" disabled={!canSubmit} className="w-full rounded-full bg-ink py-3 text-[14px] font-semibold text-[#0a0a0d] transition-transform hover:-translate-y-0.5 disabled:opacity-40 disabled:hover:translate-y-0">
        {busy ? "Connecting" : "Talk to Maya now"}
      </button>

      {!consent && (
        <p className="text-center text-[11.5px] text-mut">We cannot call you without this. It is the law in India, not a formality.</p>
      )}
    </form>
  );
}
