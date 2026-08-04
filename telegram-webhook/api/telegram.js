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

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(200).send("ok");
    return;
  }

  console.log("body", JSON.stringify(req.body));

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
