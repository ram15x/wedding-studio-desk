# Two-minute Ishqweds demo recording

Use the Railway guest link and the family link in two browser tabs. Keep the
recording continuous and show the visible result after each action. Use only
the synthetic demo guest list and do not show passwords, API keys, or private
guest details.

## Before recording

- Confirm the guest list and wedding-details sheet are the synthetic demo files.
- Sign in to the family desk in one tab. Open the guest link in another.
- Use three different synthetic guest phone numbers from the uploaded list.
- Open the family dashboard where headcounts, arrivals, pickup list, and inbox
  are visible.

## Run of show (about 120 seconds)

**0:00–0:12 — Show both sides.** Briefly show the guest chat and the family
dashboard. Say that the guest list and wedding facts are already loaded.

**0:12–0:38 — RSVP in natural Hinglish.** Log in as one demo guest and send:

```text
Hum 2 log aayenge shaadi mein, reception nahi aa paayenge
```

Show the reply and then the family dashboard: Wedding changes to coming,
Reception changes to not coming, and the headcount reflects two people.

**0:38–0:54 — Count-only RSVP.** In a second guest session, send:

```text
Hum 6 log aayenge
```

Show that the guest is marked coming. If the invite lists fewer than six, show
the family inbox flag asking the family to confirm the larger group.

**0:54–1:08 — Acknowledgement.** Send `ok` or `thanks` from a guest. Show the
friendly reply and that no family question was created.

**1:08–1:24 — Wedding detail in the guest's language.** Ask:

```text
Sangeet ka time kya hai?
```

Show the human sentence with both the date and time, taken from the uploaded
details sheet.

**1:24–1:48 — Unknown question and family reply.** Ask a detail not present in
the sheet, such as `Can I bring my dog?` Show it in the family inbox, type a
reply, and show that reply in the same guest chat.

**1:48–2:00 — Close on the dashboard.** Show the updated per-function count and
arrival/pickup list. State that unanswered facts are escalated instead of
guessed.

## If a live step fails

Do not edit the database or replay hidden API calls while recording. Stop,
capture the failure for debugging, and record again after the underlying issue
is fixed. A scripted recording must show the real live UI and current behavior.
