(async function(){
  const list = document.getElementById("list");
  try{
    const r = await fetch("reports/index.json?bust=" + Date.now(), {cache:"no-store"});
    if(!r.ok) throw new Error("Fetch failed: " + r.status);
    const j = await r.json();

    // j = { dates: ["2026-02-08", ...] }
    const dates = (j.dates || []).slice().sort().reverse(); // newest first
    list.innerHTML = dates.map(d => {
      const href = `reports/${d.slice(0,4)}/${d.slice(5,7)}/${d}.json`;
      return `<div><a href="${href}">${d}</a></div>`;
    }).join("");
  }catch(e){
    list.textContent = "Archive unavailable.";
    console.error(e);
  }
})();