const HELP_TEXT =
  "Commands:\n" +
  "/run — check for new listings right now, instead of waiting for the next automatic run\n" +
  "/catchup [hours] — re-scan mail from the last N hours (default 12) for anything not yet sent\n" +
  "/help — show this message";

async function reply(text) {
  const resp = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: process.env.TELEGRAM_CHAT_ID, text }),
  });
  console.log("sendMessage status", resp.status, await resp.text());
}

async function triggerWorkflow(workflowFile, inputs) {
  const resp = await fetch(
    `https://api.github.com/repos/${process.env.GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.GH_PAT}`,
        Accept: "application/vnd.github+json",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    }
  );
  console.log("dispatch status", resp.status, await resp.text());
}

// Mirrors housing_agent/feedback.py REASONS — keep the keys in step, they are
// what the workflow looks up to get the wording the scoring prompt reads.
const REASON_BUTTONS = [
  [
    { text: "💸 Too expensive", key: "price" },
    { text: "🚆 Commute", key: "commute" },
  ],
  [
    { text: "📐 Too small", key: "size" },
    { text: "🌿 No outdoor", key: "outdoor" },
  ],
  [{ text: "🤷 Other", key: "other" }],
];

async function telegram(method, payload) {
  const resp = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  console.log(method, "status", resp.status, await resp.text());
}

// A button press can't write to the repo from here — this is a Vercel function
// with no checkout — so it dispatches the workflow that commits the decision.
async function handleCallback(query) {
  const [kind, key, value] = (query.data || "").split(":");
  const base = { chat_id: query.message?.chat?.id, message_id: query.message?.message_id };

  if (kind === "f" && value === "pass") {
    // Ask why before recording: a bare rejection teaches the scorer nothing.
    await telegram("editMessageReplyMarkup", {
      ...base,
      reply_markup: {
        inline_keyboard: REASON_BUTTONS.map((row) =>
          row.map((b) => ({ text: b.text, callback_data: `r:${key}:${b.key}` }))
        ),
      },
    });
    await telegram("answerCallbackQuery", { callback_query_id: query.id, text: "Why pass?" });
    return;
  }

  const decision = kind === "r" ? "pass" : "interested";
  const label = kind === "r" ? "👎 Passed" : "👍 Interested";
  await triggerWorkflow("feedback.yml", { key, decision, reason: kind === "r" ? value : "" });
  // Replace the buttons with what was chosen: shows it landed, and stops a
  // second tap racing the first one's commit.
  await telegram("editMessageReplyMarkup", {
    ...base,
    reply_markup: { inline_keyboard: [[{ text: label, callback_data: "noop" }]] },
  });
  await telegram("answerCallbackQuery", { callback_query_id: query.id, text: "Noted." });
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(200).send("ok");
    return;
  }

  console.log("body", JSON.stringify(req.body));

  const callback = req.body?.callback_query;
  if (callback) {
    if (String(callback.message?.chat?.id) !== String(process.env.TELEGRAM_CHAT_ID)) {
      console.log("chat id mismatch on callback, ignoring");
      res.status(200).send("ignored");
      return;
    }
    if (callback.data && callback.data !== "noop") {
      await handleCallback(callback);
    } else {
      await telegram("answerCallbackQuery", { callback_query_id: callback.id });
    }
    res.status(200).send("ok");
    return;
  }

  const message = req.body?.message || req.body?.channel_post;
  if (!message) {
    console.log("no message/channel_post on update");
    res.status(200).send("ignored");
    return;
  }

  console.log("chat.id", message.chat?.id, "expected", process.env.TELEGRAM_CHAT_ID);
  if (String(message.chat?.id) !== String(process.env.TELEGRAM_CHAT_ID)) {
    console.log("chat id mismatch, ignoring");
    res.status(200).send("ignored");
    return;
  }

  const text = (message.text || "").trim();
  const [rawCommand, ...args] = text.split(/\s+/);
  const command = rawCommand.split("@")[0]; // strip "@BotName" used in groups
  console.log("command", JSON.stringify(command), "args", args);

  if (command === "/run") {
    await triggerWorkflow("poll.yml", {});
    await reply("On it — checking for new listings now.");
  } else if (command === "/catchup") {
    const hours = args[0] && /^\d+$/.test(args[0]) ? args[0] : "12";
    await triggerWorkflow("catchup.yml", { hours });
    await reply(`On it — re-scanning the last ${hours}h for anything not yet sent.`);
  } else if (command === "/help") {
    await reply(HELP_TEXT);
  } else {
    console.log("unrecognized command, no action");
  }

  res.status(200).send("ok");
}
