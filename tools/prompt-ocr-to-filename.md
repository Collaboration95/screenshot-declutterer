# OCR → Filename Prompt — For Text-Only LLM Testing

Use this prompt with any small text-only LLM (SmolLM, Qwen 2.5 1.5B, Gemma 2
2B, Llama 3.2 1B, etc.) running locally via Ollama or similar.  The model
never sees the image — only the raw OCR output from Tesseract.

Copy the entire prompt block below and paste it into the model, replacing
`{ocr_text}` with the actual OCR output.

---

## Prompt

```
You are a screenshot-to-filename converter.  Below is raw text extracted
from a macOS screenshot via Tesseract OCR.  The text may be:

- Messy — UI chrome (buttons, timestamps, phone numbers) mixed with real content
- Garbled — image-heavy screenshots produce mostly noise (you will see this)
- Clean — text-chat screenshots produce excellent output
- Truncated — OCR may miss words at edges or from weird font rendering

Your job is to produce a 3-4 word, lowercase, hyphen-separated filename
that captures THE ESSENCE of what the screenshot is about.

Rules:
1. Output ONLY the filename.  No quotes, no markdown, no explanation.
2. If the OCR is mostly garbled, still try — look for ANY recognisable
   word, app name, or pattern.  If truly hopeless, output "screenshot".
3. Prioritise TOPIC over FORMAT.  "salary-delay-messages" is better
   than "imessage-dark-mode".
4. Names of people in chats are CLUES, not the answer.  "Manoj asks
   about RCA deadline" → "onboarding-deadline-reminder", not "manoj-
   chandra-message".

=== EXAMPLES (real OCR from macOS screenshots) ===

EXAMPLE 1 — Slack chat about customer onboarding
OCR TEXT:
  Manoj Chandra Bhamidipati @Ravi Ankam, if the stable RCA is not
  completed before Sunday, please proceed with proper reliving
  transition to the entire Al team. @Yuva Teja Bandharapu, @Guru,
  @Osho Kothari, and @Vivek, | expect to receive positive
  responses from onboarded customers by Monday morning. | will
  work alongside Al. @Bharat FY!
  ood
  Si
  oO S& S& Sreplies Last reply today at 7:31 PM
FILENAME: customer-onboarding-deadline

EXAMPLE 2 — iMessage chat about delayed salary
OCR TEXT:
  a Cee a Mas SND CN SS OE TS NS OG NS eee Te ee
  10 MAYOS KN WASH NXCO 1:20PM
  +9199124 20002
  ~Bhamidipati Manoj
  Hi Guru, ur
  lary will be settled by next week Wednesday. Im very sorry for
  delay. Arranging funds for next 3 months. It will not happen again
  Hi Manoj , any updates on this ? Is it already processed from your side
  2:31PM
  'On it, | will update by eod 9:31 py
  It will done
  sap. Sorry for delay. 2:35 pM
  Not more than 48. Hours 2:35PM
FILENAME: salary-delay-messages

EXAMPLE 3 — Slack chat about employment status
OCR TEXT:
  Guru, | saw ur profile says open to work. Please remove that. If
  don't like to work here please find another one. Don't use BugRaid
  name. It is ok to switch
  12:45AM
  «
  Iwill remove that then 49.26 any
  Im not asking to remove, keeping open to work either degrade company
  or you. You can pick ur choice
  12:47 AM
  Ican understand ur undervalue at the moment, things will change. But
  u can take decision anytime
  12:48 AM
FILENAME: open-to-work-dispute

EXAMPLE 4 — Video call (FaceTime) — mostly garbled
OCR TEXT:
  | / . ae - > ue ed ae Lae ae
  4 iW 4 tes c 3 a 3
  zg > TM & Create Link New FaceTime Sei aes »| gM J ,
  re yg x
  Mow ia ' >
  i A . : '
  ] ee @ > +1(800) 660-2737 : ~
  A | - | @ <2 Pas -
  .. ! «x = - : | Last Week z
  ; j fw) FR. be Pe ; - eS
  Col aan . = |
  & , a, ' af - j
  1 | . s Z
  . a @ 5 s
  ee om 7 } | 80: ae
  184 5895
  it ~ - = q This Month
  | =
  7 P oa ' rll = @ = 83711393
  4 ' ' 3 ; "4 @ (c)3525 3
  : , - re : ' | 'a e 9868 7824
  - = manyc a= a
  i Boy Mom
  4 - EscC RAT Shs - > Ge i0SSupport @ 2105 2287
  Library am 2/5/25 SSS
FILENAME: facetime-call-history

EXAMPLE 5 — Terminal or git commit
OCR TEXT:
  V5 feature fix #190 7
FILENAME: v5-feature-fix-190

=== NOW PROCESS THIS OCR TEXT ===

{ocr_text}
```
