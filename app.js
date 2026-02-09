(async function(){
  const status = document.getElementById("status");
  const day = document.getElementById("day");
  const diagnosis = document.getElementById("diagnosis");
  const agon = document.getElementById("agon");
  const mandate = document.getElementById("mandate");
  const artifact = document.getElementById("artifact");
  const build = document.getElementById("build");

  try{
    const r = await fetch("reports/latest.json?bust=" + Date.now(), {cache:"no-store"});
    if(!r.ok) throw new Error("Fetch failed: " + r.status);
    const j = await r.json();

    status.textContent = "";
    day.textContent = `DAY ${String(j.day_number ?? "").padStart(3,"0")} — ${j.date ?? ""}`;

    diagnosis.textContent = j.diagnosis ?? "";

    const agonText =
      (j.agon?.summary ? j.agon.summary + "\n\n" : "") +
      (j.agon?.winner ? ("Winner: " + j.agon.winner) : "");
    agon.textContent = agonText.trim();

    const m = j.mandate || {};
    const lines = [
      `Compose: ${m.medium ?? ""}`.trim(),
      `Emotional axis: ${m.emotional_axis ?? ""}`.trim(),
      `Constraint(s): ${(m.constraints || []).join("; ")}`.trim(),
      `Timebox: ${(m.timebox_hours ?? 8)} hours`.trim(),
      `Deliverable: ${m.deliverable ?? ""}`.trim()
    ].filter(Boolean);
    mandate.textContent = lines.join("\n");

    if (j.artifact?.status === "DONE" && j.artifact?.url){
      artifact.innerHTML = `DONE — <a href="${j.artifact.url}">Open</a>`;
    } else {
      artifact.textContent = "PENDING";
    }

    if (j.engine?.version) build.textContent = `ENGINE v${j.engine.version}`;
  }catch(e){
    status.textContent = "Report unavailable right now.";
    diagnosis.textContent = "";
    agon.textContent = "";
    mandate.textContent = "";
    artifact.textContent = "";
    console.error(e);
  }
})();