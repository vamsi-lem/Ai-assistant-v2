/**
 * The enquiry form. The entry point to the whole pipeline.
 *
 * The consent checkbox is not decoration. India prohibits cold calling and
 * requires explicit digital consent before a commercial call, so ticking this
 * box is what makes the call lawful. The exact wording is sent to the backend
 * and stored against the lead, because in a complaint you need to show what
 * the person actually agreed to.
 */

import { useState } from 'react';

import type { LeadInput } from '../types';

/**
 * Stored verbatim as consent evidence. If you change this wording, you change
 * what you can prove, so change it deliberately.
 */
export const CONSENT_TEXT =
  'I agree to receive an automated AI voice call about this enquiry.';

const COURSES = [
  'MBBS Admission',
  'MD / MS Postgraduate',
  'BDS Admission',
  'Nursing',
  'Allied Health Sciences',
  'Other',
];

interface Props {
  onSubmit: (input: LeadInput) => Promise<void>;
  busy: boolean;
}

export function LeadForm({ onSubmit, busy }: Props) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [course, setCourse] = useState(COURSES[0]);
  const [notes, setNotes] = useState('');
  const [consent, setConsent] = useState(false);

  const canSubmit =
    name.trim().length >= 2 && phone.trim().length >= 10 && consent && !busy;

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
    <form className="card" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label htmlFor="name">Your name</label>
        <input
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Priya Sharma"
          autoComplete="name"
          required
        />
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="phone">Mobile number</label>
          <input
            id="phone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="98765 43210"
            inputMode="tel"
            autoComplete="tel"
            required
          />
          <span className="hint">
            A 10 digit Indian number is fine. We add +91 for you.
          </span>
        </div>

        <div className="field">
          <label htmlFor="email">
            Email <span className="optional">optional</span>
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="priya@example.com"
            autoComplete="email"
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="course">What are you enquiring about</label>
        <select id="course" value={course} onChange={(e) => setCourse(e.target.value)}>
          {COURSES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="notes">
          Anything else <span className="optional">optional</span>
        </label>
        <textarea
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Looking at this year's intake, would like to know about the process."
        />
      </div>

      <label className="consent" htmlFor="consent">
        <input
          id="consent"
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        <span>
          {CONSENT_TEXT} <strong>Required.</strong>
        </span>
      </label>

      <button type="submit" disabled={!canSubmit}>
        {busy ? 'Connecting…' : 'Talk to Maya now'}
      </button>

      {!consent && (
        <p className="hint center">
          We cannot call you without this. It is the law in India, not a formality.
        </p>
      )}
    </form>
  );
}
