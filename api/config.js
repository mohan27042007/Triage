module.exports = (request, response) => {
  const apiBaseUrl = process.env.TRIAGE_API_BASE_URL || "";
  response.setHeader("Content-Type", "application/javascript; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.status(200).send(`window.TRIAGE_API_BASE_URL = ${JSON.stringify(apiBaseUrl)};`);
};
