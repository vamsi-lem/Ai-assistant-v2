# Phone calls through Plivo

Browser calls need nothing from this page. This is the wiring for Maya to
ring a real mobile.

## How it works

```
lead form  ->  backend creates call-<id>  ->  LiveKit dials +91... via Plivo
                                                    |
                    agent joins the room, waits for "answered", greets
```

LiveKit does the dialling. Plivo is the SIP trunk that carries the call onto
the Indian phone network. Plivo never calls a webhook and never fetches any
XML, so the backend needs no public URL for this. It works from a laptop.

Three things have to exist, in this order.

## 1. Plivo: an outbound SIP trunk

Plivo's SIP trunking product is called Zentrunk. In the Plivo console:

1. **SIP Trunking (Zentrunk) -> Outbound Trunks -> Credentials -> Create.**
   Choose a username (5 to 20 letters and digits) and a password (5 to 20
   characters, at least one of `~!@#$%^&*()_+`). Write both down; LiveKit
   needs them in step 2.
2. **Outbound Trunks -> Create Trunk.** Name it `livekit`. Under Trunk
   Authentication pick the credential you just made. Leave Secure Trunking
   off for now (if you turn it on, use `transport=tls` in step 2).
3. Save, then copy the **Termination SIP Domain**. It looks like
   `abcdef123456.zt.plivo.com`.

If the SIP Trunking menu is missing from your console, Zentrunk is not
enabled on the account. Ask Plivo support to enable it; it is a switch on
their side, not a new product to buy.

## 2. LiveKit: an outbound trunk that points at Plivo

Either in the dashboard (cloud.livekit.io -> Telephony -> SIP Trunks ->
Create trunk -> Outbound) or with the CLI. The CLI is exact, so use it.

Install the CLI once (Windows PowerShell, from the project root):

```powershell
winget install LiveKit.LiveKitCLI
lk cloud auth
```

Create a file `outbound-trunk.json` (do NOT commit it; it holds the Plivo
password):

```json
{
  "trunk": {
    "name": "plivo-india",
    "address": "abcdef123456.zt.plivo.com;transport=tcp",
    "numbers": ["+918012345678"],
    "auth_username": "your-plivo-credential-username",
    "auth_password": "your-plivo-credential-password",
    "destination_country": "in"
  }
}
```

Replace the address with your Termination SIP Domain, the number with your
`PLIVO_FROM_NUMBER`, and the two credential fields with step 1's values.

```powershell
lk sip outbound create outbound-trunk.json
```

It prints an id starting with `ST_`. That is `LIVEKIT_SIP_TRUNK_ID`. Delete
`outbound-trunk.json` afterwards.

`destination_country: "in"` asks LiveKit to originate the call from inside
India, which Indian telecom rules require for domestic numbers. On LiveKit's
pricing page this ("region pinning") is listed under the Scale plan. If the
create command refuses the field on your plan, remove that line and test;
if Plivo then rejects the calls, the plan is the fix, and the honest
alternative is self-hosting LiveKit's SIP service on an Indian server.

## 3. backend/.env

```
CALL_TRANSPORT=phone
TELEPHONY_ENABLED=true
PLIVO_FROM_NUMBER=+918012345678
LIVEKIT_SIP_TRUNK_ID=ST_xxxxxxxxxxxx
```

`PLIVO_AUTH_ID` and `PLIVO_AUTH_TOKEN` can stay set; they are only used to
verify Plivo webhooks, which this path does not use. `LIVEKIT_SIP_URI` stays
blank. Restart the backend; the boot line should read
`phone via plivo from +91...` and the health endpoint should show the trunk.

## First test

1. Start backend and agent as usual.
2. Submit the form with your own mobile number.
3. Your phone rings from the Plivo number. Answer. Maya greets you after a
   beat (she waits for LiveKit to report the leg as active).
4. In `agent/agent.log` look for `Phone call: waiting`, `Phone leg ...:
   ringing`, `... active`, then the usual `Lead chose ...`.

If the phone never rings, the backend log has LiveKit's exact refusal
(`LiveKit could not place the call: ...`). The common ones:

| Message contains | Meaning |
| --- | --- |
| `trunk not found` | wrong `LIVEKIT_SIP_TRUNK_ID` |
| `401` or `403` from the address | Plivo credential username or password wrong |
| `403 Forbidden` after ringing starts | Plivo blocked the destination: KYC incomplete, or number not allowed for this trunk |
| `no route` or `404` | the termination domain is wrong, or Zentrunk is not enabled |

If it rings but you hear nothing, the agent did not join: check the agent
window is running and its log for the room name.

## What Maya may say on this number

India's commercial-calling rules tie content to the number series:

- **140 series**: promotional calls only.
- **Everything else** (landline, mobile, 160): service and transactional
  calls only. No fees, discounts, offers or other courses. Maya's prompt is
  written to this rule and she hands anything commercial to a counsellor.

Cold calling is prohibited. Maya calls only leads who submitted the form,
which is the consent that makes the call lawful, and the backend refuses to
dial anyone without it (`check_may_call` in `services/telephony/service.py`).
