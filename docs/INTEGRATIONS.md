# Slot booking, Zoom link and WhatsApp: how it is built

Short reference for the booking chain in AI Voice Platform v2. What happens
on a call, which services and APIs are involved, what was configured where,
and what to do when something stops working.

## 1. What happens on a call

```
lead fills the web form
   -> backend saves the lead (Supabase)
   -> backend asks LiveKit to dial the lead's phone through Plivo
   -> Maya (the agent) joins the room and greets the lead
   -> lead picks a language, says a day and a time
   -> agent code turns the words into an exact time (slots.py)
   -> agent calls the backend: POST /api/bookings
        1. booking saved in Supabase          (always)
        2. Zoom meeting created               (MEETING_PROVIDER=zoom)
        3. WhatsApp message sent with the link (WHATSAPP_PROVIDER=meta)
   -> Maya confirms the day, time and that the link was sent, says goodbye
   -> counsellor sees the booking at /#/counsellor with Join Zoom
```

Steps 2 and 3 are each optional. If either fails, the booking is still
saved and the dashboard shows the reason in red with a Resend button.

## 2. Technologies and services

| Layer | What we use | Why |
| --- | --- | --- |
| Phone line | Plivo (Zentrunk SIP trunk, Indian number) | Carrier that rings the lead |
| Call room | LiveKit Cloud (rooms, SIP bridge, agents framework) | Carries the audio and runs the agent |
| Ears (speech to text) | Sarvam saarika, codemix mode | Hindi, Telugu and English in one sentence |
| Voice (text to speech) | Sarvam bulbul:v3, speaker priya | Natural Indian voices, all offered languages |
| Brain (LLM) | Google Gemini flash-lite (free tier, testing). Switchable to OpenAI gpt-4o-mini or Groq gpt-oss | Decides what to say and when to call tools |
| Date arithmetic | Our own code, agent/src/slots.py | Models got dates wrong; code does not |
| Backend | Python, FastAPI | API for leads, calls, bookings, dashboard |
| Database | Supabase (Postgres) | Leads, calls, transcripts, bookings |
| Meeting link | Zoom API, Server to Server OAuth app | Creates a meeting per booking |
| WhatsApp | Meta WhatsApp Cloud API (Graph API) | Sends the approved template with the link |
| Frontend | Next.js, Tailwind | Public lead form and the counsellor dashboard (frontend/README.md) |

Google Meet is also implemented (Google Calendar API with a refresh token)
but has not been tested yet; Zoom is the one in use.

## 3. Zoom: what was set up

1. marketplace.zoom.us, Develop, Build App, **Server to Server OAuth**.
2. App name `maya-bookings`. From the App Credentials tab: Account ID,
   Client ID, Client Secret.
3. Scopes: `meeting:write:admin` (shown on some accounts as
   `meeting:write:meeting:admin`).
4. Activation tab: Activate.

`backend/.env`:

```
MEETING_PROVIDER=zoom
ZOOM_ACCOUNT_ID=
ZOOM_CLIENT_ID=
ZOOM_CLIENT_SECRET=
```

How it works: the backend exchanges the three values for a short lived
access token (`account_credentials` grant) and calls
`POST /users/me/meetings` with the booking time and a 30 minute duration.
The join URL is stored on the booking and used in the WhatsApp message and
on the dashboard. Code: `backend/app/services/meetings/zoom.py`.

## 4. WhatsApp: what was set up

Meta only lets a business start a WhatsApp conversation with a template it
has approved in advance. So the message text lives in Meta's dashboard,
and the backend only fills in the five blanks.

### Account and app (one time)

1. developers.facebook.com: create a developer account (phone number added
   through Accounts Center, then verified by SMS).
2. My Apps, Create App, use case **Connect with customers through
   WhatsApp**, app type Business. App name `AI-assistant`.
3. Business portfolio `Lemniscate Growth` created and attached to the app.
4. Use cases, Customize, **Step 1. Try it out**. This page gives:
   - a test sender number (+1 555 174 7027)
   - **Phone Number ID** (goes in `.env`)
   - **Generate token** (temporary access token, 24 hours)
   - the **To** list where test recipients are added and verified by OTP

The test number can only message up to five verified recipients.

### Template (one time, needs Meta approval)

business.facebook.com, WhatsApp Manager, Message templates, Create:

- Name `booking_confirmation`, category Utility, language English
- Body:

```
Hi {{1}}, thanks for speaking with us about {{2}}.
Your counsellor session is booked for {{3}}.
Join here: {{4}}
Team {{5}} wishes you all the best.
```

The last line ends with words because Meta rejects a variable at the very
end. Sample values are required for review. Approval took under an hour.

### Backend configuration

`backend/.env`:

```
WHATSAPP_PROVIDER=meta
WHATSAPP_PHONE_NUMBER_ID=1271873966016805
WHATSAPP_ACCESS_TOKEN=            (never commit; regenerate when expired)
WHATSAPP_TEMPLATE_NAME=booking_confirmation
WHATSAPP_TEMPLATE_LANGUAGE=en
```

How it works: the backend calls
`POST https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages` with
`type: template`, the template name and language, and the five body
parameters: lead name, course, spoken date and time, meeting link, company
name. Code: `backend/app/services/whatsapp/meta.py`.

Before the template was approved, `hello_world` / `en_US` (Meta's built in
sample) was used to prove the connection.

## 5. Where each piece lives

| Piece | File |
| --- | --- |
| Turn the lead's words into a time | `agent/src/slots.py` |
| The book_slot tool the brain calls | `agent/src/main.py` |
| Conversation script (short and full flows) | `agent/src/prompts.py` |
| Booking endpoint: save, link, WhatsApp | `backend/app/routers/bookings.py` |
| Zoom and Google Meet | `backend/app/services/meetings/` |
| WhatsApp (Meta) | `backend/app/services/whatsapp/` |
| Bookings table and dashboard view | `supabase/migrations/0002_bookings.sql` |
| Counsellor page | `frontend/src/components/CounsellorDashboard.tsx` |

## 6. Common errors and what they mean

| Dashboard shows | Meaning | Fix |
| --- | --- | --- |
| Meta refused (401): Authentication Error (190) | Access token expired (24 hours) | Generate token again on the Meta page, update `WHATSAPP_ACCESS_TOKEN`, restart backend, press Resend |
| Meta refused (404): template name does not exist (132001) | Template not approved yet, or wrong language code | Wait for Active in WhatsApp Manager; language must match the template ("English" is `en`, "English (US)" is `en_US`) |
| Meta refused (400): recipient not in allowed list | Test number can only message verified phones | Add and verify the phone in the To list on the Meta page |
| No link: Zoom error | Zoom credentials wrong or app not activated | Check the three ZOOM values and the Activation tab |
| WhatsApp skipped | `WHATSAPP_PROVIDER=none` | Set to `meta` and fill the values |

## 7. Before going live

- Replace the 24 hour token with a permanent one: business.facebook.com,
  Business settings, System users, create one, assign the app, generate a
  token with `whatsapp_business_messaging` and
  `whatsapp_business_management`. It does not expire.
- Attach your own WhatsApp business number (a number not used by any
  WhatsApp app, able to receive an SMS or call for verification). The
  Plivo number cannot be used for WhatsApp.
- Complete Meta business verification so the number can message anyone,
  not just the five test recipients.
- Move the brain to a paid tier (OpenAI, or Gemini paid) so free tier
  limits and data use terms no longer apply.
- Deploy backend and agent to the cloud (see docs/DEPLOY.md) so calls do
  not depend on a laptop being on.
