# Slot booking, meeting links and WhatsApp

What happens when a lead agrees a time on the call:

```
lead: "tomorrow evening around six"
Maya: works out the exact moment from today's date, calls book_slot
backend:
  1. saves the booking                          (always)
  2. creates a Zoom or Google Meet link         (if MEETING_PROVIDER is set)
  3. sends the link to the lead on WhatsApp     (if WHATSAPP_PROVIDER is set)
Maya: "Booked for Tuesday, 22 September at 6 pm. The link is on your WhatsApp."
counsellor: sees it on the lead page and under Appointments, with the link
            and the WhatsApp status
```

Steps 2 and 3 are each optional and each can fail without losing the
booking. Whatever did not happen is written on the booking and shown in
red on the dashboard, with a Resend button for the WhatsApp.

The booking needs one new table. Run `supabase/migrations/0002_bookings.sql`
in Supabase -> SQL Editor once.

## Stage 1: booking only (no accounts needed)

```
MEETING_PROVIDER=none
WHATSAPP_PROVIDER=none
```

Restart, make a call, agree a time. Sign in to the dashboard and open the
lead. The booking is there, marked "no link" and "WhatsApp skipped". That
proves the time was understood and saved. Do this first.

## Stage 2: meeting links

Set up one or both. Zoom is three values and ten minutes. Google Meet is a
one-time sign-in dance and better if counsellors live in Google Calendar.

With both configured, Maya asks the lead on the call whether they prefer
Google Meet or Zoom. A lead who names one gets that one; a lead who says
anything is fine gets the platform in `MEETING_PROVIDER`, which is the
default. With only one configured she does not ask. The dashboard's Join
button says which platform the link is for.

### Zoom

1. marketplace.zoom.us, sign in with the counsellor's Zoom account (a free
   account works).
2. Top right: Develop -> Build App -> Server-to-Server OAuth -> Create.
   Name it `maya-bookings`.
3. App Credentials tab: copy **Account ID**, **Client ID**, **Client Secret**.
4. Scopes tab: add `meeting:write:admin` (on some accounts it is listed as
   `meeting:write:meeting:admin`; add whichever is offered).
5. Activation tab: Activate.

```
MEETING_PROVIDER=zoom
ZOOM_ACCOUNT_ID=
ZOOM_CLIENT_ID=
ZOOM_CLIENT_SECRET=
```

### Google Meet

Google will not hand Meet links to a plain server key on a normal Gmail
account, so the backend acts as the counsellor's Google account, authorised
once.

1. console.cloud.google.com -> New project `maya-bookings`.
2. APIs & Services -> Enable APIs -> enable **Google Calendar API**.
3. OAuth consent screen -> External -> fill in the app name and your email
   -> add the counsellor's Gmail under Test users.
4. Credentials -> Create credentials -> OAuth client ID -> type
   **Web application** -> under Authorised redirect URIs add
   `https://developers.google.com/oauthplayground` -> Create. Copy the
   **Client ID** and **Client secret**.
5. Open developers.google.com/oauthplayground. Click the gear (top right),
   tick "Use your own OAuth credentials", paste the ID and secret.
6. In the left list find Google Calendar API v3, tick
   `https://www.googleapis.com/auth/calendar.events`, click Authorize APIs,
   sign in as the counsellor, allow.
7. Click "Exchange authorization code for tokens". Copy the
   **Refresh token**.

```
MEETING_PROVIDER=google
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_CALENDAR_ID=primary
```

Events land on that Google account's calendar with the lead as an attendee
when they gave an email.

## Stage 3: WhatsApp

Meta's WhatsApp Cloud API. Free to set up; utility messages in India cost
under a rupee each. The one rule that shapes everything: a business may
only start a WhatsApp conversation with a **pre-approved template**, so the
message text lives in Meta's dashboard, not in code.

1. developers.facebook.com -> My Apps -> Create App -> type **Business**.
2. Add product **WhatsApp**. This creates a test phone number and shows
   API Setup.
3. On API Setup copy **Phone number ID** and generate a **temporary access
   token** (24 hours, fine for testing). For production, create a System
   User in business.facebook.com with a permanent token; the docs page
   linked there walks through it.
4. Under "To", add your own mobile as a test recipient and verify it. The
   test number can only message up to five verified recipients until you
   attach a real business number.

First test, with the template Meta pre-approves for everyone:

```
WHATSAPP_PROVIDER=meta
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_TEMPLATE_NAME=hello_world
WHATSAPP_TEMPLATE_LANGUAGE=en_US
```

Make a call, agree a time, and the hello_world message should arrive on
your phone. That proves the token, the number and the recipient.

Then the real template. In business.facebook.com -> WhatsApp Manager ->
Message templates -> Create:

- Name: `booking_confirmation`
- Category: **Utility**
- Language: English
- Body:

```
Hi {{1}}, thanks for speaking with us about {{2}}.
Your counsellor session is booked for {{3}}.
Join here: {{4}}
Team {{5}}
```

Add sample values when asked (Meta needs them for review). Approval is
usually minutes, sometimes a day. When it shows Approved:

```
WHATSAPP_TEMPLATE_NAME=booking_confirmation
WHATSAPP_TEMPLATE_LANGUAGE=en
```

If a booking was made while the template was pending, its WhatsApp status
is red on the dashboard with Meta's reason; press Resend once approved.

Going live later means attaching your own business number (the Plivo
number cannot be used for WhatsApp; you need a number that receives an
SMS or call for verification) and completing Meta business verification.

## Where each piece lives

| Piece | File |
| --- | --- |
| Table and dashboard view | `supabase/migrations/0002_bookings.sql` |
| Book, list, resend, status endpoints | `backend/app/routers/bookings.py` |
| Zoom and Google Meet | `backend/app/services/meetings/` |
| WhatsApp (Meta) | `backend/app/services/whatsapp/` |
| The agent's `book_slot` tool and the date it reasons from | `agent/src/main.py`, `agent/src/prompts.py` |
| Counsellor page | `frontend/src/components/CounsellorDashboard.tsx` |

## How Maya gets the time right

The call follows a six stage script in `agent/src/prompts.py`: identity,
interest, offer the session, get the exact slot, book, close. She may not
name a time herself; the lead has to say the day and the time, she reads
it back, and only a yes lets her book.

The brain never does date arithmetic. On a real call it was asked to and
produced a date six months in the past, four times in a row. Now it
passes the lead's words, day and time separately ("tomorrow", "six thirty
evening"), and `agent/src/slots.py` works out the exact moment in code:
today, tomorrow, day after tomorrow, weekday names, dates like "22
September", clock times, "half past six", "saade chhe", "ఆరున్నర", with
morning or evening words in English, Hindi and Telugu. A bare "six" is
placed inside the counsellor's working hours (`COUNSELLOR_WORK_START` and
`COUNSELLOR_WORK_END`), so it means 6 pm. Anything missing comes back to
the brain as the exact question to ask, never a guess.

Two more checks sit in front of that: `book_slot` refuses when none of the
last few things the lead said contains a day or a time, so a slot the
brain made up cannot be booked; and the backend refuses a time in the past
or more than sixty days out. The transcript and the dashboard both keep
the lead's own words for the slot next to the exact time, so a wrong
reading is visible and fixable.
