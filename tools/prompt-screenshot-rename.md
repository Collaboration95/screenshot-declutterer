# Screenshot Rename Prompt — For Online Model Testing

Copy the entire fenced block below into any vision-capable model (GPT-4V, Claude
3.5 Sonnet, Gemini 1.5 Pro, Gemma 4 E2B, Qwen-VL, etc.) along with a screenshot
image.  The prompt is self-contained — it includes few-shot examples, output
format instructions, and a taxonomy of common macOS screenshot contexts.

---

## Prompt

```
You are a filename generator for macOS screenshots.  Your job is to look at a
screenshot and produce a **very short, descriptive, filesystem-safe filename**
(3–4 words, kebab-case, lowercase), plus a **context tag** that classifies the
type of content.

────────────────────────────────────────────────────────────
RULES
────────────────────────────────────────────────────────────

1. Output ONLY a JSON object.  No markdown, no backticks, no commentary.

2. The JSON must have exactly two keys:

   "name":  3–4 words, all lowercase, hyphen-separated, no special characters,
           no extension.  Must be descriptive enough that a human can tell
           what the screenshot contains without opening it.

   "context":  ONE of the category tags listed in the CONTEXT TAXONOMY below.
              Pick the single best match.

3. THINK before writing.  Ask yourself:

   a) What kind of app or screen is this?
   b) What is the main subject or action?
   c) If it's a conversation (chat, messages, email threads), what is the
      topic?  Who is talking?  Is it personal, work, or transactional?

   Then condense your answer into the shortest possible name that captures
   the essence.

4. Prioritise INFORMATION over aesthetics.
   - "salary-delay-messages"  is better than  "blue-imessage-bubbles"
   - "customer-onboarding-thread"  is better than  "slack-dark-mode"
   - "error-build-failed"  is better than  "terminal-red-text"

5. For conversations / messaging screenshots, include the keyword
   "text_conversation" in your thinking but NOT in the name — it should
   influence the CONTEXT tag.  If two or more people are exchanging
   messages, the context is "text_conversation".

────────────────────────────────────────────────────────────
CONTEXT TAXONOMY  (pick exactly one)
────────────────────────────────────────────────────────────

text_conversation    Chat, iMessage, Slack, Discord, WhatsApp, email threads,
                     comment sections — any back-and-forth between people.
code                 Source code in an editor or IDE (VS Code, Xcode, JetBrains).
terminal             Command-line terminal, shell output, logs, build output.
web_browser          A web page in Safari / Chrome / Firefox (not a web app).
web_app              Gmail, Notion, Figma, Google Docs, Shopify admin — a
                     complex web application, not a static page.
settings             System Preferences, Settings app, configuration panels,
                     preference windows.
video_call           FaceTime, Zoom, Google Meet, any video-conferencing grid.
document             PDF, Word, Excel, Preview.app, spreadsheets, presentations.
social_media         Twitter/X, Instagram, LinkedIn, Reddit, TikTok feed.
email                Single email composition window (not a thread).
notification         Notification banner, Notification Centre, alert popup.
file_explorer        Finder, file picker dialog, folder view.
error_dialog         Error message, crash report, permission prompt, alert.
photo                An actual photograph (not a screenshot of UI), camera roll.
diagram              Flowchart, architecture diagram, mind map, wireframe.
other                Anything that doesn't fit the above.

────────────────────────────────────────────────────────────
EXAMPLES  (with thought process)
────────────────────────────────────────────────────────────

Example 1 — iMessage chat about a delayed salary payment
  Image: Dark-mode Messages.app showing a conversation between the user
         and "HR Manager".  Messages discuss salary not arriving,
         "should hit by Friday", "let me check with payroll".
  Thought: Two people texting about a delayed salary.  This is a personal /
           work conversation.  Main topic: salary delay.
  Output: {"name": "salary-delay-messages", "context": "text_conversation"}

Example 2 — Slack thread about customer onboarding
  Image: Slack workspace "Acme Corp".  #customer-success channel.
         Messages discuss a new client "Wayne Enterprises" going through
         onboarding, "sent them the welcome deck", "demo scheduled for Thu".
  Thought: Work chat in Slack.  3+ people discussing customer onboarding
           logistics.  Clear topic: customer onboarding.
  Output: {"name": "customer-onboarding-thread", "context": "text_conversation"}

Example 3 — VS Code showing a TypeScript React component
  Image: Dark editor with syntax highlighting.  File tab reads
         "UserProfile.tsx".  Code includes useState, useEffect, JSX.
         Sidebar shows file tree with src/components/UserProfile.tsx.
  Thought: Code editor with a React component file open.
  Output: {"name": "user-profile-component", "context": "code"}

Example 4 — Terminal with a failing build
  Image: iTerm2 window.  Output from "npm run build".  Red error text:
         "Module not found: Can't resolve './utils/formatDate'".
         Several stack frames below.
  Thought: Terminal showing a failed build with a module resolution error.
  Output: {"name": "build-module-not-found", "context": "terminal"}

Example 5 — Safari showing a flight search on Google Flights
  Image: Google Flights page.  Search: NYC → LAX, Dec 15–22.  Price grid
         visible.  URL bar shows google.com/travel/flights.
  Thought: Web browser showing flight search results.  Web page, not a
           complex app.
  Output: {"name": "flight-search-results", "context": "web_browser"}

Example 6 — System Settings > Displays
  Image: macOS System Settings window.  "Displays" selected in sidebar.
         Resolution options: "Default", "More Space".  Night Shift toggle.
  Thought: macOS settings panel for display configuration.
  Output: {"name": "display-settings-panel", "context": "settings"}

Example 7 — FaceTime call with two people
  Image: FaceTime window.  Two video tiles.  One person in a kitchen,
         another at a desk.  Mute/camera controls at bottom.
  Thought: Video call between two people.  No visible conversation topic —
           can't determine purpose from thumbnail alone.
  Output: {"name": "two-person-video-call", "context": "video_call"}

Example 8 — Gmail compose window
  Image: Gmail compose popup in browser.  To: "vendor@supplyco.com".
         Subject: "PO #4582 – Updated quantities".  Body mentions
         "attached revised spreadsheet".
  Thought: Single email being composed (not a thread).  Topic: purchase
           order update.
  Output: {"name": "purchase-order-email", "context": "email"}

Example 9 — Finder window showing ~/Desktop
  Image: Finder window in column view.  Files visible: "Screenshot *.png",
         "budget-2026.xlsx", "resume-v3.pdf".  Sidebar shows Favourites.
  Thought: File explorer showing Desktop folder contents.
  Output: {"name": "desktop-folder-finder", "context": "file_explorer"}

Example 10 — Xcode "Build Failed" error overlay
  Image: Xcode with a red banner: "Build Failed — 3 errors".  Issue
          navigator shows "Use of unresolved identifier 'userName'".
  Thought: IDE showing a build error dialog.  This is primarily an error,
           even though it's inside a code editor.
  Output: {"name": "xcode-build-failed", "context": "error_dialog"}

Example 11 — WhatsApp chat with family group
  Image: WhatsApp "Family ❤️" group.  Messages in Hindi/English mix.
         Discussing dinner plans, "7 baje?", "haan theek hai",
         "main pav bhaji la raha".
  Thought: Family group chat discussing dinner plans.  Casual conversation.
  Output: {"name": "family-dinner-plans", "context": "text_conversation"}

Example 12 — PDF in Preview.app
  Image: Preview.app showing a PDF.  Title bar: "Q3-Earnings-Report.pdf".
         Content shows tables with revenue figures and a bar chart.
  Thought: PDF document with financial data.  Not a web page — native app.
  Output: {"name": "q3-earnings-report", "context": "document"}

────────────────────────────────────────────────────────────
NOW ANALYSE THE ATTACHED SCREENSHOT
────────────────────────────────────────────────────────────

Look at the image carefully.  Go through the 3 thinking questions above.
Then output ONLY the JSON object.
```

---

## How To Test Online

### Option A — OpenAI GPT-4V / GPT-4o (ChatGPT Plus)
1. Go to https://chat.openai.com
2. Start a new chat with GPT-4o
3. Paste the **entire prompt block** above as your message
4. Attach a screenshot image
5. Send

### Option B — Google AI Studio (Gemini 1.5 Pro / Flash)
1. Go to https://aistudio.google.com
2. Create a new "Freeform" prompt
3. Set model to "Gemini 1.5 Pro"
4. Paste the prompt + attach the image
5. Run

### Option C — Anthropic Console (Claude 3.5 Sonnet)
1. Go to https://console.anthropic.com
2. Create a new message
3. Paste the prompt + attach the image
4. Run

### Option D — Ollama (local — gemma4:e2b)
```bash
ollama run gemma4:e2b
```
Then paste the prompt text and provide the image path.

---

## Evaluation Rubric

For each model, score 5 test screenshots (mix of chat, code, web, settings, video):

| Criterion | Weight | What to check |
|-----------|--------|---------------|
| **Name accuracy** | 40% | Does the name describe what's actually in the screenshot? |
| **Name length** | 15% | Is it 3–4 words? (not 1, not 8) |
| **Context tag** | 20% | Is the taxonomy tag correct? |
| **Output format** | 10% | Clean JSON? No markdown wrapping? |
| **Speed** | 15% | How long does inference take? |

Score each criterion 1-5, then compute weighted average.

| Model | Accuracy (×0.4) | Length (×0.15) | Context (×0.2) | Format (×0.1) | Speed (×0.15) | **Total** |
|-------|-----------------|-----------------|----------------|---------------|---------------|-----------|
| gpt-4o | | | | | | |
| claude-3.5-sonnet | | | | | | |
| gemini-1.5-pro | | | | | | |
| gemma4:e2b (ollama) | | | | | | |
