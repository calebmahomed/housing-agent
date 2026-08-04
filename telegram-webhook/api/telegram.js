const HELP_TEXT =
  "Commands:\n" +
  "/run — check for new listings right now, instead of waiting for the next automatic run\n" +
  "/help — show this message";

async function reply(text) {
  await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: process.env.TELEGRAM_CHAT_ID, text }),
  });
}

async function triggerPollRun() {
  await fetch(
    `https://api.github.com/repos/${process.env.GITHUB_REPO}/actions/workflows/poll.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.GH_PAT}`,
        Accept: "application/vnd.github+json",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(200).send("ok");
    return;
  }

  const message = req.body?.message || req.body?.channel_post;
  if (!message || String(message.chat?.id) !== String(process.env.TELEGRAM_CHAT_ID)) {
    res.status(200).send("ignored");
    return;
  }

  const command = (message.text || "").trim().split("@")[0]; // strip "@BotName" used in groups

  if (command === "/run") {
    await triggerPollRun();
    await reply("On it — checking for new listings now.");
  } else if (command === "/help") {
    await reply(HELP_TEXT);
  }

  res.status(200).send("ok");
}
